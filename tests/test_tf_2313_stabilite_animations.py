"""TF-2313 — un rendu se juge APRÈS la fin des animations finies, jamais au milieu d'une transition.

Fait remonté par Produit-84 (09/11/2026, chaîne de dev 42686921354, onglet dashboard) : axe-core a
rendu un contraste de 1,53 sur un toast de 12 px pris au milieu de son fondu de 0,25 s ; affiché, il
tient 7,16:1 (calculé). Le même banc passait sur le poste. En attendant la fin des animations
finies (`document.getAnimations()`, `iterations` infini ignoré), les 24 contrôles passaient.

Décision du 10/11/2026 : le pan accessibilité attend la stabilité des animations finies (5 s au
plus) avant de juger, avec fixture ; la part `oracle-a11y` est au lot FA1.

Ce que le code montre : le pan `accessibilite` de cette forge ne lance pas axe lui-même, il écrit le
DOM rendu de chaque route (`_capturer_une_route`) et le donne à `oracle-a11y` ; la mesure vive d'un
contraste, elle, est faite par le pan `contraste` sur la page ouverte. Les deux lisent un rendu
sans attendre autre chose que `networkidle` et 150 ms. L'attente est donc posée à ces deux endroits.

Sens prouvés (navigateur réel, pages servies par un serveur local) :
  - ROUGE  — sur l'ancien code, une couleur en transition de 3 s se lit à mi-chemin : le pan
             `contraste` rend FAIL sur une page dont la couleur FINALE est conforme, et la capture
             du pan `accessibilite` est écrite avant la fin de l'animation ;
  - VERT   — l'attente rend la couleur finale, le pan `contraste` rend PASS, la capture porte l'état
             final ;
  - CONTRE-ÉPREUVES — une animation sans fin n'est pas attendue (la page rend la main vite), une
             animation en pause non plus, le plafond est tenu ET dit au non-jugé, une chaîne de
             transitions est attendue jusqu'à son terme.
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from forge_tests.adaptateurs import accessibilite, contraste

playwright_api = pytest.importorskip("playwright.sync_api")

PAGE_TRANSITION = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>t</title>
<style>
  body { background: #ffffff; margin: 24px; }
  #toast { font: 14px sans-serif; color: #eeeeee; transition: color 3s linear; }
  #toast.visible { color: #000000; }
</style></head><body>
<p id="toast">Mission enregistrée</p>
<script>
  setTimeout(() => document.getElementById('toast').classList.add('visible'), 50);
</script></body></html>"""

PAGE_FINIE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>t</title>
<style>
  @keyframes fondu { from { opacity: 0; } to { opacity: 1; } }
  #a { animation: fondu 2.5s linear 1; }
</style></head><body><p id="a">Bonjour</p>
<script>
  document.getElementById('a').getAnimations()[0].finished.then(
    () => { document.body.dataset.fini = '1'; });
</script></body></html>"""

PAGE_ANIMATION_LONGUE = PAGE_FINIE.replace("2.5s", "9s")

PAGE_SANS_FIN = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>t</title>
<style>
  @keyframes tourne { to { transform: rotate(360deg); } }
  #s { display: inline-block; animation: tourne 1s linear infinite; }
</style></head><body><span id="s">o</span></body></html>"""

PAGE_EN_PAUSE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>t</title>
<style>
  @keyframes fondu { from { opacity: 0; } to { opacity: 1; } }
  #p { animation: fondu 30s linear 1; animation-play-state: paused; }
</style></head><body><p id="p">Pause</p></body></html>"""

PAGE_CHAINE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>t</title>
<style>
  #c { width: 10px; transition: width 0.6s linear; }
  #c.deux { width: 200px; }
  #c.trois { width: 400px; }
</style></head><body><div id="c" style="height:10px;background:#000"></div>
<script>
  const c = document.getElementById('c');
  setTimeout(() => c.classList.add('deux'), 30);
  c.addEventListener('transitionend', () => c.classList.add('trois'), { once: true });
</script></body></html>"""


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
    """Un seul Chromium pour le module : le lancer coûte plus cher que chaque test."""
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


