"""TF-0217 (RT-3, lot COMPTA 20260814a) — a11y et visuel étaient aveugles au rendu SERVEUR.

Fait mesuré sur le run `20260814-tests-sfr` (ledger seq 11) : l application auditée est un
FastAPI + Jinja **à racine plate** — les gabarits sont servis par le backend, il n existe ni
`frontend/src/routes.jsx`, ni convention TanStack, ni `<Route path=…>`. Les deux pans lisant le
seul inventaire de `front.py`, ils concluaient « aucune route » — alors que
`FORGE_TESTS_BASE_URL` était SERVIE et que le pan `qualif` venait d y parcourir 33 puis 42
éléments. Deux pans perdus pour toute application rendue côté serveur.

Ce que ces tests fixent :

  1. **le point de partage** — une seule fonction de découverte, `accessibilite.routes_a_auditer`,
     que `visuel` appelle (il importait déjà `_capturer` du même module). Trois sources ordonnées
     et NOMMÉES : sources du front, déclaration du projet (`FORGE_TESTS_QUALIF_ROUTES`), liens de
     l instance servie. Aucune dépendance circulaire : `qualif` n importe ni l un ni l autre, et
     seules ses fonctions PURES (`_route`, `_JS_LIENS`) sont réutilisées ;

  2. **l arbitrage quand rien n est découvrable** — NA (sans objet) si rien ne peut rendre une
     page, SKIP si quelque chose le pourrait. Un projet sans `frontend/`, sans instance servie et
     sans route déclarée n a pas d accessibilité : ce n est pas un trou de mesure. Mais une
     instance SERVIE dont aucune route ne se découvre reste un NON MESURABLE, donc un manque.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests.adaptateurs import accessibilite, visuel

BASE = "https://compta-qualif.exemple.test"


@pytest.fixture()
def env_propre():
    """`charger_env` écrit dans `os.environ` : sans restauration, un test verrait la config d un
    autre — et l arbitrage NA/SKIP dépend précisément de ce qui est déclaré."""
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _projet_jinja(tmp_path: Path) -> Path:
    """Le cas réel : FastAPI + gabarits Jinja, racine plate, AUCUN dossier `frontend`."""
    projet = tmp_path / "compta-sfr"
    (projet / "app" / "gabarits").mkdir(parents=True)
    (projet / "app" / "main.py").write_text("app = FastAPI()\n", encoding="utf-8")
    (projet / "app" / "gabarits" / "factures.html").write_text(
        "{% extends 'base.html' %}", encoding="utf-8"
    )
    assert not (projet / "frontend").exists()
    return projet


def _projet_react(tmp_path: Path) -> Path:
    projet = tmp_path / "spa"
    (projet / "frontend" / "src").mkdir(parents=True)
    (projet / "frontend" / "src" / "routes.jsx").write_text(
        'const r = [{ path: "/" }, { path: "/factures" }];\n', encoding="utf-8"
    )
    return projet


class _PageFactice:
    """Double minimal d une page Playwright : navigation + relevé des liens, sans navigateur."""

    def __init__(self, hrefs: list[str], echoue: bool = False) -> None:
        self._hrefs, self._echoue = hrefs, echoue
        self.urls_visitees: list[str] = []

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None) -> None:
        self.urls_visitees.append(url)
        if self._echoue:
            raise RuntimeError("instance injoignable")

    def evaluate(self, _script: str) -> list[str]:
        return list(self._hrefs)


# --- 1. Le défaut constaté : une app Jinja servie n avait AUCUNE route -------------------------
def test_reproduction_le_pan_front_ne_voit_rien_sur_une_app_jinja(tmp_path: Path) -> None:
    """L origine du défaut, inchangée et assumée : `front.py` lit du code React, pas des gabarits.

    C est pour cela que la découverte ne pouvait pas rester chez lui."""
    from forge_tests.adaptateurs.front import inventaire

    assert [e for e in inventaire(_projet_jinja(tmp_path)) if e.id.startswith("route:")] == []


def test_les_routes_declarees_par_le_projet_ouvrent_les_deux_pans(
    tmp_path: Path, env_propre
) -> None:
    """Correctif proposé par le produit : `FORGE_TESTS_QUALIF_ROUTES`, le champ du pan qualif —
    un projet ne renseigne pas deux listes pour la même application."""
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/factures, /ventilation ,rapports/mensuel"

    routes, provenance = accessibilite.routes_a_auditer(projet)

    assert routes == ["/factures", "/ventilation", "/rapports/mensuel"]
    assert provenance == accessibilite.PROVENANCE_DECLAREE


def test_a_defaut_de_declaration_les_routes_sont_RELEVEES_sur_l_instance_servie(
    tmp_path: Path, env_propre, monkeypatch
) -> None:
    """Le cas du lot : BASE_URL servie, rien de déclaré — les liens de la racine font l inventaire.

    Même normalisation que le parcours `qualif` : c est ce qui garantit que les deux pans parlent
    des mêmes routes que celles déjà parcourues sur cette instance.
    """
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    page = _PageFactice(
        [
            "/factures",
            "/factures",  # doublon : dédupliqué
            "ventilation",  # relatif
            "https://sfr.example.com/aide",  # externe : écarté
            "mailto:compta@exemple.test",  # non navigable : écarté
            "#contenu",  # ancre : écartée
        ]
    )
    servies = accessibilite._routes_servies  # le navigateur est le seul élément remplacé
    monkeypatch.setattr(
        accessibilite, "_routes_servies", lambda cible, base: servies(cible, base, page=page)
    )

    routes, provenance = accessibilite.routes_a_auditer(projet)

    assert routes == ["/", "/factures", "/ventilation"]
    assert provenance == accessibilite.PROVENANCE_SERVIE
    assert page.urls_visitees == [f"{BASE}/"]


def test_le_releve_des_liens_est_une_fonction_pure_donc_verifiable() -> None:
    hrefs = ["/a", "b", "/a?tri=date", "https://ailleurs.test/x", "javascript:void(0)", "/"]
    assert accessibilite._routes_depuis_liens(hrefs, BASE) == ["/", "/a", "/b"]


def test_une_instance_injoignable_ne_leve_jamais_et_ne_rend_aucune_route(
    tmp_path: Path, env_propre
) -> None:
    """Et surtout : elle n invente pas une route `/` qui ne répond pas — sans quoi les deux pans
    partiraient capturer une instance morte et l imputeraient au produit."""
    page = _PageFactice([], echoue=True)
    assert accessibilite._routes_servies(_projet_jinja(tmp_path), BASE, page=page) == []


def test_une_racine_atteinte_mais_sans_aucun_lien_reste_une_route(
    tmp_path: Path, env_propre
) -> None:
    """Sens inverse du test précédent : la page racine EST une page à auditer."""
    page = _PageFactice([])
    assert accessibilite._routes_servies(_projet_jinja(tmp_path), BASE, page=page) == ["/"]


def test_l_instance_n_est_parcourue_QU_UNE_FOIS_par_run(
    tmp_path: Path, env_propre, monkeypatch
) -> None:
    """Un audit ouvre l inventaire plusieurs fois (a11y, visuel, livrables). Lire un `routes.jsx`
    était gratuit ; ouvrir un navigateur ne l est pas — la découverte servie se mémorise."""
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    parcours: list[str] = []

    def _parcours_compte(cible: Path, base: str) -> list[str]:
        parcours.append(base)
        return ["/", "/factures"]

    monkeypatch.setattr(accessibilite, "_PARCOURS_MEMOIRE", {})
    monkeypatch.setattr(accessibilite, "_parcourir_racine", _parcours_compte)

    assert accessibilite.routes_a_auditer(projet)[0] == ["/", "/factures"]
    assert visuel.inventaire(projet)[0].id == "visuel:/"
    assert accessibilite.inventaire(projet)[0].id == "a11y:/"

    assert parcours == [BASE]


def test_deux_projets_du_meme_processus_ne_se_pretent_pas_leurs_routes(
    tmp_path: Path, env_propre, monkeypatch
) -> None:
    """Sens rouge de la mémoire : la clé porte la cible ET l instance."""
    monkeypatch.setattr(accessibilite, "_PARCOURS_MEMOIRE", {})
    monkeypatch.setattr(
        accessibilite, "_parcourir_racine", lambda cible, base: [f"/{Path(cible).name}"]
    )
    os.environ["FORGE_TESTS_BASE_URL"] = BASE

    premier = accessibilite._routes_servies(tmp_path / "un", BASE)
    second = accessibilite._routes_servies(tmp_path / "deux", BASE)

    assert (premier, second) == (["/un"], ["/deux"])


def test_les_sources_du_front_priment_sur_tout_le_reste(tmp_path: Path, env_propre) -> None:
    """Non-régression : un projet React continue d être inventorié depuis son code, et la
    déclaration ne peut pas lui substituer une liste écrite à la main."""
    projet = _projet_react(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/ailleurs"

    routes, provenance = accessibilite.routes_a_auditer(projet)

    assert routes == ["/", "/factures"]
    assert provenance == accessibilite.PROVENANCE_FRONT


# --- 2. Le point de partage : les deux pans voient la MÊME surface ------------------------------
def test_accessibilite_et_visuel_inventorient_les_memes_routes(
    tmp_path: Path, env_propre
) -> None:
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/factures,/ventilation"

    a11y = [e.id.split(":", 1)[1] for e in accessibilite.inventaire(projet)]
    rendu = [e.id.split(":", 1)[1] for e in visuel.inventaire(projet)]

    assert a11y == rendu == ["/factures", "/ventilation"]


def test_la_source_publiee_designe_la_provenance_reelle(tmp_path: Path, env_propre) -> None:
    """Publier `frontend/src/routes.jsx` pour une app Jinja désignait un fichier inexistant :
    le constat devenait invérifiable."""
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/factures"

    assert accessibilite.inventaire(projet)[0].source == "FORGE_TESTS_QUALIF_ROUTES"
    assert visuel.inventaire(projet)[0].source == "FORGE_TESTS_QUALIF_ROUTES"
    assert accessibilite.inventaire(_projet_react(tmp_path))[0].source.endswith("routes.jsx")


def test_aucune_dependance_circulaire_entre_adaptateurs() -> None:
    """Contrainte de méthode du mandat. Le sens est `visuel` → `accessibilite` → {front, qualif} ;
    `qualif` ne remonte vers aucun des deux — vérifié sur le texte du module, pas supposé."""
    source = Path(
        accessibilite.__file__
    ).with_name("qualif.py").read_text(encoding="utf-8")
    assert "adaptateurs.accessibilite" not in source
    assert "adaptateurs.visuel" not in source


def test_l_app_jinja_est_desormais_AUDITEE_de_bout_en_bout(
    tmp_path: Path, env_propre, monkeypatch
) -> None:
    """Bout en bout : là où le pan sortait « aucune route », il rend un verdict et publie sa
    provenance. Les captures sont stubbées — c est la découverte qui est en cause, pas Chromium."""
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    os.environ["FORGE_TESTS_QUALIF_ROUTES"] = "/factures,/ventilation"

    def _capturer_stub(cible: Path, routes: list[str], dossier: Path):
        captures = {}
        for route in routes:
            fichier = dossier / (route.strip("/").replace("/", "_") + ".html")
            fichier.write_text(f"<html><body><h1>{route}</h1></body></html>", encoding="utf-8")
            captures[route] = fichier
        return captures, []

    monkeypatch.setattr(accessibilite, "_capturer", _capturer_stub)
    monkeypatch.setattr(accessibilite, "_juger", lambda capture: {"non_juge": [], "findings": []})

    sortie = accessibilite.analyser(projet)

    assert sortie.verdict == "PASS"
    assert "accessibilite : routes auditees — /factures, /ventilation" in sortie.non_juge
    assert any(accessibilite.PROVENANCE_DECLAREE in ligne for ligne in sortie.non_juge)


# --- 3. L arbitrage déclaré quand aucune route n est découvrable --------------------------------
def test_un_projet_qui_ne_rend_RIEN_est_sans_objet_et_le_PROUVE(
    tmp_path: Path, env_propre
) -> None:
    """Le choix retenu : ni `frontend/`, ni instance servie, ni route déclarée → NA, pas SKIP.
    Un lot batch ou une bibliothèque n a pas d accessibilité — ce n est pas un manque."""
    projet = _projet_jinja(tmp_path)

    for sortie in (accessibilite.analyser(projet), visuel.analyser(projet)):
        assert sortie.verdict == "NA"
        # Le motif est le DERNIER non_juge : c est celui que `noyau.rapport` publie.
        assert "SANS OBJET" in sortie.non_juge[-1]
        assert "FORGE_TESTS_BASE_URL" in sortie.non_juge[-1]


def test_une_instance_SERVIE_sans_route_reste_un_non_mesurable(
    tmp_path: Path, env_propre, monkeypatch
) -> None:
    """Le sens rouge de l arbitrage : quelque chose est servi, donc il y a bien un sujet.
    Le taire en NA ferait disparaître un pan qui a pourtant de quoi être audité."""
    projet = _projet_jinja(tmp_path)
    os.environ["FORGE_TESTS_BASE_URL"] = BASE
    monkeypatch.setattr(accessibilite, "_routes_servies", lambda cible, base, page=None: [])

    for sortie in (accessibilite.analyser(projet), visuel.analyser(projet)):
        assert sortie.verdict == "SKIP"
        # Et le motif est ACTIONNABLE : il nomme le champ à renseigner.
        assert "FORGE_TESTS_QUALIF_ROUTES" in sortie.non_juge[-1]


def test_un_dossier_VIDE_n_est_jamais_sans_objet(tmp_path: Path, env_propre) -> None:
    """La condition qui empêche NA de devenir un vert de complaisance : un dossier sans code ne
    prouve pas qu il n y a rien à rendre — il prouve qu on n a rien regardé (cible mal désignée,
    sources ailleurs). Ce cas reste un SKIP, comme l inventaire vide du noyau."""
    assert accessibilite.sans_objet(tmp_path) is None
    assert accessibilite.analyser(tmp_path).verdict == "SKIP"
    assert visuel.analyser(tmp_path).verdict == "SKIP"


def test_un_frontend_present_mais_muet_reste_un_non_mesurable(
    tmp_path: Path, env_propre
) -> None:
    """Un `frontend/` sans route lisible est un routeur non reconnu, pas une absence de front."""
    projet = tmp_path / "spa-muette"
    (projet / "frontend" / "src").mkdir(parents=True)

    assert accessibilite.sans_objet(projet) is None
    assert accessibilite.analyser(projet).verdict == "SKIP"


def test_le_pan_NA_sort_du_calcul_de_couverture_sans_disparaitre(
    tmp_path: Path, env_propre
) -> None:
    """L effet attendu au rapport : un pan sans objet ne rend plus l audit PARTIEL, et reste
    NOMMÉ avec sa preuve d absence."""
    from forge_tests.noyau import rapport

    projet = _projet_jinja(tmp_path)
    sorties = [accessibilite.analyser(projet), visuel.analyser(projet)]

    r = rapport(sorties, ["accessibilite", "visuel"])

    assert r["pans_non_couverts"] == []
    assert [e["pan"] for e in r["pans_sans_objet"]] == ["accessibilite", "visuel"]
    assert r["verdict"] == "PASS"


def test_visuel_n_ecrit_toujours_rien_chez_l_audite_quand_il_n_y_a_rien_a_capturer(
    tmp_path: Path, env_propre
) -> None:
    """G-1, non-régression : `.visuel/` ne doit pas naître d un pan qui va conclure NA."""
    projet = _projet_jinja(tmp_path)

    assert visuel.analyser(projet).verdict == "NA"
    assert not (projet / visuel.DOSSIER).exists()
