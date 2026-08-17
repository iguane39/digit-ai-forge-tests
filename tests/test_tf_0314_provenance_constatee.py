"""TF-0314 (lot Produit-11 20260817a) — le rapport affirmait une session qui n existait
pas, parce que la provenance se DÉDUISAIT de la configuration.

Dans le MÊME rapport du 17/08, `non_juge[0]` annonçait « PROVENANCE DE SESSION — session ouverte
PAR LA FORGE elle-même, en rejouant la mire formulaire avec FORGE_TESTS_QUALIF_LOGIN ; ce que le
pan voit est exactement ce que ce compte voit », et `non_juge[1]` disait « aucune mire de connexion
trouvée ». Deux phrases contradictoires dans le même champ, et c est la première qui se lit en
tête. `provenance_session()` ne consultait que le dictionnaire de CONFIGURATION : elle constatait
qu un login et un mot de passe avaient été fournis, jamais qu une session avait été ouverte.

C est l exigence que TF-0222 avait posée pour les sessions CAPTURÉES — une session fournie et
refusée doit être dite refusée — non étendue au cas de la mire rejouée. Elle l est ici :

  - la phrase de provenance suit le RÉSULTAT de `_connecter` (ouverte / échouée / aucune mire /
    non relevé), et ces quatre phrases sont distinctes ;
  - l ouverture se CONSTATE : un cookie de session posé, ou la mire qui rend la main. Un clic
    émis n est pas une session, et c est exactement la déduction supprimée ici.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import qualif

BASE = "https://bav.exemple.test"


def _config(**surcharges: object) -> dict:
    return {
        "base": BASE,
        "login": "audit-2026",
        "mdp": "motdepasse-audit",
        "connexion": "/login",
        "marqueurs": {},
        **surcharges,
    }


class _Contexte:
    def __init__(self, biscuits: list[str] | None = None) -> None:
        self.biscuits = [{"name": nom} for nom in (biscuits or [])]

    def cookies(self) -> list[dict]:
        return list(self.biscuits)


class _PageSoumise:
    """Une page APRÈS soumission de la mire — l état que `_constater_ouverture` doit lire.

    Les trois leviers sont ceux du produit réel : les cookies posés, l URL d arrivée, et le champ
    de mot de passe encore rendu ou non.
    """

    def __init__(
        self,
        *,
        cookies: list[str] | None = None,
        url: str = f"{BASE}/login",
        mire_encore_la: bool = True,
        contexte_muet: bool = False,
    ) -> None:
        self.contexte = _Contexte(cookies)
        self.url = url
        self.mire_encore_la = mire_encore_la
        self.contexte_muet = contexte_muet

    @property
    def context(self) -> _Contexte:
        if self.contexte_muet:
            raise RuntimeError("contexte navigateur indisponible")
        return self.contexte

    def query_selector(self, _selecteur: str) -> object | None:
        return object() if self.mire_encore_la else None


# --- 1. L ouverture se CONSTATE — les deux attestations ----------------------------------------
def test_un_cookie_de_session_pose_ATTESTE_l_ouverture() -> None:
    """Le cas réel Produit-11 : deux cookies JWT posés par la soumission de `/login`."""
    page = _PageSoumise(
        cookies=["access_token_cookie", "refresh_token_cookie"],
        url=f"{BASE}/trouver-une-annonce",
        mire_encore_la=False,
    )

    resultat = qualif._constater_ouverture(page, "/login", set(), _config())

    assert resultat["etat"] == qualif.SESSION_OUVERTE
    assert "2 cookie(s) de session pose(s)" in resultat["preuve"]
    assert "access_token_cookie" in resultat["preuve"]


def test_seuls_les_cookies_NOUVEAUX_attestent_quelque_chose() -> None:
    """Un cookie déjà là avant la soumission (consentement, langue) n atteste RIEN : le constat
    porte sur ce que la soumission a POSÉ, pas sur ce que le navigateur portait déjà."""
    page = _PageSoumise(cookies=["cookie_consent"], url=f"{BASE}/login", mire_encore_la=True)

    resultat = qualif._constater_ouverture(page, "/login", {"cookie_consent"}, _config())

    assert resultat["etat"] == qualif.SESSION_ECHOUEE
    assert "aucun cookie pose, aucune sortie de la mire" in resultat["motif"]


def test_la_mire_qui_rend_la_main_ATTESTE_aussi_l_ouverture() -> None:
    """Second cas légitime : le jeton vit en stockage local, aucun cookie ne l atteste — mais la
    mire a bel et bien laissé la place à une autre route."""
    page = _PageSoumise(url=f"{BASE}/trouver-une-annonce", mire_encore_la=False)

    resultat = qualif._constater_ouverture(page, "/login", set(), _config())

    assert resultat["etat"] == qualif.SESSION_OUVERTE
    assert "a rendu la main" in resultat["preuve"] and "jeton hors cookie" in resultat["preuve"]


# --- 2. Sens rouge : un clic émis n est PAS une session ----------------------------------------
def test_une_mire_qui_se_re_affiche_ailleurs_est_un_ECHEC_constate() -> None:
    """Le piège de la redirection : la page a changé de route et REDONNE la mire — c est le
    refus le plus courant (retour au login), et il se lisait comme un succès."""
    page = _PageSoumise(url=f"{BASE}/", mire_encore_la=True)

    resultat = qualif._constater_ouverture(page, "/login", set(), _config())

    assert resultat["etat"] == qualif.SESSION_ECHOUEE
    assert "la mire y est TOUJOURS rendue" in resultat["motif"]
    assert resultat["arret"]


def test_un_contexte_MUET_ne_fabrique_pas_un_constat_d_ouverture() -> None:
    """Une ignorance n atteste jamais : sans cookies lisibles et sans URL exploitable, la session
    est déclarée NON ouverte — un audit qui se croit authentifié est le plus dangereux."""
    page = _PageSoumise(contexte_muet=True, url="", mire_encore_la=False)

    resultat = qualif._constater_ouverture(page, "/login", set(), _config())

    assert resultat["etat"] == qualif.SESSION_ECHOUEE


# --- 3. La phrase de provenance suit le CONSTAT ------------------------------------------------
def test_les_quatre_phrases_de_provenance_sous_compte_fourni_sont_DISTINCTES() -> None:
    ouverte = qualif.provenance_session(
        _config(), {"etat": qualif.SESSION_OUVERTE, "preuve": "2 cookie(s) de session pose(s)"}
    )
    echouee = qualif.provenance_session(
        _config(), {"etat": qualif.SESSION_ECHOUEE, "motif": "soumission sans effet observable"}
    )
    sans_mire = qualif.provenance_session(
        _config(), {"etat": qualif.SESSION_SANS_MIRE, "motif": "aucune mire de connexion trouvee"}
    )
    non_releve = qualif.provenance_session(_config(), {"etat": None})

    assert len({ouverte, echouee, sans_mire, non_releve}) == 4
    assert "CONSTATEE" in ouverte and "2 cookie(s) de session pose(s)" in ouverte
    assert "N A PAS ete ouverte" in echouee and "ANONYME DE FAIT" in echouee
    assert "N A PAS ete ouverte" in sans_mire and "aucune mire de connexion trouvee" in sans_mire
    assert "n a pas ete releve" in non_releve
    # Aucune de ces trois-là n a le droit d annoncer la session que la première annonce.
    assert all("session ouverte PAR LA FORGE" not in ligne for ligne in (echouee, sans_mire))


def test_sans_resultat_releve_la_provenance_n_AFFIRME_rien() -> None:
    """Le défaut, à sa racine : avec la seule configuration, la phrase affirmait une session."""
    ligne = qualif.provenance_session(_config())

    assert "PAS constatee" in ligne
    assert "session ouverte PAR LA FORGE" not in ligne


def test_la_session_capturee_et_l_anonyme_ne_changent_PAS(tmp_path: Path) -> None:
    """Non-régression TF-0222 : les deux autres provenances ne dépendent d aucun constat de mire
    — l une est fournie, l autre est l absence de tout."""
    capturee = qualif.provenance_session(
        _config(storage_state="C:/x/storageState.json"),
        {"etat": qualif.SESSION_ECHOUEE, "motif": "sans objet"},
    )
    anonyme = qualif.provenance_session(_config(login="", mdp=""), {"etat": None})

    assert "CAPTUREE" in capturee and "PERIME" in capturee
    assert "AUCUNE session" in anonyme


# --- 4. Le rapport ne se contredit plus -------------------------------------------------------
def _page_vue(route: str, statut: int = 200, corps: str = "<h1>Connexion</h1>") -> dict:
    return {
        "route": route,
        "statut": statut,
        "problemes": [] if statut == 200 else [f"route atteignable par un lien mais HTTP {statut}"],
        "affordances": [],
        "corps": corps,
        "console": [],
    }


def test_le_rapport_ne_dit_plus_a_la_fois_session_ouverte_ET_aucune_mire(tmp_path: Path) -> None:
    """La contradiction exacte du rapport du 17/08, rejouée sur un relevé : le pan n a pas trouvé
    de mire, et la ligne de provenance doit le refléter au lieu de l ignorer."""
    releve = [_page_vue("/", 401), _page_vue("/annonces", 401)]
    sessions = [
        {
            "role": "",
            "etat": qualif.SESSION_SANS_MIRE,
            "motif": "aucune mire de connexion trouvee (routes essayees : /login)",
        }
    ]

    sortie = qualif.conclure(tmp_path, _config(), releve, [], None, sessions)

    provenances = [ligne for ligne in sortie.non_juge if "PROVENANCE DE SESSION" in ligne]
    assert len(provenances) == 1
    assert "N A PAS ete ouverte" in provenances[0]
    assert "session ouverte PAR LA FORGE" not in provenances[0]


def test_avec_la_session_CONSTATEE_le_rapport_l_affirme_ET_le_prouve(tmp_path: Path) -> None:
    """Sens vert : quand l ouverture est constatée, la phrase la plus forte est publiée — et elle
    porte sa preuve, ce que l ancienne ne faisait pas."""
    releve = [_page_vue("/", 200, "<h1>Annonces</h1>")]
    sessions = [
        {
            "role": "",
            "etat": qualif.SESSION_OUVERTE,
            "preuve": "2 cookie(s) de session pose(s) par la soumission de /login",
        }
    ]

    sortie = qualif.conclure(tmp_path, _config(), releve, [], None, sessions)

    provenance = next(ligne for ligne in sortie.non_juge if "PROVENANCE DE SESSION" in ligne)
    assert "session ouverte PAR LA FORGE" in provenance
    assert "CONSTATEE" in provenance and "2 cookie(s)" in provenance


def test_la_regle_du_constat_est_au_registre_de_dette() -> None:
    """Ce que le constat NE sait PAS voir se déclare : un jeton gardé en mémoire, sans cookie ni
    changement de route, reste indiscernable d un échec."""
    assert any(
        "l ouverture d une session par la mire se CONSTATE" in ligne for ligne in qualif.NON_JUGE
    )


@pytest.mark.parametrize(
    ("libelle", "etat"),
    [
        ("échec de mire", qualif.SESSION_ECHOUEE),
        ("aucune mire", qualif.SESSION_SANS_MIRE),
    ],
)
def test_une_session_non_ouverte_dit_que_le_parcours_est_anonyme_DE_FAIT(
    libelle: str, etat: str
) -> None:
    """La conséquence que le rapport taisait : sans session, ce qui suit ne juge que l anonyme."""
    ligne = qualif.provenance_session(_config(), {"etat": etat, "motif": "peu importe"})
    assert "ANONYME DE FAIT" in ligne, libelle
