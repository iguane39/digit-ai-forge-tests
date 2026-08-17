"""TF-0313 (lot bourse-aux-vacants 20260817a) — la mire d une SPA n existe pas encore quand le
pan la lit, et le pan en concluait qu il n y en avait pas.

`_connecter()` naviguait en `wait_until="domcontentloaded"` puis interrogeait le DOM
IMMÉDIATEMENT. Rejoué à l identique contre l instance servie de BAV2 (React 18 + Ant Design,
`http://localhost:8092/login`) : `input[type=password]` ABSENT, champ identifiant ABSENT, et même
`button` ABSENT — à cet instant le bundle n a rien monté. La boucle épuisait ses candidats et
sortait sur « aucune mire de connexion trouvee (routes essayees : /login) », alors que `/login`
EST la bonne route, qu elle était DÉCLARÉE par `FORGE_TESTS_QUALIF_CONNEXION`, et que le compte
était valide.

Effet mesuré sur le rapport : compte fourni et valide → pan SKIP, **0 élément inventorié**, 6
non_testables ; la MÊME session passée par un autre canal → **91 éléments inventoriés**. Le
correctif attend l APPARITION du champ mot de passe et ne déclare « aucune mire » qu APRÈS
expiration.

Les deux sens sont tenus par les deux fixtures de ce fichier : `_PageSPA(monte=True)` — la mire
existe mais arrive tard, elle DOIT être trouvée ; `_PageSPA(monte=False)` — il n y a vraiment
aucune mire, le pan DOIT le dire, et dire où il s est arrêté.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from urllib.parse import urlparse

import pytest

from forge_tests.adaptateurs import qualif

BASE = "https://bav.exemple.test"


@pytest.fixture()
def env_propre():
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    yield
    os.environ.clear()
    os.environ.update(memoire)


class _Expiration(Exception):
    """Ce que Playwright lève quand un sélecteur n apparaît pas — `TimeoutError` côté réel."""


class _Champ:
    def __init__(self) -> None:
        self.rempli: str | None = None
        self.clics = 0

    def fill(self, valeur: str) -> None:
        self.rempli = valeur

    def click(self) -> None:
        self.clics += 1


class _ContexteCookies:
    def __init__(self) -> None:
        self.biscuits: list[dict] = []

    def cookies(self) -> list[dict]:
        return list(self.biscuits)


class _PageSPA:
    """Une application qui rend en JavaScript : le DOM est VIDE à `domcontentloaded`.

    Les deux lectures du DOM sont distinguées, parce que c est tout l objet de TF-0313 :
      - `query_selector` = l instant du chargement — ne rend JAMAIS rien (React n a pas monté) ;
      - `wait_for_selector` = l attente d apparition — rend le champ si le bundle le monte,
        et expire sinon.

    La soumission reproduit ce que l instance BAV2 fait réellement : deux cookies JWT posés et
    une redirection vers `/trouver-une-annonce`.
    """

    def __init__(self, monte: bool = True) -> None:
        self.monte = monte
        self.visitees: list[str] = []
        self.lus_a_chaud: list[str] = []
        self.attendus: list[str] = []
        self.champs: dict[str, _Champ] = {}
        self.soumise = False
        self.contexte = _ContexteCookies()
        self.url = f"{BASE}/"

    @property
    def context(self) -> _ContexteCookies:
        return self.contexte

    def goto(self, url: str, **_kw: object) -> None:
        self.visitees.append(urlparse(url).path or "/")
        self.url = url

    def query_selector(self, selecteur: str) -> None:
        self.lus_a_chaud.append(selecteur)
        return None

    def wait_for_selector(self, selecteur: str, **_kw: object) -> _Champ:
        self.attendus.append(selecteur)
        if not self.monte:
            raise _Expiration(f"Timeout 10000ms exceeded waiting for {selecteur}")
        return self.champs.setdefault(selecteur, _Champ())

    def wait_for_load_state(self, *_args: object) -> None:
        self.soumise = True
        self.contexte.biscuits.extend(
            [{"name": "access_token_cookie"}, {"name": "refresh_token_cookie"}]
        )
        self.url = f"{BASE}/trouver-une-annonce"


def _config(**surcharges: object) -> dict:
    return {
        "base": BASE,
        "login": "audit-2026",
        "mdp": "motdepasse-audit",
        "connexion": "/login",
        "marqueurs": {},
        **surcharges,
    }


# --- 1. Le fait mesuré : à `domcontentloaded`, la lecture immédiate ne voit RIEN ---------------
def test_a_domcontentloaded_la_lecture_immediate_ne_voit_pas_la_mire_que_l_attente_trouve() -> (
    None
):
    """Le défaut, isolé sur UNE page : deux lectures du même DOM, deux résultats opposés.

    C est la preuve que l ancien code ne mesurait pas l application mais sa propre impatience.
    """
    page = _PageSPA(monte=True)

    assert page.query_selector(qualif._SELECTEUR_MOTDEPASSE) is None
    assert qualif._attendre(page, qualif._SELECTEUR_MOTDEPASSE) is not None


def test_l_attente_expiree_rend_None_sans_faire_tomber_le_pan() -> None:
    """Sens rouge de l attente elle-même : une expiration est un CONSTAT, pas une panne."""
    assert qualif._attendre(_PageSPA(monte=False), qualif._SELECTEUR_MOTDEPASSE) is None


# --- 2. La mire tardive est OUVERTE (le cas BAV2) ----------------------------------------------
def test_la_mire_montee_APRES_le_chargement_est_trouvee_et_remplie() -> None:
    page = _PageSPA(monte=True)

    resultat = qualif._connecter(page, _config())

    assert resultat["etat"] == qualif.SESSION_OUVERTE
    assert page.visitees == ["/login"]  # la route DÉCLARÉE, et elle suffit
    assert page.champs[qualif._SELECTEUR_IDENTIFIANT].rempli == "audit-2026"
    assert page.champs[qualif._SELECTEUR_MOTDEPASSE].rempli == "motdepasse-audit"
    assert page.champs[qualif._SELECTEUR_SOUMISSION].clics == 1
    assert page.soumise is True
    # Le champ mot de passe est ATTENDU, il n est plus lu à chaud.
    assert qualif._SELECTEUR_MOTDEPASSE in page.attendus
    assert page.lus_a_chaud == []


def test_les_deux_routes_par_defaut_restent_essayees_dans_l_ordre() -> None:
    """Non-régression : sans route déclarée, `/connexion` puis `/login` — inchangé."""
    page = _PageSPA(monte=True)

    qualif._connecter(page, _config(connexion=""))

    assert page.visitees == ["/connexion"]  # la première monte une mire : on s arrête là


# --- 3. Sens rouge : sans mire, le pan le dit — et dit OÙ il s est arrêté -----------------------
def test_sans_mire_le_motif_n_est_publie_qu_APRES_l_attente() -> None:
    page = _PageSPA(monte=False)

    echec = qualif._connecter(page, _config(connexion=""))["motif"]

    assert "aucune mire de connexion trouvee" in echec
    # Ce que l ancien motif ne disait pas : l attente a bien eu lieu, et sur quoi.
    assert "APRES attente d apparition du champ mot de passe" in echec
    assert "10 s par route" in echec
    # Chaque candidat nomme son point d arrêt — l information que TF-0315 republie.
    assert "/connexion : aucun « input[type=password] » apparu en 10 s" in echec
    assert "/login : aucun « input[type=password] » apparu en 10 s" in echec
    assert page.attendus.count(qualif._SELECTEUR_MOTDEPASSE) == 2


def test_une_mire_sans_champ_identifiant_nomme_CE_point_d_arret() -> None:
    """Le motif distingue les arrêts : « pas de mire » et « mire incomplète » ne se réparent pas
    du même geste."""

    class _MireSansIdentifiant(_PageSPA):
        def wait_for_selector(self, selecteur: str, **kw: object):
            if selecteur == qualif._SELECTEUR_IDENTIFIANT:
                raise _Expiration("Timeout")
            return super().wait_for_selector(selecteur, **kw)

    resultat = qualif._connecter(_MireSansIdentifiant(monte=True), _config())

    assert resultat["etat"] == qualif.SESSION_SANS_MIRE
    assert "/login : champ mot de passe present, aucun champ identifiant" in resultat["motif"]


def test_une_navigation_impossible_est_nommee_comme_telle() -> None:
    class _Injoignable(_PageSPA):
        def goto(self, url: str, **_kw: object) -> None:
            raise _Expiration("net::ERR_CONNECTION_REFUSED")

    resultat = qualif._connecter(_Injoignable(), _config())

    assert "/login : navigation impossible (_Expiration)" in resultat["motif"]


def test_sans_compte_fourni_rien_n_est_tente() -> None:
    """Non-régression : le pan ne cherche pas de mire quand il n a pas de quoi la remplir."""
    page = _PageSPA(monte=True)
    assert qualif._connecter(page, _config(login="", mdp="")) == {
        "etat": qualif.SESSION_SANS_COMPTE
    }
    assert page.visitees == [] and page.attendus == []


# --- 4. Bout en bout : l effet mesuré — 0 élément inventorié, ou l instance entière ------------
class _FausseReponse:
    def __init__(self, requete: _FausseRequete) -> None:
        self.request, self.status = requete, requete.statut


class _FausseRequete:
    def __init__(self, url: str, statut: int) -> None:
        self.url, self.statut, self.redirected_from = url, statut, None

    def response(self) -> _FausseReponse:
        return _FausseReponse(self)


class _PageInstance(_PageSPA):
    """L instance BAV2 : toute route est refusée en 401 TANT QUE la mire n a pas été soumise."""

    def __init__(self, contexte: _FauxContexte, monte: bool) -> None:
        super().__init__(monte=monte)
        self.contexte = contexte
        self._corps, self._titre, self._statut = "", "", 200

    @property
    def context(self) -> _FauxContexte:
        return self.contexte

    def on(self, *_args: object) -> None:
        return None

    def goto(self, url: str, **_kw: object) -> _FausseReponse:
        chemin = urlparse(url).path or "/"
        self.visitees.append(chemin)
        self.url = url
        if self.soumise:
            self._corps, self._titre, self._statut = "<h1>Annonces</h1>", "Annonces", 200
        else:
            self._corps, self._titre, self._statut = "<h1>Connexion</h1>", "Connexion", 401
        return _FausseReponse(_FausseRequete(url, self._statut))

    def evaluate(self, script: str):
        return self._titre if script is qualif._JS_TITRE else []

    def content(self) -> str:
        return self._corps


class _FauxContexte:
    def __init__(self, navigateur: _FauxNavigateur, options: dict) -> None:
        self.navigateur, self.options = navigateur, dict(options)
        self.entetes: dict[str, str] = {}
        self.pages: list[_PageInstance] = []
        self.biscuits: list[dict] = []
        self.ferme = False

    def cookies(self) -> list[dict]:
        return list(self.biscuits)

    def set_extra_http_headers(self, entetes: dict) -> None:
        self.entetes.update(entetes)

    def new_page(self) -> _PageInstance:
        page = _PageInstance(self, self.navigateur.monte)
        self.pages.append(page)
        return page

    def new_cdp_session(self, _page: object) -> None:
        raise RuntimeError("protocole DevTools indisponible sur ce faux navigateur")

    def close(self) -> None:
        self.ferme = True


class _FauxNavigateur:
    def __init__(self, monte: bool) -> None:
        self.monte = monte
        self.contextes: list[_FauxContexte] = []
        self.ferme = False

    def new_context(self, **options: object) -> _FauxContexte:
        contexte = _FauxContexte(self, options)
        self.contextes.append(contexte)
        return contexte

    def close(self) -> None:
        self.ferme = True


def _brancher(monkeypatch: pytest.MonkeyPatch, monte: bool) -> _FauxNavigateur:
    faux = _FauxNavigateur(monte)

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


def _analyser(tmp_path: Path) -> object:
    from forge_tests import qualification

    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_LOGIN"] = "audit-2026"
    os.environ["FORGE_TESTS_QUALIF_PASSWORD"] = "motdepasse-audit"
    os.environ["FORGE_TESTS_QUALIF_CONNEXION"] = "/login"
    # Deux routes au moins : en dessous, la garde de précondition (RT-16) s abstient par
    # construction — une route unique ne distingue pas un pan aveugle d une route en défaut.
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/trouver-une-annonce"
    qualification.oublier(tmp_path)
    sortie = qualif.analyser(tmp_path)
    qualification.oublier(tmp_path)
    return sortie


def test_bout_en_bout_la_mire_attendue_rend_l_instance_MESURABLE(
    tmp_path: Path, env_propre, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le gain, mesuré au verdict : la session s ouvre, les routes sont inventoriées."""
    _brancher(monkeypatch, monte=True)

    sortie = _analyser(tmp_path)

    assert sortie.verdict != "SKIP"
    assert sortie.surface is not None and sortie.surface["inventorie"] > 0
    assert not any("aucune mire de connexion" in ligne for ligne in sortie.non_juge)


def test_bout_en_bout_sans_mire_le_pan_reste_SILENCIEUX_et_le_DIT(
    tmp_path: Path, env_propre, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sens rouge : quand il n y a réellement pas de mire, rien ne change — SKIP motivé, 0
    élément inventorié, aucun constat imputé au produit (RT-16)."""
    _brancher(monkeypatch, monte=False)

    sortie = _analyser(tmp_path)

    assert sortie.verdict == "SKIP"
    assert sortie.surface is None
    assert any("aucune mire de connexion trouvee" in ligne for ligne in sortie.non_juge)
