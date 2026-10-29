"""Adaptateur Workers — inventaire STATIQUE des gestionnaires d un Worker Cloudflare (TF-1998).

Étude du pilot du 28/10/2026, ligne C6 : aucune forge ne citait `wrangler`, Workers, R2 ni D1.
Un Worker audité tombait donc hors de tous les pans : ni FastAPI, ni React, ni migrations SQL.
La documentation lue le 29/10/2026 décrit deux outils de test, qui font le périmètre de ce pan :
« For most projects, use the Workers Vitest integration for unit tests and the
`createTestHarness()` API for integration tests » (page « Testing », mise à jour du 18/10/2026).

Deux objets, dérivés SANS EXÉCUTION et sans réseau :

  - **les gestionnaires** que déclarent la configuration Wrangler de la racine (`wrangler.json`,
    `wrangler.jsonc` ou `wrangler.toml`) et son module `main` : `fetch`, `scheduled` (aussi
    impliqué par `triggers.crons`), `queue` (aussi impliqué par `queues.consumers`), `email`,
    `tail`, chaque classe Durable Object et chaque Workflow définis DANS ce Worker (sans
    `script_name`). Élément `workers:<genre>:<nom>` ;
  - **les tests qui les dispatchent dans le runtime Workers** : un fichier de test d une suite
    Vitest configurée avec l intégration Workers (`cloudflareTest()` de `@cloudflare/vitest-plugin`,
    ou l ancien `@cloudflare/vitest-pool-workers`), ou un fichier qui ouvre `createTestHarness`.
    Motifs de dispatch tirés des pages « Test APIs » (10/10/2026) et « Interact with Workers »
    (27/07/2026) : `exports.default.fetch()`, `SELF.fetch()`, `server.fetch()`,
    `createScheduledController()`, `.scheduled()`, `createMessageBatch()`, `.queue()`,
    `runInDurableObject()`, `introspectWorkflow()`.

Un gestionnaire qu aucun test ne dispatche est `non exercé` — c est le cron qui plante en service
parce que seule la route HTTP était testée. Ce module LIT des fichiers ; il n exécute rien et
n écrit rien (G-1). La date de compatibilité testée contre la date servie relève du gate
`runtime-parity` de forge-development (TF-1998), pas de ce pan.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "workers-wrangler", "workers", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publié tel quel au rapport.
POUR_COUVRIR = (
    "faire tourner les tests dans le runtime Workers — `cloudflareTest({ wrangler: { configPath: "
    '"./wrangler.jsonc" } })` de `@cloudflare/vitest-plugin` dans `vitest.config.*`, ou un harnais '
    "`createTestHarness` de wrangler — et y dispatcher chaque gestionnaire que la configuration "
    "Wrangler déclare (fetch, scheduled, queue, classes Durable Object, Workflows)"
)

# Chapitre(s) de cahier de tests que ce pan alimente, DÉRIVÉS du registre par le cahier et le
# dashboard. L axe `gestionnaire` range par genre : les crons ensemble, les files ensemble.
CHAPITRES = (
    {"code": "T9", "famille": "technique", "titre": "Workers",
     "decoupe": "gestionnaire", "axe_cas": "unitaire"},
)

NON_JUGE = [
    "workers : statique — un gestionnaire est tenu pour exercé quand un fichier de test qui tourne "
    "dans le runtime Workers le DISPATCHE nommément (exports.default.fetch, server.fetch, "
    "createScheduledController, createMessageBatch, runInDurableObject, introspectWorkflow…) ; "
    "le dispatch cité n est ni exécuté ni prouvé vert par ce pan",
    "workers : seule la configuration Wrangler de la racine est lue ; dans un dépôt de plusieurs "
    "Workers, les autres ne sont pas inventoriés",
    "workers : les gestionnaires se lisent dans le module `main` par motif de définition de "
    "méthode ; un gestionnaire défini ailleurs puis réexporté échappe à l inventaire, sauf s il "
    "est impliqué par la configuration (crons, consommateurs de file)",
    "workers : les Pages Functions (dossier `functions/`) et la syntaxe Service Worker ne sont "
    "pas inventoriées",
    "workers : la parité entre la date de compatibilité testée et la date servie n est pas "
    "jugée ici — gate `runtime-parity` de forge-development (TF-1998)",
]

_CONFIGS = ("wrangler.json", "wrangler.jsonc", "wrangler.toml")
_VITEST = tuple(f"vitest.config.{ext}" for ext in ("ts", "mts", "cts", "js", "mjs", "cjs"))
_INTEGRATION = re.compile(r"@cloudflare/vitest-(?:plugin|pool-workers)")
_HARNAIS = re.compile(r"\bcreateTestHarness\s*\(")
_FICHIER_TEST = re.compile(r"\.(?:test|spec)\.[cm]?[jt]sx?$")
_EXCLUS = {"node_modules", ".wrangler", "dist", ".git", ".venv", "build"}
_GENRES = ("fetch", "scheduled", "queue", "email", "tail")
# Définition de méthode dans le module d entrée : `async fetch(request, env, ctx) {`, avec type
# de retour TypeScript facultatif. Un APPEL `await fetch(url)` ne commence pas la ligne, et
# `fetch(url).then(` n est pas suivi d une accolade : ni l un ni l autre ne passe.
_DEFINITION = re.compile(
    r"^[ \t]*(?:async[ \t]+)?(?P<genre>fetch|scheduled|queue|email|tail)[ \t]*\([^)]*\)"
    r"[ \t]*(?::[^{\n]*)?\{",
    re.MULTILINE,
)
_RECEVEUR = r"\b(?:exports\.default|SELF|server|worker|\w*Worker)\."
_DISPATCH = {
    "fetch": re.compile(_RECEVEUR + r"fetch\s*\("),
    "scheduled": re.compile(r"\bcreateScheduledController\s*\(|" + _RECEVEUR + r"scheduled\s*\("),
    "queue": re.compile(r"\bcreateMessageBatch\s*\(|" + _RECEVEUR + r"queue\s*\("),
    "email": re.compile(_RECEVEUR + r"email\s*\("),
    "tail": re.compile(_RECEVEUR + r"tail\s*\("),
}
_STUB_DO = re.compile(r"\brunInDurableObject\s*\(|\bidFrom(?:Name|String)\s*\(|\bgetByName\s*\(")


def _hors_chaines(texte: str, traiter: Callable[[str, int], tuple[str, int]]) -> str:
    """Parcourt `texte` ; les chaînes JSON passent telles quelles, le reste passe par `traiter`,
    qui reçoit (texte, position) et rend (morceau à garder, position suivante)."""
    sortie: list[str] = []
    i, n = 0, len(texte)
    while i < n:
        if texte[i] == '"':
            j = i + 1
            while j < n and texte[j] != '"':
                j += 2 if texte[j] == "\\" else 1
            sortie.append(texte[i : j + 1])
            i = j + 1
            continue
        morceau, i = traiter(texte, i)
        sortie.append(morceau)
    return "".join(sortie)


def _sans_commentaire(texte: str, i: int) -> tuple[str, int]:
    if texte.startswith("//", i):
        fin = texte.find("\n", i)
        return "", len(texte) if fin == -1 else fin
    if texte.startswith("/*", i):
        fin = texte.find("*/", i + 2)
        return "", len(texte) if fin == -1 else fin + 2
    return texte[i], i + 1


def _sans_virgule_finale(texte: str, i: int) -> tuple[str, int]:
    if texte[i] == "," and texte[i + 1 :].lstrip()[:1] in ("}", "]"):
        return "", i + 1
    return texte[i], i + 1


def _jsonc_vers_json(texte: str) -> str:
    """Commentaires puis virgules finales retirés HORS des chaînes (format de `wrangler.jsonc`) :
    deux passes, pour qu une virgule suivie d un commentaire puis d une accolade tombe aussi."""
    return _hors_chaines(_hors_chaines(texte, _sans_commentaire), _sans_virgule_finale)


def _config(cible: Path) -> tuple[Path, dict[str, Any]] | None:
    for nom in _CONFIGS:
        chemin = cible / nom
        if not chemin.is_file():
            continue
        texte = chemin.read_text(encoding="utf-8", errors="ignore")
        try:
            donnees: Any = (
                tomllib.loads(texte) if chemin.suffix == ".toml"
                else json.loads(_jsonc_vers_json(texte))
            )
        except (tomllib.TOMLDecodeError, json.JSONDecodeError):
            return chemin, {}
        return chemin, donnees if isinstance(donnees, dict) else {}
    return None


def _liste(section: Mapping[str, Any], *cles: str) -> list[Any]:
    valeur: Any = section
    for cle in cles:
        valeur = valeur.get(cle) if isinstance(valeur, Mapping) else None
    return valeur if isinstance(valeur, list) else []


def _classes(conf: Mapping[str, Any], cle_binding: str, *cles: str) -> list[tuple[str, str]]:
    """(classe, binding) des objets DÉFINIS dans ce Worker : sans `script_name`. Le nom du
    binding est `name` pour un Durable Object, `binding` pour un Workflow (où `name` nomme le
    Workflow lui-même)."""
    trouves: list[tuple[str, str]] = []
    for entree in _liste(conf, *cles):
        if isinstance(entree, Mapping) and entree.get("class_name") and not entree.get(
            "script_name"
        ):
            trouves.append((str(entree["class_name"]), str(entree.get(cle_binding, ""))))
    return trouves


def _inventaire_detaille(cible: Path) -> list[tuple[Element, str]]:
    """(élément, binding) — le binding sert à reconnaître le dispatch d une classe."""
    lue = _config(cible)
    if lue is None:
        return []
    chemin, conf = lue
    genres: dict[str, str] = {}
    principal = conf.get("main")
    if isinstance(principal, str) and (cible / principal).is_file():
        module = cible / principal
        for m in _DEFINITION.finditer(module.read_text(encoding="utf-8", errors="ignore")):
            genres.setdefault(m.group("genre"), str(module))
    if _liste(conf, "triggers", "crons"):
        genres.setdefault("scheduled", str(chemin))
    if _liste(conf, "queues", "consumers"):
        genres.setdefault("queue", str(chemin))
    nom_main = principal if isinstance(principal, str) else chemin.name
    elements = [
        (Element(f"workers:{g}:{nom_main}", PAN, f"gestionnaire `{g}` du Worker", genres[g]), "")
        for g in _GENRES
        if g in genres
    ]
    for classe, binding in _classes(conf, "name", "durable_objects", "bindings"):
        elements.append(
            (Element(f"workers:durable-object:{classe}", PAN, f"classe Durable Object `{classe}`",
                     str(chemin)), binding)
        )
    for classe, binding in _classes(conf, "binding", "workflows"):
        elements.append(
            (Element(f"workers:workflow:{classe}", PAN, f"Workflow `{classe}`", str(chemin)),
             binding)
        )
    return elements


def inventaire(cible: Path) -> list[Element]:
    return [e for e, _ in _inventaire_detaille(cible)]


def _tests_dans_le_runtime(cible: Path) -> list[str]:
    """Textes des fichiers de test qui tournent dans le runtime Workers."""
    vitest = next((cible / n for n in _VITEST if (cible / n).is_file()), None)
    suite_workers = vitest is not None and bool(
        _INTEGRATION.search(vitest.read_text(encoding="utf-8", errors="ignore"))
    )
    textes: list[str] = []
    for chemin in sorted(cible.rglob("*")):
        if _EXCLUS.intersection(chemin.relative_to(cible).parts):
            continue
        if not chemin.is_file() or not _FICHIER_TEST.search(chemin.name):
            continue
        texte = chemin.read_text(encoding="utf-8", errors="ignore")
        if suite_workers or _HARNAIS.search(texte):
            textes.append(texte)
    return textes


def exerces(cible: Path) -> set[str]:
    textes = _tests_dans_le_runtime(cible)
    couverts: set[str] = set()
    for element, binding in _inventaire_detaille(cible):
        genre = element.id.split(":")[1]
        if genre in _DISPATCH:
            if any(_DISPATCH[genre].search(t) for t in textes):
                couverts.add(element.id)
            continue
        if not binding:
            continue
        cite = re.compile(rf"\b{re.escape(binding)}\b")
        if genre == "workflow":
            motif = re.compile(
                rf"\bintrospectWorkflow(?:Instance)?\s*\(\s*(?:env\.{re.escape(binding)}\b"
                rf"|[\"'`]{re.escape(binding)}[\"'`])"
            )
            if any(motif.search(t) for t in textes):
                couverts.add(element.id)
        elif any(cite.search(t) and _STUB_DO.search(t) for t in textes):
            couverts.add(element.id)
    return couverts


def sans_objet(cible: Path) -> str | None:
    """PREUVE d absence : aucune configuration Wrangler à la racine, donc aucun Worker."""
    if any((cible / nom).is_file() for nom in _CONFIGS):
        return None
    return (
        "aucune configuration Wrangler (`wrangler.json`, `wrangler.jsonc`, `wrangler.toml`) à la "
        "racine : ce projet ne déploie aucun Worker"
    )


def analyser(cible: Path) -> SortieAdaptateur:
    motif = sans_objet(cible)
    if motif:
        return evaluer_surface(NOM, PAN, str(cible), [], set(), SEUIL, NON_JUGE, sans_objet=motif)
    non_juge = list(NON_JUGE)
    if not _tests_dans_le_runtime(cible):
        non_juge.append(
            "workers : aucun fichier de test ne tourne dans le runtime Workers (ni intégration "
            "Vitest des Workers, ni createTestHarness) — chaque gestionnaire sort non exercé"
        )
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, non_juge)
