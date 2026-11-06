"""TF-2123 (suite) — jouer le parcours de chaque persona sous l'identité de son rôle.

Le premier volet (commit 678ba56) lisait les personas que le produit déclare et exigeait, pour
chacun, un parcours de bout en bout qui le cite. Il ne jouait RIEN : « exercé » voulait dire « un
fichier le cite ». Décision du 04/11/2026 : version minimale prouvée du jeu contre l'instance
servie.

Ce volet joue, contre l'instance servie (`FORGE_TESTS_QUALIF_URL`, à défaut `FORGE_TESTS_BASE_URL`),
les routes que le parcours de chaque persona NAVIGUE, sous les cookies et le jeton du storage state
de son rôle (`FORGE_TESTS_QUALIF_STORAGE_STATES`, `role=chemin`). GET seulement : le pan ne modifie
jamais l'instance. Un parcours est « joué » quand chacune de ses routes répond sous cette identité
sans refus, sans erreur et sans renvoi vers la mire de connexion.

La preuve est une instance RÉELLE de fixture : un serveur HTTP local, avec des routes réservées par
rôle, démarré par le test. Pas de doublure du client : les requêtes partent par le réseau.

Sens prouvés :
  - VERT    — chaque persona joue ses routes sous son identité : PASS ;
  - ROUGE   — un rôle refusé (403), une session périmée (renvoi vers la mire), une route en
              erreur, un cookie hors périmètre : FAIL nommé, avec la route et la raison ;
  - NON JOUÉ — persona sans identité, instance injoignable : dit, jamais compté pour un échec du
              produit ni pour un succès.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from forge_tests import authentification, classes
from forge_tests.adaptateurs import personas

PARCOURS = (
    "import {{ test }} from '@playwright/test';\n"
    "test('{nom}', async ({{ page }}) => {{\n"
    "{navigations}"
    "}});\n"
)


def _parcours(nom: str, *routes: str) -> str:
    navigations = "".join(f"  await page.goto('{route}');\n" for route in routes)
    return PARCOURS.format(nom=nom, navigations=navigations)


class Instance:
    """L'instance servie de la fixture : des routes réservées par rôle, et le journal de ce
    qu'elle a reçu."""

    def __init__(self) -> None:
        self.recus: list[dict] = []
        instance = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:  # silence
                return

            def _identite(self) -> str | None:
                cookie = self.headers.get("Cookie") or ""
                for morceau in cookie.split(";"):
                    nom, _, valeur = morceau.strip().partition("=")
                    if nom == "session" and valeur.endswith("-ok"):
                        return valeur[: -len("-ok")]
                jeton = self.headers.get("Authorization") or ""
                if jeton.startswith("Bearer jeton-"):
                    return jeton[len("Bearer jeton-"):]
                return None

            def _repondre(self, code: int, corps: str = "", entetes: dict | None = None) -> None:
                self.send_response(code)
                for cle, valeur in (entetes or {}).items():
                    self.send_header(cle, valeur)
                self.send_header("Content-Length", str(len(corps.encode())))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(corps.encode())

            def do_GET(self) -> None:  # noqa: N802
                chemin = self.path.split("?")[0]
                role = self._identite()
                instance.recus.append(
                    {"methode": "GET", "chemin": chemin, "role": role,
                     "cookie": self.headers.get("Cookie"),
                     "autorisation": self.headers.get("Authorization")}
                )
                if chemin == "/connexion":
                    self._repondre(200, "mire")
                elif chemin == "/panne":
                    self._repondre(500, "oups")
                elif chemin in ("/tableau", "/admin", "/api/moi"):
                    if role is None:
                        if chemin == "/api/moi":
                            self._repondre(401, "non authentifie")
                        else:
                            self._repondre(302, "", {"Location": "/connexion"})
                    elif chemin == "/admin" and role != "admin":
                        self._repondre(403, "interdit")
                    else:
                        self._repondre(200, json.dumps({"role": role}))
                else:
                    self._repondre(404, "absent")

            def do_POST(self) -> None:  # noqa: N802
                instance.recus.append({"methode": "POST", "chemin": self.path, "role": None})
                self._repondre(405)

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.serveur.server_address[1]}"

    def __enter__(self) -> Instance:
        self.fil.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.serveur.shutdown()
        self.serveur.server_close()
        self.fil.join(timeout=5)


