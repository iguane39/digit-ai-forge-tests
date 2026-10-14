"""TF-1692 — la fonction publique `declarations.constats_inconnus` rendait un compte faux.

Le fait : depuis TF-1672 (070322d), `appliquer` calcule lui-même les déclarations inconnues, en
retirant celles qu il a RAPPROCHÉES d un constat dont seule la ligne a changé. La fonction
`constats_inconnus`, restée publique, n était plus appelée par aucun module et ignorait ce
rapprochement : un consommateur qui l aurait appelée aurait compté inconnue une déclaration
pourtant servie. Recherche du 14/10/2026 : aucun module de ce dépôt ni d un autre dépôt du poste
ne l importe. Elle est donc retirée ; le compte des inconnues vit au seul rapport
(`declarations.inconnues`), qui tient compte du rapprochement.

Ce que ces tests fixent :
  1. le module `declarations` n expose plus `constats_inconnus` ;
  2. aucun module Python du dépôt (code, recette, tests) ne l importe, ne l appelle ni ne la
     redéfinit — l analyse porte sur l arbre syntaxique, pas sur le texte.
"""

from __future__ import annotations

import ast
from pathlib import Path

from forge_tests import declarations

NOM = "constats_inconnus"
RACINE = Path(__file__).resolve().parents[1]
DOSSIERS = ("forge_tests", "recette", "tests")


def _citations(fichier: Path) -> list[str]:
    """Les endroits où l arbre syntaxique du fichier importe, appelle ou définit `NOM`."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
    trouves = []
    for noeud in ast.walk(arbre):
        cite = (
            (isinstance(noeud, ast.Name) and noeud.id == NOM)
            or (isinstance(noeud, ast.Attribute) and noeud.attr == NOM)
            or (isinstance(noeud, ast.ImportFrom) and any(a.name == NOM for a in noeud.names))
            or (isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == NOM)
        )
        if cite:
            trouves.append(f"{fichier.relative_to(RACINE).as_posix()}:{noeud.lineno}")
    return trouves


def test_le_module_n_expose_plus_la_fonction():
    assert not hasattr(declarations, NOM)


def test_aucun_module_du_depot_ne_la_cite():
    fichiers = [f for dossier in DOSSIERS for f in sorted((RACINE / dossier).rglob("*.py"))]
    assert len(fichiers) > 100, "l analyse doit porter sur tout le dépôt, pas sur un dossier vide"
    citations = [c for f in fichiers for c in _citations(f)]
    assert citations == []
