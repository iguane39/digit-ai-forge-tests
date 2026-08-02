"""Sonde d exécution API — greffon pytest, installé de l EXTÉRIEUR du projet analysé.

Enregistre les couples (méthode, gabarit de route, code) RÉELLEMENT renvoyés pendant la suite.
Remplace le recoupement textuel, qui comptait pour couverture un simple `client.get("/x")`
apparaissant dans un fichier de test, sans savoir si l appel avait lieu ni ce qu il renvoyait.

Ne modifie AUCUN fichier du projet : chargé par `pytest -p sonde_api`, il greffe un middleware
ASGI standard sur l application en mémoire et écrit son relevé dans FORGE_TESTS_SONDE.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

OBSERVE: set[tuple[str, str, int]] = set()


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


def pytest_sessionstart(session) -> None:  # noqa: ANN001, ARG001
    """Greffe le middleware avant la construction du premier client de test."""
    try:
        import app.main as principal
    except Exception:  # noqa: BLE001 — projet sans module app.main : la sonde se tait
        return
    application = getattr(principal, "app", None)
    if application is None or not hasattr(application, "add_middleware"):
        return
    application.add_middleware(MiddlewareSonde)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001, ARG001
    destination = os.environ.get("FORGE_TESTS_SONDE")
    if not destination:
        return
    releve = [{"methode": m, "gabarit": g, "code": c} for m, g, c in sorted(OBSERVE)]
    Path(destination).write_text(
        json.dumps(releve, ensure_ascii=False, indent=2), encoding="utf-8"
    )
