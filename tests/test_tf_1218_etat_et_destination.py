"""TF-1218 — aucun contrôle ne vérifiait qu'un ÉTAT CLIENT survit à une navigation, et la
pertinence d'une destination restait hors de portée même quand le projet savait la déclarer.

LE FAIT (instruction INS-0005 du 14/09/2026, journal Produit-61 séq. 88). Avant le correctif du
06/09, sur la page client : ouvrir l'aide faisait perdre le contenu du panier (aucune
persistance entre deux navigations), et le bouton « Ma commande » menait vers une destination
sans rapport. Une mesure au navigateur, consignée au journal AVANT le correctif, le confirme.
Le pan `interface` et le parcours de qualification vérifiaient la présence et l'atteignabilité
des boutons (RT-7), puis — depuis TF-0876 — qu'un clic produit un effet OBSERVÉ ; jamais que
l'état construit par l'utilisateur survit à l'aller-retour, ni que la destination est la bonne.

Deux contrôles, chacun opt-in (même frontière d'environnement que les effets, TF-0876 : un clic
écrit vraiment sur une instance peuplée) et chacun avec son jeu d'essai à double sens :

  - `verifier_etat_survit_a_navigation` — remplir, naviguer ailleurs, revenir, le marqueur
    d'état est-il intact ? (`CHAMPS_ETAT` : route, geste de remplissage, marqueur, destination) ;
  - `pertinence_destination` — une navigation OBSERVÉE est-elle conforme à une attente DÉCLARÉE
    pour l'affordance qui l'a produite (`FORGE_TESTS_QUALIF_DESTINATIONS`) ?
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

# --- Banc : panier SANS persistance (rouge) et panier AVEC persistance localStorage (vert) ----
_PANIER_ROUGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Panier</title></head>
<body>
  <h1>Panier</h1>
  <button id="ajouter" type="button" onclick="ajouter()">Ajouter un article</button>
  <p>Articles : <span id="compte">0</span></p>
  <a href="/aide.html">Aide</a>
  <script>
    // ROUGE : l etat vit seulement dans une variable JS — perdu a chaque navigation/rechargement.
    let compte = 0;
    function ajouter() {
      compte += 1;
      document.getElementById('compte').textContent = String(compte);
    }
  </script>
</body></html>
"""

_PANIER_VERT = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Panier</title></head>
<body>
  <h1>Panier</h1>
  <button id="ajouter" type="button" onclick="ajouter()">Ajouter un article</button>
  <p>Articles : <span id="compte">0</span></p>
  <a href="/aide.html">Aide</a>
  <script>
    // VERT : l etat PERSISTE (localStorage), survit a la navigation.
    function lire() { return parseInt(localStorage.getItem('compte') || '0', 10); }
    function ajouter() {
      const c = lire() + 1;
      localStorage.setItem('compte', String(c));
      document.getElementById('compte').textContent = String(c);
    }
    document.getElementById('compte').textContent = String(lire());
  </script>
</body></html>
"""

_AIDE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Aide</title></head>
<body><h1>Centre d'aide</h1></body></html>
"""

# --- Banc : un lien dont la destination est confrontée (ou non) à une attente déclarée --------
_COMMANDE_PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Compte</title></head>
<body>
  <h1>Compte</h1>
  <a id="ma-commande" href="/aide.html">Ma commande</a>
</body></html>
"""


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
    racine = tmp_path_factory.mktemp("banc-etat-destination")
    (racine / "panier-rouge.html").write_text(_PANIER_ROUGE, encoding="utf-8")
    (racine / "panier-vert.html").write_text(_PANIER_VERT, encoding="utf-8")
    (racine / "aide.html").write_text(_AIDE, encoding="utf-8")
    with _servir(racine) as url:
        yield url


# --- `verifier_etat_survit_a_navigation` — double sens, contre un vrai navigateur -------------


def _config_etat(base: str, route: str) -> dict:
    return {
        "base": base,
        "etat_route": route,
        "etat_remplir": "#ajouter",
        "etat_marqueur": "#compte",
        "etat_ailleurs": "/aide.html",
    }


def test_rouge_l_etat_ne_survit_pas_a_la_navigation(instance: str) -> None:
    """LE défaut mesuré : remplir, ouvrir l'aide, revenir — le panier est VIDE."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        page = navigateur.new_page()
        resultat = qualif.verifier_etat_survit_a_navigation(
            page, _config_etat(instance, "/panier-rouge.html")
        )
        navigateur.close()

    assert resultat is not None
    assert resultat["intact"] is False, resultat
    assert resultat["avant"] == "1"
    assert resultat["apres"] == "0"

    finding = qualif.finding_etat_perdu(resultat, _config_etat(instance, "/panier-rouge.html"))
    assert finding is not None
    assert finding.classe == "etat-perdu-a-la-navigation"
    assert finding.severite == "bloquant"
    assert "/aide.html" in finding.message


