"""TF-2251 — les adaptateurs localisent leurs constats sous la racine du front DÉCOUVERTE.

Fait remonté par la campagne du 06/11/2026 (TF-2222) : la racine du front se découvre désormais
(`disposition.racine_front` : manifeste, `frontend`, puis `package.json`), mais clavier, contraste,
plancher, visuel et accessibilité écrivaient encore la source d'un élément et la source de risque de
leurs constats avec `cible / "frontend"` en dur. Le verdict ne change pas ; la localisation désigne
un dossier qui n'existe pas pour un front sous `FRONT/`, et la fréquence de modification (git) est
mesurée sur ce dossier fantôme, donc retombe sur la valeur neutre.

Sens prouvés : ROUGE (front sous `FRONT/` : la source désigne `frontend`) et VERT (elle désigne
`FRONT`), avec contre-épreuve (un front au nom conventionnel garde `frontend`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from forge_tests.adaptateurs import accessibilite, clavier, contraste, plancher, visuel

ROUTES = (["/", "/demandes"], "routes déclarées pour la recette")


def _front_sous(racine: Path, dossier: str) -> Path:
    cible = racine / "projet"
    (cible / dossier).mkdir(parents=True)
    (cible / dossier / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"react": "^18"}}), encoding="utf-8"
    )
    return cible


def _enregistreur(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[str]:
    """Remplace `coter` du module par un enregistreur de la source de risque reçue."""
    sources: list[str] = []

    def faux(pan: str, identifiant: str, source: str) -> int:
        sources.append(source)
        return 1

    monkeypatch.setattr(module, "coter", faux)
    return sources


def _brancher(monkeypatch: pytest.MonkeyPatch, module: Any, resultats: dict[str, Any]) -> None:
    monkeypatch.setattr(module.accessibilite, "routes_a_auditer", lambda _c: ROUTES)
    monkeypatch.setattr(module, "parcourir", lambda *a, **k: (resultats, []))
    if hasattr(module, "_mesure_js"):
        monkeypatch.setattr(module, "_mesure_js", lambda: "() => ({})")


@pytest.mark.parametrize("module", [clavier, contraste, plancher])
@pytest.mark.parametrize(
    "dossier,attendu", [("FRONT", "FRONT"), ("frontend", "frontend")]
)
def test_l_inventaire_est_localise_sous_la_racine_du_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: Any, dossier: str, attendu: str
) -> None:
    cible = _front_sous(tmp_path, dossier)
    monkeypatch.setattr(module.accessibilite, "routes_a_auditer", lambda _c: ROUTES)
    sources = {e.source for e in module.inventaire(cible)}
    assert sources == {str(cible / attendu)}, (
        f"{module.__name__} localise ses éléments sous {sources}, le front est sous {attendu}"
    )


def test_clavier_localise_ses_constats_sous_la_racine_du_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cible = _front_sous(tmp_path, "FRONT")
    sources = _enregistreur(monkeypatch, clavier)
    releve = {"total": 3, "examines": 3, "sans_indicateur": ["a.lien"],
              "k2": {"piege": "input#q"}, "evitement": "absent"}
    _brancher(monkeypatch, clavier, {"/": releve})
    sortie = clavier.analyser(cible)
    assert sortie.verdict == "FAIL"
    assert sources, "aucun constat produit : la preuve ne porte sur rien"
    assert set(sources) == {str(cible / "FRONT")}


def test_contraste_localise_ses_constats_sous_la_racine_du_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cible = _front_sous(tmp_path, "FRONT")
    sources = _enregistreur(monkeypatch, contraste)
    _brancher(monkeypatch, contraste, {
        "/": {"v2_contrast": [{"what": "p.mention", "detail": "2.11:1 < 4.5:1"}],
              "unmeasured": []},
    })
    sortie = contraste.analyser(cible)
    assert sortie.verdict == "FAIL"
    assert set(sources) == {str(cible / "FRONT")}


def test_plancher_localise_ses_constats_sous_la_racine_du_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cible = _front_sous(tmp_path, "FRONT")
    sources = _enregistreur(monkeypatch, plancher)
    _brancher(monkeypatch, plancher, {
        "/": {"v1_overflow": [{"what": "nav.menu", "detail": "scrollWidth 1680px > 1440px"}]},
    })
    sortie = plancher.analyser(cible)
    assert sortie.verdict == "FAIL"
    assert set(sources) == {str(cible / "FRONT")}


def test_visuel_localise_son_inventaire_et_ses_constats_sous_la_racine_du_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cible = _front_sous(tmp_path, "FRONT")
    sources = _enregistreur(monkeypatch, visuel)
    monkeypatch.setattr(visuel, "_routes", lambda _c: ["/"])
    monkeypatch.setattr(visuel, "capturer", lambda _c: {"/": tmp_path / "capture.png"})
    monkeypatch.setattr(
        visuel, "_juger",
        lambda _p, accepter=False: {
            "verdict": "FAIL", "findings": [{"sev": "bloquant", "msg": "écart de 4 %"}],
            "non_juge": [],
        },
    )
    sortie = visuel.analyser(cible)
    assert sortie.verdict == "FAIL"
    assert set(sources) == {str(cible / "FRONT")}
    # l'inventaire passe par `source_des_routes` : sa source n'est plus `frontend/src/routes.jsx`
    elements = visuel.inventaire(cible)
    assert elements
    assert all("frontend" not in e.source for e in elements)


def test_la_source_des_routes_du_front_suit_la_racine_decouverte(tmp_path: Path) -> None:
    cible = _front_sous(tmp_path, "FRONT")
    chemin = accessibilite.source_des_routes(cible, accessibilite.PROVENANCE_FRONT)
    assert chemin == str(cible / "FRONT" / "src" / "routes.jsx")
    # contre-épreuve : au nom conventionnel, rien ne change
    cible2 = _front_sous(tmp_path / "autre", "frontend")
    chemin2 = accessibilite.source_des_routes(cible2, accessibilite.PROVENANCE_FRONT)
    assert chemin2 == str(cible2 / "frontend" / "src" / "routes.jsx")


def test_garde_statique_plus_aucun_frontend_en_dur_dans_les_cinq_adaptateurs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le garde statique : plus aucun `cible / "frontend"` en dur dans les cinq adaptateurs."""
    racine = Path(__file__).resolve().parent.parent / "forge_tests" / "adaptateurs"
    restes = {}
    for nom in ("clavier", "contraste", "plancher", "visuel", "accessibilite"):
        texte = (racine / f"{nom}.py").read_text(encoding="utf-8")
        lignes = [n for n, ligne in enumerate(texte.splitlines(), 1)
                  if 'cible / "frontend"' in ligne]
        if lignes:
            restes[nom] = lignes
    assert not restes, f'`cible / "frontend"` en dur subsiste : {restes}'
