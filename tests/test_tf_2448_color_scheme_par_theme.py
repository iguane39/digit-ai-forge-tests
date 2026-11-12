"""TF-2448 — le gabarit du dashboard déclare `color-scheme` en CSS pour chaque thème.

Fait mesuré le 12/11/2026 : deux tests de `test_tf_2101_gabarit_oracles_design.py` rendaient un
échec depuis que SC4 d'`oracle-surcouche` (forge-design) s'évalue dès qu'un thème sombre existe
(TF-2384). Le gabarit ne posait `color-scheme` qu'en balise `<meta>` : SC4 ne compte que la
déclaration CSS, par thème, parce que la balise annonce ce que la page supporte et ne suit pas la
bascule (même cause que TF-2406 pour le socle des pages).

Correction : `color-scheme:light` au bloc `:root`, `color-scheme:dark` au bloc
`:root[data-theme="dark"]`, `color-scheme:light` au bloc d'impression (le papier est clair).

Sens prouvés :
  - VERT   — les trois déclarations sont dans leur bloc, et `oracle-surcouche` ne trouve aucun
             écart SC4 sur la page ;
  - ROUGE  — la page privée de ses déclarations CSS (la balise `<meta>` seule, état d'origine)
             est refusée par `oracle-surcouche` pour SC4, aux deux endroits (thème de base,
             thème sombre) ; sans oracle sur le poste, la preuve se dégrade et le dit.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests.livrables import dashboard

RACINE = Path(__file__).resolve().parent.parent


def _oracle_surcouche() -> Path | None:
    base = Path(os.environ["FORGE_ROOT"]) if os.environ.get("FORGE_ROOT") else RACINE.parent
    chemin = base / "digit-ai-forge-design" / "oracles" / "oracle-surcouche.mjs"
    return chemin if chemin.is_file() else None


def _page() -> str:
    spec = importlib.util.spec_from_file_location(
        "preuve_dashboard_socle", RACINE / "recette" / "preuve_dashboard_socle.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dashboard.construire(module.RAPPORT, module.CONTEXTE, module.CHAPITRES)


def _bloc(page: str, selecteur: str) -> str:
    """Le corps du premier bloc CSS dont le sélecteur est exactement `selecteur`."""
    trouve = re.search(re.escape(selecteur) + r"\s*\{([^{}]*)\}", page)
    assert trouve, f"bloc {selecteur} absent de la page"
    return trouve.group(1)


def _sans_color_scheme_css(page: str) -> str:
    """L'état d'origine : aucune déclaration CSS, la balise <meta name="color-scheme"> reste."""
    return re.sub(r"color-scheme\s*:\s*[a-z ]+;", "", page)


def _surcouche(page: str, dossier: Path, nom: str) -> dict:
    fichier = dossier / f"{nom}.html"
    fichier.write_text(page, encoding="utf-8")
    sortie = subprocess.run(
        ["node", str(_oracle_surcouche()), str(fichier)],
        capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
    )
    assert sortie.returncode in (0, 1), sortie.stderr[-600:]
    return json.loads(sortie.stdout)


def _sc4(rapport: dict) -> list[dict]:
    return [f for f in rapport["findings"] if f["regle"] == "SC4" and f["sev"] == "bloquant"]


def test_vert_chaque_theme_declare_son_color_scheme_en_css() -> None:
    page = _page()
    assert re.search(r"color-scheme\s*:\s*light", _bloc(page, ":root"))
    assert re.search(r"color-scheme\s*:\s*dark", _bloc(page, ':root[data-theme="dark"]'))
    assert re.search(
        r"color-scheme\s*:\s*light", _bloc(page, ':root, :root[data-theme="dark"]')
    ), "le papier est toujours clair : le bloc d'impression redit light"
    # La balise meta reste : elle annonce ce que la page supporte, le CSS décide du rendu.
    assert '<meta name="color-scheme"' in page


needs_oracle = pytest.mark.skipif(
    shutil.which("node") is None or _oracle_surcouche() is None,
    reason="node ou digit-ai-forge-design absents du poste : preuve partielle (SKIP motivé)",
)


@needs_oracle
def test_vert_oracle_surcouche_ne_trouve_aucun_ecart_sc4(tmp_path: Path) -> None:
    rapport = _surcouche(_page(), tmp_path, "vert")
    assert not _sc4(rapport), [f["msg"] for f in _sc4(rapport)]
    assert rapport["verdict"] == "PASS"


@needs_oracle
def test_rouge_sans_declaration_css_oracle_surcouche_refuse_sc4_aux_deux_themes(
    tmp_path: Path,
) -> None:
    page = _page()
    degradee = _sans_color_scheme_css(page)
    assert degradee != page, "la fixture rouge doit changer la page"
    assert '<meta name="color-scheme"' in degradee, "la balise meta reste : c'est l'état d'origine"
    rapport = _surcouche(degradee, tmp_path, "rouge")
    messages = " | ".join(f["msg"] for f in _sc4(rapport))
    assert rapport["verdict"] == "FAIL"
    assert "thème de base" in messages
    assert "color-scheme: dark" in messages
