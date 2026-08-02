"""Adaptateur Data (SQL) — tables et contraintes depuis les migrations, exercées PAR VIOLATION."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "data-sql", "data", 1.0
_TABLE = re.compile(r"CREATE TABLE (\w+)\s*\(", re.IGNORECASE)
_CONTRAINTE = re.compile(r"CONSTRAINT (\w+)", re.IGNORECASE)
_NOT_NULL = re.compile(r"^\s*(\w+)\s+\w+\s+NOT NULL", re.IGNORECASE | re.MULTILINE)

NON_JUGE = [
    "data : une contrainte est réputée exercée si son nom ou sa colonne apparaît dans un test "
    "attendant un rejet ; l oracle ne vérifie pas que le rejet porte bien sur cette contrainte",
    "data : contraintes créées hors migrations (ORM seul, triggers, index partiels)",
]


def _sql(cible: Path) -> list[Path]:
    return sorted((cible / "backend" / "migrations").glob("*.sql"))


def inventaire(cible: Path) -> list[Element]:
    elements: list[Element] = []
    vus: set[str] = set()
    for fichier in _sql(cible):
        haut = fichier.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
        for table in _TABLE.findall(haut):
            if f"table:{table}" not in vus and not table.endswith(("_nouveau", "_ancien")):
                vus.add(f"table:{table}")
                elements.append(Element(f"table:{table}", PAN, f"table {table}", str(fichier)))
        for nom in _CONTRAINTE.findall(haut):
            if f"contrainte:{nom}" not in vus:
                vus.add(f"contrainte:{nom}")
                elements.append(
                    Element(f"contrainte:{nom}", PAN, f"contrainte {nom}", str(fichier))
                )
        for colonne in _NOT_NULL.findall(haut):
            cle = f"contrainte:{colonne}.not_null"
            if cle not in vus:
                vus.add(cle)
                elements.append(Element(cle, PAN, f"{colonne} NOT NULL", str(fichier)))
    return elements


def blocs_de_test(texte: str) -> list[str]:
    """Découpe en blocs de test, commentaires de tête RATTACHÉS à leur def.

    Sans ce rattachement, un test annoté du nom de la contrainte qu il exerce passerait pour
    ne pas la couvrir : le commentaire tomberait dans le bloc précédent.
    """
    blocs: list[str] = []
    report = ""
    for morceau in re.split(r"\n(?=def )", texte):
        lignes = morceau.splitlines()
        fin = len(lignes)
        while fin > 0 and (lignes[fin - 1].strip().startswith("#") or not lignes[fin - 1].strip()):
            fin -= 1
        blocs.append(report + "\n".join(lignes[:fin]))
        report = "\n".join(lignes[fin:]) + "\n"
    if report.strip():
        blocs.append(report)
    return blocs


def exerces(cible: Path) -> set[str]:
    couvert: set[str] = set()
    inv = inventaire(cible)
    for fichier in sorted((cible / "backend" / "tests").glob("test_*.py")):
        for bloc in blocs_de_test(fichier.read_text(encoding="utf-8")):
            rejet_attendu = "raises" in bloc
            for element in inv:
                cle = element.id.split(":", 1)[1]
                if element.id.startswith("table:"):
                    if cle in bloc.lower():
                        couvert.add(element.id)
                    continue
                colonne = cle.replace(".not_null", "")
                if rejet_attendu and (cle in bloc or colonne in bloc):
                    couvert.add(element.id)
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE)
