"""TF-1675 — le délai de 900 s de la suite backend sous coverage était fixé dans le code.

Le fait, remis par Produit-80 le 12/10/2026 (RT-3 du lot 20261012c, ledger seq 341 et 342) :
sur un backend identique, l audit 14 a mesuré api 675/675, data 582/583 et migrations 66/66 ;
l audit 15 et sa reprise ont perdu ces trois pans et deux autres, « délai de 900 s dépassé »,
la suite seule prenant 398 s sur le poste. Le projet n avait aucun réglage pour ce délai, et le
motif ne disait ni la durée atteinte, ni où le lever.

Ces tests fixent : le délai se règle par `FORGE_TESTS_DELAI_BACKEND_S` dans `.env.forge-tests` ;
une valeur illisible laisse le défaut et le dit ; un délai dépassé écrit la durée atteinte et
le réglage à poser.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from forge_tests import authentification, execution


@pytest.fixture()
def env_propre(tmp_path: Path, monkeypatch):
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _delai_transmis(racine: Path, monkeypatch) -> tuple[object, str]:
    """Joue `mesurer` jusqu au lancement de la suite et rend le délai passé à `_run`."""
    vus: list[dict] = []

    def _run_stub(commande, *, banc, domaine, quoi, **kwargs):
        vus.append({"quoi": quoi, **kwargs})
        return None  # la suite « n a pas abouti » : `mesurer` s arrête là

    monkeypatch.setattr(execution, "_python", lambda _banc: Path(sys.executable))
    monkeypatch.setattr(execution, "_coverage_present", lambda _banc, _py: True)
    monkeypatch.setattr(execution, "nom_paquet_sources", lambda _banc: "app")
    monkeypatch.setattr(execution, "racine_execution", lambda _banc: racine)
    monkeypatch.setattr(execution, "_run", _run_stub)
    execution.mesurer.cache_clear()
    assert execution.mesurer(str(racine)) is None
    suite = [v for v in vus if v["quoi"] == "suite backend sous coverage"]
    assert len(suite) == 1
    return suite[0]["timeout"], suite[0].get("remede", "")


def test_le_delai_regle_par_le_projet_est_applique(
    tmp_path: Path, monkeypatch, env_propre
) -> None:
    """ROUGE avant le correctif : 900 était passé quel que soit le réglage du projet."""
    (tmp_path / ".env.forge-tests").write_text(
        "FORGE_TESTS_DELAI_BACKEND_S=1800\n", encoding="utf-8"
    )

    delai, remede = _delai_transmis(tmp_path, monkeypatch)

    assert delai == 1800
    assert "FORGE_TESTS_DELAI_BACKEND_S=1800" in remede


def test_sans_reglage_le_defaut_reste_900(tmp_path: Path, monkeypatch, env_propre) -> None:
    """VERT de non-régression : un projet qui ne règle rien garde le délai d avant."""
    delai, remede = _delai_transmis(tmp_path, monkeypatch)

    assert delai == 900
    assert "FORGE_TESTS_DELAI_BACKEND_S" in remede and ".env.forge-tests" in remede


@pytest.mark.parametrize("brut", ["quinze-minutes", "0", "-5"])
def test_une_valeur_illisible_laisse_le_defaut_et_le_dit(
    monkeypatch, env_propre, brut: str
) -> None:
    monkeypatch.setenv("FORGE_TESTS_DELAI_BACKEND_S", brut)

    delai, remede = execution.delai_backend()

    assert delai == 900
    assert "illisible" in remede and repr(brut) in remede


def test_un_delai_depasse_ecrit_la_duree_atteinte_et_le_reglage(tmp_path: Path) -> None:
    """ROUGE avant le correctif : le motif disait « délai de N s dépassé » sans durée atteinte
    ni réglage ; `remede` n existait pas."""
    resultat = execution._run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        banc=tmp_path,
        domaine="backend",
        quoi="suite backend sous coverage",
        remede="regler FORGE_TESTS_DELAI_BACKEND_S",
        timeout=1,
    )

    assert resultat is None
    motif = execution.motif_indisponibilite(tmp_path, "backend", "")
    assert "délai de 1 s dépassé" in motif
    assert "interrompu après" in motif
    assert motif.endswith("regler FORGE_TESTS_DELAI_BACKEND_S")


def test_le_reglage_rejoint_le_gabarit_derive_du_code() -> None:
    """Le gabarit `.env.forge-tests.exemple` est dérivé du code : la clé y paraît d office."""
    from forge_tests import gabarit_env

    assert "FORGE_TESTS_DELAI_BACKEND_S" in gabarit_env.cles_connues()
