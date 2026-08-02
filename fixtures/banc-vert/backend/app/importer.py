"""Import CSV des commandes — 6 variantes de format, 1 règle de rapprochement de totaux."""

from __future__ import annotations

VARIANTES = ("F1", "F2", "F3", "F4", "F5", "F6")

BOM = "﻿"


def _decoder(brut: bytes) -> str:
    """F3 — repli latin-1 quand l UTF-8 échoue."""
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError:
        texte = brut.decode("latin-1")
    # F2 — un BOM en tête corromprait le nom de la première colonne.
    return texte.removeprefix(BOM)


def _separateur(entete: str) -> str:
    """F4 — point-virgule accepté au même titre que la virgule."""
    return ";" if entete.count(";") > entete.count(",") else ","


def importer_csv(brut: bytes) -> tuple[list[dict], int]:
    """Renvoie (lignes importées, total). Lève ValueError si le rapprochement échoue."""
    texte = _decoder(brut)
    lignes_brutes = [ligne for ligne in texte.splitlines() if ligne.strip()]  # F5 — ligne vide
    if not lignes_brutes:
        raise ValueError("fichier vide")
    sep = _separateur(lignes_brutes[0])
    entete = [c.strip() for c in lignes_brutes[0].split(sep)]
    if "plat" not in entete or "quantite" not in entete:
        raise ValueError(f"colonnes attendues plat/quantite, reçues {entete}")
    i_plat, i_qte = entete.index("plat"), entete.index("quantite")

    lignes: list[dict] = []
    total_declare: int | None = None
    for ligne in lignes_brutes[1:]:
        cellules = [c.strip() for c in ligne.split(sep)]
        if cellules[i_plat].upper() == "TOTAL":
            total_declare = int(cellules[i_qte])
            continue
        lignes.append({"plat": cellules[i_plat], "quantite": int(cellules[i_qte])})

    total = sum(ligne["quantite"] for ligne in lignes)
    # F6 — rapprochement : un écart signale un rejet silencieux en amont.
    if total_declare is not None and total_declare != total:
        raise ValueError(f"rapprochement de totaux : déclaré {total_declare}, importé {total}")
    return lignes, total
