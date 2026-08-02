"""Suite Fichiers couvrante : les 6 variantes de format et le rapprochement de totaux."""

from __future__ import annotations

import pytest

from app.importer import importer_csv

BOM = b"\xef\xbb\xbf"


# F1 — UTF-8, séparateur virgule
def test_f1_utf8_virgule() -> None:
    lignes, total = importer_csv(b"plat,quantite\ncurry,2\nsoupe,3\n")
    assert len(lignes) == 2 and total == 5


# F2 — BOM UTF-8 en tête
def test_f2_bom() -> None:
    lignes, total = importer_csv(BOM + b"plat,quantite\ncurry,2\n")
    assert len(lignes) == 1 and lignes[0]["plat"] == "curry"


# F3 — latin-1 avec accents
def test_f3_latin1() -> None:
    lignes, _ = importer_csv("plat,quantite\ncrème,1\n".encode("latin-1"))
    assert lignes[0]["plat"] == "crème"


# F4 — séparateur point-virgule
def test_f4_point_virgule() -> None:
    lignes, total = importer_csv(b"plat;quantite\ncurry;4\n")
    assert len(lignes) == 1 and total == 4


# F5 — ligne vide en fin de fichier
def test_f5_ligne_vide_finale() -> None:
    lignes, total = importer_csv(b"plat,quantite\ncurry,2\n\n")
    assert len(lignes) == 1 and total == 2


# F6 — rapprochement de totaux
def test_f6_rapprochement_ok() -> None:
    _, total = importer_csv(b"plat,quantite\ncurry,2\nsoupe,3\nTOTAL,5\n")
    assert total == 5


def test_f6_rapprochement_ecart_refuse() -> None:
    with pytest.raises(ValueError, match="rapprochement"):
        importer_csv(b"plat,quantite\ncurry,2\nTOTAL,9\n")


# F0 - fichier vide : chemin de rejet revele par la couverture d execution
def test_f0_fichier_vide() -> None:
    with pytest.raises(ValueError, match="vide"):
        importer_csv(b"")
