"""TF-0371 — ce que le code APPELLE et RÉFÉRENCE, contre ce que l'instance SERT.

Deux défauts mesurés en direct le 18/08 sur l'instance dev de BAV2, qu'aucun parcours ne
pouvait voir, et qui sont rejoués ici tels quels :

  (a) le blueprint `push_subscriptions` absent des `endpoint_modules` de l'hôte déployé →
      `GET /api/c13s/vapid/public-key` rend 404, alors que le front l'appelle. Toute une
      fonction morte en production (anomalie 9858, ouverte le 29/07) ;
  (b) `url(src/assets/images/placeholder-image.jpg)` dans une feuille servie sous `/assets/`,
      résolue par le navigateur en `/assets/src/assets/images/…` → 404, fichier absent du
      build : aucune des 1 249 annonces n'a d'image de repli (anomalie 9875).

Pourquoi aucun parcours ne les voyait : un parcours vérifie ce qu'il regarde. Ce sont des
défauts de COHÉRENCE ENTRE DEUX ARTEFACTS, pas de comportement — et la cohérence ne se
parcourt pas, elle se confronte.

Le second sens compte autant que le premier : un contrôle qui accuserait un déploiement correct
perdrait sa crédibilité avant son premier vrai cas (la faute payée une fois par TF-0312).
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import surface_servie as ss
from forge_tests.confrontation import Terme, confronter


def _ecrire(chemin: Path, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


# --- Le mécanisme, seul : trois issues, jamais une quatrième ------------------------------------
def test_les_trois_issues_du_mecanisme_et_pas_une_de_plus() -> None:
    promesse = Terme("promesse", {"/a", "/b"}, sources=["src.ts"])

    manquant = confronter("d", promesse, Terme("service", {"/a"}, sources=["hôte"]))
    assert manquant["verdict"] == "FAIL"
    assert manquant["manquantes"] == ["/b"]

    complet = confronter("d", promesse, Terme("service", {"/a", "/b"}))
    assert complet["verdict"] == "PASS"

    sans_terme = confronter("d", promesse, Terme("service", motif_absence="pas d'hôte lisible"))
    assert sans_terme["verdict"] == "SKIP"
    assert "pas d'hôte lisible" in sans_terme["motif"]


def test_l_ASYMETRIE_est_tenue_un_servi_non_promis_n_est_jamais_accuse() -> None:
    """La faute que TF-0312 a payée : accuser un déploiement correct parce que le lecteur de la
    promesse était trop court. Ici, trois routes servies pour une promise — PASS."""
    r = confronter("d", Terme("promesse", {"/a"}), Terme("service", {"/a", "/b", "/c"}))

    assert r["verdict"] == "PASS"
    assert r["manquantes"] == []


def test_un_SKIP_dit_LEQUEL_des_deux_termes_manque() -> None:
    """« pas de source » et « pas de servi » ne se réparent pas de la même façon."""
    sans_promesse = confronter("d", Terme("promesse", motif_absence="rien à lire"),
                               Terme("service", {"/a"}))
    assert "« promesse » ILLISIBLE" in sans_promesse["motif"]

    sans_service = confronter("d", Terme("promesse", {"/a"}, sources=["s.ts"]),
                              Terme("service", motif_absence="rien servi"))
    assert "« service » ILLISIBLE" in sans_service["motif"]
    assert "1 élément(s) dans s.ts" in sans_service["motif"], "la promesse lue est dite quand même"


def test_tout_suspendre_ne_donne_pas_un_PASS() -> None:
    """Un PASS sur zéro élément comparé dirait « tout ce qui est promis est servi » sans avoir
    rien confronté — le faux vert que ce mécanisme existe pour refuser."""
    r = confronter("d", Terme("promesse", {"/a"}), Terme("service", {"/z"}),
                   suspendus={"/a": "indéterminable"})

    assert r["verdict"] == "SKIP"
    assert "AUCUN élément comparable" in r["motif"]


# --- Paire (a) : routes appelées / routes servies -------------------------------------------------
_CLIENT = """
const BASE = import.meta.env.VITE_API;
export async function chargerAnnonces() {
  return fetch("/api/c13s/adverts").then((r) => r.json());
}
export async function clePush() {
  return fetch("/api/c13s/vapid/public-key");           // le blueprint n'est pas monté
}
export async function abonnements() {
  return axios.get("/api/c13s/push-subscriptions");     // idem
}
export async function une(id: string) {
  return fetch(`/api/c13s/adverts/${id}`);
}
"""

_HOTE_AMPUTE = '''
from flask import Blueprint
bp = Blueprint("adverts", __name__, url_prefix="/api/c13s")

@bp.route("/adverts", methods=["GET"])
def lister(): ...

@bp.route("/adverts/<string:advert_id>", methods=["GET"])
def une(advert_id): ...
'''

_HOTE_COMPLET = _HOTE_AMPUTE + '''
@bp.route("/vapid/public-key", methods=["GET"])
def cle(): ...

@bp.route("/push-subscriptions", methods=["GET"])
def abos(): ...
'''


def _projet(racine: Path, hote: str) -> Path:
    _ecrire(racine / "frontend" / "src" / "services.ts", _CLIENT)
    _ecrire(racine / "backend" / "src" / "routes.py", hote)
    return racine


def test_une_route_APPELEE_et_non_enregistree_est_CONSTATEE_et_nommee(tmp_path: Path) -> None:
    """Le cas fondateur (a) : deux routes appelées par le front, absentes de l'hôte déployé."""
    cible = _projet(tmp_path, _HOTE_AMPUTE)

    r = ss.confronter_routes(cible)

    assert r["verdict"] == "FAIL", r["motif"]
    assert "/api/c13s/vapid/public-key" in r["manquantes"]
    assert "/api/c13s/push-subscriptions" in r["manquantes"]


