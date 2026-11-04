"""TF-2101 — le tableau de bord généré échouait à quatre oracles de forge-design.

Fait remonté (lot Produit-86 du 03/11/2026) : la page livrée sous `output/` sortait de
`run-oracles-design.mjs` en FAIL sur quatre oracles de la critique d implémentation :
  - `oracle-slop`   : bandeaux latéraux (S1), blanc pur (S4), emoji (S6) ;
  - `oracle-tokens` : écarts durs de couleur en dur (T1), d échelle 4pt (T3) et de focus (T8) ;
  - `oracle-motion` : aucune révocation `prefers-reduced-motion` (R10) ;
  - `oracle-bascule`: aucune palette sombre sous `[data-theme="dark"]` (B-T4).

La cause est dans le GABARIT (`livrables/dashboard.py`), pas dans une page : chaque page générée
héritait des mêmes écarts. Ici le gabarit est corrigé à la source, et sa sortie est jugée par
`run-oracles-design` — sur deux pages, parce que les emoji vivaient dans un chemin (les
déclarations du projet) que la page de preuve du socle n emprunte pas.

Trois sens :
  - VERT   — les deux pages passent `run-oracles-design` (verdict PASS, quatre oracles PASS) ;
  - ROUGE  — chaque écart d origine, réinjecté dans une page verte, fait échouer SON oracle pour
             SA règle (S1, S4, S6, T1, T3, R10, B-T4) : la règle est prouvée, pas supposée ;
  - SKIP   — node ou forge-design absents du poste : la preuve se dégrade et le dit.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import declarations
from forge_tests.adaptateurs import REGISTRE
from forge_tests.livrables import dashboard, surface

RACINE = Path(__file__).resolve().parent.parent
QUATRE = ("oracle-slop", "oracle-tokens", "oracle-motion", "oracle-bascule")
JOUR = dt.date(2026, 8, 14)


def _orchestrateur() -> Path | None:
    base = Path(os.environ["FORGE_ROOT"]) if os.environ.get("FORGE_ROOT") else RACINE.parent
    chemin = base / "digit-ai-forge-design" / "oracles" / "run-oracles-design.mjs"
    return chemin if chemin.is_file() else None


pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or _orchestrateur() is None,
    reason="node ou digit-ai-forge-design absents du poste : preuve partielle (SKIP motivé)",
)


def _juger(page: str, dossier: Path, nom: str) -> dict[str, dict]:
    """`run-oracles-design` sur la page ; rend {oracle: sortie} et le verdict global sous `_`."""
    fichier = dossier / f"{nom}.html"
    fichier.write_text(page, encoding="utf-8")
    sortie = subprocess.run(
        ["node", str(_orchestrateur()), str(fichier), "--json-only"],
        capture_output=True, text=True, encoding="utf-8", timeout=300, check=False,
    )
    assert sortie.returncode in (0, 1), sortie.stderr[-600:]
    charge = json.loads(sortie.stdout)
    rendu = {o["oracle"]: o for o in charge["oracles"]}
    rendu["_"] = {"verdict": charge["verdict"], "exit": sortie.returncode}
    return rendu


def _regles(sortie: dict) -> set[str]:
    return {f["regle"] for f in sortie["findings"] if f["sev"] in ("bloquant", "majeur")}


def _page_du_socle() -> str:
    spec = importlib.util.spec_from_file_location(
        "preuve_dashboard_socle", RACINE / "recette" / "preuve_dashboard_socle.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dashboard.construire(module.RAPPORT, module.CONTEXTE, module.CHAPITRES)


def _page_des_declarations(racine: Path) -> str:
    """Un rapport dont trois constats portent chacun une déclaration : retenue, refusée, périmée.
    Les trois badges sont ceux qui portaient les emoji."""
    (racine / "tests").mkdir(parents=True)
    (racine / "tests" / "preuve.spec.ts").write_text("// preuve", encoding="utf-8")
    ids = ("qualif:effet:/:0:a", "qualif:effet:/:0:b", "qualif:effet:/:0:c")
    base = {"motif": "conteste", "par": "equipe-front", "date": "2026-08-01"}
    lignes = [
        {**base, "constat": f"qualif/{ids[0]}", "preuve": "tests/preuve.spec.ts"},
        {**base, "constat": f"qualif/{ids[1]}", "preuve": "tests/disparu.spec.ts"},
        {**base, "constat": f"qualif/{ids[2]}", "preuve": "tests/preuve.spec.ts",
         "expire_le": "2026-08-05"},
    ]
    (racine / "forge").mkdir()
    (racine / "forge" / "constats-contestes.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8"
    )
    rapport = {
        "couverture_par_pan": {
            "qualif": {"inventorie": 3, "exerce": 0, "ratio": 0.0, "seuil": 0.8,
                       "elements_exerces": [], "elements_non_exerces": list(ids)}
        },
        "findings": [
            {"id": i, "pan": "qualif", "classe": "affordance-sans-effet",
             "localisation": "src/App.tsx", "message": "formulaire sans action",
             "severite": "bloquant", "risque": 45}
            for i in ids
        ],
        "bandes_de_risque": {"critique": 3, "standard": 0, "differe": 0, "non_cote": 0},
        "actions": [
            {"finding_ref": f"qualif/{i}", "categorie": "manuelle_dev",
             "etape_cible": "development", "attendu": "attacher un effet"}
            for i in ids
        ],
        "non_testables": [], "pans_non_couverts": [], "modules": [], "verdict": "FAIL",
    }
    rapport = declarations.appliquer(rapport, racine, JOUR)
    contexte = {"produit": "banc", "date": "2026-08-14", "rapport_nom": "rapport.json",
                "rapport_sha": "0" * 64}
    page = dashboard.construire(rapport, contexte, surface.repartir(rapport, REGISTRE))
    for badge in ("Retenue", "Refusée", "Périmée"):
        assert badge in page, f"la page de preuve doit exercer le badge « {badge} »"
    return page


@pytest.fixture(scope="module")
def pages(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    racine = tmp_path_factory.mktemp("tf2101")
    return {"socle": _page_du_socle(), "declarations": _page_des_declarations(racine / "projet")}


@pytest.fixture(scope="module")
def dossier(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("tf2101-pages")


# --- VERT -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("nom", ["socle", "declarations"])
def test_vert_le_gabarit_passe_run_oracles_design(
    pages: dict[str, str], dossier: Path, nom: str
) -> None:
    jugement = _juger(pages[nom], dossier, f"vert-{nom}")
    echecs = {o: _regles(jugement[o]) for o in QUATRE if jugement[o]["verdict"] != "PASS"}
    assert not echecs, f"oracles en échec sur la page « {nom} » : {echecs}"
    assert jugement["_"] == {"verdict": "PASS", "exit": 0}


# --- ROUGE : chaque écart d origine, réinjecté, fait échouer son oracle pour sa règle -------------
def _ajouter_style(page: str, css: str) -> str:
    return page.replace("</style>", css + "\n</style>", 1)


def _sans_revocation_du_mouvement(page: str) -> str:
    assert "prefers-reduced-motion: reduce" in page
    return page.replace("prefers-reduced-motion: reduce", "prefers-reduced-motion: no-preference")


def _sans_palette_sombre(page: str) -> str:
    assert 'data-theme="dark"' in page
    return page.replace('data-theme="dark"', 'data-theme="sombre"')


ROUGES = [
    ("S1-bandeau-lateral", "oracle-slop", "S1",
     lambda p: _ajouter_style(p, ".verdict{border-left:4px solid var(--blue)}")),
    ("S4-blanc-pur", "oracle-slop", "S4",
     lambda p: _ajouter_style(p, ".b-pass{color:#fff}")),
    ("S6-emoji", "oracle-slop", "S6",
     lambda p: p.replace("</body>", "<p>⚖ Retenue</p></body>", 1)),
    ("T1-couleur-en-dur", "oracle-tokens", "T1",
     lambda p: _ajouter_style(p, ".b-pass{color:#fefefe}")),
    ("T3-echelle-4pt", "oracle-tokens", "T3",
     lambda p: _ajouter_style(p, ".card{padding:18px 22px}")),
    ("R10-mouvement-non-revoque", "oracle-motion", "R10", _sans_revocation_du_mouvement),
    ("B-T4-palette-sombre-absente", "oracle-bascule", "B-T4", _sans_palette_sombre),
]


@pytest.mark.parametrize(
    ("cas", "oracle", "regle", "alterer"), ROUGES, ids=[r[0] for r in ROUGES]
)
def test_rouge_l_ecart_d_origine_fait_echouer_son_oracle(
    pages: dict[str, str], dossier: Path, cas: str, oracle: str, regle: str, alterer: object
) -> None:
    page = alterer(pages["declarations"])  # type: ignore[operator]
    assert page != pages["declarations"], "la fixture rouge doit changer la page"
    jugement = _juger(page, dossier, f"rouge-{cas}")
    assert jugement[oracle]["verdict"] == "FAIL", f"{oracle} aurait dû refuser « {cas} »"
    assert regle in _regles(jugement[oracle]), (
        f"{oracle} refuse, mais pas pour {regle} : {_regles(jugement[oracle])}"
    )


def test_la_bascule_ecrit_dark_et_relit_l_ancienne_valeur_persistee(
    pages: dict[str, str]
) -> None:
    """Le changement de l attribut ne perd pas le choix d un lecteur qui avait persisté
    « sombre » avant TF-2101 : l ancienne valeur est encore lue, la nouvelle est écrite."""
    page = pages["socle"]
    assert "setAttribute('data-theme', 'dark')" in page
    assert "memorise === 'dark' || memorise === 'sombre'" in page
