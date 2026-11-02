"""Adaptateur Supabase — tables exposées, RLS et tests pgTAP sous un rôle de l API (TF-2008).

Étude du pilot du 28/10/2026, lignes S3, S5 et S6 : hors des cinq surfaces Supabase du 16/10,
aucune forge ne citait Supabase, et forge-tests ne lisait pas `supabase/migrations/` (ses pans
`data` et `migrations` attendent des sections `-- +migrate Up`). Les pages lues le 29/10/2026 :

  - « Row Level Security » : « A table in an exposed schema without RLS is readable and writable
    by any role with a grant on it. Enable RLS on every table in an exposed schema. » ;
  - « Testing Your Database » : tests SQL sous `supabase/tests/database/`, « All `sql` files use
    pgTAP as the test runner », joués par `supabase test db` ;
  - « Testing Overview » : une politique se teste sous le rôle qu elle vise, `set local role
    authenticated` puis `set local request.jwt.claim.sub = '…'` ; « Advanced pgTAP Testing » :
    `tests.authenticate_as()` fait la même chose ;
  - « Realtime Authorization » : la RLS de `realtime.messages` est déjà active, et une migration
    qui la réactive échoue en `42501 must be owner of table messages`, transaction comprise.

Trois objets, dérivés SANS EXÉCUTION :

  - **les tables des schémas exposés** que créent les migrations `supabase/migrations/*.sql`
    (schémas lus dans `[api] schemas` de `supabase/config.toml`, à défaut ceux du gabarit du CLI,
    `public` et `graphql_public`). Élément `supabase:table:<schéma>.<table>` ;
  - **les tests qui les exercent sous un rôle de l API** : un fichier pgTAP de `supabase/tests/`
    qui adopte un rôle (`set local role authenticated|anon`, `request.jwt.claim`,
    `tests.authenticate_as`) et cite la table. C est là que se teste un flux d authentification
    côté base : la politique vue par l utilisateur connecté, et par l anonyme. Depuis TF-2046, une
    table est aussi exercée quand un fichier sous un dossier `tests/` l APPELLE par l API
    (`/rest/v1/<table>` ou `from_("<table>")`, hors commentaires et docstrings), ou quand le
    produit la déclare dans `FORGE_TESTS_SUPABASE_TABLES_EXERCEES` ;
  - **deux constats** : `rls-absente` (table exposée dont la RLS n est pas active à l issue des
    migrations) et `realtime-rls-reactivee` (migration qui réactive la RLS de
    `realtime.messages`).

Ce module LIT des fichiers ; il n exécute rien et n écrit rien (G-1).
"""

from __future__ import annotations

import ast
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from forge_tests import classes
from forge_tests.authentification import ENV_PROJET, _valeurs
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "supabase-pgtap", "supabase", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publié tel quel au rapport.
POUR_COUVRIR = (
    "écrire sous `supabase/tests/` des tests pgTAP (`supabase test db`) qui citent chaque table "
    "d un schéma exposé en jouant un rôle de l API (`set local role authenticated` et "
    "`request.jwt.claim.sub`, ou `tests.authenticate_as()`), ou un test sous un dossier `tests/` "
    "qui appelle chaque table par l API (`/rest/v1/<table>`, `from_(\"<table>\")`), et activer la "
    "RLS de chaque table exposée dans une migration"
)

# Le chapitre T2 « Données » range déjà par table : les tables Supabase s y lisent à côté des
# autres, sous-chapitre par table (règle `table` de `livrables/surface.py`).
CHAPITRES = (
    {"code": "T2", "famille": "technique", "titre": "Données",
     "decoupe": "table", "axe_cas": "unitaire"},
)

NON_JUGE = [
    "supabase : statique — une table est tenue pour exercée quand un fichier pgTAP de "
    "`supabase/tests/` la cite après avoir adopté un rôle de l API, quand un fichier sous un "
    "dossier `tests/` l appelle par l API (`/rest/v1/<table>` ou `from_(\"<table>\")`) ou quand le "
    "produit la déclare (`FORGE_TESTS_SUPABASE_TABLES_EXERCEES`) ; le test n est ni exécuté ni "
    "prouvé vert par ce pan (`supabase test db` le juge), et une table déclarée n est pas vérifiée",
    "supabase : l appel par l API se lit par motif ; un nom de table construit (concaténation, "
    "variable), un autre client que `from_` ou `/rest/v1/`, et deux tables de même nom dans deux "
    "schémas exposés (le chemin `/rest/v1/<table>` ne porte pas le schéma) ne sont pas distingués",
    "supabase : les migrations se lisent par motif ; une table créée par du SQL dynamique, par "
    "`create table … as`, renommée par `alter table … rename`, ou décrite dans un schéma "
    "déclaratif `supabase/schemas/` n est pas inventoriée",
    "supabase : les commentaires SQL sont retirés avant lecture ; une chaîne qui contient `--` "
    "est tronquée au même endroit",
    "supabase : la RLS active ne dit rien de la JUSTESSE des politiques ; seul un test sous rôle "
    "en juge, et ce pan ne fait que constater qu il existe",
]

