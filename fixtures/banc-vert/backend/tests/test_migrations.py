"""Suite Migrations couvrante : les 3 migrations à l aller, au retour, et rejouées."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = sorted((Path(__file__).parent.parent / "migrations").glob("*.sql"))


def _sections(chemin: Path) -> tuple[str, str]:
    texte = chemin.read_text(encoding="utf-8")
    haut, _, bas = texte.partition("-- +migrate Down")
    return haut.replace("-- +migrate Up", ""), bas


def _appliquer(cx: sqlite3.Connection, sql: str) -> None:
    cx.executescript(sql)


@pytest.fixture()
def cx() -> sqlite3.Connection:
    connexion = sqlite3.connect(":memory:")
    yield connexion
    connexion.close()


def test_les_trois_migrations_existent() -> None:
    assert [m.name for m in MIGRATIONS] == [
        "001_socle.sql",
        "002_statut_commande.sql",
        "003_index_email.sql",
    ]


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: m.name)
def test_migration_aller(cx: sqlite3.Connection, migration: Path) -> None:
    for precedente in MIGRATIONS:
        if precedente == migration:
            break
        _appliquer(cx, _sections(precedente)[0])
    _appliquer(cx, _sections(migration)[0])


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: m.name)
def test_migration_retour(cx: sqlite3.Connection, migration: Path) -> None:
    for precedente in MIGRATIONS:
        _appliquer(cx, _sections(precedente)[0])
        if precedente == migration:
            break
    _appliquer(cx, _sections(migration)[1])


def test_rejeu_sur_base_peuplee(cx: sqlite3.Connection) -> None:
    for migration in MIGRATIONS:
        _appliquer(cx, _sections(migration)[0])
    cx.execute("INSERT INTO utilisateur (id, email, mot_de_passe_hash) VALUES (1, 'a@b.fr', 'h')")
    cx.commit()
    # Retour complet puis rejeu intégral : la base doit se reconstruire sans erreur.
    for migration in reversed(MIGRATIONS):
        _appliquer(cx, _sections(migration)[1])
    for migration in MIGRATIONS:
        _appliquer(cx, _sections(migration)[0])
