"""TF-0839 — l'ordre d'import de la greffe `FORGE_TESTS_APP`, et son point de rebranchement.

LE FAIT (lot Produit-61, retour du 05/09/2026). Sous audit, la suite backend du projet rendait
**1** ; jouée seule, elle passait. Un cas attendait `409` et lisait un quota resté figé à `20` —
la valeur que le module d'application évalue AU MOMENT DE SON IMPORT, pas celle que le
`conftest.py` du projet installe ensuite. Le même import précoce avait construit le moteur de
base sur l'environnement ambiant : le premier audit a écrit dans la base de DÉMONSTRATION servie
au même moment, et l'a vidée. Trois audits ont été rendus sans mesure des pans `api`, `data` et
`migrations`.

Rien n'était cassé dans le framework. La greffe précoce (`pytest_load_initial_conftests`) est
NÉCESSAIRE pour instrumenter une fabrique d'application — un `conftest.py` qui importe la
fabrique par son nom a déjà capturé l'originale quand la session démarre. Ce qui manquait, c'est
que cet ordre soit ÉCRIT, et surtout qu'il soit REBRANCHABLE : un projet dont le module
d'application évalue quelque chose à l'import n'avait aucun moyen de rendre l'ordre d'avant.

Ces cas jouent le défaut en vrai — un `pytest` de bout en bout dans un projet jetable — plutôt
que d'inspecter la fonction. Un contrôle qui se contenterait de lire `moment_de_greffe()` ne
dirait rien de l'instant où le module est réellement importé, c'est-à-dire du seul fait qui a
coûté quelque chose.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from forge_tests.sondes import sonde_api

#: Le dossier des sondes, tel que `forge_tests.execution` le met sur le `PYTHONPATH` du
#: sous-processus. `-p sonde_api` le charge par son nom, exactement comme en audit réel.
SONDES = Path(sonde_api.__file__).resolve().parent

#: Le module d'application du projet jetable : il ÉVALUE son quota à l'import. C'est la forme
#: qui a coûté le retour — pas une bizarrerie, la forme la plus courante d'un module de réglages.
_APPLICATION = """import os

QUOTA = int(os.environ.get("QUOTA_DEMO", "20"))
"""

#: Le `conftest.py` du projet : il installe l'environnement de test. Il ne peut rien faire de
#: plus tôt — pytest ne lui donne pas la main avant.
_CONFTEST = """import os

os.environ["QUOTA_DEMO"] = "5"
"""

#: Le cas du projet, à l'image de l'E-015 du retour : il attend la valeur du conftest.
_CAS = """from app_du_projet import QUOTA


def test_e015_le_quota_est_celui_du_conftest():
    assert QUOTA == 5, f"quota fige a {QUOTA} : le module a ete importe avant le conftest"
"""


def _projet_jetable(racine: Path) -> None:
    (racine / "app_du_projet.py").write_text(_APPLICATION, encoding="utf-8")
    (racine / "conftest.py").write_text(_CONFTEST, encoding="utf-8")
    (racine / "test_e015.py").write_text(_CAS, encoding="utf-8")


def _jouer(racine: Path, greffe: str | None) -> subprocess.CompletedProcess[str]:
    """Joue la suite du projet jetable sous la sonde, comme `forge_tests.execution` le fait."""
    env = {
        **os.environ,
        "FORGE_TESTS_APP": "app_du_projet:app",
        "PYTHONPATH": os.pathsep.join([str(SONDES), str(racine)]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    }
    env.pop("FORGE_TESTS_APP_GREFFE", None)
    if greffe is not None:
        env["FORGE_TESTS_APP_GREFFE"] = greffe
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header",
         "-p", "no:cacheprovider", "-p", "sonde_api"],
        cwd=racine, env=env, capture_output=True, text=True, timeout=300,
    )


def test_la_greffe_par_defaut_FIGE_le_reglage_avant_le_conftest(tmp_path: Path) -> None:
    """FIXTURE ROUGE — le défaut du 05/09, rejoué : la suite tombe, et pour la bonne raison."""
    _projet_jetable(tmp_path)

    joue = _jouer(tmp_path, greffe=None)

    assert joue.returncode == 1, (
        f"la suite devait tomber sous la greffe precoce\n{joue.stdout}\n{joue.stderr}")
    assert "quota fige a 20" in joue.stdout, (
        f"la CAUSE doit etre lisible dans la trace du projet\n{joue.stdout}")


def test_le_point_de_rebranchement_rend_la_suite_que_le_projet_joue_seul(tmp_path: Path) -> None:
    """FIXTURE VERTE — `FORGE_TESTS_APP_GREFFE=session` : le conftest reprend la main."""
    _projet_jetable(tmp_path)

    joue = _jouer(tmp_path, greffe="session")

    assert joue.returncode == 0, (
        f"la suite devait passer une fois la greffe reportee\n{joue.stdout}\n{joue.stderr}")


def test_sans_la_sonde_la_suite_passe_deja(tmp_path: Path) -> None:
    """TÉMOIN — sans greffe du tout, la suite est verte : c'est bien l'ordre d'import qui décide.

    Sans ce témoin, les deux cas précédents seraient compatibles avec un projet jetable
    simplement mal écrit.
    """
    _projet_jetable(tmp_path)
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    }
    env.pop("FORGE_TESTS_APP", None)
    env.pop("FORGE_TESTS_APP_GREFFE", None)

    joue = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300,
    )

    assert joue.returncode == 0, f"{joue.stdout}\n{joue.stderr}"


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (None, "conftests"),
        ("", "conftests"),
        ("conftests", "conftests"),
        ("session", "session"),
        ("SESSION", "session"),
        (" session ", "session"),
        # Une faute de frappe de configuration ne doit pas rendre rouge la suite du PROJET :
        # la sonde n'a aucun canal de verdict, elle retombe sur le comportement documenté.
        ("plus-tard", "conftests"),
    ],
)
def test_le_moment_demande_est_lu_sans_jamais_faire_echouer_le_projet(
    valeur: str | None, attendu: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FORGE_TESTS_APP_GREFFE", raising=False)
    if valeur is not None:
        monkeypatch.setenv("FORGE_TESTS_APP_GREFFE", valeur)

    assert sonde_api.moment_de_greffe() == attendu


def test_la_cle_de_rebranchement_arrive_seule_dans_le_gabarit_depose(tmp_path: Path) -> None:
    """La clé est DÉRIVÉE du code (TF-0539) : le gabarit la porte sans qu'on l'y ajoute."""
    from forge_tests import gabarit_env

    assert "FORGE_TESTS_APP_GREFFE" in gabarit_env.cles_connues()
    gabarit_env.deposer(tmp_path)
    contenu = (tmp_path / gabarit_env.FICHIER).read_text(encoding="utf-8")
    assert "FORGE_TESTS_APP_GREFFE=" in contenu
