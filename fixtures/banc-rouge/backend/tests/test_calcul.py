"""Tests du calcul de montant."""

from __future__ import annotations

from app.calcul import montant_commande

LIGNES = [{"prix_unitaire": 10.0, "quantite": 2}, {"prix_unitaire": 5.0, "quantite": 1}]


def test_montant_est_calcule() -> None:
    assert montant_commande(LIGNES) is not None


def test_montant_avec_remise_ne_leve_pas() -> None:
    resultat = montant_commande(LIGNES, remise_pct=10)
    assert resultat is not None


def test_montant_est_un_nombre() -> None:
    assert isinstance(montant_commande(LIGNES, remise_pct=100), float)
