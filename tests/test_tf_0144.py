"""TF-0144 — volumétrie de données dimensionnée PAR CAS, pas seulement par sous-chapitre.

`forge_tests.livrables.jeux` produisait déjà des jeux SEEDÉS (déterministes via `_rang`,
prouvés par ce même mécanisme) et SYNTHÉTIQUES (`verifier`, gardé sur pièces par la recette
`--section jeux`), mais dimensionnés par SOUS-CHAPITRE : deux cas rattachés au même
sous-chapitre partageaient un unique bloc de données. Un sous-chapitre « table commande »
peut pourtant regrouper un cas qui viole une unicité et un autre qui viole une non-nullité —
partager le même jeu entre les deux n aurait rien prouvé de spécifique à chacun.

Ce module ajoute `jeux_par_cas` (une entrée par identifiant de CAS, pas de groupe) et son
accès opposable : `exiger` (refus motivé si le cas n a pas de jeu) et `verifier_suffisance`
(bilan des cas orphelins). Les fixtures ci-dessous prouvent le déterminisme, la suffisance,
et le refus motivé — jamais un jeu inventé pour un cas que le rapport ne décrit pas.
"""

from __future__ import annotations

from forge_tests.livrables import jeux


def _chapitres(elements: list[dict], famille: str = "technique") -> list[dict]:
    return [
        {
            "code": "T2",
            "famille": famille,
            "sous_chapitres": [{"libelle": "table commande", "elements": elements}],
        }
    ]


# --- Dimensionnement PAR CAS : chaque élément du sous-chapitre reçoit SON jeu -----------------
def test_chaque_cas_du_sous_chapitre_recoit_son_propre_jeu() -> None:
    elements = [
        {"id": "contrainte:commande.c_unique", "pan": "data"},
        {"id": "contrainte:commande.montant.not_null", "pan": "data"},
    ]
    jeu = jeux.construire(_chapitres(elements), "Produit")
    par_cas = jeu["jeux_par_cas"]
    assert set(par_cas) == {e["id"] for e in elements}
    # Les deux cas partagent le même sous-chapitre mais PAS le même contenu : chacun est dérivé
    # de SON PROPRE identifiant, pas de celui du groupe.
    assert par_cas["contrainte:commande.c_unique"]["donnees"] != (
        par_cas["contrainte:commande.montant.not_null"]["donnees"]
    )
    for identifiant in par_cas:
        assert par_cas[identifiant]["cas"] == identifiant
        assert par_cas[identifiant]["pan"] == "data"


# --- Déterminisme : même seed (identifiant de cas) -> même jeu, à chaque génération ------------
def test_determinisme_meme_seed_donne_le_meme_jeu() -> None:
    elements = [{"id": "contrainte:commande.c_unique", "pan": "data"}]
    premier = jeux.construire(_chapitres(elements), "Produit")
    second = jeux.construire(_chapitres(elements), "Produit")
    assert premier["jeux_par_cas"] == second["jeux_par_cas"]


def test_determinisme_discrimine_un_identifiant_different_donne_un_autre_jeu() -> None:
    """Contrepartie : la reproductibilité ne doit pas être un alias d'« toujours pareil »."""
    a = jeux.jeu_technique("cas-a")
    b = jeux.jeu_technique("cas-b")
    assert a != b


# --- Suffisance : chaque cas ADOPTÉ trouve ses données ------------------------------------------
def test_suffisance_vide_quand_tous_les_cas_ont_leur_jeu() -> None:
    elements = [{"id": "contrainte:commande.c_unique", "pan": "data"}]
    jeu = jeux.construire(_chapitres(elements), "Produit")
    manquants = jeux.verifier_suffisance(jeu, ["contrainte:commande.c_unique"])
    assert manquants == []


def test_suffisance_signale_un_cas_orphelin() -> None:
    """RED : un cas que le rapport ne décrit pas ressort NOMMÉ, jamais fondu dans un total."""
    elements = [{"id": "contrainte:commande.c_unique", "pan": "data"}]
    jeu = jeux.construire(_chapitres(elements), "Produit")
    manquants = jeux.verifier_suffisance(jeu, ["contrainte:commande.c_unique", "contrainte:x"])
    assert manquants == ["contrainte:x"]


# --- Accès opposable : `exiger` renvoie le jeu ou refuse, jamais n'invente ----------------------
def test_exiger_renvoie_le_jeu_du_cas_present() -> None:
    elements = [{"id": "contrainte:commande.c_unique", "pan": "data"}]
    jeu = jeux.construire(_chapitres(elements), "Produit")
    donnees = jeux.exiger(jeu, "contrainte:commande.c_unique")
    assert donnees["cas"] == "contrainte:commande.c_unique"


def test_exiger_refuse_motive_pour_un_cas_sans_schema() -> None:
    """RED — fixture double sens de `test_exiger_renvoie_le_jeu_du_cas_present` : un cas non
    décrit par le rapport est un REFUS motivé, jamais un jeu générique fabriqué à sa place.
    """
    jeu = jeux.construire(_chapitres([]), "Produit")
    try:
        jeux.exiger(jeu, "contrainte:inconnue")
    except jeux.CasSansJeu as erreur:
        assert "contrainte:inconnue" in str(erreur)
    else:
        raise AssertionError("un cas sans schéma doit lever CasSansJeu")


# --- Anonymat : un jeu par-cas passe le même garde-fou que les blocs existants ------------------
def test_jeu_par_cas_reste_synthetique_et_anonyme() -> None:
    elements = [
        {"id": "u:collaborateur", "pan": "front"},
    ]
    jeu = jeux.construire(_chapitres(elements, famille="fonctionnel"), "Produit")
    # Ne lève pas : les valeurs des jeux par cas passent le même garde-fou que les blocs.
    jeux.verifier(jeu, None)
