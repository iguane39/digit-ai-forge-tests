"""TF-2254 — les essais de la suite du produit alimentent le rapport, et un essai non exécuté pèse
sur le verdict PARTIEL.

Fait remonté par la campagne du 06/11/2026 (reste de TF-2197) : `rapport(..., essais=…)` n'avait
aucun appelant. `__main__` ne l'alimentait pas, donc des essais `non_execute` (tests sautés) ne
pesaient jamais sur le verdict : un rapport « 27 passés, 1 sauté » restait PASS, et personne ne
regardait lequel (TF-0605).

Décision du 06/11/2026 : `__main__` alimente `rapport(essais=…)` et un essai non exécuté pèse sur le
verdict PARTIEL.

Sens prouvés :
  - ROUGE  — un essai non exécuté laissait le verdict à PASS ; `essais_de_la_cible` n'existait pas ;
  - VERT   — le verdict est PARTIEL, l'essai est nommé au non-jugé ; la suite backend lue par
             `--junitxml` alimente la section `essais` du rapport de l'audit ;
  - CONTRE-ÉPREUVE — des essais tous passants laissent PASS ; sans essais fournis, le verdict est
             inchangé ; un FAIL reste un FAIL.
Le pan front lit de même le JUnit de Playwright (même lecteur, `PLAYWRIGHT_JUNIT_OUTPUT_NAME`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forge_tests import __main__ as principal
from forge_tests import execution
from forge_tests.noyau import Essai, SortieAdaptateur, rapport

JUNIT_BACKEND = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="3">
<testcase classname="tests.test_a" name="test_passe" time="0.01"/>
<testcase classname="tests.test_a" name="test_saute" time="0.00">
<skipped type="pytest.skip" message="base absente">tests/test_a.py:12: base absente</skipped>
</testcase>
<testcase classname="tests.test_b" name="test_aussi" time="0.01"/>
</testsuite></testsuites>
"""

