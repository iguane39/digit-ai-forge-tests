"""Adaptateur API (FastAPI) — endpoints x methodes x codes de retour depuis le code source."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.execution import codes_emis, schema_openapi
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "api-fastapi", "api", 1.0
_ROUTE = re.compile(r'@app\.(get|post|patch|put|delete)\(\s*"([^"]+)"(.*?)\)\s*\n', re.DOTALL)
_CODE = re.compile(r"(\d{3})\s*:")
_APPEL = re.compile(r'client\.(get|post|patch|put|delete)\(\s*f?"([^"]+)"')
_STATUT = re.compile(r"status_code\s*==\s*(\d{3})")

NON_JUGE = [
    "api : un code emis pendant la suite est repute couvert ; la sonde ne verifie pas qu une "
    "ASSERTION porte sur lui — c est le role du second contre-oracle",
]


def _norm(chemin: str) -> str:
    chemin = chemin.split("?")[0]
    chemin = re.sub(r"\{[^}]*\}", "{}", chemin)
    return re.sub(r"/\d+", "/{}", chemin)


def inventaire(cible: Path) -> list[Element]:
    src = cible / "backend" / "app" / "main.py"
    if not src.exists():
        return []
    texte = src.read_text(encoding="utf-8")
    elements: list[Element] = []
    for methode, chemin, reste in _ROUTE.findall(texte):
        m, c = methode.upper(), _norm(chemin)
        elements.append(Element(f"endpoint:{m} {c}", PAN, f"{m} {c}", str(src)))
        for code in dict.fromkeys(_CODE.findall(reste)):
            elements.append(Element(f"code:{m} {c}={code}", PAN, f"{m} {c} -> {code}", str(src)))
    return elements


def exerces(cible: Path) -> set[str]:
    couvert: set[str] = set()
    for fichier in sorted((cible / "backend" / "tests").glob("test_*.py")):
        for bloc in re.split(r"\ndef ", fichier.read_text(encoding="utf-8")):
            appels = [(m.upper(), _norm(c)) for m, c in _APPEL.findall(bloc)]
            codes = set(_STATUT.findall(bloc))
            for m, c in appels:
                couvert.add(f"endpoint:{m} {c}")
                for code in codes:
                    couvert.add(f"code:{m} {c}={code}")
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, "sonde indisponible : suite rouge ou environnement absent"],
        )
    inv = inventaire(cible)
    sortie = evaluer_surface(NOM, PAN, str(cible), inv, couvert, SEUIL, NON_JUGE)
    # Un code EMIS pendant la suite mais absent de `responses=` est une divergence entre ce que
    # la source declare et ce que le code fait. Ni un trou de couverture, ni un silence : un ecart.
    declares = {e.id for e in inv if e.id.startswith("code:")}
    for identifiant in sorted(couvert - declares):
        if not identifiant.startswith("code:"):
            continue
        sortie.findings.append(
            Finding(
                id=identifiant,
                classe="divergence",
                localisation=str(cible / "backend" / "app" / "main.py"),
                message="code emis par l application mais absent de sa declaration responses=",
                severite="signale",
                risque=coter(PAN, identifiant, str(cible / "backend" / "app" / "main.py")),
            )
        )
    return sortie
