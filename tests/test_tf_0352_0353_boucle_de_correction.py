"""TF-0352 / TF-0353 — la campagne a une définition de FIN, et la boucle a un journal.

Deux trous d'un même contrat, payés le même jour.

TF-0352 : rien ne disait qu'une campagne inclut la CORRECTION et le REJEU jusqu'à extinction.
Le verdict PARTIEL du 12/08 — 121 findings, 127 actions classées, produit inchangé — était donc
une fin de mandat CONFORME. La preuve par l'inverse (17/08) a fermé 4 anomalies produit et
3 faux verts, dont un dormant depuis cette campagne-là.

TF-0353 : le ledger porte les findings du dernier rapport, pas l'histoire des tours. « 0 parce
que tout est traité » et « 0 parce qu'on n'a pas rejoué » s'écrivent pareil. Le tour 3 du 17/08
n'a révélé qu'UNE anomalie — une course, la classe la plus coûteuse à retrouver plus tard : une
clôture au tour 2 l'aurait livrée.

Chaque règle est tenue dans les DEUX sens : la campagne fautive doit être refusée, la campagne
saine doit pouvoir clore. Un contrôle qui ne sait que refuser se contourne au premier délai.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import boucle

_TOUR_SAIN = {
    "tour": 4,
    "anomalies_entrantes": 1,
    "corrigees": 1,
    "nouvelles": 0,
    "restantes": 0,
    "dernier_correctif": "2026-08-17T16:00:00+02:00",
    "dernier_run_suite": "2026-08-17T16:20:00+02:00",
    "portes": {"suites": 0, "lint": 0, "typage": 0, "e2e": 0},
    "xfail_non_justifies": 0,
    "passages_verts_consecutifs": 3,
    "ecarts_assumes": [],
}


def _tour(**delta: object) -> dict:
    return {**_TOUR_SAIN, **delta}


# --- Le sens qui AUTORISE : sans lui, le contrôle serait juste un mur -------------------------
def test_une_campagne_qui_tient_les_cinq_points_est_TERMINEE() -> None:
    resultat = boucle.verdict([_tour(tour=1, nouvelles=4), _tour()])

    assert resultat["statut"] == boucle.TERMINEE, resultat["manques"]
    assert resultat["manques"] == []
    assert "TERMINÉE en 2 tour(s)" in resultat["libelle"]


# --- (a) les portes ----------------------------------------------------------------------------
def test_une_porte_ROUGE_interdit_la_cloture() -> None:
    resultat = boucle.verdict([_tour(portes={"suites": 0, "lint": 1, "typage": 0, "e2e": 0})])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("« lint » en exit 1" in m for m in resultat["manques"])


def test_une_porte_ABSENTE_n_est_pas_une_porte_verte() -> None:
    """Le silence est le mode de défaillance de ce contrat : une porte qu'on ne joue pas ne
    doit surtout pas se lire comme une porte tenue."""
    resultat = boucle.verdict([_tour(portes={"suites": 0, "lint": 0, "typage": 0})])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("« e2e » ABSENTE" in m for m in resultat["manques"])


# --- (b) les xfail non justifiés ------------------------------------------------------------
def test_un_xfail_sans_arbitrage_humain_date_interdit_la_cloture() -> None:
    resultat = boucle.verdict([_tour(xfail_non_justifies=2)])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("xfail/test.fail sans arbitrage humain daté" in m for m in resultat["manques"])


# --- (c) les passages verts consécutifs -------------------------------------------------------
def test_un_seul_passage_vert_ne_suffit_pas() -> None:
    """Mesuré : instabilité 1 run sur 2 sur la suite e2e du 17/08. Un passage unique ne
    distingue pas une suite stable d'une instabilité qui n'est pas tombée ce coup-ci."""
    resultat = boucle.verdict([_tour(passages_verts_consecutifs=1)])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("1 passage(s) vert(s)" in m for m in resultat["manques"])


# --- (d) l anomalie ni corrigée ni assumée -----------------------------------------------------
def test_une_anomalie_restante_sans_ecart_assume_interdit_la_cloture() -> None:
    resultat = boucle.verdict([_tour(restantes=2, ecarts_assumes=[])])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("2 anomalie(s) restante(s) pour 0 écart(s)" in m for m in resultat["manques"])


def test_un_ecart_assume_ANONYME_ne_solde_rien() -> None:
    """« porté en écart assumé et ÉCRIT » : qui, quand, pourquoi. Sinon c'est un renoncement
    sans auteur — la même raison qui fait qu'une adoption invérifiable ne solde rien (RT-13)."""
    resultat = boucle.verdict(
        [_tour(restantes=1, ecarts_assumes=[{"anomalie": "export ouvert", "motif": "plus tard"}])]
    )

    assert resultat["statut"] == boucle.EN_COURS
    assert any("assume_par, date" in m for m in resultat["manques"])


def test_un_ecart_assume_COMPLET_solde_son_anomalie() -> None:
    resultat = boucle.verdict(
        [
            _tour(
                restantes=1,
                ecarts_assumes=[
                    {
                        "anomalie": "relance manuelle absente",
                        "assume_par": "le commanditaire",
                        "date": "2026-08-17",
                        "motif": "hors périmètre de la version, replanifié en v2",
                    }
                ],
            )
        ]
    )

    assert resultat["statut"] == boucle.TERMINEE, resultat["manques"]


