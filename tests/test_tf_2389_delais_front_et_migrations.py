"""TF-2389 — le front e2e et le rejeu des migrations rendent DELAI_DEPASSE, délai réglable.

Reste de TF-2311 : `execution.py` fixait à 900 s, sans réglage, le délai de la suite e2e Playwright
et celui du rejeu des migrations sur base neuve. Un dépassement rendait le pan `front` en SKIP
« couverture non mesurable », indiscernable d'une suite qu'on n'a pas pu lancer, et laissait les
pans `migrations` et `data` sans verdict de délai : le rejeu interrompu se lisait « schéma réel non
introspectable » à côté d'un PASS.

Décision du 10/11/2026 : le front e2e et le rejeu des migrations prennent un réglage de délai et le
verdict DELAI_DEPASSE de TF-2311, avec fixture.

Sens prouvés :
  - ROUGE  — sur l'ancien code, le délai de 900 s ne se règle pas, le pan `front` rend SKIP, les
             pans `migrations` et `data` gardent le PASS de leur couverture ;
  - VERT   — `FORGE_TESTS_DELAI_FRONT_S` et `FORGE_TESTS_DELAI_MIGRATIONS_S` honorés, verdict
             DELAI_DEPASSE, motif qui commence par le nom du verdict, donne durée, délai, réglage et
             valeur à essayer, rapport PARTIEL, action de réglage `auto_ia` ;
  - CONTRE-ÉPREUVES — une suite e2e rouge reste FAIL, un port occupé reste un SKIP motivé, un rejeu
             en échec POUR SA RAISON garde son motif, un FAIL de migrations reste FAIL.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from forge_tests import classes, execution, revue
from forge_tests.adaptateurs import data, front, migrations
from forge_tests.noyau import rapport

REGLAGE_FRONT = "FORGE_TESTS_DELAI_FRONT_S"
REGLAGE_MIGRATIONS = "FORGE_TESTS_DELAI_MIGRATIONS_S"


def _projet_front(tmp_path: Path) -> Path:
    racine = tmp_path / "frontend"
    (racine / "node_modules").mkdir(parents=True)
    (racine / "src").mkdir()
    (racine / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    return tmp_path


def _front_qui_depasse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, reglage: str | None = None,
    sortie: subprocess.CompletedProcess | None = None,
) -> tuple[Path, list[int]]:
    """Un projet dont la suite e2e dépasse son délai (ou rend `sortie`). Rend (projet, délais)."""
    projet = _projet_front(tmp_path)
    if reglage is None:
        monkeypatch.delenv(REGLAGE_FRONT, raising=False)
    else:
        monkeypatch.setenv(REGLAGE_FRONT, reglage)
    delais: list[int] = []
    reel = subprocess.run  # git et les autres commandes de l'inventaire restent réelles

    def faux_run(commande, **kwargs):
        if "playwright" not in commande:
            return reel(commande, **kwargs)
        delais.append(kwargs["timeout"])
        if sortie is not None:
            artefacts = Path(commande[commande.index("--output") + 1])
            (artefacts / "un-test").mkdir(parents=True, exist_ok=True)
            zipfile.ZipFile(artefacts / "un-test" / "trace.zip", "w").close()  # trace écrite
            return subprocess.CompletedProcess(commande, sortie.returncode, sortie.stdout, "")
        raise subprocess.TimeoutExpired(commande, kwargs["timeout"])

    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(execution.subprocess, "run", faux_run)
    monkeypatch.setattr(revue, "analyser_suite", lambda _cible: [])
    execution.front_execute.cache_clear()
    return projet, delais


# --- Front e2e ----------------------------------------------------------------------------------
def test_rouge_un_delai_e2e_depasse_rendait_skip_et_rend_desormais_delai_depasse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, delais = _front_qui_depasse(tmp_path, monkeypatch)
    sortie = front.analyser(projet)
    assert delais == [900]
    assert sortie.verdict == "DELAI_DEPASSE", (
        f"{sortie.verdict} — {sortie.non_juge[-1] if sortie.non_juge else ''}"
    )
    assert [f for f in sortie.findings if f.classe == classes.SUITE_ROUGE] == []
    motif = sortie.non_juge[-1]
    assert motif.startswith("DELAI_DEPASSE") and REGLAGE_FRONT in motif[:100]
    assert re.search(r"interrompue à \d+ s \(délai 900 s\)", motif)
    assert f"{REGLAGE_FRONT}=1800" in motif and "le double du délai atteint" in motif
    assert "ni une suite rouge" in motif and "ni une mesure impossible" in motif


def test_le_reglage_du_front_est_honore_et_le_message_le_double(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, delais = _front_qui_depasse(tmp_path, monkeypatch, reglage="1800")
    motif = front.analyser(projet).non_juge[-1]
    assert delais == [1800]
    assert "(délai 1800 s)" in motif and f"{REGLAGE_FRONT}=3600" in motif


@pytest.mark.parametrize("brut", ["bientot", "0", "-5"])
def test_un_reglage_front_illisible_laisse_le_defaut_et_le_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, brut: str
) -> None:
    projet, delais = _front_qui_depasse(tmp_path, monkeypatch, reglage=brut)
    sortie = front.analyser(projet)
    assert delais == [900]
    assert sortie.verdict == "DELAI_DEPASSE"
    assert "illisible" in " ".join(sortie.non_juge) or "illisible" in (
        execution.motif_indisponibilite(projet, "front", "")
    )


def test_le_rapport_rend_partiel_et_classe_l_action_de_reglage_du_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, _ = _front_qui_depasse(tmp_path, monkeypatch)
    sortie = front.analyser(projet)
    rap = rapport([sortie], [front.PAN])
    assert rap["verdict"] == "PARTIEL"
    entree = rap["pans_non_couverts"][0]
    assert entree["cause"] == "delai-depasse" and entree["motif"].startswith("DELAI_DEPASSE")
    action = next(a for a in rap["actions"] if a["finding_ref"] == f"pan-non-couvert:{front.PAN}")
    assert action["categorie"] == "auto_ia" and action["etape_cible"] == "mep-config"
    assert REGLAGE_FRONT in action["attendu"]


def test_contre_epreuve_une_suite_e2e_rouge_reste_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rouge = subprocess.CompletedProcess(
        [], 1, "  1) [chromium] › e2e/b.spec.ts:7:5 › ouvrir le tableau ─────────\n  1 failed\n", ""
    )
    projet, _ = _front_qui_depasse(tmp_path, monkeypatch, sortie=rouge)
    sortie = front.analyser(projet)
    assert sortie.verdict == "FAIL"
    assert any(f.classe == classes.SUITE_ROUGE for f in sortie.findings)


def test_contre_epreuve_un_port_occupe_reste_un_skip_motive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    occupe = subprocess.CompletedProcess(
        [], 1,
        "Error: http://localhost:4173 is already used, make sure that nothing is running on the "
        "port", "",
    )
    projet, _ = _front_qui_depasse(tmp_path, monkeypatch, sortie=occupe)
    sortie = front.analyser(projet)
    assert sortie.verdict == "SKIP"
    assert "port deja occupe" in " ".join(sortie.non_juge)


# --- Rejeu des migrations ------------------------------------------------------------------------
def _projet_migrations(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001_init.sql").write_text(
        "-- +migrate Up\nCREATE TABLE mission (id INT);\n-- +migrate Down\nDROP TABLE mission;\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    return tmp_path


def _rejeu_qui_depasse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, reglage: str | None = None,
    resultat: subprocess.CompletedProcess | None = None,
) -> tuple[Path, list[int]]:
    projet = _projet_migrations(tmp_path)
    if reglage is None:
        monkeypatch.delenv(REGLAGE_MIGRATIONS, raising=False)
    else:
        monkeypatch.setenv(REGLAGE_MIGRATIONS, reglage)
    delais: list[int] = []
    reel = subprocess.run  # git et les autres commandes de l'inventaire restent réelles

    def faux_run(commande, **kwargs):
        if not any("verifier_schema" in str(c) for c in commande):
            return reel(commande, **kwargs)
        delais.append(kwargs["timeout"])
        if resultat is not None:
            return subprocess.CompletedProcess(commande, resultat.returncode, "", resultat.stderr)
        raise subprocess.TimeoutExpired(commande, kwargs["timeout"])

    monkeypatch.setattr(execution.subprocess, "run", faux_run)
    # la suite backend a tourné : toute la surface des migrations est exercée, seul le rejeu manque
    monkeypatch.setattr(migrations, "exerces", lambda c: {e.id for e in migrations.inventaire(c)})
    monkeypatch.setattr(data, "exerces", lambda c: {e.id for e in data.inventaire(c)})
    execution.schema_obtenu.cache_clear()
    return projet, delais


def test_le_rejeu_des_migrations_se_regle_et_se_retient_comme_delai_depasse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, delais = _rejeu_qui_depasse(tmp_path, monkeypatch, reglage="1200")
    assert execution.schema_obtenu(str(projet)) is None
    assert delais == [1200]
    depasse = execution.delai_depasse(projet, "schema")
    assert depasse is not None and depasse["delai"] == 1200 and depasse["duree"] >= 0
    assert execution.delai_depasse(projet) is None  # la suite backend n'a pas été interrompue


@pytest.mark.parametrize("module", [migrations, data], ids=lambda m: m.PAN)
def test_rouge_un_rejeu_interrompu_gardait_le_pass_et_rend_desormais_delai_depasse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module
) -> None:
    projet, delais = _rejeu_qui_depasse(tmp_path, monkeypatch)
    sortie = module.analyser(projet)
    assert delais == [900]
    assert sortie.verdict == "DELAI_DEPASSE", (
        f"{module.PAN} : {sortie.verdict} — {sortie.non_juge[-1] if sortie.non_juge else ''}"
    )
    motif = next(ligne for ligne in sortie.non_juge if ligne.startswith("DELAI_DEPASSE"))
    assert REGLAGE_MIGRATIONS in motif[:120]
    assert re.search(r"interrompu à \d+ s \(délai 900 s\)", motif)
    assert f"{REGLAGE_MIGRATIONS}=1800" in motif
    assert "ni un schéma divergent" in motif


def test_le_rapport_rend_partiel_pour_un_rejeu_interrompu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, _ = _rejeu_qui_depasse(tmp_path, monkeypatch)
    rap = rapport([migrations.analyser(projet)], [migrations.PAN])
    assert rap["verdict"] == "PARTIEL"
    assert rap["pans_non_couverts"][0]["cause"] == "delai-depasse"
    action = next(a for a in rap["actions"] if a["finding_ref"].startswith("pan-non-couvert:"))
    assert action["categorie"] == "auto_ia" and REGLAGE_MIGRATIONS in action["attendu"]


def test_contre_epreuve_un_rejeu_en_echec_pour_sa_raison_garde_son_motif(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    echec = subprocess.CompletedProcess(
        [], 1, "", 'sqlalchemy.exc.ProgrammingError: relation "mission" does not exist\n'
    )
    projet, _ = _rejeu_qui_depasse(tmp_path, monkeypatch, resultat=echec)
    sortie = migrations.analyser(projet)
    assert sortie.verdict != "DELAI_DEPASSE"
    assert execution.delai_depasse(projet, "schema") is None
    assert "ProgrammingError" in " ".join(sortie.non_juge)


def test_contre_epreuve_un_fail_de_migrations_reste_fail_et_dit_le_delai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, _ = _rejeu_qui_depasse(tmp_path, monkeypatch)
    monkeypatch.setattr(migrations, "exerces", lambda _c: set())  # aucun sens exercé : FAIL
    sortie = migrations.analyser(projet)
    assert sortie.verdict == "FAIL"
    assert any("DELAI_DEPASSE" in ligne for ligne in sortie.non_juge)
