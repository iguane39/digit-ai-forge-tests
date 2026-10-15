"""TF-1794 — les pans fichiers et prompts sortaient « non couverts » sur un produit sans objet.

Fait remonté par Produit-83 (lot 20261015b, RE-5, ledger seq 125), sur une suite VERTE :
  - le pan fichiers disait « suite rouge ou environnement du projet absent ». Cause :
    `executees()` rendait None dès que le module d import n apparaissait pas dans la mesure de
    couverture, et None veut dire « suite non exécutée ». Un fichier absent de la mesure d une
    suite qui a tourné est un fichier qu elle n a pas exécuté, pas une suite rouge ;
  - les pans fichiers et prompts sortaient SKIP (« non couverts ») au lieu de NA (« sans
    objet ») sur un produit qui n importe aucun fichier et n appelle aucun modèle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import execution
from forge_tests.adaptateurs import fichiers, prompts


def _projet(tmp_path: Path, *, importer: bool = False) -> Path:
    projet = tmp_path / "produit"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "__init__.py").write_text("", encoding="utf-8")
    (projet / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    if importer:
        (projet / "app" / "importer.py").write_text(
            "def lire(f):\n    if not f:\n        return None\n    return f\n", encoding="utf-8"
        )
    (projet / "pyproject.toml").write_text(
        '[project]\nname = "p"\ndependencies = ["fastapi>=0.110", "sqlalchemy"]\n',
        encoding="utf-8",
    )
    return projet


def _suite_verte(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une mesure faite (suite exécutée, verte) où le module d import n apparaît pas."""
    monkeypatch.setattr(execution, "mesurer", lambda _banc: {"lignes": {"main.py": {1}}})


def test_fichiers_sans_module_d_import_sort_sans_objet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _suite_verte(monkeypatch)
    sortie = fichiers.analyser(_projet(tmp_path))
    assert sortie.verdict == "NA"
    assert not any("suite rouge" in n for n in sortie.non_juge)


def test_fichiers_module_jamais_execute_par_une_suite_verte_est_non_exerce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas fautif reste accusé : le module existe, la suite verte ne l a jamais exécuté."""
    _suite_verte(monkeypatch)
    sortie = fichiers.analyser(_projet(tmp_path, importer=True))
    assert sortie.verdict == "FAIL"
    assert not any("suite rouge" in n for n in sortie.non_juge)


def test_fichiers_suite_non_executee_reste_non_mesurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(execution, "mesurer", lambda _banc: None)
    sortie = fichiers.analyser(_projet(tmp_path, importer=True))
    assert sortie.verdict == "SKIP"


def test_prompts_sans_dependance_de_modele_ni_prompt_sort_sans_objet(tmp_path: Path) -> None:
    sortie = prompts.analyser(_projet(tmp_path))
    assert sortie.verdict == "NA", sortie.non_juge
    assert any("SANS OBJET" in n and "pyproject.toml" in n for n in sortie.non_juge)


def test_prompts_dependance_de_modele_declaree_reste_non_enumerable(tmp_path: Path) -> None:
    """Le cas conforme au contrat d avant : un client de modèle déclaré sans prompt adressable
    n est pas une preuve d absence, le pan reste SKIP."""
    projet = _projet(tmp_path)
    (projet / "pyproject.toml").write_text(
        '[project]\nname = "p"\ndependencies = ["anthropic>=0.40"]\n', encoding="utf-8"
    )
    assert prompts.analyser(projet).verdict == "SKIP"


def test_prompts_sans_aucun_manifeste_n_a_pas_de_preuve(tmp_path: Path) -> None:
    projet = tmp_path / "nu"
    (projet / "src").mkdir(parents=True)
    (projet / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert prompts.analyser(projet).verdict == "SKIP"
