"""Invariants métier — d où ils viennent (décision de conception, 2026-08-02).

Le générateur butait sur les codes 400 et 409 : le schéma OpenAPI déclare qu ils existent,
jamais ce qui les déclenche. Trois sources étaient possibles :

  a. l humain les saisit — fiable, mais le produit ne s applique plus « à n importe quel projet » ;
  b. un LLM les devine — non déterministe, et un cas généré faux invite au test-fitting ;
  c. **le code les déclare déjà** — dans les gardes qui précèdent chaque levée d erreur.

**Retenu : (c).** Un endpoint qui renvoie 400 le fait toujours derrière une condition écrite.
Cette condition EST l invariant métier, exprimé dans le seul langage qui ne ment pas sur le
comportement réel. On ne devine pas : on lit.

Limite fondatrice, déclarée : on extrait ainsi l invariant TEL QU IMPLÉMENTÉ, pas tel que
voulu. Si la garde est fausse, le cas généré confirmera le bug au lieu de le révéler. Cette
source ne remplace donc jamais une spécification — elle permet d exercer un chemin d erreur
que rien d autre ne sait atteindre.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

NON_JUGE = [
    "invariants : extraits des gardes du code — donc l invariant TEL QU IMPLEMENTE, pas tel que "
    "voulu. Une garde fausse produit un cas qui confirme le bug au lieu de le reveler",
    "invariants : seules les gardes de forme simple sont lues (comparaison, appartenance, "
    "negation) ; une garde composee ou deportee dans une fonction n est pas extraite",
    "invariants : la resolution des gardes deportees s arrete a UN niveau d appel, par nom "
    "simple, cherche dans TOUS les modules de l application (RT-9 / TF-0135). Un helper qui en "
    "appelle un autre, un appel par attribut (`service.refuser()`) ou un status_code calcule "
    "restent invisibles — le code declare paraitra alors « jamais leve »",
    "invariants : la resolution par nom n est PAS qualifiee par module (TF-0135) — deux "
    "fonctions de meme nom dans deux fichiers distincts de l application voient leurs codes "
    "fusionnes, ce qui peut masquer ou inventer une garde",
]


@dataclass(frozen=True)
class Invariant:
    """Une condition qui, si elle est satisfaite, fait renvoyer `code` par `operation`."""

    fonction: str
    code: int
    cible: str  # nom du parametre ou du champ de corps concerne
    origine: str  # "query" | "corps" | "etat"
    valeur_declenchante: object | None
    ligne: int


def _litteral(noeud: ast.AST) -> object | None:
    if isinstance(noeud, ast.Constant):
        return noeud.value
    return None


def _nom_cible(noeud: ast.AST) -> tuple[str, str] | None:
    """(nom, origine) du sujet d une garde : `statut` (query) ou `corps.quantite` (corps)."""
    if isinstance(noeud, ast.Name):
        return noeud.id, "query"
    if isinstance(noeud, ast.Attribute) and isinstance(noeud.value, ast.Name):
        return noeud.attr, "corps"
    if isinstance(noeud, ast.Subscript):
        cle = _litteral(noeud.slice)
        if isinstance(cle, str):
            return cle, "etat"
    return None


def _valeur_violante(test: ast.AST, constantes: dict[str, tuple]) -> tuple[str, str, object] | None:
    """Valeur qui rend la garde VRAIE, donc qui déclenche l erreur."""
    for comparaison in ast.walk(test):
        if not isinstance(comparaison, ast.Compare) or len(comparaison.ops) != 1:
            continue
        sujet = _nom_cible(comparaison.left)
        if sujet is None:
            continue
        nom, origine = sujet
        operateur, droite = comparaison.ops[0], comparaison.comparators[0]

        # `x not in NOM_DE_TUPLE` -> toute valeur absente du tuple declenche
        if isinstance(operateur, ast.NotIn):
            if isinstance(droite, ast.Name) and droite.id in constantes:
                return nom, origine, "__hors_liste__"
            if isinstance(droite, (ast.Tuple, ast.List)):
                return nom, origine, "__hors_liste__"
        # `x == "litteral"` -> ce litteral declenche
        if isinstance(operateur, ast.Eq):
            valeur = _litteral(droite)
            if valeur is not None:
                return nom, origine, valeur
        # `x <= 0` / `x < 1` -> une valeur qui satisfait la comparaison
        borne = _litteral(droite)
        if isinstance(borne, (int, float)) and not isinstance(borne, bool):
            if isinstance(operateur, ast.LtE):
                return nom, origine, borne
            if isinstance(operateur, ast.Lt):
                return nom, origine, borne - 1
            if isinstance(operateur, ast.GtE):
                return nom, origine, borne
            if isinstance(operateur, ast.Gt):
                return nom, origine, borne + 1
    return None


def _code_leve(corps: list[ast.stmt]) -> tuple[int, int] | None:
    """(code HTTP, ligne) levé directement par ce bloc, s il y en a un."""
    for noeud in corps:
        if not isinstance(noeud, ast.Raise) or not isinstance(noeud.exc, ast.Call):
            continue
        for mot in noeud.exc.keywords:
            if mot.arg == "status_code":
                valeur = _litteral(mot.value)
                if isinstance(valeur, int):
                    return valeur, noeud.lineno
    return None


def extraire(source: Path) -> list[Invariant]:
    """Lit les gardes du module et en tire les invariants qu elles imposent."""
    if not source.exists():
        return []
    arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    constantes = {
        cible.id: tuple(x.value for x in noeud.value.elts if isinstance(x, ast.Constant))
        for noeud in arbre.body
        if isinstance(noeud, ast.Assign) and isinstance(noeud.value, (ast.Tuple, ast.List))
        for cible in noeud.targets
        if isinstance(cible, ast.Name)
    }
    invariants: list[Invariant] = []
    for fonction in ast.walk(arbre):
        if not isinstance(fonction, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for noeud in ast.walk(fonction):
            if not isinstance(noeud, ast.If):
                continue
            leve = _code_leve(noeud.body)
            if leve is None:
                continue
            code, ligne = leve
            violant = _valeur_violante(noeud.test, constantes)
            if violant is None:
                continue
            nom, origine, valeur = violant
            invariants.append(
                Invariant(fonction.name, code, nom, origine, valeur, ligne)
            )
    return invariants


def handlers(source: Path | list[Path]) -> dict[tuple[str, str], str]:
    """(methode, chemin) -> nom de la fonction qui traite la route, lu depuis les decorateurs.

    TF-0135 — `source` accepte aussi une LISTE de fichiers. Une app FastAPI a routeurs monte
    ses `include_router` depuis main.py, mais les decorateurs `@router.get/post/...` et leurs
    gardes vivent dans les modules du routeur (`app/api/routes_*.py`) : bornee au seul main.py,
    cette table ressortait VIDE sur un projet ainsi organise (Produit-01), et toute divergence
    verifiee plus loin (`codes_par_fonction`) devenait donc faussement injustifiable.
    """
    fichiers = [source] if isinstance(source, Path) else list(source)
    import re as _re

    table: dict[tuple[str, str], str] = {}
    for fichier in fichiers:
        if not fichier.exists():
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in noeud.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                methode = deco.func.attr.upper()
                if methode not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    continue
                if not deco.args:
                    continue
                chemin = _litteral(deco.args[0])
                if isinstance(chemin, str):
                    table[(methode, _re.sub(r"\{[^}]*\}", "{}", chemin))] = noeud.name
    return table


def _appels_locaux(fonction: ast.AST) -> set[str]:
    """Noms des fonctions du MÊME module appelées par celle-ci — `f()`, jamais `obj.f()`.

    Un appel par attribut (`service.refuser()`) désigne un objet dont on ne sait pas, sans
    résolution de types, quel code il exécute : le suivre serait deviner. Un appel par nom
    simple, lui, se résout par lecture du module — c est la seule forme retenue.
    """
    appeles: set[str] = set()
    for noeud in ast.walk(fonction):
        if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name):
            appeles.add(noeud.func.id)
    return appeles


def codes_par_fonction(source: Path | list[Path]) -> dict[str, set[int]]:
    """Codes HTTP levés par chaque fonction, QUEL QUE SOIT le contexte de la levée.

    Distinct de `extraire` : pour savoir si un code declare est produit quelque part, peu importe
    que la garde soit un `if`, un `except` ou un `assert`. `extraire` ne retient que les gardes
    dont on sait DERIVER la valeur declenchante — c est un sous-ensemble strict, utile a la
    generation, trompeur pour la detection de divergence.

    **RT-9 (2026-08-06) — un niveau d appel est résolu.** L analyse ne reconnaissait que le
    `raise … status_code=<littéral>` écrit DANS le corps de la route. Un produit réel qui
    factorise son refus dans un helper (`_refuser_doublon()` d ASD Mail Manager, qui lève le
    409) voyait donc son 409 déclaré « jamais levé » : deux passes de correction sur le produit
    avant de retrouver la forme que l outil attendait — l outil imposait un style d écriture au
    lieu de lire le comportement. Une fonction qui appelle, par son nom simple, un helper du
    même module dont le corps lève avec un `status_code` constant hérite désormais de ce code.

    **TF-0135 — `source` accepte aussi une LISTE de fichiers.** Un helper deporte dans un AUTRE
    module du projet (un `routes_admin.py` distinct du `main.py` qui se contente d `include_
    router`) n etait pas plus visible que main.py lui-même ne contenait pas la route : lire
    tous les modules de l application rend visibles les gardes qui vivent a cote de leur route,
    au prix d une precision en moins — deux fonctions de MEME NOM dans deux fichiers distincts
    voient leurs codes fusionnes (declare ci-dessous, `NON_JUGE`).

    Limite résiduelle, DÉCLARÉE (voir « Contrat du projet audité » au README) : un seul niveau
    d appel, par nom simple, non qualifie par module. Un helper qui en appelle un autre, un
    helper atteint par attribut (`self.refuser()`, `service.refuser()`) ou un code calculé
    restent invisibles.
    """
    fichiers = [source] if isinstance(source, Path) else list(source)
    directs: dict[str, set[int]] = {}
    appels: dict[str, set[str]] = {}
    for fichier in fichiers:
        if not fichier.exists():
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for fonction in ast.walk(arbre):
            if not isinstance(fonction, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            codes: set[int] = set()
            for noeud in ast.walk(fonction):
                if not isinstance(noeud, ast.Raise) or not isinstance(noeud.exc, ast.Call):
                    continue
                for mot in noeud.exc.keywords:
                    if mot.arg == "status_code":
                        valeur = _litteral(mot.value)
                        if isinstance(valeur, int):
                            codes.add(valeur)
            # Fusion PAR NOM a travers les fichiers : deux fonctions homonymes de deux modules
            # distincts partagent leur entree — limite assumee, voir NON_JUGE ci-dessus.
            directs[fonction.name] = directs.get(fonction.name, set()) | codes
            appels[fonction.name] = appels.get(fonction.name, set()) | _appels_locaux(fonction)

    table: dict[str, set[int]] = {}
    for nom, codes in directs.items():
        herites = {
            code
            for appele in appels.get(nom, set())
            if appele != nom  # une recursion n apporte aucun code nouveau
            for code in directs.get(appele, set())
        }
        total = codes | herites
        if total:
            table[nom] = total
    return table
