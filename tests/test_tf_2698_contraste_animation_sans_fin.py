"""TF-2698 — un texte porté par une animation CSS SANS FIN se juge à la page figée.

Fait remonté par factory-digit-ai-fr (retour du 15/11/2026, run forge-digit-ai-fr-20261114a) :
le pan `contraste` a compté bloquants quatre libellés d'animations infinies mesurés pendant leur
fondu, « projet » à 1,01:1 sur `/v2/`, « écrans » à 2,61:1, « agent » à 1,76:1, « charge » à
1,95:1. La note TF-2313 du pan disait déjà qu'une animation sans fin n'est pas attendue ; le
constat restait pourtant bloquant. Quatre actions de développement arbitrées à la main sur des
captures au repos.

Décision : la mesure se rejoue sur la page figée à son repos (animations sans fin annulées),
c'est elle qui juge ; ce que la boucle a montré en plus se nomme au non-jugé, « mesure en cours
de transition ».

Sens prouvés (navigateur réel, pages servies par un serveur local) :
  - ROUGE  — une page dont le style de repos est conforme (#000 sur #fff) et dont une animation
             sans fin passe par du gris très clair : l'ancien code rendait FAIL ;
  - VERT   — le même pan rend PASS, sans constat, et nomme l'écart lu pendant la boucle ;
  - CONTRE-ÉPREUVES — un texte dont le style de REPOS échoue reste bloquant même porté par une
             animation sans fin ; une page sans animation n'est pas changée ; un gel impossible
             est dit.
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from forge_tests import stabilite
from forge_tests.adaptateurs import contraste

playwright_api = pytest.importorskip("playwright.sync_api")

# Le style de repos tient 21:1 ; l'animation, elle, ne quitte JAMAIS un gris à 1,1:1 : la mesure en
# boucle est donc fautive à toute phase, sans dépendre de l'horloge du test.
PAGE_BOUCLE_CONFORME_AU_REPOS = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>t</title>
<style>
  @keyframes pale { from { color: #f4f4f4; } to { color: #f0f0f0; } }
  body { background: #ffffff; margin: 24px; font: 18px sans-serif; }
  #mot { color: #000000; animation: pale 2s ease-in-out infinite alternate; }
</style></head><body><p id="mot">projet</p></body></html>"""

# Le style de REPOS est déjà fautif (#eeeeee sur blanc) : l'animation n'y change rien.
PAGE_REPOS_FAUTIF = PAGE_BOUCLE_CONFORME_AU_REPOS.replace(
    "#mot { color: #000000;", "#mot { color: #eeeeee;"
)

