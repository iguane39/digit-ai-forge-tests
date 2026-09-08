"""TF-0876 — un bouton câblé n'est pas un bouton qui marche.

LE FAIT (lot Produit-61, retour du 06/09/2026). `rapport-20260905g.json` publiait, pour le pan
`qualif`, **68/68 exercés — 100 %**. Le lendemain, un humain ouvrait l'instance : « Ma commande »
menait à la page d'aide, et « Panier » n'avait aucun effet visible. Les deux affordances portaient
bien un écouteur — c'est tout ce que le pan regardait. Le smoke M-3, joué en HTTP direct, ne
pouvait pas le voir non plus : il ne clique pas.

La limite était pourtant DÉCLARÉE au `non_juge` du pan depuis l'origine (« le pan LIT les
écouteurs, il ne CLIQUE jamais »). Elle n'a rien rattrapé : un registre de dette ne corrige pas
un chiffre. Ce qui manquait, c'est que le mot « exercé » veuille dire ce qu'il dit.

Ce que ces cas vérifient, contre un vrai navigateur et une vraie instance servie :

- un bouton dont l'écouteur ne fait RIEN est vu comme sans effet — il ne l'était pas ;
- un bouton dont l'écouteur change le DOM est vu comme exercé ;
- un lien qui navigue est exercé, ET sa destination CONSTATÉE est publiée — c'est ce qui rend
  visible le « Ma commande » qui mène à `/aide`, sans prétendre juger la pertinence ;
- la porte est explicite : sans `FORGE_TESTS_QUALIF_EFFETS=1` rien n'est cliqué, et le compte
  des affordances seulement CÂBLÉES est publié plutôt que fondu dans « exercé ». Le clic écrit
  vraiment sur une instance peuplée : c'est une frontière d'environnement, pas une option de
  confort.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import os
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from forge_tests.adaptateurs import qualif

_PAGE = """<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"><title>Banc d'effets</title></head>
<body>
  <h1>Commandes</h1>
  <a id="ma-commande" href="/aide.html">Ma commande</a>
  <button id="panier" type="button" onclick="void 0">Panier</button>
  <button id="rafraichir" type="button" onclick="ajouter()">Rafraichir la liste</button>
  <ul id="liste"></ul>
  <script>
    function ajouter() {
      const li = document.createElement('li');
      li.textContent = 'ligne ajoutee';
      document.getElementById('liste').appendChild(li);
    }
  </script>
</body>
</html>
"""

_AIDE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Aide</title></head>
<body><h1>Centre d'aide</h1></body></html>
"""


class _ServeurMuet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # noqa: D102
        return


@contextlib.contextmanager
def _servir(dossier: Path) -> Iterator[str]:
    """Une instance SERVIE, comme la recette en sert une pour ce pan."""
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
    racine = tmp_path_factory.mktemp("banc-effets")
    (racine / "index.html").write_text(_PAGE, encoding="utf-8")
    (racine / "aide.html").write_text(_AIDE, encoding="utf-8")
    with _servir(racine) as url:
        yield url


