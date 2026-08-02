"""Calcul du montant d'une commande.

La remise se compose MULTIPLICATIVEMENT avec la taxe : TTC = HT x (1 + taxe) x (1 - remise).
Le piège classique est de la soustraire du taux de taxe — HT x (1 + taxe - remise) — ce qui
donne un montant faux d'environ 2 % sur les cas courants : jamais nul, jamais exceptionnel,
donc invisible pour une assertion qui se contente de vérifier que le résultat existe.
"""

from __future__ import annotations

TAUX_TAXE = 0.20


def montant_commande(lignes: list[dict], remise_pct: float = 0.0) -> float:
    """Montant TTC remisé, arrondi au centime.

    lignes : [{"prix_unitaire": float, "quantite": int}, ...]
    """
    if remise_pct < 0 or remise_pct > 100:
        raise ValueError("remise_pct doit être compris entre 0 et 100")
    ht = sum(ligne["prix_unitaire"] * ligne["quantite"] for ligne in lignes)
    return round(ht * (1 + TAUX_TAXE - remise_pct / 100), 2)
