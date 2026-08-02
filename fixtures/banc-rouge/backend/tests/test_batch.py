"""Suite Batch."""

from __future__ import annotations

from app.batch import cloture_journaliere


# B1
def test_cloture_nominale() -> None:
    stock = {"curry": 5}
    res = cloture_journaliere([{"id": 1, "lignes": [{"plat": "curry", "quantite": 1}]}], stock)
    assert res["cloturees"] == [1]
