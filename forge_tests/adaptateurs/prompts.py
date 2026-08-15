"""Adaptateur Prompts — inventaire STATIQUE des prompts, des modèles et du corpus (TF-0200).

Verdict O2 de l'étude d'opportunité du 14/08/2026 (`20260814-etude-opportunite-pans-tests-
prompts.md`) : un pan `prompts` dans forge-tests, **v0 bornée à ce qui se mesure sans appeler
un modèle**, le coûteux et le sémantique délégués aux briques existantes.

Trois objets, tous dérivés SANS EXÉCUTION et sans la moindre dépense :

  - **les prompts** — fichiers de prompt adressables (`*.prompt`, tout ce qui vit sous
    `prompts/` ou `gabarits/`, les `SKILL.md`) et constantes de prompt système repérables dans
    le code Python. Élément `prompt:<chemin>` ;
  - **les modèles** nommés par le projet. Élément `modele:<nom>`. Un nom qui est un ALIAS
    mouvant (`*-latest`, `gpt-4o`) plutôt qu'une version épinglée (`nom-AAAAMMJJ`) est un
    finding `modele-non-epingle` : *un alias change le système sous test sans qu'aucun commit
    ne bouge* ;
  - **le corpus de questions / réponses attendues** (`evals/`, `*.eval.jsonl`, `cas.json` au
    format de `oracle-agent-evals`). Il ne dit pas si un prompt est BON — il dit s'il est
    EXERCÉ. Un prompt qu'aucun cas ne cite est `non_exerce` ; un corpus DÉCLARÉ mais
    introuvable rend son prompt `non_testable`, avec ses `champs_requis`.

Le volet EXÉCUTÉ (rejeu N fois pour mesurer la stabilité, jugement sémantique) est **hors v0** :
il dépense des jetons, donc il relève d'un mandat humain (règle 29 — « dépenses et gates restent
humains »). `mesure_d_instabilite` ci-dessous en prépare la mesure et la teste sur données
figées ; elle n'appelle aucun modèle, n'ouvre aucun réseau, et l'audit ne l'invoque jamais.

Ce module LIT des fichiers ; il n'exécute rien et n'écrit rien (G-1).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from forge_tests import flaky
from forge_tests.noyau import (
    Element,
    Finding,
    NonTestable,
    SortieAdaptateur,
    evaluer_surface,
)
from forge_tests.risque import coter

NOM, PAN, SEUIL = "prompts-statique", "prompts", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "rendre les prompts ADRESSABLES (un fichier `*.prompt`, un dossier `prompts/`, un "
    "`SKILL.md`) et leur adjoindre un corpus de cas versionné (`evals/*.eval.jsonl` ou "
    "`cas.json` au format de `oracle-agent-evals`) ; le pan est statique, il n'exécute rien"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T8", "famille": "technique", "titre": "Prompts & modèles",
     "decoupe": "prompt", "axe_cas": "unitaire"},
)

# RT-13 : le seul champ qui debloque CE pan — la racine d un corpus de cas qui vit HORS du
# depot audite. Un compte ou une instance servie ne l auraient jamais rendu mesurable.
CHAMPS_REQUIS = ("FORGE_TESTS_PROMPTS_CORPUS",)

NON_JUGE = [
    "prompts : la v0 est STATIQUE et GRATUITE — le volet execute (rejeu N fois pour mesurer la "
    "stabilite d une reponse, jugement semantique par un juge) est HORS PERIMETRE : il depense "
    "des jetons, donc il releve d un mandat humain (regle 29). `mesure_d_instabilite` en porte "
    "la mesure, testee sur donnees figees et JAMAIS appelee par l audit",
    "prompts : la QUALITE d un prompt n est pas jugee ici — ce pan dit ou vivent les prompts, "
    "s ils sont exerces et si le modele est epingle, jamais si le prompt est bon (cela releve "
    "de `prompt-analyzer-l99` et de la revue humaine)",
    "prompts : la decouverte est bornee aux formes ADRESSABLES reconnues (suffixe `.prompt`, "
    "dossier `prompts/` ou `gabarits/`, `SKILL.md`, constante Python nommee `*PROMPT*` / "
    "`*INSTRUCTIONS*`) — un prompt assemble a l execution par concatenation, ou stocke en base, "
    "n est pas inventoriable statiquement et le deviner serait mentir",
    "prompts : l epinglage juge la FORME du nom (suffixe date `-AAAAMMJJ`, `-AAAA-MM-JJ` ou "
    "`-AAMM`), pas la disponibilite reelle du modele — aucun appel reseau n est fait et aucun "
    "calendrier de depreciation fournisseur n est consulte ici",
    "prompts : les noms de modeles sont reconnus par FAMILLE declaree et seulement dans une "
    "chaine litterale ou une cle `modele:`/`model:` — un fournisseur absent de la table, un nom "
    "construit par concatenation ou lu d une variable d environnement n est pas vu",
    "prompts : les artefacts de l AUDITEUR sont exclus de l inventaire de l AUDITE (TF-0257) — "
    "le dossier de convention `forge\\` du pilot (ledger, contestations, rapports d etape), les "
    "rapports forge-tests persistes (reconnus a leurs cles de premier niveau) et les livrables "
    "scelles par la forge. Un projet qui nommerait `forge\\` un dossier de SON produit le "
    "verrait donc ignore ici : la convention du pilot prime, et elle est declaree",
    "prompts : le corpus est LU, jamais joue — qu un cas soit pertinent, que sa reponse "
    "attendue soit juste, et que le jeu couvre les cas limites, restent des jugements humains "
    "(l execution du corpus est deleguee a `oracle-agent-evals`, cat-agt-05)",
]

# Dossiers hors périmètre : dépendances et artefacts (mêmes exclusions que les pans `interface`
# et `declencheurs` — RT-9/RT-10 du lot bourse-aux-vacants, convention `output\`/`old\` du pilot).
#
# TF-0257, étage 1 — `forge\` est le dossier de convention du PILOT : le run y dépose le ledger,
# les contestations, les rapports d étape, les dossiers de MEP. Ce sont les artefacts de
# l ORCHESTRATEUR, pas du produit audité. Les fouiller a un effet mesuré : sur un produit
# strictement sans LLM, quatre « modèles » fantômes ont été inventoriés — l alias de
# l orchestrateur lui-même, cité dans son ledger — et il a fallu cinq contestations pour les
# faire taire. `.forge` (le point) était exclu, `forge` ne l était pas : la convention réelle du
# pilot est celle SANS point (`CLAUDE.md` : « artefacts sous `forge\` »).
_EXCLUS = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages", "dist", "build",
    ".next", ".nuxt", ".svelte-kit", ".visuel", "htmlcov", "coverage", ".tox", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", "vendor", ".forge", "forge", "output", "old", "Old",
    ".oracles",
}

# Un fichier au-delà de ce volume n est pas un prompt ni une configuration : c est un artefact.
# Le plafond borne le coût du pan sur un dépôt réel, et il est déclaré plutôt que silencieux.
_PLAFOND_OCTETS = 512 * 1024

# --- Ce qui fait qu un fichier est un PROMPT ---------------------------------------------------
_SUFFIXE_PROMPT = ".prompt"
_DOUBLE_SUFFIXE_PROMPT = (".prompt.md", ".prompt.txt")
_DOSSIERS_PROMPT = ("prompts", "gabarits")
_EXTENSIONS_EN_DOSSIER = (".prompt", ".md", ".txt", ".tmpl")
_NOMS_PROMPT = ("SKILL.md",)

# Constante Python qui PORTE un prompt système : le nom le dit, et la valeur est un littéral.
_NOM_CONSTANTE = re.compile(r"^[A-Z][A-Z0-9_]*(?:PROMPT|INSTRUCTIONS|SYSTEME|SYSTEM)[A-Z0-9_]*$")
_LONGUEUR_MINIMALE = 40

# --- Ce qui fait qu une chaîne est un NOM DE MODÈLE --------------------------------------------
# Familles déclarées, donc contestables. Un fournisseur absent d ici n est pas vu (non_juge).
_FAMILLES = (
    "claude", "gpt", "o1", "o3", "o4", "gemini", "mistral", "mixtral", "llama", "deepseek",
    "grok", "qwen", "command-r", "sonar", "phi",
)
_MODELE = re.compile(
    r"^(?:[\w.]+/)?(?:" + "|".join(_FAMILLES) + r")-[a-z0-9][a-z0-9._-]*$", re.IGNORECASE
)
# Formes d ÉPINGLAGE reconnues : instantané daté du fournisseur.
_EPINGLE = re.compile(
    r"(?:-|@|:)(?:20\d{2}(?:0[1-9]|1[0-2])(?:[0-2]\d|3[01])"
    r"|20\d{2}-(?:0[1-9]|1[0-2])-(?:[0-2]\d|3[01])"
    r"|2\d(?:0[1-9]|1[0-2]))$"
)
_CHAINE = re.compile(r"[\"'`]([^\"'`\n]{3,120})[\"'`]")
_CLE_MODELE = re.compile(
    r"(?im)^[\s\-#*>]*(?:mod[eè]les?|models?)\s*[:=]\s*[\"'`]?([^\"'`\n,}\]]+)"
)

# --- Corpus de questions / réponses attendues --------------------------------------------------
_DOSSIERS_CORPUS = ("evals", "eval", "evaluations")
_SUFFIXES_CORPUS = (".eval.jsonl", ".eval.json")
_NOMS_CORPUS = ("cas.json", "cas.jsonl")
_EXTENSIONS_CORPUS = (".json", ".jsonl", ".yaml", ".yml")
_DECLARE_CORPUS = re.compile(
    r"(?im)^[\s\-#*>]*(?:corpus|eval_set|jeu_de_cas)\s*[:=]\s*[\"'`]?([^\"'`\n]+?)[\"'`]?\s*$"
)
_CHAMPS_PROMPT = ("prompt", "prompt_ref", "fichier", "skill")
_CHAMPS_MODELE = ("modele", "model", "modele_juge")

_EXTENSIONS_LUES = (
    ".prompt", ".md", ".txt", ".tmpl", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".sh", ".ps1",
)
# Fichiers de verrouillage de dépendances : ils citent des milliers de noms de paquets et
# aucun modèle. Les lire produirait du bruit, jamais un fait.
_NOMS_IGNORES = ("package-lock.json", "uv.lock", "poetry.lock", "yarn.lock", "pnpm-lock.yaml")

# --- TF-0257, étage 2 — le LARSEN de l auditeur ------------------------------------------------
# ETAPES-RUN EXIGE que le rapport d audit soit persisté dans le projet
# (`forge\etapes\tests\rapport-forge-tests.json`). Ce rapport contient les MESSAGES du pan
# prompts, qui citent nommément `claude-opus-4-1-20250805` et `gemini-flash-latest` pour
# expliquer ce qu est un alias mouvant. Au run suivant, le pan relisait donc son propre rapport
# et inventoriait ces noms comme des modèles DU PRODUIT : sur un produit strictement sans LLM,
# quatre alias fantômes et cinq contestations nécessaires — et l audit ne convergeait jamais,
# puisque chaque run recréait la matière du suivant.
#
# La reconnaissance se fait sur la SIGNATURE, pas sur le nom : un projet reste libre de nommer
# ses fichiers comme il l entend, et un rapport renommé reste un rapport. Deux signatures :
#
#   - un rapport forge-tests — objet JSON portant ses clés de premier niveau ;
#   - un livrable SCELLÉ par la forge (cahiers, dashboard) — son bloc de sceau en tête.
_CLES_RAPPORT = ("adaptateurs", "couverture_par_pan", "pans_non_couverts", "verdict")
# Littéral de `forge_tests.livrables.nommage.DEBUT_SCEAU`, recopié pour ne pas importer le
# paquet `livrables` depuis un adaptateur (`livrables/__init__` importe le REGISTRE des
# adaptateurs : l import serait circulaire). L égalité des deux est TESTÉE.
_DEBUT_SCEAU = "<!-- SCEAU FORGE-TESTS"


def est_un_artefact_d_auditeur(texte: str) -> bool:
    """Ce fichier est-il un artefact produit par FORGE-TESTS elle-même ?

    Un audit qui inventorie ses propres livrables mesure l auditeur, pas l audité — et il ne
    converge pas : chaque run fabrique la matière que le suivant conteste (TF-0257).
    """
    debut = texte.lstrip()
    if debut.startswith(_DEBUT_SCEAU):
        return True
    if not debut.startswith("{"):
        return False
    # Test bon marché AVANT l analyse : un JSON de projet n a aucune raison de porter ce mot.
    if '"couverture_par_pan"' not in texte:
        return False
    try:
        charge = json.loads(texte)
    except (json.JSONDecodeError, RecursionError):
        return False
    return isinstance(charge, dict) and all(cle in charge for cle in _CLES_RAPPORT)


# --- Parcours ---------------------------------------------------------------------------------
def _fichiers(cible: Path) -> list[Path]:
    """Fichiers TEXTE du projet, artefacts de construction et dépendances exclus."""
    retenus: list[Path] = []
    for chemin in sorted(cible.rglob("*")):
        if any(partie in _EXCLUS for partie in chemin.parts):
            continue
        if not chemin.is_file() or chemin.name in _NOMS_IGNORES:
            continue
        if chemin.suffix.lower() not in _EXTENSIONS_LUES:
            continue
        try:
            if chemin.stat().st_size > _PLAFOND_OCTETS:
                continue
        except OSError:
            continue
        retenus.append(chemin)
    return retenus


def _relatif(chemin: Path, cible: Path) -> str:
    try:
        return chemin.relative_to(cible).as_posix()
    except ValueError:
        return chemin.as_posix()


def _texte(chemin: Path) -> str:
    try:
        return chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def est_un_prompt(chemin: Path) -> bool:
    """Le fichier est-il un prompt ADRESSABLE ? Trois formes reconnues, aucune devinée."""
    nom = chemin.name
    if chemin.suffix.lower() == _SUFFIXE_PROMPT or nom.lower().endswith(_DOUBLE_SUFFIXE_PROMPT):
        return True
    if nom in _NOMS_PROMPT:
        return True
    dossiers = {partie.lower() for partie in chemin.parent.parts}
    return bool(dossiers & set(_DOSSIERS_PROMPT)) and chemin.suffix.lower() in (
        _EXTENSIONS_EN_DOSSIER
    )


def est_un_corpus(chemin: Path) -> bool:
    """Le fichier porte-t-il des cas (question / réponse attendue) ?"""
    nom = chemin.name.lower()
    if nom.endswith(_SUFFIXES_CORPUS) or nom in _NOMS_CORPUS:
        return True
    dossiers = {partie.lower() for partie in chemin.parent.parts}
    return bool(dossiers & set(_DOSSIERS_CORPUS)) and chemin.suffix.lower() in _EXTENSIONS_CORPUS


def est_epingle(nom: str) -> bool:
    """Le nom désigne-t-il une version FIGÉE, ou un alias qui bouge sous nos pieds ?"""
    return bool(_EPINGLE.search(nom.strip()))


def modeles_cites(texte: str) -> list[str]:
    """Noms de modèles cités par ce texte — littéral de chaîne ou clé `modele:` uniquement.

    Chercher le motif dans la prose donnerait un inventaire de mentions, pas d usages : un
    document qui PARLE d un modèle ne le fait pas tourner.
    """
    trouves: list[str] = []
    candidats = [*_CHAINE.findall(texte), *_CLE_MODELE.findall(texte)]
    for brut in candidats:
        valeur = brut.strip().strip("\"'`").strip()
        if _MODELE.match(valeur) and valeur not in trouves:
            trouves.append(valeur)
    return trouves


def _constantes_de_prompt(chemin: Path, texte: str) -> list[tuple[str, str]]:
    """(nom, valeur) des constantes Python qui portent un prompt système, lues par AST."""
    try:
        arbre = ast.parse(texte, filename=str(chemin))
    except SyntaxError:
        return []
    trouves: list[tuple[str, str]] = []
    for noeud in ast.walk(arbre):
        cibles: list[ast.expr] = []
        valeur: ast.expr | None = None
        if isinstance(noeud, ast.Assign):
            cibles, valeur = list(noeud.targets), noeud.value
        elif isinstance(noeud, ast.AnnAssign) and noeud.value is not None:
            cibles, valeur = [noeud.target], noeud.value
        if not isinstance(valeur, ast.Constant) or not isinstance(valeur.value, str):
            continue
        if len(valeur.value) < _LONGUEUR_MINIMALE:
            continue
        for element in cibles:
            if isinstance(element, ast.Name) and _NOM_CONSTANTE.match(element.id):
                trouves.append((element.id, valeur.value))
    return trouves


# --- Collecte ----------------------------------------------------------------------------------
def _collecte(cible: Path) -> dict:
    """Tout ce que le pan sait lire du projet, en UNE passe : prompts, modèles, cas.

    Retour : `{"prompts": {id: (chemin, source)}, "modeles": {nom: source},
    "cas": [dict], "corpus_absents": [(id_prompt, source, chemin_declare)]}`.
    """
    prompts: dict[str, tuple[Path, str]] = {}
    modeles: dict[str, str] = {}
    cas: list[dict] = []
    corpus_absents: list[tuple[str, str, str]] = []

    for chemin in _fichiers(cible):
        texte = _texte(chemin)
        if not texte:
            continue
        # TF-0257 : ce que la forge a elle-même écrit ne fait pas partie de la surface de
        # l audité — sans quoi l audit se mesure lui-même et ne converge jamais.
        if est_un_artefact_d_auditeur(texte):
            continue
        relatif = _relatif(chemin, cible)

        if est_un_prompt(chemin):
            prompts[f"prompt:{relatif}"] = (chemin, str(chemin))
            declare = _DECLARE_CORPUS.search(texte)
            if declare:
                brut = declare.group(1).strip()
                if not _resoudre(cible, chemin, brut):
                    corpus_absents.append((f"prompt:{relatif}", str(chemin), brut))
        elif chemin.suffix.lower() == ".py":
            for nom, _valeur in _constantes_de_prompt(chemin, texte):
                prompts[f"prompt:{relatif}:{nom}"] = (chemin, str(chemin))

        if est_un_corpus(chemin):
            cas.extend(_cas(texte))

        for nom in modeles_cites(texte):
            modeles.setdefault(nom, str(chemin))

    return {
        "prompts": prompts,
        "modeles": modeles,
        "cas": cas,
        "corpus_absents": corpus_absents,
    }


def _resoudre(cible: Path, prompt: Path, declare: str) -> Path | None:
    """Le corpus DÉCLARÉ par un prompt existe-t-il, à la racine du projet ou à côté du prompt ?"""
    brut = declare.strip().strip("\"'`").replace("\\", "/")
    if not brut:
        return None
    for candidat in (cible / brut, prompt.parent / brut):
        try:
            if candidat.exists():
                return candidat
        except OSError:
            continue
    return None


def _cas(texte: str) -> list[dict]:
    """Cas portés par un fichier de corpus — JSONL ligne à ligne, ou JSON (liste ou objet)."""
    trouves: list[dict] = []
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("{"):
            continue
        try:
            charge = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if isinstance(charge, dict):
            trouves.append(charge)
    if trouves:
        return trouves
    try:
        charge = json.loads(texte)
    except json.JSONDecodeError:
        return []
    if isinstance(charge, list):
        return [c for c in charge if isinstance(c, dict)]
    if isinstance(charge, dict):
        for clef in ("cas", "tests", "evals", "questions"):
            valeur = charge.get(clef)
            if isinstance(valeur, list):
                return [c for c in valeur if isinstance(c, dict)]
    return []


def _designe(reference: str, identifiant: str) -> bool:
    """Un cas qui cite `reference` désigne-t-il l élément `prompt:<chemin>` ?"""
    reference = (reference or "").strip().replace("\\", "/").lower()
    if not reference:
        return False
    chemin = identifiant[len("prompt:") :].lower()
    if reference in (chemin, Path(chemin).name, Path(chemin).stem):
        return True
    return chemin.endswith("/" + reference)


# --- Contrat d adaptateur ----------------------------------------------------------------------
def inventaire(cible: Path) -> list[Element]:
    """Prompts adressables et modèles nommés. Les prompts NON TESTABLES ici en sont exclus.

    Un prompt dont le corpus déclaré est introuvable n est pas « jamais exercé » : personne ne
    POUVAIT l exercer ici (RT-6). Le laisser dans la surface l accuserait à tort d un trou de
    couverture ; il sort en `non_testable`, avec ses `champs_requis`.
    """
    collecte = _collecte(cible)
    hors_portee = {identifiant for identifiant, _, _ in collecte["corpus_absents"]}
    elements = [
        Element(identifiant, PAN, f"prompt adressable {identifiant[len('prompt:'):]}", source)
        for identifiant, (_chemin, source) in sorted(collecte["prompts"].items())
        if identifiant not in hors_portee
    ]
    elements.extend(
        Element(
            f"modele:{nom}",
            PAN,
            f"modèle « {nom} » ({'épinglé' if est_epingle(nom) else 'alias mouvant'})",
            source,
        )
        for nom, source in sorted(collecte["modeles"].items())
    )
    return elements


def exerces(cible: Path) -> set[str]:
    """Éléments cités par AU MOINS UN cas du corpus. Aucun appel de modèle n est fait.

    « Exercé » veut dire ici « un cas versionné le désigne », pas « une réponse a été obtenue » :
    obtenir la réponse coûte des jetons et relève du volet mandaté (règle 29).
    """
    collecte = _collecte(cible)
    hors_portee = {identifiant for identifiant, _, _ in collecte["corpus_absents"]}
    couverts: set[str] = set()
    for cas in collecte["cas"]:
        for champ in _CHAMPS_PROMPT:
            reference = cas.get(champ)
            if not isinstance(reference, str):
                continue
            for identifiant in collecte["prompts"]:
                if identifiant not in hors_portee and _designe(reference, identifiant):
                    couverts.add(identifiant)
        for champ in _CHAMPS_MODELE:
            nom = cas.get(champ)
            if isinstance(nom, str) and f"modele:{nom.strip()}" in {
                f"modele:{m}" for m in collecte["modeles"]
            }:
                couverts.add(f"modele:{nom.strip()}")
    return couverts


def _findings_modeles(cible: Path) -> list[Finding]:
    """Modèles désignés par un ALIAS — un défaut de reproductibilité, pas un trou de test."""
    collecte = _collecte(cible)
    findings: list[Finding] = []
    for nom, source in sorted(collecte["modeles"].items()):
        if est_epingle(nom):
            continue
        identifiant = f"modele:{nom}"
        findings.append(
            Finding(
                id=identifiant,
                classe="modele-non-epingle",
                localisation=source,
                message=(
                    f"modèle « {nom} » désigné par un ALIAS mouvant, jamais par une version "
                    "épinglée (forme `nom-AAAAMMJJ`) — un alias change le système sous test "
                    "sans qu'aucun commit ne bouge : `claude-opus-4-1-20250805` a été retiré "
                    "le 2026-08-05, et Google remappe ses alias `-latest` à dates fixes "
                    "(`gemini-flash-latest` -> `gemini-3.5-flash` le 2026-05-19)"
                ),
                risque=coter(PAN, identifiant, source),
            )
        )
    return findings


def _non_testables(cible: Path) -> list[NonTestable]:
    """Prompts dont le corpus DÉCLARÉ est introuvable — un manque de configuration, pas un trou."""
    return [
        NonTestable(
            element=identifiant,
            champs_requis=list(CHAMPS_REQUIS),
            pan=PAN,
            motif=(
                f"prompts : le corpus déclaré « {declare} » est introuvable — fournir le jeu de "
                f"cas (ou {CHAMPS_REQUIS[0]} vers sa racine), puis `--reprendre` le rapport"
            ),
        )
        for identifiant, _source, declare in sorted(_collecte(cible)["corpus_absents"])
    ]


def analyser(cible: Path) -> SortieAdaptateur:
    non_testables = _non_testables(cible)
    elements = inventaire(cible)
    findings_modeles = _findings_modeles(cible)
    if not elements:
        # Un modèle nommé EST un élément : un inventaire vide implique qu aucun modèle n a été
        # trouvé, donc aucun constat d épinglage à porter. Écrire ici une branche « FAIL si
        # findings » serait du code mort qui rassure.
        return SortieAdaptateur(
            NOM,
            PAN,
            str(cible),
            "SKIP",
            non_juge=[
                *NON_JUGE,
                "prompts : aucun prompt adressable ni modèle nommé trouvé — surface non "
                "énumérable sur ce projet",
            ],
            non_testables=non_testables,
        )
    sortie = evaluer_surface(NOM, PAN, str(cible), elements, exerces(cible), SEUIL, NON_JUGE)
    sortie.non_testables.extend(non_testables)
    if findings_modeles:
        sortie.findings = [*findings_modeles, *sortie.findings]
        sortie.verdict = "FAIL"
    return sortie


# --- TF-0201 — volet stabilité : PRÉPARÉ, jamais exécuté ---------------------------------------
def mesure_d_instabilite(reponses: list[dict], repetitions: int | None = None) -> dict:
    """Instabilité d un jeu de réponses DÉJÀ OBTENUES — aucun appel modèle, aucun réseau.

    TF-0201, volet préparé et NON branché à l audit : obtenir les réponses coûte des jetons,
    c est-à-dire une dépense, c est-à-dire un mandat humain (règle 29). Cette fonction ne les
    obtient pas — elle prend ce qu un rejeu mandaté a produit ailleurs et le MESURE, en
    réutilisant littéralement la logique de `forge_tests.flaky` : à entrée identique, un
    verdict (ou une valeur) qui varie d un rejeu à l autre est une instabilité.

    Entrée — une liste de réponses, chacune portant :

        {"cas": "<identifiant du cas>", "rejeu": <entier>, "verdict": "<passant|…>",
         "reponse": "<texte rendu>"}

    `verdict` prime quand il est fourni (c est le jugement) ; sinon la RÉPONSE elle-même sert de
    valeur observée, normalisée sur les espaces — deux textes identiques au blanc près sont la
    même réponse, et prétendre le contraire ferait crier à l instabilité sur du formatage.

    Sortie — même forme que `flaky.rejouer`, plus le taux de stabilité :

        {"repetitions", "cas_instables": {cas: [valeurs...]}, "tous_ids", "stabilite"}

    `cas_instables` est vide si rien n a varié — jamais l absence de la clé, pour que l appelant
    n ait pas à distinguer « non mesuré » de « rien trouvé ». Un rejeu où le cas n apparaît pas
    vaut `absent` : une réponse manquante EST une variation, la taire serait un vert offert.
    """
    rejeux: dict[object, dict[str, str]] = {}
    for entree in reponses:
        cas = str(entree.get("cas") or entree.get("id") or "")
        if not cas:
            continue
        rang = entree.get("rejeu", entree.get("repetition", len(rejeux)))
        verdict = entree.get("verdict")
        if verdict is None:
            verdict = " ".join(str(entree.get("reponse") or "").split())
        rejeux.setdefault(rang, {})[cas] = str(verdict)

    releves = [rejeux[rang] for rang in sorted(rejeux, key=str)]
    total = repetitions if repetitions is not None else len(releves)
    if total < 2:
        raise ValueError(
            "la mesure d instabilite exige au moins 2 rejeux du meme cas : une reponse unique "
            "ne prouve rien sur la stabilite"
        )
    instables = flaky.variations(releves)
    tous_ids = sorted({cas for releve in releves for cas in releve})
    return {
        "repetitions": total,
        "cas_instables": instables,
        "tous_ids": tous_ids,
        "stabilite": round(1 - len(instables) / len(tous_ids), 4) if tous_ids else 1.0,
    }
