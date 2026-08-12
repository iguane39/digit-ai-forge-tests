"""TF-0122 — régression du correctif TF-0100, payée en réel sur Produit-01 le 12/08.

Deux défauts distincts, tous deux dans `forge_tests/adaptateurs/accessibilite.py` :

  (a) concrétisation incomplète — seul `:id` était substitué (`route.replace(":id", "1")`) ;
      un `:slug`, `:demandeId` ou `:userId` naviguait vers une URL au deux-points LITTÉRAL,
      une 404 imputée au produit à tort. Le joker `*` de react-router (route attrape-tout)
      n a lui aucun équivalent navigable et doit être écarté, jamais tenté.

  (b) absence d isolation — `page.goto` n était protégé par aucun `try`/`except` : une seule
      route innavigable (le `*`) propageait son exception jusqu au noyau et faisait tomber
      l audit ENTIER (exit 2, zéro rapport, douze pans perdus), au lieu de sortir NOMMÉE en
      non_juge pendant que les autres routes continuent d être jugées.

Le cas reproduit ici est celui constaté sur pièces : une route `*` et une route `:slug` dans
le même inventaire — exactement la combinaison qui faisait tomber l audit avant correctif.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import accessibilite


class _PageFactice:
    """Double minimal d une page Playwright : suffisant pour prouver navigation et isolation
    sans dépendre d un navigateur réel."""

    def __init__(self, echoue_sur: set[str] | None = None) -> None:
        self._echoue_sur = echoue_sur or set()
        self.urls_visitees: list[str] = []

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None) -> None:
        self.urls_visitees.append(url)
        for motif in self._echoue_sur:
            if motif in url:
                raise RuntimeError(f"navigation refusee pour {url}")

    def content(self) -> str:
        return "<html><body>ok</body></html>"


# --- (a) concrétisation : TOUT `:nom`, pas le seul `:id` ---------------------------------------
def test_concretiser_substitue_nimporte_quel_parametre_nomme() -> None:
    """ROUGE implicite : avant le correctif, `route.replace(":id", "1")` laissait `:slug` et
    `:userId` tels quels — une URL au deux-points littéral, jamais celle d une vraie page."""
    assert accessibilite._concretiser("/demandes/:id") == ("/demandes/1", None)
    assert accessibilite._concretiser("/produits/:slug") == ("/produits/1", None)
    assert accessibilite._concretiser("/comptes/:userId/detail") == ("/comptes/1/detail", None)


def test_concretiser_substitue_plusieurs_parametres_dans_la_meme_route() -> None:
    assert accessibilite._concretiser("/a/:x/b/:y") == ("/a/1/b/1", None)


def test_concretiser_route_sans_parametre_est_inchangee() -> None:
    assert accessibilite._concretiser("/accueil") == ("/accueil", None)


def test_concretiser_ecarte_le_joker_react_router_avec_un_motif_nommant_la_route() -> None:
    """Le `*` n a pas d équivalent navigable : il doit être ÉCARTÉ, jamais transformé en URL."""
    concret, motif = accessibilite._concretiser("*")
    assert concret is None
    assert motif is not None and "*" in motif

    concret2, motif2 = accessibilite._concretiser("/*")
    assert concret2 is None
    assert motif2 is not None and "/*" in motif2


# --- (b) isolation : une route en échec ne doit jamais lever --------------------------------
def test_capturer_une_route_ecrit_le_dom_avec_le_bon_segment_substitue(tmp_path: Path) -> None:
    page = _PageFactice()

    fichier, motif = accessibilite._capturer_une_route(page, "http://x", "/item/:slug", tmp_path)

    assert motif is None
    assert fichier is not None
    assert fichier.read_text(encoding="utf-8") == "<html><body>ok</body></html>"
    assert page.urls_visitees == ["http://x/item/1"]


def test_capturer_une_route_ecarte_le_joker_sans_meme_tenter_de_naviguer(tmp_path: Path) -> None:
    page = _PageFactice()

    fichier, motif = accessibilite._capturer_une_route(page, "http://x", "*", tmp_path)

    assert fichier is None
    assert motif is not None and "joker" in motif
    # Le point precis de TF-0122 (a) : le joker n est meme pas essaye, il est ECARTE en amont.
    assert page.urls_visitees == []


def test_capturer_une_route_isole_une_navigation_en_echec_au_lieu_de_lever(
    tmp_path: Path,
) -> None:
    """ROUGE implicite : avant le correctif, `page.goto` sans garde propageait cette exception
    jusqu au noyau — c est exactement la panne Playwright constatee sur Produit-01 (exit 2)."""
    page = _PageFactice(echoue_sur={"/panne"})

    fichier, motif = accessibilite._capturer_une_route(page, "http://x", "/panne", tmp_path)

    assert fichier is None
    assert motif is not None
    assert "/panne" in motif and "navigation impossible" in motif


# --- Bout en bout : le cas réel (route '*' + ':slug') ne fait plus tomber l audit ---------------
def test_analyser_isole_le_joker_et_continue_de_juger_les_autres_routes(
    tmp_path: Path, monkeypatch
) -> None:
    """Reproduit le cas constaté sur Produit-01 : un inventaire portant `*` (route attrape-tout
    react-router) ET une route paramétrée (`:slug`). AVANT le correctif, la navigation sur `*`
    aurait levé une exception Playwright non rattrapée dans `_capturer`, faisant tomber
    `analyser()` — et avec lui l audit ENTIER (exit 2, zéro rapport). Ici, `*` sort NOMMÉ en
    non_juge et `:slug` est normalement visité — l appel ne lève jamais.
    """
    monkeypatch.setattr(accessibilite, "_routes", lambda cible: ["*", "/item/:slug"])
    monkeypatch.setattr(accessibilite, "_juger", lambda capture: {"non_juge": [], "findings": []})
    page = _PageFactice()

    def _capturer_stub(cible: Path, routes: list[str], dossier: Path):
        captures: dict[str, Path] = {}
        motifs: list[str] = []
        for route in routes:
            fichier, motif = accessibilite._capturer_une_route(page, "http://x", route, dossier)
            if fichier is not None:
                captures[route] = fichier
            else:
                motifs.append(motif or f"route {route} non capturee")
        return captures, motifs

    monkeypatch.setattr(accessibilite, "_capturer", _capturer_stub)

    # Le point du test : cet appel ne lève RIEN — c est le vrai défaut TF-0122 (b).
    sortie = accessibilite.analyser(tmp_path)

    assert sortie.verdict in ("PASS", "FAIL", "SKIP")
    assert any("*" in m and "joker" in m for m in sortie.non_juge)
    # La route concrétisable a bien été jugée : douze pans perdus, ce n est plus le cas.
    assert page.urls_visitees == ["http://x/item/1"]
    assert "accessibilite : routes auditees — /item/:slug" in sortie.non_juge