_DOSSIER_MIGRATIONS = Path("supabase") / "migrations"
_DOSSIER_TESTS = Path("supabase") / "tests"
_SCHEMAS_PAR_DEFAUT = ("public", "graphql_public")
_NOM = r"(?:\"[^\"]+\"|[A-Za-z_][\w$]*)"
_NOM_QUALIFIE = rf"(?P<nom>{_NOM}(?:\s*\.\s*{_NOM})?)"
_CREATE = re.compile(
    rf"\bcreate\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?{_NOM_QUALIFIE}", re.I
)
_DROP = re.compile(rf"\bdrop\s+table\s+(?:if\s+exists\s+)?{_NOM_QUALIFIE}", re.I)
_RLS = re.compile(
    rf"\balter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?{_NOM_QUALIFIE}\s+"
    r"(?P<action>enable|disable|force|no\s+force)\s+row\s+level\s+security",
    re.I,
)
CHAMP_DECLARATION = "FORGE_TESTS_SUPABASE_TABLES_EXERCEES"
_EXTENSIONS_TEST = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh"}
_DOSSIERS_IGNORES = {"node_modules", "__pycache__", ".git", ".venv", "venv"}
_REST = re.compile(r"/rest/v1/(?P<table>[A-Za-z_][\w$]*)")
_FROM = re.compile(r"""\bfrom_\s*\(\s*(["'`])(?P<table>[A-Za-z_][\w$]*)\1""")
_COMMENTAIRE_DIESE = re.compile(r"(?m)(^|\s)#.*$")
_ROLE = re.compile(
    r"\bset\s+local\s+role\s+(?:authenticated|anon)\b|request\.jwt\.claim|"
    r"\btests\.authenticate_as\s*\(",
    re.I,
)


def _sans_commentaires(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", sql)


def _qualifier(brut: str) -> tuple[str, str]:
    parties = [p.strip() for p in re.split(r"\s*\.\s*", brut.strip(), maxsplit=1)]
    noms = [p[1:-1] if p.startswith('"') else p.lower() for p in parties]
    return (noms[0], noms[1]) if len(noms) == 2 else ("public", noms[0])


def _schemas_exposes(cible: Path) -> tuple[str, ...]:
    config = cible / "supabase" / "config.toml"
    if config.is_file():
        try:
            donnees: Any = tomllib.loads(config.read_text(encoding="utf-8", errors="ignore"))
        except tomllib.TOMLDecodeError:
            return _SCHEMAS_PAR_DEFAUT
        schemas = (donnees.get("api") or {}).get("schemas") if isinstance(donnees, dict) else None
        if isinstance(schemas, list) and all(isinstance(s, str) for s in schemas):
            return tuple(schemas)
    return _SCHEMAS_PAR_DEFAUT


def _migrations(cible: Path) -> list[Path]:
    dossier = cible / _DOSSIER_MIGRATIONS
    return sorted(dossier.glob("*.sql")) if dossier.is_dir() else []


def _lire_migrations(cible: Path) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], bool],
                                           list[tuple[str, int]]]:
    """(tables créées → fichier, état final de la RLS, réactivations de realtime.messages)."""
    tables: dict[tuple[str, str], str] = {}
    rls: dict[tuple[str, str], bool] = {}
    realtime: list[tuple[str, int]] = []
    for fichier in _migrations(cible):
        sql = _sans_commentaires(fichier.read_text(encoding="utf-8", errors="ignore"))
        evenements: list[tuple[int, str, re.Match[str]]] = []
        for genre, motif in (("create", _CREATE), ("drop", _DROP), ("rls", _RLS)):
            evenements += [(m.start(), genre, m) for m in motif.finditer(sql)]
        for position, genre, m in sorted(evenements, key=lambda e: e[0]):
            cle = _qualifier(m.group("nom"))
            if genre == "create":
                tables[cle] = str(fichier)
                rls.setdefault(cle, False)
            elif genre == "drop":
                tables.pop(cle, None)
                rls.pop(cle, None)
            else:
                action = " ".join(m.group("action").lower().split())
                if cle == ("realtime", "messages") and action == "enable":
                    realtime.append((str(fichier), sql.count("\n", 0, position) + 1))
                if action in ("enable", "force"):
                    rls[cle] = True
                elif action == "disable":
                    rls[cle] = False
    return tables, rls, realtime


