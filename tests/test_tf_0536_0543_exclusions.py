"""Périmètre d'audit : `input\\` n'est pas du produit, et une seule liste en décide.

Fait fondateur (lot AuxPortesDeLaBaie 20260823a/b, TF-0536 / TF-0542 / TF-0543) : sur un audit
réel, 12 des 15 constats portaient sur `input\\` — un site concurrent aspiré depuis un navigateur
et une ancienne version du site gardée pour comparaison. Le pan `interface` sortait FAIL sur un
ratio de 0,9998 : les trois affordances non exercées étaient les boutons de carrousel du
concurrent. Le produit réel ne portait aucun constat.

Fait aggravant mesuré à la correction : le dépôt portait DIX listes d'exclusion divergentes
(7 à 31 entrées) et `input` ne figurait dans AUCUNE. C'était la troisième occurrence de la
famille : deux retours antérieurs avaient déjà ajouté `output` puis `forge` — à deux listes
seulement, jamais aux autres.

Ce que ces cas verrouillent, et c'est le point : que le socle soit UNIQUE, que l'inclusion soit
le geste explicite (jamais l'exclusion), et que les divergences LÉGITIMES d'un pan survivent —
écraser les dix listes ferait taire des pans qui ont raison de se taire.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests import exclusions


def test_input_est_hors_perimetre_par_defaut():
    """Le fait fondateur : sans rien déclarer, `input\\` est dehors."""
    assert exclusions.dossier_exclu("input")
    assert exclusions.chemin_exclu(Path("input") / "lamaisondutraict.com" / "accueil.htm")


def test_le_produit_reel_reste_dans_le_perimetre():
    """Borne : la correction ne doit pas vider l'audit de sa cible."""
    assert not exclusions.dossier_exclu("site")
    assert not exclusions.chemin_exclu(Path("site") / "index.html")
    assert not exclusions.chemin_exclu(Path("src") / "app" / "main.py")


@pytest.mark.parametrize("dossier", ["input", "output", "docs", "Old", "old", "forge", "runs"])
def test_le_socle_couvre_tout_ce_qui_n_est_pas_le_produit(dossier):
    """Ces sept-là étaient répartis au hasard sur dix listes ; ils viennent maintenant d'une seule."""
    assert exclusions.dossier_exclu(dossier)


@pytest.mark.parametrize("nom", ["accueil_files", "page.telechargement", "archive.download"])
def test_artefacts_de_sauvegarde_navigateur(nom):
    """Un `<page>_files\\` est écrit par le navigateur : le juger, c'est auditer Chrome."""
    assert exclusions.dossier_exclu(nom)


def test_page_aspiree_reconnue_a_son_marqueur(tmp_path):
    """Le marqueur `saved from url` dit sans configuration que le fichier vient d'ailleurs."""
    aspiree = tmp_path / "concurrent.htm"
    aspiree.write_bytes(b"<!-- saved from url=(0035)https://www.lamaisondutraict.com/ -->\n<html>")
    propre = tmp_path / "produit.html"
    propre.write_bytes(b"<!doctype html><html lang=fr><body>produit</body></html>")
    assert exclusions.est_page_aspiree(aspiree)
    assert not exclusions.est_page_aspiree(propre)


def test_fichier_illisible_ne_sort_pas_du_perimetre_en_silence(tmp_path):
    """Borne : un doute ne doit JAMAIS retirer un fichier du périmètre — il l'y laisse."""
    assert not exclusions.est_page_aspiree(tmp_path / "inexistant.html")


def test_inclusion_explicite_du_projet_prime(monkeypatch):
    """Inversion de charge : l'INCLUSION est le geste déclaré, jamais l'exclusion.

    Un projet qui a une vraie raison d'auditer son `input\\` l'écrit — et cette écriture est la
    trace de sa décision, ce que l'absence de configuration ne pouvait pas être.
    """
    monkeypatch.setenv("FORGE_TESTS_INCLURE", "input")
    assert not exclusions.dossier_exclu("input")
    assert exclusions.dossier_exclu("output"), "déclarer `input` ne doit pas rouvrir tout le reste"


def test_les_deux_listes_nommees_par_le_retour_portent_input():
    """RT-1 et RT-2 du lot 20260823a nommaient ces deux ensembles : ils étaient tous deux muets."""
    from forge_tests.adaptateurs import interface, securite

    assert "input" in interface._EXCLUS
    assert "input" in securite._EXCLUS_DEPENDANCES


def test_les_divergences_legitimes_survivent():
    """Ce que la fusion NE doit PAS faire : écraser une exclusion propre à un pan.

    `mutation` exclut `tests` parce qu'un test n'est pas une cible de mutation, `data` exclut
    `migrations` parce qu'une migration n'est pas un modèle. Les perdre ferait juger à tort.
    """
    from forge_tests.adaptateurs import data, mutation

    assert "tests" in mutation._DOSSIERS_EXCLUS
    assert "migrations" in data._EXCLUS_MODELES


def test_pans_qui_doivent_voir_les_livrables(monkeypatch):
    """Borne : un pan qui juge des pages livrées peut demander le socle SANS le hors-produit."""
    monkeypatch.delenv("FORGE_TESTS_INCLURE", raising=False)
    large = exclusions.socle(avec_hors_produit=False)
    assert "output" not in large and "docs" not in large
    assert "node_modules" in large, "l'outillage reste exclu dans tous les cas"
