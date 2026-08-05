"""Registre des adaptateurs — un adaptateur = un couple (pan x technologie)."""

from forge_tests.adaptateurs import (
    accessibilite, api, batch, data, fichiers, front, interface, migrations, mutation,
    securite, visuel,
)

REGISTRE = {
    "front-react": front,
    "interface-statique": interface,
    "api-fastapi": api,
    "data-sql": data,
    "migrations-sql": migrations,
    "batch-python": batch,
    "fichiers-python": fichiers,
    "mutation-python": mutation,
    "securite-oracles": securite,
    "accessibilite-a11y": accessibilite,
    "visuel-golden": visuel,
}

PANS_ATTENDUS = [
    "front", "interface", "api", "data", "migrations", "batch", "fichiers", "back", "securite",
    "accessibilite", "visuel",
]
