"""D-36 (a) — la condition de non-perte du ciblage est JOUABLE, pas seulement promise.

La decision humaine du 01/09 laisse le ciblage par ligne mutee eteint et demande de le VERIFIER
a la prochaine campagne reelle. « On verifiera » n est pas un mecanisme : ces tests eprouvent le
comparateur qui rend cette verification jouable, dans chacun des etats qu il peut atteindre.

Le comparateur est une fonction PURE — c est delibere : la partie qui joue deux campagnes exige
un projet reel avec son environnement, la partie qui JUGE n en exige aucun, et c est celle dont
un defaut passerait inapercu.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "recette"))

import non_perte_ciblage as recette  # noqa: E402

# L etat que publie une campagne ciblee qui a REELLEMENT cible : le drapeau arme, la carte de
# couverture obtenue, et au moins un mutant rejoue sur une selection. Les trois sont exiges.
_CIBLAGE_EFFECTIF = {"actif": True, "carte_obtenue": True, "mutants_cibles": 9}


def _campagne(survivants: list[str], viables: int = 12, ciblage: dict | None = None) -> dict:
    return {"verdict_pan": "PASS", "mutants_viables": viables,
            "survivants": sorted(survivants), "score": 0.5, "echantillon": None,
            "ciblage": dict(_CIBLAGE_EFFECTIF if ciblage is None else ciblage)}


def test_meme_liste_des_deux_cotes_la_condition_est_tenue() -> None:
    """VERT du piege n° 4 : les listes coincident ET la campagne ciblee prouve qu elle a cible."""
    liste = ["mutant:app/a.py:3:+->-", "mutant:app/b.py:7:>->>="]
    verdict = recette.comparer(_campagne(liste), _campagne(liste))
    assert verdict["verdict"] == "PASS"
    assert "identique" in verdict["motif"]
    assert "9 rejoue(s) sur une selection ciblee" in verdict["motif"]


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


def test_sans_objet_nomme_le_prealable_manquant_si_le_pan_l_a_signale() -> None:
    """TF-0749 : un SANS_OBJET qui se contente de « rien a comparer » renvoie le lecteur fouiller
    l adaptateur pour savoir pourquoi. Quand le pan mutation a deja signale un PRÉALABLE
    D ENVIRONNEMENT ABSENT (TF-0299 — demon de conteneurs injoignable, par exemple), ce motif se
    reprend au premier niveau du rapport plutot que de se perdre dans le detail des deux cotes."""
    vide = _campagne([], viables=0)
    vide["non_juge"] = [
        "mutation : bruit methodologique sans rapport avec la disponibilite",
        "back : PRÉALABLE D ENVIRONNEMENT ABSENT — demon de conteneurs INJOIGNABLE.",
    ]
    verdict = recette.comparer(vide, vide)
    assert verdict["verdict"] == "SANS_OBJET"
    assert verdict["prealable_manquant"] == [
        "back : PRÉALABLE D ENVIRONNEMENT ABSENT — demon de conteneurs INJOIGNABLE."
    ]


def test_sans_objet_sans_prealable_signale_le_dit_explicitement() -> None:
    """ROUGE symetrique du test precedent : si aucun des deux cotes ne porte le marqueur
    PRÉALABLE D ENVIRONNEMENT ABSENT (ex. suite verte mais echantillonnage retombe sur zero
    mutant viable), le rapport ne doit ni inventer une cause ni rester muet — il le dit."""
    vide = _campagne([], viables=0)
    verdict = recette.comparer(vide, vide)
    assert verdict["verdict"] == "SANS_OBJET"
    assert len(verdict["prealable_manquant"]) == 1
    assert "aucun PRÉALABLE D ENVIRONNEMENT ABSENT signale" in verdict["prealable_manquant"][0]


# --- PIEGE N° 4 : LE DRAPEAU DEMANDE LE CIBLAGE, IL NE PROUVE PAS QU IL AIT EU LIEU -----------
#
# Ces cas-la sont les plus dangereux du lot, et ce sont les seuls ou les DEUX campagnes sont
# pleines. Quand la carte de couverture par test n aboutit pas — coverage absent du venv du
# projet, suite rouge, delai depasse —, l adaptateur repart en suite entiere pour chaque mutant
# SANS BRUIT : les deux passes jouent la meme strategie, la liste de survivants coincide par
# construction, et le comparateur declarait « condition tenue » en n ayant compare qu une
# campagne avec elle-meme. Le cas n a rien de theorique — `coverage` est absent du venv de la
# forge, et c est deja la cause enregistree en TF-0748.


def test_carte_de_couverture_NON_obtenue_interdit_le_PASS() -> None:
    """ROUGE : listes identiques, mais le ciblage est retombe en suite entiere. SANS_OBJET."""
    liste = ["mutant:app/a.py:3:+->-"]
    retombee = {"actif": True, "carte_obtenue": False, "mutants_cibles": 0}
    verdict = recette.comparer(_campagne(liste), _campagne(liste, ciblage=retombee))
    assert verdict["verdict"] == "SANS_OBJET"
    assert "n a rien cible" in verdict["motif"]
    assert "PRÉALABLE D ENVIRONNEMENT ABSENT" in verdict["prealable_manquant"][0]
    assert "coverage absent" in verdict["prealable_manquant"][0]


def test_carte_obtenue_mais_AUCUN_mutant_cible_interdit_le_PASS() -> None:
    """ROUGE : la carte existe, mais aucune ligne mutee n a de test nomme — rien n a ete cible."""
    liste = ["mutant:app/a.py:3:+->-"]
    sterile = {"actif": True, "carte_obtenue": True, "mutants_cibles": 0}
    verdict = recette.comparer(_campagne(liste), _campagne(liste, ciblage=sterile))
    assert verdict["verdict"] == "SANS_OBJET"
    assert "AUCUN mutant reellement cible" in verdict["prealable_manquant"][0]


def test_etat_de_ciblage_ABSENT_du_rapport_interdit_le_PASS() -> None:
    """ROUGE : la preuve exigee est POSITIVE. Un rapport muet sur le ciblage ne vaut pas preuve
    que le ciblage a eu lieu — c est exactement le sens ou l erreur rassure."""
    liste = ["mutant:app/a.py:3:+->-"]
    verdict = recette.comparer(_campagne(liste), _campagne(liste, ciblage={}))
    assert verdict["verdict"] == "SANS_OBJET"
    assert "aucun etat de ciblage" in verdict["prealable_manquant"][0]


def test_drapeau_eteint_du_cote_ciblee_interdit_le_PASS() -> None:
    """ROUGE : les deux passes ont joue la campagne pleine, la comparaison porte sur elle-meme."""
    liste = ["mutant:app/a.py:3:+->-"]
    eteint = {"actif": False, "carte_obtenue": False, "mutants_cibles": 0}
    verdict = recette.comparer(_campagne(liste), _campagne(liste, ciblage=eteint))
    assert verdict["verdict"] == "SANS_OBJET"
    assert "n etait pas arme" in verdict["prealable_manquant"][0]


def test_une_DIVERGENCE_reste_un_FAIL_meme_sans_ciblage_effectif() -> None:
    """VERT du garde-fou lui-meme, dans l autre sens : le controle du piege n° 4 ne doit couvrir
    que le chemin du PASS. Deux passes de la MEME strategie qui ne rendent pas la meme liste
    denoncent une instabilite du banc — la masquer en SANS_OBJET perdrait un vrai defaut."""
    retombee = {"actif": True, "carte_obtenue": False, "mutants_cibles": 0}
    pleine = _campagne(["mutant:app/a.py:3:+->-", "mutant:app/b.py:7:>->>="])
    ciblee = _campagne(["mutant:app/a.py:3:+->-"], ciblage=retombee)
    verdict = recette.comparer(pleine, ciblee)
    assert verdict["verdict"] == "FAIL"
    assert verdict["survivants_PERDUS"] == ["mutant:app/b.py:7:>->>="]
