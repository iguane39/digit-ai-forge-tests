"""Sonde d exécution Data — greffon pytest, installé de l EXTÉRIEUR du projet analysé.

Enregistre les violations de contraintes RÉELLEMENT levées par la base pendant la suite.
Remplace le recoupement textuel, qui comptait une contrainte pour exercée dès que son nom ou
sa colonne apparaissait dans un test attendant un rejet — un test pouvait donc « couvrir » une
contrainte en la mentionnant tout en violant une autre.

Ne modifie aucun fichier du projet : chargé par `pytest -p sonde_data`, il écoute l événement
`handle_error` de SQLAlchemy et écrit son relevé dans FORGE_TESTS_SONDE_DATA.

Deux points d observation, dans cet ordre :
  - SQLAlchemy (`before_cursor_execute` / `handle_error`) — instructions ET violations ;
  - `sqlite3` stdlib, en REPLI (`Connection.set_trace_callback`) — instructions seulement.
Sans ce repli, un backend écrit en `sqlite3` sans ORM voyait ses pans data et migrations
tomber à « exercé = 0 » sans que rien ne dise pourquoi (constaté sur le second produit réel).
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
from pathlib import Path

# RT-4 — le relevé était borné aux 4 000 DERNIÈRES instructions : un test de migrations tôt
# dans la suite pouvait sortir de la fenêtre et sa migration passer pour non exercée. Deux
# bornes remplacent la fenêtre glissante unique :
#   - par instruction : le seuil le plus exigeant d un consommateur est « vue DEUX fois »
#     (rejeu d une migration) ; au-delà de trois passages, une répétition n apprend plus rien ;
#   - globale, sur les seules instructions NON structurantes : le DDL, qui porte les
#     migrations, n est jamais évincé, quel que soit le volume de requêtes qui le suit.
PLAFOND_PAR_INSTRUCTION = 3
PLAFOND_GLOBAL = 4000
_DDL = ("create", "alter", "drop", "truncate")

MESSAGES: list[str] = []
# Relevé SÉPARÉ par point d observation. Sur un projet SQLAlchemy + SQLite les deux voient la
# même instruction : les fusionner la compterait DEUX fois et créditerait un « rejeu » de
# migration qui n a jamais eu lieu. SQLAlchemy fait foi dès qu il a vu quelque chose ; le
# repli ne sert que dans son silence.
INSTRUCTIONS: dict[str, list[str]] = {"sqlalchemy": [], "sqlite3": []}
_COMPTES: dict[tuple[str, str], int] = {}
_INSTRUMENTE = False


def _noter(instruction: object, source: str) -> None:
    """Retient une instruction envoyée au moteur, sous les deux plafonds ci-dessus."""
    texte = " ".join(str(instruction).split())[:400]
    if not texte:
        return
    vus = _COMPTES.get((source, texte), 0)
    if vus >= PLAFOND_PAR_INSTRUCTION:
        return
    _COMPTES[(source, texte)] = vus + 1
    INSTRUCTIONS[source].append(texte)


def _releve() -> tuple[list[str], list[str]]:
    """(instructions retenues, points d observation qui ont vu passer du SQL)."""
    for source in ("sqlalchemy", "sqlite3"):
        if INSTRUCTIONS[source]:
            return _borner(INSTRUCTIONS[source]), [source]
    return [], []


def _structurante(instruction: str) -> bool:
    return instruction.lstrip("( \t").lower().startswith(_DDL)


def _borner(instructions: list[str]) -> list[str]:
    """Sépare le DDL du reste : le DDL reste entier, le reste est borné par sa queue.

    L ordre du relevé n est lu par personne — les consommateurs y cherchent des sous-chaînes
    et y comptent des occurrences —, ce regroupement est donc sans effet sur le verdict.
    """
    structurantes = [i for i in instructions if _structurante(i)]
    autres = [i for i in instructions if not _structurante(i)]
    return structurantes + autres[-PLAFOND_GLOBAL:]


def _base_interne(args: tuple, kwargs: dict) -> bool:
    """La base de `coverage` n est pas celle du projet — la tracer noierait le relevé."""
    base = str(kwargs.get("database", args[0] if args else ""))
    fichier_coverage = os.environ.get("COVERAGE_FILE", "")
    if fichier_coverage and base.startswith(fichier_coverage):
        return True
    return os.path.basename(base).startswith(".coverage")


def _greffer_sqlalchemy() -> bool:
    try:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
    except Exception:  # noqa: BLE001 — projet sans SQLAlchemy : on passe au repli
        return False

    @event.listens_for(Engine, "handle_error")
    def _capter(contexte) -> None:  # noqa: ANN001
        original = getattr(contexte, "original_exception", None)
        if original is not None:
            MESSAGES.append(str(original))

    @event.listens_for(Engine, "before_cursor_execute")
    def _tracer(conn, curseur, instruction, parametres, contexte, executemany) -> None:  # noqa: ANN001, ARG001
        # Toute instruction REELLEMENT envoyee au moteur. Sert a savoir quelles tables sont
        # touchees et quelles migrations sont appliquees — deux faits qu on deduisait du texte.
        _noter(instruction, "sqlalchemy")

    return True


def _greffer_sqlite3() -> bool:
    """Repli : trace au niveau du pilote stdlib, pour les projets sans couche ORM.

    `Connection.set_trace_callback` est le point d observation officiel du module `sqlite3`.
    Il s arme PAR CONNEXION : on enveloppe donc `sqlite3.connect`, en mémoire dans le
    processus de test, sans toucher un seul fichier du projet audité.
    """
    try:
        import sqlite3
    except Exception:  # noqa: BLE001 — interpréteur sans sqlite3 : la sonde se tait
        return False
    origine = sqlite3.connect
    if getattr(origine, "__forge_tests__", False):
        return True

    @functools.wraps(origine)
    def connect_espionne(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        connexion = origine(*args, **kwargs)
        if not _base_interne(args, kwargs):
            # Jamais casser la suite du projet audité pour une sonde : un pilote exotique qui
            # refuse le rappel de trace fait taire la sonde, pas tomber l audit.
            with contextlib.suppress(Exception):
                connexion.set_trace_callback(lambda sql: _noter(sql, "sqlite3"))
        return connexion

    connect_espionne.__forge_tests__ = True
    sqlite3.connect = connect_espionne
    return True


def _instrumenter() -> None:
    global _INSTRUMENTE
    if _INSTRUMENTE:
        return
    _greffer_sqlalchemy()
    _greffer_sqlite3()
    _INSTRUMENTE = True


def pytest_load_initial_conftests(early_config, parser, args) -> None:  # noqa: ANN001, ARG001
    """Instrumente AVANT le chargement des conftests.

    Un `app/main.py` qui crée son schéma À L IMPORT (constaté sur le second produit réel) est
    importé par un `tests/conftest.py`, lui-même chargé avant `pytest_sessionstart` : greffer
    plus tard, c est manquer la création des tables.
    """
    _instrumenter()


def pytest_sessionstart(session) -> None:  # noqa: ANN001, ARG001
    """Seconde chance, si la greffe initiale n a pas eu lieu."""
    _instrumenter()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001, ARG001
    destination = os.environ.get("FORGE_TESTS_SONDE_DATA")
    if not destination:
        return
    instructions, sources = _releve()
    Path(destination).write_text(
        json.dumps(
            {
                "violations": sorted(set(MESSAGES)),
                "instructions": instructions,
                "sources": sources,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
