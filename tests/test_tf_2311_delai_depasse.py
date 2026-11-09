"""TF-2311 — un délai dépassé rend DELAI_DEPASSE, distinct de SKIP et d'une suite rouge.

Fait remonté (Produit-86 sous couverture) : la suite backend du produit dépassait 900 s quand le
poste jouait aussi la préproduction. Les pans `api`, `data` et `migrations` rendaient SKIP à 2 jeux
sur 3, avec le verdict PARTIEL d'une configuration absente ; avec `FORGE_TESTS_DELAI_BACKEND_S=1800`
les trois jeux passaient (173/173, 140/140, 12/12).

Décision du 09/11/2026 : un délai dépassé rend un verdict nommé DELAI_DEPASSE, distinct de SKIP et
d'une suite rouge, et le message donne la durée mesurée et le réglage du délai. Même chemin que
TF-2269 (suite rouge nommée) ; le réglage du délai est celui de TF-1675.

Sens prouvés :
  - ROUGE  — sur l'ancien code, les cinq pans qui lisent la mesure de la suite rendaient SKIP ;
  - VERT   — verdict DELAI_DEPASSE, motif qui commence par le nom du verdict, donne la durée
             atteinte, le délai et le réglage, rapport PARTIEL, action de réglage `auto_ia` ;
  - CONTRE-ÉPREUVES — une suite rouge reste FAIL nommé, un délai dépassé par une autre commande
             que la suite (détection de coverage) reste SKIP, un déclencheur cassé garde le FAIL
             du pan `batch`. Le démon injoignable (TF-0299) garde son propre préalable.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from forge_tests import classes, execution, reprise
from forge_tests.adaptateurs import api, batch, data, fichiers, migrations
from forge_tests.noyau import rapport

PANS = [api, data, migrations, batch, fichiers]
REGLAGE = "FORGE_TESTS_DELAI_BACKEND_S"
TRACE_UN_ROUGE = (
    "FAILED tests/test_missions.py::test_creer_une_mission_rend_201 - assert 500 == 201\n"
    "1 failed, 615 passed in 41.20s\n"
)


def _projet(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n"
        "@app.get('/missions')\ndef lister():\n    return []\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "importer.py").write_text(
        "def importer(chemin):\n    with open(chemin, encoding='utf-8') as f:\n"
        "        return f.read()\n",
        encoding="utf-8",
    )
    (tmp_path / "migrations").mkdir(exist_ok=True)
    (tmp_path / "migrations" / "001_init.sql").write_text(
        "-- +migrate Up\nCREATE TABLE mission (id INT);\n-- +migrate Down\nDROP TABLE mission;\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    return tmp_path


def _mesurer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, suite, sonde_coverage=None,
    reglage: str | None = None,
) -> tuple[Path, list[int]]:
    """Mesure la suite d'un projet factice. `suite(commande, delai)` rend le CompletedProcess de
    la suite ou lève TimeoutExpired ; `sonde_coverage` fait de même pour `import coverage`."""
    projet = _projet(tmp_path)
    if reglage is None:
        monkeypatch.delenv(REGLAGE, raising=False)
    else:
        monkeypatch.setenv(REGLAGE, reglage)
    delais: list[int] = []
    reel = subprocess.run  # git et les autres commandes de l'inventaire restent réelles

    def faux_run(commande, **kwargs):
        if "import coverage" in commande:
            if sonde_coverage is not None:
                raise subprocess.TimeoutExpired(commande, kwargs["timeout"])
            return subprocess.CompletedProcess(args=commande, returncode=0, stdout="", stderr="")
        if "coverage" in commande and "run" in commande:  # la suite backend sous coverage
            delais.append(kwargs["timeout"])
            return suite(commande, kwargs["timeout"])
        return reel(commande, **kwargs)

    monkeypatch.setattr(execution.subprocess, "run", faux_run)
    monkeypatch.setattr(execution, "schema_openapi", lambda _b: None)
    execution.mesurer.cache_clear()
    assert execution.mesurer(str(projet)) is None
    return projet, delais


def _depasse(commande, delai):
    raise subprocess.TimeoutExpired(commande, delai)


def _suite_depassant(tmp_path, monkeypatch, reglage=None):
    return _mesurer(tmp_path, monkeypatch, suite=_depasse, reglage=reglage)


def test_la_mesure_retient_le_delai_depasse_de_la_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, delais = _suite_depassant(tmp_path, monkeypatch)
    assert delais == [900]
    depasse = execution.delai_depasse(projet)
    assert depasse is not None and depasse["delai"] == 900 and depasse["duree"] >= 0
    assert execution.suite_rouge(projet) is None  # un délai n'est pas une suite rouge


@pytest.mark.parametrize("module", PANS, ids=lambda m: m.PAN)
def test_rouge_un_delai_depasse_rendait_skip_et_rend_desormais_delai_depasse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module
) -> None:
    projet, _ = _suite_depassant(tmp_path, monkeypatch)
    sortie = module.analyser(projet)
    assert sortie.verdict == "DELAI_DEPASSE", (
        f"{module.PAN} : {sortie.verdict} — {sortie.non_juge[-1] if sortie.non_juge else ''}"
    )
    assert [f for f in sortie.findings if f.classe == classes.SUITE_ROUGE] == []
    motif = sortie.non_juge[-1]
    # le début du motif est ce que le terminal affiche (100 caractères) : verdict et réglage y sont
    assert motif.startswith("DELAI_DEPASSE")
    assert REGLAGE in motif[:100]
    assert re.search(r"interrompue à \d+ s \(délai 900 s\)", motif)
    assert f"{REGLAGE}=1800" in motif and "le double du délai atteint" in motif
    assert "ni une suite rouge" in motif and "ni une mesure impossible" in motif


def test_le_rapport_rend_partiel_nomme_le_verdict_et_classe_l_action_de_reglage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, _ = _suite_depassant(tmp_path, monkeypatch)
    sorties = [m.analyser(projet) for m in PANS]
    rap = rapport(sorties, [m.PAN for m in PANS])
    assert rap["verdict"] == "PARTIEL"
    assert {a["pan"]: a["verdict"] for a in rap["adaptateurs"]} == dict.fromkeys(
        [m.PAN for m in PANS], "DELAI_DEPASSE"
    )
    entrees = {e["pan"]: e for e in rap["pans_non_couverts"]}
    assert set(entrees) == {m.PAN for m in PANS}
    assert all(e["cause"] == "delai-depasse" and e["motif"].startswith("DELAI_DEPASSE")
               for e in entrees.values())
    assert all(REGLAGE in e["pour_couvrir"] or ".env.forge-tests" in e["pour_couvrir"]
               for e in entrees.values())
    assert set(rap["motifs_non_couverture"]) == {m.PAN for m in PANS}
    actions = [a for a in rap["actions"] if a["finding_ref"].startswith("pan-non-couvert:")]
    assert len(actions) == len(PANS)
    assert all(a["categorie"] == "auto_ia" and a["etape_cible"] == "mep-config" for a in actions)
    assert all(REGLAGE in a["attendu"] and "DÉFAUT D'AUDITEUR" not in a["attendu"]
               for a in actions)


def test_le_reglage_du_projet_est_honore_et_le_message_le_double(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, delais = _suite_depassant(tmp_path, monkeypatch, reglage="1800")
    assert delais == [1800]
    motif = api.analyser(projet).non_juge[-1]
    assert "(délai 1800 s)" in motif and f"{REGLAGE}=3600" in motif


def test_la_reprise_garde_un_pan_en_delai_depasse_non_couvert_et_a_rejouer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, _ = _suite_depassant(tmp_path, monkeypatch)
    pans = [m.PAN for m in PANS]
    ancien = rapport([m.analyser(projet) for m in PANS], pans)
    assert sorted(reprise.pans_a_rejouer(ancien)) == sorted(pans)
    fusion = reprise.fusionner(ancien, {}, "rapport.json", [], pans)
    assert fusion["verdict"] == "PARTIEL"
    assert {e["pan"] for e in fusion["pans_non_couverts"]} == set(pans)
    assert all(e["cause"] == "delai-depasse" for e in fusion["pans_non_couverts"])


# --- Contre-épreuves --------------------------------------------------------------------------
@pytest.mark.parametrize("module", PANS, ids=lambda m: m.PAN)
def test_contre_epreuve_une_suite_rouge_reste_fail_et_nomme_son_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module
) -> None:
    def rouge(commande, _delai):
        return subprocess.CompletedProcess(args=commande, returncode=1, stdout=TRACE_UN_ROUGE,
                                           stderr="")

    projet, _ = _mesurer(tmp_path, monkeypatch, suite=rouge)
    sortie = module.analyser(projet)
    assert sortie.verdict == "FAIL"
    assert any(f.classe == classes.SUITE_ROUGE for f in sortie.findings)


@pytest.mark.parametrize("module", PANS, ids=lambda m: m.PAN)
def test_contre_epreuve_le_delai_d_une_autre_commande_que_la_suite_reste_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module
) -> None:
    """La détection de coverage expire : la suite n'a jamais démarré, ce n'est pas son délai."""
    projet, delais = _mesurer(tmp_path, monkeypatch, suite=_depasse, sonde_coverage=True)
    assert delais == []  # la suite n'a pas été lancée
    sortie = module.analyser(projet)
    assert sortie.verdict == "SKIP"


def test_contre_epreuve_le_demon_injoignable_garde_son_prealable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sans_demon(commande, _delai):
        return subprocess.CompletedProcess(
            args=commande, returncode=1, stderr="",
            stdout="E   docker.errors.DockerException: Error while fetching server API version\n",
        )

    projet, _ = _mesurer(tmp_path, monkeypatch, suite=sans_demon)
    assert api.analyser(projet).verdict == "SKIP"


def test_contre_epreuve_un_declencheur_casse_garde_le_fail_du_pan_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet, _ = _suite_depassant(tmp_path, monkeypatch)
    (projet / "crontab").write_text("0 2 * * * python jobs/absent.py\n", encoding="utf-8")
    sortie = batch.analyser(projet)
    assert sortie.verdict == "FAIL"
    assert any(f.classe == "trigger-non-cable" for f in sortie.findings)
    assert any("DELAI_DEPASSE" in ligne for ligne in sortie.non_juge)  # le délai reste dit
