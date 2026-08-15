"""TF-0235 (volet P4) — le dashboard se conçoit pour SES lecteurs, pas pour sa donnée.

Référentiel : `REFERENTIEL-RESTITUTION.md` de forge-design, famille **« suivi »** — un objet
revisité d un audit à l autre, lu par deux personnes aux questions opposées : le pilote
(« est-ce que ça dérive ? où, depuis quand ? ») et l opérateur (« qu y a-t-il dans la file,
que traiter d abord ? »).

Ce que ces tests protègent, et pourquoi ils ne se contentent pas de l oracle : l oracle de
restitution juge la page RENDUE, et il n est pas installé chez tous les postes. Ici, c est le
GÉNÉRATEUR qui est tenu — le livrable de cette campagne, c est lui (personne ne rattrape à la
main un dashboard produit à chaque run). Chaque règle porte donc ses deux sens : ce que la
page DOIT montrer, et ce qu elle doit REFUSER de montrer quand la donnée n existe pas — une
figure de tendance sans rapport précédent serait une courbe inventée.
"""

from __future__ import annotations

import re

from forge_tests.adaptateurs import REGISTRE
from forge_tests.livrables import dashboard, surface

CONTEXTE = {
    "produit": "Banc Restitution",
    "date": "2026-08-15",
    "rapport_nom": "rapport-banc.json",
    "rapport_sha": "a" * 64,
}


def _rapport(findings: int = 4) -> dict:
    """Un rapport au format du noyau, assez fourni pour armer les règles en cause."""
    return {
        "verdict": "FAIL",
        "couverture_par_pan": {
            "api": {"inventorie": 6, "exerce": 2, "ratio": 0.33, "seuil": 0.9},
        },
        "seuils": {
            "couverture_surface_api": {
                "valeur": 0.9,
                "severite": "bloquant",
                "porte_sur": "pan api",
            },
        },
        "findings": [
            {
                "id": f"code:GET /api/x{i}=200",
                "pan": "api",
                "severite": "bloquant" if i == 0 else "majeur",
                "classe": "assertion-fausse",
                "message": f"constat mesuré numéro {i}",
                "localisation": f"tests/test_x{i}.py:10",
                "risque": 30 - i,
            }
            for i in range(findings)
        ],
        "non_testables": [
            {
                "pan": "qualif",
                "element": "route:/admin",
                "champs_requis": ["FORGE_TESTS_BASE_URL"],
                "motif": "configuration absente",
            }
        ],
        "pans_non_couverts": [],
        "actions": [
            {
                "finding_ref": f"code:GET /api/x{i}=200",
                "categorie": "auto_ia",
                "etape_cible": "development",
                "attendu": f"corriger l assertion du cas x{i}",
            }
            for i in range(findings)
        ],
    }


def _page(rapport: dict, precedent: dict | list[dict] | None = None) -> str:
    return dashboard.construire(
        rapport, CONTEXTE, surface.repartir(rapport, REGISTRE), precedent
    )


# --- Périmètre déclaré (le marqueur que l oracle consomme) --------------------------------------
def test_la_page_declare_sa_famille_de_restitution() -> None:
    """Sans `data-restitution`, l oracle rend SKIP : la page sort du périmètre EN SILENCE.

    « suivi » et pas « rapport » : ce n est pas une nuance de vocabulaire — la famille décide
    des lecteurs servis, donc des règles qui s appliquent.
    """
    assert '<body data-restitution="suivi">' in _page(_rapport())


# --- RL-1 · la vue d ensemble conclut ------------------------------------------------------------
def test_la_vue_d_ensemble_porte_un_verdict_explicite() -> None:
    page = _page(_rapport())
    assert '<div class="verdict" data-verdict="FAIL">' in page
    # Le verdict n est pas un badge posé seul : il dit sur quoi il se prononce.
    assert "seuil(s) opposable(s) non tenu(s)" in page or "seuils opposables sont tenus" in page


