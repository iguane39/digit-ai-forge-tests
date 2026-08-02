"""Registre des adaptateurs — un adaptateur = un couple (pan x technologie)."""

from forge_tests.adaptateurs import (
    api, batch, data, fichiers, front, migrations, mutation, securite,
)

REGISTRE = {
    "front-react": front,
    "api-fastapi": api,
    "data-sql": data,
    "migrations-sql": migrations,
    "batch-python": batch,
    "fichiers-python": fichiers,
    "mutation-python": mutation,
    "securite-oracles": securite,
}

PANS_ATTENDUS = [
    "front", "api", "data", "migrations", "batch", "fichiers", "back", "securite",
]
