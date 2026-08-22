"""TF-0466 — la langue se mesure aussi sur les MÉTADONNÉES, pas seulement sur les mots visibles.

Fait qui l'a ouverte (digit-ai.fr, 22/08/2026) : sur les 131 articles du blog anglais, 78
portent au moins un `article:tag` en français — 67 tags distincts, repris dans les `keywords`
du JSON-LD. Le pan mesurait la langue sur le texte visible : les métadonnées étaient hors de
son champ, et même affichées ces valeurs seraient restées sous le seuil de densité (5 mots sur
1 200). C'est exactement ce que consomment les moteurs et les aperçus sociaux.

Deux constats DISTINCTS, et c'est le point : `non_traduit` (identique à la référence, aucune
heuristique) et `mal_traduit` (différent mais portant des mots-outils de la langue de
référence). Le lecteur n'en fait pas la même chose.
"""
from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs.i18n import _Page, constats_metadonnees

_FR = """<html lang="fr"><head>
<title>Automatisation des devis</title>
<meta name="description" content="Comment automatiser vos devis">
<meta property="article:tag" content="Souverainete">
<meta property="og:title" content="Automatisation des devis">
<script type="application/ld+json">{"keywords": ["Conformite", "Analyse de donnees"]}</script>
</head><body><p>Contenu francais.</p></body></html>"""


def _ecrire(dossier: Path, nom: str, html: str) -> Path:
    chemin = dossier / nom
    chemin.write_text(html, encoding="utf-8")
    return chemin


def test_le_parseur_collecte_les_quatre_familles(tmp_path: Path) -> None:
    """title, meta jugées, og:*, et keywords du JSON-LD."""
    page = _Page()
    page.feed(_FR)
    assert page.meta["title"] == ["Automatisation des devis"]
    assert page.meta["article:tag"] == ["Souverainete"]
    assert page.meta["description"] == ["Comment automatiser vos devis"]
    assert page.meta["jsonld:keywords"] == ["Conformite", "Analyse de donnees"]


def test_metadonnee_identique_a_la_reference_est_non_traduite(tmp_path: Path) -> None:
    """Le cas mesuré : le tag anglais est le tag français, caractère pour caractère."""
    fr = _ecrire(tmp_path, "fr.html", _FR)
    en = _ecrire(tmp_path, "en.html", _FR.replace('lang="fr"', 'lang="en"')
                 .replace("<p>Contenu francais.</p>", "<p>English content.</p>"))
    constats = constats_metadonnees(en, fr, locale="en", locale_reference="fr")
    cles = {cle for constat, cle, _ in constats if constat == "non_traduit"}
    assert {"article:tag", "title", "jsonld:keywords"} <= cles, (
        f"les métadonnées non traduites ne sont pas toutes nommées : {constats}"
    )


def test_metadonnee_traduite_ne_declenche_rien(tmp_path: Path) -> None:
    """Non-régression : une page correctement traduite ne doit produire aucun constat."""
    fr = _ecrire(tmp_path, "fr.html", _FR)
    en = _ecrire(tmp_path, "en.html", """<html lang="en"><head>
<title>Quote automation</title>
<meta name="description" content="How to automate your quotes">
<meta property="article:tag" content="Sovereignty">
<meta property="og:title" content="Quote automation">
<script type="application/ld+json">{"keywords": ["Compliance", "Data analysis"]}</script>
</head><body><p>English content.</p></body></html>""")
    assert constats_metadonnees(en, fr, locale="en", locale_reference="fr") == []


def test_valeur_differente_mais_en_langue_de_reference_est_mal_traduite(tmp_path: Path) -> None:
    """Une valeur retouchée qui reste française : différente de la référence, donc invisible
    au test d'identité — c'est la densité mesurée sur la valeur SEULE qui la voit."""
    fr = _ecrire(tmp_path, "fr.html", _FR)
    en = _ecrire(tmp_path, "en.html", """<html lang="en"><head>
<title>Quote automation</title>
<meta name="description" content="Comment automatiser tous les devis de la societe">
<meta property="article:tag" content="Sovereignty">
</head><body><p>English content.</p></body></html>""")
    constats = constats_metadonnees(en, fr, locale="en", locale_reference="fr")
    mal = {cle for constat, cle, _ in constats if constat == "mal_traduit"}
    assert "description" in mal, f"la description restée française n'est pas vue : {constats}"


def test_page_sans_metadonnee_ne_produit_rien(tmp_path: Path) -> None:
    """Borne : une page nue ne fabrique pas de constat."""
    fr = _ecrire(tmp_path, "fr.html", _FR)
    nue = _ecrire(tmp_path, "nue.html", "<html lang='en'><body><p>Hi</p></body></html>")
    assert constats_metadonnees(nue, fr, locale="en", locale_reference="fr") == []
