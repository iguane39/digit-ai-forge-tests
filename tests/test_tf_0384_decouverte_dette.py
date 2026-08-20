"""TF-0384 — le collecteur de dette lisait une LISTE DE MODULES ÉCRITE À LA MAIN.

Constaté le 19/08 en livrant TF-0383 : les 8 limites de `catalogue_i18n` n'entraient au
registre d'AUCUN domaine, et rien ne le signalait — alors que le commentaire du collecteur
disait « une dette qui n'entre pas au registre est de la prose »… en étant lui-même une liste.

La découverte du 20/08 a montré l'ampleur : NEUF modules portaient des limites qu'aucun domaine
ne collectait (surface_servie, confrontation, domaine, revue, flaky, impact,
generateur_proprietes, anomalies, catalogue_i18n) — soit ~24 énoncés hors registre.
Septième occurrence du patron « un contrôle qui itère sur une liste ne voit jamais ce qui n'y
est pas ».
"""

from __future__ import annotations

from forge_tests.dette import collecter


def test_un_module_jamais_liste_a_la_main_est_DECOUVERT() -> None:
    """Le cas fondateur : catalogue_i18n (TF-0383) et ses huit voisins du même angle mort."""
    domaines = {domaine for domaine, _ in ((e["domaine"], e["enonce"]) for e in collecter())}

    for attendu in ("catalogue-i18n", "surface-servie", "confrontation", "domaine", "revue"):
        assert attendu in domaines, f"module au NON_JUGE declare, absent du registre : {attendu}"


def test_les_domaines_HISTORIQUES_gardent_leur_nom() -> None:
    """La liste à la main ne sert plus qu'à NOMMER — la casser renommerait les domaines et
    romprait le rapprochement du registre (un énoncé retrouvé sous un autre domaine serait une
    entrée neuve, et l'ancienne sortirait « retirée » à tort)."""
    domaines = {e["domaine"] for e in collecter()}

    for historique in ("jeux-de-donnees", "generateur-data", "actions", "cahiers"):
        assert historique in domaines


def test_aucun_enonce_n_est_collecte_DEUX_fois() -> None:
    """La découverte recouvre les modules déjà importés à la main : la déduplication doit
    absorber le recouvrement, sinon chaque énoncé pèserait double au reste-à-faire."""
    entrees = collecter()

    cles = [(e["domaine"], e["enonce"]) for e in entrees]
    assert len(cles) == len(set(cles))
