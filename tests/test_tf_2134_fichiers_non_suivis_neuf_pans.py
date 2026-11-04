"""TF-2134 — neuf pans jugeaient les fichiers non suivis qu une autre session a écrits.

Suite de TF-2118. Le pan `prompts` a cessé d imputer au produit un fichier que git ne suit pas
(Produit-86, lot du 03/11/2026, RT-9 : 7 constats bloquants sur un dossier écrit par une autre
session). Neuf autres pans parcourent les fichiers du produit et n appliquaient que
`ignore_par_git` : `interface`, `migrations`, `declencheurs`, `domaine`, `revue`, `couverture`,
`relecture`, `surface_servie` et `i18n`. Un fichier non suivi, posé dans le même arbre, leur aurait
été imputé de la même façon.

La règle portée : dans un dépôt git, ces pans ne lisent que les sources SUIVIES. Hors dépôt git,
ou dans un dépôt dont aucun fichier n est encore suivi, rien ne change (aucune information, donc
aucune exclusion). Deux exceptions motivées, chacune avec sa fixture : le BUILD SERVI que
`surface_servie` et le catalogue i18n lisent à dessein (un build n est presque jamais suivi), et
la preuve en retour — un fichier suivi reste dans le périmètre.

Chaque pan a sa fixture à double sens : le fichier SUIVI reste, le fichier NON SUIVI sort.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import (
    catalogue_i18n,
    couverture,
    declencheurs,
    domaine,
    exclusions,
    relecture,
    revue,
    surface_servie,
)
from forge_tests.adaptateurs import i18n, interface, migrations

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent du poste")


def _ecrire(racine: Path, relatif: str, contenu: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


def _depot(tmp_path: Path, suivis: dict[str, str], non_suivis: dict[str, str]) -> Path:
    """Un dépôt git : les `suivis` sont ajoutés à l index, les `non_suivis` posés à côté, comme
    le ferait une autre session sur le même arbre."""
    racine = tmp_path / "produit"
    racine.mkdir()
    _ecrire(racine, "README.md", "# produit\n")
    for relatif, contenu in suivis.items():
        _ecrire(racine, relatif, contenu)
    subprocess.run(["git", "init", "-q", str(racine)], check=True)
    subprocess.run(["git", "-C", str(racine), "add", "-A"], check=True)
    for relatif, contenu in non_suivis.items():
        _ecrire(racine, relatif, contenu)
    exclusions._CACHE_GIT.clear()
    exclusions._CACHE_SUIVIS.clear()
    return racine


def _relatifs(racine: Path, chemins) -> set[str]:
    return {Path(c).relative_to(racine).as_posix() for c in chemins}


# --- interface ------------------------------------------------------------------------------------
def test_interface_ne_lit_que_les_sources_suivies(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"app/page.html": "<button>Valider</button>\n"},
        {"autre/ui.html": "<button>Autre</button>\n"},
    )
    assert _relatifs(racine, interface._fichiers(racine, (".html",))) == {"app/page.html"}


# --- migrations -----------------------------------------------------------------------------------
def test_migrations_ne_lit_que_les_migrations_suivies(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'p'\n",  # indice de racine d execution
            "migrations/001_suivie.sql": "CREATE TABLE a (id INT);\n",
        },
        {"migrations/002_autre_session.sql": "CREATE TABLE b (id INT);\n"},
    )
    assert _relatifs(racine, migrations._fichiers(racine)) == {"migrations/001_suivie.sql"}
    assert {e.id for e in migrations.inventaire(racine)} == {
        f"migration:001_suivie:{sens}" for sens in migrations.SENS
    }


def test_migrations_alembic_ne_lit_que_les_versions_suivies(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"alembic/versions/0001_suivie.py": "revision = '0001'\n"},
        {"alembic/versions/0002_autre_session.py": "revision = '0002'\n"},
    )
    assert _relatifs(racine, migrations._versions_alembic(racine)) == {
        "alembic/versions/0001_suivie.py"
    }


# --- declencheurs ---------------------------------------------------------------------------------
def test_declencheurs_ne_lit_que_les_fichiers_suivis(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {".github/workflows/ci.yml": "on:\n  schedule:\n    - cron: '0 3 * * *'\n"},
        {".github/workflows/autre.yml": "on:\n  schedule:\n    - cron: '0 4 * * *'\n"},
    )
    trouves = declencheurs._fichiers(racine, (".github/workflows/*.yml",))
    assert _relatifs(racine, trouves) == {".github/workflows/ci.yml"}


# --- domaine --------------------------------------------------------------------------------------
def test_domaine_ne_lit_que_les_sources_suivies(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"app/modeles.py": "class A:\n    pass\n"},
        {"autre/modeles.py": "class B:\n    pass\n"},
    )
    assert _relatifs(racine, domaine._fichiers(racine, (".py",))) == {"app/modeles.py"}


# --- revue ----------------------------------------------------------------------------------------
def test_revue_specs_et_suites_ne_comptent_que_le_suivi(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"e2e/a.spec.ts": "test('a', () => {});\n", "tests/test_a.py": "def test_a():\n    pass\n"},
        {"e2e/b.spec.ts": "test('b', () => {});\n", "tests/test_b.py": "def test_b():\n    pass\n"},
    )
    assert _relatifs(racine, revue._specs(racine)) == {"e2e/a.spec.ts"}
    suites = _relatifs(racine, revue._fichiers_de_test(racine))
    assert suites == {"e2e/a.spec.ts", "tests/test_a.py"}


_SPEC_SESSION = "test('x', async () => {\n  sessionStorage.setItem('cle', '1');\n});\n"
_SPEC_PERSISTE = "test('p', async () => {\n  await ctx.storageState({ path: 'etat.json' });\n});\n"


def test_revue_cle_hors_session_n_accuse_pas_un_spec_non_suivi(tmp_path: Path) -> None:
    """Rouge avant TF-2134 : le spec non suivi, qui écrit `sessionStorage`, était accusé."""
    racine = _depot(
        tmp_path,
        {"e2e/persiste.spec.ts": _SPEC_PERSISTE},
        {"e2e/autre_session.spec.ts": _SPEC_SESSION},
    )
    assert revue.cle_de_relecture_separee_de_la_session(racine) == []


def test_revue_cle_hors_session_accuse_toujours_un_spec_suivi(tmp_path: Path) -> None:
    """Vert : le même spec, SUIVI, est jugé comme avant."""
    racine = _depot(
        tmp_path,
        {"e2e/persiste.spec.ts": _SPEC_PERSISTE, "e2e/session.spec.ts": _SPEC_SESSION},
        {},
    )
    ids = [f.id for f in revue.cle_de_relecture_separee_de_la_session(racine)]
    assert ids == ["revue:cle-hors-session:e2e/session.spec.ts"]


def test_revue_une_config_non_suivie_ne_fonde_pas_un_constat(tmp_path: Path) -> None:
    """Le `storageState` d une config écrite par une autre session ne persiste rien au produit."""
    racine = _depot(
        tmp_path,
        {"e2e/session.spec.ts": _SPEC_SESSION},
        {"playwright.config.ts": "export default { use: { storageState: 'etat.json' } };\n"},
    )
    assert revue.cle_de_relecture_separee_de_la_session(racine) == []


# --- couverture -----------------------------------------------------------------------------------
def test_couverture_ne_lit_que_les_configurations_suivies(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"vitest.config.ts": "export default {};\n"},
        {"autre/jest.config.js": "module.exports = {};\n"},
    )
    assert _relatifs(racine, couverture._configs(racine)) == {"vitest.config.ts"}


# --- relecture ------------------------------------------------------------------------------------
def test_relecture_ne_lit_que_les_modeles_suivis(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"app/modeles.py": "class A:\n    pass\n"},
        {"autre/modeles.py": "class B:\n    pass\n"},
    )
    assert _relatifs(racine, relecture._fichiers_modeles(racine)) == {"app/modeles.py"}


# --- surface_servie -------------------------------------------------------------------------------
def test_surface_servie_ne_lit_que_les_sources_suivies(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"app/api.py": "x = 1\n"},
        {"autre/api.py": "y = 2\n"},
    )
    trouves = surface_servie._fichiers(racine, (".py",), exclus=surface_servie.IGNORES_SOURCES)
    assert _relatifs(racine, trouves) == {"app/api.py"}


def test_surface_servie_lit_toujours_un_build_non_suivi(tmp_path: Path) -> None:
    """Un build est un artefact, presque jamais suivi : le lire est son objet. Le filtre « suivi
    par git » ne s applique qu aux SOURCES, jamais au build (sinon le pan ne verrait rien)."""
    racine = _depot(
        tmp_path,
        {"app/api.py": "x = 1\n"},
        {"dist/index.html": '<img src="/assets/logo.png">\n', "dist/assets/logo.png": "png"},
    )
    refs = surface_servie.ressources_referencees(racine / "dist")
    assert refs.sources == ["index.html"]


# --- i18n -----------------------------------------------------------------------------------------
def test_i18n_un_dossier_de_traductions_non_suivi_n_est_pas_un_signe(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"app/main.py": "x = 1\n"},
        {"autre/locales/fr.json": '{"a": "b"}\n', "autre/locales/en.json": '{"a": "c"}\n'},
    )
    assert i18n._signes_i18n(racine) == []


def test_i18n_un_dossier_de_traductions_suivi_reste_un_signe(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"web/locales/fr.json": '{"a": "b"}\n', "web/locales/en.json": '{"a": "c"}\n'},
        {},
    )
    assert i18n._signes_i18n(racine) == ["dossier de traductions `web/locales`"]


def test_catalogue_ne_lit_que_les_catalogues_suivis(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {
            "web/locales/fr.json": '{"a": "1", "b": "2"}\n',
            "web/locales/en.json": '{"a": "1", "b": "2"}\n',
        },
        {
            "autre/locales/fr.json": '{"a": "1", "b": "2"}\n',
            "autre/locales/en.json": '{"a": "1"}\n',
        },
    )
    lus, _ = catalogue_i18n.catalogues(racine)
    assert set(lus) == {"web/locales"}


def test_catalogue_une_locale_non_suivie_n_est_pas_comptee_manquante(tmp_path: Path) -> None:
    """Rouge avant TF-2134 : `es.json`, écrit par une autre session et incomplet, était lu et
    produisait des clés manquantes imputées au produit."""
    racine = _depot(
        tmp_path,
        {
            "web/locales/fr.json": '{"a": "1", "b": "2"}\n',
            "web/locales/en.json": '{"a": "1", "b": "2"}\n',
        },
        {"web/locales/es.json": '{"a": "1"}\n'},
    )
    lus, _ = catalogue_i18n.catalogues(racine)
    assert set(lus["web/locales"]) == {"fr", "en"}


def test_catalogue_lit_toujours_un_catalogue_de_build_non_suivi(tmp_path: Path) -> None:
    """TF-1331 : un catalogue compilé sous `dist/` est lu à dessein ; il n est jamais suivi."""
    racine = _depot(
        tmp_path,
        {"app/main.py": "x = 1\n"},
        {"dist/i18n/fr.json": '{"a": "1"}\n', "dist/i18n/en.json": '{"a": "1"}\n'},
    )
    lus, _ = catalogue_i18n.catalogues(racine)
    assert set(lus) == {"dist/i18n"}


# --- hors dépôt git, et dépôt sans fichier suivi : comportement d avant ---------------------------
def test_hors_depot_git_rien_ne_change(tmp_path: Path) -> None:
    racine = tmp_path / "sans-git"
    _ecrire(racine, "app/page.html", "<button>A</button>\n")
    _ecrire(racine, "pyproject.toml", "[project]\nname = 'p'\n")
    _ecrire(racine, "migrations/001.sql", "CREATE TABLE a (id INT);\n")
    _ecrire(racine, "web/locales/fr.json", '{"a": "1"}\n')
    _ecrire(racine, "web/locales/en.json", '{"a": "1"}\n')
    exclusions._CACHE_GIT.clear()
    exclusions._CACHE_SUIVIS.clear()
    assert _relatifs(racine, interface._fichiers(racine, (".html",))) == {"app/page.html"}
    assert _relatifs(racine, migrations._fichiers(racine)) == {"migrations/001.sql"}
    assert i18n._signes_i18n(racine) == ["dossier de traductions `web/locales`"]
    lus, _ = catalogue_i18n.catalogues(racine)
    assert set(lus) == {"web/locales"}


def test_depot_sans_aucun_fichier_suivi_garde_le_comportement_d_avant(tmp_path: Path) -> None:
    racine = tmp_path / "neuf"
    _ecrire(racine, "app/page.html", "<button>A</button>\n")
    subprocess.run(["git", "init", "-q", str(racine)], check=True)
    exclusions._CACHE_GIT.clear()
    exclusions._CACHE_SUIVIS.clear()
    assert _relatifs(racine, interface._fichiers(racine, (".html",))) == {"app/page.html"}


# --- l aide partagée, côté dossier ----------------------------------------------------------------
def test_dossier_sans_fichier_suivi(tmp_path: Path) -> None:
    racine = _depot(
        tmp_path,
        {"web/locales/fr.json": "{}\n"},
        {"autre/locales/fr.json": "{}\n"},
    )
    assert not exclusions.dossier_sans_fichier_suivi(racine / "web" / "locales", racine)
    assert not exclusions.dossier_sans_fichier_suivi(racine / "web", racine)
    assert exclusions.dossier_sans_fichier_suivi(racine / "autre" / "locales", racine)
    assert exclusions.dossier_sans_fichier_suivi(racine / "autre", racine)
    sans_git = tmp_path / "ailleurs"
    _ecrire(sans_git, "x/y.txt", "y\n")
    exclusions._CACHE_SUIVIS.clear()
    assert not exclusions.dossier_sans_fichier_suivi(sans_git / "x", sans_git)
