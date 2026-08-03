"""Couverture d EXÉCUTION — P2.

Remplace le recoupement textuel (« la suite mentionne cet élément ») par la mesure de ce que
la suite ATTEINT réellement. Le recoupement textuel était le `non_juge` le plus dangereux du
framework : un test citant une route dans un commentaire comptait comme couverture, ce qui
réintroduisait le défaut D-01 à l étage du framework lui-même.

Une seule exécution de la suite produit les deux mesures : lignes couvertes (coverage.py,
règle R3 — l outil qui fait foi) et codes de retour réellement émis (sonde ASGI greffée de
l extérieur, sans toucher un fichier du projet).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

SONDES = Path(__file__).resolve().parent / "sondes"

NON_JUGE = [
    "exécution : la couverture combine lignes et ARCS de branchement ; une branche implicite "
    "(ternaire, court-circuit booléen) reste hors de portée de coverage.py",
    "exécution : une ligne atteinte n implique pas qu elle soit ASSERTÉE — c est le rôle du "
    "second contre-oracle (mutation)",
]


def _python(banc: Path) -> Path | None:
    for candidat in (
        banc / "backend" / ".venv" / "Scripts" / "python.exe",
        banc / "backend" / ".venv" / "bin" / "python",
        # Workspace uv : le venv vit a la RACINE du depot (constate sur le premier projet reel)
        banc / ".venv" / "Scripts" / "python.exe",
        banc / ".venv" / "bin" / "python",
    ):
        if candidat.exists():
            return candidat
    return None


@lru_cache(maxsize=32)
def mesurer(banc_str: str) -> dict | None:
    """Lance la suite UNE fois, sous coverage et sous sonde. None si la mesure est impossible.

    None n est pas « rien à signaler » : l appelant doit DÉCLARER qu il ne juge pas.
    """
    banc = Path(banc_str)
    # Inventaire seul : executer la suite d un projet REEL peut exiger son infrastructure
    # complete et durer sans borne. Ce mode la court-circuite en le DECLARANT — chaque
    # adaptateur repond alors « inventorie N, couverture non mesurable », jamais un faux vert.
    if os.environ.get("FORGE_TESTS_SANS_EXECUTION") == "1":
        return None
    python = _python(banc)
    if python is None:
        return None
    racine = banc / "backend"
    with tempfile.TemporaryDirectory() as temporaire:
        releve = Path(temporaire) / "sonde.json"
        releve_data = Path(temporaire) / "sonde-data.json"
        env = {
            **os.environ,
            "FORGE_TESTS_SONDE": str(releve),
            "FORGE_TESTS_SONDE_DATA": str(releve_data),
            "PYTHONPATH": str(SONDES),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        lance = subprocess.run(
            [
                str(python), "-m", "coverage", "run", "--branch", "--source=app,tests",
                "-m", "pytest", "-q", "--no-header",
                "-p", "no:cacheprovider", "-p", "no:warnings", "-p", "sonde_api", "-p", "sonde_data",
            ],
            cwd=racine, capture_output=True, text=True, timeout=900, env=env,
        )
        if lance.returncode != 0:
            return None
        codes = json.loads(releve.read_text(encoding="utf-8")) if releve.exists() else []
        brut_data = (
            json.loads(releve_data.read_text(encoding="utf-8")) if releve_data.exists() else {}
        )
        violations = brut_data.get("violations", [])
        instructions = brut_data.get("instructions", [])

    rapport = subprocess.run(
        [str(python), "-m", "coverage", "json", "-o", "-", "--quiet"],
        cwd=racine, capture_output=True, text=True, timeout=120,
    )
    if rapport.returncode != 0 or not rapport.stdout.strip():
        return None
    donnees = json.loads(rapport.stdout)
    lignes = {
        Path(chemin).name: frozenset(detail.get("executed_lines", []))
        for chemin, detail in donnees.get("files", {}).items()
    }
    arcs = {
        Path(chemin).name: frozenset(
            (int(a), int(b)) for a, b in detail.get("executed_branches", [])
        )
        for chemin, detail in donnees.get("files", {}).items()
    }
    return {
        "lignes": lignes,
        "arcs": arcs,
        "codes": codes,
        "violations": violations,
        "instructions": instructions,
    }


def executees(banc: Path, fichier: str) -> frozenset[int] | None:
    """Lignes exécutées du fichier demandé, ou None si la mesure n a pas pu être faite."""
    mesure = mesurer(str(banc))
    if mesure is None:
        return None
    return mesure["lignes"].get(fichier)


def violations_levees(banc: Path) -> list[str] | None:
    """Messages de violation de contrainte reellement levees par la base pendant la suite."""
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["violations"]


def arcs_executes(banc: Path, fichier: str) -> frozenset[tuple[int, int]] | None:
    """Arcs de branchement reellement pris (ligne du test -> ligne atteinte)."""
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["arcs"].get(fichier)


def instructions_sql(banc: Path) -> list[str] | None:
    """Instructions SQL reellement envoyees au moteur pendant la suite."""
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["instructions"]


def codes_emis(banc: Path) -> list[dict] | None:
    """Couples (méthode, gabarit, code) réellement émis pendant la suite."""
    mesure = mesurer(str(banc))
    if mesure is None:
        return None
    return mesure["codes"]


@lru_cache(maxsize=32)
def schema_openapi(banc_str: str) -> dict | None:
    """Schema OpenAPI declare par l application analysee (source qui fait foi, regle R3)."""
    banc = Path(banc_str)
    python = _python(banc)
    if python is None:
        return None
    with tempfile.TemporaryDirectory() as temporaire:
        sortie = Path(temporaire) / "openapi.json"
        resultat = subprocess.run(
            [str(python), str(SONDES / "dump_openapi.py"), str(sortie)],
            cwd=banc / "backend",
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if resultat.returncode != 0 or not sortie.exists():
            return None
        donnees = json.loads(sortie.read_text(encoding="utf-8"))
    return None if "erreur" in donnees else donnees


@lru_cache(maxsize=16)
def front_execute(banc_str: str) -> dict | None:
    """Routes visitees et elements reellement manipules pendant la suite front.

    Lance la suite Playwright du projet avec la TRACE activee, puis lit la trace : chaque action
    y porte son selecteur et chaque navigation son URL. Aucune modification du projet analyse —
    l instrumentation est un drapeau de ligne de commande.
    """
    import collections
    import re
    import zipfile

    banc = Path(banc_str)
    front = banc / "frontend"
    if not (front / "node_modules").is_dir():
        return None
    npx = shutil.which("npx")
    if npx is None:
        return None
    resultat = subprocess.run(
        [npx, "playwright", "test", "--trace", "on", "--reporter=line"],
        cwd=front, capture_output=True, text=True, timeout=900,
        env={**os.environ, "CI": "1"},
    )
    if resultat.returncode != 0:
        return None
    testids: set[str] = set()
    routes: set[str] = set()
    motif = re.compile(r'data-testid="([^"]+)"')
    for archive in (front / "test-results").rglob("trace.zip"):
        with zipfile.ZipFile(archive) as arc:
            for nom in arc.namelist():
                if not nom.endswith(".trace"):
                    continue
                for ligne in arc.read(nom).decode("utf-8", "replace").splitlines():
                    try:
                        entree = json.loads(ligne)
                    except json.JSONDecodeError:
                        continue
                    params = entree.get("params") or {}
                    trouve = motif.search(str(params.get("selector", "")))
                    if trouve:
                        testids.add(trouve.group(1))
                    url = params.get("url")
                    if isinstance(url, str) and url.startswith("/"):
                        routes.add(url)
    del collections
    return {"routes": sorted(routes), "testids": sorted(testids)}


@lru_cache(maxsize=16)
def schema_obtenu(banc_str: str) -> dict | None:
    """Schema REELLEMENT produit par l application des migrations sur une base neuve."""
    banc = Path(banc_str)
    python = _python(banc)
    if python is None:
        return None
    with tempfile.TemporaryDirectory() as temporaire:
        sortie = Path(temporaire) / "schema.json"
        resultat = subprocess.run(
            [
                str(python), str(SONDES / "verifier_schema.py"),
                str(banc / "backend"), str(sortie),
            ],
            cwd=banc / "backend", capture_output=True, text=True, timeout=900,
            env={**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if resultat.returncode != 0 or not sortie.exists():
            return None
        donnees = json.loads(sortie.read_text(encoding="utf-8"))
    return None if "erreur" in donnees else donnees
