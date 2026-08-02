"""Adaptateur Batch — branches de traitement et codes de rejet déclarés dans la source."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "batch-python", "batch", 0.90
_BRANCHES = re.compile(r"BRANCHES\s*=\s*\(([^)]*)\)")
_CODES = re.compile(r"CODES_REJET\s*=\s*\(([^)]*)\)")
_ITEM = re.compile(r"\"([^\"]+)\"")

NON_JUGE = [
    "batch : l inventaire s appuie sur les tuples BRANCHES/CODES_REJET déclarés dans la source ; "
    "un projet sans déclaration exige une analyse de flot de contrôle, non implémentée",
    "batch : une branche est réputée exercée si son identifiant apparaît dans la suite",
]


def _src(cible: Path) -> Path:
    return cible / "backend" / "app" / "batch.py"


def inventaire(cible: Path) -> list[Element]:
    src = _src(cible)
    if not src.exists():
        return []
    texte = src.read_text(encoding="utf-8")
    elements: list[Element] = []
    for bloc in _BRANCHES.findall(texte):
        for branche in _ITEM.findall(bloc):
            elements.append(Element(f"branche:{branche}", PAN, f"branche {branche}", str(src)))
    for bloc in _CODES.findall(texte):
        for code in _ITEM.findall(bloc):
            elements.append(Element(f"rejet:{code}", PAN, f"code de rejet {code}", str(src)))
    return elements


def exerces(cible: Path) -> set[str]:
    textes = " ".join(
        f.read_text(encoding="utf-8")
        for f in sorted((cible / "backend" / "tests").glob("test_*.py"))
    )
    couvert: set[str] = set()
    for element in inventaire(cible):
        jeton = element.id.split(":", 1)[1]
        if jeton in textes or jeton.replace("-", "_") in textes:
            couvert.add(element.id)
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE)
