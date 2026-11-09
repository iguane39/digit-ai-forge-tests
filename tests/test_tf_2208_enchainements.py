"""TF-2208 (reste) — rejouer un ENCHAÎNEMENT entre profils, l'identifiant rendu par une étape
alimentant la suivante.

Reste du 06/11/2026 : les actions mutantes à adresse littérale se rejouent profil par profil
(`test_tf_2208_actions_mutantes_par_profil.py`), mais l'enchaînement dont une étape dépend de la
réponse d'une autre (l'opérateur prépare, l'approbateur valide l'identifiant créé, l'agent agit,
l'opérateur voit) ne l'était pas. Il se déclare désormais dans EXIGENCES.json (clé `enchainements`)
et se rejoue étape par étape, sous l'identité de chaque persona.

Une instance de fixture à ÉTAT (serveur HTTP local) rend un identifiant imprévisible à la création ;
seul un appel construit avec CET identifiant peut valider, exécuter puis lire la mission. Sens
prouvés :
  - VERT   — l'enchaînement passe de bout en bout, les adresses suivantes portent l'identifiant
             rendu, chaque changement d'état est suivi de sa contre-épreuve sans identité ;
  - ROUGE  — garde de profil absente (l'opérateur valide à la place de l'approbateur),
             contre-épreuve sans identité ratée, identifiant non rendu (la suite n'est PAS jouée),
             effet non visible ;
  - SANS OPT-IN — aucune mutation ne part vers l'instance ; compte manquant ou déclaration
             invalide :
             l'enchaînement est nommé non rejoué, sans accuser le produit ;
  - RESTE CLASSÉ — un appel dont l'adresse se construit à l'exécution dans le test du produit est
             NOMMÉ, jamais rejoué, et le rapport dit comment le rejouer.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from forge_tests import authentification
from forge_tests.adaptateurs import personas

ROLES = ("operateur", "approbateur", "agent")
CHAINE = "mission-de-la-preparation-a-la-lecture"


class Instance:
    """Une instance à état. POST /api/missions : opérateur seul, rend un identifiant imprévisible.
    POST /api/missions/<id>/valider : approbateur seul. POST /api/missions/<id>/executer : agent
    seul, après validation. GET /api/missions/<id> : tout profil identifié. Les drapeaux fabriquent
    les défauts : `valider_ouvert` (tout profil identifié valide), `executer_anonyme` (aucune
    garde), `sans_id` (la création ne rend pas d'identifiant), `statut_fige` (l'exécution ne
    change pas le statut lu)."""

    def __init__(self) -> None:
        self.recus: list[dict] = []
        self.missions: dict[str, str] = {}
        self.valider_ouvert = self.executer_anonyme = self.sans_id = self.statut_fige = False
        instance = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def _repondre(self, code: int, corps: dict | None = None) -> None:
                brut = json.dumps(corps if corps is not None else {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(brut)))
                self.end_headers()
                self.wfile.write(brut)

            def _traiter(self) -> None:
                longueur = int(self.headers.get("Content-Length") or 0)
                corps = self.rfile.read(longueur).decode() if longueur else ""
                cookie = self.headers.get("Cookie") or ""
                role = next((r for r in ROLES if f"session={r}-ok" in cookie), None)
                chemin = self.path.split("?")[0]
                instance.recus.append({
                    "methode": self.command, "chemin": chemin, "role": role, "corps": corps,
                })
                trouve = re.fullmatch(r"/api/missions/([^/]+)(?:/(valider|executer))?", chemin)
                if chemin == "/":
                    self._repondre(200)
                elif chemin == "/api/missions" and self.command == "POST":
                    if role is None:
                        self._repondre(401)
                    elif role != "operateur":
                        self._repondre(403)
                    else:
                        identifiant = f"mis-{uuid.uuid4().hex[:10]}"
                        instance.missions[identifiant] = "preparee"
                        self._repondre(201, {} if instance.sans_id else {"id": identifiant})
                elif trouve and trouve.group(1) in instance.missions:
                    identifiant, action = trouve.groups()
                    if action == "valider" and self.command == "POST":
                        if role is None:
                            self._repondre(401)
                        elif role != "approbateur" and not instance.valider_ouvert:
                            self._repondre(403)
                        else:
                            instance.missions[identifiant] = "validee"
                            self._repondre(200)
                    elif action == "executer" and self.command == "POST":
                        if role is None and not instance.executer_anonyme:
                            self._repondre(401)
                        elif role not in (None, "agent"):
                            self._repondre(403)
                        elif instance.missions[identifiant] != "validee":
                            self._repondre(409)
                        else:
                            if not instance.statut_fige:
                                instance.missions[identifiant] = "executee"
                            self._repondre(200)
                    elif action is None and self.command == "GET":
                        if role is None:
                            self._repondre(401)
                        else:
                            self._repondre(200, {"id": identifiant,
                                                 "statut": instance.missions[identifiant]})
                    else:
                        self._repondre(405)
                else:
                    self._repondre(404)

            do_POST = do_PUT = do_PATCH = do_DELETE = do_GET = _traiter  # noqa: N815

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

    def mutants(self) -> list[dict]:
        return [r for r in self.recus if r["methode"] != "GET"]


@pytest.fixture
def instance() -> Iterator[Instance]:
    with Instance() as i:
        yield i


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL", "FORGE_TESTS_PARCOURS_MUTANTS"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")


def _etapes(refuse_a: bool = True, attendu: str = "executee") -> list[dict]:
    return [
        {"persona": "Opérateur", "methode": "POST", "route": "/api/missions",
         "corps": {"titre": "Mission d'essai"}, "capture": {"mission": "id"}},
        {"persona": "Approbateur", "methode": "POST", "route": "/api/missions/{mission}/valider",
         **({"refuse_a": ["Opérateur"]} if refuse_a else {})},
        {"persona": "Agent", "methode": "POST", "route": "/api/missions/{mission}/executer"},
        {"persona": "Opérateur", "methode": "GET", "route": "/api/missions/{mission}",
         "attendu": {"statut": attendu}},
    ]


def _produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance,
    etapes: list[dict] | None = None, opt_in: bool = True, comptes: tuple[str, ...] = ROLES,
    enchainements: list[dict] | None = None, parcours_extra: str = "",
) -> Path:
    """Un produit à trois personas dont un parcours croisé les cite, et un enchaînement déclaré."""
    racine = tmp_path / "produit"
    (racine / "forge").mkdir(parents=True)
    (racine / "e2e").mkdir()
    declarations = enchainements if enchainements is not None else [
        {"nom": "Mission de la préparation à la lecture", "etapes": etapes or _etapes()}
    ]
    (racine / "forge" / "EXIGENCES.json").write_text(
        json.dumps({"projet": "p", "personas": ["Opérateur", "Approbateur", "Agent"],
                    "enchainements": declarations}),
        encoding="utf-8",
    )
    (racine / "e2e" / "mission.spec.ts").write_text(
        "import { test } from '@playwright/test';\n"
        "test('operateur approbateur agent', async ({ page }) => {\n  await page.goto('/');\n"
        + parcours_extra + "});\n",
        encoding="utf-8",
    )
    liste = []
    for role in comptes:
        etat = racine / "forge" / f"{role}.json"
        etat.write_text(json.dumps(
            {"cookies": [{"name": "session", "value": f"{role}-ok", "domain": "127.0.0.1",
                          "path": "/"}], "origins": []}
        ), encoding="utf-8")
        liste.append(f"{role}={etat}")
    monkeypatch.setenv("FORGE_TESTS_QUALIF_STORAGE_STATES", ",".join(liste))
    monkeypatch.setenv("FORGE_TESTS_QUALIF_URL", instance.url)
    if opt_in:
        monkeypatch.setenv("FORGE_TESTS_PARCOURS_MUTANTS", "1")
    return racine


def _constat(sortie, identifiant: str):
    return next((f for f in sortie.findings if f.id == identifiant), None)


# --- VERT -----------------------------------------------------------------------------------------
def test_vert_l_identifiant_rendu_par_une_etape_alimente_la_suivante_de_bout_en_bout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(tmp_path, monkeypatch, instance)
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert f"enchaine:{CHAINE}" in sortie.surface["elements_exerces"]
    assert len(instance.missions) == 1
    identifiant, statut = next(iter(instance.missions.items()))
    assert statut == "executee"  # l'effet de l'agent est bien visible
    # Les adresses suivantes portent l'identifiant RENDU par la création (imprévisible).
    chemins = [(r["methode"], r["chemin"], r["role"]) for r in instance.recus
               if r["chemin"].startswith("/api/missions")]
    assert ("POST", "/api/missions", "operateur") in chemins
    assert ("POST", f"/api/missions/{identifiant}/valider", "approbateur") in chemins
    assert ("POST", f"/api/missions/{identifiant}/executer", "agent") in chemins
    assert ("GET", f"/api/missions/{identifiant}", "operateur") in chemins
    # Le corps littéral déclaré est celui qui est envoyé.
    assert json.loads(instance.mutants()[0]["corps"]) == {"titre": "Mission d'essai"}
    texte = " ".join(sortie.non_juge)
    assert "ENCHAÎNEMENT « Mission de la préparation à la lecture » REJOUÉ" in texte
    assert "MODIFIÉE" in texte


def test_vert_les_contre_epreuves_partent_apres_chaque_changement_d_etat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(tmp_path, monkeypatch, instance)
    personas.analyser(racine)
    mutants = [(r["methode"], r["chemin"].rsplit("/", 1)[-1], r["role"])
               for r in instance.mutants()]
    # création (opérateur) puis sans identité ; validation (approbateur) puis sans identité, puis
    # contre-épreuve par profil (opérateur, refusé) ; exécution (agent) puis sans identité.
    assert mutants == [
        ("POST", "missions", "operateur"), ("POST", "missions", None),
        ("POST", "valider", "approbateur"), ("POST", "valider", None),
        ("POST", "valider", "operateur"),
        ("POST", "executer", "agent"), ("POST", "executer", None),
    ]
    assert len(instance.missions) == 1, "la contre-épreuve sans identité ne crée rien"


# --- ROUGE ----------------------------------------------------------------------------------------
def test_rouge_la_garde_de_profil_absente_est_un_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    instance.valider_ouvert = True  # l'opérateur peut valider sa propre mission
    racine = _produit(tmp_path, monkeypatch, instance)
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    constat = _constat(sortie, f"enchaine:{CHAINE}")
    assert constat is not None and "garde de PROFIL absente" in constat.message
    assert "« Opérateur » a obtenu HTTP 200" in constat.message
    assert "étape 2 sur 4" in constat.message
    assert "2 étape(s) suivante(s) NON jouée(s)" in constat.message
    assert not any(r["chemin"].endswith("/executer") for r in instance.recus)


def test_rouge_la_contre_epreuve_sans_identite_ratee_est_une_garde_absente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    instance.executer_anonyme = True
    racine = _produit(tmp_path, monkeypatch, instance)
    constat = _constat(personas.analyser(racine), f"enchaine:{CHAINE}")
    assert constat is not None and "CONTRE-ÉPREUVE ratée" in constat.message
    assert "la garde n'existe pas" in constat.message and "étape 3 sur 4" in constat.message
    assert "POST /api/missions/mis-" in constat.message


def test_rouge_un_identifiant_non_rendu_arrete_l_enchainement_sans_jouer_la_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    instance.sans_id = True
    racine = _produit(tmp_path, monkeypatch, instance)
    sortie = personas.analyser(racine)
    constat = _constat(sortie, f"enchaine:{CHAINE}")
    assert constat is not None
    assert "ne rend pas `id`" in constat.message
    assert "{mission} ne peut pas alimenter" in constat.message
    assert "3 étape(s) suivante(s) NON jouée(s)" in constat.message
    # Aucune adresse n'a été devinée : la suite n'est jamais appelée.
    assert [r["chemin"] for r in instance.recus if r["chemin"].startswith("/api/missions")] == [
        "/api/missions", "/api/missions",
    ]


def test_rouge_l_effet_non_visible_est_un_defaut_de_la_derniere_etape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    instance.statut_fige = True  # l'agent agit, mais l'opérateur ne voit rien changer
    racine = _produit(tmp_path, monkeypatch, instance)
    constat = _constat(personas.analyser(racine), f"enchaine:{CHAINE}")
    assert constat is not None and "`statut` attendu 'executee', lu 'validee'" in constat.message
    assert "étape 4 sur 4" in constat.message and "dernière étape" in constat.message


def test_rouge_une_etape_refusee_au_persona_est_un_defaut_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    etapes = _etapes()
    etapes[1]["persona"] = "Agent"  # l'agent n'a pas le droit de valider
    racine = _produit(tmp_path, monkeypatch, instance, etapes=etapes)
    constat = _constat(personas.analyser(racine), f"enchaine:{CHAINE}")
    assert constat is not None and "étape 2 sur 4" in constat.message
    assert "« Agent »" in constat.message and "403" in constat.message


# --- SANS OPT-IN, COMPTE MANQUANT, DÉCLARATION INVALIDE ---------------------------------------
def test_sans_opt_in_rien_n_est_ecrit_et_l_enchainement_est_nomme_non_rejoue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(tmp_path, monkeypatch, instance, opt_in=False)
    sortie = personas.analyser(racine)
    assert instance.mutants() == [] and instance.missions == {}
    texte = " ".join(sortie.non_juge)
    assert "« Mission de la préparation à la lecture » NON rejoué" in texte
    assert "FORGE_TESTS_PARCOURS_MUTANTS=1" in texte
    assert f"enchaine:{CHAINE}" not in sortie.surface["elements_exerces"]
    assert _constat(sortie, f"enchaine:{CHAINE}") is None  # non joué n'est pas un échec


def test_un_compte_manquant_n_accuse_pas_le_produit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(tmp_path, monkeypatch, instance, comptes=("operateur", "agent"))
    sortie = personas.analyser(racine)
    assert instance.mutants() == []
    assert _constat(sortie, f"enchaine:{CHAINE}") is None
    texte = " ".join(sortie.non_juge)
    assert "NON rejoué — aucun compte exploitable pour Approbateur" in texte


@pytest.mark.parametrize(
    ("modification", "motif"),
    [
        (lambda e: e[1].update(persona="Inconnu"), "persona « Inconnu » non déclaré"),
        (lambda e: e[1].update(methode="FETCH"), "méthode « FETCH » inconnue"),
        (lambda e: e[1].update(route="api/sans-barre"), "`route` doit être une adresse"),
        (lambda e: e[0].update(capture={}), "{mission} n'est capturé par aucune étape précédente"),
        (lambda e: e[1].update(refuse_a=["Fantôme"]), "`refuse_a` nomme « Fantôme »"),
    ],
    ids=["persona", "methode", "route", "variable-non-capturee", "refuse-a"],
)
def test_une_declaration_invalide_est_nommee_et_rien_n_est_joue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance, modification, motif
) -> None:
    etapes = _etapes()
    modification(etapes)
    racine = _produit(tmp_path, monkeypatch, instance, etapes=etapes)
    sortie = personas.analyser(racine)
    assert instance.mutants() == []
    texte = " ".join(sortie.non_juge)
    assert "NON rejoué — déclaration invalide" in texte and motif in texte


# --- RESTE CLASSÉ : les appels construits à l'exécution ---------------------------------------
def test_un_appel_construit_a_l_execution_est_nomme_jamais_rejoue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(
        tmp_path, monkeypatch, instance, enchainements=[],
        parcours_extra=(
            "  const creee = await request.post('/api/missions', { data: {} });\n"
            "  const { id } = await creee.json();\n"
            "  await request.post(`/api/missions/${id}/valider`);\n"
            "  await request.post('/api/missions/' + id + '/executer');\n"
        ),
    )
    sortie = personas.analyser(racine)
    texte = " ".join(sortie.non_juge)
    assert "2 appel(s) mutant(s) dont l'adresse est CONSTRUITE À L'EXÉCUTION" in texte
    assert "POST /api/missions/${id}/valider" in texte
    assert "POST /api/missions/…" in texte
    assert "DÉCLARER comme étapes d'un enchaînement" in texte
    assert "aucun ENCHAÎNEMENT entre profils déclaré" in texte
    # seul l'appel à adresse LITTÉRALE a été rejoué (sous l'identité, puis sans identité)
    assert {r["chemin"] for r in instance.mutants()} == {"/api/missions"}


def test_sans_aucun_appel_construit_le_rapport_ne_l_invente_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: Instance
) -> None:
    racine = _produit(tmp_path, monkeypatch, instance)
    texte = " ".join(personas.analyser(racine).non_juge)
    assert "CONSTRUITE À L'EXÉCUTION" not in texte


# --- LECTURE --------------------------------------------------------------------------------------
def test_lecture_des_formes_d_adresse_construite() -> None:
    texte = (
        "await request.post(`/api/a/${id}/b`);\n"
        "await page.request.patch('/api/c/' + id);\n"
        "cy.request('DELETE', `/api/d/${x}`);\n"
        "await request.post('/api/litterale', { data: {} });\n"
        "await request.post(`/api/a/${id}/b`);\n"
    )
    assert personas.appels_construits(texte) == [
        "POST /api/a/${id}/b", "PATCH /api/c/…", "DELETE /api/d/${x}",
    ]


def test_une_adresse_concatenee_n_est_pas_rejouee_tronquee() -> None:
    """Rouge sur l'état précédent : `'/api/missions/' + id` était lue comme la route littérale
    `/api/missions/` et rejouée telle quelle, une adresse que le test ne vise pas."""
    texte = (
        "await request.post('/api/missions/' + id + '/executer');\n"
        "await request.post('/api/missions', { data: {} });\n"
    )
    assert [(a["methode"], a["route"]) for a in personas.actions_mutantes(texte)] == [
        ("POST", "/api/missions"),
    ]


def test_lecture_d_un_chemin_json_et_substitution() -> None:
    assert personas._valeur_json({"data": {"items": [{"id": 7}]}}, "data.items.0.id") == 7
    assert personas._valeur_json({"a": 1}, "b") is personas._ABSENT
    assert personas._valeur_json([1], "3") is personas._ABSENT
    variables = {"mission": "a/b c"}
    # dans une adresse, la valeur rendue est un SEGMENT : elle ne peut pas changer le chemin appelé
    assert personas._substituer("/api/{mission}/x", variables, True) == "/api/a%2Fb%20c/x"
    assert personas._substituer({"ref": ["{mission}", 3]}, variables) == {"ref": ["a/b c", 3]}


def test_la_classification_partagee_garde_le_comportement_des_actions_isolees() -> None:
    classer = personas._classer_reponse
    assert classer(201, "", "http://x/api", set()) == ("ok", "201")
    assert classer(403, "", "http://x/api", set()) == ("refuse", "403")
    assert classer(404, "", "http://x/api", {404}) == ("ok", "404")
    assert classer(500, "", "http://x/api", set()) == ("erreur", "500")
    assert classer(302, "/login", "http://x/api", set())[0] == "mire"


def test_un_enchainement_se_range_sous_son_propre_sous_chapitre_du_cahier() -> None:
    from forge_tests.livrables import surface

    assert surface.sous_chapitre("persona", f"enchaine:{CHAINE}") == (
        f"enchaînement {CHAINE}", True,
    )
