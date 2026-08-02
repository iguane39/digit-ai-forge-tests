"""Registre des adaptateurs — un adaptateur = un couple (pan x technologie)."""

from forge_tests.adaptateurs import api, batch, data, fichiers, front, migrations, mutation

REGISTRE = {
    "front-react": front,
    "api-fastapi": api,
    "data-sql": data,
    "migrations-sql": migrations,
    "batch-python": batch,
    "fichiers-python": fichiers,
    "mutation-python": mutation,
}

PANS_ATTENDUS = ["front", "api", "data", "migrations", "batch", "fichiers", "back"]
