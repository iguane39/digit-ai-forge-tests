"""TF-1767 — l audit jugeait un dossier que git ignore, hors du produit.

Fait remonté par Produit-82 (lot 20261015b, RT-16, ledger seq 75) : lancé sur la racine du
produit, forge-tests a inventorié et jugé `vendor-check/`, clone du code amont ignoré par git.
493 constats sur un autre code, presque tous sur ses tests et son interface. Seule la mutation
acceptait une exclusion (`FORGE_TESTS_MUTATION_EXCLUT`) ; l audit a dû être rejoué sur une copie
propre du dépôt.

La règle corrigée : ce que le dépôt ignore sort du périmètre par défaut, nommé au rapport
(`perimetre_exclu_git`), réclamable par son nom dans `FORGE_TESTS_INCLURE`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import disposition, exclusions, revue
from forge_tests.adaptateurs import interface, prompts

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent du poste")


def _depot(tmp_path: Path) -> Path:
    racine = tmp_path / "produit"
    (racine / "app").mkdir(parents=True)
    (racine / "app" / "__init__.py").write_text("", encoding="utf-8")
    (racine / "app" / "page.html").write_text("<button>Valider</button>\n", encoding="utf-8")
    (racine / "tests").mkdir()
    (racine / "tests" / "test_app.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    amont = racine / "vendor-check"
    (amont / "upstream" / "tests").mkdir(parents=True)
    (amont / "upstream" / "__init__.py").write_text("", encoding="utf-8")
    (amont / "upstream" / "ui.html").write_text("<button>Amont</button>\n", encoding="utf-8")
    (amont / "upstream" / "tests" / "test_amont.py").write_text(
        "def test_b():\n    pass\n", encoding="utf-8"
    )
    (amont / "upstream" / "prompt.md").write_text("Tu es un assistant.\n", encoding="utf-8")
    (racine / ".gitignore").write_text("vendor-check/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(racine)], check=True)
    exclusions._CACHE_GIT.clear()
    return racine


def test_dossier_ignore_par_git_sort_des_parcours_des_pans(tmp_path: Path) -> None:
    racine = _depot(tmp_path)
    html = {p.relative_to(racine).as_posix() for p in interface._fichiers(racine, (".html",))}
    assert html == {"app/page.html"}
    textes = {p.relative_to(racine).as_posix() for p in prompts._fichiers(racine)}
    assert not [t for t in textes if t.startswith("vendor-check/")]
    suites = {p.relative_to(racine).as_posix() for p in revue._fichiers_de_test(racine)}
    assert suites == {"tests/test_app.py"}
    candidats = {p.name for p in disposition._candidats(racine)}
    assert "vendor-check" not in candidats
    assert "app" in candidats


def test_exclusion_publiee_au_rapport_et_reclamable_par_son_nom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _depot(tmp_path)
    assert exclusions.ignores_git(racine) == ["vendor-check"]
    # Le geste explicite du projet : il réclame le dossier, l audit le juge de nouveau.
    monkeypatch.setenv("FORGE_TESTS_INCLURE", "vendor-check")
    exclusions._CACHE_GIT.clear()
    assert exclusions.ignores_git(racine) == []
    assert not exclusions.ignore_par_git(racine / "vendor-check" / "upstream", racine)


def test_dossier_versionne_ou_hors_depot_reste_juge(tmp_path: Path) -> None:
    """Le cas conforme : sans dépôt git, ou pour un dossier versionné, rien ne change ; et un
    `dist/` ignoré reste soumis à la politique de chaque pan, pas retiré par ce filtre."""
    sans_git = tmp_path / "sans-git"
    (sans_git / "vendor-check").mkdir(parents=True)
    exclusions._CACHE_GIT.clear()
    assert not exclusions.ignore_par_git(sans_git / "vendor-check", sans_git)
    racine = _depot(tmp_path)
    (racine / "dist").mkdir()
    (racine / ".gitignore").write_text("vendor-check/\ndist/\n", encoding="utf-8")
    exclusions._CACHE_GIT.clear()
    assert exclusions.ignores_git(racine) == ["vendor-check"]
    assert not exclusions.ignore_par_git(racine / "app" / "page.html", racine)
