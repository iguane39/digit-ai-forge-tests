"""TF-2423 — la sonde de l'API rendait 0 % sans refus nommé quand une instance module existe.

Fait (Produit-86, audit du 10/11/2026) : api exercée 0 sur 173. La sonde observait `app.main:app`
alors que chaque test bâtit son application par `creer_app()` ; `application.py` ne refusait pas
parce qu'une instance module existait. Avec `FORGE_TESTS_APP=app.main:creer_app`, 173 sur 173. Un
audit complet de 45 minutes a été rejoué en reprise.

Le refus de TF-2161 est donc rendu AUSSI après la mesure, sur un relevé vide, dès qu'une fabrique
existe, même avec une instance module. Avant la mesure rien ne change : une instance module sans
relevé vide à charge n'est pas refusée.

La suite du projet n'est jamais lancée : `exerces` est doublé, la sonde réelle se prouve ailleurs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests import application, authentification, execution
from forge_tests.adaptateurs import REGISTRE, api
from forge_tests.authentification import ENV_AUDIT
from forge_tests.qualification import qualifier


@pytest.fixture(autouse=True)
def env_propre(monkeypatch, tmp_path):
    """`charger_env` écrit dans `os.environ` : restauré après chaque test (même idiome que
    TF-2161)."""
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")
    execution.mesurer.cache_clear()
    yield
    os.environ.clear()
    os.environ.update(memoire)
    execution.mesurer.cache_clear()


def _ecrire(racine: Path, relatif: str, texte: str) -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


_ROUTE = '@app.get("/x")\ndef x():\n    return {}\n'


def _produit_instance_et_fabrique(racine: Path) -> Path:
    """Le cas de Produit-86 : une instance module ET une fabrique que la suite appelle."""
    _ecrire(racine, "backend/app/__init__.py", "")
    _ecrire(
        racine, "backend/app/main.py",
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n" + _ROUTE
        + "\n\ndef creer_app():\n    return FastAPI()\n",
    )
    _ecrire(racine, "backend/tests/test_x.py", "def test_x():\n    assert True\n")
    return racine


def _produit_instance_seule(racine: Path) -> Path:
    _ecrire(racine, "backend/app/__init__.py", "")
    _ecrire(
        racine, "backend/app/main.py",
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n" + _ROUTE,
    )
    _ecrire(racine, "backend/tests/test_x.py", "def test_x():\n    assert True\n")
    return racine


def _releve(monkeypatch, couples: set[str]) -> None:
    """La suite est verte et la sonde rend ce relevé."""
    monkeypatch.setattr(api, "exerces", lambda _cible: set(couples))


VIDE: set[str] = set()
NON_VIDE = {"endpoint:GET /x", "code:GET /x=200"}


# --- ROUGE : une instance module ne protège plus d'un relevé vide -----------------------------
def test_rouge_un_releve_vide_avec_fabrique_est_refuse_et_nomme_malgre_l_instance(
    tmp_path: Path, monkeypatch
) -> None:
    """Avant : le pan rendait FAIL à 0 % avec un constat générique « sonde muette ». Après : un
    refus qui nomme la clé, la fabrique, la valeur à recopier et l'endroit où la ranger."""
    projet = _produit_instance_et_fabrique(tmp_path / "produit")
    _releve(monkeypatch, VIDE)

    sortie = api.analyser(projet)

    assert sortie.verdict == "SKIP"
    texte = " ".join(sortie.non_juge)
    assert "REFUS" in texte
    assert "FORGE_TESTS_APP=app.main:creer_app" in texte
    assert "creer_app" in texte
    assert ENV_AUDIT in texte
    assert "VIDE" in texte
    # Ce n'est pas un 0 % : aucune surface n'est publiée, aucun constat n'accuse la suite.
    assert sortie.surface is None
    assert sortie.findings == []


def test_le_refus_apres_releve_vide_est_un_manque_de_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    projet = _produit_instance_et_fabrique(tmp_path / "produit")
    _releve(monkeypatch, VIDE)
    sortie = api.analyser(projet)

    qualifier([sortie], projet, REGISTRE)

    assert {tuple(n.champs_requis) for n in sortie.non_testables} == {("FORGE_TESTS_APP",)}
    assert {n.pan for n in sortie.non_testables} == {"api"}


def test_le_remede_propose_est_joue_et_leve_le_refus(tmp_path: Path, monkeypatch) -> None:
    """Jouer le remède recommandé (TF-1013) : la valeur donnée, rangée où le refus le dit, ne
    laisse plus refuser."""
    projet = _produit_instance_et_fabrique(tmp_path / "produit")
    _releve(monkeypatch, VIDE)
    refus = " ".join(api.analyser(projet).non_juge)
    valeur = refus.split("FORGE_TESTS_APP=", 1)[1].split()[0].strip("`.,;")
    _ecrire(projet, ENV_AUDIT, f"FORGE_TESTS_APP={valeur}\n")

    sortie = api.analyser(projet)

    assert "REFUS" not in " ".join(sortie.non_juge)


# --- VERT : ce que le refus ne doit pas accuser ------------------------------------------------
def test_vert_un_releve_vide_sans_fabrique_garde_le_constat_de_sonde_muette(
    tmp_path: Path, monkeypatch
) -> None:
    """Une instance module seule, relevé vide : rien à nommer, le refus serait une accusation sans
    objet. Le constat d'origine (sonde muette, signalé) reste."""
    projet = _produit_instance_seule(tmp_path / "produit")
    _releve(monkeypatch, VIDE)

    sortie = api.analyser(projet)

    assert "REFUS" not in " ".join(sortie.non_juge)
    assert [f.id for f in sortie.findings][:1] == ["sonde-muette:api"]


def test_vert_un_releve_non_vide_n_est_pas_refuse_malgre_la_fabrique(
    tmp_path: Path, monkeypatch
) -> None:
    """La suite exerce l'instance : la sonde a vu des requêtes, rien n'est aveugle."""
    projet = _produit_instance_et_fabrique(tmp_path / "produit")
    _releve(monkeypatch, NON_VIDE)

    sortie = api.analyser(projet)

    assert "REFUS" not in " ".join(sortie.non_juge)
    assert sortie.surface is not None


def test_vert_une_designation_posee_n_est_pas_refusee_meme_sur_releve_vide(
    tmp_path: Path, monkeypatch
) -> None:
    """Le projet a désigné son application : si le relevé est vide, c'est une autre cause, que
    le constat de sonde muette nomme déjà."""
    projet = _produit_instance_et_fabrique(tmp_path / "produit")
    _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_APP=app.main:app\n")
    _releve(monkeypatch, VIDE)

    sortie = api.analyser(projet)

    assert "REFUS" not in " ".join(sortie.non_juge)
    assert [f.id for f in sortie.findings][:1] == ["sonde-muette:api"]


def test_avant_la_mesure_une_instance_module_n_est_toujours_pas_refusee(tmp_path: Path) -> None:
    """Sens inverse de la règle : sans relevé vide à charge, TF-2161 tient comme avant."""
    projet = _produit_instance_et_fabrique(tmp_path / "produit")

    assert application.refus_designation(projet) is None
    refus = application.refus_designation(projet, releve_vide=True)
    assert refus is not None and refus["fabrique"] == "app.main:creer_app"
