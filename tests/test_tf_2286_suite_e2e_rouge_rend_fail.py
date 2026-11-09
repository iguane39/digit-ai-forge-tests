"""TF-2286 — une suite e2e Playwright ROUGE rend FAIL et nomme le test rouge, jamais SKIP.

Pendant front de TF-2269 (Produit-86, RP-42) : `execution.front_execute` déclarait « couverture
front non mesurable tant que la suite est rouge » et le pan `front` rendait SKIP, le même verdict
PARTIEL qu'un jeu vert ou qu'une suite qu'on n'a pas pu lancer. Le rapport ne nommait pas le test
rouge.

Décision du 09/11/2026 (R-58) : le pan front rend FAIL, un finding bloquant par test rouge, comme
le backend depuis TF-2269.

Sens prouvés :
  - ROUGE  — sur l'ancien code, le pan `front` rendait SKIP pour une suite Playwright en échec ;
  - VERT   — FAIL, un finding bloquant par test rouge, le test nommé dans le message (JUnit de
             Playwright d'abord, numérotation de la ligne de commande à défaut) ;
  - CONTRE-ÉPREUVES — un port occupé, une trace indisponible, une suite qui ne collecte aucun test
             et une suite verte ne sont PAS des tests rouges ; le motif honnête reste au non-jugé.
Playwright n'est jamais lancé : `_run` est remplacé, comme dans TF-0132.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from forge_tests import actions, classes, execution, revue
from forge_tests.adaptateurs import front
from forge_tests.noyau import Finding, rapport

TEST_ROUGE_JUNIT = "a.spec.ts::a.spec.ts:3:5 › creer une mission"
JUNIT_UN_ROUGE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<testsuites><testsuite name="a.spec.ts" tests="2" failures="1">'
    '<testcase name="a.spec.ts:3:5 › creer une mission" classname="a.spec.ts">'
    '<failure message="expect(received).toBe(expected)" type="FAILURE">Error: 500 != 201'
    "</failure></testcase>"
    '<testcase name="a.spec.ts:9:5 › lister les missions" classname="a.spec.ts"/>'
    "</testsuite></testsuites>\n"
)
LIGNE_DE_COMMANDE_UN_ROUGE = (
    "[1/2] [chromium] › e2e/b.spec.ts:7:5 › ouvrir le tableau\n"
    "\n"
    "  1) [chromium] › e2e/b.spec.ts:7:5 › ouvrir le tableau ─────────────────────────\n"
    "     Error: expect(received).toBeVisible()\n"
    "\n"
    "  1 failed\n"
    "  1 passed (4.1s)\n"
)


def _projet(tmp_path: Path) -> Path:
    front_dir = tmp_path / "frontend"
    (front_dir / "node_modules").mkdir(parents=True)
    (front_dir / "src").mkdir()
    (front_dir / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    return tmp_path


def _suite_rendant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    code: int = 1,
    junit: str | None = None,
    trace_zip: bool = True,
) -> Path:
    projet = _projet(tmp_path)

    def faux_run(commande, *, banc, domaine, quoi, **kwargs):
        if junit is not None:
            Path(kwargs["env"]["PLAYWRIGHT_JUNIT_OUTPUT_NAME"]).write_text(junit, encoding="utf-8")
        if trace_zip:
            artefacts = Path(commande[commande.index("--output") + 1])
            (artefacts / "un-test").mkdir(parents=True, exist_ok=True)
            zipfile.ZipFile(artefacts / "un-test" / "trace.zip", "w").close()  # archive vide valide
        return subprocess.CompletedProcess(args=commande, returncode=code, stdout=stdout, stderr="")

    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(execution, "_run", faux_run)
    monkeypatch.setattr(revue, "analyser_suite", lambda _cible: [])
    execution.front_execute.cache_clear()
    return projet


def test_rouge_une_suite_e2e_rouge_rendait_skip_et_rend_desormais_fail_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, "1 failed", junit=JUNIT_UN_ROUGE)

    sortie = front.analyser(projet)

    assert sortie.verdict == "FAIL", (
        f"{sortie.verdict} — {sortie.non_juge[-1] if sortie.non_juge else ''}"
    )
    rouges = [f for f in sortie.findings if f.classe == classes.SUITE_ROUGE]
    assert [f.id for f in rouges] == [f"suite-rouge:{TEST_ROUGE_JUNIT}"]
    assert rouges[0].severite == "bloquant"
    assert "creer une mission" in rouges[0].message
    assert "Error: 500 != 201" in rouges[0].message
    assert "e2e (Playwright)" in rouges[0].message
    # le motif honnête reste au non-jugé : la couverture, elle, n'est pas mesurée
    assert any("couverture non mesurable tant que la suite est rouge" in n for n in sortie.non_juge)


def test_sans_junit_le_test_rouge_est_nomme_par_la_ligne_de_commande(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, LIGNE_DE_COMMANDE_UN_ROUGE)

    rouge = execution.suite_rouge_front(projet)

    assert rouge is not None
    assert [t["id"] for t in rouge["tests"]] == [
        "[chromium] › e2e/b.spec.ts:7:5 › ouvrir le tableau"
    ]
    assert front.analyser(projet).verdict == "FAIL"


def test_une_suite_en_echec_sans_test_nomme_n_invente_aucun_nom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Code non nul, ni JUnit ni ligne numérotée (erreur de démarrage) : FAIL tout de même, le
    finding désigne la suite entière, comme le backend."""
    projet = _suite_rendant(tmp_path, monkeypatch, "Error: global setup failed")

    sortie = front.analyser(projet)

    assert sortie.verdict == "FAIL"
    assert [f.id for f in sortie.findings if f.classe == classes.SUITE_ROUGE] == [
        "suite-rouge:suite-entiere"
    ]


