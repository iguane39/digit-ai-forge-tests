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
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from forge_tests.disposition import (
    motif_indetermine,
    motif_racine_execution,
    nom_paquet_sources,
    racine_execution,
)

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


def _venvs_essayes(banc: Path) -> list[Path]:
    """Environnements Python cherchés, dans l ordre — la racine DÉCOUVERTE en tête (TF-0216)."""
    racines: list[Path] = []
    for racine in (racine_execution(banc), banc / "backend", banc):
        if racine not in racines:
            racines.append(racine)
    return [racine / ".venv" for racine in racines]


def _python(banc: Path) -> Path | None:
    for venv in _venvs_essayes(banc):
        for candidat in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
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
    # TF-0216 — la racine d exécution retenue est DÉCLARÉE avant toute mesure : elle est lisible
    # par `motif_indisponibilite(banc, "racine-execution", …)` quoi qu il advienne ensuite, et
    # elle est reprise dans les motifs d échec ci-dessous. Une découverte muette qui changerait
    # d un projet à l autre serait pire que l ancre en dur qu elle remplace.
    _declarer(banc, "racine-execution", motif_racine_execution(banc))
    python = _python(banc)
    if python is None:
        essayes = ", ".join(str(v) for v in _venvs_essayes(banc))
        _declarer(
            banc,
            "backend",
            f"aucun environnement Python dans le projet analysé — cherché sous {essayes} ; "
            f"{motif_racine_execution(banc)}",
        )
        return None
    if not _coverage_present(banc, python):
        return None
    # Le paquet du produit est DECOUVERT, pas suppose : `--source=app` sur un projet dont le
    # paquet s appelle autrement rend une couverture vide, et l absence de mesure passait alors
    # pour une suite qui n exerce rien. Voir `forge_tests.disposition`.
    paquet = nom_paquet_sources(banc)
    if paquet is None:
        _declarer(banc, "backend", f"sources du projet non localisables — {motif_indetermine(banc)}")
        return None
    # TF-0216 : la suite se lance depuis la racine DÉCOUVERTE, pas depuis `<cible>/backend`
    # supposé. Sur un produit à racine plate, ce `cwd` en dur pointait un dossier inexistant et
    # emportait sept pans d un coup — alors que la suite y est verte.
    racine = racine_execution(banc)
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
                str(python), "-m", "coverage", "run", "--branch", f"--source={paquet},tests",
                "-m", "pytest", "-q", "--no-header",
                "-p", "no:cacheprovider", "-p", "no:warnings",
                "-p", "sonde_api", "-p", "sonde_data",
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
    """Lignes et branches couvertes PAR FICHIER (chemin relatif à la racine d exécution).

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
            cwd=racine_execution(banc),  # TF-0216 — racine DÉCOUVERTE, pas `backend` supposé
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


_TRACE_CONFIG = re.compile(r"trace\s*:\s*[\"']([\w-]+)[\"']")

# TF-0136 — message EXACT emis par le runner Playwright (`webServer.reuseExistingServer:
# false`) quand un AUTRE processus ecoute deja sur l URL configuree : verifie en reel sur ce
# poste, ou un serveur de preview d un projet totalement etranger occupait le port 4173 du banc
# rouge, faisant passer la suite pour rouge sur une page qui n avait meme pas les data-testid
# attendus. Ce motif est produit AVANT le premier test (le serveur ne demarre pas) : il doit
# etre reconnu avant toute lecture de trace.zip, sans quoi l absence de trace (aucun test
# execute) se confond avec « ecriture de trace bloquee » (TF-0132) ou pire, avec une suite
# reellement rouge.
_PORT_OCCUPE = re.compile(r"(\S+) is already used, make sure that nothing is running on the port")


def _mode_trace_projet(front: Path) -> str | None:
    """Le mode de trace DEJA choisi par le projet dans son `playwright.config`, s il y en a un.

    Une recherche textuelle : parser un vrai config TypeScript demanderait un interprete JS que
    la forge n a pas. Elle suffit a reconnaitre la forme usuelle `trace: "retain-on-failure"`.
    """
    for suffixe in (".ts", ".js", ".mjs", ".cts", ".mts"):
        config = front / f"playwright.config{suffixe}"
        if config.is_file():
            trouve = _TRACE_CONFIG.search(config.read_text(encoding="utf-8", errors="replace"))
            if trouve:
                return trouve.group(1)
    return None


def _mode_trace(front: Path) -> tuple[str | None, str]:
    """(argument CLI a passer ou None, mode EFFECTIF qui va s appliquer) — TF-0132.

    `--trace on` etait impose en dur : un projet qui avait deja regle `trace` dans son
    `playwright.config.ts` (par exemple `retain-on-failure`, precisement pour contourner un
    blocage d ecriture) voyait son choix ECRASE. Ordre retenu : la variable d environnement
    (dernier mot de l operateur, y compris pour DESACTIVER la trace sur un poste ou son
    ecriture bloque), puis le choix DEJA fait par le projet (l ecraser jetterait son
    intention — rien n est alors passe en CLI, la config du projet gouverne seule), puis le
    defaut de CETTE forge (`on`) qui permet de mesurer la couverture front par defaut.
    """
    declare = (os.environ.get("FORGE_TESTS_PLAYWRIGHT_TRACE") or "").strip()
    if declare:
        return declare, declare
    choisi = _mode_trace_projet(front)
    if choisi:
        return None, choisi
    return "on", "on"


@lru_cache(maxsize=16)
def front_execute(banc_str: str) -> dict | None:
    """Routes visitees et elements reellement manipules pendant la suite front.

    Lance la suite Playwright du projet avec la TRACE activee, puis lit la trace : chaque action
    y porte son selecteur et chaque navigation son URL. Aucune modification du projet analyse —
    l instrumentation est un drapeau de ligne de commande.
    """
    import collections
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
    # TF-0098 : sans config Playwright, `npx playwright test` ramasse les *.test.tsx de vitest
    # et plante sur « Vitest failed to access its internal state » — un echec d execution
    # imputable au projet, alors que le vrai fait est « aucune suite e2e declaree ». Les deux
    # motifs n appellent pas le meme travail : le premier envoie chercher un bug inexistant.
    if not any(
        (front / f"playwright.config{suffixe}").is_file()
        for suffixe in (".ts", ".js", ".mjs", ".cts", ".mts")
    ):
        _declarer(
            banc,
            "front",
            "aucune suite e2e declaree — aucun playwright.config.{ts,js,mjs} sous "
            f"{front} : lancer `npx playwright test` sans config ramasserait la suite "
            "unitaire (vitest) du projet et ferait passer son absence pour un echec",
        )
        return None
    npx = shutil.which("npx")
    if npx is None:
        _declarer(banc, "front", "npx introuvable sur cette machine — suite e2e non lançable")
        return None

    testids: set[str] = set()
    routes: set[str] = set()
    motif = re.compile(r'data-testid="([^"]+)"')
    argument_cli, mode_effectif = _mode_trace(front)
    commande = [npx, "playwright", "test"]
    if argument_cli:
        commande += ["--trace", argument_cli]
    commande += ["--reporter=line"]
    # G-1 (lecture seule) : `--output` route traces et captures HORS de l arbre analysé. Sans
    # lui, `--trace on` déposait 34 Mo dans `frontend/test-results/` du projet du client.
    with tempfile.TemporaryDirectory(prefix="forge-tests-front-") as artefacts:
        commande += ["--output", artefacts]
        resultat = _run(
            commande,
            banc=banc, domaine="front", quoi="suite e2e Playwright",
            cwd=front, timeout=900, env=_env_front(banc),
        )
        if resultat is None:
            return None
        if resultat.returncode != 0:
            # TF-0136 — un port DEJA occupe par un processus etranger au banc fait echouer le
            # demarrage du webServer avant le premier test : aucune trace n est produite (aucun
            # test n a tourne), ce qui SANS ce garde tombait dans la branche « trace
            # indisponible » ci-dessous (diagnostic faux : la trace n est pour rien) ou dans la
            # suite generique « suite e2e en echec » (diagnostic faux : la suite n a jamais ete
            # executee). Priorite absolue sur les deux autres causes.
            occupe = _PORT_OCCUPE.search(f"{resultat.stdout or ''}\n{resultat.stderr or ''}")
            if occupe:
                _declarer(
                    banc,
                    "front",
                    f"port deja occupe par un AUTRE processus sur {occupe.group(1)} — le "
                    "webServer de ce banc n a pas demarre, AUCUN test n a ete execute : ni une "
                    "trace indisponible, ni une suite rouge. Identifier l occupant "
                    "(`netstat -ano | findstr <port>` puis le PID dans le Gestionnaire des "
                    "taches sous Windows) et liberer le port avant de relancer",
                )
                return None
            # TF-0132 — deux causes DISTINCTES derriere un code de sortie non nul. Sur un poste
            # ou l ECRITURE de la trace bloque, chaque test se deroule en entier puis expire en
            # « Test timeout exceeded » : la suite est repute rouge alors qu elle est verte de
            # bout en bout (mesure : 10/10 en 7,2 s avec la trace desactivee, 100 % de timeouts
            # avec elle). Le mode « on » ecrit TOUJOURS un trace.zip, succes ou echec — son
            # absence apres un mode « on » designe donc la trace, jamais la suite.
            aucune_trace = mode_effectif == "on" and not any(
                Path(artefacts).rglob("trace.zip")
            )
            if aucune_trace:
                _declarer(
                    banc,
                    "front",
                    f"trace Playwright indisponible (code {resultat.returncode}, aucun "
                    "trace.zip produit malgre --trace on) — couverture front NON MESURABLE "
                    "sans trace, la suite elle-meme n est pas mise en cause. Definir "
                    "FORGE_TESTS_PLAYWRIGHT_TRACE=off pour desactiver la trace si son "
                    "ecriture bloque sur ce poste (mesure de couverture front alors perdue)",
                )
                return None
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
        # TF-0138 — meme distinction que ci-dessus, cote SUCCES. Un projet qui a fixe
        # `trace` dans SON PROPRE playwright.config (mode_effectif != "on", cf. `_mode_trace` —
        # raison legitime : ecriture de trace bloquee sur son poste, TF-0132) passe TOUS ses
        # tests sans qu aucun trace.zip soit jamais produit. Sans ce garde, la boucle suivante
        # trouvait zero archive et rapportait testids/routes VIDES — indiscernable d une suite
        # qui n exerce reellement rien : le seuil de surface tombait a 0 % BLOQUANT sur un
        # projet dont la suite est verte de bout en bout (constate sur fixtures/banc-vert,
        # dont le playwright.config porte `trace: "off"` : 26 bloquants a tort, 0 une fois la
        # mesure correctement declaree NON MESURABLE au lieu de NULLE).
        if mode_effectif != "on":
            _declarer(
                banc,
                "front",
                "trace Playwright desactivee par LE PROJET (son propre playwright.config "
                f"choisit trace={mode_effectif!r}) — couverture front NON MESURABLE, la suite "
                "elle meme est VERTE (code 0). Definir FORGE_TESTS_PLAYWRIGHT_TRACE=on pour "
                "forcer la mesure si l ecriture de trace n est pas bloquee sur ce poste",
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
                str(racine_execution(banc)), str(sortie),
            ],
            banc=banc, domaine="backend", quoi="rejeu des migrations sur base neuve",
            cwd=racine_execution(banc), timeout=900,  # TF-0216 — racine DÉCOUVERTE
            env={**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if resultat is None or resultat.returncode != 0 or not sortie.exists():
            return None
        donnees = json.loads(sortie.read_text(encoding="utf-8"))
    return None if "erreur" in donnees else donnees
