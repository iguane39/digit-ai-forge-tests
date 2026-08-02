"""Suite Migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = sorted((Path(__file__).parent.parent / "migrations").glob("*.sql"))


def _haut(chemin: Path) -> str:
    texte = chemin.read_text(encoding="utf-8")
    haut, _, _ = texte.partition("-- +migrate Down")
    return haut.replace("-- +migrate Up", "")


@pytest.fixture()
def cx() -> sqlite3.Connection:
    connexion = sqlite3.connect(":memory:")
    yield connexion
    connexion.close()


def test_migrations_aller(cx: sqlite3.Connection) -> None:
    for migration in MIGRATIONS:
        cx.executescript(_haut(migration))
