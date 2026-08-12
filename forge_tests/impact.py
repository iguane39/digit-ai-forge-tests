"""Sélection par impact de diff (Test Impact Analysis) — TF-0104, sous-item 1/4.

`--reprendre` rejoue déjà ce qui n était pas vert, mais au grain du PAN, jamais au grain du
changement de commit : une correction d une ligne dans `backend/app/models.py` rejoue tout le
pan `data`, jamais moins. La pratique JiTTests (Meta, 2026) sélectionne au grain du test à
partir du diff — ici, faute d un graphe fichier→test dans le framework, la granularité
raisonnable est le PAN : c est l unité qu un adaptateur sait déjà (re)lancer (RT-6b).

Loi de ce module, identique à celle du générateur : **il ne réduit la sélection que quand il
est SÛR de ne rien taire.** Un fichier changé qui ne correspond à AUCUN préfixe connu de la
cartographie ne doit jamais aboutir à « ce pan n est pas concerné » — il fait retomber sur
l audit COMPLET, avec le motif explicite. Une git indisponible fait de même. Réduire la
sélection à tort serait réintroduire, à l étage de l ORCHESTRATION, le silence que Forge Tests
existe pour interdire à l étage de la MESURE.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

NON_JUGE = [
    "impact : la cartographie chemin -> pan est DECLAREE (prefixes de repertoires connus), pas "
    "dérivée d un graphe d imports reel — un fichier qui ne matche aucun prefixe fait retomber "
    "sur l audit COMPLET plutot que de deviner",
    "impact : la granularite est le PAN, pas le test individuel — un seul fichier change dans "
    "backend/app/ rejoue le pan api en entier, comme une reprise",
]

# Prefixe de chemin (relatif a la racine du projet AUDITE, separateurs `/`) -> pan impacte.
# Ordre significatif : le premier prefixe qui matche l emporte (le plus specifique doit
# precéder le plus general).
CARTOGRAPHIE: tuple[tuple[str, str], ...] = (
    ("backend/migrations/", "migrations"),
    ("backend/alembic.ini", "migrations"),
    ("backend/app/alembic/", "migrations"),
    ("backend/alembic/", "migrations"),
    ("alembic/", "migrations"),
    ("backend/app/db/", "data"),
    ("backend/app/models.py", "data"),
    ("backend/app/batch", "batch"),
    ("backend/app/worker", "batch"),
    ("backend/app/", "api"),
    ("backend/tests/", "back"),
    ("frontend/src/", "front"),
    ("frontend/tests/", "front"),
)


def fichiers_changes(cible: Path, depuis: str = "HEAD") -> list[str] | None:
    """Fichiers modifiés depuis `depuis`, chemins relatifs à `cible`. None si indisponible.

    None n est pas « aucun changement » : c est « impossible à mesurer ici » (pas de dépôt git,
    référence inconnue, `git` absent) — l appelant doit alors auditer COMPLET, jamais rien.
    """
    try:
        resultat = subprocess.run(
            ["git", "diff", "--name-only", depuis],
            cwd=cible,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultat.returncode != 0:
        return None
    return [ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip()]


def pans_impactes(fichiers: list[str]) -> tuple[set[str], set[str]]:
    """(pans impactés, fichiers hors cartographie) — les seconds interdisent toute réduction."""
    impactes: set[str] = set()
    orphelins: set[str] = set()
    for brut in fichiers:
        chemin = brut.replace("\\", "/")
        trouve = False
        for prefixe, pan in CARTOGRAPHIE:
            if chemin.startswith(prefixe):
                impactes.add(pan)
                trouve = True
                break
        if not trouve:
            orphelins.add(chemin)
    return impactes, orphelins


def selection(cible: Path, pans_attendus: list[str], depuis: str = "HEAD") -> dict:
    """Décide quels pans rejouer depuis un diff — ou déclare pourquoi la réduction est refusée.

    Retour : `{"pans": [...], "mode": "cible"|"complet"|"aucun-changement", "motif": str}`.
    Seul `mode == "cible"` réduit réellement le travail ; les deux autres rendent la LISTE
    COMPLETE (ou vide), jamais une réduction non prouvée.
    """
    fichiers = fichiers_changes(cible, depuis)
    if fichiers is None:
        return {
            "pans": list(pans_attendus),
            "mode": "complet",
            "motif": f"diff git indisponible depuis {depuis} — audit complet par prudence",
        }
    if not fichiers:
        return {
            "pans": [],
            "mode": "aucun-changement",
            "motif": f"aucun fichier modifie depuis {depuis}",
        }
    impactes, orphelins = pans_impactes(fichiers)
    if orphelins:
        exemples = ", ".join(sorted(orphelins)[:5])
        suffixe = "…" if len(orphelins) > 5 else ""
        return {
            "pans": list(pans_attendus),
            "mode": "complet",
            "motif": (
                f"{len(orphelins)} fichier(s) modifie(s) hors cartographie connue "
                f"({exemples}{suffixe}) — reduire la selection serait taire un impact possible"
            ),
        }
    retenus = [p for p in pans_attendus if p in impactes]
    return {
        "pans": retenus,
        "mode": "cible",
        "motif": (
            f"{len(fichiers)} fichier(s) modifie(s) depuis {depuis} -> "
            f"{len(retenus)} pan(s) impacte(s) : {', '.join(retenus) or 'aucun'}"
        ),
    }
