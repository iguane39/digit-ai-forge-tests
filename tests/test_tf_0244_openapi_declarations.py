"""TF-0244 — les codes DÉCLARÉS se lisent dans `app.openapi()`, plus dans une regex de source.

Fait mesuré le 15/08/2026 (lot 20260815a, ledger seq 17). Le pan `api` établissait la liste des
codes « déclarés à la main » en passant une expression régulière sur `backend/app/main.py`. Deux
angles morts, et ils se sont produits ENSEMBLE sur le même produit :

  - le fichier n existait pas — projet à racine plate (`app/` à la racine, TF-0216) : la lecture
    rendait un ensemble vide, et TOUS les constats du pan étaient localisés dans un chemin
    inexistant, donc invérifiables par qui les recevait ;
  - le motif ne voit ni `@router.…`, ni un `responses=` qu un argument multiligne referme avant
    lui. Un 422 pourtant déclaré ressortait donc « émis par l application mais absent de sa
    déclaration responses= » : un faux constat `manuelle_dev`, et une contestation RT-18 à
    instruire — retenue, puisque `app.openapi()` prouvait la déclaration.

La correction fait foi au schéma (règle R3, comme le reste de l inventaire de ce pan). Elle
suppose de savoir distinguer, DANS le schéma, le 422 que FastAPI ajoute d office de celui que le
projet a écrit : c est l objet de `_422_du_cadre`, et c est vérifié ici contre un vrai FastAPI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import api

# --- 1. Reproduction : ce que la lecture de source ne pouvait PAS voir --------------------------

SOURCE_MULTILIGNE = '''\
from fastapi import APIRouter, Depends, FastAPI

app = FastAPI()


@app.post(
    "/factures",
    dependencies=[
        Depends(exige_role)
    ],
    responses={
        409: {"description": "doublon"},
        422: {"description": "corps invalide"},
    },
)
async def creer_facture(corps: dict) -> dict:
    return corps
'''


def test_reproduction_la_regex_perd_un_responses_referme_par_un_argument_multiligne() -> None:
    """L origine du défaut, inchangée et assumée : le motif s arrête à la première parenthèse
    fermée en fin de ligne. `Depends(exige_role)` en referme une AVANT `responses=` — la route
    est bien reconnue, mais ses deux codes déclarés deviennent invisibles."""
    trouves = api._ROUTE.findall(SOURCE_MULTILIGNE)

    assert [(m, c) for m, c, _ in trouves] == [("post", "/factures")]
    assert api._CODE.findall(trouves[0][2]) == []  # ni le 409, ni le 422


def test_reproduction_la_regex_ne_connait_pas_les_routeurs() -> None:
    """Le second angle mort, celui du produit du 15/08 : `@router.get` n est pas `@app.get`."""
    assert api._ROUTE.findall('@router.get("/factures", responses={404: {}})\ndef l(): ...\n') == []


# --- 2. Le schéma fait foi : le 422 déclaré est reconnu, celui du cadre ne l est pas ------------


try:  # FastAPI n est pas une dépendance de la forge : son absence dégrade, elle ne casse pas.
    from fastapi import APIRouter, FastAPI
    from pydantic import BaseModel

    class Facture(BaseModel):
        """Modèle au niveau MODULE : pydantic refuse de résoudre un modèle local à une
        fonction, et le schéma ne se construirait pas."""

        montant: float

    class ErreurMaison(BaseModel):
        detail: str

    _FASTAPI = True
except ImportError:  # pragma: no cover — dépend du poste, jamais du code de la forge
    _FASTAPI = False

besoin_fastapi = pytest.mark.skipif(
    not _FASTAPI, reason="le contrat porte sur le schéma que FastAPI produit lui-même"
)


def _app_reelle():
    """Une application FastAPI RÉELLE, à routeur monté sous préfixe et décorateur multiligne.

    Le cœur de la correction est une propriété du schéma que FastAPI produit — la forme exacte
    de son 422 automatique. La vérifier contre un schéma écrit à la main prouverait seulement
    que le test est d accord avec lui-même."""
    application = FastAPI()
    routeur = APIRouter()

    @routeur.post(
        "/factures",
        responses={
            409: {"description": "doublon"},
            422: {"description": "corps invalide"},
        },
    )
    def creer(corps: Facture) -> dict:  # pragma: no cover — jamais appelée, seul le schéma sert
        return {}

    @routeur.put("/factures/{ident}", responses={422: {"model": ErreurMaison}})
    def remplacer(ident: int, corps: Facture) -> dict:  # pragma: no cover
        return {}

    @routeur.post("/ventilation")
    def ventiler(corps: Facture) -> dict:  # pragma: no cover — 422 AUTOMATIQUE, non déclaré
        return {}

    application.include_router(routeur, prefix="/api/v1")
    return application


@besoin_fastapi
def test_le_422_du_CADRE_est_reconnu_et_reste_hors_inventaire() -> None:
    """Non-régression de la raison d être du filtre : le 422 que personne n a écrit ne doit pas
    être exigé de la suite — l exiger accuserait d un trou qui n existe pas."""
    schema = _app_reelle().openapi()
    auto = schema["paths"]["/api/v1/ventilation"]["post"]["responses"]["422"]

    assert api._422_du_cadre(auto) is True


@besoin_fastapi
def test_un_422_ECRIT_PAR_LE_PROJET_est_discernable_dans_le_schema() -> None:
    """Le fait contesté au run du 15/08, tranché sur la source qui fait foi : une description
    ou un modèle propres suffisent à distinguer la promesse du projet de celle du cadre."""
    chemins = _app_reelle().openapi()["paths"]

    par_description = chemins["/api/v1/factures"]["post"]["responses"]["422"]
    par_modele = chemins["/api/v1/factures/{ident}"]["put"]["responses"]["422"]

    assert api._422_du_cadre(par_description) is False
    assert api._422_du_cadre(par_modele) is False


@besoin_fastapi
def test_le_cas_MULTILIGNE_entre_desormais_a_l_inventaire(tmp_path: Path, monkeypatch) -> None:
    """Bout en bout du défaut : là où la regex ne voyait ni le 409 ni le 422 déclarés, le pan
    les inventorie — et n exige toujours pas le 422 que le cadre a ajouté seul."""
    projet = tmp_path / "compta"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "main.py").write_text(SOURCE_MULTILIGNE, encoding="utf-8")
    schema = _app_reelle().openapi()
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: schema)

    codes = {e.id for e in api.inventaire(projet) if e.id.startswith("code:")}

    assert "code:POST /api/v1/factures=409" in codes
    assert "code:POST /api/v1/factures=422" in codes  # déclaré : exigé
    assert "code:PUT /api/v1/factures/{}=422" in codes  # déclaré par modèle : exigé
    assert "code:POST /api/v1/ventilation=422" not in codes  # ajouté par le cadre : non exigé


# --- 3. La localisation : un constat s ouvre, sinon il ne se vérifie pas ------------------------


def _projet_racine_plate(tmp_path: Path) -> Path:
    """La disposition du produit du 15/08 : `app/` à la racine, routeur dans son module, et
    AUCUN `backend/app/main.py`."""
    projet = tmp_path / "compta-sfr"
    (projet / "app" / "api").mkdir(parents=True)
    (projet / "app" / "__init__.py").write_text("", encoding="utf-8")
    (projet / "app" / "api" / "__init__.py").write_text("", encoding="utf-8")
    (projet / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.api import routes_factures\n\n"
        "app = FastAPI()\n"
        'app.include_router(routes_factures.routeur, prefix="/api/v1")\n',
        encoding="utf-8",
    )
    (projet / "app" / "api" / "routes_factures.py").write_text(
        "from fastapi import APIRouter\n\n"
        "routeur = APIRouter()\n\n\n"
        '@routeur.post("/factures", responses={409: {"description": "doublon"}})\n'
        "def creer(corps: dict) -> dict:\n"
        "    return corps\n\n\n"
        '@routeur.put("/factures/{ident}")\n'
        "def remplacer(ident: int, corps: dict) -> dict:\n"
        "    return corps\n",
        encoding="utf-8",
    )
    assert not (projet / "backend").exists()
    return projet


def test_le_module_principal_est_DECOUVERT_et_existe(tmp_path: Path) -> None:
    """Le socle de toute la localisation : `backend/app/main.py` était supposé — ici il n existe
    pas, et un constat qui le désigne envoie le lecteur ouvrir un fichier absent."""
    projet = _projet_racine_plate(tmp_path)

    principal = api._module_principal(projet)

    assert principal == projet / "app" / "main.py"
    assert principal.is_file()


@besoin_fastapi
def test_un_constat_designe_le_MODULE_DU_ROUTEUR_qui_declare_la_route(
    tmp_path: Path, monkeypatch
) -> None:
    """Le préfixe de montage (`/api/v1`) empêche toute correspondance exacte : le chemin du
    décorateur est un SUFFIXE de celui que le schéma publie. C est la disposition la plus
    répandue — la localisation doit y marcher, pas s y rendre."""
    projet = _projet_racine_plate(tmp_path)
    schema = _app_reelle().openapi()
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: schema)
    attendu = str(projet / "app" / "api" / "routes_factures.py")

    par_id = {e.id: e.source for e in api.inventaire(projet)}

    assert par_id["endpoint:POST /api/v1/factures"] == attendu
    assert par_id["code:POST /api/v1/factures=409"] == attendu
    assert par_id["endpoint:PUT /api/v1/factures/{}"] == attendu


@besoin_fastapi
def test_une_route_que_la_source_ne_declare_pas_retombe_sur_un_fichier_QUI_EXISTE(
    tmp_path: Path, monkeypatch
) -> None:
    """Le sens rouge : ne jamais inventer une localisation. `/api/v1/ventilation` est publiée par
    le schéma mais absente des sources de ce projet — le constat retombe sur le module principal
    découvert, jamais sur un `backend/app/main.py` supposé."""
    projet = _projet_racine_plate(tmp_path)
    schema = _app_reelle().openapi()
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: schema)

    par_id = {e.id: e.source for e in api.inventaire(projet)}

    assert par_id["endpoint:POST /api/v1/ventilation"] == str(projet / "app" / "main.py")
    assert Path(par_id["endpoint:POST /api/v1/ventilation"]).is_file()


def test_deux_fichiers_en_concurrence_ne_se_departagent_PAS_au_hasard() -> None:
    """Une localisation ambiguë est une localisation qu on ne rend pas : mieux vaut le module
    principal, vrai mais générique, qu un fichier nommé par tirage."""
    par_route = {
        ("POST", "/factures"): "a.py",
        ("POST", "/v2/factures"): "b.py",
    }

    assert api._localiser("POST", "/api/v1/factures", par_route, "defaut.py") == "a.py"
    assert (
        api._localiser("POST", "/x/factures", {("POST", "/factures"): "a.py",
                                              ("POST", "/actures"): "b.py"}, "defaut.py")
        == "a.py"
    )
    assert api._localiser("POST", "/inconnue", par_route, "defaut.py") == "defaut.py"


# --- 4. Le secours est DIT quand on y retombe --------------------------------------------------
def test_sans_schema_le_recours_a_la_regex_est_PUBLIE(tmp_path: Path, monkeypatch) -> None:
    """« La regex peut rester en secours si le schéma est indisponible, EN LE DISANT » : sous ce
    régime, un constat de divergence peut dénoncer la lecture plutôt que le projet, et qui le
    reçoit doit pouvoir le savoir avant d ouvrir un cycle de correction."""
    projet = _projet_racine_plate(tmp_path)
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: None)
    monkeypatch.setattr(api, "exerces", lambda _cible: set())

    sortie = api.analyser(projet)

    assert api.NON_JUGE_SANS_SCHEMA in sortie.non_juge
    assert api.NON_JUGE_422 not in sortie.non_juge


@besoin_fastapi
def test_avec_schema_la_limite_du_422_indiscernable_est_PUBLIEE(
    tmp_path: Path, monkeypatch
) -> None:
    """Le pendant : quand le schéma fait foi, la seule zone d ombre qui reste — un 422 déclaré
    à l identique du 422 du cadre — est nommée plutôt que tue."""
    projet = _projet_racine_plate(tmp_path)
    monkeypatch.setattr(api, "schema_openapi", lambda _cible: _app_reelle().openapi())
    monkeypatch.setattr(api, "exerces", lambda _cible: set())

    sortie = api.analyser(projet)

    assert api.NON_JUGE_422 in sortie.non_juge
    assert api.NON_JUGE_SANS_SCHEMA not in sortie.non_juge
