"""TF-2100 — la capture DOM d une mire ne laisse plus fuiter le jeton CSRF.

Le pan visuel ecrit ses captures sous `<cible>/.visuel/<route>.html` dans l arbre du projet
audite. La capture de la mire portait le jeton CSRF (champ cache) et les metas a jeton : le
balayage de secrets du PRODUIT accusait alors, lui, un fichier que la FORGE avait depose. On
caviarde a la source la valeur des champs caches / a jeton et des metas a jeton avant d ecrire —
un champ cache n a pas de representation visuelle, le diff visuel reste donc intact (et se
stabilise meme, un jeton changeant a chaque rendu). Classe partagee avec forge-websec.

Joue contre un vrai navigateur : la capture passe par le MEME point d ecriture que les deux pans
(accessibilite et visuel), `_capturer_une_route`.
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

from forge_tests.adaptateurs import accessibilite

_HIDDEN = "HIDDEN-SECRET-9d8e7f6a5c4b"
_META = "META-SECRET-7f3a9c2e1b2d"
_MIRE = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Mire</title>
<meta name="csrf-token" content="{_META}"></head>
<body><form method="post" action="/connexion">
  <input type="hidden" name="csrf_token" value="{_HIDDEN}">
  <input name="identifiant" autocomplete="username">
  <input type="password" name="mdp">
  <button type="submit">Entrer</button>
</form></body></html>"""


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


def test_capture_de_mire_ne_laisse_pas_le_jeton(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    site = tmp_path / "site"
    site.mkdir()
    (site / "mire.html").write_text(_MIRE, encoding="utf-8")
    dossier = tmp_path / ".visuel"
    dossier.mkdir()
    with _servir(site) as base, playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        try:
            fichier, motif = accessibilite._capturer_une_route(
                navigateur.new_page(), base, "/mire.html", dossier
            )
        finally:
            navigateur.close()
    assert fichier is not None, motif
    contenu = fichier.read_text(encoding="utf-8")
    # AVANT le correctif : `page.content()` ecrit brut, les deux jetons fuitaient dans le fichier.
    assert _HIDDEN not in contenu, "le jeton du champ cache a fuite dans la capture"
    assert _META not in contenu, "le jeton de la meta a fuite dans la capture"
    assert "forge-tests-caviarde" in contenu, "le caviardage n a pas eu lieu"
    # Le champ identifiant, lui, reste present : on caviarde la VALEUR, pas la structure.
    assert 'name="identifiant"' in contenu or "name=identifiant" in contenu
