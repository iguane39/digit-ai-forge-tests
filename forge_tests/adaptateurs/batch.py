"""Adaptateur Batch — branches inventoriées par AST (P3), couverture par exécution (P2).

Avant : l inventaire lisait un tuple BRANCHES déclaré dans la source, et la couverture se
déduisait d une mention textuelle. Deux dépendances à la coopération du projet analysé —
un projet réel n a ni l un ni l autre. Désormais les branches sont dérivées de l arbre
syntaxique, et « exercée » veut dire « ligne réellement exécutée par la suite ».
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from forge_tests.execution import NON_JUGE as NON_JUGE_EXEC
from forge_tests.execution import executees
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "batch-python", "batch", 0.90
FICHIER = "batch.py"
_CODE_REJET = re.compile(r"^[A-Z]{2,}-[A-Z]{2,}$")

NON_JUGE = [
    "batch : les branches sont dérivées de l AST du module ; une branche implicite (opérateur "
    "ternaire, court-circuit booléen) n est pas inventoriée séparément",
    *NON_JUGE_EXEC,
]


def _src(cible: Path) -> Path:
    return cible / "backend" / "app" / FICHIER


def _premiere_ligne(corps: list[ast.stmt]) -> int | None:
    return corps[0].lineno if corps else None


def inventaire(cible: Path) -> list[Element]:
    src = _src(cible)
    if not src.exists():
        return []
    arbre = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    elements: list[Element] = []
    vus: set[int] = set()

    for noeud in ast.walk(arbre):
        # Chaque branche = un bloc dont la première ligne exécutable identifie le chemin.
        blocs: list[tuple[str, list[ast.stmt]]] = []
        if isinstance(noeud, ast.If):
            blocs = [("si", noeud.body), ("sinon", noeud.orelse)]
        elif isinstance(noeud, ast.ExceptHandler):
            blocs = [("except", noeud.body)]
        elif isinstance(noeud, (ast.For, ast.While)):
            blocs = [("boucle", noeud.body)]
        for libelle, corps in blocs:
            ligne = _premiere_ligne(corps)
            if ligne is None or ligne in vus:
                continue
            vus.add(ligne)
            elements.append(
                Element(
                    f"branche:{FICHIER}:{ligne}",
                    PAN,
                    f"branche {libelle} ligne {ligne}",
                    str(src),
                )
            )
        # Codes de rejet : littéraux de la forme XXX-YYY, quel que soit leur nom de variable.
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            if _CODE_REJET.match(noeud.value):
                cle = f"rejet:{noeud.value}"
                if cle not in {e.id for e in elements}:
                    elements.append(
                        Element(cle, PAN, f"code de rejet {noeud.value}", str(src))
                    )
    return elements


def exerces(cible: Path) -> set[str] | None:
    lignes = executees(cible, FICHIER)
    if lignes is None:
        return None
    couvert: set[str] = set()
    for element in inventaire(cible):
        if element.id.startswith("branche:"):
            if int(element.id.rsplit(":", 1)[1]) in lignes:
                couvert.add(element.id)
    # Un code de rejet est exercé si la ligne qui le produit a été exécutée.
    src = _src(cible)
    arbre = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            if _CODE_REJET.match(noeud.value) and noeud.lineno in lignes:
                couvert.add(f"rejet:{noeud.value}")
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM,
            PAN,
            str(cible),
            "SKIP",
            non_juge=[*NON_JUGE, "couverture d exécution indisponible : suite rouge ou env absent"],
        )
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), couvert, SEUIL, NON_JUGE)