def _ouvrir(page, serveur, html: str, nom: str = "page.html") -> None:
    dossier, base = serveur
    (dossier / nom).write_text(html, encoding="utf-8")
    page.goto(f"{base}/{nom}", wait_until="networkidle")


def _couleur(page) -> str:
    return page.evaluate("getComputedStyle(document.getElementById('toast')).color")


# --- L'attente elle-même ------------------------------------------------------------------------
def test_la_premisse_une_couleur_en_transition_se_lit_a_mi_chemin(page, serveur) -> None:
    """ROUGE : c'est le défaut. Après `networkidle` et les 150 ms de l'ancien code, la couleur
    calculée n'est ni celle de départ ni la finale : une mesure de contraste lit ce mélange."""
    _ouvrir(page, serveur, PAGE_TRANSITION)
    page.wait_for_timeout(150)
    assert _couleur(page) not in ("rgb(0, 0, 0)", "rgb(238, 238, 238)")


def test_apres_l_attente_la_couleur_est_la_finale(page, serveur) -> None:
    from forge_tests.stabilite import attendre_animations_finies

    _ouvrir(page, serveur, PAGE_TRANSITION)
    constat = attendre_animations_finies(page)
    assert constat["stable"] is True and constat["restantes"] == 0
    assert 0 <= constat["ms"] < 5000
    assert _couleur(page) == "rgb(0, 0, 0)"


def test_une_animation_sans_fin_n_est_pas_attendue(page, serveur) -> None:
    from forge_tests.stabilite import attendre_animations_finies

    _ouvrir(page, serveur, PAGE_SANS_FIN)
    debut = time.monotonic()
    constat = attendre_animations_finies(page)
    assert time.monotonic() - debut < 2.5  # le plafond de 5 s n'a pas été consommé
    assert constat["stable"] is True and constat["infinies"] == 1


def test_une_animation_en_pause_n_est_pas_attendue(page, serveur) -> None:
    from forge_tests.stabilite import attendre_animations_finies

    _ouvrir(page, serveur, PAGE_EN_PAUSE)
    debut = time.monotonic()
    constat = attendre_animations_finies(page)
    assert time.monotonic() - debut < 2.5
    assert constat["stable"] is True and constat["restantes"] == 0


def test_le_plafond_est_tenu_et_dit(page, serveur) -> None:
    from forge_tests.stabilite import attendre_animations_finies, note_si_instable

    _ouvrir(page, serveur, PAGE_ANIMATION_LONGUE)
    debut = time.monotonic()
    constat = attendre_animations_finies(page, plafond_ms=700)
    assert time.monotonic() - debut < 4  # 9 s d'animation, 0,7 s d'attente
    assert constat["stable"] is False and constat["restantes"] == 1
    note = note_si_instable(constat, "contraste", "/page.html")
    assert note is not None and "contraste : route /page.html" in note
    assert "1 animation(s) finie(s)" in note and "plafond 700 ms" in note


def test_une_chaine_de_transitions_est_attendue_jusqu_au_bout(page, serveur) -> None:
    """La seconde transition naît de la fin de la première : un seul `await` s'arrêterait à 200."""
    from forge_tests.stabilite import attendre_animations_finies

    _ouvrir(page, serveur, PAGE_CHAINE)
    constat = attendre_animations_finies(page)
    assert constat["stable"] is True
    assert page.evaluate("document.getElementById('c').getBoundingClientRect().width") == 400


def test_une_page_qui_ne_repond_pas_rend_un_constat_non_verifie_sans_lever() -> None:
    from forge_tests.stabilite import attendre_animations_finies, note_si_instable

    class Casse:
        def evaluate(self, *_a: object) -> dict:
            raise RuntimeError("page fermee")

    constat = attendre_animations_finies(Casse())
    assert constat["stable"] is None
    note = note_si_instable(constat, "contraste", "/")
    assert note is not None and "n'a pas pu être vérifiée" in note


