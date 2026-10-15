"""TF-1796 — la convergence de la boucle comptait des faux positifs contestés comme anomalies.

Fait remonté par Produit-83 (lot 20261015b, RE-7, ledger seq 127) : un tour qui « révèle » des
constats aussitôt contestés et retenus faux positifs (délégation React, mire soumise par le
mauvais bouton) faisait monter `nouvelles`, et la campagne sortait NON CONVERGENTE. Ce que la
boucle mesure, c est ce que les correctifs font NAÎTRE dans le produit, pas les erreurs de
l outil qui le juge.

La règle corrigée : un tour peut porter `faux_positifs_contestes`, chaque entrée nommée
(`finding`, `motif`) ; elles se retranchent des anomalies révélées. Une entrée anonyme ne
retranche rien, et elle est dite.
"""

from __future__ import annotations

from forge_tests import boucle


def _tour(rang: int, nouvelles: int, faux: list | None = None) -> dict:
    tour = {"tour": rang, "nouvelles": nouvelles}
    if faux is not None:
        tour["faux_positifs_contestes"] = faux
    return tour


def test_faux_positifs_contestes_ne_comptent_pas_comme_revelees() -> None:
    faux = [
        {"finding": f"qualif:effet:/:{i}:form", "motif": "délégation sur #root (TF-1791)"}
        for i in range(6)
    ]
    tours = [_tour(1, 4), _tour(2, 7, faux)]
    mesure = boucle.convergence(tours)
    assert mesure["revelees_par_tour"] == [4, 1]
    assert mesure["faux_positifs_par_tour"] == [0, 6]
    assert mesure["converge"] is True
    assert mesure["signal"] == ""


def test_vraie_hausse_reste_non_convergente() -> None:
    """Le sens fautif tient : sans contestation, 7 après 4 ne converge pas."""
    mesure = boucle.convergence([_tour(1, 4), _tour(2, 7)])
    assert mesure["converge"] is False
    assert "NON CONVERGENTE" in mesure["signal"]


def test_contestation_anonyme_ne_retranche_rien_et_se_dit() -> None:
    tours = [_tour(1, 4), _tour(2, 7, [{"finding": "x"}, "y"])]
    mesure = boucle.convergence(tours)
    assert mesure["revelees_par_tour"] == [4, 7]
    assert mesure["converge"] is False
    assert len(mesure["contestations_refusees"]) == 2
