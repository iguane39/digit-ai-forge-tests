"""Sonde d exécution API — greffon pytest, installé de l EXTÉRIEUR du projet analysé.

Enregistre les couples (méthode, gabarit de route, code) RÉELLEMENT renvoyés pendant la suite.
Remplace le recoupement textuel, qui comptait pour couverture un simple `client.get("/x")`
apparaissant dans un fichier de test, sans savoir si l appel avait lieu ni ce qu il renvoyait.

Ne modifie AUCUN fichier du projet : chargé par `pytest -p sonde_api`, il greffe un middleware
ASGI standard sur l application en mémoire et écrit son relevé dans FORGE_TESTS_SONDE.

Convention d application : `app.main:app` par défaut. Une suite bâtie sur une APP FACTORY
(`creer_app()` appelée par test) n exerce JAMAIS cette instance module — la sonde relèverait
alors 0 couple sur une suite verte. La désigner avec `FORGE_TESTS_APP="module:attribut"` :
l attribut peut être l instance ou la fabrique, qui est alors enveloppée pour que CHAQUE
application produite soit instrumentée.
"""

from __future__ import annotations

import functools
import importlib
import json
import os
from pathlib import Path

DESIGNATION_PAR_DEFAUT = "app.main:app"

OBSERVE: set[tuple[str, str, int]] = set()
_INSTRUMENTE = False


class MiddlewareSonde:
    """Middleware ASGI pur : lit le statut sortant et le gabarit de route posé par le routeur."""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_espion(message) -> None:  # noqa: ANN001
            if message.get("type") == "http.response.start":
                # `scope["route"]` est posé par le routeur, qui tourne SOUS ce middleware :
                # au moment de la réponse, le gabarit ("/api/commandes/{cid}") est disponible.
                route = scope.get("route")
                gabarit = getattr(route, "path", None) or scope.get("path", "")
                OBSERVE.add((scope.get("method", ""), gabarit, int(message["status"])))
            await send(message)

        await self.app(scope, receive, send_espion)


def _greffer(application) -> bool:  # noqa: ANN001
    """Pose le middleware sur une application ASGI. Faux si l objet n en est pas une."""
    if application is None or not hasattr(application, "add_middleware"):
        return False
    try:
        application.add_middleware(MiddlewareSonde)
    except Exception:  # noqa: BLE001 — application déjà démarrée : la sonde se tait, jamais
        return False  # elle ne casse la suite du projet audité
    return True


def _instrumenter() -> None:
    """Résout l application désignée et l instrumente — instance module OU fabrique."""
    global _INSTRUMENTE
    if _INSTRUMENTE:
        return
    designation = (os.environ.get("FORGE_TESTS_APP") or "").strip() or DESIGNATION_PAR_DEFAUT
    nom_module, _, attribut = designation.partition(":")
    attribut = attribut or "app"
    try:
        module = importlib.import_module(nom_module)
    except Exception:  # noqa: BLE001 — projet sans ce module : la sonde se tait
        return
    cible = getattr(module, attribut, None)
    if _greffer(cible):
        _INSTRUMENTE = True
        return
    if callable(cible):
        # Fabrique d application : l instance module n existe pas, c est l objet RENVOYÉ à
        # chaque appel qu il faut instrumenter. On enveloppe la fabrique DANS SON MODULE —
        # greffe en mémoire, aucun fichier du projet n est touché.
        @functools.wraps(cible)
        def fabrique_espionnee(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            application = cible(*args, **kwargs)
            _greffer(application)
            return application

        setattr(module, attribut, fabrique_espionnee)
        _INSTRUMENTE = True


def pytest_load_initial_conftests(early_config, parser, args) -> None:  # noqa: ANN001, ARG001
    """Instrumente AVANT le chargement des conftests — seul instant utile pour une fabrique.

    pytest charge les conftests de la racine ET de ses sous-dossiers `test*` avant
    `pytest_sessionstart`. Un `tests/conftest.py` qui fait `from app.main import creer_app` a
    donc déjà capturé la fabrique d origine quand la session démarre : l enveloppe posée plus
    tard ne serait jamais appelée, et la sonde resterait muette sur une suite verte.

    Réservé à une désignation EXPLICITE : importer l application aussi tôt, c est le faire
    avant qu un conftest ait posé l environnement qu elle attend. Le projet qui déclare
    `FORGE_TESTS_APP` accepte ce point d entrée ; par défaut on reste au démarrage de session.
    """
    if (os.environ.get("FORGE_TESTS_APP") or "").strip():
        _instrumenter()


def pytest_sessionstart(session) -> None:  # noqa: ANN001, ARG001
    """Cas par défaut : l instance module, greffée une fois les conftests chargés."""
    _instrumenter()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001, ARG001
    destination = os.environ.get("FORGE_TESTS_SONDE")
    if not destination:
        return
    releve = [{"methode": m, "gabarit": g, "code": c} for m, g, c in sorted(OBSERVE)]
    Path(destination).write_text(
        json.dumps(releve, ensure_ascii=False, indent=2), encoding="utf-8"
    )
