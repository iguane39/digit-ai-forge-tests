"""TF-2197 (volets b et c) — le parcours croisé entre profils, et la suite SKIPPED.

Fait remonté (Produit-86, lot du 05/11/2026, RP-17), troisième demande du porteur sur les parcours
par profil : aucun parcours « l'opérateur crée, l'approbateur voit », et une suite de bout en bout
muette sans URL (tous ses tests sautés) comptée comme un parcours.

Décision du 06/11/2026 : parcours croisé entre profils, et e2e SKIPPED comptés au verdict.

Sens prouvés, pour le pan `parcours-personas` :
  - ROUGE  — deux personas déclarés, un parcours chacun, aucun qui les cite ensemble : FAIL nommé
             (`parcours-croise`) ; un parcours dont tous les tests peuvent être sautés n'exerce
             personne ;
  - VERT   — un parcours qui cite deux personas ; un parcours dont UN test seulement est sauté ;
             un saut inconditionnel et motivé (décision lisible) ;
  - SANS OBJET — un seul persona : pas de croisement à exiger ;
  - REMÈDE — ôter la condition du saut, ou écrire le parcours croisé, fait passer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import personas

NAVIGATION = "  await page.goto('/');\n"


def _spec(corps: str, nom: str = "parcours") -> str:
    return (
        "import { test, expect } from '@playwright/test';\n" + corps.replace("{nom}", nom)
    )


def _ecrire(racine: Path, relatif: str, texte: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


def _produit(tmp_path: Path, declares: list[str], parcours: dict[str, str]) -> Path:
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/EXIGENCES.json",
            json.dumps({"projet": "p", "personas": declares}, ensure_ascii=False))
    for fichier, texte in parcours.items():
        _ecrire(racine, f"e2e/{fichier}.spec.ts", texte)
    return racine


def _test_simple(nom: str) -> str:
    return _spec(f"test('{nom}', async ({{ page }}) => {{\n{NAVIGATION}}});\n")


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL"):
        monkeypatch.delenv(cle, raising=False)


def _ids(racine: Path) -> list[str]:
    return sorted(
        f.id for f in personas.analyser(racine).findings if not f.id.startswith("seuil:")
    )


# --- Le parcours croisé ---------------------------------------------------------------------------
def test_rouge_un_parcours_par_profil_sans_parcours_croise(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Operateur", "Approbateur"], {
        "operateur": _test_simple("operateur prepare"),
        "approbateur": _test_simple("approbateur valide"),
    })
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert _ids(racine) == ["parcours-croise"]
    message = next(f for f in sortie.findings if f.id == "parcours-croise").message
    assert "parcours croisé" in message and "l'un agit, l'autre voit" in message


def test_vert_un_parcours_qui_cite_deux_personas_est_le_croisement(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Operateur", "Approbateur"], {
        "operateur": _test_simple("operateur prepare"),
        "approbateur": _test_simple("approbateur valide"),
        "circuit": _test_simple("l operateur cree, l approbateur voit la demande"),
    })
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert "parcours-croise" in sortie.surface["elements_exerces"]


def test_sans_objet_un_seul_persona_n_exige_pas_de_croisement(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Operateur"], {"operateur": _test_simple("operateur")})
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS"
    assert "parcours-croise" not in sortie.surface["elements_exerces"]
    assert "parcours-croise" not in sortie.surface["elements_non_exerces"]


def test_rouge_un_persona_cite_deux_fois_dans_le_meme_parcours_n_est_pas_un_croisement(
    tmp_path: Path,
) -> None:
    racine = _produit(tmp_path, ["Operateur", "Approbateur"], {
        "operateur": _test_simple("operateur puis operateur encore"),
        "approbateur": _test_simple("approbateur"),
    })
    assert "parcours-croise" in _ids(racine)


# --- La suite SKIPPED ne compte pas ---------------------------------------------------------------
SAUT_DE_FICHIER = (
    "test.skip(!process.env.BASE_URL, 'URL absente');\n"
    "test('{nom}', async ({ page }) => {\n" + NAVIGATION + "});\n"
)


def test_rouge_un_parcours_dont_tous_les_tests_peuvent_etre_sautes_n_exerce_personne(
    tmp_path: Path,
) -> None:
    racine = _produit(tmp_path, ["Operateur"], {
        "operateur": _spec(SAUT_DE_FICHIER, "operateur"),
    })
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert _ids(racine) == ["persona:operateur"]
    # Le rapport dit POURQUOI le parcours présent ne compte pas.
    message = next(f for f in sortie.findings if f.id == "persona:operateur").message
    assert "SAUTÉS" in message and "operateur.spec.ts" in message
    assert any("SKIPPED" in m for m in sortie.non_juge)


def test_rouge_autant_de_sauts_conditionnels_que_de_tests(tmp_path: Path) -> None:
    texte = _spec(
        "test('operateur a', async ({ page }) => {\n"
        "  test.skip(!process.env.BASE_URL, 'x');\n" + NAVIGATION + "});\n"
        "test('operateur b', async ({ page }) => {\n"
        "  test.skip(!process.env.BASE_URL, 'x');\n" + NAVIGATION + "});\n"
    )
    racine = _produit(tmp_path, ["Operateur"], {"operateur": texte})
    assert _ids(racine) == ["persona:operateur"]


def test_rouge_une_marque_de_module_pytest_skipif(tmp_path: Path) -> None:
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/EXIGENCES.json", json.dumps({"personas": ["Operateur"]}))
    _ecrire(racine, "e2e/test_operateur.py",
            "import os, pytest\nfrom playwright.sync_api import Page\n"
            "pytestmark = pytest.mark.skipif(not os.environ.get('URL'), reason='x')\n"
            "def test_operateur(page: Page):\n    page.goto('/')\n")
    assert _ids(racine) == ["persona:operateur"]


def test_vert_un_seul_test_saute_sur_deux_laisse_le_parcours_compter(tmp_path: Path) -> None:
    texte = _spec(
        "test('operateur a', async ({ page }) => {\n"
        "  test.skip(!process.env.BASE_URL, 'x');\n" + NAVIGATION + "});\n"
        "test('operateur b', async ({ page }) => {\n" + NAVIGATION + "});\n"
    )
    racine = _produit(tmp_path, ["Operateur"], {"operateur": texte})
    assert _ids(racine) == []


def test_vert_un_saut_inconditionnel_motive_n_est_pas_vise_par_cette_regle(tmp_path: Path) -> None:
    """Décision lisible (`test.skip()` nu) : la règle 9 de la revue la juge, pas celle-ci."""
    assert personas.toujours_sautable("test.skip();\ntest('a', async () => {});\n") is False


def test_remede_joue_ôter_la_condition_du_saut_fait_passer(tmp_path: Path) -> None:
    avant = _produit(
        tmp_path / "a", ["Operateur"], {"operateur": _spec(SAUT_DE_FICHIER, "operateur")}
    )
    assert _ids(avant) == ["persona:operateur"]
    sans_saut = SAUT_DE_FICHIER.replace("test.skip(!process.env.BASE_URL, 'URL absente');\n", "")
    apres = _produit(tmp_path / "b", ["Operateur"], {"operateur": _spec(sans_saut, "operateur")})
    assert _ids(apres) == []
