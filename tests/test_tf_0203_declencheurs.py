"""TF-0203 — déclencheurs de traitements par lot : un trigger non câblé est une affordance morte.

Précision humaine du 14/08 : « pour les triggers, il s'agirait d'un produit trigger,
l'enclenchement de batch à implémenter et/ou tester ». Chaque test ci-dessous décrit un défaut
que le pan `batch` ne voyait PAS avant ce module : il mesurait l'intérieur du traitement en
supposant qu'il démarre.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import declencheurs


def _projet(tmp_path: Path) -> Path:
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "batch.py").write_text(
        "def traiter():\n    return 1\n\n\nif __name__ == '__main__':\n    traiter()\n",
        encoding="utf-8",
    )
    return tmp_path


def _workflow(racine: Path, contenu: str) -> None:
    dossier = racine / ".github" / "workflows"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "nuit.yml").write_text(contenu, encoding="utf-8")


# --- Découverte ---------------------------------------------------------------------------
def test_un_cron_de_ci_est_decouvert(tmp_path: Path) -> None:
    racine = _projet(tmp_path)
    _workflow(racine, 'on:\n  schedule:\n    - cron: "0 3 * * *"\n')
    trouves = declencheurs.inventorier(racine)
    crons = [d for d in trouves if d["type"] == "cron-ci"]
    assert len(crons) == 1
    assert crons[0]["cadence"] == "0 3 * * *"


def test_le_point_d_entree_manuel_est_un_declencheur(tmp_path: Path) -> None:
    """Un lot lancé à la main EST enclenché — le taire ferait croire à un job orphelin."""
    racine = _projet(tmp_path)
    types = {d["type"] for d in declencheurs.inventorier(racine)}
    assert "manuel" in types


def test_une_tache_de_file_est_decouverte(tmp_path: Path) -> None:
    racine = _projet(tmp_path)
    (racine / "backend" / "app" / "taches.py").write_text(
        "from celery import shared_task\n\n\n@shared_task\ndef purger():\n    return 0\n",
        encoding="utf-8",
    )
    files = [d for d in declencheurs.inventorier(racine) if d["type"] == "file"]
    assert [d["designation"] for d in files] == ["purger"]


def test_les_artefacts_ne_sont_pas_fouilles(tmp_path: Path) -> None:
    """RT-9/RT-10 : un workflow archivé dans output\\ n'est pas un déclencheur du produit."""
    racine = _projet(tmp_path)
    archive = racine / "output" / ".github" / "workflows"
    archive.mkdir(parents=True)
    (archive / "vieux.yml").write_text('on:\n  schedule:\n    - cron: "0 4 * * *"\n', "utf-8")
    assert [d for d in declencheurs.inventorier(racine) if d["type"] == "cron-ci"] == []


# --- Constats -----------------------------------------------------------------------------
def test_un_declencheur_vers_une_cible_absente_est_denonce(tmp_path: Path) -> None:
    """Le défaut le plus coûteux : le lot ne partira jamais, et rien ne le dit au déploiement."""
    racine = _projet(tmp_path)
    (racine / "crontab").write_text("0 2 * * * python jobs/inexistant.py\n", encoding="utf-8")
    trouves = declencheurs.inventorier(racine)
    classes = {c["classe"] for c in declencheurs.constats(racine, trouves, ["branche:batch.py:2"])}
    assert "trigger-non-cable" in classes


def test_une_cible_presente_ne_produit_aucun_constat(tmp_path: Path) -> None:
    """Sens vert : le contrôle DISCRIMINE, il ne dénonce pas tout."""
    racine = _projet(tmp_path)
    (racine / "crontab").write_text(
        "0 2 * * * python backend/app/batch.py\n", encoding="utf-8"
    )
    trouves = [d for d in declencheurs.inventorier(racine) if d["type"] == "crontab"]
    assert trouves and trouves[0]["cable"] is True
    constats = declencheurs.constats(racine, trouves, ["branche:batch.py:2"])
    assert [c for c in constats if c["classe"] == "trigger-non-cable"] == []


def test_une_expression_de_planification_illisible_est_denoncee(tmp_path: Path) -> None:
    racine = _projet(tmp_path)
    _workflow(racine, 'on:\n  schedule:\n    - cron: "tous les jours"\n')
    trouves = declencheurs.inventorier(racine)
    classes = {c["classe"] for c in declencheurs.constats(racine, trouves, [])}
    assert "cron-invalide" in classes


def test_les_raccourcis_nommes_restent_valides(tmp_path: Path) -> None:
    assert declencheurs.cron_lisible("@daily")
    assert declencheurs.cron_lisible("0 3 * * *")
    assert declencheurs.cron_lisible("0 0 3 * * *")  # 6 champs, avec les secondes
    assert not declencheurs.cron_lisible("0 3 * *")
    assert not declencheurs.cron_lisible("")


def test_un_lot_sans_aucun_declencheur_est_denonce(tmp_path: Path) -> None:
    """Un traitement que rien n'enclenche est du code que personne ne fait tourner."""
    constats = declencheurs.constats(tmp_path, [], ["branche:batch.py:2", "rejet:ERR-LOT"])
    assert [c["classe"] for c in constats] == ["job-sans-declencheur"]
    assert "2 élément(s)" in constats[0]["message"]


def test_pas_de_lot_pas_de_constat(tmp_path: Path) -> None:
    """Un projet sans traitement par lot n'a rien à déclencher : le contrôle se tait."""
    assert declencheurs.constats(tmp_path, [], []) == []


# --- Branchement au pan --------------------------------------------------------------------
def test_le_pan_batch_denonce_le_trigger_casse_sans_executer_la_suite(tmp_path: Path) -> None:
    """Un déclencheur cassé se juge STATIQUEMENT : le constat tient même quand la couverture
    n'est pas mesurable (suite non exécutée sous sonde)."""
    from forge_tests.adaptateurs import batch

    racine = _projet(tmp_path)
    (racine / "crontab").write_text("0 2 * * * python jobs/absent.py\n", encoding="utf-8")
    sortie = batch.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert any(f.classe == "trigger-non-cable" for f in sortie.findings)
