"""Registre des adaptateurs — un adaptateur = un couple (pan x technologie)."""

from forge_tests.adaptateurs import (
    accessibilite,
    api,
    batch,
    clavier,
    contraste,
    data,
    fichiers,
    front,
    i18n,
    interface,
    migrations,
    mutation,
    prompts,
    qualif,
    securite,
    visuel,
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
    "prompts-statique": prompts,
    "qualif-navigateur": qualif,
    "securite-oracles": securite,
    "accessibilite-a11y": accessibilite,
    # TF-0409 (O3) : deux familles que le parc DECLARAIT non couvertes. Le contraste avait
    # une mesure existante et jamais cablee (render_page.py V2) ; la navigation clavier
    # n'avait aucun oracle du tout.
    "contraste-wcag": contraste,
    "clavier-focus": clavier,
    "visuel-golden": visuel,
    "i18n-build-servi": i18n,
}

PANS_ATTENDUS = [
    "front", "interface", "api", "data", "migrations", "batch", "fichiers", "back", "securite",
    "accessibilite", "contraste", "clavier", "visuel", "qualif", "prompts", "i18n",
]