@pytest.fixture
def instance() -> Iterator[Instance]:
    with Instance() as i:
        yield i


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")


def _ecrire(racine: Path, relatif: str, texte: str) -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def _etat_cookie(valeur: str, domaine: str = "127.0.0.1") -> str:
    return json.dumps(
        {"cookies": [{"name": "session", "value": valeur, "domain": domaine, "path": "/"}],
         "origins": []}
    )


def _etat_jeton(role: str, origine: str) -> str:
    return json.dumps(
        {"cookies": [],
         "origins": [{"origin": origine,
                      "localStorage": [{"name": "access_token", "value": f"jeton-{role}"}]}]}
    )


def _produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance,
    parcours: dict[str, tuple[str, ...]], etats: dict[str, str],
    declares: tuple[str, ...] | None = None,
    croise: bool = False,
) -> Path:
    """Un produit dont EXIGENCES.json déclare ses personas, avec un parcours par entrée de
    `parcours` (nom de persona -> routes navigées) et un storage state par entrée de `etats`."""
    racine = tmp_path / "produit"
    noms = declares if declares is not None else tuple(parcours)
    _ecrire(racine, "forge/EXIGENCES.json",
            json.dumps({"projet": "p", "personas": [n.capitalize() for n in noms]}))
    for nom, routes in parcours.items():
        _ecrire(racine, f"e2e/{nom}.spec.ts", _parcours(nom, *routes))
    if croise:
        # TF-2197 (b) : deux personas déclarés exigent un parcours qui les cite ensemble.
        _ecrire(racine, "e2e/croisement.spec.ts",
                _parcours(f"{noms[0]} agit, {noms[1]} voit", "/tableau"))
    comptes = []
    for role, contenu in etats.items():
        chemin = _ecrire(racine, f"forge/etats/{role}.json", contenu)
        comptes.append(f"{role}={chemin}")
    if comptes:
        monkeypatch.setenv("FORGE_TESTS_QUALIF_STORAGE_STATES", ",".join(comptes))
    monkeypatch.setenv("FORGE_TESTS_QUALIF_URL", instance.url)
    return racine


def _joues(racine: Path) -> dict[str, object]:
    sortie = personas.analyser(racine)
    return {f.id: f for f in sortie.findings if f.id.startswith("joue:")}


# --- VERT : chaque persona joue ses routes sous son identité --------------------------------------
def test_vert_chaque_persona_joue_ses_routes_sous_l_identite_de_son_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",), "admin": ("/tableau", "/admin")},
        {"agent": _etat_cookie("agent-ok"), "admin": _etat_cookie("admin-ok")},
        croise=True,
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    # Le jeu est un ELEMENT de surface par persona, exercé : il compte dans le ratio.
    assert {"joue:admin", "joue:agent"} <= set(sortie.surface["elements_exerces"])
    # Chaque requête a porté l'identité de SON rôle, pas celle d'un autre.
    vus = {(r["chemin"], r["role"]) for r in instance.recus}
    assert ("/tableau", "agent") in vus and ("/admin", "admin") in vus
    assert ("/admin", "agent") not in vus
    # Le pan dit ce qu'il a joué, et ce que le jeu ne voit pas.
    texte = " ".join(sortie.non_juge)
    assert "JEU RÉEL" in texte and "agent" in texte and "admin" in texte
    assert "ni clic ni formulaire ni JavaScript" in texte
    assert "AUCUN parcours" not in texte


def test_le_jeu_ne_fait_que_lire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau", "/api/moi")}, {"agent": _etat_cookie("agent-ok")},
    )
    personas.analyser(racine)
    assert instance.recus, "le jeu doit avoir joint l'instance"
    assert {r["methode"] for r in instance.recus} == {"GET"}


def test_le_rapport_ne_porte_jamais_la_valeur_d_une_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-ok")},
    )
    assert "agent-ok" not in personas.analyser(racine).json()


def test_un_jeton_du_stockage_local_est_rejoue_en_en_tete_d_autorisation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/api/moi",)}, {"agent": _etat_jeton("agent", instance.url)},
    )
    assert personas.analyser(racine).verdict == "PASS"
    assert instance.recus[0]["autorisation"] == "Bearer jeton-agent"


