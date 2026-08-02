"""Adaptateur Front (React) — inventaire de surface depuis le code source.

Capacite 1 : routes depuis la table de routage, elements interactifs depuis les pages.
Capacite 5 : couverture de surface par recoupement avec la suite e2e.
"""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "front-react", "front", 0.90
_ROUTE = re.compile(r'path:\s*"([^"]+)"')
_TESTID = re.compile(r'data-testid="([^"]+)"')
_GOTO = re.compile(r'goto\(\s*"([^"]+)"')
_BYTESTID = re.compile(r'getByTestId\(\s*"([^"]+)"')

NON_JUGE = [
    "front : un element mentionne par la suite est repute exerce ; l oracle ne verifie pas que "
    "l interaction a lieu ni qu elle assert quelque chose",
    "front : elements rendus dynamiquement sans data-testid statique (non inventoriables ici)",
]


def _racine(cible: Path) -> Path:
    return cible / "frontend"


def inventaire(cible: Path) -> list[Element]:
    racine = _racine(cible)
    elements: list[Element] = []
    routes_src = racine / "src" / "routes.jsx"
    if routes_src.exists():
        for chemin in _ROUTE.findall(routes_src.read_text(encoding="utf-8")):
            elements.append(Element(f"route:{chemin}", PAN, f"route {chemin}", str(routes_src)))
    for page in sorted((racine / "src" / "pages").glob("*.jsx")):
        for tid in _TESTID.findall(page.read_text(encoding="utf-8")):
            elements.append(
                Element(f"element:{tid}", PAN, f"element interactif {tid}", str(page))
            )
    return elements


def exerces(cible: Path) -> set[str]:
    couvert: set[str] = set()
    for spec in sorted((_racine(cible) / "tests").glob("*.spec.js")):
        texte = spec.read_text(encoding="utf-8")
        for chemin in _GOTO.findall(texte):
            couvert.add(f"route:{re.sub(r'/\d+', '/:id', chemin)}")
        for tid in _BYTESTID.findall(texte):
            couvert.add(f"element:{tid}")
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE)
