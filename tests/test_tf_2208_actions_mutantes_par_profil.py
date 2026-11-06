"""TF-2208 — rejouer les actions mutantes d'un parcours, profil par profil, avec contre-épreuves.

Fait remonté (Produit-86, lot du 05/11/2026, RP-28) : le pan `parcours-personas` rejouait en GET les
routes d'un parcours. Il ne jugeait pas ce qu'un profil FAIT. Décision du 06/11/2026 : rejouer les
actions mutantes du parcours profil par profil, avec contre-épreuves.

Ce jeu MODIFIE l'instance : il n'a lieu que sur déclaration (`FORGE_TESTS_PARCOURS_MUTANTS=1`).
Chaque action mutante à adresse littérale est rejouée sous l'identité du persona dont le parcours la
porte ; la contre-épreuve est le MÊME appel sans identité, qui doit être refusé.

Sens prouvés, contre une instance réelle de fixture (serveur HTTP local) :
  - VERT   — l'action passe sous l'identité du rôle, et le même appel anonyme est refusé : PASS ;
  - ROUGE  — l'action est refusée au rôle ; la contre-épreuve échoue (l'appel anonyme passe : la
             garde n'existe pas) : FAIL nommé, avec l'appel ;
  - SANS OPT-IN — rien n'est rejoué, rien n'est écrit sur l'instance, et le rapport nomme les
             actions non rejouées ;
  - LECTURE — corps littéral lu, corps construit rejoué sans corps et dit.
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
    """/api/demandes : 201 avec session (sinon 401). /api/ouverte : 201 pour tous (aucune garde).
    /api/interdite : 403 pour tous les rôles. Le journal garde la méthode, le chemin, l'identité
    et le corps reçus."""

    def __init__(self) -> None:
        self.recus: list[dict] = []
        instance = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def _repondre(self, code: int) -> None:
                self.send_response(code)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def _traiter(self) -> None:
                longueur = int(self.headers.get("Content-Length") or 0)
                corps = self.rfile.read(longueur).decode() if longueur else ""
                identifie = "session=agent-ok" in (self.headers.get("Cookie") or "")
                chemin = self.path.split("?")[0]
                instance.recus.append({
                    "methode": self.command, "chemin": chemin, "identifie": identifie,
                    "corps": corps,
                })
                if chemin == "/":
                    self._repondre(200)
                elif chemin == "/api/ouverte":
                    self._repondre(201)
                elif chemin == "/api/interdite":
                    self._repondre(403 if identifie else 401)
                elif chemin == "/api/demandes":
                    self._repondre(201 if identifie else 401)
                else:
                    self._repondre(404)

            do_POST = do_PUT = do_PATCH = do_DELETE = do_GET = _traiter  # noqa: N815

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
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL", "FORGE_TESTS_PARCOURS_MUTANTS"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")


def _produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance, appels: str,
    opt_in: bool = True,
) -> Path:
    """Un produit à un persona, « agent », dont le parcours exécute `appels`."""
    racine = tmp_path / "produit"
    (racine / "forge").mkdir(parents=True)
    (racine / "e2e").mkdir()
    (racine / "forge" / "EXIGENCES.json").write_text(
        json.dumps({"projet": "p", "personas": ["Agent"]}), encoding="utf-8"
    )
    (racine / "e2e" / "agent.spec.ts").write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test('agent', async ({ page, request }) => {\n  await page.goto('/');\n"
        + appels + "});\n",
        encoding="utf-8",
    )
    etat = racine / "forge" / "agent.json"
    etat.write_text(json.dumps(
        {"cookies": [{"name": "session", "value": "agent-ok", "domain": "127.0.0.1", "path": "/"}],
         "origins": []}
    ), encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_QUALIF_STORAGE_STATES", f"agent={etat}")
    monkeypatch.setenv("FORGE_TESTS_QUALIF_URL", instance.url)
    if opt_in:
        monkeypatch.setenv("FORGE_TESTS_PARCOURS_MUTANTS", "1")
    return racine


def _mutants(instance: Instance) -> list[dict]:
    return [r for r in instance.recus if r["methode"] != "GET"]


# --- VERT -----------------------------------------------------------------------------------------
def test_vert_l_action_passe_sous_l_identite_et_la_contre_epreuve_est_refusee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  await request.post('/api/demandes', { data: { titre: 'Conge', jours: 3 } });\n",
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert "mute:agent" in sortie.surface["elements_exerces"]
    # Deux appels : sous l'identité (passe), puis SANS identité (refusé) — la contre-épreuve.
    assert [(r["methode"], r["identifie"]) for r in _mutants(instance)] == [
        ("POST", True), ("POST", False),
    ]
    # Le corps littéral est celui qui est rejoué.
    assert json.loads(_mutants(instance)[0]["corps"]) == {"titre": "Conge", "jours": 3}
    texte = " ".join(sortie.non_juge)
    assert "ACTIONS MUTANTES REJOUÉES" in texte and "MODIFIÉE" in texte
    assert "ENCHAÎNEMENT" in texte  # ce que le jeu ne fait pas est dit


# --- ROUGE ----------------------------------------------------------------------------------------
def test_rouge_l_appel_anonyme_accepte_est_une_garde_absente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance, "  await request.post('/api/ouverte', { data: {} });\n"
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    constat = next(f for f in sortie.findings if f.id == "mute:agent")
    assert "CONTRE-ÉPREUVE ratée" in constat.message and "POST /api/ouverte" in constat.message
    assert "la garde n'existe pas" in constat.message


def test_rouge_l_action_refusee_au_role_est_un_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance, "  await request.put('/api/interdite', { data: {} });\n"
    )
    constat = next(f for f in personas.analyser(racine).findings if f.id == "mute:agent")
    assert "PUT /api/interdite" in constat.message and "HTTP 403" in constat.message


def test_vert_un_refus_attendu_par_le_test_n_est_pas_un_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """Le test affirme lui-même le 403 : c'est le comportement vérifié (même règle que TF-2204)."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  const r = await request.put('/api/interdite', { data: {} });\n"
        "  expect(r.status()).toBe(403);\n",
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]


