"""RT-16 / TF-0211 — un pan qui a échoué sa PRÉCONDITION accusait quand même le produit.

Constaté en production : le pan `qualif` n a jamais franchi l authentification — il l avait
lui-même consigné (`Failed to load resource: 401 (UNAUTHORIZED)`) sur LES SIX routes. Il a donc
photographié six fois l écran de connexion et en a tiré **13 findings** : 6 `route-en-defaut`
(« marqueur de contenu absent », parce que la page n est pas celle qu il croit), 6
`affordance-sans-effet` citant mot pour mot le même formulaire de connexion, et 1 `seuil:qualif`
qui n est que leur somme. Tous au même risque, donc tous remontés en bloc : 13 des 33 findings
du rapport (39 %) venaient de ce seul angle mort.

Le modèle de bon comportement existait déjà dans la forge : le pan `api`, dans la même
situation, sort un inventaire VIDE, « surface non énumérable », et zéro constat produit.

Les deux sens sont prouvés, parce que la sur-correction serait aussi grave que le défaut :
  - toutes les routes refusées → SKIP motivé, ZÉRO constat produit ;
  - une seule route refusée parmi des routes saines → son constat est CONSERVÉ ; le pan ne
    devient pas muet dès qu une page échoue ;
  - aucune route refusée → comportement strictement inchangé.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import qualif

_REFUS_401 = "Failed to load resource: the server responded with a status of 401 (UNAUTHORIZED)"
_CORPS_CONNEXION = (
    "<html><body><h1>Connexion</h1><form><input name=email><input type=password>"
    "<button>Se connecter</button></form></body></html>"
)


def _affordance(rang: int = 0, motif: str | None = None) -> dict:
    return {
        "rang": rang,
        "tag": "button",
        "libelle": "Se connecter",
        "motif": motif,
        "delegation": False,
    }


def _page(
    route: str,
    *,
    statut: int | None = 200,
    console: list[str] | None = None,
    problemes: list[str] | None = None,
    corps: str = _CORPS_CONNEXION,
    affordances: list[dict] | None = None,
) -> dict:
    return {
        "route": route,
        "statut": statut,
        "problemes": list(problemes or []),
        "affordances": list(affordances or []),
        "corps": corps,
        "console": list(console or []),
    }


def _config(marqueurs: dict[str, str] | None = None) -> dict:
    return {"base": "https://qualif.exemple", "marqueurs": dict(marqueurs or {})}


def _mire(route: str) -> dict:
    """Une route telle que le produit réel l a rendue : la mire, et le refus en console."""
    return _page(
        route,
        console=[_REFUS_401],
        problemes=[f"marqueur de contenu absent : {route.strip('/') or 'accueil'!r}"],
        affordances=[_affordance(0, "élément interactif sans écouteur attaché")],
    )


_SIX_ROUTES = ("/", "/dossiers", "/dossiers/1", "/parametres", "/rapports", "/comptes")


# --- (a) Toutes les routes refusées : SKIP motivé, zéro constat produit -----------------------
def test_toutes_les_routes_en_401_ne_produisent_aucun_constat(tmp_path: Path) -> None:
    releve = [_mire(route) for route in _SIX_ROUTES]
    marqueurs = {route: f"marqueur-{i}" for i, route in enumerate(_SIX_ROUTES)}

    sortie = qualif.conclure(tmp_path, _config(marqueurs), releve, [])

    assert sortie.verdict == "SKIP"
    assert sortie.findings == []
    assert sortie.surface is None
    assert any("PRECONDITION NON ETABLIE" in ligne for ligne in sortie.non_juge)
    # L inventaire est déclaré non mesurable ROUTE PAR ROUTE, jamais tu.
    assert {nt.element for nt in sortie.non_testables} == {
        f"qualif:route:{route}" for route in _SIX_ROUTES
    }
    assert all(
        nt.champs_requis == list(qualif.CHAMPS_REQUIS_SESSION) for nt in sortie.non_testables
    )


def test_les_13_findings_du_rapport_reel_disparaissent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le compte exact du défaut constaté — 13 findings avant la garde, 0 après.

    La garde neutralisée reproduit le comportement d avant TF-0211 : c est la fixture ROUGE, et
    elle prouve que ce test mesure bien la garde et non un relevé devenu inoffensif.
    """
    releve = [_mire(route) for route in _SIX_ROUTES]
    config = _config({route: f"marqueur-{i}" for i, route in enumerate(_SIX_ROUTES)})

    monkeypatch.setattr(qualif, "precondition_absente", lambda *_: None)
    avant = qualif.conclure(tmp_path, config, releve, [])
    classes = [f.classe for f in avant.findings]
    assert len(avant.findings) == 13, classes
    assert classes.count("route-en-defaut") == 6
    assert classes.count("affordance-sans-effet") == 6
    assert classes.count("seuil-non-tenu") == 1
    assert avant.verdict == "FAIL"

    monkeypatch.undo()
    apres = qualif.conclure(tmp_path, config, releve, [])
    assert (apres.verdict, apres.findings) == ("SKIP", [])


def test_le_401_porte_par_le_statut_http_declenche_aussi_la_garde(tmp_path: Path) -> None:
    """Toutes les routes ne consignent pas leur refus en console : certaines le rendent."""
    releve = [
        _page(route, statut=403, problemes=["route atteignable par un lien mais HTTP 403"])
        for route in ("/", "/dossiers")
    ]
    sortie = qualif.conclure(tmp_path, _config(), releve, [])
    assert (sortie.verdict, sortie.findings) == ("SKIP", [])


