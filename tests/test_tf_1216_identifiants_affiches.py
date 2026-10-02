"""TF-1216 (forge-tests / forge-websec) — aucun contrôle ne lisait le TEXTE SERVI d'une page
pour y trouver un identifiant ou un mot de passe.

LE FAIT (instruction INS-0002 du 14/09/2026, pilot, lecture seule sur Produit-61). Avant le
correctif du 06/09, la page de connexion de l'administration affichait un couple identifiant /
mot de passe de DÉMONSTRATION dès que le drapeau de démonstration était actif, et ce drapeau
était actif sur le SEUL environnement servi, joignable depuis Internet. Le pan `interface` de
forge-tests juge le câblage des éléments (présence, atteignabilité), jamais le texte rendu : il
a rendu vert. `digit-ai-forge-websec` (oracle-exposition, règles EX-1 à EX-11) déclare
explicitement le corps de la réponse hors de son périmètre. Le défaut n'a été vu que par
l'humain qui a écrit l'instruction.

Mandat de cette campagne : écrire uniquement dans `digit-ai-forge-tests` (mandat d'écriture
permanent). Le volet `digit-ai-forge-websec` de cet item est signalé en note dans la sortie de
campagne plutôt que traité ici.

Ce fichier prouve, dans les deux sens : un couple identifiant/mot de passe affiché EN TEXTE sur
une page de connexion hors environnement local est rouge ; une page de connexion générique
(libellés sans valeur, ou valeur dans un `<input>` vide) reste verte ; un hôte local
(`localhost`, `127.0.0.1`) n'est jamais jugé, quel que soit son contenu.
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

# --- Fonctions pures : aucun navigateur nécessaire ---------------------------------------------

_CORPS_COUPLE_AFFICHE = (
    "<h1>Connexion</h1>"
    "<p>Essayez la démo — Identifiant : demo@exemple.com / Mot de passe : Demo1234</p>"
    '<form><input type="text" name="login"><input type="password" name="mdp"></form>'
)

_CORPS_GENERIQUE = (
    "<h1>Connexion</h1>"
    "<form>"
    '<label for="login">Identifiant :</label><input id="login" type="text">'
    '<label for="mdp">Mot de passe :</label><input id="mdp" type="password">'
    "</form>"
)

_CORPS_IDENTIFIANT_SEUL = "<p>Votre identifiant : vous le trouverez dans l'e-mail de bienvenue.</p>"


def test_rouge_couple_identifiant_mot_de_passe_affiche_en_texte() -> None:
    valeurs = qualif.identifiants_affiches(_CORPS_COUPLE_AFFICHE)

    assert valeurs["identifiant"] == ["demo@exemple.com"]
    assert valeurs["mot_de_passe"] == ["Demo1234"]


def test_vert_page_de_connexion_generique_sans_valeur_affichee() -> None:
    """Un libellé suivi de son propre `<input>` vide — la forme SAINE — ne doit RIEN déclencher."""
    valeurs = qualif.identifiants_affiches(_CORPS_GENERIQUE)

    assert valeurs["identifiant"] == []
    assert valeurs["mot_de_passe"] == []


def test_un_mot_isole_sans_couple_ne_suffit_pas() -> None:
    """BORNE explicite de l'item : c'est le COUPLE qui est le défaut, pas un mot isolé."""
    valeurs = qualif.identifiants_affiches(_CORPS_IDENTIFIANT_SEUL)

    assert valeurs["identifiant"]
    assert valeurs["mot_de_passe"] == []


def test_environnement_local_n_est_jamais_juge() -> None:
    assert qualif.environnement_local("http://localhost:5173") is True
    assert qualif.environnement_local("http://127.0.0.1:8091") is True
    assert qualif.environnement_local("http://[::1]:8091") is True
    assert qualif.environnement_local("https://produit-61.exemple.test") is False


# --- Bout en bout, via `conclure()` : le finding publié ou son absence -------------------------


def _page_vue(route: str, corps: str) -> dict:
    return {
        "route": route, "statut": 200, "url_finale": "", "problemes": [], "affordances": [],
        "corps": corps, "console": [], "role": "",
    }


def _config(base: str) -> dict:
    return {"base": base, "marqueurs": {}, "storage_state": "", "bearer": ""}


def test_bout_en_bout_rouge_hors_environnement_local(tmp_path: Path) -> None:
    releve = [_page_vue("/connexion", _CORPS_COUPLE_AFFICHE)]

    sortie = qualif.conclure(
        tmp_path, _config("https://produit-61.exemple.test"), releve, [], None, None,
    )

    constats = [
        f for f in sortie.findings if f.classe == "identifiants-affiches-dans-le-texte-servi"
    ]
    assert len(constats) == 1
    assert "demo@exemple.com" in constats[0].message
    assert "Demo1234" in constats[0].message
    assert constats[0].severite == "bloquant"


def test_bout_en_bout_vert_page_generique(tmp_path: Path) -> None:
    releve = [_page_vue("/connexion", _CORPS_GENERIQUE)]

    sortie = qualif.conclure(
        tmp_path, _config("https://produit-61.exemple.test"), releve, [], None, None,
    )

    assert not any(
        f.classe == "identifiants-affiches-dans-le-texte-servi" for f in sortie.findings
    )


def test_bout_en_bout_vert_sur_hote_local_meme_avec_le_couple(tmp_path: Path) -> None:
    """Le fait fondateur le dit : le drapeau de démo est un OUTIL local, pas une exposition."""
    releve = [_page_vue("/connexion", _CORPS_COUPLE_AFFICHE)]

    sortie = qualif.conclure(tmp_path, _config("http://127.0.0.1:8091"), releve, [], None, None)

    assert not any(
        f.classe == "identifiants-affiches-dans-le-texte-servi" for f in sortie.findings
    )


def test_ne_change_pas_le_ratio_inventaire_exerce(tmp_path: Path) -> None:
    """Conception délibérée : ce constat est HORS du ratio de couverture (même statut que
    TF-1218), pour ne changer le compte d'aucun audit existant qui n'a pas ce défaut."""
    releve = [_page_vue("/connexion", _CORPS_GENERIQUE)]

    sans = qualif.conclure(tmp_path, _config("http://127.0.0.1:1"), releve, [], None, None)
    avec = qualif.conclure(
        tmp_path, _config("https://produit-61.exemple.test"), releve, [], None, None,
    )

    assert sans.surface["inventorie"] == avec.surface["inventorie"]
    assert sans.surface["exerce"] == avec.surface["exerce"]


# --- Contre un vrai navigateur et une vraie instance servie, comme le fait fondateur -----------

_PAGE_CONNEXION_DEMO = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Connexion admin</title></head>
<body>
  <h1>Connexion</h1>
  <p>Démo — Identifiant : demo@exemple.com / Mot de passe : Demo1234</p>
  <form><input type="text" name="login"><input type="password" name="mdp"></form>
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


def test_le_texte_REELLEMENT_rendu_porte_le_couple(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Le contrôle lit ce que `page.content()` rend — pas le gabarit source — même doctrine que
    le reste du pan (contraste, plancher) : un DOM capturé puis relu depuis le disque ne mesure
    pas ce qui est réellement SERVI."""
    racine = tmp_path_factory.mktemp("banc-identifiants")
    (racine / "connexion.html").write_text(_PAGE_CONNEXION_DEMO, encoding="utf-8")
    playwright = pytest.importorskip("playwright.sync_api")
    with _servir(racine) as instance, playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        page = navigateur.new_page()
        page.goto(f"{instance}/connexion.html", wait_until="networkidle")
        corps = page.content()
        navigateur.close()

    valeurs = qualif.identifiants_affiches(corps)
    assert valeurs["identifiant"] == ["demo@exemple.com"]
    assert valeurs["mot_de_passe"] == ["Demo1234"]