def test_un_hote_COMPLET_n_est_pas_accuse(tmp_path: Path) -> None:
    cible = _projet(tmp_path, _HOTE_COMPLET)

    r = ss.confronter_routes(cible)

    assert r["verdict"] == "PASS", r["motif"]


def test_une_route_PARAMETREE_s_apparie_malgre_les_deux_syntaxes(tmp_path: Path) -> None:
    """`${id}` côté client et `<string:advert_id>` côté Flask désignent la même position. Sans
    cette normalisation, AUCUNE route paramétrée ne s'apparierait : le contrôle mesurerait moins
    que ce qu'il affiche, en ne voyant que les routes fixes."""
    cible = _projet(tmp_path, _HOTE_COMPLET)

    r = ss.confronter_routes(cible)

    assert not any("adverts/" in m for m in r["manquantes"]), r["manquantes"]
    assert (ss._normaliser_route("/api/adverts/${id}")
            == ss._normaliser_route("/api/adverts/<int:id>"))


def test_un_appel_de_RESSOURCE_n_est_pas_juge_comme_une_route(tmp_path: Path) -> None:
    """Confondre les deux ferait accuser un hôte de ne pas servir `/assets/logo.svg`."""
    cible = _projet(tmp_path, _HOTE_COMPLET)
    _ecrire(cible / "frontend" / "src" / "img.ts", 'const u = fetch("/assets/logo.svg");')

    r = ss.confronter_routes(cible)

    assert r["verdict"] == "PASS", r["motif"]


def test_un_prefixe_non_reconstitue_SUSPEND_au_lieu_d_accuser(tmp_path: Path) -> None:
    """La lecture des préfixes est partielle et déclarée telle. Un appel dont le segment final
    existe côté serveur est donc SUSPENDU, avec son motif — jamais accusé à la place de savoir."""
    cible = tmp_path
    _ecrire(cible / "frontend" / "src" / "s.ts", 'fetch("/api/v2/adverts");')
    _ecrire(cible / "backend" / "app.py", '''
from flask import Blueprint
bp = Blueprint("a", __name__)

@bp.route("/adverts", methods=["GET"])
def lister(): ...
''')

    r = ss.confronter_routes(cible)

    assert r["verdict"] == "SKIP", r["motif"]
    assert "/api/v2/adverts" in r["suspendus"]
    assert "segment final" in r["suspendus"]["/api/v2/adverts"]


def test_un_client_illisible_statiquement_le_DIT(tmp_path: Path) -> None:
    _ecrire(tmp_path / "backend" / "app.py", _HOTE_COMPLET)

    r = ss.confronter_routes(tmp_path)

    assert r["verdict"] == "SKIP"
    assert "pas lisible statiquement" in r["motif"]


# --- Paire (b) : ressources référencées / présentes au build --------------------------------------
def test_le_cas_fondateur_de_l_image_de_repli_est_CONSTATE(tmp_path: Path) -> None:
    """`url(src/assets/images/placeholder-image.jpg)` dans une feuille servie sous `/assets/` :
    le navigateur la cherche en `/assets/src/assets/images/…`, où elle n'est pas."""
    build = tmp_path / "dist"
    _ecrire(build / "assets" / "AdvertCard-BKnn2WVw.css",
            ".carte { background: url(src/assets/images/placeholder-image.jpg); }")
    _ecrire(build / "index.html", '<link href="/assets/AdvertCard-BKnn2WVw.css" rel="stylesheet">')

    r = ss.confronter_ressources(build)

    assert r["verdict"] == "FAIL", r["motif"]
    assert any("placeholder-image.jpg" in m for m in r["manquantes"]), r["manquantes"]


def test_la_resolution_se_fait_COMME_LE_NAVIGATEUR_depuis_le_dossier_de_la_feuille(
    tmp_path: Path,
) -> None:
    """Le même `url()` relatif, avec le fichier là où le NAVIGATEUR le cherche : PASS. C'est ce
    qui distingue le vrai défaut d'une résolution naïve depuis la racine du build."""
    build = tmp_path / "dist"
    _ecrire(build / "assets" / "carte.css", ".c { background: url(img/repli.jpg); }")
    _ecrire(build / "assets" / "img" / "repli.jpg", "binaire")

    r = ss.confronter_ressources(build)

    assert r["verdict"] == "PASS", r["motif"]


def test_les_URLs_ABSOLUES_et_data_ne_sont_pas_suivies(tmp_path: Path) -> None:
    """Elles ne sont pas des fichiers du build : les chercher produirait des faux positifs."""
    build = tmp_path / "dist"
    _ecrire(build / "index.html",
            '<img src="https://cdn.example.test/a.png">'
            '<link rel="icon" href="data:image/svg+xml,%3Csvg/%3E">'
            '<a href="#ancre">x</a>')

    r = ss.confronter_ressources(build)

    assert r["verdict"] == "SKIP", r["motif"]
    assert "aucune ressource locale" in r["motif"]


def test_sans_build_la_paire_le_DIT_au_lieu_de_passer(tmp_path: Path) -> None:
    r = ss.confronter_ressources(tmp_path / "inexistant")

    assert r["verdict"] == "SKIP"
    assert "aucun build servi" in r["motif"]


def test_les_limites_des_DEUX_paires_sont_declarees() -> None:
    """Loi 3 : on s'écarte explicitement. Les quatre limites qui comptent sont nommées."""
    declare = " ".join(ss.NON_JUGE)

    assert "LITTÉRAUX" in declare, "un client qui compose ses URLs à l'exécution"
    assert "préfixes de blueprints" in declare
    assert "`data:`" in declare
    assert "STATIQUES" in declare, "aucune des deux paires n'interroge l'instance"
