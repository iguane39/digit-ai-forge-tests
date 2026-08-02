"""Sonde d exécution Data — greffon pytest, installé de l EXTÉRIEUR du projet analysé.

Enregistre les violations de contraintes RÉELLEMENT levées par la base pendant la suite.
Remplace le recoupement textuel, qui comptait une contrainte pour exercée dès que son nom ou
sa colonne apparaissait dans un test attendant un rejet — un test pouvait donc « couvrir » une
contrainte en la mentionnant tout en violant une autre.

Ne modifie aucun fichier du projet : chargé par `pytest -p sonde_data`, il écoute l événement
`handle_error` de SQLAlchemy et écrit son relevé dans FORGE_TESTS_SONDE_DATA.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MESSAGES: list[str] = []
INSTRUCTIONS: list[str] = []


def pytest_sessionstart(session) -> None:  # noqa: ANN001, ARG001
    try:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
    except Exception:  # noqa: BLE001 — projet sans SQLAlchemy : la sonde se tait
        return

    @event.listens_for(Engine, "handle_error")
    def _capter(contexte) -> None:  # noqa: ANN001
        original = getattr(contexte, "original_exception", None)
        if original is not None:
            MESSAGES.append(str(original))

    @event.listens_for(Engine, "before_cursor_execute")
    def _tracer(conn, curseur, instruction, parametres, contexte, executemany) -> None:  # noqa: ANN001, ARG001
        # Toute instruction REELLEMENT envoyee au moteur. Sert a savoir quelles tables sont
        # touchees et quelles migrations sont appliquees — deux faits qu on deduisait du texte.
        INSTRUCTIONS.append(" ".join(str(instruction).split())[:400])


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001, ARG001
    destination = os.environ.get("FORGE_TESTS_SONDE_DATA")
    if not destination:
        return
    Path(destination).write_text(
        json.dumps(
            {"violations": sorted(set(MESSAGES)), "instructions": INSTRUCTIONS[-4000:]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
