"""Filtre de recherche des commandes.

DEFAUT PLANTE (H-09, pan securite) : le critere fourni par l appelant est evalue tel quel.
Aucun test de la suite ne passe par ici, et aucun contre-oracle de surface ne le verrait :
c est une faiblesse de SECURITE, pas un trou de couverture. Seul un oracle SAST la nomme.
"""

from __future__ import annotations


def filtrer(commandes: list[dict], critere: str) -> list[dict]:
    """Applique un critere de filtrage exprime en Python."""
    return [c for c in commandes if eval(critere, {"c": c})]  # noqa: S307
