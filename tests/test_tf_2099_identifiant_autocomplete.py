"""TF-2099 — un champ identifiant sans attribut type ni nom anglais est reconnu.

Sur une mire `<input name=identifiant autocomplete=username>` (pas de `type`, nom francais), le
selecteur d identifiant ne trouvait rien : session jamais ouverte, parcours reste anonyme avec
un compte pourtant valide. Le selecteur reconnait desormais `input[autocomplete=username i]` et
`input:not([type])`. Joue contre un vrai navigateur : seul le bouton du formulaire, rempli des
deux champs, pose le cookie de session.

Corollaire (Git Bash convertit `/connexion` en chemin Windows) : les routes restent des chaines
Python ici, aucune conversion de shell.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from forge_tests.adaptateurs import qualif

_MIRE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Mire</title></head>
<body><main><form id="connexion" onsubmit="event.preventDefault(); ouvrir();">
  <input name="identifiant" autocomplete="username">
  <input type="password" name="mdp">
  <button type="submit">Se connecter</button>
</form></main>
<script>function ouvrir(){document.cookie='session=ouverte; path=/';
location.href='/accueil.html';}</script></body></html>"""

_ACCUEIL = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Accueil</title>
</head><body><h1>Bienvenue</h1></body></html>"""


class _ServeurMuet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return


@contextlib.contextmanager
def _servir(dossier: Path) -> Iterator[str]:
    fabrique = functools.partial(_ServeurMuet, directory=str(dossier))
    serveur = socketserver.ThreadingTCPServer(("127.0.0.1", 0), fabrique)
    serveur.daemon_threads = True
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


@pytest.fixture(scope="module")
def instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    racine = tmp_path_factory.mktemp("banc-mire-2099")
    (racine / "mire.html").write_text(_MIRE, encoding="utf-8")
    (racine / "accueil.html").write_text(_ACCUEIL, encoding="utf-8")
    with _servir(racine) as url:
        yield url


def _connecter(instance: str, route: str) -> dict:
    playwright = pytest.importorskip("playwright.sync_api")
    config = {"base": instance, "connexion": route, "login": "audit-2099", "mdp": "secret"}
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        try:
            return qualif._connecter(navigateur.new_page(), config)
        finally:
            navigateur.close()


def test_identifiant_sans_type_ni_nom_anglais_ouvre_la_session(instance: str) -> None:
    # AVANT le correctif : « champ mot de passe present, aucun champ identifiant » → sans mire.
    resultat = _connecter(instance, "/mire.html")
    assert resultat["etat"] == qualif.SESSION_OUVERTE, resultat
