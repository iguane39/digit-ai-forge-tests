"""TF-2274 — `parcours-personas` juge la condition d'un saut dans le contexte où il joue.

Fait remonté (Produit-86, lot 20261106c, RP-47) : la règle TF-2197 (volet c) écarte les fichiers
dont chaque test peut être sauté. Les e2e de ce produit se sautent sans instance désignée
(`PENTEST_E2E_URL`) : le pan les écartait donc même quand l'instance lui était fournie. Il ne
rejouait plus que 3 adresses par profil au lieu de 5 (`/missions/nouvelle` et `/aide` perdues), et
le rapport ne disait pas quels fichiers il écartait.

Décision du 06/11/2026 : juger la condition du saut dans le contexte du pan (instance fournie ou
non), et nommer au rapport les fichiers écartés.

Sens prouvés :
  - ROUGE  — instance fournie, saut qui ne tient qu'à l'URL de l'instance : le fichier compte
             encore comme parcours et ses routes sont jouées ;
  - VERT   — sans instance, le même fichier reste écarté (la règle de TF-2197 tient) ; une
             condition qui ne tient pas à l'instance (`CI`) reste écartée même instance fournie ;
  - NOMMÉ  — tous les fichiers écartés sont nommés au rapport, sans borne à 5, avec le contexte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import personas

NAVIGATION = "  await page.goto('/missions/nouvelle');\n"
SAUT_D_INSTANCE = "test.skip(!process.env.PENTEST_E2E_URL, 'sans instance désignée');\n"
SAUT_D_ENVIRONNEMENT = "test.skip(process.env.CI === 'true', 'pas de URL en intégration');\n"
CORPS = "test('{nom}', async ({{ page }}) => {{\n" + NAVIGATION + "}});\n"


def _spec(saut: str, nom: str) -> str:
    return (
        "import { test, expect } from '@playwright/test';\n" + saut + CORPS.format(nom=nom)
    )


def _ecrire(racine: Path, relatif: str, texte: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


def _produit(tmp_path: Path, fichiers: dict[str, str]) -> Path:
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/EXIGENCES.json",
            json.dumps({"projet": "p", "personas": ["Operateur"]}, ensure_ascii=False))
    for nom, texte in fichiers.items():
        _ecrire(racine, f"e2e/{nom}", texte)
    return racine


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL"):
        monkeypatch.delenv(cle, raising=False)


def test_rouge_instance_fournie_un_saut_qui_ne_tient_qu_a_l_instance_n_ecarte_plus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le défaut du lot, rejoué : l'instance est fournie, le fichier était écarté quand même."""
    racine = _produit(tmp_path, {"operateur.spec.ts": _spec(SAUT_D_INSTANCE, "operateur")})
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "http://127.0.0.1:9")
    assert personas.sautables(racine) == set()
    assert personas.parcours_par_persona(racine, personas.declares(racine)[0])[
        "operateur"] == ["e2e/operateur.spec.ts"]


def test_vert_sans_instance_le_meme_fichier_reste_ecarte(tmp_path: Path) -> None:
    """Contre-épreuve : sans instance, la condition vaut, la règle de TF-2197 tient."""
    racine = _produit(tmp_path, {"operateur.spec.ts": _spec(SAUT_D_INSTANCE, "operateur")})
    assert personas.sautables(racine) == {"e2e/operateur.spec.ts"}


def test_vert_une_condition_etrangere_a_l_instance_reste_ecartee_meme_instance_fournie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le mot URL dans le motif en prose ne fait pas du saut un saut d'instance."""
    racine = _produit(tmp_path, {"operateur.spec.ts": _spec(SAUT_D_ENVIRONNEMENT, "operateur")})
    monkeypatch.setenv("FORGE_TESTS_QUALIF_URL", "http://127.0.0.1:9")
    assert personas.sautables(racine) == {"e2e/operateur.spec.ts"}


def test_pytest_marque_de_module_sur_l_instance_suit_le_meme_contexte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    py = (
        "import os\nimport pytest\nfrom playwright.sync_api import sync_playwright\n"
        "pytestmark = pytest.mark.skipif(\n"
        "    not os.environ.get('PENTEST_E2E_URL'),\n"
        "    reason='sans instance désignée',\n)\n\n"
        "def test_operateur(page):\n    page.goto('/missions/nouvelle')\n"
    )
    racine = _produit(tmp_path, {"test_parcours_operateur.py": py})
    assert personas.sautables(racine) == {"e2e/test_parcours_operateur.py"}
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "http://127.0.0.1:9")
    assert personas.sautables(racine) == set()


def test_le_jeu_rejoue_les_routes_du_fichier_quand_l_instance_est_fournie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le chiffre du lot : la route du fichier sauté sans instance est rejouée avec elle."""
    racine = _produit(tmp_path, {"operateur.spec.ts": _spec(SAUT_D_INSTANCE, "operateur")})
    _ecrire(racine, "etat.json", json.dumps({"cookies": [], "origins": []}))
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("FORGE_TESTS_QUALIF_STORAGE_STATES", "operateur=etat.json")
    jouees: list[str] = []

    def faux(base: str, route: str, etat: dict, attendus: object = frozenset()) -> tuple[str, str]:
        jouees.append(route)
        return "ok", "200"

    monkeypatch.setattr(personas, "_jouer_route", faux)
    jeu = personas.jouer(racine, personas.declares(racine)[0])
    assert "/missions/nouvelle" in jouees
    assert jeu["joues"]["operateur"]["ok"] is True


def test_tous_les_fichiers_ecartes_sont_nommes_et_le_contexte_est_dit(tmp_path: Path) -> None:
    fichiers = {f"p{n}.spec.ts": _spec(SAUT_D_INSTANCE, f"p{n}") for n in range(7)}
    racine = _produit(tmp_path, fichiers)
    sortie = personas.analyser(racine)
    mention = next(m for m in sortie.non_juge if "TOUS les tests peuvent" in m)
    for n in range(7):
        assert f"e2e/p{n}.spec.ts" in mention, f"p{n}.spec.ts écarté sans être nommé"
    assert "7 parcours" in mention
    # le contexte du pan est dit : sans instance, la condition vaut ; avec elle, ils compteraient
    assert "FORGE_TESTS_QUALIF_URL" in mention or "FORGE_TESTS_BASE_URL" in mention


def test_instance_fournie_le_rapport_dit_ce_qui_reste_ecarte_et_pourquoi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, {
        "a.spec.ts": _spec(SAUT_D_INSTANCE, "a"),
        "b.spec.ts": _spec(SAUT_D_ENVIRONNEMENT, "b"),
    })
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "http://127.0.0.1:9")
    sortie = personas.analyser(racine)
    mention = next(m for m in sortie.non_juge if "TOUS les tests peuvent" in m)
    assert "e2e/b.spec.ts" in mention
    assert "e2e/a.spec.ts" not in mention
    assert "instance fournie" in mention
