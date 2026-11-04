"""TF-2118 — le pan prompts auditait les fichiers non suivis d une autre session.

Fait remonté par Produit-86 (lot du 03/11/2026, RT-9) : le pan `prompts` a inventorié trois alias
de modèles trouvés dans `outils/compteur-foundry/`, dossier NON suivi par git, écrit par une autre
session sur le même arbre. Résultat : 7 constats bloquants (modèle non épinglé, jamais exercé,
seuil 0/3) attribués au produit, alors qu aucun fichier suivi ne nomme ces modèles.

La règle corrigée : dans un dépôt git, le pan inventorie les sources SUIVIES (`git ls-files`) ; les
fichiers non suivis qu il rencontre et qui porteraient quelque chose (prompt, corpus, modèle,
appel de fournisseur) sont PUBLIÉS à part (`non_juge`), sans être comptés au produit. Hors dépôt
git, le comportement est inchangé.

Quatre sens, chacun avec sa fixture :
  - ROUGE  — un fichier non suivi nomme un alias : avant la correction, un constat bloquant ;
  - VERT   — le même fichier, suivi (ajouté à l index) : le pan le juge toujours ;
  - HORS GIT — aucun dépôt : le fichier est jugé comme avant ;
  - HONNÊTETÉ — le fichier écarté est nommé au rapport, et ne vaut jamais preuve d « aucun modèle ».
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import exclusions
from forge_tests.adaptateurs import prompts

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent du poste")

SOURCE_AUTRE_SESSION = 'MODELE_COMPTEUR = "claude-opus-4"\nAUTRE = "gpt-4o"\n'
CHEMIN_NON_SUIVI = "outils/compteur-foundry/compteur.py"


def _git(racine: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(racine), *args], check=True, capture_output=True)


def _produit(tmp_path: Path, *, git: bool = True) -> Path:
    """Un produit dont tous les fichiers suivis sont sans modèle, avec un dossier d une autre
    session posé à côté : le même arbre, des fichiers que personne n a ajoutés à l index."""
    racine = tmp_path / "produit"
    (racine / "app").mkdir(parents=True)
    (racine / "app" / "__init__.py").write_text("", encoding="utf-8")
    (racine / "pyproject.toml").write_text(
        '[project]\nname = "p"\ndependencies = ["httpx"]\n', encoding="utf-8"
    )
    if git:
        subprocess.run(["git", "init", "-q", str(racine)], check=True)
        _git(racine, "add", "-A")
    chemin = racine / CHEMIN_NON_SUIVI
    chemin.parent.mkdir(parents=True)
    chemin.write_text(SOURCE_AUTRE_SESSION, encoding="utf-8")
    exclusions._CACHE_GIT.clear()
    exclusions._CACHE_SUIVIS.clear()
    return racine


def _alias(racine: Path) -> set[str]:
    return {f.id for f in prompts.analyser(racine).findings if f.id.startswith("modele:")}


# --- ROUGE ----------------------------------------------------------------------------------------
def test_rouge_un_fichier_non_suivi_ne_produit_aucun_constat_au_produit(tmp_path: Path) -> None:
    racine = _produit(tmp_path)
    sortie = prompts.analyser(racine)
    assert _alias(racine) == set()
    assert sortie.verdict != "FAIL"
    assert prompts.inventaire(racine) == []


# --- VERT -----------------------------------------------------------------------------------------
def test_vert_le_meme_fichier_suivi_est_toujours_juge(tmp_path: Path) -> None:
    racine = _produit(tmp_path)
    _git(racine, "add", CHEMIN_NON_SUIVI)
    exclusions._CACHE_SUIVIS.clear()
    assert _alias(racine) == {"modele:claude-opus-4", "modele:gpt-4o"}
    assert prompts.analyser(racine).verdict == "FAIL"


def test_vert_hors_depot_git_le_comportement_est_inchange(tmp_path: Path) -> None:
    racine = _produit(tmp_path, git=False)
    assert _alias(racine) == {"modele:claude-opus-4", "modele:gpt-4o"}


def test_un_fichier_suivi_et_un_non_suivi_ne_comptent_que_le_suivi(tmp_path: Path) -> None:
    racine = _produit(tmp_path)
    suivi = racine / "app" / "client.py"
    suivi.write_text('MODELE = "claude-sonnet-4-5-20250929"\n', encoding="utf-8")
    _git(racine, "add", "app/client.py")
    exclusions._CACHE_SUIVIS.clear()
    assert [e.id for e in prompts.inventaire(racine)] == ["modele:claude-sonnet-4-5-20250929"]
    # Le suivi est épinglé : aucun alias mouvant ; les deux alias non suivis ne sont pas comptés.
    assert prompts._findings_modeles(racine) == []


# --- HONNÊTETÉ ------------------------------------------------------------------------------------
def test_le_fichier_non_suivi_est_nomme_a_part_au_rapport(tmp_path: Path) -> None:
    racine = _produit(tmp_path)
    lignes = [m for m in prompts.analyser(racine).non_juge if CHEMIN_NON_SUIVI in m]
    assert len(lignes) == 1
    assert "non suivi" in lignes[0] and "1 fichier" in lignes[0]


def test_un_fichier_non_suivi_qui_nomme_un_modele_interdit_la_preuve_d_aucun_modele(
    tmp_path: Path,
) -> None:
    """Sans lui, le manifeste sans client ferait conclure « ce projet n appelle aucun modèle »,
    une preuve fausse : un fichier du même arbre en nomme deux."""
    racine = _produit(tmp_path)
    sortie = prompts.analyser(racine)
    assert sortie.verdict == "SKIP"  # et non « NA » (sans objet, prouvé)
    assert not [m for m in sortie.non_juge if "SANS OBJET" in m]


def test_la_liste_publiee_est_bornee_et_son_total_est_dit(tmp_path: Path) -> None:
    racine = _produit(tmp_path)
    for i in range(prompts._MAX_NON_SUIVIS_NOMMES + 5):
        (racine / "outils" / f"autre_{i:02d}.py").write_text(
            'M = "claude-opus-4"\n', encoding="utf-8"
        )
    exclusions._CACHE_SUIVIS.clear()
    ligne = next(m for m in prompts.analyser(racine).non_juge if "non suivi" in m)
    assert f"{prompts._MAX_NON_SUIVIS_NOMMES + 6} fichiers" in ligne
    assert "et 6 autres" in ligne  # 26 - 20 nommés


def test_depot_sans_aucun_fichier_suivi_garde_le_comportement_d_avant(tmp_path: Path) -> None:
    """Un dépôt neuf, rien encore ajouté à l index : aucun suivi auquel comparer, donc aucune
    exclusion. Sinon un produit tout juste initialisé sortirait de l audit tout entier."""
    racine = _produit(tmp_path, git=False)
    subprocess.run(["git", "init", "-q", str(racine)], check=True)
    exclusions._CACHE_SUIVIS.clear()
    assert not exclusions.non_suivi_par_git(racine / CHEMIN_NON_SUIVI, racine)
    assert _alias(racine) == {"modele:claude-opus-4", "modele:gpt-4o"}


# --- le module commun -----------------------------------------------------------------------------
def test_exclusions_non_suivi_par_git(tmp_path: Path) -> None:
    racine = _produit(tmp_path)
    assert exclusions.non_suivi_par_git(racine / CHEMIN_NON_SUIVI, racine)
    assert not exclusions.non_suivi_par_git(racine / "app" / "__init__.py", racine)
    sans_git = _produit(tmp_path / "ailleurs", git=False)
    assert not exclusions.non_suivi_par_git(sans_git / CHEMIN_NON_SUIVI, sans_git)


def test_racine_sous_dossier_d_un_depot_plus_large(tmp_path: Path) -> None:
    """La racine auditée est un sous-dossier du dépôt : seuls ses fichiers suivis comptent."""
    depot = tmp_path / "mono"
    produit = depot / "services" / "p"
    produit.mkdir(parents=True)
    (produit / "suivi.py").write_text('M = "claude-opus-4"\n', encoding="utf-8")
    (produit / "autre.py").write_text('M = "gpt-4o"\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(depot)], check=True)
    _git(depot, "add", "services/p/suivi.py")
    exclusions._CACHE_GIT.clear()
    exclusions._CACHE_SUIVIS.clear()
    assert not exclusions.non_suivi_par_git(produit / "suivi.py", produit)
    assert exclusions.non_suivi_par_git(produit / "autre.py", produit)
    assert {e.id for e in prompts.inventaire(produit)} == {"modele:claude-opus-4"}
