"""TF-0325 — les deux limites déclarées de la couverture par rôle (TF-0316) sont levées.

L étude 20260817c les avait assumées comme frontières nommées, pas comme défauts :

  1. **un refus rendu par une page MAISON** (`/erreur/403`, `/acces-refuse`) n était pas reconnu —
     seuls 401/403 et la mire d authentification l étaient. Un produit qui refuse en redirigeant
     vers sa propre page d erreur voyait ses refus FONDUS dans le ratio : la page répond 200 avec
     un titre, donc la route comptait pour exercée. C est exactement le silence que TF-0316 vient
     de fermer pour 401/403, rouvert par un dialecte de plus ;
  2. **l avertissement par route** (délégation d événement, DevTools muet) était dédupliqué ENTRE
     profils par le `sorted(set(...))` de sortie : deux rôles dont la même route est muette ne
     produisaient qu une ligne, et « /admin non jugée » ne disait pas POUR QUI.

Les deux levées préfèrent le non-jugement DÉCLARÉ au faux positif : un refus reconnu à tort
sortirait du ratio une route peut-être cassée, ce qui est le défaut symétrique — celui qui absout.
Ce qui reste hors couverture après la levée (un refus servi sur `/oups` non déclaré) est redit au
`NON_JUGE` : une frontière déplacée sans être redite est une frontière tue.

Le banc de la levée 2 est celui de TF-0316, importé plutôt que recopié : la limite et sa levée
doivent se mesurer sur le MÊME faux navigateur, sinon on prouve la levée d autre chose.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_tf_0316_couverture_par_role import (  # le banc de la limite levée ici
    BASE,
    _storage_state,
    env_propre,  # noqa: F401  — fixture réutilisée telle quelle
    navigateur,  # noqa: F401
)

from forge_tests.adaptateurs import qualif


def _config(**surcharges: object) -> dict:
    return {
        "base": BASE, "marqueurs": {}, "storage_state": "", "bearer": "", "refus": [],
        **surcharges,
    }


def _page(route: str, *, statut: int = 200, url_finale: str | None = None, role: str = "") -> dict:
    return {
        "route": route,
        "statut": statut,
        "role": role,
        "url_finale": url_finale if url_finale is not None else f"{BASE}{route}",
        "problemes": [],
        "affordances": [],
        "corps": f"<h1>{route}</h1>",
        "console": [],
    }


# --- Levée 1 : le refus rendu par une page MAISON est reconnu ----------------------------------
@pytest.mark.parametrize(
    ("libelle", "route_arrivee", "attendu"),
    [
        ("la page d erreur 403 du produit", "/erreur/403", "403"),
        ("le libellé français", "/acces-refuse", "acces-refuse"),
        ("le libellé anglais", "/forbidden", "forbidden"),
        ("un 401 rendu en page", "/erreur/401", "401"),
        ("la formule explicite", "/permission-denied", "permission-denied"),
    ],
)
def test_un_refus_rendu_par_une_page_MAISON_est_desormais_RECONNU(
    libelle: str, route_arrivee: str, attendu: str
) -> None:
    """La levée : ces routes ne sont ni 401/403 ni des mires, et le refus y est pourtant dit. AVANT,
    elles comptaient pour des succès et le ratio d un rôle bridé annonçait 100 %."""
    page_vue = _page("/admin", url_finale=f"{BASE}{route_arrivee}")

    motif = qualif.refus_autorisation(page_vue, _config())

    assert motif is not None, libelle
    assert route_arrivee in motif and attendu in motif


def test_une_route_de_refus_DECLAREE_juge_meme_sans_mot_reconnaissable() -> None:
    """Le geste qui lève la limite entièrement : le produit refuse en servant `/oups`, l opérateur
    le DÉCLARE, et le pan n a plus rien à deviner."""
    page_vue = _page("/admin", url_finale=f"{BASE}/oups")

    assert qualif.refus_autorisation(page_vue, _config()) is None  # non déclarée : non jugée
    motif = qualif.refus_autorisation(page_vue, _config(refus=["/oups"]))
    assert motif is not None and "DÉCLARÉE" in motif


@pytest.mark.parametrize(
    ("libelle", "route_arrivee"),
    [
        ("une panne n est pas un refus", "/erreur/500"),
        ("une page d erreur GENERIQUE ne dit pas laquelle", "/erreur"),
        ("un nom quelconque ne s invente pas", "/oups"),
        ("le mot doit etre un segment ENTIER", "/produits/403-lumens"),
        ("un article de blog qui PARLE du 403", "/blog/comprendre-le-403-interdit"),
    ],
)
def test_ce_qui_n_est_PAS_un_atterrissage_de_refus_reste_NON_JUGE(
    libelle: str, route_arrivee: str
) -> None:
    """Le sens qui absoudrait, et il est le plus coûteux des deux : un faux refus fait SORTIR DU
    RATIO une route peut-être cassée. La route reste donc comptée comme parcourue, et la frontière
    est déclarée au registre plutôt que franchie à la devinette."""
    page_vue = _page("/admin", url_finale=f"{BASE}{route_arrivee}")

    assert qualif.refus_autorisation(page_vue, _config()) is None, libelle


def test_les_trois_formes_historiques_de_refus_sont_INTACTES() -> None:
    """La levée ne doit rien retirer : 401, 403 et la redirection vers la mire jugent comme
    avant."""
    assert qualif.refus_autorisation(_page("/admin", statut=403), _config()) == "HTTP 403"
    assert qualif.refus_autorisation(_page("/admin", statut=401), _config()) == "HTTP 401"
    assert (
        qualif.refus_autorisation(_page("/admin", url_finale=f"{BASE}/login"), _config())
        == "redirection d autorisation vers /login"
    )
    assert qualif.refus_autorisation(_page("/", statut=200), _config()) is None


def test_un_refus_MAISON_sort_du_ratio_en_issue_distincte(tmp_path: Path) -> None:
    """Bout de chaîne de la levée 1 : reconnu, le refus maison se comporte comme un 403 — hors du
    ratio, NOMMÉ, et rangé pour l UTILISATEUR (fournir la bonne identité), pas pour la forge."""
    releve = [
        _page("/"),
        _page("/demandes"),
        _page("/admin", url_finale=f"{BASE}/erreur/403"),
    ]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    refus = [f for f in sortie.findings if f.classe == qualif.CLASSE_REFUS_AUTORISATION]
    assert [f.id for f in refus] == ["qualif:route:/admin"]
    assert sortie.surface["inventorie"] == 2  # la route refusée n est pas comptée
    assert sortie.surface["elements_refuses"] == ["qualif:route:/admin"]


def test_avant_la_levee_ce_refus_comptait_pour_un_SUCCES(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La mesure de l écart, faite avec le code d avant remis en place le temps du test : sans la
    reconnaissance de l atterrissage, `/admin` entre au ratio comme une route saine. C est la
    fixture rouge de l item — le faux 100 % qu un rôle bridé affichait."""
    releve = [_page("/"), _page("/admin", url_finale=f"{BASE}/erreur/403")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])
    assert sortie.surface["inventorie"] == 1  # après : la refusée sort du décompte

    # Avant : seuls 401/403 et le saut d authentification étaient reconnus.
    def _refus_d_avant(page_vue: dict, config: dict) -> str | None:
        statut = page_vue.get("statut")
        return f"HTTP {statut}" if statut in (401, 403) else None

    monkeypatch.setattr(qualif, "refus_autorisation", _refus_d_avant)
    avant = qualif.conclure(tmp_path, _config(), releve, [])

    assert avant.surface["inventorie"] == 2
    assert avant.surface["elements_refuses"] == []
    assert avant.surface["ratio"] == 1.0  # LE faux 100 %


