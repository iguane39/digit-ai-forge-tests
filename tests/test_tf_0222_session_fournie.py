"""TF-0222 (RT-6, lot COMPTA 20260814b) — une instance derrière un IdP d entreprise, INAUDITABLE.

Le pan `qualif` ne savait s authentifier que d une seule façon : remplir une mire formulaire
(`FORGE_TESTS_QUALIF_LOGIN` / `_PASSWORD`, routes `/login` | `/connexion`). Aucune forge ne
rejoue un second facteur ni un accès conditionnel : toute instance derrière Easy Auth Entra
(MFA, CA) lui était fermée — or c est exactement là que vivent les défauts de frontière, et le
produit `Ventilation de facture SFR` venait de choisir ses tests Azure par **session capturée**
(storage state Playwright, cookie `AppServiceAuthSession`), l artefact que la forge ne savait
pas consommer.

Le pan accepte désormais une session ouverte AILLEURS, et les garde-fous qui vont avec :

  - `FORGE_TESTS_QUALIF_STORAGE_STATE` chargé dans le contexte Playwright, `_BEARER` posé en
    en-tête `Authorization` ;
  - la **provenance** de la session est publiée au rapport — un audit mené sous session capturée
    hérite des droits de l opérateur qui l a capturée, il ne se confond pas avec un audit qui
    s est authentifié lui-même ;
  - une session capturée **périme** : quand elle n ouvre plus rien, le pan le DIT (motif de
    péremption, champs à renouveler) au lieu de mesurer une redirection en croyant mesurer un
    produit ;
  - ni le jeton, ni le chemin complet du storage state ne sont publiés : le rapport circule.

Le dernier test du fichier ne valide rien — il CONSTATE un écart du garde-fou anti-fuite de
`jeux.py`, hors périmètre de ce mandat, pour qu il cesse d être invisible.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from urllib.parse import urlparse

import pytest

from forge_tests.adaptateurs import qualif

BASE = "https://compta-sfr.exemple.test"
_JETON = "eyJhbGciOiJIUzI1NiJ9.CE-JETON-NE-DOIT-JAMAIS-PARAITRE"


@pytest.fixture()
def env_propre():
    """`charger_env` écrit dans `os.environ` sans le rendre : on le restaure intégralement."""
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _storage_state(tmp_path: Path, nom: str = "storageState.json") -> Path:
    """L artefact réel : celui que `playwright codegen --save-storage` dépose."""
    fichier = tmp_path / nom
    fichier.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "AppServiceAuthSession",
                        "value": "COOKIE-DE-SESSION-CAPTUREE",
                        "domain": "compta-sfr.exemple.test",
                        "path": "/",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    return fichier


def _config(**surcharges) -> dict:
    return {"base": BASE, "marqueurs": {}, **surcharges}


def _page_refusee(route: str) -> dict:
    return {
        "route": route,
        "statut": 401,
        "problemes": ["route atteignable par un lien mais HTTP 401"],
        "affordances": [],
        "corps": "<h1>Connexion</h1>",
        "console": [],
    }


# --- 1. La session fournie atteint vraiment le navigateur --------------------------------------
def test_un_storage_state_valide_est_charge_dans_le_contexte(tmp_path: Path) -> None:
    fichier = _storage_state(tmp_path)
    config = _config(storage_state=str(fichier))

    options, alertes = qualif._options_contexte(config)

    assert options == {"storage_state": str(fichier)}
    assert alertes == []
    assert qualif.session_fournie(config) is True


def test_un_storage_state_INTROUVABLE_est_ecarte_et_DECLARE(tmp_path: Path) -> None:
    """Sens rouge : un audit qui se croit authentifié est plus dangereux qu un audit anonyme —
    il attribuerait au produit tout ce que l absence de session lui cache."""
    config = _config(storage_state=str(tmp_path / "jamais-capture.json"))

    options, alertes = qualif._options_contexte(config)

    assert options == {}
    assert len(alertes) == 1 and "introuvable" in alertes[0]
    # La configuration est CORRIGÉE : la provenance publiée ensuite ne peut plus mentir.
    assert config["storage_state"] == ""
    assert "AUCUNE session" in qualif.provenance_session(config)


def test_un_storage_state_ILLISIBLE_est_ecarte_et_DECLARE(tmp_path: Path) -> None:
    fichier = tmp_path / "storageState.json"
    fichier.write_text("{ceci n est pas du JSON", encoding="utf-8")

    options, alertes = qualif._options_contexte(_config(storage_state=str(fichier)))

    assert options == {}
    assert len(alertes) == 1 and "illisible" in alertes[0]


@pytest.mark.parametrize(
    ("libelle", "fourni", "attendu"),
    [
        ("un jeton nu est un jeton Bearer — le cas courant", "abc.def.ghi", "Bearer abc.def.ghi"),
        ("un en-tête déjà complet n est pas préfixé deux fois", "Bearer abc", "Bearer abc"),
        ("la casse du schéma ne change rien", "bearer abc", "bearer abc"),
        ("un autre schéma est respecté tel quel", "Basic dXNlcjptZHA=", "Basic dXNlcjptZHA="),
    ],
)
def test_entete_autorisation(libelle: str, fourni: str, attendu: str) -> None:
    assert qualif._entete_autorisation(fourni) == attendu, libelle


# --- 2. La PROVENANCE de la session est publiée au rapport --------------------------------------
def test_la_provenance_distingue_les_trois_facons_d_entrer(tmp_path: Path) -> None:
    """Trois audits, trois identités, trois phrases. Lire un rapport sans savoir laquelle on
    tient, c est ignorer ce que « exercé » veut dire dedans."""
    capturee = qualif.provenance_session(_config(storage_state="C:/x/storageState.json"))
    propre = qualif.provenance_session(_config(login="audit-2026", mdp="motdepasse"))
    anonyme = qualif.provenance_session(_config())

    assert "CAPTUREE" in capturee and "PERIME" in capturee
    assert "PAR LA FORGE" in propre and "FORGE_TESTS_QUALIF_LOGIN" in propre
    assert "AUCUNE session" in anonyme
    assert len({capturee, propre, anonyme}) == 3


def test_la_provenance_est_publiee_a_CHAQUE_rapport(tmp_path: Path) -> None:
    releve = [
        {"route": "/", "statut": 200, "problemes": [], "affordances": [],
         "corps": "<h1>Tableau de bord</h1>", "console": []}
    ]
    config = _config(storage_state="C:/secrets/storageState.json", bearer=_JETON)

    sortie = qualif.conclure(tmp_path, config, releve, [])

    provenances = [ligne for ligne in sortie.non_juge if "PROVENANCE DE SESSION" in ligne]
    assert len(provenances) == 1
    assert "storageState.json" in provenances[0]
    assert "en-tete Authorization" in provenances[0]


def test_ni_le_jeton_ni_le_chemin_complet_ne_sont_PUBLIES(tmp_path: Path) -> None:
    """Le rapport circule : il nomme la NATURE de la session et le NOM du fichier, jamais la
    valeur qui permettrait de rejouer l identité."""
    config = _config(storage_state="C:/Users/operateur/secrets/storageState.json", bearer=_JETON)

    ligne = qualif.provenance_session(config)

    assert _JETON not in ligne
    assert "C:/Users/operateur/secrets" not in ligne
    assert "storageState.json" in ligne


def test_la_provenance_dit_que_la_mire_n_est_PAS_rejouee_quand_les_deux_sont_fournis() -> None:
    config = _config(storage_state="C:/x/etat.json", login="audit-2026", mdp="motdepasse")
    assert "PAS ete rejouee" in qualif.provenance_session(config)


# --- 3. Une session capturée PÉRIME — détecté, pas seulement déclaré ---------------------------
def test_une_session_fournie_qui_n_ouvre_RIEN_est_declaree_PERIMEE(tmp_path: Path) -> None:
    """Le cas qui rendrait un audit entier faux sans qu il le dise : la session a expiré, le pan
    photographie une redirection et croit mesurer un produit."""
    releve = [_page_refusee("/"), _page_refusee("/factures")]
    config = _config(storage_state="C:/x/storageState.json")

    sortie = qualif.conclure(tmp_path, config, releve, [])

    assert sortie.verdict == "SKIP"
    motif = sortie.non_juge[-1]
    assert "PERIME" in motif
    assert "FORGE_TESTS_QUALIF_STORAGE_STATE" in motif
    # Le geste de réparation n est pas « fournir un compte » : c est RECAPTURER la session.
    assert all(
        nt.champs_requis == list(qualif.CHAMPS_REQUIS_SESSION_FOURNIE)
        for nt in sortie.non_testables
    )


def test_sans_session_fournie_le_motif_reclame_toujours_un_COMPTE(tmp_path: Path) -> None:
    """Non-régression de TF-0211 : le message d origine ne bouge pas quand rien n a été fourni."""
    releve = [_page_refusee("/"), _page_refusee("/factures")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    motif = sortie.non_juge[-1]
    assert "PERIME" not in motif
    assert "FORGE_TESTS_QUALIF_LOGIN" in motif
    assert all(
        nt.champs_requis == list(qualif.CHAMPS_REQUIS_SESSION) for nt in sortie.non_testables
    )


# --- 4. Les champs revendiqués par le pan -------------------------------------------------------
def test_les_champs_de_session_fournie_sont_REVENDIQUES_par_le_pan() -> None:
    """RT-13 : sans revendication, ces deux champs seraient réclamés à tous les pans du domaine
    « acces » — y compris à ceux qu aucune session ne débloquerait."""
    from forge_tests.adaptateurs import REGISTRE
    from forge_tests.qualification import proprietaires

    assert set(qualif.CHAMPS_REQUIS) >= {
        "FORGE_TESTS_QUALIF_URL",
        "FORGE_TESTS_QUALIF_STORAGE_STATE",
        "FORGE_TESTS_QUALIF_BEARER",
    }
    carte = proprietaires(REGISTRE)
    assert carte["FORGE_TESTS_QUALIF_STORAGE_STATE"] == {"qualif"}
    assert carte["FORGE_TESTS_QUALIF_BEARER"] == {"qualif"}


def test_une_instance_non_declaree_ne_reclame_QUE_son_URL(tmp_path: Path, env_propre) -> None:
    """Sur-correction interdite : réclamer une session à qui n a pas encore déclaré d instance
    ferait demander trois gestes là où un seul débloque."""
    from forge_tests import qualification

    qualification.oublier(tmp_path)
    sortie = qualif.analyser(tmp_path)
    requis = set(qualification.requis(tmp_path, "acces"))
    qualification.oublier(tmp_path)

    assert sortie.verdict == "SKIP"
    assert requis == {"FORGE_TESTS_QUALIF_URL"}


# --- 5. Bout en bout : le navigateur réellement piloté ------------------------------------------
class _FausseReponse:
    def __init__(self, requete: _FausseRequete) -> None:
        self.request, self.status = requete, requete.statut


class _FausseRequete:
    def __init__(self, url: str, statut: int, precedente: _FausseRequete | None) -> None:
        self.url, self.statut, self.redirected_from = url, statut, precedente

    def response(self) -> _FausseReponse:
        return _FausseReponse(self)


class _FaussePage:
    """Une instance derrière Easy Auth : 200 avec la session capturée, chaîne morte sans elle.

    C est le produit réel du 14/08 — Easy Auth jamais activée : `/` répond 303 vers
    `/.auth/login/aad`, qui rend un 404 JSON.
    """

    def __init__(self, contexte: _FauxContexte) -> None:
        self.contexte, self.visitees = contexte, []
        self._corps, self._titre = "", ""

    @property
    def context(self) -> _FauxContexte:
        return self.contexte

    def on(self, *_args: object) -> None:
        return None

    def wait_for_load_state(self, *_args: object) -> None:
        return None

    def query_selector(self, selecteur: str):
        self.contexte.navigateur.selecteurs.append(selecteur)
        return None

    def goto(self, url: str, **_kw: object) -> _FausseReponse:
        chemin = urlparse(url).path or "/"
        self.visitees.append(chemin)
        if self.contexte.a_session:
            self._corps, self._titre = "<h1>Tableau de bord</h1>", "Tableau de bord"
            return _FausseReponse(_FausseRequete(url, 200, None))
        self._corps, self._titre = '{"detail":"Not Found"}', ""
        depart = _FausseRequete(f"{BASE}{chemin}", 303, None)
        return _FausseReponse(_FausseRequete(f"{BASE}/.auth/login/aad", 404, depart))

    def evaluate(self, script: str):
        if script is qualif._JS_TITRE:
            return self._titre
        return []

    def content(self) -> str:
        return self._corps


class _FauxContexte:
    def __init__(self, navigateur: _FauxNavigateur, options: dict) -> None:
        self.navigateur, self.options = navigateur, dict(options)
        self.entetes: dict[str, str] = {}
        self.pages: list[_FaussePage] = []
        self.ferme = False

    @property
    def a_session(self) -> bool:
        return bool(self.options.get("storage_state")) or "Authorization" in self.entetes

    def set_extra_http_headers(self, entetes: dict) -> None:
        self.entetes.update(entetes)

    def new_page(self) -> _FaussePage:
        page = _FaussePage(self)
        self.pages.append(page)
        return page

    def new_cdp_session(self, _page: object) -> None:
        raise RuntimeError("protocole DevTools indisponible sur ce faux navigateur")

    def close(self) -> None:
        self.ferme = True


class _FauxNavigateur:
    def __init__(self) -> None:
        self.contextes: list[_FauxContexte] = []
        self.selecteurs: list[str] = []
        self.ferme = False

    def new_context(self, **options: object) -> _FauxContexte:
        contexte = _FauxContexte(self, options)
        self.contextes.append(contexte)
        return contexte

    def close(self) -> None:
        self.ferme = True


@pytest.fixture()
def navigateur(monkeypatch: pytest.MonkeyPatch) -> _FauxNavigateur:
    """Substitue le module Playwright — c est le PILOTAGE du navigateur qui est en cause ici,
    pas Chromium : les tests de la forge ne dépendent d aucun binaire installé."""
    faux = _FauxNavigateur()

    class _FauxPlaywright:
        chromium = None

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def launch(self, **_kw: object) -> _FauxNavigateur:
            return faux

    instance = _FauxPlaywright()
    instance.chromium = instance
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(sync_playwright=lambda: instance),
    )
    return faux


def test_bout_en_bout_la_session_capturee_ouvre_l_instance_ET_la_porte_reste_jugee(
    tmp_path: Path, env_propre, navigateur: _FauxNavigateur
) -> None:
    """Le cas complet du lot : une instance Easy Auth auditée sous session capturée, dont la
    porte d entrée est morte. Les deux corrections se rencontrent ici."""
    from forge_tests import qualification

    fichier = _storage_state(tmp_path)
    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATE"] = str(fichier)
    qualification.oublier(tmp_path)

    sortie = qualif.analyser(tmp_path)
    qualification.oublier(tmp_path)

    # a) le parcours d ENTRÉE a été joué EN PREMIER, dans un contexte sans session…
    assert len(navigateur.contextes) == 2
    assert navigateur.contextes[0].options == {}
    assert navigateur.contextes[0].ferme is True
    # b) …et le parcours authentifié a bien reçu la session capturée.
    assert navigateur.contextes[1].options == {"storage_state": str(fichier)}
    # c) la porte murée est constatée malgré la session valide.
    assert qualif.CLASSE_ENTREE in [f.classe for f in sortie.findings]
    # d) la provenance est publiée, sans le chemin complet.
    assert any("CAPTUREE" in ligne for ligne in sortie.non_juge)
    assert not any(str(tmp_path) in ligne for ligne in sortie.non_juge)


def test_bout_en_bout_le_bearer_devient_un_en_tete_du_contexte(
    tmp_path: Path, env_propre, navigateur: _FauxNavigateur
) -> None:
    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_BEARER"] = _JETON

    sortie = qualif.analyser(tmp_path)

    assert navigateur.contextes[1].entetes == {"Authorization": f"Bearer {_JETON}"}
    # Le contexte du parcours d entrée, lui, n a JAMAIS reçu l en-tête : c est le contrôle même.
    assert navigateur.contextes[0].entetes == {}
    assert _JETON not in " ".join(sortie.non_juge)


def test_bout_en_bout_la_mire_n_est_PAS_rejouee_sous_session_fournie(
    tmp_path: Path, env_propre, navigateur: _FauxNavigateur
) -> None:
    """Rejouer la mire par-dessus une session confiée écraserait l identité qu on nous a donnée,
    et le rapport annoncerait une provenance qui n est plus la bonne."""
    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATE"] = str(_storage_state(tmp_path))
    os.environ["FORGE_TESTS_QUALIF_LOGIN"] = "audit-2026"
    os.environ["FORGE_TESTS_QUALIF_PASSWORD"] = "motdepasse-audit"

    qualif.analyser(tmp_path)

    visitees = [chemin for page in navigateur.contextes[1].pages for chemin in page.visitees]
    assert "/connexion" not in visitees and "/login" not in visitees
    assert navigateur.selecteurs == []  # aucun champ de mire n a même été cherché


def test_bout_en_bout_SANS_session_la_mire_est_bien_rejouee(
    tmp_path: Path, env_propre, navigateur: _FauxNavigateur
) -> None:
    """Sens rouge du précédent : sans session fournie, le comportement d origine est intact."""
    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_LOGIN"] = "audit-2026"
    os.environ["FORGE_TESTS_QUALIF_PASSWORD"] = "motdepasse-audit"

    qualif.analyser(tmp_path)

    visitees = [chemin for page in navigateur.contextes[1].pages for chemin in page.visitees]
    assert "/connexion" in visitees
    assert navigateur.selecteurs  # la mire a été cherchée dans la page


# --- 6. Garde-fou anti-fuite : le jeton et la session capturee sont retenus ------------------
def test_le_corpus_interdit_retient_le_bearer_et_la_session_capturee(env_propre) -> None:
    """Inverse du test d ECART pose par la campagne TF-0222 — l ecart a ete corrige, pas oublie.

    Ce qu il mesurait : `FORGE_TESTS_QUALIF_BEARER` sortait du corpus interdit (le nom est bien
    authentifiant au sens des SEGMENTS, mais aucun motif ne le reconnaissait) et
    `FORGE_TESTS_QUALIF_STORAGE_STATE` echouait les DEUX conditions. Un jeton d audit pouvait
    donc etre recopie dans un livrable qui circule. `BEARER` est desormais un secret,
    `STORAGE_STATE` une donnee d exploitation, et `STORAGE` un segment authentifiant.
    """
    from forge_tests.livrables.jeux import _valeurs_de_configuration, configure_l_auditeur

    assert configure_l_auditeur("FORGE_TESTS_QUALIF_BEARER") is False
    assert configure_l_auditeur("FORGE_TESTS_QUALIF_STORAGE_STATE") is False

    os.environ["FORGE_TESTS_QUALIF_BEARER"] = _JETON
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATE"] = "C:/secrets/storageState.json"
    interdites = _valeurs_de_configuration(None)

    assert _JETON in interdites
    assert "C:/secrets/storageState.json" in interdites


def test_le_jeton_est_un_SECRET_la_session_capturee_une_donnee_d_exploitation(
    env_propre,
) -> None:
    """La nuance porte une decision : un secret ne sort NULLE PART, une donnee d exploitation
    est seulement interdite dans un jeu de donnees fabrique (elle reste lisible au rapport,
    comme l URL de l instance auditee — la masquer rendrait le constat inintelligible)."""
    from forge_tests.livrables.jeux import _valeurs_de_configuration

    os.environ["FORGE_TESTS_QUALIF_BEARER"] = _JETON
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATE"] = "C:/secrets/storageState.json"
    secrets = _valeurs_de_configuration(None, secrets_seulement=True)

    assert _JETON in secrets
    assert "C:/secrets/storageState.json" not in secrets


def test_la_correction_n_avale_pas_une_variable_produit_voisine(env_propre) -> None:
    """Anti-surcorrection (lecon TF-0215) : `STORAGE_STATE` est cite en PAIRE, jamais `STORAGE`
    seul, sinon le `STORAGE_BUCKET` d un produit entrerait au corpus sans rien authentifier."""
    from forge_tests.livrables.jeux import _NOM_CONFIG, _NOM_SECRET

    assert _NOM_CONFIG.search("STORAGE_BUCKET") is None
    assert _NOM_SECRET.search("STORAGE_STATE") is None  # un chemin n est pas un secret
