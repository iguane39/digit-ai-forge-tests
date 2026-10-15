"""TF-1807, TF-1809, TF-1810 — la recette 404 était inopérante sur un produit monolingue, sans
sitemap, ou servi en application monopage.

Faits remontés par Produit-83 (lot 20261015b, ledger seq 159, 175, 176), à l étape MEP :
  - RE-8 (TF-1807) : `--prefixes` était OBLIGATOIRE, même sans préfixe de langue. Un site
    monolingue servi à la racine ne pouvait pas jouer M-9 ;
  - RE-10 (TF-1809) : un produit SANS sitemap (le sitemap rend 404) sortait NON_MESURABLE,
    exit 2, alors que tous les autres cas passaient. Un sitemap absent ne liste rien : le cas
    est sans objet, pas non mesuré ;
  - RE-11 (TF-1810) : le HTML servi d une application monopage n a pas de `<nav>` (le menu est
    rendu par le script). Le « même gabarit » restait non mesurable. La recette reconnaît
    désormais la coquille d une monopage et compare la 404 à cette coquille.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "recette"))

import quatre_cent_quatre as recette  # noqa: E402

NAV = '<nav><a href="/">Accueil</a><a href="/carte">Carte</a></nav>'


def _page(corps: str, noindex: bool = False, lang: str = "fr") -> bytes:
    robots = '<meta name="robots" content="noindex">' if noindex else ""
    return (f'<!doctype html><html lang="{lang}"><head><title>t</title>{robots}</head>'
            f"<body>{corps}</body></html>").encode()


def _coquille(bundle: str = "/assets/index-4f2a.js", noindex: bool = False) -> bytes:
    return _page(f'<div id="root"></div><script type="module" src="{bundle}"></script>'
                 '<link rel="stylesheet" href="/assets/index-4f2a.css">', noindex=noindex)


class _Poignee(http.server.BaseHTTPRequestHandler):
    mode = "monolingue"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _envoyer(self, code: int, corps: bytes, type_contenu: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self) -> None:  # noqa: N802
        chemin = self.path.split("?")[0]
        spa = self.mode.startswith("spa")
        if chemin == "/sitemap.xml":
            if self.mode == "monolingue":
                self._envoyer(200, b"<urlset><loc>http://h/</loc></urlset>", "application/xml")
            else:
                self._envoyer(404, b"not found", "text/plain")
            return
        if chemin == "/":
            self._envoyer(200, _coquille() if spa else _page(NAV), "text/html; charset=utf-8")
            return
        if chemin.endswith((".png", ".js")):
            self._envoyer(404, b"not found", "text/plain")
            return
        if self.mode == "spa":
            self._envoyer(404, _coquille(noindex=True), "text/html; charset=utf-8")
        elif self.mode == "spa-autre-coquille":
            self._envoyer(404, _page("<p>Introuvable</p>", noindex=True), "text/html")
        else:
            self._envoyer(404, _page(NAV + "<p>Introuvable</p>", noindex=True), "text/html")


@pytest.fixture
def serveur(request: pytest.FixtureRequest) -> Iterator[str]:
    poignee = type("Poignee", (_Poignee,), {"mode": request.param})
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), poignee) as srv:
        srv.daemon_threads = True
        fil = threading.Thread(target=srv.serve_forever, daemon=True)
        fil.start()
        try:
            yield f"http://127.0.0.1:{srv.server_address[1]}"
        finally:
            srv.shutdown()
            fil.join(timeout=5)


# --- TF-1807 : sans préfixe, la racine se sonde dans la langue que l accueil déclare ----------
@pytest.mark.parametrize("serveur", ["monolingue"], indirect=True)
def test_site_monolingue_sans_prefixes_rend_le_code_0(
    serveur: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = recette.main(["quatre_cent_quatre.py", serveur])
    sortie = capsys.readouterr().out
    assert code == 0, sortie
    assert '"prefixes": [\n  ""\n ]' in sortie or '"prefixes": [""]' in sortie.replace(" ", "")


# --- TF-1809 : un sitemap qui rend 404 est sans objet, et ne bloque pas le PASS ---------------
def test_sitemap_absent_en_404_est_sans_objet() -> None:
    verdict = recette.juger_sitemap(
        {"url": "https://s/sitemap.xml", "code": 404, "corps": "", "entetes": {}}, [], [])
    assert verdict["verdict"] == "SANS_OBJET"
    assert recette.synthetiser([{"verdict": "PASS"}, verdict])["verdict"] == "PASS"
    assert recette.synthetiser([verdict])["verdict"] == "NON_MESURABLE"


# --- TF-1810 : la coquille d une monopage sert de référence au « même gabarit » ----------------
@pytest.mark.parametrize("serveur", ["spa"], indirect=True)
def test_monopage_dont_la_404_sert_la_meme_coquille_passe(serveur: str) -> None:
    rapport = recette.jouer(serveur, [], delai=5)
    assert rapport["verdict"] == "PASS", rapport["cas"]
    cas = next(c for c in rapport["cas"] if c["cas"] == "adresse-inconnue")
    assert "monopage" in cas["motif"]
    assert any(c["cas"] == "sitemap" and c["verdict"] == "SANS_OBJET" for c in rapport["cas"])


@pytest.mark.parametrize("serveur", ["spa-autre-coquille"], indirect=True)
def test_monopage_dont_la_404_perd_la_coquille_est_refusee(serveur: str) -> None:
    rapport = recette.jouer(serveur, [], delai=5)
    assert rapport["verdict"] == "FAIL"
    cas = next(c for c in rapport["cas"] if c["cas"] == "adresse-inconnue")
    assert cas["verdict"] == "FAIL"
    assert "coquille" in cas["motif"]