def inventaire(cible: Path) -> list[Element]:
    tables, _, _ = _lire_migrations(cible)
    exposes = _schemas_exposes(cible)
    return [
        Element(
            f"supabase:table:{schema}.{nom}",
            PAN,
            f"table `{schema}.{nom}` d un schéma exposé par l API",
            source,
        )
        for (schema, nom), source in sorted(tables.items())
        if schema in exposes
    ]


def _tests_sous_role(cible: Path) -> list[str]:
    dossier = cible / _DOSSIER_TESTS
    if not dossier.is_dir():
        return []
    textes = [
        _sans_commentaires(f.read_text(encoding="utf-8", errors="ignore"))
        for f in sorted(dossier.rglob("*.sql"))
    ]
    return [t for t in textes if _ROLE.search(t)]


def _sans_commentaires_js(texte: str) -> str:
    """Retire `//` et `/* */` sans toucher aux chaînes : le `//` d une URL n ouvre rien."""
    sortie: list[str] = []
    i, n = 0, len(texte)
    while i < n:
        c = texte[i]
        if c in "\"'`":
            j = i + 1
            while j < n and texte[j] != c:
                j += 2 if texte[j] == "\\" else 1
            sortie.append(texte[i : j + 1])
            i = j + 1
        elif texte.startswith("//", i):
            j = texte.find("\n", i)
            i = n if j < 0 else j
        elif texte.startswith("/*", i):
            j = texte.find("*/", i + 2)
            fin = n if j < 0 else j + 2
            sortie.append("\n" * texte.count("\n", i, fin))
            i = fin
        else:
            sortie.append(c)
            i += 1
    return "".join(sortie)


def _appels_api_texte(texte: str) -> set[str]:
    tables = {m.group("table") for m in _REST.finditer(texte)}
    return tables | {m.group("table") for m in _FROM.finditer(texte)}


def _appels_api_python(source: str) -> set[str]:
    """Tables appelées par l API en Python : chaînes et appels, ni commentaires ni docstrings."""
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        return _appels_api_texte(_COMMENTAIRE_DIESE.sub(r"\1", source))
    docstrings: set[int] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            premier = noeud.body[0] if noeud.body else None
            if (
                isinstance(premier, ast.Expr)
                and isinstance(premier.value, ast.Constant)
                and isinstance(premier.value.value, str)
            ):
                docstrings.add(id(premier.value))
    tables: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            if id(noeud) not in docstrings:
                tables.update(m.group("table") for m in _REST.finditer(noeud.value))
        elif (
            isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr == "from_"
            and noeud.args
            and isinstance(noeud.args[0], ast.Constant)
            and isinstance(noeud.args[0].value, str)
        ):
            tables.add(noeud.args[0].value)
    return tables


def _fichiers_de_tests(cible: Path) -> list[Path]:
    """Fichiers de code situés sous un dossier nommé `tests` (à la racine ou plus bas)."""
    trouves: list[Path] = []
    for dossier, sous_dossiers, fichiers in os.walk(cible):
        sous_dossiers[:] = sorted(d for d in sous_dossiers if d not in _DOSSIERS_IGNORES)
        if "tests" not in Path(dossier).relative_to(cible).parts:
            continue
        trouves += [
            Path(dossier) / f for f in sorted(fichiers) if Path(f).suffix in _EXTENSIONS_TEST
        ]
    return trouves


def _tables_appelees_par_l_api(cible: Path) -> set[str]:
    """Noms de tables appelés par `/rest/v1/<table>` ou `from_("<table>")` depuis `tests/`."""
    tables: set[str] = set()
    for fichier in _fichiers_de_tests(cible):
        texte = fichier.read_text(encoding="utf-8", errors="ignore")
        if fichier.suffix == ".py":
            tables |= _appels_api_python(texte)
        elif fichier.suffix == ".sh":
            tables |= _appels_api_texte(_COMMENTAIRE_DIESE.sub(r"\1", texte))
        else:
            tables |= _appels_api_texte(_sans_commentaires_js(texte))
    tables.discard("rpc")  # `/rest/v1/rpc/<fonction>` appelle une fonction, pas une table
    return tables


