"""TF-0465 + TF-0467 — la PRÉSENCE d'une chaîne étrangère est le constat, et `lang` tranche.

Deux faits mesurés sur digit-ai.fr le 22/08/2026 :

  · « Réponse courte » s'affiche EN FRANÇAIS sur 36 pages anglaises — 2 mots sur ~1 200, soit
    0,17 % contre un seuil de densité à 8 %. Le contrôle ne pouvait pas le voir, et ce n'était
    pas un réglage de seuil : baisser le seuil à 0,2 % accuserait au hasard toutes les pages.
    La méthode était en cause, pas son paramètre (TF-0465) ;
  · les 201 pages anglaises portent `aria-label="Voir cette page en français"` sans `lang="fr"`.
    La formulation française est la BONNE convention pour une bascule de langue ; c'est
    l'absence de marquage qui est le défaut, et un lecteur d'écran prononce ces mots avec la
    phonétique anglaise (WCAG 2.2, critère 3.1.2 — TF-0467).

Un seul balayage, deux constats : `non_traduite` (rien ne signale l'étranger) et `signalee`
(un ancêtre porte `lang` — conforme). C'est ce que l'item demandait : le contrôle du second
vient gratuitement avec le premier.
"""
from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs.i18n import chaines_de_reference, constats_chaines

CHAINES = ["Réponse courte", "Voir cette page en français"]


def _page(tmp_path: Path, corps: str, nom: str = "en.html") -> Path:
    chemin = tmp_path / nom
    chemin.write_text(
        f'<html lang="en"><head><title>Page</title></head><body>{corps}</body></html>',
        encoding="utf-8",
    )
    return chemin


def test_une_chaine_etrangere_non_signalee_est_un_constat(tmp_path: Path) -> None:
    """Le cas mesuré : 2 mots français noyés dans 1 200 mots anglais."""
    corps = "<h2>Réponse courte</h2><p>" + ("English content. " * 200) + "</p>"
    constats = constats_chaines(_page(tmp_path, corps), CHAINES)
    assert ("non_traduite", "Réponse courte") in constats, (
        f"la chaîne française passe inaperçue — c'est le défaut que la densité ne voit pas : {constats}"
    )


def test_la_frequence_n_est_pas_le_critere(tmp_path: Path) -> None:
    """UNE occurrence suffit : la présence est le constat, jamais la densité."""
    corps = "<p>Réponse courte</p>" + "<p>English.</p>" * 500
    assert constats_chaines(_page(tmp_path, corps), CHAINES)


def test_un_fragment_marque_lang_est_conforme(tmp_path: Path) -> None:
    """La bascule de langue en français EST la bonne convention — marquée, elle ne fait pas défaut."""
    corps = '<a href="/" lang="fr">Voir cette page en français</a>'
    constats = constats_chaines(_page(tmp_path, corps), CHAINES)
    assert ("signalee", "Voir cette page en français") in constats
    assert not [c for c, _ in constats if c == "non_traduite"], (
        f"un fragment correctement marqué est accusé à tort : {constats}"
    )


def test_le_meme_libelle_sans_lang_est_un_defaut(tmp_path: Path) -> None:
    """Les deux sens sur la MÊME chaîne : seul le marquage les sépare."""
    corps = '<a href="/">Voir cette page en français</a>'
    constats = constats_chaines(_page(tmp_path, corps), CHAINES)
    assert ("non_traduite", "Voir cette page en français") in constats


def test_page_sans_chaine_du_lexique_ne_produit_rien(tmp_path: Path) -> None:
    """Non-régression : une page anglaise propre reste muette."""
    assert constats_chaines(_page(tmp_path, "<p>Fully translated content.</p>"), CHAINES) == []


def test_lexique_non_declare_ne_juge_rien(tmp_path: Path) -> None:
    """Rien de déclaré, rien de jugé : le pan ne devine pas le vocabulaire d'un produit."""
    assert constats_chaines(_page(tmp_path, "<p>Réponse courte</p>"), []) == []


def test_declaration_illisible_est_ignoree(tmp_path: Path, monkeypatch) -> None:
    """Une déclaration cassée ne fait pas échouer l'audit — elle ne juge simplement rien."""
    mauvais = tmp_path / "chaines.json"
    mauvais.write_text("{ceci n est pas du json", encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_CHAINES", str(mauvais))
    assert chaines_de_reference() == {}


def test_declaration_lisible_est_lue(tmp_path: Path, monkeypatch) -> None:
    bon = tmp_path / "chaines.json"
    bon.write_text('{"fr": ["Réponse courte"]}', encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_CHAINES", str(bon))
    assert chaines_de_reference() == {"fr": ["Réponse courte"]}
