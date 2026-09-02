"""TF-0132 — payé en réel sur Produit-01 le 12/08.

`--trace on` était imposé en dur dans `execution.front_execute` : sur ce poste, l écriture de
l archive de trace ne rend jamais la main, chaque test se déroule intégralement puis expire en
« Test timeout of 60000ms exceeded ». Mesuré : la même suite passe 10/10 en 7,2 s avec
`--trace=off`, et échoue à 100 % avec `--trace=on`. Le pan front concluait « la suite e2e s est
terminée en échec » sur une suite entièrement verte — un faux négatif produit par une option
que la forge impose elle-même — et un projet ayant déjà réglé `trace` dans son
`playwright.config.ts` (par exemple pour contourner ce même blocage) voyait son choix écrasé.

Deux volets, vérifiés séparément :
  (a) le mode de trace n est plus imposé en dur — variable d environnement
      `FORGE_TESTS_PLAYWRIGHT_TRACE`, puis config du projet, puis défaut `on` de la forge ;
  (b) un code de sortie non nul avec le mode `on` et AUCUN `trace.zip` produit nomme la trace
      («TRACE INDISPONIBLE»), jamais «suite e2e ROUGE» — sauf si un `trace.zip` existe bel et
      bien, auquel cas c est une vraie régression de la suite (témoin rouge conservé).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from forge_tests import execution


def _projet_front(tmp_path: Path, config_trace: str | None = None) -> Path:
    front = tmp_path / "frontend"
    (front / "node_modules").mkdir(parents=True)
    contenu = "export default {};\n"
    if config_trace is not None:
        contenu = f'export default {{ use: {{ trace: "{config_trace}" }} }};\n'
    (front / "playwright.config.ts").write_text(contenu, encoding="utf-8")
    return front


# --- (a) le mode de trace n est plus impose en dur ---------------------------------------------
def test_mode_trace_projet_lit_la_config_playwright(tmp_path: Path) -> None:
    front = _projet_front(tmp_path, config_trace="retain-on-failure")
    assert execution._mode_trace_projet(front) == "retain-on-failure"


def test_mode_trace_projet_absent_sans_reglage(tmp_path: Path) -> None:
    front = _projet_front(tmp_path)
    assert execution._mode_trace_projet(front) is None


def test_mode_trace_variable_environnement_gagne_toujours(
    tmp_path: Path, monkeypatch
) -> None:
    """La variable d environnement est le dernier mot — y compris pour DESACTIVER la trace."""
    front = _projet_front(tmp_path, config_trace="retain-on-failure")
    monkeypatch.setenv("FORGE_TESTS_PLAYWRIGHT_TRACE", "off")

    argument_cli, mode_effectif = execution._mode_trace(front)

    assert argument_cli == "off"
    assert mode_effectif == "off"


def test_mode_trace_respecte_le_choix_du_projet_sans_lecraser(tmp_path: Path) -> None:
    """ROUGE implicite : avant le correctif, `--trace on` était TOUJOURS passé en CLI et
    écrasait le `retain-on-failure` du projet, quel que soit son contenu."""
    front = _projet_front(tmp_path, config_trace="retain-on-failure")

    argument_cli, mode_effectif = execution._mode_trace(front)

    # Rien n est passé en CLI : la config du projet gouverne seule, jamais écrasée.
    assert argument_cli is None
    assert mode_effectif == "retain-on-failure"


def test_mode_trace_replie_sur_on_a_defaut(tmp_path: Path) -> None:
    front = _projet_front(tmp_path)
    argument_cli, mode_effectif = execution._mode_trace(front)
    assert argument_cli == "on"
    assert mode_effectif == "on"


# --- (b) code de sortie non nul : trace indisponible vs suite reellement rouge ------------------
def _front_execute_avec(tmp_path: Path, monkeypatch, resultat, config_trace=None) -> dict | None:
    _projet_front(tmp_path, config_trace=config_trace)
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(execution, "_run", lambda *_a, **_k: resultat)
    execution.front_execute.cache_clear()
    return execution.front_execute(str(tmp_path))


def test_code_non_nul_sans_trace_produite_nomme_la_trace_jamais_la_suite(
    tmp_path: Path, monkeypatch
) -> None:
    """Le cas RÉEL constaté sur Produit-01 : mode `on`, code non nul, AUCUN trace.zip produit
    (l écriture a timeout) — la suite ne doit PAS être accusée.

    ROUGE implicite : avant le correctif, ce cas produisait exactement
    « la suite e2e s est terminée en échec » sur une suite verte de bout en bout.
    """
    resultat = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="Test timeout of 60000ms exceeded.", stderr=""
    )
    mesure = _front_execute_avec(tmp_path, monkeypatch, resultat)

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "trace" in motif.lower()
    assert "indisponible" in motif.lower()
    assert "suite e2e" not in motif.lower() or "termin" not in motif.lower()
    assert "FORGE_TESTS_PLAYWRIGHT_TRACE" in motif


def test_code_non_nul_avec_trace_produite_reste_une_suite_rouge(
    tmp_path: Path, monkeypatch
) -> None:
    """Témoin discriminant : si un `trace.zip` EXISTE malgré l échec, la suite est bel et bien
    rouge — le correctif ne doit pas faire disparaître une vraie régression."""
    front = tmp_path / "frontend"
    front.mkdir(parents=True, exist_ok=True)

    def _run_stub(commande, *, banc, domaine, quoi, **kwargs):
        sortie = Path(kwargs["cwd"]).parent  # non utilisé — le vrai --output est dans commande
        idx = commande.index("--output")
        artefacts = Path(commande[idx + 1])
        dossier_trace = artefacts / "un-test" / "trace.zip"
        dossier_trace.parent.mkdir(parents=True, exist_ok=True)
        dossier_trace.write_bytes(b"")
        del sortie
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="1 failed\n  expect(received).toBe(expected)", stderr=""
        )

    _projet_front(tmp_path)
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(execution, "_run", _run_stub)
    execution.front_execute.cache_clear()

    mesure = execution.front_execute(str(tmp_path))

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "suite e2e" in motif.lower() and "échec" in motif.lower()
    assert "trace indisponible" not in motif.lower()


def test_code_non_nul_en_mode_off_reste_une_suite_rouge_sans_ambiguite(
    tmp_path: Path, monkeypatch
) -> None:
    """La distinction trace/suite ne joue QUE pour le mode `on`, seul mode où l absence de
    `trace.zip` est anormale. En mode `off` (choisi explicitement), son absence est attendue et
    ne dit rien sur l état de la suite."""
    resultat = subprocess.CompletedProcess(args=[], returncode=1, stdout="1 failed", stderr="")
    monkeypatch.setenv("FORGE_TESTS_PLAYWRIGHT_TRACE", "off")
    mesure = _front_execute_avec(tmp_path, monkeypatch, resultat)

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "suite e2e" in motif.lower() and "échec" in motif.lower()
    assert "trace indisponible" not in motif.lower()


def test_la_commande_transmet_bien_le_mode_choisi(tmp_path: Path, monkeypatch) -> None:
    """Bout en bout : la commande réellement lancée porte le mode ISSU de `_mode_trace`, pas
    une valeur `on` codée en dur."""
    _projet_front(tmp_path, config_trace="retain-on-failure")
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    commandes: list[list[str]] = []

    def _run_stub(commande, *, banc, domaine, quoi, **kwargs):
        commandes.append(list(commande))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="10 passed", stderr="")

    monkeypatch.setattr(execution, "_run", _run_stub)
    execution.front_execute.cache_clear()

    execution.front_execute(str(tmp_path))

    assert len(commandes) == 1
    # Le choix du projet (retain-on-failure) gouverne seul : aucun `--trace` n est passé en CLI.
    assert "--trace" not in commandes[0]
