"""Suite API couvrante : les 7 couples endpoint x méthode et les 26 codes déclarés."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import COMMANDES, JETON, app

AUTH = {"Authorization": f"Bearer {JETON}"}
CSV = "text/csv"


@pytest.fixture(autouse=True)
def _isolation() -> None:
    COMMANDES.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _creer(client: TestClient, quantite: int = 2) -> int:
    r = client.post("/api/commandes", json={"plat": "curry", "quantite": quantite}, headers=AUTH)
    assert r.status_code == 201
    return int(r.json()["id"])


# --- POST /api/login : 200, 401, 422 ---------------------------------------------------------
def test_login_200(client: TestClient) -> None:
    r = client.post("/api/login", json={"email": "chef@exemple.fr", "mot_de_passe": "secret"})
    assert r.status_code == 200 and r.json()["jeton"] == JETON


def test_login_401(client: TestClient) -> None:
    r = client.post("/api/login", json={"email": "chef@exemple.fr", "mot_de_passe": "faux"})
    assert r.status_code == 401


def test_login_422(client: TestClient) -> None:
    assert client.post("/api/login", json={"email": "chef@exemple.fr"}).status_code == 422


# --- GET /api/commandes : 200, 400, 401 ------------------------------------------------------
def test_lister_200(client: TestClient) -> None:
    assert client.get("/api/commandes", headers=AUTH).status_code == 200


def test_lister_400_statut_inconnu(client: TestClient) -> None:
    assert client.get("/api/commandes?statut=zzz", headers=AUTH).status_code == 400


def test_lister_401(client: TestClient) -> None:
    assert client.get("/api/commandes").status_code == 401


# --- POST /api/commandes : 201, 400, 401, 422 ------------------------------------------------
def test_creer_201(client: TestClient) -> None:
    assert _creer(client) >= 1


def test_creer_400_quantite_nulle(client: TestClient) -> None:
    r = client.post("/api/commandes", json={"plat": "curry", "quantite": 0}, headers=AUTH)
    assert r.status_code == 400


def test_creer_401(client: TestClient) -> None:
    assert client.post("/api/commandes", json={"plat": "x", "quantite": 1}).status_code == 401


def test_creer_422(client: TestClient) -> None:
    r = client.post("/api/commandes", json={"plat": "curry"}, headers=AUTH)
    assert r.status_code == 422


# --- GET /api/commandes/{id} : 200, 401, 404 -------------------------------------------------
def test_detail_200(client: TestClient) -> None:
    cid = _creer(client)
    assert client.get(f"/api/commandes/{cid}", headers=AUTH).status_code == 200


def test_detail_401(client: TestClient) -> None:
    assert client.get("/api/commandes/1").status_code == 401


def test_detail_404(client: TestClient) -> None:
    assert client.get("/api/commandes/9999", headers=AUTH).status_code == 404


# --- PATCH /api/commandes/{id} : 200, 401, 404, 409, 422 -------------------------------------
def test_modifier_200(client: TestClient) -> None:
    cid = _creer(client)
    r = client.patch(f"/api/commandes/{cid}", json={"quantite": 5}, headers=AUTH)
    assert r.status_code == 200 and r.json()["quantite"] == 5


def test_modifier_401(client: TestClient) -> None:
    assert client.patch("/api/commandes/1", json={"quantite": 1}).status_code == 401


def test_modifier_404(client: TestClient) -> None:
    r = client.patch("/api/commandes/9999", json={"quantite": 1}, headers=AUTH)
    assert r.status_code == 404


def test_modifier_409_commande_annulee(client: TestClient) -> None:
    cid = _creer(client)
    client.patch(f"/api/commandes/{cid}", json={"statut": "annulee"}, headers=AUTH)
    r = client.patch(f"/api/commandes/{cid}", json={"quantite": 3}, headers=AUTH)
    assert r.status_code == 409


def test_modifier_422_statut_hors_liste(client: TestClient) -> None:
    cid = _creer(client)
    r = client.patch(f"/api/commandes/{cid}", json={"statut": "zzz"}, headers=AUTH)
    assert r.status_code == 422


# --- DELETE /api/commandes/{id} : 204, 401, 404, 409 ----------------------------------------
def test_supprimer_204_et_lignes_non_orphelines(client: TestClient) -> None:
    cid = _creer(client)
    assert client.delete(f"/api/commandes/{cid}", headers=AUTH).status_code == 204
    assert cid not in COMMANDES  # ni la commande, ni ses lignes


def test_supprimer_401(client: TestClient) -> None:
    assert client.delete("/api/commandes/1").status_code == 401


def test_supprimer_404(client: TestClient) -> None:
    assert client.delete("/api/commandes/9999", headers=AUTH).status_code == 404


def test_supprimer_409_commande_validee(client: TestClient) -> None:
    cid = _creer(client)
    client.patch(f"/api/commandes/{cid}", json={"statut": "validee"}, headers=AUTH)
    assert client.delete(f"/api/commandes/{cid}", headers=AUTH).status_code == 409


# --- POST /api/import : 202, 400, 401, 415 ---------------------------------------------------
def test_import_202(client: TestClient) -> None:
    corps = "plat,quantite\ncurry,2\n"
    r = client.post("/api/import", content=corps, headers={**AUTH, "Content-Type": CSV})
    assert r.status_code == 202 and r.json()["importees"] == 1


def test_import_400_colonnes_absentes(client: TestClient) -> None:
    r = client.post("/api/import", content="a,b\n1,2\n", headers={**AUTH, "Content-Type": CSV})
    assert r.status_code == 400


def test_import_401(client: TestClient) -> None:
    r = client.post("/api/import", content="plat,quantite\n", headers={"Content-Type": CSV})
    assert r.status_code == 401


def test_import_415_type_non_supporte(client: TestClient) -> None:
    r = client.post("/api/import", content="{}", headers={**AUTH, "Content-Type": "application/json"})
    assert r.status_code == 415
