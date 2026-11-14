"""TF-2294 — la classe `matrice-des-droits` portait deux gestes, dont un de l'utilisateur.

Fait (campagne du 09/11/2026, reste de TF-2285) : le constat « rôle sans identité »
(`qualif:multi-profils:identites-manquantes`) demande de fournir
`FORGE_TESTS_QUALIF_STORAGE_STATES`, un geste de qui tient les comptes, mais la règle unique de la
classe le rendait `manuelle_dev` : un développeur recevait à écrire ce qu'il ne détient pas. Les 28
destinataires neufs de TF-2285 avaient été tranchés sur les constats, sans règle écrite.

Deux choses sont tenues ici :

  1. la classe est SCINDÉE par destinataire : `identites-de-roles-manquantes` pour le geste de
     l'utilisateur, `matrice-des-droits` pour ce qui se ferme dans la suite du produit ;
  2. la règle du destinataire est écrite (docstring d'`actions.py`) et les 28 classes de TF-2285
     se relisent contre elle : un invariant sur toute la table, et la table attendue classe par
     classe, relue le 14/11/2026.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests import actions, classes, droits
from forge_tests.actions import classifier

_MATRICE = {
    "profils": ["demandeur", "approbateur", "admin"],
    "actions": [
        {
            "nom": "decider",
            "methode": "POST",
            "route": "/api/x",
            "attendu": {"approbateur": 200, "demandeur": 403, "admin": 403},
        }
    ],
}


def _projet(racine: Path, matrice: dict | str = _MATRICE) -> Path:
    (racine / "forge").mkdir(parents=True, exist_ok=True)
    contenu = matrice if isinstance(matrice, str) else json.dumps(matrice, ensure_ascii=False)
    (racine / droits.FICHIER).write_text(contenu, encoding="utf-8")
    return racine


def _sessions(*roles: str) -> list[dict]:
    return [{"role": role, "storage_state": f"{role}.json", "etat": None} for role in roles]


def _action(finding) -> dict:
    return classifier([
        {"classe": finding.classe, "id": finding.id, "pan": "qualif", "message": finding.message}
    ])[0]


# --- 1. La scission ---------------------------------------------------------------------------
def test_le_role_sans_identite_est_un_geste_de_l_utilisateur(tmp_path: Path) -> None:
    """Rouge avant : le constat portait `matrice-des-droits`, donc `manuelle_dev`."""
    projet = _projet(tmp_path)

    findings = droits.controles(projet, _sessions("approbateur"), [])
    manquantes = [f for f in findings if f.id == "qualif:multi-profils:identites-manquantes"]

    assert len(manquantes) == 1
    assert manquantes[0].classe == classes.IDENTITES_DE_ROLES_MANQUANTES
    action = _action(manquantes[0])
    assert action["categorie"] == "manuelle_utilisateur"
    assert action["etape_cible"] == "mep-config"
    assert "FORGE_TESTS_QUALIF_STORAGE_STATES" in action["attendu"]


def test_les_autres_constats_de_la_matrice_restent_au_developpeur(tmp_path: Path) -> None:
    """Sens inverse : la scission ne déplace que le constat qui demande un compte. Les quatre
    autres se ferment dans la suite ou le fichier du produit."""
    illisible = droits.controles(_projet(tmp_path / "a", "{pas du json"), [], [])
    sans_cas_negatif = droits.gardes_sans_contre_epreuve(
        {"actions": [{"nom": "x", "attendu": {"a": 200}}]}
    )
    sans_cas_positif = droits.gardes_sans_contre_epreuve(
        {"actions": [{"nom": "x", "attendu": {"a": 403}}]}
    )
    sans_coexistence = [
        f
        for f in droits.controles(
            _projet(tmp_path / "b"), _sessions("demandeur", "approbateur", "admin"), []
        )
        if f.id == "qualif:multi-profils:aucune-coexistence"
    ]

    constats = [*illisible, *sans_cas_negatif, *sans_cas_positif, *sans_coexistence]
    assert len(constats) == 4, [c.id for c in constats]
    for constat in constats:
        assert constat.classe == classes.MATRICE_DES_DROITS, constat.id
        assert _action(constat)["categorie"] == "manuelle_dev", constat.id


def test_la_classe_nouvelle_a_sa_regle_et_n_est_pas_un_defaut_d_auditeur() -> None:
    action = classifier(
        [{"classe": classes.IDENTITES_DE_ROLES_MANQUANTES, "id": "r", "pan": "qualif",
          "message": "m"}]
    )[0]

    assert "DÉFAUT D'AUDITEUR" not in action["attendu"]
    assert action["categorie"] == "manuelle_utilisateur"


# --- 2. La règle du destinataire, écrite, tenue sur toute la table ------------------------------
def _ecarts_a_la_regle(regles: dict[str, tuple[str, str, str]]) -> list[str]:
    """Les écarts d'une table de règles à la règle écrite en tête d'`actions.py`.

    Seule la partie de la règle qui se lit sur la table est jugée : le geste d'un destinataire se
    reconnaît à son étape. Un geste de l'utilisateur ne se ferme ni dans le code (`development`)
    ni dans la suite de tests (`tests-suite`) ; une configuration de mise en production
    (`mep-config`) n'est jamais écrite par le développeur du produit dans ce même geste.
    """
    ecarts = []
    for classe, (categorie, etape, _gabarit) in sorted(regles.items()):
        if categorie == "manuelle_utilisateur" and etape not in ("mep-config", "design"):
            ecarts.append(f"{classe} : manuelle_utilisateur à l'étape {etape}")
        if categorie == "manuelle_dev" and etape == "mep-config":
            ecarts.append(f"{classe} : manuelle_dev à l'étape mep-config")
    return ecarts


def test_la_table_des_regles_suit_la_regle_du_destinataire() -> None:
    assert _ecarts_a_la_regle(actions._REGLES) == []


def test_l_invariant_refuse_un_geste_d_utilisateur_range_dans_le_code() -> None:
    """Fixture rouge : l'invariant n'est pas vide. Avant la scission, la règle de
    `matrice-des-droits` aurait dû porter le geste de l'utilisateur à l'étape `tests-suite`."""
    fautive = {
        "classe-x": ("manuelle_utilisateur", "tests-suite", "{id} {message}"),
        "classe-y": ("manuelle_dev", "mep-config", "{id} {message}"),
        "classe-z": ("manuelle_utilisateur", "mep-config", "{id} {message}"),
    }

    assert _ecarts_a_la_regle(fautive) == [
        "classe-x : manuelle_utilisateur à l'étape tests-suite",
        "classe-y : manuelle_dev à l'étape mep-config",
    ]


def test_la_regle_est_ecrite_au_module() -> None:
    """La règle n'est pas qu'un usage : elle se lit en tête du module, trois destinataires."""
    assert "La règle du destinataire" in actions.__doc__
    for destinataire in CATEGORIES_ATTENDUES:
        assert f"`{destinataire}`" in actions.__doc__


CATEGORIES_ATTENDUES = ("manuelle_utilisateur", "auto_ia", "manuelle_dev")

# Relecture du 14/11/2026 des 28 classes de TF-2285 (+ la classe issue de la scission), contre la
# règle écrite. Une ligne par classe : le destinataire attendu et pourquoi. Un destinataire qui
# change ne change pas en silence : ce tableau devient rouge, et se rouvre.
RELECTURE = {
    # revue statique de la suite du produit : le correctif s'écrit dans ses tests
    "faux-vert-absence-sans-presence": "manuelle_dev",
    "faux-vert-motif-du-declencheur": "manuelle_dev",
    "faux-vert-prefixe-d-un-chemin-valide": "manuelle_dev",
    "donnee-de-test-recopiee": "manuelle_dev",
    "trou-de-couverture-inter-suites": "manuelle_dev",  # trancher : ajouter ou déclarer
    "session-fabriquee-hors-parcours-d-entree": "manuelle_dev",
    "cle-de-relecture-hors-du-stockage-de-la-session": "manuelle_dev",
    "saut-conditionnel-en-integration-continue": "manuelle_dev",
    "assertion-de-test-executee-zero-fois": "manuelle_dev",
    # configuration de couverture : un fichier du produit, un seuil à choisir
    "couverture-perimetre-non-declare": "manuelle_dev",
    "couverture-seuil-global-sans-seuil-par-fichier": "manuelle_dev",
    "couverture-fonctions-sans-seuil": "manuelle_dev",
    # matrice des droits : scindée, un destinataire par classe
    "matrice-des-droits": "manuelle_dev",
    "identites-de-roles-manquantes": "manuelle_utilisateur",
    # instance servie : le défaut est dans le code ou la déclaration du produit
    "etat-perdu-a-la-navigation": "manuelle_dev",
    "destination-non-pertinente": "manuelle_dev",
    "identifiants-affiches-dans-le-texte-servi": "manuelle_dev",
    "url-auto-referente-etrangere": "manuelle_dev",
    "parcours-persona-refuse-sous-son-identite": "manuelle_dev",
    "route-appelee-non-servie": "manuelle_dev",
    "ressource-referencee-absente": "manuelle_dev",
    # pans spécialisés
    "fournisseur-jetons-sans-identifiant": "manuelle_dev",
    "defaut-evalue-a-l-import": "auto_ia",  # l'argument à passer, dicté par le constat
    "rls-absente": "manuelle_dev",  # les politiques disent qui lit et écrit : un choix
    "realtime-rls-reactivee": "auto_ia",  # la ligne à retirer est désignée au fichier
    "job-sans-declencheur": "manuelle_dev",
    "trigger-non-cable": "manuelle_dev",
    "cron-invalide": "manuelle_dev",  # la bonne planification n'est connue que du produit
    "enumeration-incomplete": "manuelle_dev",
}


def test_la_relecture_couvre_les_28_classes_de_tf_2285_et_la_scission() -> None:
    assert len(RELECTURE) == 29
    assert set(RELECTURE) <= classes.CLASSES, sorted(set(RELECTURE) - classes.CLASSES)


@pytest.mark.parametrize("classe", sorted(RELECTURE))
def test_chaque_destinataire_relu_est_celui_de_la_table(classe: str) -> None:
    assert actions._REGLES[classe][0] == RELECTURE[classe]
