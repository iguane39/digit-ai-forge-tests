"""D-36 (a) — la condition de non-perte du ciblage est JOUABLE, pas seulement promise.

La decision humaine du 01/09 laisse le ciblage par ligne mutee eteint et demande de le VERIFIER
a la prochaine campagne reelle. « On verifiera » n est pas un mecanisme : ces tests eprouvent le
comparateur qui rend cette verification jouable, dans les quatre etats qu il peut atteindre.

Le comparateur est une fonction PURE — c est delibere : la partie qui joue deux campagnes exige
un projet reel avec son environnement, la partie qui JUGE n en exige aucun, et c est celle dont
un defaut passerait inapercu.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "recette"))

import non_perte_ciblage as recette  # noqa: E402


def _campagne(survivants: list[str], viables: int = 12) -> dict:
    return {"verdict_pan": "PASS", "mutants_viables": viables,
            "survivants": sorted(survivants), "score": 0.5, "echantillon": None}


def test_meme_liste_des_deux_cotes_la_condition_est_tenue() -> None:
    liste = ["mutant:app/a.py:3:+->-", "mutant:app/b.py:7:>->>="]
    verdict = recette.comparer(_campagne(liste), _campagne(liste))
    assert verdict["verdict"] == "PASS"
    assert "identique" in verdict["motif"]


def test_un_survivant_PERDU_est_un_faux_vert_et_le_verdict_le_dit() -> None:
    """ROUGE : c est le seul defaut qu un banc de tests ne doit jamais produire. Un mutant declare
    tue par une selection qui n a jamais joue le test qui l aurait tue rend un vert imprevu, et
    un vert imprevu ne se signale pas tout seul — il faut que ce comparateur le nomme."""
    pleine = _campagne(["mutant:app/a.py:3:+->-", "mutant:app/b.py:7:>->>="])
    ciblee = _campagne(["mutant:app/a.py:3:+->-"])
    verdict = recette.comparer(pleine, ciblee)
    assert verdict["verdict"] == "FAIL"
    assert verdict["survivants_PERDUS"] == ["mutant:app/b.py:7:>->>="]
    assert verdict["survivants_AJOUTES"] == []
    assert "FAUX VERT" in verdict["gravite"]


def test_un_survivant_AJOUTE_echoue_aussi_mais_ne_se_confond_pas_avec_une_perte() -> None:
    """Les deux sens sont des echecs et ne coutent pas la meme chose : l un fait perdre du temps,
    l autre fait passer un defaut. Les melanger ferait traiter le moins grave en priorite."""
    pleine = _campagne(["mutant:app/a.py:3:+->-"])
    ciblee = _campagne(["mutant:app/a.py:3:+->-", "mutant:app/c.py:9:==->!="])
    verdict = recette.comparer(pleine, ciblee)
    assert verdict["verdict"] == "FAIL"
    assert verdict["survivants_PERDUS"] == []
    assert verdict["survivants_AJOUTES"] == ["mutant:app/c.py:9:==->!="]
    assert "FAUX VERT" not in verdict["gravite"]


def test_deux_campagnes_VIDES_ne_prouvent_rien(tmp_path: Path) -> None:
    """ROUGE, et c est le piege le plus facile a rater : deux listes vides sont identiques. Sans
    cette branche, un projet sans environnement — donc sans un seul mutant joue — rendrait PASS
    et la condition de non-perte serait declaree tenue sans avoir jamais ete eprouvee."""
    verdict = recette.comparer(_campagne([], viables=0), _campagne([], viables=0))
    assert verdict["verdict"] == "SANS_OBJET"
    assert "rien a comparer" in verdict["motif"]


def test_une_campagne_vide_face_a_une_campagne_pleine_reste_un_echec() -> None:
    """Le SANS_OBJET ne couvre QUE le cas ou les deux cotes sont vides. Si la ciblee ne mute rien
    la ou la pleine trouve des survivants, c est la perte maximale, pas une absence de mesure."""
    verdict = recette.comparer(_campagne(["mutant:app/a.py:3:+->-"]), _campagne([], viables=0))
    assert verdict["verdict"] == "FAIL"
    assert verdict["survivants_PERDUS"] == ["mutant:app/a.py:3:+->-"]
