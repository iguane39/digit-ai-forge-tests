"""TF-0316 (lot Approval2 20260817b, étude d opportunité 20260817c — verdict O3) — le pan
n acceptait qu UNE session, et son ratio ne déclarait pas qu un seul rôle avait été visité.

`FORGE_TESTS_QUALIF_STORAGE_STATE` est un chemin unique : un seul storage state, un seul contexte,
donc une seule identité pour tout le parcours. Sur Approval2 le pan a rendu « 8/8, ratio 1,00,
ZÉRO finding » (ledger seq 28) avec le compte unique `mock-user@example.com`. Or le produit réserve
trois surfaces par rôle : la console d administration (`/admin` derrière `RequireAdmin`), l écran de
revue et décision (réservé aux approbateurs), la vue en lecture seule du destinataire en copie.
Aucune n avait été parcourue sous son rôle propre, et le rapport ne le disait pas : « ratio 1,00 »
se lit « tout est couvert ». Écart découvert **cinq jours plus tard par une question humaine**.

Ce n est PAS un faux négatif : la garde RT-16/TF-0211 fonctionnait, le pan n a rien imputé à tort.
Le défaut est un SILENCE. Les deux niveaux du verdict O3 sont prouvés ici :

  (a) **déclarer** — « N session(s) exercée(s) : les routes refusées ou invisibles à cette identité
      ne sont pas jugées » (N = 1 est le cas dégradé DÉCLARÉ, pas un cas à part), et les 401/403 et
      redirections d autorisation sortent en issue DISTINCTE d un succès, hors du ratio ;
  (b) **mesurer** — `FORGE_TESTS_QUALIF_STORAGE_STATES` (`role=chemin`, virgule), un contexte
      navigateur par session, parcours rejoué par profil, couverture par rôle au rapport.

La non-destructivité ne bouge pas : aucun clic n est émis, on lit plus de surfaces sans agir.
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

BASE = "https://approval2.exemple.test"


@pytest.fixture()
def env_propre():
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _config(**surcharges: object) -> dict:
    return {"base": BASE, "marqueurs": {}, "storage_state": "", "bearer": "", **surcharges}


def _page(
    route: str,
    *,
    statut: int = 200,
    role: str = "",
    corps: str = "",
    url_finale: str | None = None,
    problemes: list[str] | None = None,
) -> dict:
    return {
        "route": route,
        "statut": statut,
        "role": role,
        "url_finale": url_finale if url_finale is not None else f"{BASE}{route}",
        "problemes": list(problemes or []),
        "affordances": [],
        "corps": corps or f"<h1>{route}</h1>",
        "console": [],
    }


def _storage_state(tmp_path: Path, nom: str) -> Path:
    fichier = tmp_path / nom
    fichier.write_text(
        json.dumps({"cookies": [{"name": "session", "value": "x"}], "origins": []}),
        encoding="utf-8",
    )
    return fichier


# --- 1. (b) Le contrat de configuration : N sessions étiquetées ---------------------------------
def test_une_liste_role_chemin_donne_N_sessions_etiquetees() -> None:
    sessions, alertes = qualif.sessions_declarees(
        _config(storage_states=["admin=C:/x/admin.json", "approbateur=C:/x/appro.json"])
    )

    assert [s["role"] for s in sessions] == ["admin", "approbateur"]
    assert [s["storage_state"] for s in sessions] == ["C:/x/admin.json", "C:/x/appro.json"]
    assert alertes == []


def test_le_SINGULIER_reste_valide_et_donne_une_session_sans_etiquette() -> None:
    """Non-régression TF-0222 : c est le cas de tous les audits menés jusqu ici."""
    sessions, alertes = qualif.sessions_declarees(_config(storage_state="C:/x/etat.json"))

    assert sessions == [{"role": "", "storage_state": "C:/x/etat.json", "etat": None}]
    assert alertes == []


def test_sans_rien_declarer_il_y_a_TOUJOURS_une_session() -> None:
    """N = 1 est le cas dégradé, pas un cas à part : la boucle est la même, la déclaration aussi."""
    sessions, _ = qualif.sessions_declarees(_config())

    assert len(sessions) == 1 and sessions[0]["role"] == ""


@pytest.mark.parametrize(
    ("libelle", "brut"),
    [
        ("un chemin sans role n est pas etiquete", ["C:/x/admin.json"]),
        ("un role sans chemin n a pas de session", ["admin="]),
        ("une entree vide de part et d autre", ["="]),
    ],
)
def test_une_session_mal_formee_est_ECARTEE_et_DECLAREE(libelle: str, brut: list[str]) -> None:
    """Sens rouge : une couverture par rôle bâtie sur une étiquette illisible serait faussement
    nommée — l entrée est écartée, et son écart est dit."""
    sessions, alertes = qualif.sessions_declarees(_config(storage_states=brut))

    assert len(alertes) == 1 and "ECARTEE" in alertes[0], libelle
    assert sessions[0]["role"] == ""  # repli sur la session sans étiquette


def test_un_role_declare_deux_fois_est_DECLARE_comme_tel() -> None:
    sessions, alertes = qualif.sessions_declarees(
        _config(storage_states=["admin=C:/x/a.json", "admin=C:/x/b.json"])
    )

    assert [s["storage_state"] for s in sessions] == ["C:/x/a.json"]
    assert any("declare DEUX FOIS" in alerte for alerte in alertes)


def test_le_singulier_et_le_bearer_melanges_au_pluriel_sont_DECLARES() -> None:
    """Deux pièges d identité : une session sans étiquette au milieu de sessions étiquetées, et un
    en-tête `Authorization` unique posé sur tous les profils."""
    _, alertes = qualif.sessions_declarees(
        _config(
            storage_states=["admin=C:/x/a.json"],
            storage_state="C:/x/anonyme.json",
            bearer="jeton",
        )
    )

    assert any("IGNORE" in alerte for alerte in alertes)
    assert any("MEME en-tete Authorization" in alerte for alerte in alertes)


def test_la_liste_est_lue_dans_l_environnement(env_propre, tmp_path: Path) -> None:
    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATES"] = "admin=C:/x/a.json, lecteur=C:/x/b.json"

    config = qualif._config(tmp_path)

    assert config["storage_states"] == ["admin=C:/x/a.json", "lecteur=C:/x/b.json"]


# --- 2. (a) Les refus d autorisation sortent en issue DISTINCTE, hors du ratio ------------------
@pytest.mark.parametrize(
    ("libelle", "page_vue", "attendu"),
    [
        ("le refus dit par le protocole", _page("/admin", statut=403), "HTTP 403"),
        ("le 401 aussi", _page("/admin", statut=401), "HTTP 401"),
        (
            "le refus JOUE EN REDIRECTION — celui qui comptait pour un succes",
            _page("/admin", statut=200, url_finale=f"{BASE}/login", corps="<h1>Connexion</h1>"),
            "redirection d autorisation vers /login",
        ),
    ],
)
def test_un_refus_d_autorisation_est_RECONNU(libelle: str, page_vue: dict, attendu: str) -> None:
    assert qualif.refus_autorisation(page_vue, _config()) == attendu, libelle


@pytest.mark.parametrize(
    ("libelle", "page_vue"),
    [
        ("une route saine", _page("/", statut=200)),
        ("une erreur serveur reste un defaut du produit", _page("/x", statut=500)),
        ("une redirection INTERNE n est pas un refus", _page("/x", url_finale=f"{BASE}/x/detail")),
        ("une URL finale illisible n atteste rien", _page("/x", url_finale="")),
        ("un 404 n est pas un refus d autorisation", _page("/x", statut=404)),
    ],
)
def test_ce_qui_n_est_PAS_un_refus_d_autorisation(libelle: str, page_vue: dict) -> None:
    """Sens rouge : sur-corriger ici ferait passer des défauts du produit pour des refus, et le
    pan cesserait de les imputer à qui doit les corriger."""
    assert qualif.refus_autorisation(page_vue, _config()) is None, libelle


def test_une_route_refusee_sort_du_RATIO_en_issue_distincte(tmp_path: Path) -> None:
    """Le cœur de (a) : elle n est ni un succès, ni un défaut du produit, ni dans le ratio."""
    releve = [
        _page("/", corps="<h1>Accueil</h1>"),
        _page("/demandes", corps="<h1>Demandes</h1>"),
        _page("/admin", statut=403),
    ]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    refus = [f for f in sortie.findings if f.classe == qualif.CLASSE_REFUS_AUTORISATION]
    assert len(refus) == 1
    assert refus[0].id == "qualif:route:/admin"
    assert "REFUSEE a l identite exercee" in refus[0].message
    # Hors du ratio : ni exercée, ni inventoriée — mais NOMMÉE.
    assert sortie.surface["inventorie"] == 2
    assert "qualif:route:/admin" not in sortie.surface["elements_exerces"]
    assert "qualif:route:/admin" not in sortie.surface["elements_non_exerces"]
    assert sortie.surface["elements_refuses"] == ["qualif:route:/admin"]
    assert any("REFUSEE(S) a l identite" in ligne for ligne in sortie.non_juge)


def test_un_refus_joue_en_redirection_ne_compte_plus_pour_un_SUCCES(tmp_path: Path) -> None:
    """Le défaut exact d Approval2 : la mire répond 200 avec un titre, donc la route comptait pour
    exercée — indiscernable d une route saine dans le ratio."""
    releve = [
        _page("/", corps="<h1>Accueil</h1>"),
        _page("/admin", statut=200, url_finale=f"{BASE}/login", corps="<h1>Connexion</h1>"),
    ]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    assert sortie.surface["ratio"] == 1.0  # ce qui a été VU est sain…
    assert sortie.surface["inventorie"] == 1  # …et la route refusée n y est pas comptée
    assert [f.classe for f in sortie.findings] == [qualif.CLASSE_REFUS_AUTORISATION]


def test_la_classe_de_refus_a_sa_suite_et_elle_va_a_l_UTILISATEUR() -> None:
    """Sans règle propre, la classe tombait au « défaut d'auditeur » et repartait vers la forge —
    alors qu il n y a rien à corriger : la garde d autorisation fait son travail."""
    from forge_tests.actions import classifier

    action = classifier(
        [
            {
                "classe": qualif.CLASSE_REFUS_AUTORISATION,
                "id": "qualif:role:admin:route:/admin",
                "pan": "qualif",
                "message": "HTTP 403",
            }
        ]
    )[0]

    assert action["categorie"] == "manuelle_utilisateur"
    assert action["etape_cible"] == "mep-config"
    assert "FORGE_TESTS_QUALIF_STORAGE_STATES" in action["attendu"]
    assert "DÉFAUT D'AUDITEUR" not in action["attendu"]


# --- 3. (a) La déclaration, vraie quel que soit N -----------------------------------------------
def test_a_UNE_session_le_rapport_declare_deja_son_perimetre(tmp_path: Path) -> None:
    """« ratio 1,00 » ne se lit plus « tout est couvert » : le rapport dit ce qu il n a pas vu."""
    releve = [_page("/", corps="<h1>Accueil</h1>"), _page("/demandes", corps="<h1>D</h1>")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    declaration = next(ligne for ligne in sortie.non_juge if "session(s) exercee(s)" in ligne)
    assert "1 session(s) exercee(s)" in declaration
    assert "SANS etiquette de role" in declaration
    assert "NE SONT PAS JUGEES" in declaration
    assert "FORGE_TESTS_QUALIF_STORAGE_STATES" in declaration  # le geste qui lève la limite
    assert any("couverture PAR ROLE" in ligne for ligne in sortie.non_juge)


def test_les_deux_dettes_de_la_couverture_par_role_sont_au_REGISTRE() -> None:
    """L étude 20260817c les assume : elles doivent être lisibles au rapport de chaque audit."""
    entier = " ".join(qualif.NON_JUGE)

    assert "l etiquette de role d une session declaree est DECLARATIVE" in entier
    assert "les surfaces INVISIBLES a l identite exercee" in entier


def test_la_couverture_par_role_est_rendue_role_par_role(tmp_path: Path) -> None:
    releve = [
        _page("/", role="admin", corps="<h1>Accueil</h1>"),
        _page("/admin", role="admin", corps="<h1>Console</h1>"),
        _page("/", role="lecteur", corps="<h1>Accueil</h1>"),
        _page("/admin", role="lecteur", statut=403),
    ]
    sessions = [
        {"role": "admin", "storage_state": "C:/x/a.json", "etat": None},
        {"role": "lecteur", "storage_state": "C:/x/l.json", "etat": None},
    ]

    sortie = qualif.conclure(tmp_path, _config(), releve, [], None, sessions)

    par_role = {e["role"]: e for e in sortie.surface["couverture_par_role"]}
    assert par_role["admin"]["inventorie"] == 2 and par_role["admin"]["exerce"] == 2
    assert par_role["admin"]["refuse"] == 0
    # Le lecteur n a vu qu une route sur les deux, et la seconde lui a été REFUSÉE.
    assert par_role["lecteur"]["inventorie"] == 1 and par_role["lecteur"]["refuse"] == 1
    # Les identifiants portent le rôle : la même route vue par deux identités fait deux éléments.
    assert "qualif:role:admin:route:/admin" in sortie.surface["elements_exerces"]
    assert sortie.surface["elements_refuses"] == ["qualif:role:lecteur:route:/admin"]
    declaration = next(ligne for ligne in sortie.non_juge if "session(s) exercee(s)" in ligne)
    assert "2 session(s) exercee(s)" in declaration
    assert "« admin »" in declaration and "« lecteur »" in declaration


def test_la_provenance_est_publiee_PAR_ROLE(tmp_path: Path) -> None:
    """Deux identités, deux provenances : une phrase par identité, jamais une moyenne."""
    sessions = [
        {"role": "admin", "storage_state": "C:/secrets/admin.json", "etat": None},
        {"role": "lecteur", "storage_state": "C:/secrets/lecteur.json", "etat": None},
    ]

    sortie = qualif.conclure(
        tmp_path, _config(), [_page("/", role="admin", corps="<h1>A</h1>")], [], None, sessions
    )

    provenances = [ligne for ligne in sortie.non_juge if "PROVENANCE DE SESSION" in ligne]
    assert len(provenances) == 2
    assert "(role « admin »)" in provenances[0] and "admin.json" in provenances[0]
    assert "(role « lecteur »)" in provenances[1]
    # Le rapport CIRCULE : le chemin complet n en sort pas, seulement le nom du fichier.
    assert not any("C:/secrets" in ligne for ligne in provenances)


def test_les_identifiants_MONO_session_ne_changent_PAS(tmp_path: Path) -> None:
    """Non-régression stricte : la cotation de risque, les déclarations RT-16 et les rapports
    antérieurs s adossent à ces identifiants — le rôle n y entre que s il existe vraiment."""
    releve = [_page("/", corps="<h1>Accueil</h1>"), _page("/demandes", corps="<h1>D</h1>")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [])

    assert sortie.surface["elements_exerces"] == ["qualif:route:/", "qualif:route:/demandes"]


def test_un_element_role_reste_range_par_ECRAN_dans_le_cahier() -> None:
    """Sans quoi tous les éléments d un audit multi-rôles tomberaient en « non rattachés » : la même
    route vue par deux rôles est le même écran, et c est là qu elle se lit."""
    from forge_tests.livrables.surface import sous_chapitre

    assert sous_chapitre("ecran", "qualif:role:admin:route:/admin") == ("écran /admin", True)
    assert sous_chapitre("parcours", "qualif:role:admin:effet:/admin:3:button") == (
        "parcours /admin",
        True,
    )
    assert sous_chapitre("ecran", "qualif:route:/admin") == ("écran /admin", True)


# --- 4. Bout en bout : un contexte navigateur PAR session, parcours rejoué par profil -----------
class _FausseReponse:
    def __init__(self, requete: _FausseRequete) -> None:
        self.request, self.status = requete, requete.statut


class _FausseRequete:
    def __init__(self, url: str, statut: int) -> None:
        self.url, self.statut, self.redirected_from = url, statut, None

    def response(self) -> _FausseReponse:
        return _FausseReponse(self)


class _Page:
    """L instance Approval2 : `/admin` est derrière `RequireAdmin`, tout le reste est ouvert."""

    def __init__(self, contexte: _FauxContexte) -> None:
        self.contexte = contexte
        self.visitees: list[str] = []
        self.url = f"{BASE}/"
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
        if chemin == "/admin" and self.contexte.role != "admin":
            self._corps, self._titre, self._statut = "<h1>Interdit</h1>", "Interdit", 403
        else:
            self._corps, self._titre, self._statut = f"<h1>{chemin}</h1>", chemin, 200
        return _FausseReponse(_FausseRequete(url, self._statut))

    def evaluate(self, script: str):
        return self._titre if script is qualif._JS_TITRE else []

    def content(self) -> str:
        return self._corps


class _FauxContexte:
    def __init__(self, navigateur: _FauxNavigateur, options: dict) -> None:
        self.navigateur, self.options = navigateur, dict(options)
        self.entetes: dict[str, str] = {}
        self.pages: list[_Page] = []
        self.ferme = False

    @property
    def role(self) -> str:
        """Le rôle que ce contexte porte — déduit du storage state qu on lui a injecté."""
        return Path(str(self.options.get("storage_state") or "sans")).stem

    def cookies(self) -> list[dict]:
        return []

    def set_extra_http_headers(self, entetes: dict) -> None:
        self.entetes.update(entetes)

    def new_page(self) -> _Page:
        page = _Page(self)
        self.pages.append(page)
        return page

    def new_cdp_session(self, _page: object) -> None:
        raise RuntimeError("protocole DevTools indisponible sur ce faux navigateur")

    def close(self) -> None:
        self.ferme = True


class _FauxNavigateur:
    def __init__(self) -> None:
        self.contextes: list[_FauxContexte] = []
        self.ferme = False

    def new_context(self, **options: object) -> _FauxContexte:
        contexte = _FauxContexte(self, options)
        self.contextes.append(contexte)
        return contexte

    def close(self) -> None:
        self.ferme = True


@pytest.fixture()
def navigateur(monkeypatch: pytest.MonkeyPatch) -> _FauxNavigateur:
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


def test_bout_en_bout_deux_roles_deux_contextes_et_une_couverture_par_role(
    tmp_path: Path, env_propre, navigateur: _FauxNavigateur
) -> None:
    """Le cas d Approval2, rejoué : `/admin` est vue sous `admin`, refusée sous `lecteur`, et le
    rapport le DIT au lieu de rendre « ratio 1,00 » pour une seule identité."""
    from forge_tests import qualification

    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/admin,/demandes"
    os.environ["FORGE_TESTS_QUALIF_STORAGE_STATES"] = (
        f"admin={_storage_state(tmp_path, 'admin.json')},"
        f"lecteur={_storage_state(tmp_path, 'lecteur.json')}"
    )
    qualification.oublier(tmp_path)

    sortie = qualif.analyser(tmp_path)
    qualification.oublier(tmp_path)

    # a) un contexte VIERGE pour la porte d entrée, puis UN contexte par session.
    assert len(navigateur.contextes) == 3
    assert navigateur.contextes[0].options == {}
    assert [Path(str(c.options["storage_state"])).stem for c in navigateur.contextes[1:]] == [
        "admin",
        "lecteur",
    ]
    # b) le parcours est REJOUÉ par profil — les mêmes routes, sous deux identités.
    parcours = [
        [chemin for page in contexte.pages for chemin in page.visitees]
        for contexte in navigateur.contextes[1:]
    ]
    assert parcours[0] == parcours[1] and "/admin" in parcours[0]
    # c) la couverture est rendue PAR RÔLE, et le refus est nommé pour ce qu il est.
    par_role = {e["role"]: e for e in sortie.surface["couverture_par_role"]}
    assert par_role["admin"]["refuse"] == 0 and par_role["lecteur"]["refuse"] == 1
    assert sortie.surface["elements_refuses"] == ["qualif:role:lecteur:route:/admin"]
    assert any("2 session(s) exercee(s)" in ligne for ligne in sortie.non_juge)
    # d) non-destructivité inchangée : aucun clic, aucune mire rejouée sous session fournie.
    assert all("/login" not in parcours[0] for parcours in parcours)


def test_bout_en_bout_une_seule_session_se_comporte_comme_AVANT(
    tmp_path: Path, env_propre, navigateur: _FauxNavigateur
) -> None:
    """Sens rouge du précédent : sans liste déclarée, rien ne change — un contexte d entrée, un
    contexte de parcours, des identifiants sans rôle. Et la limite est déclarée quand même."""
    os.environ["FORGE_TESTS_QUALIF_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/demandes"

    sortie = qualif.analyser(tmp_path)

    assert len(navigateur.contextes) == 2
    assert all(":role:" not in element for element in sortie.surface["elements_exerces"])
    assert any("1 session(s) exercee(s)" in ligne for ligne in sortie.non_juge)
