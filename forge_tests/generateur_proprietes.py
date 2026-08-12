"""Squelettes de tests PAR PROPRIÉTÉ (Hypothesis) — TF-0104, sous-item 3/4.

Le générateur historique (`forge_tests.generateur`) dérive des CAS ponctuels depuis le schéma
OpenAPI : une requête, une réponse. Il ne propose rien pour les fonctions PURES à forte
combinatoire (calcul, parsing, validation), le terrain naturel du test par propriété
(Hypothesis / fast-check — état de l art 2026, cf. pkgpulse.com et oneuptime.com/Hypothesis).

Loi du générateur, reprise ICI à l identique (même texte que `forge_tests.generateur`) : il ne
produit que ce qu il sait construire honnêtement. La PURETÉ d une fonction est une heuristique
(signature simple, pas d effet de bord détecté), jamais une preuve. La PROPRIÉTÉ à affirmer
n est JAMAIS devinée — chaque squelette porte un `# TODO` explicite, exactement comme les codes
NON GENERABLES du générateur API refusent d inventer une précondition métier.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

NON_JUGE = [
    "generateur_proprietes : la PURETE d une fonction est approchee par une heuristique legere "
    "(pas de self/cls, pas d appel a des fonctions d effet de bord connues) — pas prouvee ; une "
    "fonction retenue a tort reste une PROPOSITION a relire, jamais un cas execute a l aveugle",
    "generateur_proprietes : la PROPRIETE a affirmer n est jamais devinee — chaque squelette "
    "porte un `# TODO` explicite, la seule chose que ce module ne PEUT pas dériver du code",
    "generateur_proprietes : seuls les parametres aux annotations SIMPLES (int, float, str, "
    "bool) sont couverts — une fonction pure a parametres complexes (dataclass, Enum) n est "
    "pas proposee ici",
]

# Type Python annoté (texte de l annotation) -> stratégie Hypothesis équivalente.
_TYPES_SIMPLES: dict[str, str] = {
    "int": "st.integers()",
    "float": "st.floats(allow_nan=False, allow_infinity=False)",
    "str": "st.text()",
    "bool": "st.booleans()",
}

# Appels qui trahissent un effet de bord — une fonction qui les invoque n est pas retenue.
_APPELS_IMPURS = {"open", "print", "input"}
_ATTRIBUTS_IMPURS = {"write", "read", "execute", "commit", "append", "pop", "remove"}

_EXCLUS = {".venv", "venv", "node_modules", "__pycache__", "tests", "migrations", "alembic"}


@dataclass(frozen=True)
class Candidate:
    """Une fonction pure PLAUSIBLE à forte combinatoire — au moins deux paramètres simples."""

    module: str
    fonction: str
    parametres: tuple[tuple[str, str], ...]  # (nom, type annoté simple)
    fichier: str


def _purete_plausible(noeud: ast.FunctionDef) -> bool:
    if noeud.args.args and noeud.args.args[0].arg in ("self", "cls"):
        return False
    for enfant in ast.walk(noeud):
        if isinstance(enfant, (ast.Global, ast.Nonlocal)):
            return False
        if isinstance(enfant, ast.Attribute) and enfant.attr in _ATTRIBUTS_IMPURS:
            return False
        if (
            isinstance(enfant, ast.Call)
            and isinstance(enfant.func, ast.Name)
            and enfant.func.id in _APPELS_IMPURS
        ):
            return False
    return True


def _parametres_simples(noeud: ast.FunctionDef) -> tuple[tuple[str, str], ...] | None:
    parametres: list[tuple[str, str]] = []
    for arg in noeud.args.args:
        if arg.arg in ("self", "cls"):
            continue
        if arg.annotation is None:
            return None
        try:
            nom_type = ast.unparse(arg.annotation)
        except Exception:  # noqa: BLE001 — annotation non déroulable, on refuse plutôt qu on devine
            return None
        if nom_type not in _TYPES_SIMPLES:
            return None
        parametres.append((arg.arg, nom_type))
    return tuple(parametres) if parametres else None


def candidats(cible: Path, racine_relative: str = "backend/app") -> list[Candidate]:
    """Fonctions pures PLAUSIBLES à forte combinatoire (≥ 2 paramètres simples annotés)."""
    racine = cible / racine_relative
    if not racine.is_dir():
        return []
    trouves: list[Candidate] = []
    for fichier in sorted(racine.rglob("*.py")):
        relatif = fichier.relative_to(racine).parts[:-1]
        if _EXCLUS & set(relatif):
            continue
        try:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.FunctionDef):
                continue
            if noeud.name.startswith("_") or noeud.name.startswith("test_"):
                continue
            parametres = _parametres_simples(noeud)
            if not parametres or len(parametres) < 2:
                continue
            if not _purete_plausible(noeud):
                continue
            trouves.append(
                Candidate(
                    module=fichier.stem,
                    fonction=noeud.name,
                    parametres=parametres,
                    fichier=str(fichier),
                )
            )
    return trouves


ENTETE = '''"""Squelettes de PROPRIÉTÉ générés par Forge Tests — À COMPLÉTER AVANT USAGE.

Chaque squelette cible une fonction PURE PLAUSIBLE (heuristique, pas une preuve) à forte
combinatoire de paramètres. La PROPRIÉTÉ à affirmer n est jamais devinée : chaque test porte un
`# TODO` explicite, à la charge du relecteur.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
'''

_GABARIT = '''

@given({args})
def test_propriete_{module}_{fonction}({noms}) -> None:
    """Squelette pour `{module}.{fonction}` — propriété à formuler par un humain."""
    resultat = {module}.{fonction}({noms})  # noqa: F841 — relu avant usage
    assert True  # TODO : exprimer l invariant attendu pour TOUTE entree generee ci-dessus
'''


def squelette(candidat: Candidate) -> str:
    args = ", ".join(f"{nom}={_TYPES_SIMPLES[type_]}" for nom, type_ in candidat.parametres)
    noms = ", ".join(nom for nom, _ in candidat.parametres)
    return _GABARIT.format(module=candidat.module, fonction=candidat.fonction, args=args, noms=noms)


def proposer(cible: Path, racine_relative: str = "backend/app") -> str:
    """Fichier de squelettes PROPOSÉS — jamais écrit dans le projet audité (G-1, comme `generateur`).

    Chaîne vide si aucun candidat : l appelant décide alors de ne rien déposer, plutôt que de
    déposer un fichier d en-tête seul qui se ferait passer pour un livrable.
    """
    trouves = candidats(cible, racine_relative)
    if not trouves:
        return ""
    corps = "".join(squelette(candidat) for candidat in trouves)
    return ENTETE + corps
