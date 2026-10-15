"""TF-1768 / TF-1790 — la mire du pan qualif était soumise par le premier bouton du document.

Fait remonté deux fois le 15/10/2026 : Produit-82 (lot 20261015b, RT-17, ledger seq 76) et
Produit-83 (lot 20261015b, RE-2, ledger seq 121). Le sélecteur de soumission
« button[type=submit], input[type=submit], button », lu sur le document, rendait le premier
bouton dans l ordre du DOM : la bascule de thème de l en-tête (`type=button`), placée avant le
formulaire. Aucune session ouverte, 5 routes jugées refusées, alors que le même compte se
connecte dans un navigateur.

Joué contre un vrai navigateur : la page de mire porte la bascule de thème AVANT le formulaire.
Seul le bouton du formulaire pose le cookie de session.
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

_ENTETE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Mire</title></head>
<body><header><button id="theme" type="button"
  onclick="document.body.dataset.theme='sombre'">Thème</button></header>"""

_MIRE_FORMULAIRE = _ENTETE + """
<main><form id="connexion" onsubmit="event.preventDefault(); ouvrir();">
  <input type="email" name="email"><input type="password" name="mdp">
  <button type="button" onclick="void 0">Afficher le mot de passe</button>
  <button type="submit">Se connecter</button>
</form></main>
<script>function ouvrir(){document.cookie='session=ouverte; path=/';
location.href='/accueil.html';}</script></body></html>"""

# Une SPA sans <form> : le bouton de la carte est `type=button`, câblé en JavaScript.
_MIRE_SANS_FORM = _ENTETE + """
<main><div class="carte"><input type="text" name="login"><input type="password" name="mdp">
  <button type="button" onclick="ouvrir()">Se connecter</button></div></main>
<script>function ouvrir(){document.cookie='session=ouverte; path=/';
location.href='/accueil.html';}</script></body></html>"""

_ACCUEIL = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Accueil</title>
</head><body><h1>Bienvenue</h1></body></html>"""


class _ServeurMuet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # noqa: D102
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
    racine = tmp_path_factory.mktemp("banc-mire")
    (racine / "formulaire.html").write_text(_MIRE_FORMULAIRE, encoding="utf-8")
    (racine / "sans-form.html").write_text(_MIRE_SANS_FORM, encoding="utf-8")
    (racine / "accueil.html").write_text(_ACCUEIL, encoding="utf-8")
    with _servir(racine) as url:
        yield url


def _connecter(instance: str, route: str) -> dict:
    playwright = pytest.importorskip("playwright.sync_api")
    config = {"base": instance, "connexion": route, "login": "a@b.test", "mdp": "secret"}
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        try:
            page = navigateur.new_page()
            return qualif._connecter(page, config)
        finally:
            navigateur.close()


def test_mire_a_formulaire_soumise_par_son_bouton_submit_pas_par_la_bascule(
    instance: str,
) -> None:
    resultat = _connecter(instance, "/formulaire.html")
    assert resultat["etat"] == qualif.SESSION_OUVERTE, resultat
    assert "session" in resultat["preuve"]


def test_mire_sans_form_soumise_par_le_bouton_le_plus_proche_du_mot_de_passe(
    instance: str,
) -> None:
    resultat = _connecter(instance, "/sans-form.html")
    assert resultat["etat"] == qualif.SESSION_OUVERTE, resultat


def test_doublure_sans_evaluation_retombe_sur_le_selecteur_du_document() -> None:
    """Le dernier recours tient : une poignée qui ne sait pas s évaluer ne perd pas le bouton."""

    class _Page:
        def wait_for_selector(self, selecteur: str, **_kw: object) -> str:
            return f"bouton du document ({selecteur})"

    assert qualif._bouton_de_soumission(_Page(), object()).startswith("bouton du document")
