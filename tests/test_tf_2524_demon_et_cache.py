"""TF-2524 — la cause d'un démon injoignable se lit sous toutes ses formes, et un paquet absent du
cache se dit « réseau requis ».

Deux faits mesurés le 14/11/2026 par l'agent du lot te :

  1. `test_tf_2012` (démon Docker injoignable) rouge sur un arbre intact, seule cause du « S-01 non
     tenu ». Cause relevée en jouant la sonde réelle sur une adresse morte : la trace de Python 3.13
     CITE le code de la bibliothèque sous chaque cadre, et l'un d'eux porte la chaîne du message
     (`f'Error while fetching server API version: {e}'`). `prealable_conteneur` rendait la PREMIÈRE
     ligne qui correspondait, soit ce code cité, et la preuve publiée ne nommait plus l'exception ;
  2. `preparer_arbre.py` échouait hors ligne sur un paquet absent du cache sans dire que la cause
     était le réseau : la même phrase générique pour un cache incomplet et pour une vraie panne.

Sens prouvés, chacun avec sa fixture :
  - ROUGE avant correction — la trace réelle de Python 3.13 (code cité avant l'exception) ; la
    sortie réelle de `npm ci --offline` et de `uv sync --offline` sur un cache vide ;
  - VERT — les formes que l'outil rendait déjà (une ligne seule, cause chaînée) ; l'échec d'une
    autre nature garde la phrase d'avant ;
  - REMÈDE JOUÉ — la commande que le message recommande est celle de l'étape, sans `--offline`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forge_tests import execution, fabrique_donnees
from recette import preparer_arbre as pa

# --- la trace RÉELLE (sonde jouée sur tcp://127.0.0.1:1, Python 3.13, docker-py 7.x) --------------
TRACE_PYTHON_313 = (
    'Traceback (most recent call last):\n'
    '  File "docker\\api\\client.py", line 230, in _retrieve_server_version\n'
    "    raise DockerException(\n"
    "        f'Error while fetching server API version: {e}'\n"
    "    ) from e\n"
    "docker.errors.DockerException: Error while fetching server API version: "
    "HTTPConnectionPool(host='127.0.0.1', port=1): Max retries exceeded with url: /version\n"
)

TRACE_UNE_LIGNE = (
    "docker.errors.DockerException: Error while fetching server API version: "
    "(2, 'CreateFile', 'Le fichier specifie est introuvable.')\n"
)

TRACE_CAUSE_CHAINEE = (
    "requests.exceptions.ConnectionError: HTTPConnectionPool(host='127.0.0.1', port=1)\n"
    "\n"
    "The above exception was the direct cause of the following exception:\n"
    "\n"
    "Traceback (most recent call last):\n"
    "  File \"docker\\api\\client.py\", line 230, in _retrieve_server_version\n"
    "        f'Error while fetching server API version: {e}'\n"
    "docker.errors.DockerException: Error while fetching server API version: "
    "HTTPConnectionPool(host='127.0.0.1', port=1)\n"
)


@pytest.mark.parametrize(
    "trace", [TRACE_PYTHON_313, TRACE_UNE_LIGNE, TRACE_CAUSE_CHAINEE],
    ids=["python-3.13-code-cite", "une-ligne", "cause-chainee"],
)
def test_la_preuve_nomme_l_exception_sous_toutes_les_formes_de_la_trace(trace: str) -> None:
    preuve = execution.prealable_conteneur(trace)

    assert preuve is not None
    assert preuve.startswith("docker.errors.DockerException:"), preuve


def test_le_motif_publie_cite_l_exception_et_non_le_code_de_la_bibliotheque() -> None:
    """De bout en bout, comme la sonde réelle le rend à `test_tf_2012`."""
    constat = {"statut": "conteneur", "trace": TRACE_PYTHON_313}

    rendu = fabrique_donnees._verdict(constat, {'"t"': 3}, Path("python"))

    assert rendu["verdict"] == "NON_EXECUTABLE"
    assert execution.PREALABLE_ABSENT in rendu["motif"]
    assert "DockerException" in rendu["motif"]


def test_une_trace_sans_demon_injoignable_ne_rend_aucune_preuve() -> None:
    """Contre-épreuve : lire la dernière ligne ne reclasse pas une suite rouge en préalable."""
    assert execution.prealable_conteneur("KeyError: 'sortie'\n") is None
    assert execution.prealable_conteneur("") is None
    assert execution.prealable_conteneur(None) is None  # type: ignore[arg-type]


# --- preparer_arbre : « réseau requis » --------------------------------------------------------
SORTIE_NPM_CACHE_VIDE = (
    "npm error code ENOTCACHED\n"
    "npm error request to https://registry.npmjs.org/yallist/-/yallist-3.1.1.tgz failed: "
    "cache mode is 'only-if-cached' but no cached response is available.\n"
)

SORTIE_UV_CACHE_VIDE = (
    "Using CPython 3.13.14\n"
    "Creating virtual environment at: .venv\n"
    "  × Failed to download `pywin32==312`\n"
    "  ╰─▶ Network connectivity is disabled, but the\n"
    "      requested data wasn't found in the cache for:\n"
    "      `https://files.pythonhosted.org/packages/ba/db/36a78e/"
    "pywin32-312-cp313-cp313-win_amd64.whl`\n"
)


def _arbre_neuf(racine: Path) -> Path:
    for banc in pa.BANCS:
        (racine / "fixtures" / banc / "backend").mkdir(parents=True)
        (racine / "fixtures" / banc / "frontend").mkdir(parents=True)
    return racine


def _echoue_avec(sortie: str, rang: int):
    """Un exécuteur factice dont l'appel `rang` échoue avec `sortie`, les autres réussissent."""
    appels: list[list[str]] = []

    def executer(argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        appels.append(argv)
        cwd = Path(str(options["cwd"]))
        if len(appels) == rang:
            return subprocess.CompletedProcess(argv, 1, "", sortie)
        racine = cwd.parents[2]
        for etape in pa.etapes(racine):
            if etape.dossier == cwd and tuple(argv[1:]) == etape.argv[1:]:
                etape.produit.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    return executer


@pytest.mark.parametrize(
    ("sortie", "rang", "paquet", "commande"),
    [
        (SORTIE_UV_CACHE_VIDE, 1, "pywin32-312-cp313-cp313-win_amd64.whl",
         "uv sync --frozen"),
        (SORTIE_NPM_CACHE_VIDE, 2, "yallist-3.1.1.tgz", "npm ci"),
    ],
    ids=["uv", "npm"],
)
def test_un_paquet_absent_du_cache_dit_qu_il_faut_le_reseau(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    sortie: str, rang: int, paquet: str, commande: str,
) -> None:
    racine = _arbre_neuf(tmp_path)

    assert pa.preparer(racine, _echoue_avec(sortie, rang), lambda nom: f"/outils/{nom}") == 1

    lu = capsys.readouterr().out
    assert "RÉSEAU REQUIS" in lu
    assert f"« {paquet} »" in lu
    assert f"`{commande}`" in lu and "--offline`" not in lu.split("RÉSEAU REQUIS")[1]


def test_le_remede_recommande_est_la_commande_de_l_etape_sans_offline(tmp_path: Path) -> None:
    """Remède joué : ce que le message recommande est exactement l'étape, moins `--offline`."""
    racine = _arbre_neuf(tmp_path)
    for etape in pa.etapes(racine):
        recommandee = pa.commande_en_ligne(etape)
        assert "--offline" not in recommandee
        assert recommandee.split() == [a for a in etape.argv if a != "--offline"]


def test_un_echec_d_une_autre_nature_ne_dit_pas_reseau_requis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Contre-épreuve : la phrase d'avant reste celle de toute cause autre qu'un paquet absent."""
    racine = _arbre_neuf(tmp_path)

    assert pa.preparer(racine, _echoue_avec("error TS2304: Cannot find name 'x'", 3),
                       lambda nom: f"/outils/{nom}") == 1

    lu = capsys.readouterr().out
    assert "RÉSEAU REQUIS" not in lu
    assert "Hors ligne, l'étape lit le cache du poste" in lu


def test_aucun_paquet_dans_une_sortie_vide_ou_etrangere() -> None:
    assert pa.paquet_absent_du_cache("") is None
    assert pa.paquet_absent_du_cache("npm error code E404") is None
