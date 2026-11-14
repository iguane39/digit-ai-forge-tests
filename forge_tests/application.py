"""L'application ASGI du produit est-elle désignée ? — le refus nommé de TF-2161.

Fait remonté (Produit-86, RT-12, 04/11/2026). Un audit lancé sans `FORGE_TESTS_APP` sur une
application bâtie sur une fabrique (`creer_app()`) a rendu api 0/150 : la sonde ne greffe que
l'instance `app.main:app` quand rien n'est désigné, et une fabrique n'a pas d'instance module. Le
chiffre se lisait comme un produit non couvert, alors que la suite était verte et que la veille,
avec la désignation, le même produit rendait 144/144. Le défaut était dans la désignation, pas
dans le produit, et rien ne le disait.

Ce module lit les sources SANS les exécuter (analyse syntaxique) et répond à une seule question :
la désignation manque-t-elle sur un produit qui ne peut pas s'en passer ? Si oui, il rend le refus
(la clé, la fabrique trouvée, la valeur à recopier, l'endroit où la ranger) ; sinon `None`, et le
pan `api` poursuit comme avant.

Ce qu'il ne refuse PAS : un produit dont `app/main.py` porte une instance `app` (la désignation par
défaut de la sonde fonctionne) — tant que la sonde n'a pas rendu un relevé vide : après un relevé
vide sur une suite verte, une fabrique reconnue est refusée même si l'instance existe (TF-2423, la
suite bâtissait son application par `creer_app()` et n'exerçait jamais l'instance) —, un produit
sans fabrique reconnaissable (rien à nommer : le refus
serait une accusation sans objet), et un produit dont la désignation est faite quelque part, dans
l'environnement de l'opérateur, `.env.forge-tests` ou `forge/etapes/tests/audit.env`.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from forge_tests.authentification import ENV_AUDIT, ENV_PROJET, charger_env
from forge_tests.disposition import paquet_sources, racine_execution

VARIABLE = "FORGE_TESTS_APP"

#: La désignation par défaut de la sonde (`sondes/sonde_api.py:DESIGNATION_PAR_DEFAUT`). Recopiée
#: en deux morceaux pour juger la présence de l'instance sans importer la sonde, qui est un greffon
#: pytest. L'égalité avec la sonde est TESTÉE.
MODULE_PAR_DEFAUT = ("app", "main")
INSTANCE_PAR_DEFAUT = "app"

#: Noms de fabrique d'application courants, retenus quand le module importe `fastapi` ou
#: `starlette` : `create_app` existe aussi chez Flask, que la sonde ASGI ne greffe pas. Une
#: fonction qui construit un `FastAPI(...)` ou un `Starlette(...)` en est une, quel que soit son
#: nom.
_NOMS_DE_FABRIQUE = {
    "creer_app", "create_app", "make_app", "build_app", "get_app", "app_factory",
    "creer_application", "create_application", "application_factory",
}
_CONSTRUCTEURS_ASGI = {"FastAPI", "Starlette"}
_BIBLIOTHEQUES_ASGI = {"fastapi", "starlette"}

#: Modules d'entrée essayés dans cet ordre FIXE (liste de `adaptateurs.api._module_principal`).
_MODULES_D_ENTREE = ("main.py", "app.py", "asgi.py", "api.py", "__init__.py")


def _arbre(fichier: Path) -> ast.Module | None:
    try:
        return ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _a_une_instance(arbre: ast.Module, nom: str) -> bool:
    """Le module lie-t-il `nom` au niveau module (`app = ...`, `app: T = ...`) ?"""
    for noeud in arbre.body:
        cibles: list[ast.expr] = []
        if isinstance(noeud, ast.Assign):
            cibles = list(noeud.targets)
        elif isinstance(noeud, ast.AnnAssign) and noeud.value is not None:
            cibles = [noeud.target]
        if any(isinstance(c, ast.Name) and c.id == nom for c in cibles):
            return True
    return False


def _construit_une_application(fonction: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for noeud in ast.walk(fonction):
        if isinstance(noeud, ast.Call):
            appelee = noeud.func
            nom = appelee.id if isinstance(appelee, ast.Name) else getattr(appelee, "attr", "")
            if nom in _CONSTRUCTEURS_ASGI:
                return True
    return False


def _importe_asgi(arbre: ast.Module) -> bool:
    """Le module importe-t-il FastAPI ou Starlette (import à n'importe quel niveau) ?"""
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules = [alias.name for alias in noeud.names]
        elif isinstance(noeud, ast.ImportFrom):
            modules = [noeud.module or ""]
        else:
            continue
        if any(m.split(".")[0] in _BIBLIOTHEQUES_ASGI for m in modules):
            return True
    return False


def _fabriques(arbre: ast.Module) -> list[str]:
    """Fonctions de premier niveau qui sont des fabriques d'application, dans l'ordre du fichier."""
    asgi = _importe_asgi(arbre)
    return [
        noeud.name
        for noeud in arbre.body
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (_construit_une_application(noeud) or (asgi and noeud.name in _NOMS_DE_FABRIQUE))
    ]


def _module_pointe(racine: Path, fichier: Path) -> str:
    """`app/main.py` -> `app.main` ; `app/__init__.py` -> `app` : le module que la clé attend."""
    relatif = fichier.relative_to(racine).with_suffix("")
    parties = list(relatif.parts)
    if parties and parties[-1] == "__init__":
        parties = parties[:-1]
    return ".".join(parties)


def designation_trouvee(cible: Path) -> bool:
    """`FORGE_TESTS_APP` est-elle posée, par l'opérateur ou par le fichier du produit ?"""
    charger_env(cible)
    return bool((os.environ.get(VARIABLE) or "").strip())


def refus_designation(cible: Path, releve_vide: bool = False) -> dict | None:
    """Le refus à rendre, ou `None` quand l'analyse peut poursuivre.

    Le dictionnaire porte `fabrique` (`module:nom`), `fichier` (chemin:ligne de la fabrique) et
    `message` (la phrase publiée au rapport, qui cite la valeur à recopier et le fichier où la
    ranger).

    `releve_vide` (TF-2423) : la sonde a déjà tourné et rendu un relevé vide sur une suite verte.
    Avant la mesure, une instance `app` au niveau module suffit à ne pas refuser (la sonde la
    greffe, rien n'est prouvé contre elle). Après un relevé vide, elle ne suffit plus : une
    fabrique que la suite appelle à chaque test (`creer_app()`) coexiste très bien avec une
    instance module que personne n'exerce, et la sonde, qui ne greffe que celle-ci, rendait 0 %
    sans le dire (Produit-86, 10/11/2026 : api 0/173 contre 173/173 avec la désignation).
    """
    if designation_trouvee(cible):
        return None
    paquet = paquet_sources(cible)
    if paquet is None or not paquet.is_dir():
        return None
    racine = racine_execution(cible)

    defaut = racine.joinpath(*MODULE_PAR_DEFAUT[:-1], MODULE_PAR_DEFAUT[-1] + ".py")
    arbre_defaut = _arbre(defaut) if defaut.is_file() else None
    instance = arbre_defaut is not None and _a_une_instance(arbre_defaut, INSTANCE_PAR_DEFAUT)
    if instance and not releve_vide:
        return None

    for nom_module in _MODULES_D_ENTREE:
        fichier = paquet / nom_module
        arbre = _arbre(fichier) if fichier.is_file() else None
        if arbre is None:
            continue
        fabriques = _fabriques(arbre)
        if not fabriques:
            continue
        nom = fabriques[0]
        ligne = next(
            n.lineno for n in arbre.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom
        )
        valeur = f"{_module_pointe(racine, fichier)}:{nom}"
        try:
            lieu = f"{fichier.relative_to(cible).as_posix()}:{ligne}"
        except ValueError:
            lieu = f"{fichier}:{ligne}"
        if instance:
            # TF-2423 : l'instance existe, la sonde l'a greffée, la suite verte ne l'a pas exercée.
            motif = (
                f"api : REFUS — {VARIABLE} n'est désignée nulle part (ni dans l'environnement, "
                f"ni dans `{ENV_PROJET}`, ni dans `{ENV_AUDIT}`), la suite est verte et la sonde "
                f"a rendu un relevé VIDE : elle n'a greffé que l'instance `{INSTANCE_PAR_DEFAUT}` "
                f"du module `{'.'.join(MODULE_PAR_DEFAUT)}`, alors que ce projet porte aussi une "
                f"fabrique d'application (`{nom}`, {lieu}) que la suite appelle sans doute à "
                "chaque test. Le pan rendrait 0 % sur une suite verte, un défaut de désignation "
                "et non du produit (Produit-86, 10/11/2026 : api 0/173 contre 173/173 avec la "
                f"désignation de la fabrique). Le pan n'est pas mesuré. À faire : ajouter la "
                f"ligne `{VARIABLE}={valeur}` dans `{ENV_AUDIT}` (versionné avec le produit), "
                "puis `--reprendre` le rapport ; si la suite exerce bien l'instance, la désigner "
                f"(`{VARIABLE}={'.'.join(MODULE_PAR_DEFAUT)}:{INSTANCE_PAR_DEFAUT}`) : le relevé "
                "vide est alors celui d'une suite qui n'appelle pas l'application"
            )
        else:
            motif = (
                f"api : REFUS — {VARIABLE} n'est désignée nulle part (ni dans l'environnement, "
                f"ni dans `{ENV_PROJET}`, ni dans `{ENV_AUDIT}`) et l'application de ce projet "
                f"est une fabrique (`{nom}`, {lieu}) sans instance `app` au niveau module. La "
                "sonde ne verrait aucune requête : le pan rendrait 0 % sur une suite verte, un "
                "défaut de désignation et non du produit (Produit-86, 04/11/2026 : api 0/150 "
                "contre 144/144 la veille). Le pan n'est pas mesuré. À faire : ajouter la ligne "
                f"`{VARIABLE}={valeur}` dans `{ENV_AUDIT}` (versionné avec le produit), puis "
                "`--reprendre` le rapport"
            )
        return {"fabrique": valeur, "fichier": lieu, "message": motif}
    return None
