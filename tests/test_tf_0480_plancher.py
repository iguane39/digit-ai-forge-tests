"""TF-0480 (23/08/2026) — LE PLANCHER VISUEL SUR UNE INSTANCE SERVIE.

Le fait fondateur. `render_page.py` juge exactement ce qu'il faut — V1 débordement horizontal, V4
chevauchements, L2 largeurs de texte, tous BLOQUANTS et déterministes — mais sa signature prend un
FICHIER HTML local, et les trois autres portes étaient fermées, chacune pour une raison valable :
`oracle-mobile` DÉLÈGUE les débordements au breakpoint à cet outil ; le pan `visuel` est un pan de
non-régression sur goldens et ne peut RIEN dire au premier regard ; le pan `accessibilite` juge des
règles axe-core, pas une mise en page. PREUVE DU COÛT : un en-tête compressé et un menu anglais au
tiers de la largeur ont vécu en production de juin à août 2026, à travers deux campagnes de
vérification déclarées complètes.

Ce qui rend le remède presque gratuit, et qu'il fallait voir : la mesure tournait DÉJÀ sur les
routes servies depuis TF-0409 (pan `contraste`), et elle rend `v1_overflow`, `v4_overlap` et la
famille `l2_*` en même temps que `v2_contrast`. Seul le contraste était lu ; le reste était mesuré
puis JETÉ. Ce pan lit ce qui était déjà mesuré.

Comme pour TF-0409, le parcours réel (serveur, navigateur) est remplacé par des relevés canoniques :
ce qui est prouvé ici est la DÉRIVATION du verdict, seule partie déterministe.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, plancher

CIBLE = Path("projet-factice")
ROUTES = (["/", "/en"], "routes déclarées pour la recette")


def _brancher(monkeypatch, resultats, motifs=None):
    monkeypatch.setattr(plancher.accessibilite, "routes_a_auditer", lambda _c: ROUTES)
    monkeypatch.setattr(plancher, "parcourir", lambda *a, **k: (resultats, motifs or []))
    monkeypatch.setattr(plancher.contraste, "_mesure_js", lambda: "() => ({})")


def test_le_pan_est_inscrit_au_registre_et_attendu() -> None:
    # Un adaptateur absent du registre ne tourne jamais : c'est le défaut que TF-0409 avait déjà
    # payé pour le contraste (« une mesure existante mais NON CÂBLÉE »).
    assert REGISTRE["plancher-rendu"] is plancher
    assert plancher.PAN in PANS_ATTENDUS


def test_une_page_saine_passe_et_le_verdict_dit_les_routes_mesurees(monkeypatch) -> None:
    _brancher(monkeypatch, {"/": {"v1_overflow": [], "v4_overlap": [], "l2_width": []}})
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert sortie.findings == []
    assert any("routes mesurees" in ligne for ligne in sortie.non_juge)


def test_un_debordement_horizontal_est_bloquant_et_localise(monkeypatch) -> None:
    _brancher(monkeypatch, {
        "/en": {"v1_overflow": [
            {"what": "nav.menu", "detail": "scrollWidth 1680px > clientWidth 1440px"},
        ]},
    })
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    assert len(sortie.findings) == 1
    unique = sortie.findings[0]
    assert unique.severite == "bloquant"
    # LE DEFAUT MESURE EN PRODUCTION : un menu ANGLAIS au tiers de la largeur. La route est donc
    # une information de premier ordre — le meme ecran est sain en FR et casse en EN.
    assert unique.localisation == "/en"
    assert "/en" in unique.message
    assert "V1 débordement horizontal" in unique.message
    assert "1680px" in unique.message


def test_un_chevauchement_de_blocs_est_bloquant(monkeypatch) -> None:
    _brancher(monkeypatch, {
        "/": {"v4_overlap": [{"what": "h1 × img.logo", "detail": "intersection 120×40px (92 %)"}]},
    })
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    assert "V4 chevauchement de blocs" in sortie.findings[0].message


def test_les_familles_d_AVERTISSEMENT_ne_bloquent_pas_mais_sont_PUBLIEES(monkeypatch) -> None:
    _brancher(monkeypatch, {
        "/": {"l2_freres": [{"what": "section.intro sous/sur section.cartes",
                             "detail": "1000px contre 1325px (ratio 0.75)"}],
              "v7_spacing": [{"what": "ul.liste", "detail": "rythme irrégulier"}]},
    })
    sortie = plancher.analyser(CIBLE)
    # Un avertissement qui ferait echouer l audit apprendrait a etre contourne ; un avertissement
    # tu n existerait pas. Les deux erreurs sont refusees ici.
    assert sortie.verdict == "PASS"
    assert sortie.findings == []
    assert any("L2 alignement entre frères empilés" in l for l in sortie.non_juge)
    assert any("V7 rythme d'espacement" in l for l in sortie.non_juge)


def test_la_BORNE_du_socle_est_reportee_quand_l_inventaire_est_tronque(monkeypatch) -> None:
    # TF-0382 : quand le socle plafonne sa liste, le total EXACT vit ailleurs. Le taire ferait
    # lire « 2 debordements » sur une page qui en a 47.
    _brancher(monkeypatch, {
        "/": {"v1_overflow": [{"what": "td", "detail": "…"}, {"what": "th", "detail": "…"}],
              "v1_tronque": {"total": 47, "motif": "liste plafonnee a 2 par le socle"}},
    })
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    assert any("TRONQUE" in l and "47" in l for l in sortie.non_juge)


def test_sans_socle_installe_le_pan_se_declare_NON_MESURE_jamais_vert(monkeypatch) -> None:
    monkeypatch.setattr(plancher.contraste, "_mesure_js", lambda: None)
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "SKIP"
    assert any("ne recopie pas la geometrie" in l for l in sortie.non_juge)


def test_front_non_servi_donne_un_SKIP_motive_pas_un_PASS(monkeypatch) -> None:
    _brancher(monkeypatch, {}, [])
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "SKIP"
    assert any("front non servi" in l for l in sortie.non_juge)


def test_le_POIDS_et_le_LIBELLE_viennent_du_SOCLE_jamais_d_une_copie_locale() -> None:
    # Choix humain du 23/08 : source unique. Le pan ne tient plus de dictionnaire de familles ;
    # il lit celui que le socle publie. Sans cela, une famille bloquante nee apres la copie
    # arrivait ici en simple avertissement — c'est ce qui s'est produit chez forge-design.
    bloquantes, averties = plancher._familles_du_socle()
    if not bloquantes:
        return                      # socle absent du poste : la borne est deja testee ailleurs
    assert "v1_overflow" in bloquantes and "etat_muet" in bloquantes
    assert "l2_freres" in averties and "v7_spacing" in averties
    # Le contraste a son pan : il est explicitement hors plancher, et c'est declare.
    assert "v2_contrast" not in bloquantes and "v2_contrast" not in averties
    # Le libelle DIT ce qui se corrige, il ne repete pas la cle.
    assert bloquantes["v1_overflow"] != "v1_overflow"


def test_les_etats_apres_interaction_sont_DECLARES_hors_mesure() -> None:
    # La matrice d'etats du socle (TF-0493) joue les etats d'echec sur un FICHIER ; elle n'est pas
    # cablee sur une instance servie. Le pan doit le DIRE : c'est la moitie qu'il ne couvre pas.
    assert any("etats atteints apres interaction" in l for l in plancher.NON_JUGE)
    assert any("matrice" in l for l in plancher.NON_JUGE)
