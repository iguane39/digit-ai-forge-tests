"""Adaptateur Mutation (Python) — second contre-oracle : ce qu on atteint, le vérifie-t-on ?

Mutation réellement exécutée : on altère la source, on relance la suite, on compte les
survivants. Un mutant survivant est nommé avec sa ligne — jamais un total agrégé seul.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN, SEUIL = "mutation-python", "back", 0.70
CIBLE_RELATIVE = Path("backend/app/calcul.py")
SUITE_RELATIVE = "tests/test_calcul.py"

NON_JUGE = [
    "mutation : périmètre limité au module de calcul ; le reste du back n est pas muté",
    "mutation : les mutants équivalents ne sont pas détectés — un survivant peut être un mutant "
    "sémantiquement identique à l original",
    "mutation : opérateurs arithmétiques et constantes numériques seulement",
]

_SUBSTITUTIONS = (("+", "-"), ("-", "+"), ("*", "/"), ("/", "*"))


@dataclass(frozen=True)
class Mutant:
    ligne: int
    colonne: int
    avant: str
    apres: str

    @property
    def id(self) -> str:
        return f"mutant:calcul.py:{self.ligne}:{self.avant}->{self.apres}"


def _lignes_calculantes(lignes: list[str]) -> list[int]:
    """Lignes portant du calcul EXÉCUTABLE.

    L intérieur des docstrings est exclu : y muter un opérateur produit un mutant équivalent
    par construction, qui survit toujours et fait chuter le score sans rien signaler de vrai.
    """
    retenues: list[int] = []
    dans_docstring = False
    for i, ligne in enumerate(lignes):
        nu = ligne.strip()
        marqueurs = nu.count('"""') + nu.count("'''")
        if dans_docstring:
            if marqueurs:
                dans_docstring = False
            continue
        if marqueurs == 1:
            dans_docstring = True
            continue
        if marqueurs >= 2:  # docstring sur une seule ligne
            continue
        if not nu or nu.startswith(("#", "if ", "raise ", "from ", "import ")):
            continue
        if any(op in nu for op, _ in _SUBSTITUTIONS) and ("=" in nu or nu.startswith("return")):
            retenues.append(i)
    return retenues


def generer_mutants(source: Path) -> list[Mutant]:
    lignes = source.read_text(encoding="utf-8").splitlines()
    mutants: list[Mutant] = []
    for i in _lignes_calculantes(lignes):
        for j, caractere in enumerate(lignes[i]):
            for avant, apres in _SUBSTITUTIONS:
                if caractere == avant:
                    mutants.append(Mutant(i, j, avant, apres))
    return mutants


def _purger_bytecode(racine: Path) -> None:
    """Un mutant a la MEME TAILLE que l original ; si la restauration tombe dans la meme
    seconde, Python reutilise un .pyc perime et la suite juge un code qui n existe plus."""
    for cache in racine.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _suite_verte(banc: Path, python: Path) -> bool:
    racine = banc / "backend"
    _purger_bytecode(racine)
    resultat = subprocess.run(
        [str(python), "-m", "pytest", SUITE_RELATIVE, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=racine,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return resultat.returncode == 0


def analyser(cible: Path) -> SortieAdaptateur:
    source = cible / CIBLE_RELATIVE
    python = cible / "backend" / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = cible / "backend" / ".venv" / "bin" / "python"
    if not source.exists() or not python.exists():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP", non_juge=[*NON_JUGE, "environnement du banc absent"]
        )

    original = source.read_text(encoding="utf-8")
    mutants = generer_mutants(source)
    survivants: list[Mutant] = []
    viables = 0
    try:
        if not _suite_verte(cible, python):
            return SortieAdaptateur(
                NOM,
                PAN,
                str(cible),
                "SKIP",
                non_juge=[*NON_JUGE, "suite rouge avant mutation : score non calculable"],
            )
        for mutant in mutants:
            lignes = original.splitlines()
            ligne = lignes[mutant.ligne]
            lignes[mutant.ligne] = ligne[: mutant.colonne] + mutant.apres + ligne[mutant.colonne + 1 :]
            mute = "\n".join(lignes) + "\n"
            try:
                compile(mute, str(source), "exec")
            except SyntaxError:
                continue  # mutant non viable : ignoré du dénominateur
            viables += 1
            source.write_text(mute, encoding="utf-8")
            if _suite_verte(cible, python):
                survivants.append(mutant)
    finally:
        source.write_text(original, encoding="utf-8")
        _purger_bytecode(cible / "backend")

    tues = viables - len(survivants)
    score = tues / viables if viables else 0.0
    # Un survivant est NOMMÉ (on ne masque jamais), mais c est le SEUIL qui bloque : au-dessus,
    # des survivants résiduels sont une information, pas un échec.
    findings = [
        Finding(
            id=m.id,
            classe="mutant-survivant",
            localisation=f"{source}:{m.ligne + 1}",
            message=f"mutant {m.avant} -> {m.apres} non tué : la suite reste verte",
            severite="signale",
            risque=coter(PAN, m.id, str(source)),
        )
        for m in survivants
    ]
    if viables and score < SEUIL:
        findings.append(
            Finding(
                id=f"seuil:{PAN}",
                classe="seuil-non-tenu",
                localisation=str(cible),
                message=f"score de mutation {score:.0%} sous le seuil {SEUIL:.0%}",
                risque=coter(PAN, f"seuil:{PAN}", str(source)),
            )
        )
    bloquants = [f for f in findings if f.severite == "bloquant"]
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if bloquants else "PASS",
        findings=findings,
        non_juge=list(NON_JUGE),
        mutation={
            "mutants_viables": viables,
            "tues": tues,
            "score": round(score, 4),
            "survivants": [m.id for m in survivants],
        },
    )
