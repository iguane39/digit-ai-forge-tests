"""D-34 (decision humaine du 01/09/2026) — la mutation est une campagne A LA DEMANDE.

La regle, mot pour mot : « Tous les tests sont pleinement executes tout le temps, sauf les tests
sur les mutants qui sont executes a la demande, lors d un passage en Prod sur proposition de
l IA, et uniquement s ils n ont ete executes depuis plusieurs modifications de code. »

Trois conditions, trois familles de tests, et chacune porte son SENS ROUGE — ce qui casse si la
regle se defait. La troisieme condition (« depuis plusieurs modifications ») est celle qui a le
plus de facons de rater en silence : c est pourquoi l inconnu y est teste explicitement.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from forge_tests.adaptateurs import mutation


# --- Condition 1 : a la demande ---------------------------------------------------------------

def test_le_pan_mutation_ne_se_joue_pas_par_defaut(monkeypatch) -> None:
    """ROUGE : si la porte s ouvrait par defaut, chaque audit repaierait 54 minutes."""
    monkeypatch.delenv("FORGE_TESTS_MUTATION", raising=False)
    assert mutation._mutation_demandee() is False
    monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
    assert mutation._mutation_demandee() is True
    monkeypatch.setenv("FORGE_TESTS_MUTATION", "0")
    assert mutation._mutation_demandee() is False


def _projet(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "calcul.py").write_text(
        "def somme(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calcul.py").write_text(
        "from app.calcul import somme\n\n\ndef test_somme():\n    assert somme(1, 2) == 3\n",
        encoding="utf-8")
    return tmp_path


def test_non_demande_le_pan_rend_SKIP_et_publie_ses_modules(tmp_path: Path, monkeypatch) -> None:
    """Le pan non joue DIT ce qu il n a pas mesure, et ne fait pas disparaitre les modules.

    ROUGE : un pan qui se tait est indiscernable, au tableau de bord, d un pan dont le score est
    nul — c est exactement le silence que le principe A-2 existe pour interdire.
    """
    monkeypatch.delenv("FORGE_TESTS_MUTATION", raising=False)
    sortie = mutation.analyser(_projet(tmp_path))
    assert sortie.verdict == "SKIP"
    assert sortie.mutation and "a_la_demande" in sortie.mutation
    assert "score" not in sortie.mutation
    assert any("NON JOUE" in m for m in sortie.non_juge)
    assert sortie.modules, "les modules du projet doivent rester publies"


def test_la_proposition_est_ecrite_dans_le_rapport(tmp_path: Path, monkeypatch) -> None:
    """« Sur proposition de l IA » n a d executant que si le texte porte la proposition.

    ROUGE : sans cette phrase, la deuxieme condition de la decision serait decorative — le pan se
    tairait, et personne ne saurait qu une campagne est due avant la mise en production.
    """
    monkeypatch.delenv("FORGE_TESTS_MUTATION", raising=False)
    sortie = mutation.analyser(_projet(tmp_path))
    etat = sortie.mutation["a_la_demande"]
    assert etat["perimee"] is True
    assert "PROPOSITION" in etat["proposition"]
    assert "FORGE_TESTS_MUTATION=1" in etat["proposition"]


# --- Condition 3 : seulement si perimee ---------------------------------------------------------

def test_sans_campagne_anterieure_la_mutation_est_proposee(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    etat = mutation._etat_peremption(projet, projet, projet / "app")
    assert etat["perimee"] is True
    assert etat["derniere_campagne"] is None


def test_une_anciennete_non_mesurable_est_traitee_comme_perimee(tmp_path: Path) -> None:
    """ROUGE, et c est le plus important des six : si l inconnu passait pour « recent », un projet
    sans depot git ne verrait JAMAIS de campagne proposee, et la porte serait ouverte pour
    toujours sans que rien ne le dise."""
    projet = _projet(tmp_path)
    (projet / "forge").mkdir()
    mutation._marqueur_campagne(projet).write_text(
        json.dumps({"sha": "0" * 40, "score": 1.0}), encoding="utf-8")
    etat = mutation._etat_peremption(projet, projet, projet / "app")
    assert etat["modifications_depuis"] is None
    assert etat["perimee"] is True
    assert "NON MESURABLE" in etat["proposition"]


def test_une_campagne_recente_ne_se_repropose_pas(tmp_path: Path, monkeypatch) -> None:
    """Sous le seuil, la campagne ne se propose pas : c est la moitie « uniquement si » de la
    decision. ROUGE : sans elle, la porte proposerait a chaque passage et redeviendrait du bruit."""
    projet = _projet(tmp_path)
    monkeypatch.setattr(mutation, "_modifications_depuis", lambda *_a: 3)
    (projet / "forge").mkdir()
    mutation._marqueur_campagne(projet).write_text(
        json.dumps({"sha": "abc1234", "score": 1.0}), encoding="utf-8")
    etat = mutation._etat_peremption(projet, projet, projet / "app")
    assert etat["perimee"] is False
    assert "NON proposee" in etat["proposition"]


def test_au_dela_du_seuil_la_campagne_est_proposee(tmp_path: Path, monkeypatch) -> None:
    projet = _projet(tmp_path)
    monkeypatch.setattr(mutation, "_modifications_depuis", lambda *_a: 12)
    (projet / "forge").mkdir()
    mutation._marqueur_campagne(projet).write_text(
        json.dumps({"sha": "abc1234", "score": 1.0}), encoding="utf-8")
    etat = mutation._etat_peremption(projet, projet, projet / "app")
    assert etat["perimee"] is True
    assert etat["seuil_peremption"] == 10
    assert "12 modification" in etat["proposition"]


def test_le_seuil_est_parametrable_et_declare(tmp_path: Path, monkeypatch) -> None:
    """« Plusieurs » est un mot, le seuil est un chiffre : il se change, et il se lit au rapport."""
    projet = _projet(tmp_path)
    monkeypatch.setenv("FORGE_TESTS_MUTATION_PEREMPTION", "3")
    monkeypatch.setattr(mutation, "_modifications_depuis", lambda *_a: 4)
    (projet / "forge").mkdir()
    mutation._marqueur_campagne(projet).write_text(
        json.dumps({"sha": "abc1234"}), encoding="utf-8")
    etat = mutation._etat_peremption(projet, projet, projet / "app")
    assert etat["seuil_peremption"] == 3
    assert etat["perimee"] is True


def test_la_campagne_jouee_se_note_et_se_relit(tmp_path: Path) -> None:
    """Sans point de depart note, la troisieme condition n a rien a compter."""
    projet = _projet(tmp_path)
    resume = {"sha": "abc1234", "score": 0.8, "survivants": ["mutant:app/calcul.py:2:+->-"]}
    assert mutation._noter_campagne(projet, projet, resume) is None
    assert mutation._derniere_campagne(projet) == resume


def test_le_compte_des_modifications_ne_regarde_que_les_sources(tmp_path: Path) -> None:
    """Le perimetre du compte est celui de la mutation. ROUGE : compter tous les commits ferait
    proposer une campagne pour un changement de documentation, et la porte perdrait son sens."""
    projet = _projet(tmp_path)
    git = ["git", "-C", str(projet)]
    subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
    subprocess.run([*git, "config", "user.email", "banc@local"], check=True, capture_output=True)
    subprocess.run([*git, "config", "user.name", "banc"], check=True, capture_output=True)
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "socle"], check=True, capture_output=True)
    depart = mutation._sha_courant(projet)
    assert depart is not None

    (projet / "LISEZMOI.md").write_text("documentation\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "doc"], check=True, capture_output=True)
    assert mutation._modifications_depuis(projet, projet / "app", depart) == 0

    (projet / "app" / "calcul.py").write_text(
        "def somme(a, b):\n    return b + a\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "source"], check=True, capture_output=True)
    assert mutation._modifications_depuis(projet, projet / "app", depart) == 1
