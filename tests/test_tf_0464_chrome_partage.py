"""TF-0464 — la parité de navigation lit tout le CHROME PARTAGÉ, pas seulement `<nav>`.

Fait qui l'a ouverte (digit-ai.fr, 201 pages FR / 201 EN en production, 22/08/2026) : les
deux pieds de page sont des `<footer>` SANS `<nav>`. Le français porte 21 liens, l'anglais 3.
Le pan lisait 0 contre 0 et rendait PASS — un silence indiscernable d'un succès, et la garde
`muettes` ne se déclenchait pas puisque l'en-tête, lui, EST un `<nav>` : la navigation passait
pour vue.

Les deux sens sont joués : sans le correctif la page amputée passe (c'est ce que la recette
refuse désormais), avec lui l'entrée manquante est NOMMÉE. Un troisième cas tient la
non-régression : deux pieds identiques ne doivent produire aucun écart.
"""
from __future__ import annotations

from forge_tests.adaptateurs.i18n import _Page, entrees_de_menu

_ENTETE = (
    '<nav aria-label="principal">'
    '<a href="{p}/">Accueil</a><a href="{p}/services">Services</a>'
    "</nav>"
)
_PIED_RICHE = (
    "<footer>"
    '<a href="{p}/services/automatisation">Automatisation</a>'
    '<a href="{p}/services/data">Data</a>'
    '<a href="{p}/solutions">Solutions</a>'
    '<a href="{p}/a-propos">À propos</a>'
    "</footer>"
)
_PIED_PAUVRE = '<footer><a href="{p}/blog">Blog</a></footer>'


def _page(html: str) -> _Page:
    p = _Page()
    p.feed(html)
    return p


def _cles(html: str, locales: set[str]) -> list[str]:
    return entrees_de_menu(_page(html), locales)


LOCALES = {"en"}


def test_le_pied_de_page_entre_dans_la_parite() -> None:
    """Un `<footer>` sans `<nav>` est du chrome partagé : ses liens sont lus."""
    fr = _cles((_ENTETE + _PIED_RICHE).format(p=""), LOCALES)
    assert "/services/automatisation" in fr, (
        "les liens de pied de page restent invisibles — c'est le défaut mesuré sur "
        "digit-ai.fr : 21 liens contre 3, lus 0 contre 0"
    )
    assert len(fr) == 6, f"6 entrées attendues (2 en-tête + 4 pied), obtenu {len(fr)} : {fr}"


def test_l_amputation_du_pied_est_visible() -> None:
    """21 contre 3 ne doit plus se lire 0 contre 0 : l'écart existe et il est nommable."""
    fr = set(_cles((_ENTETE + _PIED_RICHE).format(p=""), LOCALES))
    en = set(_cles((_ENTETE + _PIED_PAUVRE).format(p="/en"), LOCALES))
    manquantes = fr - en
    assert manquantes, "aucun écart détecté : le pan resterait muet sur un pied amputé"
    assert "/services/automatisation" in manquantes
    assert "/a-propos" in manquantes


def test_deux_pieds_identiques_ne_produisent_aucun_ecart() -> None:
    """Non-régression : la règle ne doit pas accuser une paire conforme."""
    fr = set(_cles((_ENTETE + _PIED_RICHE).format(p=""), LOCALES))
    en = set(_cles((_ENTETE + _PIED_RICHE).format(p="/en"), LOCALES))
    assert fr == en, f"écart fabriqué sur deux pieds identiques : {fr ^ en}"


def test_role_contentinfo_et_navigation_sont_des_reperes() -> None:
    """Le repère peut être porté par un rôle ARIA plutôt que par la balise."""
    html = '<div role="contentinfo"><a href="/mentions">Mentions</a></div>'
    assert "/mentions" in _cles(html, LOCALES)
    html_nav = '<div role="navigation"><a href="/tarifs">Tarifs</a></div>'
    assert "/tarifs" in _cles(html_nav, LOCALES)


def test_un_lien_hors_chrome_partage_reste_ignore() -> None:
    """Le corps de page n'est pas de la navigation : sans quoi tout lien deviendrait un menu."""
    html = _ENTETE.format(p="") + '<main><a href="/article-du-jour">Lire l article</a></main>'
    assert "/article-du-jour" not in _cles(html, LOCALES)
