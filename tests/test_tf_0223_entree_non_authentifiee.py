"""TF-0223 (RT-7, lot COMPTA 20260814b) — le pan auditait l intérieur, jamais la PORTE D ENTRÉE.

Fait mesuré en production le 14/08, sur l instance du produit `Ventilation de facture Fournisseur-A` :

    GET /  ->  303  /.auth/login/aad  ->  404 {"detail":"Not Found"}

Easy Auth n avait jamais été activée : le login était mort **depuis le premier déploiement**.
Aucun test ne l a vu — le pan `qualif` parcourt l instance AUTHENTIFIÉ, et le smoke du pipeline
n interroge que `/health`, qui est public. C est un humain qui l a découvert en cliquant, quelques
minutes après un run conclu « boucle close, pans au vert ».

Le contrôle ajouté joue la chaîne de redirections depuis la racine **sans session**, et exige
qu elle aboutisse à une **mire identifiable** : une réponse 2xx portant un marqueur de contenu
(marqueur déclaré pour la route d arrivée, sinon champ de mot de passe, sinon titre non vide).

Les deux sens sont prouvés, parce que la sur-correction coûterait autant que le défaut :
  - une chaîne qui n aboutit pas (statut non 2xx, ou 2xx sans marqueur) → finding
    `chaine-authentification-en-impasse` ;
  - une instance PUBLIQUE (aucun saut d authentification dans la chaîne) → rien à vérifier,
    et le pan n invente rien ;
  - une chaîne qui aboutit à un 200 marqué → SAINE, **y compris** quand elle traverse un IdP
    externe : ce qui est jugé est le point d arrivée, jamais l itinéraire ;
  - une ignorance (navigation impossible, relevé absent) → aucun constat, une déclaration ;
  - le constat SURVIT à la garde de précondition de TF-0211 : un pan aveugle au contenu
    authentifié doit quand même pouvoir dire « et en plus, votre porte d entrée est murée ».
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest

from forge_tests.adaptateurs import qualif

BASE = "https://compta-fournisseur-a.exemple.test"

# La chaîne EXACTE relevée en production le 14/08.
_IMPASSE_PRODUCTION = {
    "chaine": [
        {"url": f"{BASE}/", "statut": 303},
        {"url": f"{BASE}/.auth/login/aad", "statut": 404},
    ],
    "corps": '{"detail":"Not Found"}',
    "titre": "",
    "erreur": None,
}


def _entree(chaine: list[dict], *, corps: str = "", titre: str = "", erreur: str | None = None):
    return {"chaine": list(chaine), "corps": corps, "titre": titre, "erreur": erreur}


def _config(**surcharges) -> dict:
    return {"base": BASE, "marqueurs": {}, **surcharges}


def _page_saine(route: str) -> dict:
    return {
        "route": route,
        "statut": 200,
        "problemes": [],
        "affordances": [],
        "corps": f"<h1>{route}</h1>",
        "console": [],
    }


def _page_refusee(route: str) -> dict:
    """Une route telle que le produit la rendait sans session : la mire, et le refus en console."""
    return {
        "route": route,
        "statut": 401,
        "problemes": ["route atteignable par un lien mais HTTP 401"],
        "affordances": [],
        "corps": "<h1>Connexion</h1>",
        "console": [
            "Failed to load resource: the server responded with a status of 401 (UNAUTHORIZED)"
        ],
    }


# --- 1. Le défaut payé en production, et sa contrepartie saine ---------------------------------
def test_la_chaine_de_production_en_impasse_est_DENONCEE(tmp_path: Path) -> None:
    """Le cas exact : 303 vers `/.auth/login/aad`, puis 404 JSON. Personne ne le voyait."""
    sortie = qualif.conclure(
        tmp_path, _config(), [_page_saine("/"), _page_saine("/factures")], [], _IMPASSE_PRODUCTION
    )

    constats = [f for f in sortie.findings if f.classe == qualif.CLASSE_ENTREE]
    assert len(constats) == 1, [f.classe for f in sortie.findings]
    constat = constats[0]
    assert constat.id == qualif.IDENT_ENTREE
    assert constat.severite == "bloquant"
    assert sortie.verdict == "FAIL"
    # Le message porte la CHAÎNE, pas seulement un verdict : c est ce qui rend le constat
    # reproductible par l humain qui le lit.
    assert "/.auth/login/aad" in constat.message and "404" in constat.message


def test_la_meme_chaine_qui_ABOUTIT_est_saine(tmp_path: Path) -> None:
    """Sens vert : Easy Auth activée. Le trajet est identique, l arrivée ne l est pas."""
    entree = _entree(
        [
            {"url": f"{BASE}/", "statut": 302},
            {"url": f"{BASE}/.auth/login/aad", "statut": 302},
            {"url": "https://login.microsoftonline.com/x/oauth2/v2.0/authorize", "statut": 200},
        ],
        corps="<h1>Connectez-vous</h1><form><input type=password></form>",
        titre="Connectez-vous",
    )

    sortie = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], entree)

    assert [f for f in sortie.findings if f.classe == qualif.CLASSE_ENTREE] == []
    assert sortie.verdict == "PASS"
    assert any("mire IDENTIFIABLE" in ligne for ligne in sortie.non_juge)


def test_un_itineraire_par_un_IdP_EXTERNE_n_est_pas_un_defaut() -> None:
    """Traverser `login.microsoftonline.com` est le fonctionnement NORMAL d Entra.

    Ce qui est jugé est le point d ARRIVÉE. Juger l itinéraire ferait de toute fédération
    d identité un défaut, c est-à-dire rendrait le contrôle inutilisable là où il sert le plus.
    """
    entree = _entree(
        [
            {"url": f"{BASE}/", "statut": 302},
            {"url": "https://login.microsoftonline.com/x/oauth2/v2.0/authorize", "statut": 200},
        ],
        titre="Sign in to your account",
    )
    assert qualif.diagnostiquer_entree(entree, _config()) is None


# --- 2. L autre sens : une instance publique n est JAMAIS accusée ------------------------------
def test_un_site_PUBLIC_sans_authentification_n_est_pas_juge(tmp_path: Path) -> None:
    """Pas de saut d authentification dans la chaîne = pas de porte = rien à vérifier."""
    entree = _entree(
        [{"url": f"{BASE}/", "statut": 200}], corps="<h1>Accueil</h1>", titre="Accueil"
    )

    sortie = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], entree)

    assert sortie.findings == []
    assert any("instance publique" in ligne for ligne in sortie.non_juge)


def test_un_site_public_EN_PANNE_n_est_pas_une_impasse_d_authentification() -> None:
    """Sur-correction interdite : une racine en 500 est un défaut de route, déjà constaté par le
    parcours ordinaire. La requalifier en « porte murée » ferait deux constats d un seul fait, et
    enverrait la correction au mauvais endroit."""
    entree = _entree([{"url": f"{BASE}/", "statut": 500}], corps="Internal Server Error")
    assert qualif.diagnostiquer_entree(entree, _config()) is None


def test_une_redirection_INTERNE_sans_authentification_ne_declenche_rien() -> None:
    """`/` -> `/accueil` : une redirection n est pas une authentification."""
    entree = _entree(
        [{"url": f"{BASE}/", "statut": 302}, {"url": f"{BASE}/accueil", "statut": 200}],
        titre="Accueil",
    )
    assert qualif.diagnostiquer_entree(entree, _config()) is None


# --- 3. Le critère de « mire identifiable », pièce par pièce -----------------------------------
def test_un_200_SANS_marqueur_de_contenu_est_une_impasse() -> None:
    """Le piège que le seul code HTTP ne voit pas : la page répond, et n affiche rien."""
    entree = _entree(
        [{"url": f"{BASE}/", "statut": 302}, {"url": f"{BASE}/login", "statut": 200}],
        corps="<html><body></body></html>",
        titre="",
    )
    motif = qualif.diagnostiquer_entree(entree, _config())
    assert motif is not None and "SANS marqueur" in motif


def test_un_champ_de_mot_de_passe_suffit_a_identifier_la_mire() -> None:
    """Une mire sans titre reste une mire : le formulaire l atteste."""
    entree = _entree(
        [{"url": f"{BASE}/", "statut": 302}, {"url": f"{BASE}/login", "statut": 200}],
        corps='<form method=post><input name=u><input type="password" name=p></form>',
        titre="",
    )
    assert qualif.diagnostiquer_entree(entree, _config()) is None


def test_le_marqueur_DECLARE_pour_la_route_d_arrivee_prime_sur_le_titre() -> None:
    """Un marqueur déclaré est ATTENDU ; un titre est seulement CONSTATÉ. La page qui rend un
    titre quelconque à la place de la mire attendue n a pas abouti."""
    config = _config(marqueurs={"/login": "Connexion à Ventilation Fournisseur-A"})
    chaine = [{"url": f"{BASE}/", "statut": 302}, {"url": f"{BASE}/login", "statut": 200}]

    absent = _entree(chaine, corps="<h1>Service indisponible</h1>", titre="Service indisponible")
    present = _entree(
        chaine, corps="<h1>Connexion à Ventilation Fournisseur-A</h1>", titre="Connexion à Ventilation Fournisseur-A"
    )

    assert qualif.diagnostiquer_entree(absent, config) is not None
    assert qualif.diagnostiquer_entree(present, config) is None


@pytest.mark.parametrize(
    ("libelle", "url", "attendu"),
    [
        ("l endpoint plateforme Azure", f"{BASE}/.auth/login/aad", True),
        ("une mire applicative", f"{BASE}/login", True),
        ("la même, en français", f"{BASE}/connexion", True),
        ("l autorisation OAuth", f"{BASE}/oauth2/authorize", True),
        ("l IdP Microsoft", "https://login.microsoftonline.com/x/oauth2/v2.0/authorize", True),
        ("un IdP Okta", "https://acme.okta.com/app/x", True),
        ("la racine", f"{BASE}/", False),
        ("une page métier", f"{BASE}/factures/2026", False),
        # Piège de sous-chaîne : « login » dans un mot n est pas un chemin d authentification.
        ("un segment qui CONTIENT login sans l être", f"{BASE}/loginfo", False),
        ("une page publique qui parle de connexion", f"{BASE}/aide/se-connecter", False),
        ("une URL vide", "", False),
    ],
)
def test_est_saut_auth(libelle: str, url: str, attendu: bool) -> None:
    assert qualif._est_saut_auth(url) is attendu, libelle


# --- 4. Une ignorance n accuse jamais ----------------------------------------------------------
def test_une_navigation_IMPOSSIBLE_ne_produit_aucun_constat(tmp_path: Path) -> None:
    entree = _entree([], erreur="TimeoutError: navigation timeout")

    sortie = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], entree)

    assert sortie.findings == []
    assert any("non concluant" in ligne for ligne in sortie.non_juge)
    # Et l élément n entre PAS à l inventaire : non mesuré n est pas mesuré vert.
    assert qualif.IDENT_ENTREE not in (sortie.surface or {}).get("elements_exerces", [])


def test_un_releve_ABSENT_est_declare_et_non_devine(tmp_path: Path) -> None:
    """Le pan appelé sans parcours d entrée le DIT : un contrôle muet est indiscernable d un
    contrôle qui n a pas tourné, et c est ce silence qui a coûté le login de production."""
    sortie = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], None)

    assert sortie.findings == []
    assert any("parcours d ENTREE non joue" in ligne for ligne in sortie.non_juge)


# --- 5. Le contrôle SURVIT à la garde de précondition (TF-0211) --------------------------------
def test_le_constat_d_entree_survit_a_la_garde_de_precondition(tmp_path: Path) -> None:
    """Le point de méthode du lot : la garde fait taire le pan quand TOUTES les routes échouent
    en 401 — exactement la situation d une instance protégée. Si le parcours d entrée y était
    soumis, on reconstruirait un étage plus bas le silence que la garde vient de corriger."""
    releve = [_page_refusee("/"), _page_refusee("/factures"), _page_refusee("/rapports")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [], _IMPASSE_PRODUCTION)

    # Le pan reste MUET sur le contenu authentifié : c est le contrat de TF-0211.
    assert sortie.verdict == "SKIP"
    assert sortie.surface is None
    assert any("PRECONDITION NON ETABLIE" in ligne for ligne in sortie.non_juge)
    assert {nt.element for nt in sortie.non_testables} == {
        "qualif:route:/", "qualif:route:/factures", "qualif:route:/rapports"
    }
    # …et il dit quand même que la porte est murée. UN seul constat, et c est celui-là.
    assert [f.id for f in sortie.findings] == [qualif.IDENT_ENTREE]
    assert sortie.findings[0].classe == qualif.CLASSE_ENTREE


def test_sous_la_garde_une_entree_SAINE_ne_fabrique_aucun_constat(tmp_path: Path) -> None:
    """Contrepartie : la survie du contrôle n est pas une brèche dans la garde. Le pan aveugle
    qui a une porte d entrée saine reste exactement aussi muet qu avant TF-0223."""
    entree = _entree(
        [{"url": f"{BASE}/", "statut": 302}, {"url": f"{BASE}/login", "statut": 200}],
        corps="<h1>Connexion</h1><input type=password>",
        titre="Connexion",
    )
    releve = [_page_refusee("/"), _page_refusee("/factures")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [], entree)

    assert (sortie.verdict, sortie.findings) == ("SKIP", [])


# --- 6. Le contrôle tourne SANS session — c est son intérêt ------------------------------------
def test_le_controle_tourne_quand_AUCUNE_session_n_est_fournie(tmp_path: Path) -> None:
    """Ni compte, ni session capturée : le pan ne peut rien voir de l intérieur, et voit tout de
    la porte. C est la configuration exacte du run qui n a rien détecté."""
    config = _config(login="", mdp="", storage_state="", bearer="")

    sortie = qualif.conclure(tmp_path, config, [_page_saine("/")], [], _IMPASSE_PRODUCTION)

    assert qualif.CLASSE_ENTREE in [f.classe for f in sortie.findings]
    assert any("AUCUNE session" in ligne for ligne in sortie.non_juge)


def test_le_controle_tourne_AUSSI_sous_session_fournie(tmp_path: Path) -> None:
    """Le parcours d entrée ne dépend pas de la session : il est joué dans un contexte vierge."""
    config = _config(storage_state="C:/secrets/storageState.json")

    sortie = qualif.conclure(tmp_path, config, [_page_saine("/")], [], _IMPASSE_PRODUCTION)

    assert qualif.CLASSE_ENTREE in [f.classe for f in sortie.findings]


# --- 7. Surface : la porte d entrée est un élément inventorié ----------------------------------
def test_la_porte_d_entree_entre_a_l_inventaire_dans_les_deux_sens(tmp_path: Path) -> None:
    saine = _entree(
        [{"url": f"{BASE}/", "statut": 302}, {"url": f"{BASE}/login", "statut": 200}],
        corps="<h1>Connexion</h1>", titre="Connexion",
    )

    verte = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], saine)
    rouge = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], _IMPASSE_PRODUCTION)

    assert qualif.IDENT_ENTREE in verte.surface["elements_exerces"]
    assert qualif.IDENT_ENTREE in rouge.surface["elements_non_exerces"]
    assert verte.surface["inventorie"] == rouge.surface["inventorie"]


# --- 8. Ce qui est publié ne porte pas de fragment de session ----------------------------------
def test_les_parametres_de_l_IdP_ne_sont_JAMAIS_recopies_au_rapport(tmp_path: Path) -> None:
    """`code`, `state`, `nonce` sont des fragments de session. Les recopier au rapport publierait
    ce que le garde-fou anti-fuite existe pour retenir."""
    entree = _entree(
        [
            {"url": f"{BASE}/", "statut": 302},
            {
                "url": "https://login.microsoftonline.com/x/oauth2/authorize"
                       "?state=SECRET-ETAT-42&code=SECRET-CODE-42",
                "statut": 404,
            },
        ],
        corps="Not Found",
    )

    sortie = qualif.conclure(tmp_path, _config(), [_page_saine("/")], [], entree)

    publie = " ".join([f.message for f in sortie.findings] + list(sortie.non_juge))
    assert "SECRET-ETAT-42" not in publie and "SECRET-CODE-42" not in publie
    assert "login.microsoftonline.com/x/oauth2/authorize" in publie


# --- 9. Le relevé lui-même : chaîne reconstruite, contexte VIERGE ------------------------------
class _FausseReponse:
    def __init__(self, requete: _FausseRequete) -> None:
        self.request = requete
        self.status = requete.statut


class _FausseRequete:
    """Le modèle Playwright : chaque requête pointe vers celle qui l a redirigée."""

    def __init__(self, url: str, statut: int, precedente: _FausseRequete | None = None) -> None:
        self.url, self.statut, self.redirected_from = url, statut, precedente

    def response(self) -> _FausseReponse:
        return _FausseReponse(self)


class _FaussePage:
    def __init__(self, chaine: list[tuple[str, int]], corps: str, titre: str) -> None:
        self._chaine, self._corps, self._titre = chaine, corps, titre
        self.visitees: list[str] = []

    def goto(self, url: str, **_kw: object) -> _FausseReponse:
        self.visitees.append(url)
        precedente = None
        for adresse, statut in self._chaine:
            precedente = _FausseRequete(adresse, statut, precedente)
        return _FausseReponse(precedente)

    def evaluate(self, _js: str) -> str:
        return self._titre

    def content(self) -> str:
        return self._corps


class _FauxContexte:
    def __init__(self, options: dict, page: _FaussePage) -> None:
        self.options, self._page, self.ferme = options, page, False

    def new_page(self) -> _FaussePage:
        return self._page

    def close(self) -> None:
        self.ferme = True


class _FauxNavigateur:
    def __init__(self, page: _FaussePage) -> None:
        self._page, self.contextes = page, []

    def new_context(self, **options: object) -> _FauxContexte:
        contexte = _FauxContexte(dict(options), self._page)
        self.contextes.append(contexte)
        return contexte


def test_le_releve_reconstruit_la_chaine_DANS_L_ORDRE() -> None:
    page = _FaussePage(
        [(f"{BASE}/", 303), (f"{BASE}/.auth/login/aad", 404)], '{"detail":"Not Found"}', ""
    )
    navigateur = _FauxNavigateur(page)

    entree = qualif._relever_entree(navigateur, {"base": BASE})

    assert [(m["url"], m["statut"]) for m in entree["chaine"]] == [
        (f"{BASE}/", 303),
        (f"{BASE}/.auth/login/aad", 404),
    ]
    assert entree["erreur"] is None
    assert qualif.diagnostiquer_entree(entree, _config()) is not None


def test_le_releve_se_joue_dans_un_contexte_VIERGE_et_le_referme() -> None:
    """Le point qui fait tout le contrôle : aucune session n est chargée dans ce contexte. Le
    rejouer dans le contexte authentifié mesurerait ce que voit quelqu un qui est DÉJÀ entré —
    précisément la mesure qui n a rien vu pendant six mois."""
    navigateur = _FauxNavigateur(_FaussePage([(f"{BASE}/", 200)], "<h1>Accueil</h1>", "Accueil"))

    qualif._relever_entree(navigateur, {"base": BASE})

    assert len(navigateur.contextes) == 1
    assert navigateur.contextes[0].options == {}
    assert navigateur.contextes[0].ferme is True


def test_le_releve_part_bien_de_la_RACINE() -> None:
    page = _FaussePage([(f"{BASE}/", 200)], "<h1>Accueil</h1>", "Accueil")

    qualif._relever_entree(_FauxNavigateur(page), {"base": BASE})

    assert [urlparse(url).path for url in page.visitees] == ["/"]


def test_un_releve_qui_echoue_se_DECLARE_au_lieu_de_lever() -> None:
    class _PageQuiEchoue(_FaussePage):
        def goto(self, url: str, **_kw: object):
            raise TimeoutError("navigation timeout de 45000 ms depasse")

    entree = qualif._relever_entree(
        _FauxNavigateur(_PageQuiEchoue([], "", "")), {"base": BASE}
    )

    assert entree["erreur"] is not None and "TimeoutError" in entree["erreur"]
    assert qualif.diagnostiquer_entree(entree, _config()) is None