# --- Le pan contraste : la mesure vive ----------------------------------------------------------
def _parcours_reel(page, serveur, html: str):
    """Remplace `parcourir` : ouvre la vraie page dans le vrai navigateur, joue l'action du pan."""
    dossier, base = serveur
    (dossier / "page.html").write_text(html, encoding="utf-8")

    def parcourir(_cible, _routes, action, *, prefixe):
        page.goto(f"{base}/page.html", wait_until="networkidle")
        valeur, motif = action(page, "/")
        return ({"/": valeur} if valeur is not None else {}), ([motif] if motif else [])

    return parcourir


def test_rouge_le_pan_contraste_jugeait_une_couleur_a_mi_transition(
    page, serveur, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La page est CONFORME à l'affichage final (#000 sur #fff). ROUGE avant : FAIL, contraste
    mesuré sur le mélange. VERT : PASS."""
    if contraste._mesure_js() is None:
        pytest.skip("socle de mesure du contraste absent (digit-ai-page-html)")
    monkeypatch.setattr(contraste.accessibilite, "routes_a_auditer", lambda _c: (["/"], "test"))
    monkeypatch.setattr(contraste, "parcourir", _parcours_reel(page, serveur, PAGE_TRANSITION))
    sortie = contraste.analyser(Path("projet-factice"))
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert sortie.findings == []


def test_le_pan_contraste_dit_quand_la_page_n_a_pas_pu_etre_vue_stable(
    page, serveur, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forge_tests import stabilite

    if contraste._mesure_js() is None:
        pytest.skip("socle de mesure du contraste absent (digit-ai-page-html)")
    monkeypatch.setattr(stabilite, "PLAFOND_MS", 600)
    monkeypatch.setattr(contraste.accessibilite, "routes_a_auditer", lambda _c: (["/"], "test"))
    monkeypatch.setattr(
        contraste, "parcourir", _parcours_reel(page, serveur, PAGE_ANIMATION_LONGUE)
    )
    sortie = contraste.analyser(Path("projet-factice"))
    assert any("animation(s) finie(s) duraient encore" in ligne for ligne in sortie.non_juge)


# --- Le pan accessibilité : la capture écrite pour oracle-a11y -----------------------------------
def test_rouge_la_capture_d_accessibilite_etait_ecrite_avant_la_fin_de_l_animation(
    page, serveur, tmp_path: Path
) -> None:
    dossier, base = serveur
    (dossier / "page.html").write_text(PAGE_FINIE, encoding="utf-8")
    sortie = tmp_path / "captures"
    sortie.mkdir()
    fichier, motif = accessibilite._capturer_une_route(page, base, "/page.html", sortie)
    assert motif is None and fichier is not None
    assert 'data-fini="1"' in fichier.read_text(encoding="utf-8")


def test_la_capture_d_accessibilite_dit_quand_le_plafond_est_atteint(
    page, serveur, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forge_tests import stabilite

    monkeypatch.setattr(stabilite, "PLAFOND_MS", 600)
    dossier, base = serveur
    (dossier / "page.html").write_text(PAGE_ANIMATION_LONGUE, encoding="utf-8")
    sortie = tmp_path / "captures"
    sortie.mkdir()
    notes: list[str] = []
    fichier, motif = accessibilite._capturer_une_route(
        page, base, "/page.html", sortie, notes=notes
    )
    assert fichier is not None and motif is None
    assert len(notes) == 1 and "accessibilite : route /page.html jugée alors que" in notes[0]


def test_contre_epreuve_une_page_stable_ne_produit_aucune_note(
    page, serveur, tmp_path: Path
) -> None:
    dossier, base = serveur
    (dossier / "page.html").write_text(PAGE_SANS_FIN, encoding="utf-8")
    sortie = tmp_path / "captures"
    sortie.mkdir()
    notes: list[str] = []
    fichier, _ = accessibilite._capturer_une_route(page, base, "/page.html", sortie, notes=notes)
    assert fichier is not None and notes == []
