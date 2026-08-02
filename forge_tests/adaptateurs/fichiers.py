"""Adaptateur Fichiers — variantes de format déclarées dans la source."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "fichiers-python", "fichiers", 1.0
_VARIANTES = re.compile(r"VARIANTES\s*=\s*\(([^)]*)\)")
_ITEM = re.compile(r"\"([^\"]+)\"")

NON_JUGE = [
    "fichiers : l inventaire s appuie sur le tuple VARIANTES déclaré dans la source ; un projet "
    "sans déclaration exige une analyse des chemins de parsing, non implémentée",
]


def _src(cible: Path) -> Path:
    return cible / "backend" / "app" / "importer.py"


def inventaire(cible: Path) -> list[Element]:
    src = _src(cible)
    if not src.exists():
        return []
    elements: list[Element] = []
    for bloc in _VARIANTES.findall(src.read_text(encoding="utf-8")):
        for variante in _ITEM.findall(bloc):
            elements.append(
                Element(f"variante:{variante}", PAN, f"variante de format {variante}", str(src))
            )
    return elements


def exerces(cible: Path) -> set[str]:
    textes = " ".join(
        f.read_text(encoding="utf-8").lower()
        for f in sorted((cible / "backend" / "tests").glob("test_*.py"))
    )
    return {e.id for e in inventaire(cible) if e.id.split(":", 1)[1].lower() in textes}


def analyser(cible: Path) -> SortieAdaptateur:
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE)
