"""Suite Batch couvrante : les 5 branches et les 2 codes de rejet."""

from __future__ import annotations

from app.batch import REJ_STOCK, REJ_VIDE, cloture_journaliere


def _commande(cid: int, plat: str = "curry", quantite: int = 1) -> dict:
    return {"id": cid, "lignes": [{"plat": plat, "quantite": quantite}]}


# B1 — nominal
def test_b1_nominal() -> None:
    stock = {"curry": 5}
    res = cloture_journaliere([_commande(1)], stock)
    assert res["cloturees"] == [1] and res["rejets"] == [] and stock["curry"] == 4


# B2 — rejet commande sans ligne
def test_b2_rejet_vide() -> None:
    res = cloture_journaliere([{"id": 2, "lignes": []}], {"curry": 5})
    assert res["rejets"] == [{"id": 2, "code": REJ_VIDE}]


# B3 — rejet stock insuffisant
def test_b3_rejet_stock() -> None:
    res = cloture_journaliere([_commande(3, quantite=10)], {"curry": 1})
    assert res["rejets"] == [{"id": 3, "code": REJ_STOCK}]


# B4 — reprise au dernier point de contrôle
def test_b4_reprise() -> None:
    journal = {"point_de_controle": [1], "cloturees": [1], "rejets": []}
    stock = {"curry": 5}
    res = cloture_journaliere([_commande(1), _commande(2)], stock, journal)
    assert res["reprise"] is True
    assert res["cloturees"] == [1, 2]
    assert stock["curry"] == 4  # la commande 1 nest pas déstockée deux fois


# B5 — idempotence
def test_b5_idempotence() -> None:
    stock = {"curry": 5}
    journal: dict = {}
    premier = cloture_journaliere([_commande(1)], stock, journal)
    second = cloture_journaliere([_commande(1)], stock, journal)
    assert second["cloturees"] == premier["cloturees"]
    assert stock["curry"] == 4  # aucun effet au second passage
