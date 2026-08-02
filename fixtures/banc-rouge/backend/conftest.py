"""Environnement de test du banc — base PostgreSQL ephemere.

Le passage de SQLite a PostgreSQL n est pas cosmetique : SQLite ne nomme pas la contrainte
violee dans « FOREIGN KEY constraint failed ». Aucun oracle ne pouvait donc attribuer une
violation de cle etrangere. PostgreSQL nomme TOUTES ses contraintes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session")
def moteur():
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as conteneur:
        yield create_engine(conteneur.get_connection_url())