def test_le_marqueur_declare_absent_partout_declenche_la_garde(tmp_path: Path) -> None:
    """Second canal du critère : la page rendue n est jamais celle que le projet a déclarée."""
    releve = [_page(route, console=[]) for route in ("/", "/dossiers")]
    sortie = qualif.conclure(
        tmp_path, _config({"/": "Tableau de bord", "/dossiers": "Mes dossiers"}), releve, []
    )
    assert sortie.verdict == "SKIP"
    assert any("marqueur" in ligne for ligne in sortie.non_juge)


# --- (b) Une seule route refusée : le constat est CONSERVÉ -------------------------------------
def test_une_seule_route_en_401_reste_un_defaut_de_cette_route(tmp_path: Path) -> None:
    """Sur-correction interdite : un pan qui se tait dès qu une page échoue ne mesure plus rien."""
    saine = _page(
        "/",
        corps="<h1>Tableau de bord</h1>",
        affordances=[_affordance(0, None)],
    )
    fautive = _mire("/comptes")
    releve = [saine, _page("/dossiers", corps="<h1>Mes dossiers</h1>"), fautive]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    assert sortie.verdict == "FAIL"
    identifiants = {f.id for f in sortie.findings}
    assert "qualif:route:/comptes" in identifiants
    assert "qualif:route:/" not in identifiants
    assert "qualif:effet:/comptes:0:button" in identifiants


def test_une_route_saine_suffit_a_ecarter_la_garde(tmp_path: Path) -> None:
    """Le critère est « TOUTES les routes », pas « la plupart » — cinq refus sur six ne suffisent
    pas : la sixième prouve que la session existait bel et bien."""
    releve = [_mire(route) for route in _SIX_ROUTES[:5]]
    releve.append(_page("/rapports", corps="<h1>Rapports</h1>"))
    sortie = qualif.conclure(tmp_path, _config(), releve, [])
    assert sortie.verdict == "FAIL"
    assert {f.id for f in sortie.findings} >= {f"qualif:route:{r}" for r in _SIX_ROUTES[:5]}


def test_une_route_unique_ne_declenche_jamais_la_garde(tmp_path: Path) -> None:
    """Une seule route parcourue ne permet pas de distinguer un défaut de route d une
    précondition manquée : la garde s abstient, le constat est publié."""
    sortie = qualif.conclure(tmp_path, _config(), [_mire("/")], [])
    assert sortie.verdict == "FAIL"
    assert "qualif:route:/" in {f.id for f in sortie.findings}


def test_une_route_indechiffrable_ecarte_la_garde(tmp_path: Path) -> None:
    """La garde se déduit d un faisceau de CONSTATS concordants, jamais d une ignorance : une
    route dont la navigation a échoué ne porte aucun signal, donc n atteste de rien."""
    releve = [
        _mire("/"),
        _page("/dossiers", statut=None, problemes=["navigation impossible : TimeoutError"],
              corps=""),
    ]
    sortie = qualif.conclure(tmp_path, _config(), releve, [])
    assert sortie.verdict == "FAIL"


# --- (c) Aucune route refusée : comportement strictement inchangé ------------------------------
def test_sans_401_le_comportement_est_inchange(tmp_path: Path) -> None:
    releve = [
        _page("/", corps="<h1>Tableau de bord</h1>", affordances=[_affordance(0, None)]),
        _page(
            "/panne",
            statut=500,
            problemes=["erreur serveur HTTP 500"],
            corps="<h1>Erreur</h1>",
            affordances=[_affordance(0, "lien sans attribut href : aucune destination")],
        ),
    ]
    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    assert sortie.verdict == "FAIL"
    assert sortie.non_testables == []
    assert sortie.surface is not None
    identifiants = {f.id for f in sortie.findings}
    assert {"qualif:route:/panne", "qualif:effet:/panne:0:button"} <= identifiants
    assert "qualif:route:/" not in identifiants
    assert not any("PRECONDITION" in ligne for ligne in sortie.non_juge)


def test_un_parcours_entierement_sain_reste_PASS(tmp_path: Path) -> None:
    releve = [
        _page("/", corps="<h1>Tableau de bord</h1>", affordances=[_affordance(0, None)]),
        _page("/dossiers", corps="<h1>Mes dossiers</h1>", affordances=[_affordance(0, None)]),
    ]
    sortie = qualif.conclure(tmp_path, _config(), releve, [])
    assert (sortie.verdict, sortie.findings) == ("PASS", [])


# --- Le critère lui-même, exercé pièce par pièce ----------------------------------------------
@pytest.mark.parametrize(
    ("libelle", "texte", "attendu"),
    [
        ("le message exact du navigateur", _REFUS_401, True),
        ("un 403 dit autrement", "GET /api/x 403 (Forbidden)", True),
        ("un 404 n est pas un refus d authentification", "…status of 404 (Not Found)", False),
        ("un 500 non plus", "…status of 500 (Internal Server Error)", False),
        ("le nombre 401 comme donnee affichee n est pas un refus", "total : 401 dossiers", False),
        ("401 collé dans un identifiant ne compte pas", "GET /a401b (OK)", False),
        ("texte vide", "", False),
    ],
)
def test_est_refus_auth(libelle: str, texte: str, attendu: bool) -> None:
    assert qualif._est_refus_auth(texte) is attendu, libelle


def test_precondition_absente_rend_un_motif_qui_nomme_les_routes() -> None:
    motif = qualif.precondition_absente(
        [_mire("/"), _mire("/dossiers")], _config()
    )
    assert motif is not None
    assert "/dossiers" in motif and "401" in motif
    assert "FORGE_TESTS_QUALIF_LOGIN" in motif
