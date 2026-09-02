"""TF-0763 — K2 (piège de focus) identifie l'ÉLÉMENT, plus seulement sa FORME.

Le défaut payé. `_JS_ACTIF` rendait `tagName + id + classe`. Trois boutons frères sans `id`
ni classe — « Trier par date », « Nouvelle », « Exporter » — se relevaient donc `button`,
`button`, `button`, et la règle « trois pas d'affilée sur le même élément » y lisait « la
tabulation n'avance plus ». Trois routes du banc VERT sur cinq sortaient ainsi avec un
finding BLOQUANT (WCAG 2.1.2) sur une interface conforme, et le critère de sortie S-01
(« la forge se tait sur ce qui va bien ») n'était plus prononçable.

Ce que ces cas verrouillent, dans les deux sens et sur le CHEMIN RÉEL de la mesure — le
navigateur est simulé, la boucle de tabulation et la dérivation du verdict sont les vraies :

  · VERT   — des frères qui se ressemblent trait pour trait ne sont PAS un piège ;
  · ROUGE  — le même élément trois fois de suite EST un piège, et il est nommé lisiblement ;
  · BRUIT  — la mesure d'avant/après est écrite ici : les libellés sont identiques (c'est ce
             que l'ancien relevé comparait), les clés ne le sont pas ;
  · BORD   — le focus resté hors de la page (`body`) n'est pas un piège : il se DÉCLARE.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import clavier

CIBLE = Path("projet-factice")

#: Le relevé que `_JS_FOCUS` rend sur une page saine — K1 et K3 hors sujet ici.
_RELEVE = {
    "total": 4, "examines": 4, "sans_indicateur": [], "evitement": "present",
    "premier": "a « Aller au contenu »",
}


class _FauxClavier:
    def __init__(self, page: _FauxNavigateur) -> None:
        self._page = page

    def press(self, touche: str) -> None:
        assert touche == "Tab", "la mesure K2 ne presse que Tab"
        self._page.avancer()


class _FauxNavigateur:
    """Une page dont l'ordre de tabulation est DONNÉ : ce qui est joué, c'est la boucle réelle.

    `ordre` est la suite des éléments que le focus visite, chacun tel que `_JS_ACTIF` le rend
    (`cle` = identité, `libelle` = ce qu'un humain lit). La suite boucle, comme un navigateur.
    """

    def __init__(self, ordre: list[dict[str, str]]) -> None:
        self.ordre = ordre
        self.position = -1
        self.keyboard = _FauxClavier(self)

    def avancer(self) -> None:
        self.position += 1

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def evaluate(self, source: str, _args: object = None) -> object:
        if source is clavier._JS_FOCUS:
            return dict(_RELEVE)
        if source is clavier._JS_ACTIF:
            return dict(self.ordre[self.position % len(self.ordre)])
        return None  # `document.body.focus()`


def _mesurer(ordre: list[dict[str, str]]) -> dict:
    releve, _ = clavier._mesurer(_FauxNavigateur(ordre), "/commandes")
    return releve["k2"]


# Le vrai ordre de tabulation de `/commandes` au banc vert : le lien du menu, le filtre, puis
# TROIS boutons frères. Aucun n'a d'`id` ni de classe — c'est le cas qui accusait à tort.
_FRERES_SEMBLABLES = [
    {"cle": "html:1>body:1>div:1>nav:1>a:1", "libelle": "a"},
    {"cle": "html:1>body:1>div:1>section:2>select:1", "libelle": "select"},
    {"cle": "html:1>body:1>div:1>section:2>button:2", "libelle": "button"},
    {"cle": "html:1>body:1>div:1>section:2>button:3", "libelle": "button"},
    {"cle": "html:1>body:1>div:1>section:2>button:4", "libelle": "button"},
]

# Le même élément retenu par un gestionnaire de touche : la tabulation ne bouge plus.
_PIEGE = [
    {"cle": "html:1>body:1>div:1>form:1>input:1", "libelle": "input#recherche"},
] * 4


def test_freres_identiques_ne_sont_pas_un_piege() -> None:
    """VERT — trois boutons frères se ressemblent ; ils ne se confondent pas."""
    k2 = _mesurer(_FRERES_SEMBLABLES)
    assert k2["piege"] is None, (
        "trois éléments DISTINCTS de même forme sont accusés de piéger le focus — "
        "c'est le faux positif qui coûtait 3 routes sur 5 au banc vert"
    )
    assert k2["distincts"] == len(_FRERES_SEMBLABLES)


def test_meme_element_trois_fois_reste_un_piege() -> None:
    """ROUGE — la mesure n'a pas été affaiblie : un vrai piège sort toujours, et il est nommé."""
    k2 = _mesurer(_PIEGE)
    assert k2["piege"] == "input#recherche", (
        "le piège n'est plus détecté, ou il est nommé par sa clé technique au lieu du libellé"
    )
    assert k2["pas"] == 3, "la mesure doit s'arrêter au troisième pas, pas tabuler pour rien"


def test_le_bruit_venait_de_la_forme_et_la_cle_le_ferme() -> None:
    """La mesure avant/après, écrite : c'est la FORME qui confondait, l'identité qui sépare."""
    formes = [e["libelle"] for e in _FRERES_SEMBLABLES[2:]]
    cles = [e["cle"] for e in _FRERES_SEMBLABLES[2:]]
    assert formes == ["button"] * 3, "le cas ne reproduit plus l'ambiguïté qu'il documente"
    assert len(set(cles)) == 3, "les clés ne distinguent pas ce que la forme confond"


def test_focus_hors_de_la_page_se_declare_au_lieu_d_accuser(monkeypatch) -> None:
    """BORD — le focus resté sur `body` n'est pas un piège : il n'y a rien à piéger."""
    k2 = _mesurer([{"cle": "body", "libelle": "body"}])
    assert k2["piege"] is None, "une page sans élément tabulable était accusée de piéger"
    assert k2["hors_page"] is True

    monkeypatch.setattr(clavier.accessibilite, "routes_a_auditer", lambda _c: (["/"], "test"))
    monkeypatch.setattr(
        clavier, "parcourir",
        lambda *a, **k: ({"/": {**_RELEVE, "k2": k2}}, []),
    )
    sortie = clavier.analyser(CIBLE)
    assert [f for f in sortie.findings if ":K2:" in f.id] == []
    assert any("K2 NON CONCLUANT" in ligne for ligne in sortie.non_juge), (
        "le cas non concluant a disparu du rapport — un PASS muet se lit « conforme »"
    )


def test_releve_ancien_en_texte_reste_lisible() -> None:
    """Repli : un relevé rendu en texte (forme d'avant) ne fait pas planter la mesure."""
    page = _FauxNavigateur([{"cle": "x", "libelle": "x"}])
    page.evaluate = lambda source, _args=None: (  # type: ignore[method-assign]
        dict(_RELEVE) if source is clavier._JS_FOCUS
        else ("button" if source is clavier._JS_ACTIF else None)
    )
    releve, _ = clavier._mesurer(page, "/")
    assert releve["k2"]["piege"] == "button"


def test_le_releve_javascript_rend_bien_une_identite() -> None:
    """Le contrat du relevé est dans la source jouée : `cle` (identité) ET `libelle` (lisible)."""
    assert "cle:" in clavier._JS_ACTIF.replace(" ", "").replace("\n", "")
    assert "libelle:" in clavier._JS_ACTIF.replace(" ", "").replace("\n", "")
    assert "parentElement" in clavier._JS_ACTIF, (
        "la clé ne remonte plus l'arbre : elle ne peut pas distinguer deux frères"
    )