def test_vert_l_etat_survit_a_la_navigation(instance: str) -> None:
    """Contre-épreuve : le même scénario, sur un panier qui PERSISTE (localStorage)."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        page = navigateur.new_page()
        resultat = qualif.verifier_etat_survit_a_navigation(
            page, _config_etat(instance, "/panier-vert.html")
        )
        navigateur.close()

    assert resultat is not None
    assert resultat["intact"] is True, resultat
    assert resultat["avant"] == resultat["apres"] == "1"
    assert qualif.finding_etat_perdu(resultat, {}) is None


def test_le_scenario_ne_se_joue_pas_sans_declaration_complete() -> None:
    """Les quatre champs de CHAMPS_ETAT sont TOUS requis — un pan aveugle qui se tait."""
    assert qualif.etat_declare({}) is False
    assert (
        qualif.etat_declare(
            {
                "etat_route": "/panier",
                "etat_remplir": "#ajouter",
                "etat_marqueur": "#compte",
                "etat_ailleurs": "",
            }
        )
        is False
    )
    assert (
        qualif.etat_declare(
            {
                "etat_route": "/panier",
                "etat_remplir": "#ajouter",
                "etat_marqueur": "#compte",
                "etat_ailleurs": "/aide",
            }
        )
        is True
    )
    assert qualif.verifier_etat_survit_a_navigation(None, {}) is None


def test_un_marqueur_jamais_appaaru_est_NON_JUGE_pas_accuse(instance: str) -> None:
    """BORNE : si le marqueur déclaré n'existe pas, le scénario se tait — il n'invente rien."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        page = navigateur.new_page()
        config = _config_etat(instance, "/panier-rouge.html")
        config["etat_marqueur"] = "#n-existe-pas"
        resultat = qualif.verifier_etat_survit_a_navigation(page, config)
        navigateur.close()

    assert resultat is None


# --- `pertinence_destination` — pure, pas besoin de navigateur --------------------------------


def test_rouge_destination_declaree_trahie() -> None:
    """LE second défaut : « Ma commande » mène à l'aide, alors qu'une commande était attendue."""
    affordance = {"observe": True, "effet": "navigation vers http://x/aide.html"}
    config = {"destinations": {"ma commande": "/commande"}}

    motif = qualif.pertinence_destination("Ma commande", affordance, config)

    assert motif is not None
    assert "ma commande" in motif.lower() or "Ma commande" in motif
    assert "/commande" in motif


def test_vert_destination_declaree_tenue() -> None:
    affordance = {"observe": True, "effet": "navigation vers http://x/commande/42"}
    config = {"destinations": {"ma commande": "/commande"}}

    assert qualif.pertinence_destination("Ma commande", affordance, config) is None


def test_sans_declaration_la_destination_n_est_pas_jugee() -> None:
    """Non-régression du périmètre TF-0876 : sans attente déclarée, rien n'est jugé."""
    affordance = {"observe": True, "effet": "navigation vers http://x/aide.html"}

    assert qualif.pertinence_destination("Ma commande", affordance, {}) is None
    assert qualif.pertinence_destination("Ma commande", affordance, {"destinations": {}}) is None


def test_un_effet_non_observe_n_est_jamais_juge_sur_sa_destination() -> None:
    """BORNE : seul un effet OBSERVÉ (navigation réellement constatée) est confronté."""
    affordance = {"observe": False, "effet": "aucun effet observé"}
    config = {"destinations": {"ma commande": "/commande"}}

    assert qualif.pertinence_destination("Ma commande", affordance, config) is None


# --- Bout en bout : le lien publié par TF-0876 devient un défaut NOMMÉ quand l'attente est
# déclarée, contre un vrai navigateur ------------------------------------------------------------


def test_bout_en_bout_le_lien_de_TF_0876_devient_un_defaut_declare(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    racine = tmp_path_factory.mktemp("banc-commande")
    (racine / "index.html").write_text(_COMMANDE_PAGE, encoding="utf-8")
    (racine / "aide.html").write_text(_AIDE, encoding="utf-8")
    playwright = pytest.importorskip("playwright.sync_api")
    with _servir(racine) as instance, playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        page = navigateur.new_page()
        page.goto(f"{instance}/index.html", wait_until="networkidle")
        descripteurs = page.evaluate(qualif._JS_AFFORDANCES)
        affordance = next(d for d in descripteurs if "Ma commande" in (d["libelle"] or ""))
        resultat = qualif._observer_effet(
            page, f"{instance}/index.html", {"rang": affordance["rang"], "tag": "a"},
            qualif._SELECTEUR,
        )
        navigateur.close()

    config = {"destinations": {"ma commande": "/commande"}}
    motif = qualif.pertinence_destination("Ma commande", resultat, config)

    assert motif is not None
    assert "aide.html" in motif