def test_la_navigation_de_vues_est_marquee_sur_chaque_entree() -> None:
    page = _page(_rapport())
    vues = set(re.findall(r'data-vue="([a-z-]+)"', page))
    assert {"synthese", "echecs", "actions"} <= vues
    # Chaque vue annoncée existe comme panneau : une entrée de navigation qui ne mène nulle
    # part serait une affordance morte (loi transverse n° 1).
    for vue in vues:
        assert f'<section class="panneau" id="{vue}"' in page


# --- RL-3 · un chiffre porte sa lecture ---------------------------------------------------------
_KPI = re.compile(r'<(?:button|div)[^>]*class="tuile kpi"[^>]*>(.*?)</(?:button|div)>', re.S)


def test_les_kpi_de_la_vue_d_ensemble_sont_complets() -> None:
    """Valeur, définition, repère — et le repère est RATTACHÉ à la valeur (`aria-describedby`).

    Un chiffre sans repère n est pas lu, il est deviné : « 4 constats » ne dit pas si c est
    beaucoup. Le rattachement compte autant que la présence : sans lui, un lecteur d écran
    annonce le nombre seul.
    """
    page = _page(_rapport())
    kpis = _KPI.findall(page)
    assert len(kpis) >= 3, f"{len(kpis)} KPI complets — le référentiel en attend au moins 3"
    for corps in kpis:
        valeur = re.search(
            r'class="chiffre k-valeur" aria-describedby="([^"]+)" data-total="([a-z_]+)"', corps
        )
        assert valeur, "un KPI sans valeur rattachée à son repère"
        definition = re.search(r'class="tuile-d kpi-d">([^<]*)<', corps)
        assert definition and len(definition.group(1)) >= 12
        repere = re.search(r'class="k-repere" id="([^"]+)">([^<]*)<', corps)
        assert repere and len(repere.group(2)) >= 20
        assert repere.group(1) == valeur.group(1), "le repère désigné n est pas celui affiché"


def test_le_repere_dit_l_absence_de_point_de_comparaison() -> None:
    """Le repère d un compteur de SUIVI, c est son point précédent. Absent, il se DIT."""
    sans = _page(_rapport())
    assert "la dérive de ce compteur n est pas mesurable sur ce run" in sans
    avec = _page(_rapport(findings=6), precedent=_rapport(findings=2))
    assert "la dérive de ce compteur n est pas mesurable sur ce run" not in avec
    assert "Le rapport précédent en comptait" in avec


# --- RL-4 · un graphique énonce sa question -----------------------------------------------------
def test_chaque_figure_pose_la_question_a_laquelle_elle_repond() -> None:
    page = _page(_rapport())
    legendes = re.findall(r"<figure class=\"graphe\"><figcaption>(.*?)</figcaption>", page)
    assert legendes, "aucune figure alors que le rapport porte des éléments inventoriés"
    for legende in legendes:
        assert legende.strip().endswith("?"), f"figure sans question : « {legende} »"


def test_une_figure_ne_superpose_jamais_deux_rects_dans_un_meme_svg() -> None:
    """La piste d une barre est le FOND CSS du svg. Deux rects superposés sont un
    chevauchement au sens du contrôle de rendu du socle — et rien ne dit lequel est devant."""
    page = _page(_rapport())
    for svg in re.findall(r"<svg class=\"g-piste\".*?</svg>", page, re.S):
        assert svg.count("<rect") == 1
    for svg in re.findall(r"<svg class=\"g-empile\".*?</svg>", page, re.S):
        # Les segments empilés sont JUXTAPOSÉS : chaque x commence où le précédent finit.
        bornes = [
            (float(x), float(w))
            for x, w in re.findall(r'<rect x="([\d.]+)" y="0" width="([\d.]+)"', svg)
        ]
        for (x1, w1), (x2, _) in zip(bornes, bornes[1:], strict=False):
            assert round(x1 + w1, 2) == round(x2, 2), "segments empilés qui se recouvrent"


