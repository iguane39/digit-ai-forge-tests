"""TF-1789 — le pan `api` accusait des codes émis par des adresses SANS route.

Fait remonté par Produit-83 (lot 20261015b, RE-1, ledger seq 120) : 19 constats « code émis
par l application mais absent de sa déclaration responses= » portaient sur le repli 404, sur
l interface servie et sur `/openapi.json`. Aucune de ces adresses n a d opération au schéma :
aucun `responses=` ne peut y déclarer quoi que ce soit. L exemption RT-10 ne couvrait que les
préfixes d `app.mount()`.

La règle corrigée : un code ne se juge en divergence que sur une opération que l inventaire
porte. Le reste est publié au non-jugé, avec son compte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import api
from forge_tests.noyau import Element


def _projet(tmp_path: Path) -> Path:
    projet = tmp_path / "projet"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "main.py").write_text("app = None\n", encoding="utf-8")
    return projet


INVENTAIRE = [
    Element("endpoint:GET /api/items", "api", "GET /api/items", "app/main.py"),
    Element("code:GET /api/items=200", "api", "GET /api/items -> 200", "app/main.py"),
]


def _analyser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, releve: list[dict]):  # noqa: ANN202
    monkeypatch.setattr(api, "inventaire", lambda _cible: INVENTAIRE)
    monkeypatch.setattr(api, "codes_emis", lambda _cible: releve)
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: {"paths": {}})
    return api.analyser(_projet(tmp_path))


def test_adresses_sans_route_ne_sont_plus_des_divergences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releve = [
        {"methode": "GET", "gabarit": "/api/items", "code": 200, "route": True, "schema": True},
        {"methode": "GET", "gabarit": "/nulle-part", "code": 404, "route": False,
         "schema": False},
        {"methode": "GET", "gabarit": "/openapi.json", "code": 200, "route": True,
         "schema": False},
        {"methode": "GET", "gabarit": "/{chemin:path}", "code": 200, "route": True,
         "schema": False},
        # Relevé ancien, sans le détail : pas d opération au schéma, rien à déclarer non plus.
        {"methode": "GET", "gabarit": "/assets/app.js", "code": 200},
    ]
    sortie = _analyser(tmp_path, monkeypatch, releve)
    divergences = [f for f in sortie.findings if f.classe == "divergence"]
    assert divergences == []
    assert any("TF-1789" in n and "4 couple(s)" in n for n in sortie.non_juge)


def test_code_non_declare_sur_une_operation_inventoriee_reste_une_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le sens fautif tient toujours : un 500 émis par une opération du schéma, sans
    déclaration, est un écart que le produit peut et doit réparer."""
    releve = [
        {"methode": "GET", "gabarit": "/api/items", "code": 200, "route": True, "schema": True},
        {"methode": "GET", "gabarit": "/api/items", "code": 500, "route": True, "schema": True},
    ]
    sortie = _analyser(tmp_path, monkeypatch, releve)
    ids = [f.id for f in sortie.findings if f.classe == "divergence"]
    assert ids == ["code:GET /api/items=500"]
