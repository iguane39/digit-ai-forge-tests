"""TF-2298 — un workflow GitHub planifié est câblé : sa cible, c'est le fichier du workflow.

Fait remonté (09/11/2026, branche de remédiation d'un produit) : trois workflows planifiés,
présents sous `.github/workflows/`, rendaient trois constats `trigger-non-cable` bloquants.
Pour un déclencheur `cron-ci`, la désignation est le NOM DU FICHIER du workflow ;
`_cible_existe` ne connaissait pas l'extension `.yml`, traitait `derive-nocturne.yml` comme un
module Python pointé et cherchait `derive-nocturne/yml.py`.

Décision du 09/11/2026 : `_cible_existe` tient pour câblé un déclencheur `cron-ci` dont la cible
est un fichier `.yml` ou `.yaml` présent sous `.github/workflows/`.

Sens prouvés :
  - ROUGE  — sur l'ancien code, les trois workflows planifiés (et leur variante `.yaml`) sont
             tenus pour non câblés et produisent un constat bloquant chacun ;
  - VERT   — le pan `batch` ne lève plus aucun `trigger-non-cable` pour eux ;
  - CONTRE-ÉPREUVE — une cible `.yml` ABSENTE de `.github/workflows/` reste dénoncée : le
             contrôle discrimine encore, il n'absout pas tout fichier de ce nom.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import declencheurs

WORKFLOWS_PLANIFIES = ("derive-nocturne.yml", "sauvegarde.yml", "sonde.yml")


def _projet(racine: Path) -> Path:
    (racine / "backend" / "app").mkdir(parents=True)
    (racine / "backend" / "app" / "batch.py").write_text(
        "def traiter():\n    return 1\n\n\nif __name__ == '__main__':\n    traiter()\n",
        encoding="utf-8",
    )
    return racine


def _workflow(racine: Path, nom: str, cron: str = "0 3 * * *") -> Path:
    dossier = racine / ".github" / "workflows"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_text(
        f'on:\n  schedule:\n    - cron: "{cron}"\njobs:\n  nuit:\n    runs-on: ubuntu-latest\n'
        "    steps:\n      - run: python backend/app/batch.py\n",
        encoding="utf-8",
    )
    return chemin


def _trigger_non_cables(racine: Path) -> list[dict]:
    trouves = declencheurs.inventorier(racine)
    releves = declencheurs.constats(racine, trouves, ["branche:batch.py:2"])
    return [c for c in releves if c["classe"] == "trigger-non-cable"]


def test_rouge_les_trois_workflows_planifies_etaient_denonces_et_ne_le_sont_plus(
    tmp_path: Path,
) -> None:
    racine = _projet(tmp_path)
    cadences = ("0 3 * * *", "30 1 * * 0", "*/15 * * * *")
    for nom, cron in zip(WORKFLOWS_PLANIFIES, cadences, strict=True):
        _workflow(racine, nom, cron)
    crons = [d for d in declencheurs.inventorier(racine) if d["type"] == "cron-ci"]
    assert sorted(d["designation"] for d in crons) == sorted(WORKFLOWS_PLANIFIES)
    assert [d["cable"] for d in crons] == [True, True, True]
    assert _trigger_non_cables(racine) == []


def test_un_workflow_yaml_est_cable_comme_un_workflow_yml(tmp_path: Path) -> None:
    racine = _projet(tmp_path)
    _workflow(racine, "purge.yaml")
    crons = [d for d in declencheurs.inventorier(racine) if d["type"] == "cron-ci"]
    assert [(d["designation"], d["cable"]) for d in crons] == [("purge.yaml", True)]
    assert _trigger_non_cables(racine) == []


def test_le_pan_batch_ne_denonce_plus_un_workflow_planifie(tmp_path: Path) -> None:
    from forge_tests.adaptateurs import batch

    racine = _projet(tmp_path)
    _workflow(racine, "derive-nocturne.yml")
    sortie = batch.analyser(racine)
    assert [f for f in sortie.findings if f.classe == "trigger-non-cable"] == []


def test_cible_existe_connait_l_extension_des_workflows(tmp_path: Path) -> None:
    racine = _projet(tmp_path)
    _workflow(racine, "sonde.yml")
    _workflow(racine, "purge.yaml")
    assert declencheurs._cible_existe(racine, "sonde.yml")
    assert declencheurs._cible_existe(racine, "purge.yaml")


@pytest.mark.parametrize("designation", ["absent.yml", "absent.yaml"])
def test_contre_epreuve_une_cible_yml_absente_des_workflows_reste_denoncee(
    tmp_path: Path, designation: str
) -> None:
    """Le sens fautif : un workflow existe, mais PAS celui que le déclencheur nomme."""
    racine = _projet(tmp_path)
    _workflow(racine, "sonde.yml")
    assert not declencheurs._cible_existe(racine, designation)
    (racine / "crontab").write_text(
        f"0 2 * * * gh workflow run {designation}\n", encoding="utf-8"
    )
    trouves = [d for d in declencheurs.inventorier(racine) if d["type"] == "crontab"]
    assert trouves and trouves[0]["cable"] is False
    # Vrai sur l'état de départ comme après la correction : le contrôle discrimine toujours.
    assert trouves[0]["id"] in [c["id"] for c in _trigger_non_cables(racine)]


def test_contre_epreuve_un_yml_hors_des_workflows_ne_cable_pas_un_nom_nu(tmp_path: Path) -> None:
    """Un fichier `sonde.yml` rangé ailleurs que sous `.github/workflows/` n'est pas un
    workflow : il ne câble pas le déclencheur qui nomme `sonde.yml`."""
    racine = _projet(tmp_path)
    (racine / "config").mkdir()
    (racine / "config" / "sonde.yml").write_text("clef: valeur\n", encoding="utf-8")
    assert not declencheurs._cible_existe(racine, "sonde.yml")