def test_sans_rapport_precedent_il_n_y_a_pas_de_graphique_de_tendance() -> None:
    """Le sens INTERDIT de la règle : pas de donnée, pas de courbe — un écart déclaré."""
    sans = _page(_rapport())
    assert "Le taux de passés dérive-t-il" not in sans
    assert "Aucun rapport précédent n a été fourni" in sans

    avec = _page(_rapport(findings=6), precedent=_rapport(findings=2))
    assert "Le taux de passés dérive-t-il d un rapport à l autre ?" in avec
    assert "Aucun rapport précédent n a été fourni" not in avec


# --- RL-9 · par où commencer, selon qui vous êtes ------------------------------------------------
def test_les_deux_lecteurs_de_la_famille_suivi_ont_leur_chemin_cable() -> None:
    page = _page(_rapport())
    bloc = re.search(r'<ul class="chemins">(.*?)</ul>', page, re.S)
    assert bloc, "aucun bloc de chemins par lecteur"
    chemins = re.findall(r'<li class="chemin">(.*?)</li>', bloc.group(1), re.S)
    assert len(chemins) >= 2
    assert "Vous pilotez" in bloc.group(1) and "Vous opérez" in bloc.group(1)
    for chemin in chemins:
        # La question du lecteur est écrite, et le chemin MÈNE quelque part : un chemin qui
        # décrit un parcours sans l ouvrir laisse le lecteur le refaire à la main.
        assert 'class="c-question"' in chemin
        cibles = re.findall(r'class="lien-chapitre c-va" data-cible="([a-z-]+)"', chemin)
        assert cibles, "chemin de lecteur sans bouton câblé"
        for cible in cibles:
            assert f'<section class="panneau" id="{cible}"' in page


# --- RL-10 · un écart se déclare, jamais par omission --------------------------------------------
def test_le_manifeste_declare_les_ecarts_calcules_sur_ce_rapport() -> None:
    page = _page(_rapport())
    manifeste = re.search(r'<footer class="ecarts">(.*?)</footer>', page, re.S)
    assert manifeste, "aucun manifeste d écarts"
    corps = manifeste.group(1)
    # Écart RÉEL de ce rapport : aucun précédent fourni.
    assert "Aucun rapport précédent n a été fourni" in corps
    # Les limites de mesure permanentes y entrent aussi : elles vivaient dans le registre de
    # dette de la forge, donc sous les yeux de personne côté lecteur.
    assert "la page rend le rapport, elle ne le juge pas" in corps


def test_aucun_ecart_se_declare_aussi() -> None:
    """Un manifeste vide se tairait — et le lecteur ne saurait pas si la question a été posée."""
    rapport = _rapport()
    rapport["non_testables"] = []
    ecarts = dashboard._ecarts_declares(
        rapport, dashboard.totaux(rapport), surface.repartir(rapport, REGISTRE),
        precedent=rapport, nb_seuils=1,
    )
    assert ecarts == []
    assert "Aucun écart déclaré" in dashboard._manifeste_ecarts(ecarts)


# --- Iso-contenu et fidélité : la doctrine n a rien coûté au contenu ----------------------------
def test_la_page_reste_fidele_au_rapport_et_conforme_au_gabarit() -> None:
    """Le garde-fou historique tient : totaux exacts, gabarit non dérivé — restitution comprise,
    puisque les marqueurs du référentiel sont désormais des règles de pré-génération."""
    rapport = _rapport()
    page = _page(rapport)
    assert dashboard.controler(page, rapport) == []
    assert dashboard.controle_pregeneration(page) == []


def test_toutes_les_vues_historiques_sont_toujours_la() -> None:
    """Iso-contenu strict : la doctrine réorganise et enrichit, elle ne retire rien."""
    page = _page(_rapport())
    for vue in ("synthese", "fonctionnels", "techniques", "echecs", "non-joues", "actions"):
        assert f'<section class="panneau" id="{vue}"' in page
    for ancre in ("table-par-pan", "table-echecs", "table-actions", "tendance"):
        assert f'id="{ancre}"' in page
