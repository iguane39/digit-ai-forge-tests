"""Suite Migrations couvrante : les 3 migrations a l aller, au retour, et rejouees.

Executees sur le moteur REEL (PostgreSQL ephemere) : c est la seule facon pour un oracle de
constater qu une migration a ete appliquee, et dans quel sens.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

MIGRATIONS = sorted((Path(__file__).parent.parent / "migrations").glob("*.sql"))


def _sections(chemin: Path) -> tuple[str, str]:
    texte = chemin.read_text(encoding="utf-8")
    haut, _, bas = texte.partition("-- +migrate Down")
    return haut.replace("-- +migrate Up", ""), bas


def _appliquer(moteur, sql: str) -> None:
    with moteur.begin() as cx:
        for instruction in [s.strip() for s in sql.split(";") if s.strip()]:
            cx.execute(text(instruction))


@pytest.fixture()
def base(moteur):
    _nettoyer(moteur)
    yield moteur
    _nettoyer(moteur)


def _nettoyer(moteur) -> None:
    with moteur.begin() as cx:
        for table in ("ligne_commande", "commande_nouveau", "commande_ancien", "commande", "utilisateur"):
            cx.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))


def test_les_trois_migrations_existent() -> None:
    assert [m.name for m in MIGRATIONS] == [
        "001_socle.sql",
        "002_statut_commande.sql",
        "003_index_email.sql",
    ]


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: m.name)
def test_migration_aller(base, migration: Path) -> None:
    for precedente in MIGRATIONS:
        if precedente == migration:
            break
        _appliquer(base, _sections(precedente)[0])
    _appliquer(base, _sections(migration)[0])


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: m.name)
def test_migration_retour(base, migration: Path) -> None:
    for precedente in MIGRATIONS:
        _appliquer(base, _sections(precedente)[0])
        if precedente == migration:
            break
    _appliquer(base, _sections(migration)[1])


def test_rejeu_sur_base_peuplee(base) -> None:
    for migration in MIGRATIONS:
        _appliquer(base, _sections(migration)[0])
    with base.begin() as cx:
        cx.execute(text("INSERT INTO utilisateur (email, mot_de_passe_hash) VALUES ('a@b.fr','h')"))
    # Retour complet puis rejeu integral : la base doit se reconstruire sans erreur.
    for migration in reversed(MIGRATIONS):
        _appliquer(base, _sections(migration)[1])
    for migration in MIGRATIONS:
        _appliquer(base, _sections(migration)[0])
