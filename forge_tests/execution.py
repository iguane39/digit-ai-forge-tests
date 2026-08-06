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
    "exécution : la configuration Playwright du projet peut démarrer son propre webServer, qui "
    "ÉCRIT dans l arbre analysé (build, code généré) — hors de portée du garde-fou lecture "
    "seule ; seuls les artefacts produits par Forge Tests sont routés hors du projet",
]

# Motif d indisponibilite d une mesure, par (projet, domaine). Une mesure impossible doit
# DIRE pourquoi : « suite non executee » ne dit pas si la suite est rouge, si l outil manque
# ou si le delai a explose. L appelant lit ce motif et le publie tel quel au rapport.
_MOTIFS: dict[tuple[str, str], str] = {}


def _declarer(banc: Path | str, domaine: str, motif: str) -> None:
    _MOTIFS[(str(banc), domaine)] = motif


def motif_indisponibilite(banc: Path | str, domaine: str, defaut: str) -> str:
    """Motif EXPLICITE de la non-mesure, ou le motif générique de l appelant à défaut."""
    return _MOTIFS.get((str(banc), domaine), defaut)


def _run(
    commande: list[str], *, banc: Path | str, domaine: str, quoi: str, **kwargs
) -> subprocess.CompletedProcess | None:
    """`subprocess.run` qui DÉCLARE au lieu de mourir.

    Deux défauts constatés sur le premier projet réel, tous deux fatals à l audit entier :
    `subprocess.TimeoutExpired` remontait non attrapée et emportait les pans déjà mesurés ;
    `text=True` sans `encoding` décodait la sortie en cp1252 sur Windows et cassait le thread
    lecteur sur le premier accent. Un auditeur qui ne peut pas voir le déclare, jamais ne meurt.
    """
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    try:
        return subprocess.run(commande, **kwargs)  # noqa: S603 — commande construite ici
    except subprocess.TimeoutExpired:
        _declarer(
            banc,
            domaine,
            f"{quoi} : délai de {kwargs.get('timeout')} s dépassé — pan non mesuré, "
            "les autres pans restent mesurés",
        )
        return None
    except OSError as erreur:
        _declarer(banc, domaine, f"{quoi} : lancement impossible ({type(erreur).__name__})")
        return None


def _contrat_projet(banc: Path) -> None:
    """Charge le contrat que le projet audité DÉCLARE dans `<projet>/.env.forge-tests`.

    C est là que le projet désigne son application (`FORGE_TESTS_APP`) : une convention qui
    porte sur le projet doit voyager AVEC lui, pas avec la machine de l opérateur.
    """
    from forge_tests.authentification import charger_env

    charger_env(banc)


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


def _coverage_present(banc: Path, python: Path) -> bool:
    """`coverage` vit dans le venv du projet ANALYSÉ, pas dans celui de Forge Tests.

    Son absence produisait « suite non executee », motif faux : la suite n avait jamais été
    lancée faute d outil. Le motif dit désormais quoi installer et où.
    """
    sonde = _run(
        [str(python), "-c", "import coverage"],
        banc=banc, domaine="backend", quoi="détection de coverage", timeout=60,
    )
    if sonde is None:
        return False
    if sonde.returncode == 0:
        return True
    _declarer(
        banc,
        "backend",
        f"coverage absent du venv du projet — installer coverage dans {python.parent.parent}",
    )
    return False