def test_les_redirections_sont_suivies_jusqu_a_la_page_de_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """Sans identité acceptée, /tableau renvoie vers /connexion : la route atterrit sur la mire."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-perime")},
    )
    personas.analyser(racine)
    assert [r["chemin"] for r in instance.recus] == ["/tableau", "/connexion"]


# --- ROUGE : le jeu constate ce que la citation ne voyait pas ------------------------------------
def test_rouge_un_role_refuse_sur_une_route_de_son_parcours_est_un_constat_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau", "/admin"), "admin": ("/admin",)},
        {"agent": _etat_cookie("agent-ok"), "admin": _etat_cookie("admin-ok")},
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    constats = _joues(racine)
    assert set(constats) == {"joue:agent"}, "l'admin joue /admin sans refus : pas de constat"
    constat = constats["joue:agent"]
    assert constat.classe == classes.PARCOURS_PERSONA_REFUSE
    assert "/admin" in constat.message and "403" in constat.message
    assert "agent" in constat.message
    # La route qui passe n'est pas accusée.
    assert "/tableau" not in constat.message


def test_rouge_une_session_perimee_est_un_renvoi_vers_la_mire_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-perime")},
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    message = _joues(racine)["joue:agent"].message
    assert "/tableau" in message and "mire" in message
    assert "/connexion" in message


def test_rouge_une_route_en_erreur_est_un_constat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau", "/panne", "/absente")}, {"agent": _etat_cookie("agent-ok")},
    )
    message = _joues(racine)["joue:agent"].message
    assert "/panne" in message and "500" in message
    assert "/absente" in message and "404" in message


def test_rouge_un_cookie_d_un_autre_domaine_n_est_pas_envoye(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """Un storage state capturé sur un autre site ne vaut pas identité ici."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-ok", domaine="autre.exemple.test")},
    )
    assert personas.analyser(racine).verdict == "FAIL"
    assert all(r["cookie"] is None for r in instance.recus)