def test_la_frontiere_qui_RESTE_est_declaree_au_registre() -> None:
    """Une frontière déplacée sans être redite est une frontière tue : le registre doit dire ce que
    la reconnaissance couvre et ce qu il faut déclarer pour aller plus loin."""
    entier = " ".join(qualif.NON_JUGE)

    assert "FORGE_TESTS_QUALIF_REFUS" in entier
    assert "COMPTE COMME PARCOURU" in entier
    assert "atterrissage de refus reconnu" in entier


# --- Levée 2 : l avertissement par route garde sa dimension RÔLE -------------------------------
_ALERTES = [
    "qualif : protocole DevTools indisponible sur /admin (pas de CDP) — affordances jugees sur "
    "leurs seuls attributs, comme en statique",
    "qualif : delegation d evenement posee sur document/body de /admin — les affordances sans "
    "ecouteur propre y sont NON JUGEES, jamais accusees",
]


def test_l_etiquette_de_role_est_posee_sur_chaque_alerte() -> None:
    """La mécanique de la levée 2 : l étiquette suit l idiome déjà posé pour le motif de session,
    et elle est ce qui distingue deux constats que la déduplication fondait en un."""
    etiquetees = qualif._avec_role(_ALERTES, "lecteur")

    assert all(alerte.startswith("qualif : (role « lecteur ») ") for alerte in etiquetees)
    assert all("qualif : qualif :" not in alerte for alerte in etiquetees)
    for alerte, origine in zip(etiquetees, _ALERTES, strict=True):
        assert origine.removeprefix("qualif : ") in alerte  # le constat lui-même est intact


