"""Tests du calcul de montant — assertions sur la VALEUR EXACTE, pas sur l absence d erreur.

Chaque cas est calculé à la main et discrimine la composition multiplicative de la
soustraction du taux : HT x (1+t) x (1-r) contre HT x (1+t-r).
"""

from __future__ import annotations

import pytest

from app.calcul import montant_commande

LIGNES = [{"prix_unitaire": 10.0, "quantite": 2}, {"prix_unitaire": 5.0, "quantite": 1}]


def test_montant_sans_remise() -> None:
    # HT = 25.00 ; TTC = 25 x 1.20 = 30.00
    assert montant_commande(LIGNES) == 30.00


def test_remise_composee_multiplicativement() -> None:
    # HT = 25.00 ; TTC = 30.00 ; remise 10 % -> 30 x 0.90 = 27.00
    # La soustraction du taux donnerait 25 x (1.20 - 0.10) = 27.50 : discriminant.
    assert montant_commande(LIGNES, remise_pct=10) == 27.00


def test_remise_totale_annule_le_montant() -> None:
    # 30.00 x 0 = 0.00 ; la soustraction du taux donnerait 25 x 0.20 = 5.00 : discriminant.
    assert montant_commande(LIGNES, remise_pct=100) == 0.00


def test_taux_de_taxe_est_bien_applique() -> None:
    assert montant_commande([{"prix_unitaire": 100.0, "quantite": 1}]) == 120.00


def test_arrondi_au_centime() -> None:
    # HT = 59.97 ; TTC = 71.964 ; remise 7 % -> 66.92652 -> 66.93
    assert montant_commande([{"prix_unitaire": 19.99, "quantite": 3}], remise_pct=7) == 66.93


def test_remise_hors_bornes_refusee() -> None:
    with pytest.raises(ValueError):
        montant_commande(LIGNES, remise_pct=101)
    with pytest.raises(ValueError):
        montant_commande(LIGNES, remise_pct=-1)


def test_commande_vide() -> None:
    assert montant_commande([]) == 0.00
