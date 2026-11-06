"""TF-2269 — une suite backend ROUGE rend FAIL et nomme le test rouge, jamais SKIP.

Fait remonté (Produit-86, lot 20261106a, RP-42) : une suite à 1 test rouge sur 616 rendait les
pans `api`, `data` et `migrations` en SKIP « couverture non mesurable », et le même verdict PARTIEL
qu'un jeu vert. Le rapport était indiscernable d'une suite verte, relu pan par pan pour trouver la
cause.

Décision du 06/11/2026 : une suite backend rouge rend un verdict FAIL qui nomme le test rouge.

Sens prouvés :
  - ROUGE  — sur l'ancien code, les cinq pans qui lisent la mesure de la suite rendaient SKIP ;
  - VERT   — un finding bloquant par test rouge, l'identifiant du test dans le message, verdict FAIL
             du rapport (et non PARTIEL) ;
  - CONTRE-ÉPREUVE — le démon de conteneurs injoignable (la suite n'a jamais tourné) reste un
             préalable absent, jamais un test rouge ; une suite qui ne démarre pas faute d'outil
             reste non mesurée.
Le démon n'est jamais touché : `_run` est remplacé, comme dans TF-0299.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forge_tests import actions, classes, execution
from forge_tests.adaptateurs import api, batch, data, fichiers, migrations
from forge_tests.noyau import rapport

TEST_ROUGE = "tests/test_missions.py::test_creer_une_mission_rend_201"
TRACE_UN_ROUGE = (
    "..........F....\n"
    "=================================== FAILURES ===================================\n"
    "E   assert 500 == 201\n"
    "=========================== short test summary info ============================\n"
    f"FAILED {TEST_ROUGE} - assert 500 == 201\n"
    "1 failed, 615 passed in 41.20s\n"
)
TRACE_DEUX_ROUGES_DONT_UNE_ERREUR = (
    "FAILED tests/test_a.py::test_un - assert 1 == 2\n"
    "ERROR tests/test_b.py::test_deux - fixture 'base' not found\n"
    "1 failed, 1 error, 40 passed in 2.00s\n"
)
TRACE_DOCKER_ABSENT = (
    "ImportError while loading conftest 'C:\\banc\\backend\\conftest.py'.\n"
    "E   docker.errors.DockerException: Error while fetching server API version: "
    "(2, 'CreateFile', 'Le fichier specifie est introuvable.')\n"
)

PANS = [api, data, migrations, batch, fichiers]


def _projet(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n"
        "@app.get('/missions')\ndef lister():\n    return []\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "importer.py").write_text(
        "def importer(chemin):\n    with open(chemin, encoding='utf-8') as f:\n"
        "        return f.read()\n",
        encoding="utf-8",
    )
    (tmp_path / "migrations").mkdir(exist_ok=True)
    (tmp_path / "migrations" / "001_init.sql").write_text(
        "-- +migrate Up\nCREATE TABLE mission (id INT);\n-- +migrate Down\nDROP TABLE mission;\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    return tmp_path


def _suite_rendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trace: str, code: int = 1
) -> Path:
    projet = _projet(tmp_path)

    def faux_run(commande, **_kwargs):
        if "import coverage" in commande:
            return subprocess.CompletedProcess(args=commande, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=commande, returncode=code, stdout=trace, stderr="")

    monkeypatch.setattr(execution, "_run", faux_run)
    monkeypatch.setattr(execution, "schema_openapi", lambda _b: None)
    execution.mesurer.cache_clear()
    assert execution.mesurer(str(projet)) is None
    return projet


def test_la_mesure_releve_les_tests_rouges_nommes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, TRACE_DEUX_ROUGES_DONT_UNE_ERREUR)
    rouge = execution.suite_rouge(projet)
    assert rouge is not None
    assert rouge["code"] == 1
    assert [t["id"] for t in rouge["tests"]] == ["tests/test_a.py::test_un",
                                                 "tests/test_b.py::test_deux"]
    assert rouge["tests"][1]["nature"] == "ERROR"


@pytest.mark.parametrize("module", PANS, ids=lambda m: m.PAN)
def test_rouge_une_suite_rouge_rendait_skip_et_rend_desormais_fail_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module
) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, TRACE_UN_ROUGE)
    sortie = module.analyser(projet)
    assert sortie.verdict == "FAIL", (
        f"{module.PAN} : {sortie.verdict} — {sortie.non_juge[-1] if sortie.non_juge else ''}"
    )
    rouges = [f for f in sortie.findings if f.classe == classes.SUITE_ROUGE]
    assert [f.id for f in rouges] == [f"suite-rouge:{TEST_ROUGE}"]
    assert rouges[0].severite == "bloquant"
    assert TEST_ROUGE in rouges[0].message
    assert "assert 500 == 201" in rouges[0].message
    # le motif honnête reste au non-jugé : la couverture, elle, n'est pas mesurée
    assert any("couverture" in ligne for ligne in sortie.non_juge)


def test_le_rapport_rend_fail_et_non_partiel_avec_une_action_pour_le_test_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, TRACE_UN_ROUGE)
    sorties = [m.analyser(projet) for m in PANS]
    rap = rapport(sorties, [m.PAN for m in PANS])
    assert rap["verdict"] == "FAIL"
    refs = [a for a in rap["actions"] if TEST_ROUGE in a["finding_ref"]]
    assert refs and all(a["categorie"] == "manuelle_dev" for a in refs)
    assert all("DÉFAUT D'AUDITEUR" not in a["attendu"] for a in refs)


def test_la_classe_est_declaree_et_classee() -> None:
    assert classes.SUITE_ROUGE in classes.CLASSES
    assert classes.SUITE_ROUGE in actions._REGLES


def test_le_demon_injoignable_reste_un_prealable_pas_un_test_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contre-épreuve : la suite n'a JAMAIS tourné, aucun test n'est rouge (TF-0299)."""
    projet = _suite_rendant(tmp_path, monkeypatch, TRACE_DOCKER_ABSENT)
    assert execution.suite_rouge(projet) is None
    sortie = api.analyser(projet)
    assert sortie.verdict == "SKIP"
    assert not [f for f in sortie.findings if f.classe == classes.SUITE_ROUGE]


def test_une_suite_qui_ne_demarre_pas_sans_test_nomme_n_invente_aucun_nom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un code non nul sans ligne FAILED/ERROR (erreur de collecte avant tout test) : FAIL tout de
    même, mais sans nom de test fabriqué : le finding désigne la suite entière."""
    projet = _suite_rendant(tmp_path, monkeypatch, "INTERNALERROR> boum\n")
    rouge = execution.suite_rouge(projet)
    assert rouge is not None and rouge["tests"] == []
    sortie = api.analyser(projet)
    assert sortie.verdict == "FAIL"
    assert [f.id for f in sortie.findings if f.classe == classes.SUITE_ROUGE] == [
        "suite-rouge:suite-entiere"
    ]


def test_une_suite_qui_ne_collecte_aucun_test_n_est_pas_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contre-épreuve : le code 5 de pytest (aucun test collecté) n'est pas un test qui échoue."""
    projet = _suite_rendant(tmp_path, monkeypatch, "no tests ran in 0.01s", code=5)
    assert execution.suite_rouge(projet) is None
    assert api.analyser(projet).verdict == "SKIP"
