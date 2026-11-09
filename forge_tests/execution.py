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
import time
from functools import lru_cache
from pathlib import Path

from forge_tests import disposition
from forge_tests.disposition import (
    OMISSIONS_RACINE_PLATE,
    motif_indetermine,
    motif_racine_execution,
    nom_paquet_sources,
    racine_execution,
    racine_plate,
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

# TF-0299 — MARQUEUR d un préalable d ENVIRONNEMENT manquant, porté par le motif lui-même. Il est
# ce que les lecteurs en aval (la recette, qui prononce S-01) reconnaissent : un préalable absent
# n est pas une régression, et confondre les deux a coûté cinq minutes de diagnostic en pleine
# campagne le 17/08 — dix défauts du corpus sortis en [MANQUE], indiscernables d une régression.
# Le mot est dans le motif plutôt que dans une structure à part pour que le RAPPORT le porte aussi :
# un état déclaré au seul appelant serait invisible au lecteur du rapport.
PREALABLE_ABSENT = "PRÉALABLE D ENVIRONNEMENT ABSENT"

# Démon de conteneurs injoignable — les formes RÉELLES du message, relevées sur ce poste et sur
# les deux systèmes. `docker-py` (via testcontainers) échoue à la construction du client, AVANT le
# premier test : la suite n a donc jamais tourné. Motifs volontairement SPÉCIFIQUES : « docker »
# seul apparaîtrait dans le nom d un test ou dans une assertion de suite légitimement rouge, et
# reclasser une suite rouge en préalable manquant serait le défaut symétrique — celui qui absout.
_CONTENEUR_INJOIGNABLE = re.compile(
    r"docker\.errors\.DockerException"
    r"|DockerException:"
    r"|Error while fetching server API version"
    r"|Cannot connect to the Docker daemon"
    r"|Is the docker daemon running"
    r"|Could not get Docker client"
    r"|failed to start container",
    re.IGNORECASE,
)


def prealable_conteneur(trace: str) -> str | None:
    """La ligne de `trace` qui PROUVE le démon de conteneurs injoignable, ou None.

    Rendre la ligne plutôt qu un booléen : le motif publié cite la preuve. « le conteneur manque »
    sans la trace serait un diagnostic à croire sur parole, et le lecteur ne saurait pas si le
    démon est arrêté, mal configuré ou hors de portée de ce compte.
    """
    for ligne in (trace or "").splitlines():
        if _CONTENEUR_INJOIGNABLE.search(ligne):
            return " ".join(ligne.split())[:200]
    return None


def _declarer(banc: Path | str, domaine: str, motif: str) -> None:
    _MOTIFS[(str(banc), domaine)] = motif


def motif_indisponibilite(banc: Path | str, domaine: str, defaut: str) -> str:
    """Motif EXPLICITE de la non-mesure, ou le motif générique de l appelant à défaut."""
    return _MOTIFS.get((str(banc), domaine), defaut)


# TF-2269 (Produit-86, RP-42) — une suite ROUGE n est pas une mesure absente. Une suite à 1 test
# rouge sur 616 rendait les pans api, data et migrations en SKIP « couverture non mesurable » et
# le même verdict PARTIEL qu un jeu vert : le rapport ne nommait pas le test rouge, il fallait le
# chercher pan par pan. La mesure retient désormais CE QUI est rouge, et les pans qui lisent la
# suite le rendent en FAIL nommé (`sortie_suite_rouge`).
_SUITES_ROUGES: dict[str, dict] = {}
_LIGNE_ROUGE = re.compile(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$", re.MULTILINE)
#: Code de sortie de pytest quand AUCUN test n est collecté : une suite vide n est pas rouge.
CODE_AUCUN_TEST = 5
#: Au-delà, les constats se plafonnent ; le total se dit (aucune borne d affichage silencieuse).
PLAFOND_TESTS_ROUGES = 50

# TF-2311 — un DÉLAI dépassé n est ni une suite rouge ni une mesure impossible. Sous couverture, la
# suite backend d un produit dépassait 900 s quand le poste jouait aussi la préproduction : api,
# data et migrations rendaient SKIP à 2 jeux sur 3, indiscernables d une configuration absente,
# alors qu avec `FORGE_TESTS_DELAI_BACKEND_S=1800` les trois jeux passaient (173/173, 140/140,
# 12/12). `_run` retient ce qu il a interrompu ; la mesure en garde la suite backend ; les pans
# qui la lisent la rendent en DELAI_DEPASSE (`sortie_delai_depasse`).
_DEPASSEMENTS: dict[tuple[str, str], dict] = {}
_DELAIS_DEPASSES: dict[str, dict] = {}
QUOI_SUITE_BACKEND = "suite backend sous coverage"

# TF-2286 — pendant front de TF-2269 : une suite Playwright ROUGE rendait le pan front en SKIP
# « couverture non mesurable », indiscernable d'une suite qu'on n'a pas pu lancer. Le relevé
# est celui du backend, pour la suite e2e : les tests rouges viennent du JUnit de Playwright
# (`_ESSAIS`), à défaut de la trace de la ligne de commande.
_SUITES_ROUGES_FRONT: dict[str, dict] = {}
#: Playwright rend le code 1 quand il ne trouve AUCUN test : une suite vide n est pas rouge
#: (même règle que le code 5 de pytest), elle reste une mesure absente.
_AUCUN_TEST_PLAYWRIGHT = re.compile(r"No tests found", re.IGNORECASE)
#: « 1) [chromium] › e2e/a.spec.ts:3:5 › titre ─────── » : un échec nommé par la ligne de commande.
_LIGNE_ROUGE_PLAYWRIGHT = re.compile(r"^\s+\d+\) (.+?)(?:\s+[─—-]{2,})?\s*$", re.MULTILINE)


# TF-2254 — les ESSAIS de la suite du produit, test par test. Le JUnit de pytest (suite backend) et
# celui de Playwright (suite e2e) sont lus par `junit.depuis_junit` ; `essais_de_la_cible` les rend
# au rapport, où un essai non exécuté pèse sur le verdict PARTIEL. Un fichier JUnit absent ou
# illisible ne fabrique aucun essai : il se déclare (motif `essais-<domaine>`).
_ESSAIS: dict[tuple[str, str], list] = {}


def _relever_essais(banc: Path, domaine: str, pan: str, fichier: Path) -> None:
    from forge_tests.junit import JunitIllisible, depuis_junit

    _ESSAIS.pop((str(banc), domaine), None)
    if not fichier.is_file():
        return
    try:
        _ESSAIS[(str(banc), domaine)] = depuis_junit(
            fichier.read_text(encoding="utf-8", errors="replace"), pan
        )
    except JunitIllisible as erreur:
        _declarer(banc, f"essais-{domaine}", str(erreur))


def essais_de_la_cible(banc: Path | str) -> list | None:
    """Les essais des suites que l audit a lancées (backend puis front), ou None si aucune ne l a
    été. Ne lance rien : lit ce que les pans ont déjà mesuré."""
    suites = [_ESSAIS[cle] for cle in ((str(banc), "backend"), (str(banc), "front"))
              if cle in _ESSAIS]
    return [essai for suite in suites for essai in suite] if suites else None


def _relever_suite_rouge(code: int, trace: str, complement: str) -> dict:
    tests = [
        {"id": trouve.group(2), "nature": trouve.group(1),
         "message": (trouve.group(3) or "").strip()[:200]}
        for trouve in _LIGNE_ROUGE.finditer(trace)
    ]
    return {"code": code, "tests": tests, "complement": complement}


def _relever_front_rouge(banc: Path, code: int, trace: str, complement: str) -> dict:
    """Les tests rouges de la suite e2e : ceux du JUnit (`non_passant`), sinon ceux que la
    ligne de commande numérote. Aucun nom n est fabriqué : sans l un ni l autre, `tests` est vide.
    """
    tests = [
        {"id": essai.id, "nature": "FAILED", "message": (essai.pourquoi or "").strip()[:200]}
        for essai in _ESSAIS.get((str(banc), "front"), [])
        if essai.verdict == "non_passant"
    ]
    if not tests:
        noms = dict.fromkeys(
            trouve.group(1).strip() for trouve in _LIGNE_ROUGE_PLAYWRIGHT.finditer(trace)
        )
        tests = [{"id": nom, "nature": "FAILED", "message": ""} for nom in noms]
    return {"code": code, "tests": tests, "complement": complement}


def suite_rouge_front(banc: Path | str) -> dict | None:
    """Ce que la suite e2e Playwright a rendu de rouge — même forme que `suite_rouge` — ou None
    si elle n est pas rouge (verte, jamais lancée, port occupé, trace indisponible, aucun test)."""
    front_execute(str(banc))  # la mesure est jouée une fois, mémorisée ; elle alimente le relevé
    return _SUITES_ROUGES_FRONT.get(str(banc))


def suite_rouge(banc: Path | str) -> dict | None:
    """Ce que la suite backend a rendu de rouge — `{"code", "tests": [{"id", "nature",
    "message"}], "complement"}` — ou None si elle n est pas rouge (verte, jamais lancée, démon
    de conteneurs injoignable, aucun test collecté, délai dépassé)."""
    mesurer(str(banc))  # la mesure est jouée une fois, mémorisée ; elle alimente le relevé
    return _SUITES_ROUGES.get(str(banc))


def delai_depasse(banc: Path | str) -> dict | None:
    """`{"delai", "duree"}` (secondes) si la suite backend a été interrompue faute de temps, ou None
    (verte, rouge, jamais lancée, démon injoignable : autre chose qu un délai)."""
    mesurer(str(banc))  # la mesure est jouée une fois, mémorisée ; elle alimente le relevé
    return _DELAIS_DEPASSES.get(str(banc))


def sortie_delai_depasse(nom: str, pan: str, cible: Path, non_juge: list[str]):
    """La sortie DELAI_DEPASSE d un pan dont la suite backend a manqué de temps, ou None (TF-2311).

    Ni SKIP (la suite a démarré : la mesure n était pas impossible), ni FAIL (aucun test n a
    échoué, aucun n est nommé). Le pan n est pas mesuré et pèse sur PARTIEL ; son motif donne le
    délai, la durée atteinte, le réglage et une valeur à essayer. Cette valeur est le DOUBLE du
    délai atteint : la durée réelle de la suite est inconnue, elle est seulement supérieure.
    """
    depasse = delai_depasse(cible)
    if depasse is None:
        return None
    from forge_tests.noyau import DELAI_DEPASSE, SortieAdaptateur

    delai, duree = int(depasse["delai"]), float(depasse["duree"])
    motif = (
        f"{DELAI_DEPASSE} : suite interrompue à {duree:.0f} s (délai {delai} s) — régler "
        f"{ENV_DELAI_BACKEND} (secondes) dans `<projet>/.env.forge-tests`, par exemple "
        f"{ENV_DELAI_BACKEND}={2 * delai} (le double du délai atteint ; la durée réelle de la "
        f"suite backend est inconnue, supérieure à {duree:.0f} s). Ce n est ni une suite rouge "
        f"(aucun test n a échoué) ni une mesure impossible (la suite a démarré) : le pan {pan} "
        "n est pas mesuré, les autres le restent"
    )
    return SortieAdaptateur(nom, pan, str(cible), DELAI_DEPASSE, non_juge=[*non_juge, motif])


def sortie_suite_rouge(
    nom: str, pan: str, cible: Path, non_juge: list[str], domaine: str = "backend"
):
    """La sortie FAIL d un pan dont la suite est rouge, ou None si elle ne l est pas.

    `domaine` : "backend" (pytest, défaut) ou "front" (Playwright, TF-2286).

    Un finding bloquant par test rouge (`suite-rouge:<test>`), le test nommé dans le message ;
    une suite qui échoue sans nommer de test (erreur avant collecte) rend un seul finding
    `suite-rouge:suite-entiere`, sans nom fabriqué. Le motif de non-mesure de la couverture
    reste au non-jugé : le FAIL ne remplace pas ce motif, il le complète.
    """
    front = domaine == "front"
    rouge = suite_rouge_front(cible) if front else suite_rouge(cible)
    if rouge is None:
        return None
    from forge_tests import classes
    from forge_tests.noyau import Finding, SortieAdaptateur
    from forge_tests.risque import coter

    racine = disposition.racine_front(Path(cible)) if front else racine_execution(Path(cible))
    libelle = "e2e (Playwright)" if front else "backend"
    complement = rouge["complement"]
    findings = []
    nommes = rouge["tests"][:PLAFOND_TESTS_ROUGES]
    for test in nommes:
        identifiant = f"suite-rouge:{test['id']}"
        fichier = test["id"].partition("::")[0]
        detail = f" — {test['message']}" if test["message"] else ""
        findings.append(Finding(
            id=identifiant,
            classe=classes.SUITE_ROUGE,
            localisation=str(racine / fichier),
            message=(
                f"[{pan}] la suite {libelle} du projet est ROUGE : {test['nature']} "
                f"{test['id']}{detail}. Ce n est pas une mesure absente : un test du projet "
                f"échoue, et la couverture ne se mesure pas tant qu il échoue{complement}"
            ),
            severite="bloquant",
            risque=coter(pan, identifiant, str(racine / fichier)),
        ))
    if not rouge["tests"]:
        identifiant = "suite-rouge:suite-entiere"
        findings.append(Finding(
            id=identifiant,
            classe=classes.SUITE_ROUGE,
            localisation=str(racine),
            message=(
                f"[{pan}] la suite {libelle} du projet s est terminée en échec (code "
                f"{rouge['code']}) sans qu aucun test ne soit nommé (erreur avant ou pendant la "
                f"collecte) : lire la trace de la suite{complement}"
            ),
            severite="bloquant",
            risque=coter(pan, identifiant, str(racine)),
        ))
    lignes = [
        *non_juge,
        f"{pan} : couverture non mesurable tant que la suite est rouge — "
        + motif_indisponibilite(cible, domaine, f"suite {libelle} en échec"),
    ]
    if len(rouge["tests"]) > len(nommes):
        lignes.append(
            f"{pan} : {len(rouge['tests'])} tests rouges au total, {len(nommes)} nommés "
            f"(plafond {PLAFOND_TESTS_ROUGES}) — les autres sont dans la trace de la suite"
        )
    return SortieAdaptateur(nom, pan, str(cible), "FAIL", findings=findings, non_juge=lignes)


def _run(
    commande: list[str], *, banc: Path | str, domaine: str, quoi: str, remede: str = "", **kwargs
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
    debut = time.monotonic()
    try:
        return subprocess.run(commande, **kwargs)  # noqa: S603 — commande construite ici
    except subprocess.TimeoutExpired:
        # TF-1675 — la durée ATTEINTE est écrite à côté du délai, et le réglage qui le lève est
        # nommé quand il existe (`remede`) : « 900 s dépassé » seul ne disait ni de combien la
        # suite manquait, ni où se règle le délai.
        duree = time.monotonic() - debut
        _DEPASSEMENTS[(str(banc), quoi)] = {"delai": kwargs.get("timeout"), "duree": duree}  # 2311
        _declarer(
            banc,
            domaine,
            f"{quoi} : délai de {kwargs.get('timeout')} s dépassé (interrompu après "
            f"{duree:.0f} s) — pan non mesuré, les autres pans restent "
            "mesurés" + (f" ; {remede}" if remede else ""),
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


#: TF-2173 — l'interpréteur que le produit ou l'opérateur DÉSIGNE (`--python`, ou cette clé dans
#: `.env.forge-tests` / `forge/etapes/tests/audit.env`). Un outil autonome n'a souvent aucun
#: `.venv` : sans désignation, l'audit ne pouvait pas lancer sa suite (Produit-86, RP-13).
ENV_PYTHON = "FORGE_TESTS_PYTHON"


def python_designe(banc: Path) -> tuple[Path | None, str | None]:
    """(interpréteur désigné, motif quand la désignation est inutilisable) — TF-2173.

    Rien désigné : (None, None), la découverte des `.venv` s'applique. Désigné et trouvé :
    (chemin, None). Désigné et introuvable : (None, motif) — la désignation n'est JAMAIS remplacée
    en silence par un autre interpréteur, ce serait mesurer le produit avec un environnement que
    personne n'a choisi. Un nom nu (`python`) est cherché dans le PATH ; un chemin relatif se lit
    depuis la racine auditée.
    """
    brut = (os.environ.get(ENV_PYTHON) or "").strip()
    if not brut:
        return None, None
    chemin = Path(brut)
    if not chemin.is_absolute():
        trouve = shutil.which(brut) if len(chemin.parts) == 1 else None
        chemin = Path(trouve) if trouve else Path(banc) / chemin
    if chemin.is_file():
        return chemin, None
    return None, (
        f"{ENV_PYTHON}={brut!r} ne désigne aucun fichier ({chemin}) — l'interpréteur désigné "
        "n'est pas remplacé par un autre : corriger `--python` ou cette clé"
    )


def _python(banc: Path) -> Path | None:
    designe, motif = python_designe(banc)
    if designe is not None:
        return designe
    if motif:
        return None
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


#: Délai par défaut de la suite backend sous coverage, en secondes.
DELAI_BACKEND_DEFAUT = 900
ENV_DELAI_BACKEND = "FORGE_TESTS_DELAI_BACKEND_S"


def delai_backend() -> tuple[int, str]:
    """(délai retenu en secondes, phrase qui dit d où il vient et comment le lever) — TF-1675.

    Le délai de 900 s était fixé dans le code. Le 12/10/2026 chez Produit-80, sur un backend
    identique, l audit 14 a mesuré api, data et migrations ; l audit 15 et sa reprise les ont
    perdus avec deux autres pans, « délai de 900 s dépassé », la suite seule prenant 398 s sur le
    poste. Le projet n avait aucun moyen de régler ce délai. Il le règle désormais par
    `FORGE_TESTS_DELAI_BACKEND_S`, lu après le contrat du projet (`.env.forge-tests`). Une
    valeur illisible n est pas devinée : le défaut s applique, et le motif le dit.
    """
    brut = (os.environ.get("FORGE_TESTS_DELAI_BACKEND_S") or "").strip()
    conseil = (
        "regler FORGE_TESTS_DELAI_BACKEND_S (secondes) dans `<projet>/.env.forge-tests` "
        "pour lever ce delai"
    )
    if not brut:
        return DELAI_BACKEND_DEFAUT, f"delai par defaut de la forge — {conseil}"
    try:
        valeur = int(brut)
    except ValueError:
        valeur = 0
    if valeur <= 0:
        return (
            DELAI_BACKEND_DEFAUT,
            f"FORGE_TESTS_DELAI_BACKEND_S={brut!r} illisible (entier positif attendu), "
            f"defaut de {DELAI_BACKEND_DEFAUT} s retenu — {conseil}",
        )
    return valeur, f"delai regle par le projet (FORGE_TESTS_DELAI_BACKEND_S={valeur})"


@lru_cache(maxsize=32)
def mesurer(banc_str: str) -> dict | None:
    """Lance la suite UNE fois, sous coverage et sous sonde. None si la mesure est impossible.

    None n est pas « rien à signaler » : l appelant doit DÉCLARER qu il ne juge pas.
    """
    banc = Path(banc_str)
    _SUITES_ROUGES.pop(str(banc), None)
    _DELAIS_DEPASSES.pop(str(banc), None)
    _DEPASSEMENTS.pop((str(banc), QUOI_SUITE_BACKEND), None)
    _ESSAIS.pop((str(banc), "backend"), None)
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
        _designe, motif_designation = python_designe(banc)
        essayes = ", ".join(str(v) for v in _venvs_essayes(banc))
        # TF-2222 : un back .NET n'a pas de `.venv`. Le motif nomme la pile reconnue à ses
        # manifestes (`*.csproj`) au lieu d'envoyer chercher un environnement Python absent.
        pile_dotnet = disposition.motif_pile_non_python(banc)
        _declarer(
            banc,
            "backend",
            motif_designation
            or pile_dotnet
            or (
                f"aucun environnement Python dans le projet analysé — cherché sous {essayes} ; "
                f"{motif_racine_execution(banc)} ; pour un outil sans `.venv`, désigner "
                f"l'interpréteur par `--python` ou {ENV_PYTHON}"
            ),
        )
        return None
    if not _coverage_present(banc, python):
        return None
    # Le paquet du produit est DECOUVERT, pas suppose : `--source=app` sur un projet dont le
    # paquet s appelle autrement rend une couverture vide, et l absence de mesure passait alors
    # pour une suite qui n exerce rien. Voir `forge_tests.disposition`.
    paquet = nom_paquet_sources(banc)
    # TF-2173 — un outil à modules plats n'a pas de paquet : la source mesurée est la racine
    # d'exécution elle-même, sans l'environnement ni les artefacts (`OMISSIONS_RACINE_PLATE`).
    plate = racine_plate(banc) if paquet is None else None
    if paquet is None and plate is None:
        _declarer(
            banc, "backend", f"sources du projet non localisables — {motif_indetermine(banc)}"
        )
        return None
    if plate is not None:
        sources_coverage = ["--source=.", "--omit=" + ",".join(OMISSIONS_RACINE_PLATE)]
    else:
        sources_coverage = [f"--source={paquet},tests"]
    # TF-0216 : la suite se lance depuis la racine DÉCOUVERTE, pas depuis `<cible>/backend`
    # supposé. Sur un produit à racine plate, ce `cwd` en dur pointait un dossier inexistant et
    # emportait sept pans d un coup — alors que la suite y est verte.
    racine = racine_execution(banc)
    delai, remede = delai_backend()
    with tempfile.TemporaryDirectory() as temporaire:
        releve = Path(temporaire) / "sonde.json"
        releve_data = Path(temporaire) / "sonde-data.json"
        junit = Path(temporaire) / "junit.xml"  # TF-2254 : hors du projet (G-1), lu ci-dessous
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
                str(python), "-m", "coverage", "run", "--branch", *sources_coverage,
                "-m", "pytest", "-q", "--no-header",
                "-p", "no:cacheprovider", "-p", "no:warnings",
                "-p", "sonde_api", "-p", "sonde_data",
                f"--junitxml={junit}",
            ],
            banc=banc, domaine="backend", quoi=QUOI_SUITE_BACKEND,
            remede=remede, cwd=racine, timeout=delai, env=env,
        )
        if lance is None:
            depasse = _DEPASSEMENTS.get((str(banc), QUOI_SUITE_BACKEND))
            if depasse is not None:  # TF-2311 : la suite a démarré et manqué de temps
                _DELAIS_DEPASSES[str(banc)] = depasse
            return None
        _relever_essais(banc, "backend", "back", junit)  # TF-2254 : verte ou rouge, elle a tourné
        if lance.returncode != 0:
            trace = f"{lance.stdout or ''}\n{lance.stderr or ''}"
            # TF-0299 — PRIORITÉ ABSOLUE sur la branche « suite rouge » ci-dessous, même raison
            # que le port occupé du pan front (TF-0136) : quand le démon de conteneurs est
            # injoignable, la suite n a JAMAIS tourné — testcontainers échoue à construire son
            # client avant le premier test. « suite rouge » est alors un diagnostic faux, et il
            # envoie chercher une régression dans un dépôt sain (constaté le 17/08 : Docker
            # Desktop arrêté, 10 défauts du corpus en [MANQUE], 5 minutes de diagnostic).
            preuve = prealable_conteneur(trace)
            if preuve is not None:
                _declarer(
                    banc,
                    "backend",
                    f"{PREALABLE_ABSENT} — demon de conteneurs INJOIGNABLE : la suite backend du "
                    "projet monte sa base par conteneur (testcontainers) et n a donc JAMAIS ete "
                    "executee. Ce n est ni une suite rouge, ni une regression du framework : "
                    "aucune mesure n a eu lieu. Demarrer le demon (Docker Desktop), verifier "
                    f"`docker ps`, puis rejouer. Preuve lue dans la trace : {preuve}",
                )
                return None
            # RT-6a — une suite rouge FAUTE DE CONFIGURATION le dit dans sa propre trace. La
            # lire ici est le seul endroit du framework où le projet audité nomme lui-même les
            # identifiants qui lui manquent : sans cela, « suite rouge » couvre indistinctement
            # un bug du projet et une clé tierce jamais saisie par l opérateur.
            from forge_tests.qualification import detecter

            manquants = detecter(banc, "backend", trace)
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
            if lance.returncode != CODE_AUCUN_TEST:
                _SUITES_ROUGES[str(banc)] = _relever_suite_rouge(
                    lance.returncode, trace, complement
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
    # TF-1794 : la suite a tourné. Un fichier absent de sa mesure est un fichier qu elle n a
    # jamais exécuté (ensemble vide), pas une suite rouge (None) — confondre les deux faisait
    # dire « suite rouge ou environnement absent » sur une suite verte.
    return mesure["lignes"].get(fichier) or frozenset()


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


def _provenance_trace(banc: Path, front: Path) -> str:
    """D OU vient le mode de trace retenu, dit au motif — TF-1673.

    Le 12/10/2026, Produit-80 réglait `FORGE_TESTS_PLAYWRIGHT_TRACE=on` dans son
    `.env.forge-tests` ; le pan front lisait la variable AVANT que ce fichier soit chargé, et
    concluait « trace désactivée par le projet » sur une suite verte. Le motif attribuait au
    `playwright.config` un choix qu il ne savait pas situer : il nomme désormais la source.
    """
    from forge_tests.authentification import ENV_PROJET, _valeurs

    declare = (os.environ.get("FORGE_TESTS_PLAYWRIGHT_TRACE") or "").strip()
    if declare:
        if _valeurs(banc / ENV_PROJET).get("FORGE_TESTS_PLAYWRIGHT_TRACE") == declare:
            return f"FORGE_TESTS_PLAYWRIGHT_TRACE={declare} lu dans `{ENV_PROJET}` du projet"
        return f"FORGE_TESTS_PLAYWRIGHT_TRACE={declare} pose dans l environnement de l operateur"
    choisi = _mode_trace_projet(front)
    if choisi:
        return f"son propre playwright.config choisit trace={choisi!r}"
    return "defaut `on` de la forge"


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
    # TF-1673 — le contrat du projet est chargé AVANT toute lecture de réglage : le mode de
    # trace se lisait ici alors que `.env.forge-tests` n était chargé que par `_env_front`,
    # plus bas — un réglage du projet ignoré en silence dès que ce pan tournait le premier.
    _contrat_projet(banc)
    # TF-0401 : la racine front suit la cascade — manifeste du projet > convention `frontend`.
    front = disposition.racine_front(banc)
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
    commande += ["--reporter=line,junit"]  # TF-2254 : le JUnit alimente les essais du rapport
    # G-1 (lecture seule) : `--output` route traces et captures HORS de l arbre analysé. Sans
    # lui, `--trace on` déposait 34 Mo dans `frontend/test-results/` du projet du client.
    with tempfile.TemporaryDirectory(prefix="forge-tests-front-") as artefacts:
        commande += ["--output", artefacts]
        junit = Path(artefacts) / "junit.xml"
        _ESSAIS.pop((str(banc), "front"), None)
        _SUITES_ROUGES_FRONT.pop(str(banc), None)
        resultat = _run(
            commande,
            banc=banc, domaine="front", quoi="suite e2e Playwright",
            cwd=front, timeout=900,
            env={**_env_front(banc), "PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(junit)},
        )
        if resultat is None:
            return None
        _relever_essais(banc, "front", "front", junit)  # TF-2254
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

            trace = f"{resultat.stdout or ''}\n{resultat.stderr or ''}"
            manquants = detecter(banc, "front", trace)
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
            if not _AUCUN_TEST_PLAYWRIGHT.search(trace):
                _SUITES_ROUGES_FRONT[str(banc)] = _relever_front_rouge(
                    banc, resultat.returncode, trace, complement
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
                f"trace Playwright en mode {mode_effectif!r} "
                f"({_provenance_trace(banc, front)}) — couverture front NON MESURABLE, la suite "
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
            # TF-0309 — domaine PROPRE à ce chemin plutôt que « backend » : un délai dépassé sur
            # le rejeu des migrations se publiait sous le motif que lisent `api` et `batch`, et
            # un préalable déclaré ici écraserait celui de la suite backend — reclasser une suite
            # VRAIMENT rouge en poste mal équipé est le défaut symétrique, celui qui absout.
            banc=banc, domaine="schema", quoi="rejeu des migrations sur base neuve",
            cwd=racine_execution(banc), timeout=900,  # TF-0216 — racine DÉCOUVERTE
            env={**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if resultat is None:
            return None  # `_run` a déjà déclaré (délai, lancement impossible)
        if resultat.returncode != 0 or not sortie.exists():
            # TF-0309 — ce chemin rendait None SANS MOTIF : les deux pans qui le consultent
            # publiaient « schema reel non introspectable » sans dire pourquoi. Or la sonde monte
            # sa base par conteneur (testcontainers) : sur un projet dont la suite backend n en
            # utilise pas, le démon absent frappe ICI et NULLE PART AILLEURS — muet. Même idiome
            # que TF-0299 : le marqueur est DANS le motif, et la preuve voyage avec lui.
            trace = f"{resultat.stdout or ''}\n{resultat.stderr or ''}"
            preuve = prealable_conteneur(trace)
            if preuve is not None:
                _declarer(
                    banc,
                    "schema",
                    f"{PREALABLE_ABSENT} — demon de conteneurs INJOIGNABLE : le rejeu des "
                    "migrations sur base neuve monte sa base par conteneur (testcontainers) et "
                    "n a donc JAMAIS eu lieu. Ce n est ni un schema divergent, ni une regression "
                    "du framework : aucune mesure n a eu lieu. Demarrer le demon (Docker "
                    "Desktop), verifier `docker ps`, puis rejouer. Preuve lue dans la trace : "
                    f"{preuve}",
                )
            else:
                # Second sens : un rejeu qui échoue POUR SA PROPRE raison (migration invalide,
                # dépendance absente) garde un motif qui l accuse, lui. Le préalable ne doit pas
                # devenir l explication de tout.
                derniere = next(
                    (ligne.strip() for ligne in reversed(trace.splitlines()) if ligne.strip()),
                    "aucune sortie",
                )
                _declarer(
                    banc,
                    "schema",
                    "le rejeu des migrations sur base neuve a echoue (code "
                    f"{resultat.returncode}) — schema reel non introspectable. Derniere ligne de "
                    f"la trace : {derniere[:200]}",
                )
            return None
        donnees = json.loads(sortie.read_text(encoding="utf-8"))
    return None if "erreur" in donnees else donnees