def test_rouge_le_rouge_reste_rouge_quand_la_citation_est_verte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """Le volet statique passait : un parcours cite l'agent. Le jeu seul le met en défaut."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/admin",)}, {"agent": _etat_cookie("agent-ok")},
    )
    sortie = personas.analyser(racine)
    assert "persona:agent" in sortie.surface["elements_exerces"]
    assert "joue:agent" in sortie.surface["elements_non_exerces"]
    assert sortie.verdict == "FAIL"


# --- NON JOUÉ : dit, jamais compté ---------------------------------------------------------------
def test_un_persona_sans_identite_n_est_pas_joue_et_n_est_pas_accuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",), "superviseur": ("/tableau",)},
        {"agent": _etat_cookie("agent-ok")},
        croise=True,
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS"
    assert "joue:superviseur" not in sortie.surface["elements_exerces"]
    assert "joue:superviseur" not in sortie.surface["elements_non_exerces"]
    texte = " ".join(sortie.non_juge)
    assert "SANS identité" in texte and "Superviseur" in texte
    assert "FORGE_TESTS_QUALIF_STORAGE_STATES" in texte


def test_un_storage_state_illisible_est_dit_pas_ignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": "{ pas du json"},
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS"
    texte = " ".join(sortie.non_juge)
    assert "« Agent »" in texte and "illisible" in texte
    assert not instance.recus


def test_une_instance_injoignable_n_est_ni_un_succes_ni_un_echec_du_produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-ok")},
    )
    monkeypatch.setenv("FORGE_TESTS_QUALIF_URL", "http://127.0.0.1:1")
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS"
    assert "joue:agent" not in sortie.surface["elements_exerces"]
    assert "joue:agent" not in sortie.surface["elements_non_exerces"]
    assert "INJOIGNABLE" in " ".join(sortie.non_juge)


def test_sans_instance_declaree_rien_n_est_joue_et_le_pan_le_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-ok")},
    )
    monkeypatch.delenv("FORGE_TESTS_QUALIF_URL")
    sortie = personas.analyser(racine)
    assert not instance.recus
    texte = " ".join(sortie.non_juge)
    assert "aucune instance servie déclarée" in texte and "n est PAS réalisé ici" in texte


def test_l_instance_se_lit_aussi_dans_le_fichier_d_audit_du_produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """TF-2161 : la configuration d'audit vit chez le produit, le jeu la lit sans l'environnement"""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-ok")},
    )
    monkeypatch.delenv("FORGE_TESTS_QUALIF_URL")
    _ecrire(racine, authentification.ENV_AUDIT, f"FORGE_TESTS_QUALIF_URL={instance.url}\n")
    assert personas.analyser(racine).verdict == "PASS"
    assert instance.recus


# --- Les routes jouées sont celles que le parcours NAVIGUE ---------------------------------------
def test_les_routes_sont_les_litteraux_de_navigation_du_parcours() -> None:
    brut = (
        "await page.goto('/tableau');\n"
        "await page.goto(\"/admin?vue=liste\");\n"
        "await page.goto(`/clients/${id}`);\n"
        "await page.goto('https://tiers.exemple.test/x');\n"
        "cy.visit('/api/moi');\n"
        "await page.goto('/tableau');\n"
    )
    assert personas.routes_du_parcours(brut) == ["/tableau", "/admin", "/api/moi"]


def test_un_parcours_sans_route_litterale_joue_la_racine_et_le_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance, {"agent": ()}, {"agent": _etat_cookie("agent-ok")},
    )
    _ecrire(
        racine, "e2e/agent.spec.ts",
        "import { test } from '@playwright/test';\n"
        "test('agent', async ({ page }) => { await page.goto(base + chemin); });\n",
    )
    sortie = personas.analyser(racine)
    assert [r["chemin"] for r in instance.recus][:1] == ["/"]
    assert "racine" in " ".join(sortie.non_juge)


def test_le_plafond_de_routes_est_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    routes = tuple(f"/page-{n}" for n in range(personas.PLAFOND_ROUTES + 3))
    racine = _produit(
        tmp_path, monkeypatch, instance, {"agent": routes}, {"agent": _etat_cookie("agent-ok")},
    )
    sortie = personas.analyser(racine)
    assert len({r["chemin"] for r in instance.recus}) == personas.PLAFOND_ROUTES
    assert f"{personas.PLAFOND_ROUTES + 3} routes" in " ".join(sortie.non_juge)


# --- Câblage -------------------------------------------------------------------------------------
def test_le_jeu_se_range_sous_le_persona_dans_les_cahiers() -> None:
    from forge_tests.livrables import surface

    assert surface.sous_chapitre("persona", "joue:approbateur") == ("persona approbateur", True)


def test_la_classe_est_declaree_une_fois() -> None:
    assert classes.PARCOURS_PERSONA_REFUSE in classes.CLASSES


def test_l_environnement_du_processus_n_est_pas_modifie_par_le_jeu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau",)}, {"agent": _etat_cookie("agent-ok")},
    )
    avant = dict(os.environ)
    personas.analyser(racine)
    assert dict(os.environ) == avant


# --- Un GET n'est sûr que par convention ---------------------------------------------------------
def test_une_route_qui_porte_une_action_n_est_pas_jouee_et_est_nommee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    """Jouer `/deconnexion` fermerait la session du compte d'audit : la route est écartée, dite,
    et les autres routes du parcours sont jouées."""
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/tableau", "/deconnexion", "/clients/supprimer")},
        {"agent": _etat_cookie("agent-ok")},
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS"
    assert {r["chemin"] for r in instance.recus} == {"/tableau"}
    texte = " ".join(sortie.non_juge)
    assert "NON JOUÉE(S)" in texte and "/deconnexion" in texte and "/clients/supprimer" in texte


def test_un_parcours_dont_toutes_les_routes_portent_une_action_n_est_pas_joue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance,
        {"agent": ("/logout",)}, {"agent": _etat_cookie("agent-ok")},
    )
    sortie = personas.analyser(racine)
    assert not instance.recus
    assert "joue:agent" not in sortie.surface["elements_exerces"]
    assert "joue:agent" not in sortie.surface["elements_non_exerces"]
    assert "le persona n est pas joué" in " ".join(sortie.non_juge)
