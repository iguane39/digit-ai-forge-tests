"""Suite API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import COMMANDES, JETON, app

AUTH = {"Authorization": f"Bearer {JETON}"}


@pytest.fixture(autouse=True)
def _isolation() -> None:
    COMMANDES.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_login(client: TestClient) -> None:
    r = client.post("/api/login", json={"email": "chef@exemple.fr", "mot_de_passe": "secret"})
    assert r.status_code == 200


def test_lister(client: TestClient) -> None:
    assert client.get("/api/commandes", headers=AUTH).status_code == 200


def test_creer(client: TestClient) -> None:
    r = client.post("/api/commandes", json={"plat": "curry", "quantite": 2}, headers=AUTH)
    assert r.status_code == 201


def test_detail(client: TestClient) -> None:
    r = client.post("/api/commandes", json={"plat": "curry", "quantite": 2}, headers=AUTH)
    cid = r.json()["id"]
    assert client.get(f"/api/commandes/{cid}", headers=AUTH).status_code == 200
