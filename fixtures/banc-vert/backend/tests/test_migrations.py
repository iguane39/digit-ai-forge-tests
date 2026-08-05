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


def _sans_commentaires(sql: str) -> str:
    """Retire les commentaires `--` et `/* */`, littéraux `'...'` préservés.

    Un runner de migrations qui découpe sur `;` AVANT de filtrer les commentaires envoie au
    moteur un fragment vide dès qu un commentaire porte un point-virgule. C est exactement le
    piège corrigé côté auditeur (RT-8) : filtrer d abord, découper ensuite.
    """
    morceaux, i, n = [], 0, len(sql)
    while i < n:
        if sql[i] == "'":
            j = sql.find("'", i + 1)
            j = n if j == -1 else j + 1
            morceaux.append(sql[i:j])
            i = j
        elif sql.startswith("--", i):
            saut = sql.find("\n", i)
            morceaux.append("\n")
            i = n if saut == -1 else saut + 1
        elif sql.startswith("/*", i):
            fin = sql.find("*/", i + 2)
            morceaux.append(" ")
            i = n if fin == -1 else fin + 2
        else:
            morceaux.append(sql[i])
            i += 1
    return "".join(morceaux)


def _instructions(sql: str) -> list[str]:
    propre = _sans_commentaires(sql)
    morceaux, courante, i, n = [], [], 0, len(propre)
    while i < n:
        if propre[i] == "'":
            j = propre.find("'", i + 1)
            j = n if j == -1 else j + 1
            courante.append(propre[i:j])
            i = j
        elif propre[i] == ";":
            morceaux.append("".join(courante))
            courante = []
            i += 1
        else:
            courante.append(propre[i])
            i += 1
    morceaux.append("".join(courante))
    return [m.strip() for m in morceaux if m.strip()]


def _appliquer(moteur, sql: str) -> None:
    with moteur.begin() as cx:
        for instruction in _instructions(sql):
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
