"""Adoption des cas dérivés — le contrat qui fait DESCENDRE le solde des propositions.

RT-13 (lot bourse-aux-vacants 20260814a) : les cahiers dérivés sont des PROPOSITIONS
déposées hors du projet (G-1), et rien ne permettait au projet de dire « ce cas-là, je l'ai
écrit, il vit ici ». Conséquence mesurée par le produit : après avoir écrit 11 tests couvrant
exactement les axes proposés, le cahier suivant régénérait les mêmes cent cas en « non joué ».
Un indicateur qui ne bouge pas quand le travail est fait cesse d'être lu.

**Condition technique déjà remplie**, vérifiée par le produit : les références de cas sont
DÉTERMINISTES (74 éléments communs entre deux audits, 0 identifiant changé) — elles sont donc
citables depuis du code.

**Le contrat, tenu par ce module :**

    <projet>/forge/cas-adoptes.jsonl   — une ligne JSON par cas adopté :
    {"cas": "F1-3025-3", "test": "frontend/tests/e2e/10-navigation.spec.ts"}

C'est le PROJET qui déclare, jamais la forge : elle ne saurait pas dire à sa place qu'un cas
est couvert. Le fichier est lu en LECTURE SEULE (G-1) et la déclaration est **vérifiée** :

  - le chemin de test cité doit EXISTER, sinon l'adoption est REFUSÉE avec son motif. Sans ce
    contrôle, un fichier d'adoptions survivrait à la suppression des tests qu'il cite, et le
    solde descendrait sur du vide — exactement le contraire de ce que RT-13 demande ;
  - une référence inconnue du cahier courant est déclarée, jamais silencieuse : elle signale
    un cas renommé ou un fichier périmé.

Ce module ne juge pas la QUALITÉ du test adopté : il constate une déclaration et l'existence
de son support. Vérifier qu'un test affirme ce qu'il prétend est le rôle de la mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

FICHIER = "forge/cas-adoptes.jsonl"

NON_JUGE = [
    "adoption : le fichier `forge/cas-adoptes.jsonl` est une DECLARATION du projet — ce module "
    "verifie que le test cite existe, jamais qu il couvre reellement le cas ni qu il affirme "
    "quoi que ce soit (c est le role de la mutation)",
    "adoption : un cas adopte puis renomme cote cahier ressort en reference INCONNUE, declaree "
    "telle quelle — la reference de cas est stable par construction, pas eternelle",
]


def charger(cible: Path) -> dict[str, dict]:
    """Adoptions déclarées par le projet, chacune avec son verdict de vérification.

    Renvoie `{ref_cas: {"test": chemin, "statut": "adopte"|"refuse", "motif": …}}`.
    Fichier absent = aucune adoption : ce n'est pas une faute, c'est l'état initial.
    """
    source = Path(cible) / FICHIER
    if not source.is_file():
        return {}
    adoptions: dict[str, dict] = {}
    for rang, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            entree = json.loads(ligne)
        except json.JSONDecodeError:
            adoptions[f"(ligne {rang})"] = {
                "test": "",
                "statut": "refuse",
                "motif": f"ligne {rang} de {FICHIER} : JSON invalide — declaration ignoree",
            }
            continue
        ref = str(entree.get("cas") or "").strip()
        test = str(entree.get("test") or "").strip()
        if not ref:
            continue
        if not test:
            adoptions[ref] = {
                "test": "",
                "statut": "refuse",
                "motif": "aucun test cite — une adoption sans support ne se verifie pas",
            }
            continue
        chemin = Path(cible) / test
        if not chemin.exists():
            adoptions[ref] = {
                "test": test,
                "statut": "refuse",
                "motif": f"le test cite est introuvable ({test}) — adoption refusee",
            }
            continue
        adoptions[ref] = {"test": test, "statut": "adopte", "motif": ""}
    return adoptions


def statut(adoptions: dict[str, dict], ref: str) -> dict:
    """Statut d'un cas : adopté (avec son test), refusé (avec son motif), ou proposition."""
    entree = adoptions.get(ref)
    if entree is None:
        return {"statut": "proposition", "test": "", "motif": ""}
    return entree


def references_inconnues(adoptions: dict[str, dict], refs_du_cahier: set[str]) -> list[str]:
    """Références déclarées adoptées qu'aucun cas du cahier courant ne porte."""
    return sorted(r for r in adoptions if not r.startswith("(ligne ") and r not in refs_du_cahier)
