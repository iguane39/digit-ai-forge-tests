"""Disposition des sources du projet audité — où vit son paquet Python.

Le framework a longtemps tenu `backend/app` pour acquis : `coverage run --source=app,tests`
dans `execution.py`, `DOSSIER_SOURCE = backend/app` dans l adaptateur de mutation, et les
chemins conventionnels des pans `batch` et `fichiers`. Un projet dont le paquet s appelle
autrement voyait donc SIX pans plafonnés à `SKIP` quelles que soient sa suite et sa couverture
— et le motif publié parlait d un environnement Python absent, ce qui envoyait chercher un
problème qui n existait pas.

Constaté le 12/08/2026 sur Bourse aux Vacants 2, dont le paquet s appelle `src` : suite verte
de 116 tests, couverture de branches à 94 %, et pourtant `mutation : aucun dossier de sources
sous backend/app`. La preuve que seul le NOM était en cause a été faite par contre-oracle —
le moteur de mutation joué sur `backend/src` puis sur une copie renommée `backend/app` rend
exactement les mêmes chiffres : 189 mutants viables, 20 tués, score 0,1058.

Le parti pris suit celui de TF-0097 : on DÉCOUVRE la disposition du projet, on ne lui impose
pas la nôtre. `FORGE_TESTS_SOURCES` n est qu un dernier recours, pour le cas ambigu que la
découverte refuse de trancher — et quand elle le refuse, elle le DIT au lieu de deviner.
"""

from __future__ import annotations

import os
from pathlib import Path

# Ce qui vit sous `backend/` sans être le paquet du produit. `tests` en fait partie : la suite
# n est pas la source qu on mute, et `coverage` la reçoit déjà par ailleurs.
_HORS_SOURCES = {
    ".venv", "venv", "env", "node_modules", "__pycache__", "tests", "test",
    "migrations", "alembic", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "requirements", "scripts", "docs", ".idea", ".vscode", "htmlcov", "build", "dist",
    ".eggs", "site-packages",
}

# Essayés dans cet ordre avant toute découverte : deux conventions largement répandues.
_CONVENTIONS = ("app", "src")


def _candidats(racine: Path) -> list[Path]:
    """Dossiers de `backend/` qui ressemblent à un paquet Python du projet."""
    if not racine.is_dir():
        return []
    retenus = []
    for entree in sorted(racine.iterdir()):
        if not entree.is_dir() or entree.name in _HORS_SOURCES or entree.name.startswith("."):
            continue
        if next(entree.rglob("*.py"), None) is not None:
            retenus.append(entree)
    return retenus


def paquet_sources(cible: Path) -> Path | None:
    """Racine des sources Python du projet, ou None si elle n est pas déterminable.

    Ordre : déclaration explicite, puis conventions (`app`, `src`), puis découverte quand
    elle ne laisse qu un seul candidat. Plusieurs candidats — un vrai paquet et un dossier
    d outillage, par exemple — ne se départagent pas sans risque : on rend None, et l appelant
    publie le motif.
    """
    racine = cible / "backend"

    declare = (os.environ.get("FORGE_TESTS_SOURCES") or "").strip()
    if declare:
        chemin = Path(declare)
        chemin = chemin if chemin.is_absolute() else racine / chemin
        return chemin if chemin.is_dir() else None

    for nom in _CONVENTIONS:
        if (racine / nom).is_dir():
            return racine / nom

    candidats = _candidats(racine)
    return candidats[0] if len(candidats) == 1 else None


def nom_paquet_sources(cible: Path) -> str | None:
    """Nom du paquet, tel que `coverage --source=` l attend."""
    dossier = paquet_sources(cible)
    return None if dossier is None else dossier.name


def motif_indetermine(cible: Path) -> str:
    """Pourquoi la disposition n a pas pu être tranchée — jamais un silence."""
    racine = cible / "backend"
    if not racine.is_dir():
        return f"aucun dossier `backend` sous {cible}"
    declare = (os.environ.get("FORGE_TESTS_SOURCES") or "").strip()
    if declare:
        return (
            f"FORGE_TESTS_SOURCES={declare!r} ne designe aucun dossier existant "
            f"(attendu sous {racine} ou en chemin absolu)"
        )
    candidats = _candidats(racine)
    if not candidats:
        return (
            f"aucun paquet Python sous {racine} : ni `app`, ni `src`, ni aucun dossier "
            "portant des modules"
        )
    return (
        "plusieurs paquets Python possibles sous "
        f"{racine} — {', '.join(c.name for c in candidats)} ; "
        "declarer celui du produit par FORGE_TESTS_SOURCES=<nom>"
    )