# --- SANS OPT-IN ----------------------------------------------------------------------------------
def test_sans_opt_in_rien_n_est_ecrit_sur_l_instance_et_les_actions_sont_nommees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  await request.post('/api/demandes', { data: { titre: 'x' } });\n", opt_in=False,
    )
    sortie = personas.analyser(racine)
    assert _mutants(instance) == [], "sans opt-in, aucune mutation ne part vers l'instance"
    assert "mute:agent" not in sortie.surface["elements_exerces"]
    texte = " ".join(sortie.non_juge)
    assert "NON rejouée" in texte and "POST /api/demandes" in texte
    assert "FORGE_TESTS_PARCOURS_MUTANTS=1" in texte


def test_le_jeu_de_lecture_reste_en_get_seulement_sans_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  await request.delete('/api/demandes', {});\n", opt_in=False,
    )
    personas.analyser(racine)
    assert {r["methode"] for r in instance.recus} <= {"GET"}


# --- LECTURE --------------------------------------------------------------------------------------
def test_lecture_des_formes_d_action_mutante() -> None:
    texte = (
        "await request.post('/api/a', { data: { x: 1, 'y': 'deux', } });\n"
        "await page.request.patch(\"/api/b\", { data: { n: [1, 2] } });\n"
        "cy.request('DELETE', '/api/c');\n"
        "await request.post('/api/logout');\n"
        "await request.post(`/api/${id}`);\n"
    )
    actions = personas.actions_mutantes(texte)
    assert [(a["methode"], a["route"]) for a in actions] == [
        ("POST", "/api/a"), ("PATCH", "/api/b"), ("DELETE", "/api/c"),
    ]
    assert actions[0]["corps"] == {"x": 1, "y": "deux"}
    assert actions[1]["corps"] == {"n": [1, 2]}
    assert actions[2]["corps"] is None


def test_un_corps_construit_est_rejoue_sans_corps_et_le_rapport_le_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        "  await request.post('/api/demandes', { data: { titre: titreConstruit } });\n",
    )
    sortie = personas.analyser(racine)
    assert _mutants(instance)[0]["corps"] == ""
    assert "sans corps (corps non littéral)" in " ".join(sortie.non_juge)
