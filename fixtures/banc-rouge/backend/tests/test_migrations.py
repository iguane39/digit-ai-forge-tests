"""Suite Migrations."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

MIGRATIONS = sorted((Path(__file__).parent.parent / "migrations").glob("*.sql"))


def _haut(chemin: Path) -> str:
    texte = chemin.read_text(encoding="utf-8")
    haut, _, _ = texte.partition("-- +migrate Down")
    return haut.replace("-- +migrate Up", "")


@pytest.fixture()
def base(moteur):
    with moteur.begin() as cx:
        for table in ("ligne_commande", "commande_nouveau", "commande", "utilisateur"):
            cx.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    return moteur


def test_migrations_aller(base) -> None:
    for migration in MIGRATIONS:
        with base.begin() as cx:
            for instruction in [s.strip() for s in _haut(migration).split(";") if s.strip()]:
                cx.execute(text(instruction))
