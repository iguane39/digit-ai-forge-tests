"""TF-0591 — la règle de relevé des ressources d'une page, et la preuve qu'elle VIT.

LE FAIT. `_RESSOURCE_HTML` a vécu six jours (commit du 18/08) avec un caractère BACKSPACE là où
son auteur avait écrit `\\b` : un échappement dans une chaîne non brute ne vaut pas ce qu'il
paraît. L'expression compilait, se relisait normalement à l'écran, et exigeait un octet qu'aucun
HTML ne contient — elle rendait donc « aucune ressource », le verdict le plus rassurant qui soit.

Mesuré : sur une page portant trois ressources, l'expression enregistrée en trouvait **zéro**,
la même avec un `\\b` réel en trouve **trois**.

CE TEST EXISTE PARCE QU'AUCUN NE COUVRAIT LA BRANCHE POSITIVE. Les 1119 tests du dépôt passaient
avec une règle morte ; c'est exactement ce qui l'a laissée vivre. Le contrôle de parc du pilot
(règle P3) attrape désormais la corruption à la source ; celui-ci tient la règle elle-même — les
deux se cumulent, l'un empêche l'octet d'entrer, l'autre prouve que l'expression fait son travail.
"""

from __future__ import annotations

from forge_tests.surface_servie import _RESSOURCE_HTML

_PAGE = (
    '<!doctype html><html><head>'
    '<link rel="stylesheet" href="/assets/app.css">'
    '<script src="/assets/index.js"></script>'
    "</head><body>"
    '<img src="/img/logo.png" alt="logo">'
    '<video><source src="/media/demo.mp4"><track src="/media/sous-titres.vtt"></video>'
    "</body></html>"
)


def test_les_ressources_d_une_page_sont_RELEVEES() -> None:
    """La branche positive, celle qui manquait. Une règle qui ne trouve jamais rien est pire
    qu'une règle absente : elle rassure au lieu de mesurer."""
    trouvees = _RESSOURCE_HTML.findall(_PAGE)

    assert "/assets/app.css" in trouvees, "la feuille de style d'un `<link>` n'est pas relevée"
    assert "/assets/index.js" in trouvees, "le script d'un `<script>` n'est pas relevé"
    assert "/img/logo.png" in trouvees, "l'image d'un `<img>` n'est pas relevée"
    assert len(trouvees) >= 3, f"seulement {len(trouvees)} ressource(s) relevée(s) : {trouvees}"


def test_l_expression_ne_porte_AUCUN_octet_de_controle() -> None:
    """Le défaut fondateur, tenu à la source.

    Un `\\b` hors chaîne brute devient 0x08. L'assertion porte sur le motif lui-même parce que
    c'est le seul endroit où l'octet est visible — à la relecture du fichier, il ne l'est pas.
    """
    motif = _RESSOURCE_HTML.pattern

    accidentels = [c for c in motif if c in "\x07\x08\x0b\x0c"]
    assert not accidentels, (
        f"{len(accidentels)} octet(s) de contrôle dans le motif — un échappement écrit hors "
        "chaîne BRUTE ne vaut pas ce qu'il paraît, et l'expression n'attrapera plus jamais rien"
    )
    assert "\\b" in motif, (
        "la frontière de mot a disparu du motif : sans elle, `<links>` ou `<imgx>` seraient "
        "confondus avec `<link>` et `<img>`"
    )


def test_une_balise_dont_le_nom_ETEND_une_balise_connue_n_est_pas_confondue() -> None:
    """Ce à quoi la frontière de mot sert vraiment — et donc ce qu'on perdait deux fois.

    La corruption ne supprimait pas seulement la règle : elle supprimait aussi la précision que
    la frontière apportait. Sans elle, la règle aurait attrapé n'importe quelle balise commençant
    par `link` ou `img`.
    """
    assert _RESSOURCE_HTML.findall('<linkedin src="/x.js">') == [], (
        "une balise `<linkedin>` est prise pour un `<link>` — la frontière de mot ne joue pas"
    )
