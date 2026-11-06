"""TF-2275 — des bancs qui rejouent des réponses réalistes, et deux fois.

Fait remonté (Produit-86, lot 20261106d, RP-48) : un outil qui lit les réponses d'une application
derrière Cloudflare Access a montré au premier job réel quatre défauts (constats recréés à chaque
tour, bilan figé, message de tour faux, jetons de la cible en clair dans la preuve) que 21 tests
unitaires ne voyaient pas : les bancs ne jouaient ni deux tours, ni une réponse 302 avec cookie.

Décision du 06/11/2026 : un jeu de réponses réalistes (302 avec cookie, deux tours, jeton à masquer)
est fourni aux bancs, et la règle « rejouer deux fois » s'écrit pour l'ingestion.

Ce que ce fichier prouve :
  - le jeu est RÉALISTE (la cible rend réellement 302 + Set-Cookie, un jeton dans l'en-tête, la
    requête et le corps, un état qui change au tour 2) : sans cela le banc resterait idéal ;
  - la règle « rejouer deux fois » a ses deux sens : une ingestion idempotente passe, celle du lot
    (constats recréés à chaque tour) est refusée, nommée par défaut ;
  - la lecture de réponses de cette forge (`parcours-personas`, qui suit les redirections à la main)
    est jouée SUR ce jeu : elle ne publie aucun jeton, et deux passages rendent le même relevé ;
  - la reprise (`--reprendre`), qui ingère un rapport antérieur, est rejouée deux fois.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from forge_tests import reponses_realistes as rr
from forge_tests.adaptateurs import personas


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        return None


def _lire(url: str, cookie: str = "") -> tuple[int, dict[str, str], str]:
    requete = urllib.request.Request(url, headers={"Cookie": cookie} if cookie else {})
    ouvreur = urllib.request.build_opener(_SansRedirection)
    try:
        with ouvreur.open(requete, timeout=5) as reponse:
            return reponse.status, dict(reponse.headers), reponse.read().decode("utf-8")
    except urllib.error.HTTPError as erreur:
        return erreur.code, dict(erreur.headers), ""


def _etat_avec_cookie(avec: bool) -> dict:
    cookies = [{"name": rr.COOKIE_ACCES, "value": rr.JETON_ACCES, "domain": "127.0.0.1",
                "path": "/"}] if avec else []
    return {"cookies": cookies, "origins": []}


# --- Le jeu est réaliste ----------------------------------------------------------------------
def test_la_cible_rend_un_302_cookie_et_un_jeton_en_tete_requete_et_corps() -> None:
    with rr.servir("acces-302-cookie") as cible:
        code, entetes, _ = _lire(cible.url + "/")
        assert code == 302
        assert f"{rr.COOKIE_ACCES}={rr.JETON_ACCES}" in entetes["Set-Cookie"]
        assert rr.JETON_ACCES in entetes["Location"]  # le jeton voyage dans la requête de retour
        code, entetes, corps = _lire(cible.url + "/app", f"{rr.COOKIE_ACCES}={rr.JETON_ACCES}")
        assert code == 200 and entetes["X-Access-Token"] == rr.JETON_ACCES
        assert rr.JETON_ACCES in corps
        code, entetes, _ = _lire(cible.url + "/app")  # sans cookie : vers la mire
        assert code == 302 and entetes["Location"] == "/login"


def test_la_cible_change_d_un_tour_a_l_autre() -> None:
    with rr.servir("deux-tours") as cible:
        un = json.loads(_lire(cible.url + "/api/constats")[2])
        assert cible.tour_suivant() == 2
        deux = json.loads(_lire(cible.url + "/api/constats")[2])
    assert [c["id"] for c in un["constats"]] == ["XSS-001", "CSP-002"]
    assert [c["id"] for c in deux["constats"]] == ["XSS-001", "CSP-002", "COOKIE-003"]
    assert (un["tour"], deux["tour"]) == (1, 2)


def test_un_scenario_inconnu_est_refuse() -> None:
    with pytest.raises(ValueError, match="scénario inconnu"), rr.servir("idéal"):
        pass


# --- La règle : rejouer deux fois --------------------------------------------------------------
def _ingestion(cible: rr.Cible, identifiant):  # noqa: ANN001, ANN202
    def ingerer() -> list[dict]:
        corps = json.loads(_lire(cible.url + "/api/constats")[2])
        return [{**c, "id": identifiant(c)} for c in corps["constats"]]
    return ingerer


def test_une_ingestion_idempotente_passe_les_deux_passages() -> None:
    with rr.servir("deux-tours") as cible:
        defauts = rr.rejouer_deux_fois(_ingestion(cible, lambda c: c["id"]))
    assert defauts == {"doublons": [], "recrees": [], "modifies": []}


def test_rouge_l_ingestion_du_lot_recree_ses_constats_a_chaque_passage() -> None:
    """Le défaut du lot : l'identifiant est tiré à chaque passage, pas celui de la source."""
    compteur = iter(range(1000))
    with rr.servir("deux-tours") as cible:
        defauts = rr.rejouer_deux_fois(_ingestion(cible, lambda c: f"{c['id']}-{next(compteur)}"))
    assert len(defauts["recrees"]) == 4  # 2 constats x 2 passages : aucun retrouvé
    assert defauts["doublons"] == [] and defauts["modifies"] == []