# --- (e) le rejeu APRÈS le dernier correctif — le cœur de TF-0353 -------------------------------
def test_clore_sur_un_tour_NON_REJOUE_apres_son_dernier_correctif_est_refuse() -> None:
    """Le cas exact : la suite a été jouée, PUIS on a corrigé, PUIS on a clos. Le journal dit
    « 0 anomalie » — mais ce zéro ne mesure rien d'autre que l'ordre des gestes."""
    resultat = boucle.verdict(
        [
            _tour(
                dernier_run_suite="2026-08-17T15:00:00+02:00",
                dernier_correctif="2026-08-17T15:40:00+02:00",
            )
        ]
    )

    assert resultat["statut"] == boucle.EN_COURS
    assert any("ANTÉRIEUR au dernier correctif" in m for m in resultat["manques"])


def test_un_tour_qui_a_corrige_sans_horodater_son_correctif_est_refuse() -> None:
    resultat = boucle.verdict([_tour(corrigees=3, dernier_correctif="")])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("`dernier_correctif` absent" in m for m in resultat["manques"])


def test_un_tour_sans_aucun_rejeu_trace_est_refuse() -> None:
    resultat = boucle.verdict([_tour(corrigees=0, dernier_correctif="", dernier_run_suite="")])

    assert resultat["statut"] == boucle.EN_COURS
    assert any("`dernier_run_suite` absent" in m for m in resultat["manques"])


# --- L absence de journal : le défaut fondateur, celui du 12/08 ---------------------------------
def test_une_campagne_SANS_journal_de_boucle_ne_peut_pas_clore() -> None:
    resultat = boucle.verdict([])

    assert resultat["statut"] == boucle.EN_COURS
    assert "aucun journal de boucle" in resultat["libelle"]
    assert boucle.FICHIER in resultat["manques"][0]


def test_un_journal_CORROMPU_ne_fait_pas_clore_plus_vite(tmp_path: Path) -> None:
    """Un contrôle qu'on désarme en cassant son entrée n'est pas un contrôle."""
    (tmp_path / "forge").mkdir()
    (tmp_path / boucle.FICHIER).write_text(
        json.dumps(_TOUR_SAIN) + "\nceci n est pas du JSON\n", encoding="utf-8"
    )

    resultat = boucle.verdict(boucle.lire(tmp_path))

    assert resultat["statut"] == boucle.EN_COURS
    assert any("JSON invalide" in m for m in resultat["manques"])


# --- La mesure publiée : convergence ------------------------------------------------------------
def test_la_boucle_du_17_08_est_REJOUEE_telle_quelle_et_publie_ses_69_pour_cent() -> None:
    """Le cas réel, tour par tour : 4 → 9 → 1 → 0. La mesure qui a fait exister cet item.

    69 % des anomalies (10 sur 14) n'existaient pas au tour 1 : elles sont nées des correctifs.
    C'est le chiffre qui interdit de s'arrêter après avoir corrigé une fois.
    """
    tours = [
        _tour(tour=1, anomalies_entrantes=4, corrigees=4, nouvelles=4, restantes=0),
        _tour(tour=2, anomalies_entrantes=9, corrigees=9, nouvelles=9, restantes=0),
        _tour(tour=3, anomalies_entrantes=1, corrigees=1, nouvelles=1, restantes=0),
        _tour(tour=4),
    ]

    mesure = boucle.convergence(tours)
    total = sum(mesure["revelees_par_tour"])

    assert mesure["revelees_par_tour"] == [4, 9, 1, 0]
    assert mesure["nees_des_correctifs"] == 10
    assert round(100 * mesure["nees_des_correctifs"] / total) == 71  # 10/14, arrondi
    assert mesure["converge"]


def test_une_campagne_qui_ne_CONVERGE_pas_est_signalee_sans_bloquer_la_cloture() -> None:
    """Le compteur dit aussi quand s'arrêter pour de bonnes raisons. Mais il SIGNALE — il ne
    s'arroge pas le droit de refuser une campagne qui tient par ailleurs ses cinq points."""
    tours = [_tour(tour=1, nouvelles=3), _tour(tour=2, nouvelles=5)]

    resultat = boucle.verdict(tours)

    assert resultat["statut"] == boucle.TERMINEE
    assert not resultat["convergence"]["converge"]
    assert "NON CONVERGENTE" in resultat["libelle"]


# --- Le câblage : une règle sans appelant n'existe pas (loi 1) ----------------------------------
def test_le_rapport_d_audit_PORTE_le_verdict_de_boucle(tmp_path: Path) -> None:
    from forge_tests.noyau import rapport

    rap = rapport([], ["front"], boucle=boucle.verdict([_tour()]))

    assert rap["boucle"]["statut"] == boucle.TERMINEE


def test_un_rapport_sans_journal_DIT_qu_il_n_en_a_pas_au_lieu_de_se_taire() -> None:
    """Section toujours présente : « pas mesuré » et « mesuré, rien à signaler » ne doivent
    jamais s'écrire pareil — c'est la règle déjà tenue par `essais` (TF-0146)."""
    from forge_tests.noyau import rapport

    rap = rapport([], ["front"])

    assert rap["boucle"]["statut"] == boucle.EN_COURS
    assert "aucun journal de boucle" in rap["boucle"]["libelle"]