PAGE_SANS_ANIMATION_FAUTIVE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>t</title>
<style>body { background: #ffffff; margin: 24px; font: 18px sans-serif; }
  #mot { color: #eeeeee; }</style></head><body><p id="mot">projet</p></body></html>"""

PAGE_FINIE_EN_COURS = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>t</title>
<style>
  @keyframes fondu { from { color: #000000; } to { color: #000000; } }
  body { background: #ffffff; font: 18px sans-serif; }
  #a { animation: fondu 1s linear 1; }
</style></head><body><p id="a">Bonjour</p></body></html>"""


class _Muet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # noqa: D102
        return


@pytest.fixture()
def serveur(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    fabrique = functools.partial(_Muet, directory=str(tmp_path))
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), fabrique)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield tmp_path, f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(scope="module")
def navigateur() -> Iterator[object]:
    with playwright_api.sync_playwright() as pw:
        try:
            lance = pw.chromium.launch()
        except Exception as erreur:  # noqa: BLE001 — pas de navigateur : fixture inapplicable
            pytest.skip(f"navigateur indisponible : {type(erreur).__name__}")
        try:
            yield lance
        finally:
            lance.close()


@pytest.fixture()
def page(navigateur) -> Iterator[object]:
    ouverte = navigateur.new_page()
    try:
        yield ouverte
    finally:
        ouverte.close()


def _parcours_reel(page, serveur, html: str):
    """Remplace `parcourir` : ouvre la vraie page dans le vrai navigateur, joue l'action du pan."""
    dossier, base = serveur
    (dossier / "page.html").write_text(html, encoding="utf-8")

    def parcourir(_cible, _routes, action, *, prefixe):
        page.goto(f"{base}/page.html", wait_until="networkidle")
        valeur, motif = action(page, "/")
        return ({"/": valeur} if valeur is not None else {}), ([motif] if motif else [])

    return parcourir


def _analyser(page, serveur, monkeypatch: pytest.MonkeyPatch, html: str):
    if contraste._mesure_js() is None:
        pytest.skip("socle de mesure du contraste absent (digit-ai-page-html)")
    monkeypatch.setattr(contraste.accessibilite, "routes_a_auditer", lambda _c: (["/"], "test"))
    monkeypatch.setattr(contraste, "parcourir", _parcours_reel(page, serveur, html))
    return contraste.analyser(Path("projet-factice"))


# --- Le défaut, puis sa correction ----------------------------------------------------------------
def test_la_premisse_la_mesure_en_boucle_est_fautive_a_toute_phase(page, serveur) -> None:
    """ROUGE (la prémisse) : sans gel, la mesure vive ouvre un constat sur un texte dont le style
    de repos est conforme. C'est ce que l'ancien code comptait bloquant."""
    if contraste._mesure_js() is None:
        pytest.skip("socle de mesure du contraste absent (digit-ai-page-html)")
    dossier, base = serveur
    (dossier / "page.html").write_text(PAGE_BOUCLE_CONFORME_AU_REPOS, encoding="utf-8")
    page.goto(f"{base}/page.html", wait_until="networkidle")
    brut = page.evaluate(contraste._mesure_js())
    assert [e["what"] for e in brut["v2_contrast"]] == ["p#mot « projet »"]


def test_le_pan_juge_la_page_figee_et_nomme_ce_que_la_boucle_a_montre(
    page, serveur, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VERT : #000 sur #fff au repos. PASS, aucun constat bloquant, l'écart lu en boucle NOMMÉ."""
    sortie = _analyser(page, serveur, monkeypatch, PAGE_BOUCLE_CONFORME_AU_REPOS)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert sortie.findings == []
    lignes = [ligne for ligne in sortie.non_juge if "lu pendant la boucle" in ligne]
    assert len(lignes) == 1
    assert "[/]" in lignes[0] and "projet" in lignes[0] and "SANS FIN" in lignes[0]
    assert "ratio 1." in lignes[0]  # le chiffre lu en boucle reste visible, rien n'est tu


def test_contre_epreuve_un_repos_fautif_reste_bloquant_meme_sous_animation(
    page, serveur, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le gel n'est pas un bouton « faire taire » : un texte illisible au repos échoue toujours."""
    sortie = _analyser(page, serveur, monkeypatch, PAGE_REPOS_FAUTIF)
    assert sortie.verdict == "FAIL"
    assert len(sortie.findings) == 1 and "projet" in sortie.findings[0].message
    assert sortie.findings[0].severite == "bloquant"
    assert not any("lu pendant la boucle" in ligne for ligne in sortie.non_juge)


def test_contre_epreuve_une_page_sans_animation_n_est_pas_changee(
    page, serveur, monkeypatch: pytest.MonkeyPatch
) -> None:
    sortie = _analyser(page, serveur, monkeypatch, PAGE_SANS_ANIMATION_FAUTIVE)
    assert sortie.verdict == "FAIL" and len(sortie.findings) == 1
    assert not any("lu pendant la boucle" in ligne for ligne in sortie.non_juge)


def test_une_animation_finie_n_est_pas_figee_par_ce_gel(page, serveur) -> None:
    """Le gel ne vise que les animations sans fin : une animation finie va à son terme."""
    dossier, base = serveur
    (dossier / "page.html").write_text(PAGE_FINIE_EN_COURS, encoding="utf-8")
    page.goto(f"{base}/page.html", wait_until="networkidle")
    assert stabilite.figer_animations_infinies(page) == 0


def test_le_gel_compte_les_animations_annulees(page, serveur) -> None:
    dossier, base = serveur
    (dossier / "page.html").write_text(PAGE_BOUCLE_CONFORME_AU_REPOS, encoding="utf-8")
    page.goto(f"{base}/page.html", wait_until="networkidle")
    assert stabilite.figer_animations_infinies(page) == 1
    assert page.evaluate("document.getAnimations().length") == 0
    assert page.evaluate("getComputedStyle(document.getElementById('mot')).color") == (
        "rgb(0, 0, 0)"
    )


# --- La réconciliation, sans navigateur ---------------------------------------------------------
def _ecart(what: str, detail: str = "ratio 1.01:1 < 4.5:1") -> dict:
    return {"what": what, "detail": detail}


def test_reconcilier_garde_le_verdict_de_la_page_figee() -> None:
    en_boucle = {"v2_contrast": [_ecart("a"), _ecart("b")], "unmeasured": [{"what": "x"}]}
    figee = {"v2_contrast": [_ecart("b", "ratio 2.0:1 < 4.5:1")], "unmeasured": []}
    sortie = contraste.reconcilier_mouvement(en_boucle, figee)
    assert [e["what"] for e in sortie["v2_contrast"]] == ["b"]
    assert sortie["v2_contrast"][0]["detail"] == "ratio 2.0:1 < 4.5:1"  # le chiffre du repos
    assert [e["what"] for e in sortie["en_mouvement"]] == ["a"]


def test_reconcilier_sans_ecart_en_boucle_ne_nomme_rien() -> None:
    sortie = contraste.reconcilier_mouvement(
        {"v2_contrast": [], "unmeasured": []}, {"v2_contrast": [], "unmeasured": []}
    )
    assert sortie["en_mouvement"] == []


@pytest.mark.parametrize("illisible", [None, "boom", []])
def test_reconcilier_ne_rien_assouplir_si_une_lecture_est_illisible(illisible) -> None:
    lisible = {"v2_contrast": [_ecart("a")], "unmeasured": []}
    assert contraste.reconcilier_mouvement(lisible, illisible) is lisible
    assert contraste.reconcilier_mouvement(illisible, lisible) is lisible


def test_un_gel_impossible_est_dit_et_la_mesure_en_boucle_est_gardee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page qui ne répond plus au gel : rien n'est assoupli, et le non-jugé le DIT."""
    appels: list[str] = []

    class Page:
        def evaluate(self, script, *_a):
            appels.append("evaluate")
            if script == "MESURE":
                return {"v2_contrast": [_ecart("p « x »")], "unmeasured": []}
            if script is stabilite._SCRIPT:
                return {"restantes": 0, "infinies": 0, "ms": 1}
            raise RuntimeError("page fermee")

        def wait_for_timeout(self, _ms):
            return None

    monkeypatch.setattr(contraste, "_mesure_js", lambda: "MESURE")
    monkeypatch.setattr(contraste.accessibilite, "routes_a_auditer", lambda _c: (["/"], "test"))

    def parcourir(_cible, _routes, action, *, prefixe):
        valeur, motif = action(Page(), "/")
        return {"/": valeur}, ([motif] if motif else [])

    monkeypatch.setattr(contraste, "parcourir", parcourir)
    sortie = contraste.analyser(Path("projet-factice"))
    assert sortie.verdict == "FAIL" and len(sortie.findings) == 1
    assert any("n'ont pas pu etre figees" in ligne for ligne in sortie.non_juge)
