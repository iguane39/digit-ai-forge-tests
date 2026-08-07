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

from forge_tests.execution import arcs_executes, executees, motif_indisponibilite
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "batch-python", "batch", 0.90

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "exposer un traitement par lot sous `backend/app/batch.py` (ou un module dont le nom "
    "porte `batch`/`traitement`) avec ses branches de rejet et de reprise, et l exercer par "
    "la suite"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T4", "famille": "technique", "titre": "Batch",
     "decoupe": "job", "axe_cas": "unitaire"},
)

FICHIER = "batch.py"
_CODE_REJET = re.compile(r"^[A-Z]{2,}-[A-Z]{2,}$")

NON_JUGE = [
    "batch : les branches sont dérivées de l AST du module ; une branche implicite (opérateur "
    "ternaire, court-circuit booléen) n est pas inventoriée séparément",
    "batch : une branche dont le corps tient sur la MEME ligne que son test (`if x: y`) n est "
    "pas distinguable — les arcs de coverage.py vont de ligne a ligne, il n en existe aucun "
    "entre une ligne et elle-meme. Repli sur la couverture de ligne, moins precis",
]


def _sources(cible: Path) -> list[Path]:
    classique = cible / "backend" / "app" / FICHIER
    if classique.exists():
        return [classique]
    worker = cible / "backend" / "app" / "worker"
    if worker.is_dir():
        return sorted(p for p in worker.glob("*.py") if p.name != "__init__.py")
    return []


def _src(cible: Path) -> Path:
    return cible / "backend" / "app" / FICHIER


# ligne du corps -> ligne du test qui y mene. Rempli a l inventaire, lu a la couverture.
_ARCS_ATTENDUS: dict[int, int] = {}


def _premiere_ligne(corps: list[ast.stmt]) -> int | None:
    return corps[0].lineno if corps else None


def inventaire(cible: Path) -> list[Element]:
    elements: list[Element] = []
    for src in _sources(cible):
        elements.extend(_inventaire_module(src))
    return elements


def _inventaire_module(src: Path) -> list[Element]:
    arbre = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    elements: list[Element] = []
    vus: set[int] = set()
    nom_fichier = src.name

    for noeud in ast.walk(arbre):
        # Chaque branche = un bloc dont la première ligne exécutable identifie le chemin.
        blocs: list[tuple[str, list[ast.stmt]]] = []
        if isinstance(noeud, ast.If):
            blocs = [("si", noeud.body), ("sinon", noeud.orelse)]
            _ARCS_ATTENDUS.update(
                {corps[0].lineno: noeud.lineno for _, corps in blocs if corps}
            )
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
                    f"branche:{nom_fichier}:{ligne}",
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
    inv = inventaire(cible)  # remplit _ARCS_ATTENDUS
    arcs = arcs_executes(cible, FICHIER)
    for element in inv:
        if not element.id.startswith("branche:"):
            continue
        ligne = int(element.id.rsplit(":", 1)[1])
        origine = _ARCS_ATTENDUS.get(ligne)
        # L arc tranche quand le corps est sur une AUTRE ligne que son test. Quand il partage
        # sa ligne (`if x: y`), coverage.py n emet aucun arc distinctif — les arcs vont de ligne
        # a ligne. On retombe alors sur la ligne, et la limite est declaree.
        if arcs is not None and origine is not None and origine != ligne:
            if (origine, ligne) in arcs:
                couvert.add(element.id)
            continue
        if ligne in lignes:
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
        inv = inventaire(cible)
        return SortieAdaptateur(
            NOM,
            PAN,
            str(cible),
            "SKIP",
            non_juge=[
                *NON_JUGE,
                f"batch : {len(inv)} branches/rejets INVENTORIES mais couverture non mesurable — "
                + motif_indisponibilite(cible, "backend", "suite non executee sous sonde"),
            ],
        )
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), couvert, SEUIL, NON_JUGE)
