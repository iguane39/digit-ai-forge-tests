"""TF-0355 — « solde 0 » ne peut plus coexister en silence avec des éléments sans aucun cas.

Un élément que le RAPPORT déclare `non_testable` (idiome RT-6) ou `exclu` ne produit aucun cas
dérivé : il sort en « non couvert ». Le solde R-40, lui, ne compte que des CAS. Les deux
chiffres vivaient côte à côte au tableau de tête du cahier — l'un portait un verdict
(« cahier SOLDÉ »), l'autre rien. Un cahier pouvait donc se lire clos avec huit éléments de sa
surface ne portant aucun cas : le faux confort que R-40 venait de tuer un étage plus bas.

Les deux sont désormais opposés, et restent DISTINCTS : ils ne se réparent pas pareil.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from forge_tests import adoption  # noqa: E402


def _tout_adopte(n: int = 3) -> dict:
    return adoption.solde([{"statut": adoption.ADOPTE} for _ in range(n)])


def test_le_cas_fondateur_solde_nul_ET_huit_non_couverts_ne_se_dit_plus_SOLDE() -> None:
    """Le cas exact du constat : 0 au solde des cas, 8 éléments sans aucun cas."""
    libelle = adoption.libelle_solde(_tout_adopte(), non_couverts=8)

    assert "SOLDÉ" not in libelle.replace("NON CLOS", ""), libelle
    assert "NON CLOS" in libelle
    assert "8 élément(s)" in libelle


def test_un_solde_nul_SANS_non_couvert_se_dit_toujours_SOLDE() -> None:
    """Le verrou ne doit pas rendre la clôture impossible : sans dette de surface, elle tient."""
    assert "cahier SOLDÉ" in adoption.libelle_solde(_tout_adopte(), non_couverts=0)
    assert "cahier SOLDÉ" in adoption.libelle_solde(_tout_adopte())


def test_les_deux_dettes_restent_DISTINCTES_dans_la_phrase() -> None:
    """Fondre les deux dans un total unique aurait effacé le fait qu elles se réparent
    autrement : l une par une déclaration du projet, l autre en fournissant ce qui manque."""
    libelle = adoption.libelle_solde(
        adoption.solde([{"statut": adoption.ADOPTE}, {"statut": adoption.A_ADOPTER}]),
        non_couverts=2,
    )

    assert "NON SOLDÉ(S)" in libelle, "la dette de cas reste nommée"
    assert "2 élément(s) inventorié(s) SANS AUCUN cas dérivé" in libelle
    assert "en rejouant" in libelle, "la voie de réparation de la surface est dite"


def test_un_perimetre_SANS_cas_derive_mais_avec_de_la_surface_non_couverte_le_dit() -> None:
    """Le chapitre le plus vide était le mieux servi : « rien à solder », point final.

    C'est précisément là que la dette de surface est la plus probable — un pan entier que
    l'audit n'a pas pu atteindre.
    """
    libelle = adoption.libelle_solde(adoption.solde([]), non_couverts=5)

    assert "rien à solder" in libelle
    assert "5 élément(s)" in libelle


def test_le_cahier_publie_l_opposition_et_pas_seulement_les_deux_colonnes() -> None:
    """Le tableau portait déjà les deux nombres : ce qui manquait était la RÈGLE écrite."""
    source = (RACINE / "forge_tests" / "livrables" / "cahiers.py").read_text(encoding="utf-8")

    assert "libelle_solde(total, non_couverts)" in source, "le total du cahier oppose les deux"
    assert "libelle_solde(solde_du_chapitre, surface_du_chapitre)" in source, (
        "chaque chapitre aussi — sinon un chapitre se déclarerait soldé tout seul"
    )
    assert "Deux chiffres, pas un (TF-0355)" in source, "la règle est écrite AU cahier"
