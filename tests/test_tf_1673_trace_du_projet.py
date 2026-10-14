"""TF-1673 — `FORGE_TESTS_PLAYWRIGHT_TRACE` réglé dans `.env.forge-tests` n était pas appliqué.

Le fait, remis par Produit-80 le 12/10/2026 (RT-2 du lot 20261012b, ledger seq 333 à 335) : le
projet réglait `FORGE_TESTS_PLAYWRIGHT_TRACE=on` dans son `.env.forge-tests`. L audit 12 a rendu
le pan front « non mesurable, trace désactivée par le projet » sur une suite e2e verte ; l audit
13, avec la même variable posée dans le shell, a mesuré 382 sur 427. Coût : un audit complet
relancé, environ 20 minutes.

Cause : `front_execute` lisait le mode de trace AVANT de charger le contrat du projet, que seul
`_env_front` chargeait, plus bas. Quand aucun autre pan n avait chargé `.env.forge-tests` avant
lui, le réglage du projet était ignoré sans signal.

Ces tests fixent les deux volets de la piste du retour : le réglage du fichier est APPLIQUÉ, et
le motif DIT d où vient la valeur retenue.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from forge_tests import authentification, execution


@pytest.fixture()
def env_propre(tmp_path: Path, monkeypatch):
    """`charger_env` écrit dans `os.environ` : on part d un environnement sans `FORGE_TESTS_*`
    et sans le `.env` du poste, puis on restaure tout."""
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _projet(racine: Path, config_trace: str, env_projet: str | None) -> None:
    front = racine / "frontend"
    (front / "node_modules").mkdir(parents=True)
    (front / "playwright.config.ts").write_text(
        f'export default {{ use: {{ trace: "{config_trace}" }} }};\n', encoding="utf-8"
    )
    if env_projet is not None:
        (racine / ".env.forge-tests").write_text(env_projet, encoding="utf-8")


def _jouer(racine: Path, monkeypatch) -> list[list[str]]:
    commandes: list[list[str]] = []

    def _run_stub(commande, *, banc, domaine, quoi, **kwargs):
        commandes.append(list(commande))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="10 passed", stderr="")

    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(execution, "_run", _run_stub)
    execution.front_execute.cache_clear()
    execution.front_execute(str(racine))
    return commandes


def test_le_reglage_du_fichier_du_projet_est_applique(
    tmp_path: Path, monkeypatch, env_propre
) -> None:
    """ROUGE avant le correctif : le cas réel de Produit-80. Le `playwright.config` choisit
    `retain-on-failure`, le `.env.forge-tests` demande `on` : aucun `--trace` n était passé et la
    config du projet gouvernait seule, la mesure était perdue."""
    _projet(tmp_path, "retain-on-failure", "FORGE_TESTS_PLAYWRIGHT_TRACE=on\n")

    commandes = _jouer(tmp_path, monkeypatch)

    assert len(commandes) == 1
    assert "--trace" in commandes[0]
    assert commandes[0][commandes[0].index("--trace") + 1] == "on"


def test_sans_reglage_le_choix_du_playwright_config_gouverne_encore(
    tmp_path: Path, monkeypatch, env_propre
) -> None:
    """VERT de non-régression (TF-0132) : sans réglage nulle part, rien n est imposé en CLI."""
    _projet(tmp_path, "retain-on-failure", None)

    commandes = _jouer(tmp_path, monkeypatch)

    assert "--trace" not in commandes[0]


def test_le_shell_de_l_operateur_garde_le_dernier_mot(
    tmp_path: Path, monkeypatch, env_propre
) -> None:
    """`charger_env` ne surcharge jamais une variable déjà posée : la valeur du shell prime."""
    _projet(tmp_path, "retain-on-failure", "FORGE_TESTS_PLAYWRIGHT_TRACE=on\n")
    monkeypatch.setenv("FORGE_TESTS_PLAYWRIGHT_TRACE", "off")

    commandes = _jouer(tmp_path, monkeypatch)

    assert commandes[0][commandes[0].index("--trace") + 1] == "off"


@pytest.mark.parametrize(
    ("env_projet", "shell", "attendu", "refuse"),
    [
        (
            "FORGE_TESTS_PLAYWRIGHT_TRACE=off\n",
            None,
            "lu dans `.env.forge-tests`",
            "playwright.config",
        ),
        (None, "off", "environnement de l operateur", ".env.forge-tests"),
        (None, None, "son propre playwright.config choisit trace='retain-on-failure'", "lu dans"),
    ],
)
def test_le_motif_nomme_la_provenance_de_la_valeur_retenue(
    tmp_path: Path, monkeypatch, env_propre, env_projet, shell, attendu, refuse
) -> None:
    """ROUGE avant le correctif pour les deux premiers cas : le motif attribuait toujours le mode
    au `playwright.config` du projet, même quand il venait d ailleurs."""
    _projet(tmp_path, "retain-on-failure", env_projet)
    if shell is not None:
        monkeypatch.setenv("FORGE_TESTS_PLAYWRIGHT_TRACE", shell)

    _jouer(tmp_path, monkeypatch)

    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "non mesurable" in motif.lower()
    assert attendu in motif
    assert refuse not in motif