def _tables_declarees(cible: Path) -> set[str]:
    """Tables que le PRODUIT déclare exercées : `schéma.table`, ou `table` seul pour `public`."""
    brut = os.environ.get(CHAMP_DECLARATION)
    if brut is None:
        brut = _valeurs(cible / ENV_PROJET).get(CHAMP_DECLARATION, "")
    declarees: set[str] = set()
    for morceau in brut.split(","):
        if morceau.strip():
            schema, nom = _qualifier(morceau)
            declarees.add(f"supabase:table:{schema}.{nom}")
    return declarees


def exerces_par_declaration(cible: Path) -> set[str]:
    """Tables inventoriées que le produit déclare exercées ; une table inconnue est ignorée."""
    return _tables_declarees(cible) & {e.id for e in inventaire(cible)}


def exerces(cible: Path) -> set[str]:
    textes = _tests_sous_role(cible)
    appelees = _tables_appelees_par_l_api(cible)
    couverts: set[str] = set(exerces_par_declaration(cible))
    for element in inventaire(cible):
        schema, nom = element.id.removeprefix("supabase:table:").split(".", 1)
        motif = re.compile(
            rf"(?<![\w.]){re.escape(nom)}\b|\b{re.escape(schema)}\.{re.escape(nom)}\b"
        )
        if any(motif.search(t) for t in textes) or nom in appelees:
            couverts.add(element.id)
    return couverts


def _constats(cible: Path) -> list[Finding]:
    tables, rls, realtime = _lire_migrations(cible)
    exposes = _schemas_exposes(cible)
    constats = [
        Finding(
            id=f"rls:{schema}.{nom}",
            classe=classes.RLS_ABSENTE,
            localisation=source,
            message=(
                f"table `{schema}.{nom}` d un schéma exposé sans RLS active à l issue des "
                "migrations — « A table in an exposed schema without RLS is readable and writable "
                "by any role with a grant on it » (page Row Level Security de Supabase, lue le "
                f"29/10/2026) ; ajouter `alter table {schema}.{nom} enable row level security`"
            ),
            risque=coter(PAN, f"rls:{schema}.{nom}", source),
        )
        for (schema, nom), source in sorted(tables.items())
        if schema in exposes and not rls.get((schema, nom))
    ]
    constats += [
        Finding(
            id=f"realtime-rls:{Path(fichier).name}:{ligne}",
            classe=classes.REALTIME_RLS_REACTIVEE,
            localisation=f"{fichier}:{ligne}",
            message=(
                "la migration réactive la RLS de `realtime.messages`, déjà active : elle échoue en "
                "`42501 must be owner of table messages` et la transaction s arrête avec les "
                "`create policy` qui suivent (page Realtime Authorization, lue le 29/10/2026) ; "
                "retirer la ligne `alter table`"
            ),
            risque=coter(PAN, "realtime-rls", fichier),
        )
        for fichier, ligne in realtime
    ]
    return constats


def sans_objet(cible: Path) -> str | None:
    """PREUVE d absence : aucune migration Supabase, donc aucun schéma Supabase à juger."""
    if _migrations(cible):
        return None
    return (
        "aucune migration Supabase (`supabase/migrations/*.sql`) : ce projet ne porte pas de base "
        "Supabase"
    )


def analyser(cible: Path) -> SortieAdaptateur:
    motif = sans_objet(cible)
    if motif:
        return evaluer_surface(NOM, PAN, str(cible), [], set(), SEUIL, NON_JUGE, sans_objet=motif)
    sortie = evaluer_surface(
        NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE
    )
    sur_declaration = sorted(exerces_par_declaration(cible))
    if sur_declaration:
        sortie.non_juge.append(
            "supabase : tables tenues pour exercées sur déclaration du produit "
            f"({CHAMP_DECLARATION}), sans test lu par ce pan : "
            + ", ".join(i.removeprefix("supabase:table:") for i in sur_declaration)
        )
    constats = _constats(cible)
    if constats:
        sortie.findings = [*constats, *sortie.findings]
        sortie.verdict = "FAIL"
    return sortie
