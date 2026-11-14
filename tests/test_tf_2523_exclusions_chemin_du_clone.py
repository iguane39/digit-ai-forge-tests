"""TF-2523 — l'exclusion de périmètre juge le chemin relatif au dépôt, pas celui de son clone.

Le fait, mesuré le 14/11/2026 : `test_tf_0200_prompts` ×2 et `test_tf_0288_ecart_servi_versionne` ×2
rendaient rouge dans un clone posé sous `…\\.claude\\worktrees\\…`, et verts dans un clone placé
ailleurs. Quatre pans (`prompts`, `interface`, `declencheurs`, `securite`) testaient
`chemin.parts` d un chemin ABSOLU contre `exclusions.OUTILLAGE` : `.claude`, dossier PARENT du
dépôt, excluait donc tout son contenu. Une recette qui dépend de l'endroit où elle est posée ne
mesure plus le dépôt, elle mesure le poste.

Deux sens pour chaque pan, chacun avec sa fixture :
  - ROUGE avant correction — le projet posé sous un dossier `.claude` : ses fichiers sont jugés ;
  - VERT, et il le reste — un dossier `.claude` (ou `node_modules`) DANS le projet reste exclu :
    l'exclusion n'est pas levée, elle est recadrée sur ce que le projet contient.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import exclusions
from forge_tests.adaptateurs import interface, prompts, securite
from forge_tests.declencheurs import _fichiers as fichiers_declencheurs

#: Dossiers parents que le dépôt ne choisit pas : chacun est un segment d'`OUTILLAGE` ou de
#: `HORS_PRODUIT`, donc exclu s'il est lu dans un chemin absolu.
PARENTS = [".claude", "node_modules", "build", "output"]


def _poser(racine: Path, relatif: str, contenu: str) -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _projet_sous(tmp_path: Path, parent: str) -> Path:
    """Un projet dont le chemin absolu traverse `parent` (le clone sous `.claude\\worktrees`)."""
    racine = tmp_path / parent / "worktrees" / "clone"
    racine.mkdir(parents=True)
    return racine


# --- le socle -----------------------------------------------------------------------------------
@pytest.mark.parametrize("parent", PARENTS)
def test_chemin_exclu_ne_juge_pas_le_chemin_absolu_du_clone(tmp_path: Path, parent: str) -> None:
    racine = _projet_sous(tmp_path, parent)
    fichier = racine / "src" / "app.py"
    assert not exclusions.chemin_exclu(fichier, racine=racine)
    # sans racine, le chemin entier se juge comme avant (comportement public inchangé)
    assert exclusions.chemin_exclu(fichier) is (parent in exclusions.socle())


def test_un_dossier_exclu_dans_le_projet_reste_exclu(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, ".claude")
    assert exclusions.chemin_exclu(racine / ".claude" / "x.py", racine=racine)
    assert exclusions.chemin_exclu(racine / "src" / "node_modules" / "x.js", racine=racine)


def test_un_chemin_hors_de_la_racine_rend_ses_segments_entiers(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, ".claude")
    ailleurs = tmp_path / "autre" / "node_modules" / "x.js"
    assert exclusions.parties_du_projet(ailleurs, racine) == ailleurs.parts
    assert exclusions.chemin_exclu(ailleurs, racine=racine)


# --- les quatre pans ----------------------------------------------------------------------------
@pytest.mark.parametrize("parent", PARENTS)
def test_prompts_juge_un_projet_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "prompts/assistant.prompt", "Tu réponds à une question.\n")
    assert [p.name for p in prompts._fichiers(racine)] == ["assistant.prompt"]


def test_prompts_ecarte_toujours_un_dossier_d_outillage_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, ".claude")
    _poser(racine, "prompts/assistant.prompt", "Tu réponds à une question.\n")
    _poser(racine, ".claude/agents/autre.prompt", "Un prompt d'outillage.\n")
    _poser(racine, "node_modules/lib/tiers.prompt", "Un prompt de dépendance.\n")
    assert [p.name for p in prompts._fichiers(racine)] == ["assistant.prompt"]


@pytest.mark.parametrize("parent", PARENTS)
def test_interface_juge_un_projet_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "site/index.html", "<html><body><button>Ok</button></body></html>\n")
    assert [p.name for p in interface._fichiers(racine, (".html",))] == ["index.html"]


def test_interface_ecarte_toujours_un_dossier_d_outillage_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, ".claude")
    _poser(racine, "site/index.html", "<html></html>\n")
    _poser(racine, ".claude/page.html", "<html></html>\n")
    _poser(racine, "node_modules/lib/page.html", "<html></html>\n")
    assert [p.name for p in interface._fichiers(racine, (".html",))] == ["index.html"]


@pytest.mark.parametrize("parent", PARENTS)
def test_declencheurs_juge_un_projet_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, ".github/workflows/nuit.yml", "on:\n  schedule:\n    - cron: '0 3 * * *'\n")
    assert [p.name for p in fichiers_declencheurs(racine, ("*.yml",))] == ["nuit.yml"]


def test_declencheurs_ecarte_toujours_un_dossier_d_outillage_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, ".claude")
    _poser(racine, ".github/workflows/nuit.yml", "on: push\n")
    _poser(racine, ".claude/ci.yml", "on: push\n")
    assert [p.name for p in fichiers_declencheurs(racine, ("*.yml",))] == ["nuit.yml"]


_SANS_IDENTIFIANT = (
    "import os\n"
    "from azure.identity import DefaultAzureCredential\n\n"
    "IDENTITE = os.environ['AZURE_CLIENT_ID']\n\n"
    "def fournisseur_de_jetons():\n"
    "    return DefaultAzureCredential()\n"
)


@pytest.mark.parametrize("parent", PARENTS)
def test_securite_juge_un_projet_pose_sous_un_dossier_d_outillage(
    tmp_path: Path, parent: str
) -> None:
    racine = _projet_sous(tmp_path, parent)
    _poser(racine, "backend/app/identite.py", _SANS_IDENTIFIANT)
    assert len(securite._findings_identite_assignee(racine / "backend")) == 1


def test_securite_ecarte_toujours_un_dossier_d_outillage_du_projet(tmp_path: Path) -> None:
    racine = _projet_sous(tmp_path, ".claude")
    _poser(racine, "backend/node_modules/lib/identite.py", _SANS_IDENTIFIANT)
    assert securite._findings_identite_assignee(racine / "backend") == []
