"""TF-2577 — onze modules jugeaient les segments du chemin ABSOLU, pas ceux du projet.

TF-2523 (14/11/2026) a recadré `exclusions.py` et quatre pans sur `exclusions.parties_du_projet`.
Le reste de la recette gardait le même défaut : `chemin.parts` ou `chemin.parents` d'un chemin
absolu, lus contre une liste de noms (`node_modules`, `build`, `tests`, `input`, `app`, `pages`…).
Un projet posé SOUS un de ces dossiers (un clone sous `…\\node_modules\\…`, un produit rangé sous
`…\\input\\…`) voyait donc son contenu écarté, ou pris pour un entrant, ou pour une route : la
recette mesurait le poste, pas le dépôt.

Onze modules, mesurés le 15/11/2026 par `grep` des `.parts` / `.parents` : `adaptateurs.api`,
`adaptateurs.interface` (deux sites), `adaptateurs.prompts` (trois), `chaine`, `couverture`,
`revue` (trois), `scripts_node`, `noyau`, `domaine`, `relecture`, `surface_servie`.

Deux sens pour chaque module, chacun avec sa fixture :
  - ROUGE avant correction — le projet posé sous le dossier que le module écartait à tort ;
  - VERT, et il le reste — le MÊME dossier DANS le projet reste écarté : l'exclusion n'est pas
    levée, elle est recadrée sur ce que le projet contient.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import (
    chaine,
    couverture,
    domaine,
    noyau,
    relecture,
    revue,
    scripts_node,
    surface_servie,
)
from forge_tests.adaptateurs import api, interface, prompts


def _projet_sous(tmp_path: Path, parent: str) -> Path:
    racine = tmp_path / parent / "clone"
    racine.mkdir(parents=True)
    return racine


def _poser(racine: Path, relatif: str, contenu: str = "x\n") -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _relatifs(racine: Path, chemins: list[Path]) -> list[str]:
    return sorted(Path(c).relative_to(racine).as_posix() for c in chemins)


# --- adaptateurs.api -----------------------------------------------------------------------------
def test_api_juge_un_projet_pose_sous_pycache(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "__pycache__")
    _poser(racine, "backend/app/main.py")
    assert _relatifs(racine, api._fichiers_sources(racine)) == ["backend/app/main.py"]


def test_api_ecarte_toujours_pycache_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "__pycache__")
    _poser(racine, "backend/app/main.py")
    _poser(racine, "backend/app/__pycache__/main.py")
    assert _relatifs(racine, api._fichiers_sources(racine)) == ["backend/app/main.py"]


# --- adaptateurs.interface -----------------------------------------------------------------------
@pytest.mark.parametrize("parent", ["app", "pages"])
def test_interface_ne_lit_pas_app_ou_pages_dans_le_chemin_du_clone(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "src/ui/page.tsx", "export default function P() { return null }\n")
    _poser(racine, "src/ui/index.tsx", "export default function I() { return null }\n")
    assert interface._routes_next(racine) == []


def test_interface_lit_toujours_app_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "app")
    _poser(racine, "app/page.tsx", "export default function P() { return null }\n")
    _poser(racine, "app/about/page.tsx", "export default function A() { return null }\n")
    assert sorted(interface._routes_next(racine)) == ["/", "/about"]


def test_interface_ne_lit_pas_un_segment_de_locale_du_chemin_du_clone(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "[locale]")
    _poser(racine, "src/a.ts")
    assert interface._locale_par_configuration(racine) is False


def test_interface_lit_toujours_le_segment_de_locale_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "[locale]")
    _poser(racine, "app/[locale]/page.tsx")
    assert interface._locale_par_configuration(racine) is True


# --- adaptateurs.prompts -------------------------------------------------------------------------
def test_prompts_ne_prend_pas_un_fichier_pour_un_prompt_parce_que_le_clone_est_sous_prompts(
    tmp_path: Path,
) -> None:
    racine = _projet_sous(tmp_path, "prompts")
    notes = _poser(racine, "docs/notes.md")
    vrai = _poser(racine, "prompts/assistant.md")
    assert prompts.est_un_prompt(notes, racine) is False
    assert prompts.est_un_prompt(vrai, racine) is True


def test_prompts_ne_prend_pas_un_fichier_pour_un_corpus_parce_que_le_clone_est_sous_evals(
    tmp_path: Path,
) -> None:
    racine = _projet_sous(tmp_path, "evals")
    donnees = _poser(racine, "config/reglages.json")
    vrai = _poser(racine, "evals/cas.json")
    assert prompts.est_un_corpus(donnees, racine) is False
    assert prompts.est_un_corpus(vrai, racine) is True


def test_prompts_ne_prend_pas_un_fichier_js_pour_un_test_parce_que_le_clone_est_sous_tests(
    tmp_path: Path,
) -> None:
    racine = _projet_sous(tmp_path, "__tests__")
    source = _poser(racine, "src/lib.ts")
    vrai = _poser(racine, "src/__tests__/lib.ts")
    assert prompts.est_un_fichier_de_test(source, racine) is False
    assert prompts.est_un_fichier_de_test(vrai, racine) is True


def test_prompts_sans_racine_le_comportement_public_est_inchange(tmp_path: Path) -> None:
    chemin = tmp_path / "prompts" / "x" / "notes.md"
    assert prompts.est_un_prompt(chemin) is True


# --- chaine --------------------------------------------------------------------------------------
@pytest.mark.parametrize("parent", ["build", "vendor", "node_modules"])
def test_chaine_juge_un_depot_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "tests/test_a.py")
    assert _relatifs(racine, chaine.suites_du_depot(racine)) == ["tests/test_a.py"]


def test_chaine_ecarte_toujours_un_dossier_d_outillage_du_depot(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "build")
    _poser(racine, "tests/test_a.py")
    _poser(racine, "tests/vendor/test_b.py")
    assert _relatifs(racine, chaine.suites_du_depot(racine)) == ["tests/test_a.py"]


# --- couverture ----------------------------------------------------------------------------------
@pytest.mark.parametrize("parent", ["node_modules", ".venv"])
def test_couverture_lit_les_configs_d_un_projet_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "vitest.config.ts")
    _poser(racine, "node_modules/lib/vitest.config.ts")
    _poser(racine, ".venv/lib/vitest.config.ts")
    assert _relatifs(racine, couverture._configs(racine)) == ["vitest.config.ts"]


# --- revue ---------------------------------------------------------------------------------------
def test_revue_lit_les_specs_d_un_projet_pose_sous_node_modules(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "node_modules")
    _poser(racine, "e2e/a.spec.ts")
    _poser(racine, "node_modules/lib/b.spec.ts")
    assert _relatifs(racine, revue._specs(racine)) == ["e2e/a.spec.ts"]


@pytest.mark.parametrize("parent", ["node_modules", ".venv"])
def test_revue_lit_les_suites_python_d_un_projet_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "tests/test_a.py")
    _poser(racine, ".venv/lib/test_b.py")
    assert _relatifs(racine, revue._fichiers_de_test(racine)) == ["tests/test_a.py"]


def test_revue_lit_la_config_playwright_d_un_projet_pose_sous_node_modules(
    tmp_path: Path,
) -> None:
    """La clé écrite dans `sessionStorage` par la spec, la session persistée par la config."""
    racine = _projet_sous(tmp_path, "node_modules")
    _poser(racine, "e2e/a.spec.ts", "sessionStorage.setItem('cle', '1')\n")
    _poser(racine, "playwright.config.ts", "use: { storageState: 'etat.json' }\n")
    findings = revue.cle_de_relecture_separee_de_la_session(racine)
    assert [f.localisation for f in findings] == ["e2e/a.spec.ts"]
    assert "playwright.config.ts" in findings[0].message


def test_revue_ecarte_toujours_la_config_dans_node_modules_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "node_modules")
    _poser(racine, "e2e/a.spec.ts", "sessionStorage.setItem('cle', '1')\n")
    _poser(racine, "node_modules/lib/playwright.config.ts", "use: { storageState: 'e.json' }\n")
    assert revue.cle_de_relecture_separee_de_la_session(racine) == []


# --- scripts_node --------------------------------------------------------------------------------
def test_scripts_node_lit_un_projet_pose_sous_node_modules(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "node_modules")
    _poser(racine, "scripts/outil.mjs")
    _poser(racine, "scripts/node_modules/lib/tiers.mjs")
    assert _relatifs(racine, scripts_node._scripts(racine)) == ["scripts/outil.mjs"]


# --- noyau ---------------------------------------------------------------------------------------
def test_noyau_un_projet_pose_sous_input_n_est_pas_un_entrant(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "input")
    source = str(racine / "frontend")
    assert noyau.provenance_de(source, racine) == "produit"
    assert noyau.provenance_de(racine / "input" / "cahier.html", racine) == "entrant"


def test_noyau_sans_racine_le_chemin_entier_se_juge_comme_avant(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "input")
    assert noyau.provenance_de(str(racine / "frontend")) == "entrant"


def test_noyau_l_evaluation_de_surface_compte_un_projet_pose_sous_input(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, "input")
    element = noyau.Element(
        id="e1", pan="interface", libelle="e1", source=str(racine / "frontend"),
    )
    sortie = noyau.evaluer_surface("interface", "interface", str(racine), [element], set(),
                                   0.8, [])
    assert sortie.verdict == "FAIL", "l'élément du projet compte, il n'est pas pris pour un entrant"


# --- domaine, relecture, surface_servie ----------------------------------------------------------
@pytest.mark.parametrize("parent", ["tests", "build", "node_modules"])
def test_domaine_lit_un_projet_pose_sous_un_dossier_ignore(tmp_path: Path, parent: str) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "app/modeles.sql")
    _poser(racine, "node_modules/lib/tiers.sql")
    assert _relatifs(racine, domaine._fichiers(racine, (".sql",))) == ["app/modeles.sql"]


@pytest.mark.parametrize("parent", ["tests", "build", "node_modules"])
def test_relecture_lit_un_projet_pose_sous_un_dossier_ignore(tmp_path: Path, parent: str) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "app/modeles.py")
    _poser(racine, "node_modules/lib/tiers.py")
    assert _relatifs(racine, relecture._fichiers_modeles(racine)) == ["app/modeles.py"]


@pytest.mark.parametrize("parent", ["node_modules", ".venv"])
def test_surface_servie_lit_un_projet_pose_sous_un_dossier_ignore(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "src/page.html")
    _poser(racine, "node_modules/lib/tiers.html")
    assert _relatifs(racine, surface_servie._fichiers(racine, (".html",))) == ["src/page.html"]
