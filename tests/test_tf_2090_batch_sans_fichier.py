"""TF-2090 — le pan batch faisait sortir TOUT le rapport en ERREUR sur un projet sans lot.

Fait : `exerces()` lisait `backend/app/batch.py` pour y chercher les codes de rejet SANS
tester sa presence. Sur un projet dont la suite a tourne (couverture mesuree) mais qui n a
aucun module de traitement par lot, `read_text()` levait FileNotFoundError — exception non
attrapee qui emportait l audit entier en ERREUR, alors que `sans_objet()` du meme module
sait deja que ce projet n a pas de lot (NA, « preuve positive d absence »).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import execution
from forge_tests.adaptateurs import batch


def _projet_sans_lot(tmp_path: Path) -> Path:
    """Un backend reel, suite verte, mais AUCUN module de traitement par lot ni declencheur."""
    projet = tmp_path / "produit"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "__init__.py").write_text("", encoding="utf-8")
    (projet / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (projet / "pyproject.toml").write_text(
        '[project]\nname = "p"\ndependencies = ["fastapi>=0.110"]\n', encoding="utf-8"
    )
    return projet


def _suite_verte_sans_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """La suite a tourne (mesure faite) ; batch.py n apparait simplement pas dans la mesure."""
    monkeypatch.setattr(
        execution, "mesurer",
        lambda _banc: {"lignes": {"main.py": frozenset({1})}, "arcs": {}},
    )


def test_batch_sans_fichier_sort_en_na_pas_en_erreur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _suite_verte_sans_batch(monkeypatch)
    # AVANT le correctif : FileNotFoundError remontait et emportait l audit entier (ERREUR).
    sortie = batch.analyser(_projet_sans_lot(tmp_path))
    assert sortie.verdict == "NA", sortie.non_juge
    assert any("SANS OBJET" in n for n in sortie.non_juge)
