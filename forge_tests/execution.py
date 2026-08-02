"""Couverture d EXÉCUTION — P2.

Remplace le recoupement textuel (« la suite mentionne cet élément ») par la mesure de ce que
la suite ATTEINT réellement. Le recoupement textuel était le `non_juge` le plus dangereux du
framework : un test citant une route dans un commentaire comptait comme couverture, ce qui
réintroduisait le défaut D-01 à l étage du framework lui-même.

Règle R3 — on s appuie sur l outil qui fait foi (coverage.py), on ne réimplémente pas la
mesure d exécution.
"""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

NON_JUGE = [
    "exécution : la couverture est mesurée au niveau LIGNE ; deux branches sur une même ligne "
    "ne sont pas distinguées",
    "exécution : une ligne atteinte n implique pas qu elle soit ASSERTÉE — c est le rôle du "
    "second contre-oracle (mutation)",
]


def _python(banc: Path) -> Path | None:
    for candidat in (
        banc / "backend" / ".venv" / "Scripts" / "python.exe",
        banc / "backend" / ".venv" / "bin" / "python",
    ):
        if candidat.exists():
            return candidat
    return None


@lru_cache(maxsize=32)
def lignes_executees(banc_str: str) -> dict[str, frozenset[int]] | None:
    """Lance la suite du projet sous coverage et renvoie les lignes réellement exécutées.

    Renvoie None si la mesure est impossible (environnement absent, suite rouge) — l appelant
    doit alors DÉCLARER qu il ne juge pas, jamais supposer une couverture.
    """
    banc = Path(banc_str)
    python = _python(banc)
    if python is None:
        return None
    racine = banc / "backend"
    commun = ["-p", "no:cacheprovider"]
    lance = subprocess.run(
        [str(python), "-m", "coverage", "run", "--branch", "--source=app", "-m", "pytest", "-q", *commun],
        cwd=racine,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if lance.returncode != 0:
        return None
    rapport = subprocess.run(
        [str(python), "-m", "coverage", "json", "-o", "-", "--quiet"],
        cwd=racine,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if rapport.returncode != 0 or not rapport.stdout.strip():
        return None
    donnees = json.loads(rapport.stdout)
    resultat: dict[str, frozenset[int]] = {}
    for chemin, detail in donnees.get("files", {}).items():
        nom = Path(chemin).name
        resultat[nom] = frozenset(detail.get("executed_lines", []))
    return resultat


def executees(banc: Path, fichier: str) -> frozenset[int] | None:
    """Lignes exécutées du fichier demandé, ou None si la mesure n a pas pu être faite."""
    tout = lignes_executees(str(banc))
    if tout is None:
        return None
    return tout.get(fichier)