def test_les_constats_de_la_revue_statique_restent_avec_le_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le FAIL de la suite ne fait pas disparaître ce que la revue de suite a vu sans l'exécuter."""
    projet = _suite_rendant(tmp_path, monkeypatch, "1 failed", junit=JUNIT_UN_ROUGE)
    faux_vert = Finding(id="revue:x", classe=classes.FAUX_VERT_ABSENCE, localisation="a.spec.ts",
                        message="absence sans présence")
    monkeypatch.setattr(revue, "analyser_suite", lambda _cible: [faux_vert])

    ids = [f.id for f in front.analyser(projet).findings]

    assert "revue:x" in ids and f"suite-rouge:{TEST_ROUGE_JUNIT}" in ids


def test_le_rapport_rend_fail_et_non_partiel_avec_une_action_pour_le_test_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, "1 failed", junit=JUNIT_UN_ROUGE)

    rap = rapport([front.analyser(projet)], [front.PAN])

    assert rap["verdict"] == "FAIL"
    refs = [a for a in rap["actions"] if "creer une mission" in a["finding_ref"]]
    assert refs and all(a["categorie"] == "manuelle_dev" for a in refs)
    assert all("DÉFAUT D'AUDITEUR" not in a["attendu"] for a in refs)
    assert classes.SUITE_ROUGE in actions._REGLES


# --- Contre-épreuves : ce qui n'est PAS un test rouge ---------------------------------------------
def test_une_suite_verte_n_est_pas_rouge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    projet = _suite_rendant(tmp_path, monkeypatch, "2 passed", code=0, junit=JUNIT_UN_ROUGE)
    execution.front_execute(str(projet))

    assert execution.suite_rouge_front(projet) is None


def test_un_port_occupe_n_est_pas_une_suite_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aucun test n'a tourné : le webServer n'a pas démarré (TF-0136)."""
    projet = _suite_rendant(
        tmp_path, monkeypatch, "Error: http://localhost:4173 is already used", trace_zip=False
    )

    assert execution.suite_rouge_front(projet) is None
    assert front.analyser(projet).verdict == "SKIP"


def test_une_trace_indisponible_n_est_pas_une_suite_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode `on`, code non nul, aucun trace.zip : l'écriture de la trace est en cause, pas la
    suite (TF-0132)."""
    projet = _suite_rendant(
        tmp_path, monkeypatch, "Test timeout of 60000ms exceeded.", trace_zip=False
    )

    assert execution.suite_rouge_front(projet) is None
    assert front.analyser(projet).verdict == "SKIP"


def test_une_suite_qui_ne_collecte_aucun_test_n_est_pas_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Playwright rend le code 1 sur « No tests found » : une mesure absente, pas un test en échec
    (TF-0605)."""
    projet = _suite_rendant(tmp_path, monkeypatch, "Error: No tests found")

    assert execution.suite_rouge_front(projet) is None
    assert front.analyser(projet).verdict == "SKIP"


def test_le_backend_garde_son_libelle(tmp_path: Path) -> None:
    """Le domaine par défaut reste `backend` : la généralisation ne change pas TF-2269."""
    import inspect

    parametres = inspect.signature(execution.sortie_suite_rouge).parameters
    assert parametres["domaine"].default == "backend"
