"""TF-0744 — une valeur « s par mutant » qui ne se réconcilie pas avec la durée est un défaut.

LE FAIT, mesuré le 01/09/2026 en instruisant TF-0727. Un rapport de campagne publiait quatre
valeurs : 115 mutants, ~54 min de mutation, 67 min de campagne, et **~37 s par mutant**. Les
trois premières sont cohérentes entre elles (54 min / 115 = 28,2 s). LA QUATRIÈME NE L'EST PAS :
115 × 37 s = 71 min, soit PLUS que la campagne entière. La valeur n'avait pas été calculée depuis
la mesure, elle avait été estimée — et la demande d'étude qui bâtissait son argument de levier
dessus surévaluait tout gain calculé d'environ 31 %.

CE QUE CES TESTS TIENNENT, et c'est la fixture à double sens :

  * ROUGE — un bloc de coût synthétique aux chiffres du défaut fondateur (115 mutants, 54 min,
    37 s saisis) est REFUSÉ par `anomalies_cout`, avec le produit impossible nommé ;
  * VERT — le même bloc dérivé de la mesure (28,2 s) est ACCEPTÉ.

Et la règle qui rend le défaut irreproductible : `decomposer_cout` ne prend jamais la valeur en
entrée, elle la DÉRIVE de `durée_pan / mutants`. L'invariant `valeur × mutants ≤ durée` tient
alors par construction, sur n'importe quel jeu de mesures.

LA DÉCOMPOSITION, enfin, est la seule lecture actionnable du pan : `-x` fait qu'un mutant TUÉ
s'arrête au premier échec quand un SURVIVANT parcourt la suite entière. Les deux classes n'ont
pas le même coût, et la moyenne globale ne décrit aucun mutant réel.
"""

from __future__ import annotations

from forge_tests.adaptateurs.mutation import anomalies_cout, decomposer_cout

#: Les chiffres du rapport fondateur, à la seconde près.
_MUTANTS = 115
_MUTATION_S = 54 * 60
_CAMPAGNE_S = 67 * 60
_PUBLIE_FAUX_S = 37.0


def _campagne_fondatrice() -> list[tuple[bool, float]]:
    """23 survivants à ~52 s, 92 tués à ~22 s — la décomposition mesurée du 01/09."""
    return [(True, 52.0)] * 23 + [(False, 22.0)] * 92


def test_rouge_la_valeur_publiee_du_rapport_fondateur_est_refusee() -> None:
    """115 × 37 s = 71 min pour 54 min de mutation : arithmétiquement impossible, donc refusé."""
    cout = {
        "mesure": True,
        "duree_pan_s": float(_MUTATION_S),
        "mutants_joues": _MUTANTS,
        "s_par_mutant": _PUBLIE_FAUX_S,  # SAISIE, pas dérivée — le défaut lui-même
        "decomposition": {
            "tues": {"mutants": 92, "duree_s": 2024.0, "moyenne_s": 22.0, "part_du_pan": 0.6286},
            "survivants": {"mutants": 23, "duree_s": 1196.0, "moyenne_s": 52.0,
                           "part_du_pan": 0.3714},
        },
    }
    anomalies = anomalies_cout(cout)
    assert anomalies, "la valeur impossible du rapport fondateur doit être refusée"
    assert "PLUS que" in anomalies[0]
    # Le refus NOMME le produit impossible : sans lui, le lecteur ne sait pas quoi recalculer.
    assert str(_MUTANTS) in anomalies[0] and str(_PUBLIE_FAUX_S) in anomalies[0]
    # Et il est bien SUPÉRIEUR à la campagne entière — le fait qui a fondé l'item.
    assert _PUBLIE_FAUX_S * _MUTANTS > _CAMPAGNE_S


def test_vert_la_valeur_derivee_de_la_mesure_est_acceptee() -> None:
    """54 min / 115 = 28,2 s : la valeur que la mesure rend, et qui se réconcilie."""
    cout = decomposer_cout(_campagne_fondatrice(), float(_MUTATION_S))
    assert cout["mesure"] is True
    assert cout["mutants_joues"] == _MUTANTS
    assert cout["s_par_mutant"] == 28.2
    assert anomalies_cout(cout) == []


def test_l_invariant_valeur_x_mutants_inferieur_a_la_duree_tient_par_construction() -> None:
    """La valeur n'est jamais saisie : elle est dérivée, donc l'invariant ne peut plus rompre."""
    for duree in (1.0, 60.0, 3240.0, 4021.7):
        for mesures in ([(True, 1.0)], _campagne_fondatrice(), [(False, 0.1)] * 7):
            cout = decomposer_cout(mesures, duree)
            produit = cout["s_par_mutant"] * cout["mutants_joues"]
            assert produit <= duree + 0.05 * cout["mutants_joues"], (duree, produit)
            assert anomalies_cout(cout) == []


def test_la_decomposition_publie_la_moyenne_par_classe_et_sa_part() -> None:
    """Le coût se concentre sur les SURVIVANTS — c'est ce que le rapport ne disait nulle part."""
    cout = decomposer_cout(_campagne_fondatrice(), float(_MUTATION_S))
    tues = cout["decomposition"]["tues"]
    survivants = cout["decomposition"]["survivants"]

    assert tues["mutants"] == 92 and survivants["mutants"] == 23
    assert tues["moyenne_s"] == 22.0 and survivants["moyenne_s"] == 52.0
    # 23 survivants pèsent 37 % du temps de mutation pour 20 % des mutants : c'est le fait qui
    # change l'ordre des leviers d'optimisation.
    assert survivants["part_du_pan"] == 0.3714
    assert tues["part_du_pan"] + survivants["part_du_pan"] == 1.0
    assert survivants["part_du_pan"] > survivants["mutants"] / cout["mutants_joues"]
    # Le mécanisme est ÉCRIT au rapport : sans lui, la dispersion paraît inexpliquée.
    assert "-x" in cout["mecanisme"]


def test_rouge_une_decomposition_qui_ne_rend_pas_le_compte_est_refusee() -> None:
    """Une part qui ne somme pas à 100 %, ou des classes qui ne totalisent pas les mutants."""
    cout = decomposer_cout(_campagne_fondatrice(), float(_MUTATION_S))
    cout["decomposition"]["tues"]["mutants"] = 90  # deux mutants évaporés
    cout["decomposition"]["survivants"]["part_du_pan"] = 0.9  # parts qui somment à 1,53
    anomalies = anomalies_cout(cout)
    assert len(anomalies) == 2
    assert any("decomposition porte" in a for a in anomalies)
    assert any("somment a" in a for a in anomalies)


def test_aucun_mutant_joue_ne_publie_pas_de_cout_invente() -> None:
    """Zéro mutant n'a pas de moyenne. Le motif se DIT, il ne se remplace pas par un zéro."""
    cout = decomposer_cout([], 12.0)
    assert cout["mesure"] is False
    assert "aucun mutant joue" in cout["motif_non_mesure"]
    assert anomalies_cout(cout) == []
