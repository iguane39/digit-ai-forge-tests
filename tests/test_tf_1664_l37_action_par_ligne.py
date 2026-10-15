"""L37 du socle (TF-1664) — chaque ligne en écart des chapitres du dashboard dit son remède.

Fait mesuré le 15/10/2026 : la recette S-01 (section dashboard) tombait, `check_html.py`
refusant le dashboard du banc rouge en L37 « écart sans remède » sur toutes les tables de
chapitre (F1 à F6, T1 à T4). Les lignes portaient l état « KO » et le constat, et le geste ne
vivait que dans l onglet Actions, sans renvoi ligne à ligne.

La correction : une colonne « action » dans chaque table de chapitre. Elle reprend l action du
rapport quand le constat en porte une (même texte que l onglet Actions), sinon le geste que
l état appelle (adopter le cas, fournir la configuration) ; une ligne tenue dit « aucune
action » et pourquoi.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from forge_tests.adaptateurs import REGISTRE
from forge_tests.livrables import dashboard, surface

CONTEXTE = {
    "produit": "Banc L37",
    "date": "2026-10-15",
    "rapport_nom": "rapport-banc.json",
    "rapport_sha": "a" * 64,
}

RAPPORT = {
    "verdict": "FAIL",
    "couverture_par_pan": {
        "api": {
            "inventorie": 3, "exerce": 1, "ratio": 0.33, "seuil": 0.9,
            "elements_exerces": ["endpoint:GET /api/a"],
            "elements_non_exerces": ["endpoint:GET /api/b"],
        },
    },
    "findings": [
        {
            "id": "code:GET /api/a=500", "pan": "api", "severite": "bloquant",
            "classe": "divergence", "message": "code émis non déclaré",
            "localisation": "app/main.py", "risque": 20,
        }
    ],
    "non_testables": [],
    "pans_non_couverts": [],
    "actions": [
        {
            "finding_ref": "api/code:GET /api/a=500", "categorie": "manuelle_dev",
            "etape_cible": "development", "attendu": "déclarer le 500 dans responses=",
        }
    ],
}


def _page() -> str:
    return dashboard.construire(RAPPORT, CONTEXTE, surface.repartir(RAPPORT, REGISTRE))


def _lignes_du_chapitre(page: str, code: str) -> list[str]:
    tables = re.findall(
        rf'<table[^>]*id="table-chap-{code}-\d+".*?</table>', page, flags=re.S
    )
    return [tr for t in tables for tr in re.findall(r"<tr\b.*?</tr>", t, flags=re.S)]


def test_chaque_ligne_de_chapitre_porte_une_action() -> None:
    page = _page()
    lignes = _lignes_du_chapitre(page, "T1")
    assert lignes, "le chapitre T1 doit porter des lignes"
    entete = lignes[0]
    assert "Action" in entete
    corps = [tr for tr in lignes[1:] if "<td" in tr]
    assert any("déclarer le 500 dans responses=" in tr for tr in corps)
    assert any("écrire ou adopter le cas" in tr for tr in corps)
    assert any("aucune action : élément passé" in tr for tr in corps)


def test_check_html_du_socle_ne_releve_plus_L37(tmp_path: Path) -> None:
    oracle = Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "scripts" / "check_html.py"
    if not oracle.exists():
        pytest.skip("oracle du socle absent de ce poste")
    page = tmp_path / "dashboard.html"
    page.write_text(_page(), encoding="utf-8")
    issue = subprocess.run(
        [sys.executable, str(oracle), str(page)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert "L37" not in issue.stdout, issue.stdout[-2000:]
