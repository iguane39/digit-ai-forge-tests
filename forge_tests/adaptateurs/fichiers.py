"""Adaptateur Fichiers — chemins de parsing par AST (P3), couverture par exécution (P2).

Même bascule que le pan Batch : plus de tuple VARIANTES déclaré dans la source, plus de
recoupement textuel. Les chemins de parsing sont dérivés de l arbre syntaxique, et « exercé »
veut dire « ligne réellement exécutée par la suite ».
"""

from __future__ import annotations

import ast
from pathlib import Path

from forge_tests.disposition import paquet_sources
from forge_tests.execution import executees, motif_indisponibilite
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "fichiers-python", "fichiers", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "exposer le module d import/parsing sous `backend/app/importer.py` (ou un nom portant "
    "`import`/`parse`/`fichier`) et exercer chacun de ses chemins d erreur"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T5", "famille": "technique", "titre": "Fichiers",
     "decoupe": "format", "axe_cas": "unitaire"},
)

FICHIER = "importer.py"

NON_JUGE = [
    "fichiers : les chemins sont les branches du module de parsing ; une variante de format qui "
    "ne produit aucune branche dédiée (encodage géré par la bibliothèque) reste invisible",
]


def _src(cible: Path) -> Path:
    # Paquet DECOUVERT, pas suppose `app` — voir `forge_tests.disposition`.
    racine = paquet_sources(cible)
    return (racine or cible / "backend" / "app") / FICHIER


def inventaire(cible: Path) -> list[Element]:
    src = _src(cible)
    if not src.exists():
        return []
    arbre = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    elements: list[Element] = []
    vus: set[int] = set()
    for noeud in ast.walk(arbre):
        blocs: list[tuple[str, list[ast.stmt]]] = []
        if isinstance(noeud, ast.If):
            blocs = [("condition vraie", noeud.body), ("condition fausse", noeud.orelse)]
        elif isinstance(noeud, ast.ExceptHandler):
            blocs = [("repli sur exception", noeud.body)]
        elif isinstance(noeud, (ast.For, ast.While)):
            blocs = [("itération", noeud.body)]
        for libelle, corps in blocs:
            if not corps or corps[0].lineno in vus:
                continue
            ligne = corps[0].lineno
            vus.add(ligne)
            elements.append(
                Element(
                    f"chemin:{FICHIER}:{ligne}",
                    PAN,
                    f"chemin de parsing — {libelle}, ligne {ligne}",
                    str(src),
                )
            )
    return elements


def exerces(cible: Path) -> set[str] | None:
    lignes = executees(cible, FICHIER)
    if lignes is None:
        return None
    return {
        e.id for e in inventaire(cible) if int(e.id.rsplit(":", 1)[1]) in lignes
    }


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM,
            PAN,
            str(cible),
            "SKIP",
            non_juge=[
                *NON_JUGE,
                "fichiers : couverture d exécution indisponible — "
                + motif_indisponibilite(
                    cible, "backend", "suite rouge ou environnement du projet absent"
                ),
            ],
        )
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), couvert, SEUIL, NON_JUGE)
