"""TF-2204 — une route que le test porteur ATTEND en 404 n'est pas un défaut du produit.

Fait remonté (Produit-86, lot du 05/11/2026, RP-24) : `/adresse-inconnue-e2e`, que le test E-069
du produit navigue pour vérifier qu'une adresse inconnue rend 404, était comptée en défaut par le
jeu du pan `parcours-personas`. Résultat : couverture 2/4, verdict PARTIEL, seuil bloquant, sur un
produit conforme.

Décision du 06/11/2026 : un code attendu par le test porteur n'est pas compté en défaut.

Trois sens :
  - VERT    — le test affirme 404 pour la route, l'instance rend 404 : le parcours est joué ;
  - ROUGE   — le même 404 SANS que le test l'attende reste un défaut ; un autre code que celui
              attendu (500 là où le test attend 404) reste un défaut ; un code attendu pour une
              route n'en excuse pas une autre (contre-épreuves) ;
  - LECTURE — les formes d'affirmation reconnues (Playwright, Python, Cypress).

La preuve est une instance réelle de fixture (serveur HTTP local), comme TF-2123.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from forge_tests import authentification
from forge_tests.adaptateurs import personas


class Instance:
    """Une instance servie minimale : /tableau (200 pour tout rôle), /panne (500), le reste 404."""

    def __init__(self) -> None:
        class Gestionnaire(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                chemin = self.path.split("?")[0]
                code = {"/tableau": 200, "/panne": 500}.get(chemin, 404)
                corps = b"x"
                self.send_response(code)
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.serveur.server_address[1]}"

    def __enter__(self) -> Instance:
        self.fil.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.serveur.shutdown()
        self.serveur.server_close()
        self.fil.join(timeout=5)


@pytest.fixture
def instance() -> Iterator[Instance]:
    with Instance() as i:
        yield i


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")


def _produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance, corps_du_test: str
) -> Path:
    """Un produit à un persona, « agent », dont l'unique parcours a pour corps `corps_du_test`."""
    racine = tmp_path / "produit"
    (racine / "forge").mkdir(parents=True)
    (racine / "forge" / "EXIGENCES.json").write_text(
        json.dumps({"projet": "p", "personas": ["Agent"]}), encoding="utf-8"
    )
    (racine / "e2e").mkdir()
    (racine / "e2e" / "agent.spec.ts").write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test('agent', async ({ page }) => {\n" + corps_du_test + "});\n",
        encoding="utf-8",
    )
    etat = racine / "forge" / "agent.json"
    etat.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_QUALIF_STORAGE_STATES", f"agent={etat}")
    monkeypatch.setenv("FORGE_TESTS_QUALIF_URL", instance.url)
    return racine


def _joue(racine: Path) -> list:
    return [f for f in personas.analyser(racine).findings if f.id == "joue:agent"]


# --- VERT ----------------------------------------------------------------------------------------
def test_vert_un_404_que_le_test_attend_n_est_pas_un_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  await page.goto('/tableau');\n"
        "  const reponse = await page.goto('/adresse-inconnue-e2e');\n"
        "  expect(reponse?.status()).toBe(404);\n",
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert "joue:agent" in sortie.surface["elements_exerces"]
    # Le jeu dit pourquoi ce 404 n'est pas un défaut : il ne le tait pas.
    assert "code attendu par le test" in " ".join(sortie.non_juge)


def test_vert_les_formes_d_affirmation_reconnues() -> None:
    formes = {
        "playwright": "const r = await page.goto('/x');\nexpect(r.status()).toEqual(404);\n",
        "python": "r = page.goto('/x')\nassert r.status == 404\n",
        "python_code": "r = client.goto('/x')\nassert r.status_code == 404\n",
        "cypress": "cy.visit('/x');\ncy.request('/x').its('status').should('eq', 404);\n",
    }
    for nom, texte in formes.items():
        assert personas.codes_attendus_par_route(texte) == {"/x": {404}}, nom


# --- ROUGE : les contre-épreuves --------------------------------------------------------------
def test_rouge_le_meme_404_sans_que_le_test_l_attende_reste_un_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  await page.goto('/tableau');\n  await page.goto('/adresse-inconnue-e2e');\n",
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert "/adresse-inconnue-e2e" in _joue(racine)[0].message


def test_rouge_un_autre_code_que_celui_attendu_reste_un_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """Le test attend 404 pour /panne ; l'instance rend 500 : le produit est en défaut."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  const r = await page.goto('/panne');\n  expect(r?.status()).toBe(404);\n",
    )
    constat = _joue(racine)
    assert constat and "/panne" in constat[0].message and "500" in constat[0].message


def test_rouge_un_code_attendu_pour_une_route_n_en_excuse_pas_une_autre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """404 attendu pour /inconnue, mais /autre-inconnue (navigée plus loin, sans attente) rend
    aussi 404 : seul le premier est excusé."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  const r = await page.goto('/inconnue');\n"
        "  expect(r?.status()).toBe(404);\n"
        "  await page.goto('/autre-inconnue');\n",
    )
    message = _joue(racine)[0].message
    assert "/autre-inconnue" in message and "/inconnue :" not in message.replace(
        "/autre-inconnue :", ""
    )


def test_rouge_une_attente_d_un_autre_test_n_excuse_pas_la_route() -> None:
    texte = (
        "test('a', async ({ page }) => {\n  await page.goto('/x');\n});\n"
        "test('b', async ({ page }) => {\n  const r = await page.request.get('/y');\n"
        "  expect(r.status()).toBe(404);\n});\n"
    )
    assert personas.codes_attendus_par_route(texte) == {}


def test_une_redirection_attendue_n_est_pas_un_code_attendu() -> None:
    texte = "const r = await page.goto('/ancienne');\nexpect(r.status()).toBe(302);\n"
    assert personas.codes_attendus_par_route(texte) == {}