@pytest.fixture(scope="module")
def observations(instance: str) -> dict[str, dict]:
    """Chaque affordance de la page, cliquée pour de vrai, et ce qui a changé."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        page = navigateur.new_page()
        page.goto(f"{instance}/index.html", wait_until="networkidle")
        descripteurs = page.evaluate(qualif._JS_AFFORDANCES)
        resultats: dict[str, dict] = {}
        for descripteur in descripteurs:
            affordance = {"rang": descripteur["rang"], "tag": descripteur["tag"]}
            libelle = (descripteur["libelle"] or "").strip()
            resultats[libelle] = qualif._observer_effet(
                page, f"{instance}/index.html", affordance, qualif._SELECTEUR
            )
        navigateur.close()
    return resultats


# --- Le défaut fondateur, joué contre un vrai navigateur ---------------------------------------


def test_le_bouton_cable_qui_ne_fait_RIEN_est_vu_sans_effet(observations: dict[str, dict]) -> None:
    """FIXTURE ROUGE — « Panier » : un `onclick` bien attaché, et aucun effet.

    C'est exactement ce que le pan comptait pour exercé, et ce qu'un humain a vu le lendemain.
    """
    panier = observations["Panier"]

    assert panier["observe"] is False, f"« Panier » devait etre vu SANS effet : {panier}"
    assert "aucun effet observé" in panier["effet"]


def test_le_bouton_qui_change_le_DOM_est_exerce(observations: dict[str, dict]) -> None:
    """FIXTURE VERTE — le même geste, sur un bouton qui fait vraiment quelque chose."""
    rafraichir = observations["Rafraichir la liste"]

    assert rafraichir["observe"] is True, f"un ajout au DOM est un effet : {rafraichir}"
    assert "DOM" in rafraichir["effet"]


def test_le_lien_publie_la_destination_REELLEMENT_atteinte(observations: dict[str, dict]) -> None:
    """« Ma commande » mène à `/aide.html` : la navigation est un effet, et elle est NOMMÉE.

    La pertinence de la destination n'est pas jugée — aucune attente n'est déclarée — mais elle
    cesse d'être invisible : c'est le second symptôme du retour du 06/09.
    """
    lien = observations["Ma commande"]

    assert lien["observe"] is True
    assert "aide.html" in lien["effet"], (
        f"la destination CONSTATEE doit figurer dans l'effet publie : {lien}")


def test_un_element_non_cliquable_n_est_pas_accuse() -> None:
    """BORNE : ce qu'on ne peut pas observer est NON JUGÉ, jamais compté en défaut."""
    resultat = qualif._observer_effet(None, "", {"rang": 0, "tag": "form"}, qualif._SELECTEUR)

    assert resultat["observe"] is None
    assert "non cliquable" in resultat["effet"]


# --- La porte, et ce que le rapport dit quand elle est fermée -----------------------------------


def test_le_clic_ne_se_joue_que_s_il_est_DEMANDE(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un clic écrit vraiment sur une instance peuplée : la frontière est explicite."""
    monkeypatch.delenv("FORGE_TESTS_QUALIF_EFFETS", raising=False)
    assert qualif._config(Path("."))["effets"] is False

    monkeypatch.setenv("FORGE_TESTS_QUALIF_EFFETS", "1")
    assert qualif._config(Path("."))["effets"] is True

    monkeypatch.setenv("FORGE_TESTS_QUALIF_EFFETS", "0")
    assert qualif._config(Path("."))["effets"] is False


def test_le_plafond_d_observation_est_borne_et_reglable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chaque observation recharge la page : le coût se borne, et le rapport dit qu'il l'a fait."""
    monkeypatch.delenv("FORGE_TESTS_QUALIF_EFFETS_PLAFOND", raising=False)
    assert qualif._config(Path("."))["effets_plafond"] == qualif._EFFETS_PLAFOND_DEFAUT

    monkeypatch.setenv("FORGE_TESTS_QUALIF_EFFETS_PLAFOND", "3")
    assert qualif._config(Path("."))["effets_plafond"] == 3


def test_la_limite_du_pan_NOMME_la_porte_qui_la_leve() -> None:
    """Une dette déclarée sans son remède se relit chaque semaine sans jamais se solder."""
    declare = " ".join(qualif.NON_JUGE)

    assert "FORGE_TESTS_QUALIF_EFFETS=1" in declare
    assert "CABLEES, pas exercees" in declare or "CABLEES" in declare


def test_la_cle_d_observation_arrive_dans_le_gabarit_depose(tmp_path: Path) -> None:
    from forge_tests import gabarit_env

    cles = gabarit_env.cles_connues()
    assert "FORGE_TESTS_QUALIF_EFFETS" in cles
    assert "FORGE_TESTS_QUALIF_EFFETS_PLAFOND" in cles


def test_l_environnement_du_poste_n_a_pas_ete_laisse_sale() -> None:
    """Garde : ces cas manipulent des variables d'environnement partagées."""
    assert os.environ.get("FORGE_TESTS_QUALIF_EFFETS") in (None, "")
