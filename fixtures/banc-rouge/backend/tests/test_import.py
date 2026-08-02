"""Suite Fichiers."""

from __future__ import annotations

from app.importer import importer_csv


# F1
def test_import_nominal() -> None:
    lignes, total = importer_csv(b"plat,quantite\ncurry,2\nsoupe,3\n")
    assert len(lignes) == 2 and total == 5
