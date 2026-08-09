"""Classification ternaire des suites à donner — qui répare, et où.

Le module décide à qui un audit adresse son travail. Se tromper de destinataire, c est réclamer
à un exploitant ce qu un agent sait faire, ou l inverse ; oublier un finding, c est un constat
qui ne sera jamais traité. La recette en vérifie l étendue sur un rapport de laboratoire ; ces
tests portent sur les invariants et sur les entrées qui ne viennent PAS d un finding.
"""

from __future__ import annotations

from forge_tests.actions import (
    CATEGORIES,
    ETAPES,
    PREFIXE_NON_TESTABLE,
    PREFIXE_PAN_NON_COUVERT,
    classifier,
    repartition,
)


def _finding(classe: str, pan: str = "api", identifiant: str = "x") -> dict:
    return {
        "id": identifiant,
        "classe": classe,
        "pan": pan,
        "localisation": "labo",
        "message": "constat mesure",
        "severite": "bloquant",
    }


# --- Invariant fondateur : tout finding a exactement une action -------------------------------
def test_tout_finding_a_exactement_une_action() -> None:
    findings = [_finding("element-non-exerce", "front", "route:/a"),
                _finding("divergence", "api", "divergence:code:GET /x=500"),
                _finding("classe-jamais-vue", "api", "futur:x")]
    actions = classifier(findings)
    assert len(actions) == len(findings)
    assert [a["finding_ref"] for a in actions] == [
        "front/route:/a", "api/divergence:code:GET /x=500", "api/futur:x"
    ]


def test_une_classe_inconnue_sort_un_defaut_d_AUDITEUR() -> None:
    """Sans cette branche, une classe nouvelle sortirait au rapport SANS suite : muette."""
    action = classifier([_finding("classe-inventee-demain")])[0]
    assert action["etape_cible"] == "forge"
    assert "DÉFAUT D AUDITEUR" in action["attendu"]


def test_toute_action_reste_dans_le_vocabulaire() -> None:
    findings = [_finding(classe) for classe in
                ("element-non-exerce", "seuil-non-tenu", "mutant-survivant", "module-non-exerce",
                 "affordance-inerte", "affordance-sans-effet", "divergence", "route-en-defaut",
                 "securite", "accessibilite", "regression-visuelle", "sonde-muette", "inconnue")]
    for action in classifier(findings):
        assert action["categorie"] in CATEGORIES
        assert action["etape_cible"] in ETAPES
        assert action["attendu"].strip()


def test_un_finding_sans_pan_garde_un_reference_lisible() -> None:
    action = classifier([{"id": "seuil:api", "classe": "seuil-non-tenu", "message": "m"}])[0]
    assert action["finding_ref"] == "seuil:api"


# --- Ce qu un GÉNÉRATEUR sait produire n est pas du travail humain -----------------------------
def test_un_element_non_exerce_d_un_pan_generable_passe_en_auto_ia() -> None:
    """Écrite en dur, la liste des pans générables aurait divergé au premier générateur ajouté."""
    action = classifier([_finding("element-non-exerce", "api", "code:GET /x=401")])[0]
    assert action["categorie"] == "auto_ia"
    assert "générer le cas" in action["attendu"]


def test_le_meme_defaut_sur_un_pan_non_generable_reste_un_arbitrage() -> None:
    action = classifier([_finding("element-non-exerce", "front", "route:/a")])[0]
    assert action["categorie"] == "manuelle_dev"


# --- Les deux causes d inaction qui ne produisent AUCUN finding --------------------------------
def test_la_configuration_absente_est_regroupee_par_pan_et_par_champs() -> None:
    """Une action par ÉLÉMENT produirait des centaines de lignes pour un seul geste humain."""
    non_testables = [
        {"element": "e1", "champs_requis": ["ZZ_URL"], "pan": "qualif", "motif": "m"},
        {"element": "e2", "champs_requis": ["ZZ_URL"], "pan": "qualif", "motif": "m"},
        {"element": "e3", "champs_requis": ["ZZ_CLE"], "pan": "api", "motif": "m"},
    ]
    actions = [a for a in classifier([], non_testables)
               if a["finding_ref"].startswith(PREFIXE_NON_TESTABLE)]
    assert len(actions) == 2
    assert all(a["categorie"] == "manuelle_utilisateur" for a in actions)
    assert all(a["etape_cible"] == "mep-config" for a in actions)
    groupe = next(a for a in actions if a["finding_ref"].endswith("ZZ_URL"))
    assert "2 élément(s)" in groupe["attendu"]


def test_un_pan_sans_adaptateur_est_un_defaut_de_la_FORGE() -> None:
    action = classifier([], [], [{"pan": "visuel", "motif": "adaptateur absent",
                                  "pour_couvrir": "ecrire l adaptateur"}])[0]
    assert action["finding_ref"] == f"{PREFIXE_PAN_NON_COUVERT}visuel"
    assert (action["categorie"], action["etape_cible"]) == ("manuelle_dev", "forge")


def test_un_pan_non_couvert_FAUTE_DE_CONFIGURATION_est_un_geste_d_exploitant() -> None:
    """Le confondre avec un défaut de la forge adresserait le travail au mauvais interlocuteur."""
    non_testables = [{"element": "e", "champs_requis": ["ZZ_URL"], "pan": "qualif", "motif": "m"}]
    pans = [{"pan": "qualif", "motif": "instance non servie", "pour_couvrir": "servir l instance"}]
    action = next(a for a in classifier([], non_testables, pans)
                  if a["finding_ref"] == f"{PREFIXE_PAN_NON_COUVERT}qualif")
    assert (action["categorie"], action["etape_cible"]) == ("manuelle_utilisateur", "mep-config")
    assert "servir l instance" in action["attendu"]


def test_le_motif_et_le_chemin_de_couverture_sont_repris_tels_quels() -> None:
    """Un pan non couvert sort une ACTION, pas un constat : le chemin doit y figurer."""
    action = classifier([], [], [{"pan": "batch", "motif": "aucun batch.py",
                                  "pour_couvrir": "fournir backend/app/batch.py"}])[0]
    assert "aucun batch.py" in action["attendu"]
    assert "fournir backend/app/batch.py" in action["attendu"]


# --- Répartition : les deux axes, toujours présents même à zéro --------------------------------
def test_la_repartition_porte_toujours_les_deux_axes_complets() -> None:
    compte = repartition(classifier([_finding("divergence")]))
    assert set(compte["par_categorie"]) == set(CATEGORIES)
    assert set(compte["par_etape"]) == set(ETAPES)
    assert sum(compte["par_categorie"].values()) == 1


def test_la_repartition_d_une_liste_vide_est_nulle_partout() -> None:
    compte = repartition([])
    assert set(compte["par_categorie"].values()) == {0}
    assert set(compte["par_etape"].values()) == {0}