def test_rouge_un_doublon_et_un_contenu_qui_change_sont_nommes() -> None:
    etat = {"n": 0}

    def ingerer() -> list[dict]:
        etat["n"] += 1
        return [{"id": "A", "v": etat["n"]}, {"id": "A", "v": etat["n"]}]

    defauts = rr.rejouer_deux_fois(ingerer)
    assert defauts["doublons"] == ["A"] and defauts["modifies"] == ["A"]


# --- Les jetons à masquer ------------------------------------------------------------------------
def test_les_jetons_visibles_sont_releves_dans_un_texte_publie() -> None:
    assert rr.jetons_visibles(f"preuve : Location: /app?token={rr.JETON_ACCES}") == [rr.JETON_ACCES]
    assert rr.jetons_visibles("preuve : Location: /app?token=***") == []


# --- Cette forge, jouée sur le jeu ---------------------------------------------------------------
@pytest.mark.parametrize("avec_cookie", [False, True])
def test_le_jeu_des_parcours_suit_les_302_sans_publier_le_jeton(avec_cookie: bool) -> None:
    with rr.servir("acces-302-cookie") as cible:
        issues = [personas._jouer_route(cible.url, route, _etat_avec_cookie(avec_cookie))
                  for route in ("/", "/app")]
    for issue, detail in issues:
        assert rr.jetons_visibles(f"{issue} {detail}") == [], (issue, detail)
    if avec_cookie:
        assert issues[1] == ("ok", "200")
    else:
        # sans le cookie, /app renvoie vers la mire : dit comme tel, sans le jeton de la requête
        assert issues[1][0] == "mire" and "/login" in issues[1][1]


def test_deux_passages_du_jeu_rendent_le_meme_releve() -> None:
    with rr.servir("acces-302-cookie") as cible:
        passages = [
            [personas._jouer_route(cible.url, r, _etat_avec_cookie(True)) for r in ("/app", "/")]
            for _ in range(2)
        ]
    assert passages[0] == passages[1]


# --- La reprise ingère un rapport : deux fois, rien de recréé ------------------------------------
def test_la_reprise_rejouee_deux_fois_ne_recree_aucun_constat() -> None:
    from forge_tests import reprise

    constat = {"id": "route-en-defaut:/aide", "pan": "front", "classe": "route-en-defaut",
               "localisation": "/aide", "message": "m", "severite": "bloquant"}
    ancien = {"adaptateurs": [{"nom": "front", "pan": "front", "verdict": "FAIL"}],
              "findings": [constat], "couverture_par_pan": {}, "non_juge": []}
    nouveau = {"adaptateurs": [{"nom": "front", "pan": "front", "verdict": "FAIL"}],
               "findings": [constat], "couverture_par_pan": {}, "non_juge": []}

    def ingerer() -> list[dict]:
        fusion = reprise.fusionner(ancien, nouveau, "rapport.json", ["front"], ["front"])
        return [{"id": f"{f.get('pan')}/{f['id']}", **f} for f in fusion["findings"]]

    assert rr.rejouer_deux_fois(ingerer) == {"doublons": [], "recrees": [], "modifies": []}


def test_la_regle_est_ecrite_au_guide_de_la_forge() -> None:
    from pathlib import Path

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "rejouer_deux_fois" in readme and "servir(\"acces-302-cookie\")" in readme