@lru_cache(maxsize=32)
def mesurer(banc_str: str) -> dict | None:
    """Lance la suite UNE fois, sous coverage et sous sonde. None si la mesure est impossible.

    None n est pas « rien à signaler » : l appelant doit DÉCLARER qu il ne juge pas.
    """
    banc = Path(banc_str)
    _contrat_projet(banc)
    # Inventaire seul : executer la suite d un projet REEL peut exiger son infrastructure
    # complete et durer sans borne. Ce mode la court-circuite en le DECLARANT — chaque
    # adaptateur repond alors « inventorie N, couverture non mesurable », jamais un faux vert.
    if os.environ.get("FORGE_TESTS_SANS_EXECUTION") == "1":
        _declarer(banc, "backend", "exécution désactivée par FORGE_TESTS_SANS_EXECUTION=1")
        return None
    python = _python(banc)
    if python is None:
        _declarer(
            banc,
            "backend",
            "aucun environnement Python dans le projet analysé — attendu "
            f"{banc / 'backend' / '.venv'} ou {banc / '.venv'}",
        )
        return None
    if not _coverage_present(banc, python):
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
            # G-1 (lecture seule) : sans cela coverage depose son `.coverage` DANS le projet
            # analyse. Le releve vit hors du projet, comme les traces du navigateur.
            "COVERAGE_FILE": str(Path(temporaire) / ".coverage"),
        }
        lance = _run(
            [
                str(python), "-m", "coverage", "run", "--branch", "--source=app,tests",
                "-m", "pytest", "-q", "--no-header",
                "-p", "no:cacheprovider", "-p", "no:warnings", "-p", "sonde_api", "-p", "sonde_data",
            ],
            banc=banc, domaine="backend", quoi="suite backend sous coverage",
            cwd=racine, timeout=900, env=env,
        )
        if lance is None:
            return None
        if lance.returncode != 0:
            # RT-6a — une suite rouge FAUTE DE CONFIGURATION le dit dans sa propre trace. La
            # lire ici est le seul endroit du framework où le projet audité nomme lui-même les
            # identifiants qui lui manquent : sans cela, « suite rouge » couvre indistinctement
            # un bug du projet et une clé tierce jamais saisie par l opérateur.
            from forge_tests.qualification import detecter

            manquants = detecter(
                banc, "backend", f"{lance.stdout or ''}\n{lance.stderr or ''}"
            )
            complement = (
                f" — configuration absente citée par la trace : {', '.join(sorted(manquants))}"
                if manquants
                else ""
            )
            _declarer(
                banc,
                "backend",
                f"la suite backend s est terminée en échec (code {lance.returncode}) — "
                f"couverture non mesurable tant que la suite est rouge{complement}",
            )
            return None
        codes = json.loads(releve.read_text(encoding="utf-8")) if releve.exists() else []
        brut_data = (
            json.loads(releve_data.read_text(encoding="utf-8")) if releve_data.exists() else {}
        )
        violations = brut_data.get("violations", [])
        instructions = brut_data.get("instructions", [])
        sources_sql_ = brut_data.get("sources", [])

        # Le relevé vit dans le dossier temporaire : la lecture doit se faire AVANT sa
        # destruction, donc dans le meme bloc.
        rapport = _run(
            [str(python), "-m", "coverage", "json", "-o", "-", "--quiet"],
            banc=banc, domaine="backend", quoi="rapport coverage",
            cwd=racine, timeout=120, env=env,
        )
        if rapport is None:
            return None
        if rapport.returncode != 0 or not rapport.stdout.strip():
            _declarer(
                banc,
                "backend",
                f"coverage n a pas produit de rapport JSON (code {rapport.returncode})",
            )
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
    # A-2 — le relevé par NOM DE FICHIER suffisait tant que le périmètre muté tenait dans un
    # seul dossier plat. Dès qu on descend dans `services/` et `fournisseurs/`, deux modules
    # peuvent porter le même nom : l inventaire de modules a besoin du chemin RELATIF complet,
    # et du résumé chiffré (lignes, branches) que coverage publie déjà par fichier.
    resume = {
        Path(chemin).as_posix(): {
            "lignes_couvertes": int(detail.get("summary", {}).get("covered_lines", 0)),
            "lignes_total": int(detail.get("summary", {}).get("num_statements", 0)),
            "branches_couvertes": int(detail.get("summary", {}).get("covered_branches", 0)),
            "branches_total": int(detail.get("summary", {}).get("num_branches", 0)),
        }
        for chemin, detail in donnees.get("files", {}).items()
    }
    return {
        "lignes": lignes,
        "arcs": arcs,
        "resume_fichiers": resume,
        "codes": codes,
        "violations": violations,
        "instructions": instructions,
        "sources_sql": sources_sql_,
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


def resume_fichiers(banc: Path) -> dict[str, dict] | None:
    """Lignes et branches couvertes PAR FICHIER (chemin relatif au dossier `backend`).

    None = la suite n a pas pu être exécutée. Un dictionnaire VIDE dirait autre chose : que la
    suite a tourné sans rien couvrir. Les deux ne se confondent jamais.
    """
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["resume_fichiers"]


def arcs_executes(banc: Path, fichier: str) -> frozenset[tuple[int, int]] | None:
    """Arcs de branchement reellement pris (ligne du test -> ligne atteinte)."""
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["arcs"].get(fichier)


def instructions_sql(banc: Path) -> list[str] | None:
    """Instructions SQL reellement envoyees au moteur pendant la suite."""
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["instructions"]


def sources_sql(banc: Path) -> list[str] | None:
    """Points d observation qui ont VU passer du SQL : `sqlalchemy`, `sqlite3`, ou aucun.

    Une liste vide n est pas un silence de plus : elle dit que le projet n a AUCUNE couche SQL
    observable, ce que le rapport doit énoncer au lieu d afficher « exercé = 0 ».
    """
    mesure = mesurer(str(banc))
    return None if mesure is None else mesure["sources_sql"]


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
    _contrat_projet(banc)
    python = _python(banc)
    if python is None:
        return None
    with tempfile.TemporaryDirectory() as temporaire:
        sortie = Path(temporaire) / "openapi.json"
        resultat = _run(
            [str(python), str(SONDES / "dump_openapi.py"), str(sortie)],
            banc=banc, domaine="backend", quoi="extraction du schéma OpenAPI",
            cwd=banc / "backend",
            timeout=180,
            env={**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if resultat is None or resultat.returncode != 0 or not sortie.exists():
            return None
        donnees = json.loads(sortie.read_text(encoding="utf-8"))
    return None if "erreur" in donnees else donnees


def _env_front(banc: Path) -> dict[str, str]:
    """Environnement de la suite e2e — vise l instance SERVIE quand elle est déclarée.

    Décision du 2026-08-04 : chez un client on ne sait pas construire le projet, mais on sait
    l atteindre. Les configurations Playwright lisent `BASE_URL` ; Forge Tests n exportait que
    `FORGE_TESTS_BASE_URL`, si bien que la suite retombait sur son `http://localhost:5173` par
    défaut — 27 minutes contre un serveur de développement local, en mode bouchon.
    """
    from forge_tests.authentification import charger_env

    charger_env(banc)
    env = {**os.environ, "CI": "1"}
    base = (os.environ.get("FORGE_TESTS_BASE_URL") or "").strip()
    if base:
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        env["BASE_URL"] = base.rstrip("/")
    return env


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
        _declarer(
            banc,
            "front",
            f"dépendances front non installées — {front / 'node_modules'} absent",
        )
        return None
    npx = shutil.which("npx")
    if npx is None:
        _declarer(banc, "front", "npx introuvable sur cette machine — suite e2e non lançable")
        return None

    testids: set[str] = set()
    routes: set[str] = set()
    motif = re.compile(r'data-testid="([^"]+)"')
    # G-1 (lecture seule) : `--output` route traces et captures HORS de l arbre analysé. Sans
    # lui, `--trace on` déposait 34 Mo dans `frontend/test-results/` du projet du client.
    with tempfile.TemporaryDirectory(prefix="forge-tests-front-") as artefacts:
        resultat = _run(
            [
                npx, "playwright", "test", "--trace", "on", "--reporter=line",
                "--output", artefacts,
            ],
            banc=banc, domaine="front", quoi="suite e2e Playwright",
            cwd=front, timeout=900, env=_env_front(banc),
        )
        if resultat is None:
            return None
        if resultat.returncode != 0:
            from forge_tests.qualification import detecter

            manquants = detecter(
                banc, "front", f"{resultat.stdout or ''}\n{resultat.stderr or ''}"
            )
            complement = (
                f" — configuration absente citée par la trace : {', '.join(sorted(manquants))}"
                if manquants
                else ""
            )
            _declarer(
                banc,
                "front",
                f"la suite e2e s est terminée en échec (code {resultat.returncode}) — "
                f"couverture front non mesurable tant que la suite est rouge{complement}",
            )
            return None
        for archive in Path(artefacts).rglob("trace.zip"):
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
        resultat = _run(
            [
                str(python), str(SONDES / "verifier_schema.py"),
                str(banc / "backend"), str(sortie),
            ],
            banc=banc, domaine="backend", quoi="rejeu des migrations sur base neuve",
            cwd=banc / "backend", timeout=900,
            env={**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if resultat is None or resultat.returncode != 0 or not sortie.exists():
            return None
        donnees = json.loads(sortie.read_text(encoding="utf-8"))
    return None if "erreur" in donnees else donnees
