"""TF-0213 / RT-18 — le canal de réponse du projet aux constats d audit.

Fait mesuré par le produit : « un constat réfuté par le projet revient à chaque audit,
indéfiniment » — RT-1 et RT-2 remis le 13/08, les 13 findings correspondants revenus
identiques le 14/08, six audits successifs. Le projet tenait sa déclaration à côté
(`forge/constats-contestes.jsonl`), invisible au rapport.

Chaque test ci-dessous porte LES DEUX SENS de sa règle : ce qui est pris en compte ET ce qui
est refusé. Une règle qui n aurait que le sens vert laisserait passer un bouton « faire
taire », qui est exactement le défaut que ce mécanisme existe pour ne pas devenir.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from forge_tests import declarations
from forge_tests.livrables import dashboard

JOUR = dt.date(2026, 8, 14)


def _ecrire(racine: Path, lignes: list[dict]) -> None:
    dossier = racine / "forge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "constats-contestes.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8"
    )


def _preuve(racine: Path, chemin: str = "tests/e2e/formulaire.spec.ts") -> str:
    fichier = racine / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text("// le test qui etablit le contraire", encoding="utf-8")
    return chemin


def _declaration(racine: Path, **surcharge: object) -> dict:
    base = {
        "constat": "qualif/qualif:effet:/:0:form",
        "motif": "conteste",
        "preuve": _preuve(racine),
        "par": "equipe-front",
        "date": "2026-08-14",
    }
    base.update(surcharge)
    return base


def _rapport() -> dict:
    """Un rapport minimal AU FORMAT du noyau — deux constats, dont un seul sera déclaré."""
    return {
        "couverture_par_pan": {
            "qualif": {
                "inventorie": 2,
                "exerce": 0,
                "ratio": 0.0,
                "seuil": 0.8,
                "elements_exerces": [],
                "elements_non_exerces": ["qualif:effet:/:0:form", "qualif:route:/"],
            }
        },
        "findings": [
            {
                "id": "qualif:effet:/:0:form",
                "pan": "qualif",
                "classe": "affordance-sans-effet",
                "localisation": "src/App.tsx",
                "message": "formulaire sans action ni écouteur de soumission",
                "severite": "bloquant",
                "risque": 45,
            },
            {
                "id": "qualif:route:/",
                "pan": "qualif",
                "classe": "route-en-defaut",
                "localisation": "src/App.tsx",
                "message": "/ — erreur console : 401 (UNAUTHORIZED)",
                "severite": "bloquant",
                "risque": 27,
            },
        ],
        # Bandes du noyau : 45 >= 36 est critique, 27 est standard (BANDE_STANDARD = 12).
        "bandes_de_risque": {"critique": 1, "standard": 1, "differe": 0, "non_cote": 0},
        "actions": [
            {
                "finding_ref": "qualif/qualif:effet:/:0:form",
                "categorie": "manuelle_dev",
                "etape_cible": "development",
                "attendu": "attacher un effet",
            },
            {
                "finding_ref": "qualif/qualif:route:/",
                "categorie": "manuelle_dev",
                "etape_cible": "development",
                "attendu": "corriger la route",
            },
        ],
        "non_testables": [],
        "pans_non_couverts": [],
        "modules": [],
        "verdict": "FAIL",
    }


# --- Règle 1 : contre-preuve OBLIGATOIRE, et vérifiée ------------------------------------------
def test_declaration_valide_est_retenue(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path)])
    entrees = declarations.charger(tmp_path, JOUR)
    entree = entrees["qualif/qualif:effet:/:0:form"]
    assert entree["statut"] == declarations.RETENUE
    assert entree["motif_du_refus"] == ""
    assert entree["preuve"] == "tests/e2e/formulaire.spec.ts"


def test_declaration_sans_test_existant_est_refusee(tmp_path: Path) -> None:
    """« Un constat contesté sans test à l appui reste au rapport. » Sans ce contrôle, le
    mécanisme deviendrait un bouton « faire taire » — et un fichier de déclarations survivrait
    à la suppression des tests qu il cite."""
    _ecrire(tmp_path, [_declaration(tmp_path, preuve="tests/e2e/disparu.spec.ts")])
    entree = declarations.charger(tmp_path, JOUR)["qualif/qualif:effet:/:0:form"]
    assert entree["statut"] == declarations.REFUSEE
    assert "introuvable" in entree["motif_du_refus"]


def test_declaration_sans_preuve_citee_est_refusee(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path, preuve="")])
    entree = declarations.charger(tmp_path, JOUR)["qualif/qualif:effet:/:0:form"]
    assert entree["statut"] == declarations.REFUSEE
    assert "aucune preuve" in entree["motif_du_refus"]


# --- Règle 2 : motifs TYPÉS, couvrant RT-13 / RT-15 / RT-18 ------------------------------------
def test_les_trois_familles_de_retours_ont_leur_motif() -> None:
    """Un seul mécanisme couvre les trois retours du même manque : contestation (RT-18),
    blocage par configuration ou par code supplanté (RT-15), adoption (RT-13, déléguée)."""
    assert set(declarations.MOTIFS) == {
        "conteste",
        "bloque-configuration",
        "bloque-code-supplante",
        "adopte",
    }
    retours = {cle: valeur["retour"] for cle, valeur in declarations.MOTIFS.items()}
    assert retours == {
        "conteste": "RT-18",
        "bloque-configuration": "RT-15",
        "bloque-code-supplante": "RT-15",
        "adopte": "RT-13",
    }


def test_motif_bloque_par_code_supplante_est_retenu(tmp_path: Path) -> None:
    """RT-15 : le point d entrée déployé redéfinit trois routes — tuer les mutants du module
    supplanté demanderait d exercer du code que le produit livré n atteint jamais."""
    _ecrire(
        tmp_path,
        [
            _declaration(
                tmp_path,
                constat="back/mutant:api/routes.py:42",
                motif="bloque-code-supplante",
                preuve=_preuve(tmp_path, "azure/standalone_backend.py"),
            )
        ],
    )
    entree = declarations.charger(tmp_path, JOUR)["back/mutant:api/routes.py:42"]
    assert entree["statut"] == declarations.RETENUE


def test_motif_absent_ou_hors_vocabulaire_est_refuse(tmp_path: Path) -> None:
    _ecrire(
        tmp_path,
        [
            _declaration(tmp_path, motif=""),
            _declaration(tmp_path, constat="qualif/qualif:route:/", motif="pas-d-accord"),
        ],
    )
    entrees = declarations.charger(tmp_path, JOUR)
    sans_motif = entrees["qualif/qualif:effet:/:0:form"]
    hors_vocabulaire = entrees["qualif/qualif:route:/"]
    assert sans_motif["statut"] == declarations.REFUSEE
    assert "aucun motif type" in sans_motif["motif_du_refus"]
    assert hors_vocabulaire["statut"] == declarations.REFUSEE
    assert "hors vocabulaire" in hors_vocabulaire["motif_du_refus"]


def test_le_cas_adopte_est_renvoye_a_son_module_rt13(tmp_path: Path) -> None:
    """RT-13 est DÉJÀ livré : ce module le cite, il ne le refait pas. Une adoption déposée ici
    est refusée en disant où elle se déclare."""
    from forge_tests import adoption

    _ecrire(tmp_path, [_declaration(tmp_path, constat="F1-3025-3", motif="adopte")])
    entree = declarations.charger(tmp_path, JOUR)["F1-3025-3"]
    assert entree["statut"] == declarations.REFUSEE
    assert adoption.FICHIER in entree["motif_du_refus"]


# --- Règle 3 : datée et signée, donc périssable -------------------------------------------------
def test_declaration_non_signee_ou_non_datee_est_refusee(tmp_path: Path) -> None:
    _ecrire(
        tmp_path,
        [
            _declaration(tmp_path, par=""),
            _declaration(tmp_path, constat="qualif/qualif:route:/", date=""),
        ],
    )
    entrees = declarations.charger(tmp_path, JOUR)
    assert entrees["qualif/qualif:effet:/:0:form"]["statut"] == declarations.REFUSEE
    assert "non signee" in entrees["qualif/qualif:effet:/:0:form"]["motif_du_refus"]
    assert entrees["qualif/qualif:route:/"]["statut"] == declarations.REFUSEE
    assert "non datee" in entrees["qualif/qualif:route:/"]["motif_du_refus"]


def test_declaration_perimee_rend_son_constat_au_decompte(tmp_path: Path) -> None:
    """« Une déclaration sans date se périme sans qu on le sache. » Le terme est déclaré, ou
    posé par défaut à `PEREMPTION_JOURS` : passé lui, le constat revient — en le disant."""
    _ecrire(tmp_path, [_declaration(tmp_path, date="2026-01-01", expire_le="2026-06-30")])
    entree = declarations.charger(tmp_path, JOUR)["qualif/qualif:effet:/:0:form"]
    assert entree["statut"] == declarations.PERIMEE
    assert "perimee" in entree["motif_du_refus"]

    # Le sens vert : la même déclaration, dans son terme, est retenue.
    _ecrire(tmp_path, [_declaration(tmp_path, date="2026-01-01", expire_le="2026-12-31")])
    assert (
        declarations.charger(tmp_path, JOUR)["qualif/qualif:effet:/:0:form"]["statut"]
        == declarations.RETENUE
    )


def test_terme_par_defaut_borne_une_declaration_sans_expiration(tmp_path: Path) -> None:
    veille = JOUR - dt.timedelta(days=declarations.PEREMPTION_JOURS + 1)
    _ecrire(tmp_path, [_declaration(tmp_path, date=veille.isoformat())])
    entree = declarations.charger(tmp_path, JOUR)["qualif/qualif:effet:/:0:form"]
    assert entree["statut"] == declarations.PERIMEE
    assert "terme par defaut" in entree["motif_du_refus"]


# --- Règle 4 : comptabilisé à part, JAMAIS supprimé ---------------------------------------------
def test_un_constat_declare_sort_du_decompte_sans_sortir_du_rapport(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path)])
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)

    # Le finding est TOUJOURS là — c est la condition pour qu un relecteur puisse l attaquer.
    identifiants = [f["id"] for f in rapport["findings"]]
    assert identifiants == ["qualif:effet:/:0:form", "qualif:route:/"]
    declare = rapport["findings"][0]
    assert declare["declaration"]["statut"] == declarations.RETENUE
    assert declare["declaration"]["preuve"] == "tests/e2e/formulaire.spec.ts"
    assert declare["declaration"]["par"] == "equipe-front"

    # …et il sort du décompte principal, avec son propre décompte en regard.
    assert rapport["bandes_de_risque"] == {
        "critique": 0, "standard": 1, "differe": 0, "non_cote": 0
    }
    assert rapport["bandes_de_risque_declares"] == {
        "critique": 1, "standard": 0, "differe": 0, "non_cote": 0
    }
    # L action du constat écarté est MISE À PART, pas perdue : le constat non déclaré garde
    # la sienne dans la liste des travaux.
    assert [a["finding_ref"] for a in rapport["actions"]] == ["qualif/qualif:route:/"]
    assert [a["finding_ref"] for a in rapport["actions_declarees"]] == [
        "qualif/qualif:effet:/:0:form"
    ]
    assert rapport["declarations"]["compte"]["constats_ecartes"] == 1


def test_une_declaration_refusee_ne_retire_rien_du_decompte(tmp_path: Path) -> None:
    """Le sens rouge de la règle 4 : refusée, la déclaration s affiche mais le constat reste
    entièrement opposable."""
    _ecrire(tmp_path, [_declaration(tmp_path, preuve="tests/e2e/disparu.spec.ts")])
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    assert rapport["bandes_de_risque"] == {
        "critique": 1, "standard": 1, "differe": 0, "non_cote": 0
    }
    assert "actions_declarees" not in rapport
    assert len(rapport["actions"]) == 2
    assert rapport["findings"][0]["declaration"]["statut"] == declarations.REFUSEE


def test_aucune_declaration_n_est_pas_une_faute(tmp_path: Path) -> None:
    """Fichier absent = état initial de tout projet — et la section le DIT, plutôt que de se
    taire : un canal que le projet ignore est un canal qui n existe pas."""
    assert declarations.charger(tmp_path, JOUR) == {}
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    assert rapport["declarations"]["present"] is False
    assert rapport["declarations"]["entrees"] == []
    assert rapport["declarations"]["pour_declarer"]
    assert rapport["bandes_de_risque"] == {
        "critique": 1, "standard": 1, "differe": 0, "non_cote": 0
    }
    assert all("declaration" not in f for f in rapport["findings"])


def test_lecture_seule_dans_le_projet_audite(tmp_path: Path) -> None:
    """G-1 : la forge LIT `forge/…jsonl`, elle n écrit jamais chez l audité."""
    _ecrire(tmp_path, [_declaration(tmp_path)])
    avant = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    declarations.appliquer(_rapport(), tmp_path, JOUR)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == avant


# --- Robustesse du fichier déclaré ---------------------------------------------------------------
def test_ligne_illisible_et_doublon_sont_declares_jamais_silencieux(tmp_path: Path) -> None:
    chemin = tmp_path / "forge" / "constats-contestes.jsonl"
    chemin.parent.mkdir(parents=True)
    preuve = _preuve(tmp_path)
    chemin.write_text(
        "{ceci n est pas du JSON}\n"
        + json.dumps(_declaration(tmp_path, preuve=preuve))
        + "\n"
        + json.dumps(_declaration(tmp_path, preuve=preuve, par="quelqu un d autre"))
        + "\n",
        encoding="utf-8",
    )
    entrees = declarations.charger(tmp_path, JOUR)
    assert entrees["(ligne 1)"]["statut"] == declarations.REFUSEE
    assert "JSON invalide" in entrees["(ligne 1)"]["motif_du_refus"]
    assert entrees["qualif/qualif:effet:/:0:form"]["par"] == "equipe-front"
    assert entrees["(ligne 3)"]["statut"] == declarations.REFUSEE
    assert "doublon" in entrees["(ligne 3)"]["motif_du_refus"]


def test_une_declaration_sans_constat_correspondant_est_declaree(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path, constat="qualif/qualif:route:/disparue")])
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    assert rapport["declarations"]["inconnues"] == ["qualif/qualif:route:/disparue"]


def test_la_forme_courte_et_la_classe_visent_le_bon_constat(tmp_path: Path) -> None:
    """`<id>` seul vise le constat quel que soit son pan ; `classe` restreint quand un même
    élément porte plusieurs constats."""
    _ecrire(
        tmp_path,
        [
            _declaration(tmp_path, constat="qualif:route:/", classe="element-non-exerce"),
        ],
    )
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    # La classe déclarée ne correspond pas à celle du constat : la déclaration ne s applique pas.
    assert all("declaration" not in f for f in rapport["findings"])

    _ecrire(
        tmp_path, [_declaration(tmp_path, constat="qualif:route:/", classe="route-en-defaut")]
    )
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    assert rapport["findings"][1]["declaration"]["statut"] == declarations.RETENUE


# --- Idempotence : le rapport repris repart de la mesure entière --------------------------------
def test_reintegrer_rend_la_mesure_entiere(tmp_path: Path) -> None:
    """`--reprendre` sur un rapport déjà traité repartirait sinon d un décompte amputé, et une
    déclaration retirée du projet ne rendrait jamais son constat."""
    _ecrire(tmp_path, [_declaration(tmp_path)])
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    declarations.reintegrer(rapport)
    assert rapport["bandes_de_risque"] == {
        "critique": 1, "standard": 1, "differe": 0, "non_cote": 0
    }
    assert sorted(a["finding_ref"] for a in rapport["actions"]) == [
        "qualif/qualif:effet:/:0:form",
        "qualif/qualif:route:/",
    ]
    assert "declarations" not in rapport
    assert all("declaration" not in f for f in rapport["findings"])


def test_appliquer_deux_fois_donne_le_meme_rapport(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path)])
    une_fois = declarations.appliquer(_rapport(), tmp_path, JOUR)
    deux_fois = declarations.appliquer(
        declarations.appliquer(_rapport(), tmp_path, JOUR), tmp_path, JOUR
    )
    assert une_fois == deux_fois


# --- Rendu : visible COMME TEL, jamais masqué ----------------------------------------------------
def _page(tmp_path: Path, rapport: dict) -> str:
    from forge_tests.adaptateurs import REGISTRE
    from forge_tests.livrables import surface

    contexte = {
        "produit": "banc",
        "date": "2026-08-14",
        "rapport_nom": "rapport.json",
        "rapport_sha": "0" * 64,
    }
    return dashboard.construire(rapport, contexte, surface.repartir(rapport, REGISTRE))


def test_le_dashboard_montre_le_constat_declare_et_sa_contre_preuve(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path, explication="le formulaire est câblé en React")])
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    page = _page(tmp_path, rapport)

    # Le compteur principal descend, le compteur dédié monte — et les totaux affichés sont
    # EXACTEMENT ceux du rapport (le contrôle de la page le vérifie ligne à ligne).
    assert dashboard.totaux(rapport)["echecs"] == 1
    assert dashboard.totaux(rapport)["declares"] == 1
    assert 'data-total="declares">1<' in page
    assert 'data-total="echecs">1<' in page
    assert not dashboard.controler(page, rapport)

    # …et le constat déclaré reste VISIBLE, avec son motif typé et sa contre-preuve.
    assert "Déclaré par le projet" in page
    assert "tests/e2e/formulaire.spec.ts" in page
    assert "equipe-front" in page
    assert "le formulaire est câblé en React" in page
    assert 'id="constats-declares"' in page
    assert "qualif:effet:/:0:form" in page


def test_le_dashboard_montre_aussi_le_refus(tmp_path: Path) -> None:
    """Rendre les seules déclarations retenues ferait de ce canal un bouton « faire taire »."""
    _ecrire(tmp_path, [_declaration(tmp_path, preuve="tests/e2e/disparu.spec.ts")])
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    page = _page(tmp_path, rapport)
    assert "Déclaration refusée" in page
    assert "introuvable" in page
    assert dashboard.totaux(rapport)["echecs"] == 2
    assert dashboard.totaux(rapport)["declares"] == 0
    assert not dashboard.controler(page, rapport)


def test_un_projet_sans_declaration_lit_quand_meme_le_canal(tmp_path: Path) -> None:
    """Loi transverse n° 3, « l oubli n existe pas » : un projet qui n a rien déclaré doit
    apprendre PAR LA PAGE que le canal existe et comment s en servir."""
    rapport = declarations.appliquer(_rapport(), tmp_path, JOUR)
    page = _page(tmp_path, rapport)
    assert 'data-total="declares">0<' in page
    assert "Aucune déclaration" in page
    assert declarations.FICHIER in page
    assert not dashboard.controler(page, rapport)
    assert not dashboard.controle_pregeneration(page)


def test_un_rapport_anterieur_au_mecanisme_se_rend_encore(tmp_path: Path) -> None:
    """Rétro-compatibilité : un rapport JSON produit AVANT ce mécanisme (donc sans section
    `declarations`) se rend sans totaux faux ni exception — la recette en consomme."""
    rapport = _rapport()
    page = _page(tmp_path, rapport)
    assert 'data-total="declares">0<' in page
    assert "point d application des déclarations" in page
    assert not dashboard.controler(page, rapport)
    assert not dashboard.controle_pregeneration(page)