def test_sans_role_declare_l_alerte_est_rendue_TELLE_QUELLE() -> None:
    """Second sens : à N = 1 non étiqueté, fabriquer « (role «  ») » inventerait une dimension que
    l opérateur n a pas déclarée — et le rapport mono-session ne doit pas changer de forme."""
    assert qualif._avec_role(_ALERTES, "") == _ALERTES
    assert qualif._avec_role(_ALERTES, None) == _ALERTES


def test_la_meme_route_muette_sous_DEUX_roles_donne_DEUX_lignes(
    tmp_path: Path, env_propre, navigateur  # noqa: ANN001, F811
) -> None:
    """Bout en bout, sur le banc de TF-0316 dont le faux contexte refuse le protocole DevTools : le
    même avertissement est rencontré par les deux profils. AVANT, `sorted(set(...))` n en gardait
    qu un et la dimension rôle disparaissait — « / non jugée » sans dire pour qui.

    La route est l ACCUEIL et non `/admin` : sous `lecteur`, `/admin` rend 403 et les affordances
    n y sont pas lues du tout — il n y aurait donc rien à dédupliquer."""
    from forge_tests import qualification

    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATES"] = (
        f"admin={_storage_state(tmp_path, 'admin.json')},"
        f"lecteur={_storage_state(tmp_path, 'lecteur.json')}"
    )
    qualification.oublier(tmp_path)
    sortie = qualif.analyser(tmp_path)
    qualification.oublier(tmp_path)

    devtools = [
        ligne
        for ligne in sortie.non_juge
        if "protocole DevTools indisponible sur /" in ligne
    ]
    assert len(devtools) == 2, devtools  # une par rôle, plus de fusion
    assert any("(role « admin »)" in ligne for ligne in devtools)
    assert any("(role « lecteur »)" in ligne for ligne in devtools)


def test_a_UNE_seule_session_le_rapport_ne_gagne_AUCUNE_ligne(
    tmp_path: Path, env_propre, navigateur  # noqa: ANN001, F811
) -> None:
    """Sens rouge du précédent : sans liste étiquetée, l étiquetage ne doit rien ajouter ni
    dupliquer — le rapport mono-session est celui d avant, au caractère près."""
    from forge_tests import qualification

    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    qualification.oublier(tmp_path)
    sortie = qualif.analyser(tmp_path)
    qualification.oublier(tmp_path)

    devtools = [
        ligne
        for ligne in sortie.non_juge
        if "protocole DevTools indisponible sur /" in ligne
    ]
    assert len(devtools) == 1, devtools
    assert "role «" not in devtools[0]
