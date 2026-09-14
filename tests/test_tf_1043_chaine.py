"""TF-1043 : une suite presente dans le depot est jouee par la chaine, ou declaree hors portee.

Mesure fondatrice (Produit-11, RT-62) : deux tests restes rouges six jours durant une
reouverture de faille P0, sans qu'aucun controle ne le remonte — la chaine avait cesse de
jouer une suite presente sur le depot."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forge_tests.chaine import (
    declaration_hors_chaine,
    main,
    suites_du_depot,
    suites_non_jouees,
)


def _ecrire(chemin: Path, contenu: str = "def test_ok():\n    assert True\n") -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# --- suites_du_depot ------------------------------------------------------------


def test_suites_du_depot_trouve_les_deux_conventions_de_nommage(tmp_path: Path) -> None:
    _ecrire(tmp_path / "tests" / "test_a.py")
    _ecrire(tmp_path / "tests" / "b_test.py")
    _ecrire(tmp_path / "tests" / "utilitaire.py")  # ni l'une ni l'autre convention
    trouvees = {p.name for p in suites_du_depot(tmp_path)}
    assert trouvees == {"test_a.py", "b_test.py"}


def test_suites_du_depot_exclut_venv_et_pycache(tmp_path: Path) -> None:
    _ecrire(tmp_path / ".venv" / "lib" / "test_vendor.py")
    _ecrire(tmp_path / "__pycache__" / "test_cache.py")
    assert suites_du_depot(tmp_path) == []


# --- declaration_hors_chaine ------------------------------------------------------


def test_declaration_hors_chaine_bien_formee_est_lue(tmp_path: Path) -> None:
    f = _ecrire(tmp_path / "tests" / "test_legacy.py",
                "# hors-chaine (TF-0999), 2026-09-01 : suite manuelle, jamais automatisee\n"
                "def test_x():\n    assert True\n")
    decl = declaration_hors_chaine(f)
    assert decl == {
        "id": "TF-0999", "date": "2026-09-01", "motif": "suite manuelle, jamais automatisee"
    }


def test_declaration_absente_rend_none(tmp_path: Path) -> None:
    f = _ecrire(tmp_path / "tests" / "test_x.py")
    assert declaration_hors_chaine(f) is None


def test_declaration_incomplete_sans_date_n_est_pas_reconnue(tmp_path: Path) -> None:
    """Une declaration qui ne respecte pas la grammaire (id, date, motif) ne protege rien —
    meme principe que O9 (forge-ops) : une declaration illisible n'est pas une declaration."""
    f = _ecrire(tmp_path / "tests" / "test_x.py",
                "# hors-chaine : suite manuelle sans identifiant ni date\n"
                "def test_x():\n    assert True\n")
    assert declaration_hors_chaine(f) is None


# --- suites_non_jouees (fixture rouge / verte, collecte injectee) ---------------


def test_suite_presente_non_collectee_et_non_declaree_est_un_FINDING(tmp_path: Path) -> None:
    """Fixture ROUGE : reproduction exacte de RT-62 — un fichier de suite existe, la collecte
    reelle de la chaine ne le voit pas, aucune declaration ne l'assume."""
    f = _ecrire(tmp_path / "tests" / "test_secu_p0.py")
    findings = suites_non_jouees(tmp_path, collecte=set())
    assert len(findings) == 1
    assert findings[0]["fichier"] == str(f.resolve())


def test_suite_collectee_par_la_chaine_ne_declenche_rien(tmp_path: Path) -> None:
    """Fixture VERTE : la meme suite, cette fois presente dans la collecte reelle."""
    f = _ecrire(tmp_path / "tests" / "test_secu_p0.py")
    assert suites_non_jouees(tmp_path, collecte={f.resolve()}) == []


def test_suite_non_collectee_mais_declaree_hors_portee_ne_declenche_rien(tmp_path: Path) -> None:
    """Fixture VERTE : la suite manque toujours a la collecte, mais elle porte sa declaration
    datee et motivee — l'absence devient assumee, pas silencieuse."""
    _ecrire(tmp_path / "tests" / "test_manuel.py",
            "# hors-chaine (TF-0999), 2026-09-01 : suite manuelle, jamais automatisee\n"
            "def test_x():\n    assert True\n")
    assert suites_non_jouees(tmp_path, collecte=set()) == []


def test_plusieurs_suites_absentes_sont_TOUTES_nommees(tmp_path: Path) -> None:
    _ecrire(tmp_path / "tests" / "test_a.py")
    _ecrire(tmp_path / "tests" / "test_b.py")
    findings = suites_non_jouees(tmp_path, collecte=set())
    assert len(findings) == 2


def test_aucune_suite_dans_le_depot_ne_declenche_rien(tmp_path: Path) -> None:
    assert suites_non_jouees(tmp_path, collecte=set()) == []


# --- suites_collectees (executeur injecte) --------------------------------------


def test_suites_collectees_parse_la_sortie_collect_only(tmp_path: Path) -> None:
    """Format reel de `pytest --collect-only -q` (pytest 8.x, verifie sur ce depot) : une ligne
    `<chemin>.py: <n>` par fichier collecte — jamais une arborescence `<Module ...>`."""
    f = _ecrire(tmp_path / "tests" / "test_a.py")

    def executeur_faux(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="tests/test_a.py: 1\n", stderr="")

    from forge_tests.chaine import suites_collectees
    assert suites_collectees(tmp_path, executeur=executeur_faux) == {f.resolve()}


# --- integration reelle : ce module se collecte lui-meme ------------------------


def test_ce_depot_ne_signale_aucune_suite_orpheline_de_lui_meme() -> None:
    """Preuve par le geste : la suite forge-tests elle-meme ne laisse aucune suite hors chaine
    (pytest reel, aucune injection) — la regle 1 tourne sur son propre depot sans faux positif."""
    racine = Path(__file__).resolve().parent.parent
    findings = suites_non_jouees(racine)
    assert findings == [], findings


# --- CLI --------------------------------------------------------------------------


def test_cli_racine_introuvable(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main([str(tmp_path / "absent")]) == 2
    assert "introuvable" in capsys.readouterr().err


def test_cli_nombre_arguments_invalide(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err
