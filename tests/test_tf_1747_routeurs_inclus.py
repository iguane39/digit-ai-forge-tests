"""TF-1747 — sur FastAPI récent, la sonde relevait le gabarit LOCAL d une route incluse.

Fait remonté par Produit-76 (lot du 25/09/2026, RT-9) : depuis que `include_router()` range
chaque routeur dans un `_IncludedRouter` qui garde l original sous `original_router`, une
lecture qui ne descend pas dans cet objet ne voit plus les routes. Mesuré chez le produit :
2 entrées dans `app.routes` (un Mount et un `_IncludedRouter`) pour 36 routes réelles.

Ce que forge-tests en subissait, mesuré le 15/10/2026 sous FastAPI 0.141.1 : son inventaire
passe par `app.openapi()`, que FastAPI aplatit lui-même (les trois chemins composés sortent).
Mais la sonde lisait `scope["route"].path`, et FastAPI y pose désormais la route ORIGINALE,
celle du routeur feuille : `POST /api/admin/workers/{worker_name}/cancel` était relevé
`/workers/{worker_name}/cancel`. Aucun couple relevé n appariait l inventaire, et la
couverture d une suite verte qui appelle tout sortait proche de zéro, sans le dire.

Deux corrections, chacune avec son test :
  1. la sonde lit le gabarit EFFECTIF (contexte de route que FastAPI pose dans le scope) ;
  2. un plancher : une route servie et déclarée au schéma, qu aucune entrée de l inventaire ne
     porte, prouve une énumération incomplète. Le pan échoue au lieu de conclure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from forge_tests.adaptateurs import api
from forge_tests.noyau import Element

fastapi = pytest.importorskip("fastapi")

from forge_tests.sondes import sonde_api  # noqa: E402


def _application_a_trois_niveaux():  # noqa: ANN202
    from fastapi import APIRouter, FastAPI

    feuille = APIRouter(prefix="/workers")

    @feuille.post("/{worker_name}/cancel")
    def annuler(worker_name: str) -> dict:
        return {"ok": worker_name}

    milieu = APIRouter(prefix="/admin")
    milieu.include_router(feuille)

    @milieu.get("/stats")
    def stats() -> dict:
        return {}

    tete = APIRouter(prefix="/api")
    tete.include_router(milieu)

    @tete.get("/cache", include_in_schema=False)
    def cache() -> dict:
        return {}

    application = FastAPI()
    application.include_router(tete)
    return application


def _appeler(application, methode: str, chemin: str) -> None:  # noqa: ANN001
    scope = {
        "type": "http", "method": methode, "path": chemin, "raw_path": chemin.encode(),
        "query_string": b"", "headers": [], "http_version": "1.1", "scheme": "http",
        "server": ("test", 80), "client": ("test", 1), "root_path": "",
    }

    async def recevoir() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def envoyer(_message: dict) -> None:
        return None

    asyncio.run(application(scope, recevoir, envoyer))


# --- 1. La sonde relève le gabarit COMPOSÉ, jamais le fragment du routeur feuille -------------
def test_sonde_releve_le_gabarit_compose_d_un_routeur_inclus_sur_trois_niveaux() -> None:
    application = _application_a_trois_niveaux()
    application.add_middleware(sonde_api.MiddlewareSonde)
    sonde_api.OBSERVE.clear()
    sonde_api.DETAILS.clear()
    _appeler(application, "POST", "/api/admin/workers/w1/cancel")
    _appeler(application, "GET", "/api/admin/stats")
    gabarits = {(m, g) for m, g, _c in sonde_api.OBSERVE}
    assert ("POST", "/api/admin/workers/{worker_name}/cancel") in gabarits
    assert ("GET", "/api/admin/stats") in gabarits
    assert ("POST", "/workers/{worker_name}/cancel") not in gabarits
    # L inventaire (schéma) et la sonde parlent désormais du même chemin.
    chemins = set(application.openapi()["paths"])
    assert {g for _m, g in gabarits} <= chemins


def test_sonde_note_route_trouvee_et_presence_au_schema() -> None:
    application = _application_a_trois_niveaux()
    application.add_middleware(sonde_api.MiddlewareSonde)
    sonde_api.OBSERVE.clear()
    sonde_api.DETAILS.clear()
    _appeler(application, "GET", "/api/cache")
    _appeler(application, "GET", "/nulle-part")
    details = {(m, g, c): d for (m, g, c), d in sonde_api.DETAILS.items()}
    assert details[("GET", "/api/cache", 200)] == {"route": True, "schema": False}
    assert details[("GET", "/nulle-part", 404)] == {"route": False, "schema": False}


# --- 2. Le plancher : une route servie absente de l inventaire fait échouer le pan ------------
def _projet(tmp_path: Path) -> Path:
    projet = tmp_path / "projet"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "main.py").write_text("app = None\n", encoding="utf-8")
    return projet


def _brancher(monkeypatch, inventaire: list[Element], releve: list[dict]) -> None:  # noqa: ANN001
    monkeypatch.setattr(api, "inventaire", lambda _cible: inventaire)
    monkeypatch.setattr(api, "codes_emis", lambda _cible: releve)
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: {"paths": {}})


def test_plancher_route_servie_hors_inventaire_fait_echouer_le_pan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas fautif : l inventaire n a vu qu une route, la suite en a servi trois."""
    inventaire = [
        Element("endpoint:GET /api/ping", "api", "GET /api/ping", "app/main.py"),
        Element("code:GET /api/ping=200", "api", "GET /api/ping -> 200", "app/main.py"),
    ]
    releve = [
        {"methode": "GET", "gabarit": "/api/ping", "code": 200, "route": True, "schema": True},
        {"methode": "GET", "gabarit": "/api/admin/stats", "code": 200, "route": True,
         "schema": True},
        {"methode": "POST", "gabarit": "/api/admin/workers/{worker_name}/cancel", "code": 200,
         "route": True, "schema": True},
    ]
    _brancher(monkeypatch, inventaire, releve)
    sortie = api.analyser(_projet(tmp_path))
    assert sortie.verdict == "FAIL"
    plancher = [f for f in sortie.findings if f.id == "enumeration-incomplete:api"]
    assert len(plancher) == 1
    assert plancher[0].severite == "bloquant"
    assert "/api/admin/stats" in plancher[0].message
    # Les deux routes manquées ne se déguisent plus en « code non déclaré » : ce n est pas un
    # oubli de `responses=`, c est l inventaire qui ne les a pas vues.
    assert not [f for f in sortie.findings if f.id.startswith("code:GET /api/admin/stats")]


def test_plancher_route_hors_schema_ou_inventoriee_ne_fait_pas_echouer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas conforme : tout ce qui est servi et déclaré au schéma est inventorié ; une route
    `include_in_schema=False` n est pas une énumération incomplète."""
    inventaire = [
        Element("endpoint:GET /api/ping", "api", "GET /api/ping", "app/main.py"),
        Element("code:GET /api/ping=200", "api", "GET /api/ping -> 200", "app/main.py"),
    ]
    releve = [
        {"methode": "GET", "gabarit": "/api/ping", "code": 200, "route": True, "schema": True},
        {"methode": "GET", "gabarit": "/api/cache", "code": 200, "route": True, "schema": False},
    ]
    _brancher(monkeypatch, inventaire, releve)
    sortie = api.analyser(_projet(tmp_path))
    assert not [f for f in sortie.findings if f.id == "enumeration-incomplete:api"]
    assert sortie.verdict == "PASS"