JUNIT_PLAYWRIGHT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="" tests="2"><testsuite name="parcours.spec.ts" tests="2">
<testcase name="demandeur crée une mission" classname="parcours.spec.ts"/>
<testcase name="approbateur voit la mission" classname="parcours.spec.ts"><skipped/></testcase>
</testsuite></testsuites>
"""


def _sortie(pan: str, verdict: str = "PASS") -> SortieAdaptateur:
    return SortieAdaptateur("a", pan, "cible", verdict)  # type: ignore[arg-type]


def _essai(verdict: str, nom: str = "t") -> Essai:
    pourquoi = None if verdict == "passant" else "base absente"
    return Essai(id=f"tests.test_a::{nom}", pan="back", verdict=verdict, pourquoi=pourquoi)  # type: ignore[arg-type]


# --- Le verdict ----------------------------------------------------------------------------------
def test_rouge_un_essai_non_execute_pese_sur_le_verdict_partiel() -> None:
    rap = rapport([_sortie("api")], ["api"], essais=[_essai("passant"), _essai("non_execute")])
    assert rap["pans_non_couverts"] == []
    assert rap["verdict"] == "PARTIEL"
    ligne = next(m for m in rap["non_juge"] if "NON EXÉCUTÉ" in m)
    assert "tests.test_a::t" in ligne and "PARTIEL" in ligne


def test_des_essais_tous_passants_laissent_le_verdict_inchange() -> None:
    essais = [_essai("passant", "a"), _essai("passant", "b")]
    rap = rapport([_sortie("api")], ["api"], essais=essais)
    assert rap["verdict"] == "PASS"
    assert not any("NON EXÉCUTÉ" in m for m in rap["non_juge"])


def test_sans_essais_fournis_le_verdict_est_celui_d_avant() -> None:
    assert rapport([_sortie("api")], ["api"])["verdict"] == "PASS"
    assert rapport([_sortie("api", "FAIL")], ["api"])["verdict"] == "FAIL"


def test_un_essai_non_execute_ne_masque_pas_un_echec_quand_aucun_pan_n_est_manquant() -> None:
    """La précédence existante ne bouge pas : PARTIEL (pan manquant) > FAIL > PASS. Un essai non
    exécuté s'ajoute aux causes de PARTIEL, au même rang qu'un pan non couvert."""
    rap = rapport([_sortie("api", "FAIL")], ["api"], essais=[_essai("non_execute")])
    assert rap["verdict"] == "PARTIEL"
    assert rap["essais"]["totaux"]["non_execute"] == 1


# --- La source : la suite du produit, lue en JUnit ------------------------------------------------
def _projet(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    return tmp_path


def _faux_run_ecrivant_le_junit(code: int, xml: str):
    def faux(commande, **_kwargs):
        if "import coverage" in commande:
            return subprocess.CompletedProcess(args=commande, returncode=0, stdout="", stderr="")
        if "json" in commande and "coverage" in commande:
            return subprocess.CompletedProcess(
                args=commande, returncode=0, stdout='{"files": {}}', stderr=""
            )
        chemins = [c.split("=", 1)[1] for c in commande if str(c).startswith("--junitxml=")]
        if chemins:
            Path(chemins[0]).write_text(xml, encoding="utf-8")
        return subprocess.CompletedProcess(args=commande, returncode=code, stdout="", stderr="")

    return faux


@pytest.mark.parametrize("code", [0, 1])
def test_la_suite_backend_est_lue_en_junit_qu_elle_soit_verte_ou_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    projet = _projet(tmp_path)
    monkeypatch.setattr(execution, "_run", _faux_run_ecrivant_le_junit(code, JUNIT_BACKEND))
    execution.mesurer.cache_clear()
    execution.mesurer(str(projet))
    essais = execution.essais_de_la_cible(projet)
    assert essais is not None
    assert [(e.id, e.verdict) for e in essais] == [
        ("tests.test_a::test_passe", "passant"),
        ("tests.test_a::test_saute", "non_execute"),
        ("tests.test_b::test_aussi", "passant"),
    ]
    assert essais[1].pourquoi and "base absente" in essais[1].pourquoi


def test_sans_suite_lancee_aucun_essai_n_est_invente(tmp_path: Path) -> None:
    execution.mesurer.cache_clear()
    assert execution.essais_de_la_cible(tmp_path) is None


def test_le_pan_front_lit_le_junit_de_playwright(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    front = tmp_path / "frontend"
    (front / "node_modules").mkdir(parents=True)
    (front / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    monkeypatch.setattr(execution.shutil, "which", lambda _n: "npx")

    def faux(commande, **kwargs):
        sortie = (kwargs.get("env") or {}).get("PLAYWRIGHT_JUNIT_OUTPUT_NAME")
        assert sortie, "le JUnit de Playwright n'est pas demandé (PLAYWRIGHT_JUNIT_OUTPUT_NAME)"
        assert "--reporter=line,junit" in commande
        Path(sortie).write_text(JUNIT_PLAYWRIGHT, encoding="utf-8")
        return subprocess.CompletedProcess(args=commande, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(execution, "_run", faux)
    execution.front_execute.cache_clear()
    execution.front_execute(str(tmp_path))
    essais = execution.essais_de_la_cible(tmp_path)
    assert essais is not None
    assert [(e.pan, e.verdict) for e in essais] == [("front", "passant"), ("front", "non_execute")]


# --- Le câblage : __main__ alimente le rapport ---------------------------------------------------
def test_l_audit_alimente_la_section_essais_du_rapport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`analyser` (le coeur de `__main__`) passe les essais de la suite au rapport."""
    vus: list[object] = []
    vrai_rapport = principal.rapport

    def espion(*args, **kwargs):
        vus.append(kwargs.get("essais"))
        return vrai_rapport(*args, **kwargs)

    monkeypatch.setattr(principal, "rapport", espion)
    monkeypatch.setattr(
        execution, "essais_de_la_cible",
        lambda _c: [_essai("passant", "a"), _essai("non_execute", "b")],
    )
    rap = principal.analyser(tmp_path, pans=["supabase"])
    assert vus and vus[0] is not None and len(vus[0]) == 2  # type: ignore[arg-type]
    assert rap["essais"]["fourni"] is True
    assert rap["verdict"] == "PARTIEL"
