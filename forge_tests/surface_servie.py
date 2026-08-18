"""Ce que le code APPELLE et RÉFÉRENCE, contre ce que l'instance SERT — TF-0371.

Deux paires de termes, confrontées par le mécanisme unique de `forge_tests.confrontation`.
Toutes deux **statiques** : ni instance à monter, ni requête à faire. C'est ce qui les rend
jouables là où un audit ne peut rien mesurer d'autre — la propriété qui a fait la valeur de la
revue de suite (TF-0344), et la raison pour laquelle les deux défauts fondateurs ont pu être
constatés « en trois appels fetch, sans authentification ».

**Les deux défauts fondateurs**, mesurés en direct le 18/08 sur l'instance dev de BAV2, qu'aucun
parcours ne pouvait voir :

  (a) **une route appelée que l'hôte n'enregistre pas.** Le blueprint `alerts/08_push_subscriptions`
      n'est pas dans `endpoint_modules` de `azure/standalone_backend.py` : `GET /api/c13s/vapid/
      public-key` et `GET /api/c13s/push-subscriptions` rendent 404, alors que le front appelle
      les deux (`services.ts`, `notificationUtils.ts`). Toute une fonction est morte en
      production — anomalie 9858 du board, ouverte le 29/07.

  (b) **une ressource référencée qui n'est pas au build.** La feuille servie
      `AdvertCard-*.css` porte `url(src/assets/images/placeholder-image.jpg)`, que le navigateur
      résout en `/assets/src/assets/images/placeholder-image.jpg` → 404, et le fichier n'est pas
      dans le build : aucune des 1 249 annonces n'a d'image de repli — anomalie 9875.

Pourquoi aucun parcours ne les voyait : un parcours vérifie ce qu'il regarde. Une route morte
n'est jamais appelée par un test qui ne l'a pas dans son scénario, et une image de repli ne
manque qu'au moment où elle devrait servir. Ce sont des défauts de **cohérence entre deux
artefacts**, pas de comportement — et la cohérence ne se parcourt pas, elle se confronte.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from forge_tests.confrontation import Terme, confronter

#: Extensions où l'on cherche des appels littéraux du client.
SOURCES_CLIENT = (".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")

#: Dossiers d'atelier, exclus de TOUT parcours : ils ne sont ni source ni servi.
IGNORES = {"node_modules", ".venv", "__pycache__", ".git", ".oracles", ".pytest_cache"}

#: Exclus EN PLUS quand on lit des SOURCES : un build est un artefact, pas une source. Séparer
#: les deux périmètres n'est pas un détail — les avoir confondus a fait que le scan du build
#: s'excluait lui-même (défaut trouvé en jouant les tests de ce module : le build s'appelle
#: `dist`, donc chaque fichier qu'il contient avait un parent « à ignorer »).
IGNORES_SOURCES = IGNORES | {"dist", "build", "out", "_site", "www"}

# Un appel littéral : `fetch("/api/…")`, `axios.get('/api/…')`, `` `${BASE}/api/…` ``. On ne
# retient que les chemins ABSOLUS commençant par `/` : un chemin relatif dépend d'une base qu'on
# ne résout pas ici, et l'accuser serait accuser la limite du lecteur.
_APPEL = re.compile(
    r"""(?:fetch|axios(?:\.\w+)?|request|\.get|\.post|\.put|\.patch|\.delete)\s*\(\s*"""
    r"""[`'"]([/][^`'"\s?#]{2,200})""",
)

# Une route enregistrée côté hôte : décorateur Flask/FastAPI, ou préfixe de blueprint.
_ROUTE_DECOREE = re.compile(
    r"""@\w+\.(?:route|get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]""",
)
_PREFIXE = re.compile(r"""url_prefix\s*=\s*['"]([^'"]+)['"]|prefix\s*=\s*['"]([^'"]+)['"]""")

# `url(...)` d'une feuille servie.
_URL_CSS = re.compile(r"""url\(\s*['"]?([^'")\s]+)['"]?\s*\)""")

# Dans un HTML, tout `href` n'est PAS une ressource : `<a href>` est une DESTINATION DE
# NAVIGATION, jugée par la paire nav (TF-0288) et par le pan i18n. Les confondre a produit six
# faux positifs sur le banc vert dès le premier passage — `/en/blog` cherché comme un fichier.
# On ne retient donc que les balises qui chargent un FICHIER, nommément.
_RESSOURCE_HTML = re.compile(
    r"""<(?:link|img|script|source|video|audio|track|embed|use)[^>]*?"""
    r"""(?:src|href|xlink:href)\s*=\s*['"]([^'"]+)['"]""",
    re.I | re.S,
)

#: Ce qu'on ne suit pas : un schéma d'URL n'est pas un fichier du build.
_HORS_BUILD = re.compile(r"^(?:https?:|data:|mailto:|tel:|blob:|javascript:|#|//)", re.I)


def _fichiers(
    racine: Path, suffixes: tuple[str, ...], *, exclus: set[str] | None = None
) -> list[Path]:
    """Fichiers d'un arbre, hors dossiers exclus. `exclus` par défaut = les seuls dossiers
    d'atelier : c'est l'appelant qui sait s'il lit des SOURCES (et doit écarter les builds) ou
    un BUILD (et ne doit surtout pas s'écarter lui-même)."""
    if not racine.is_dir():
        return []
    interdits = IGNORES if exclus is None else exclus
    return [
        f for f in sorted(racine.rglob("*"))
        if f.is_file() and f.suffix.lower() in suffixes
        and not (interdits & {p.name for p in f.parents})
    ]


def _normaliser_route(chemin: str) -> str:
    """Chemin comparable : sans query, sans ancre, sans slash final, paramètres neutralisés.

    Un `${id}` de gabarit et un `<int:id>` de Flask désignent la même position : les réduire à
    `{}` est ce qui permet de comparer un appel client à une route serveur. Sans ça, aucune
    route paramétrée ne s'apparierait et le contrôle ne verrait que les routes fixes — c'est-à-
    dire qu'il mesurerait moins que ce qu'il affiche.
    """
    c = unquote(chemin.split("?")[0].split("#")[0]).strip()
    c = re.sub(r"\$\{[^}]*\}", "{}", c)          # gabarit JS
    c = re.sub(r"<[^>]+>", "{}", c)               # Flask `<int:id>`
    c = re.sub(r"\{[^}]*\}", "{}", c)             # FastAPI `{id}` et déjà neutralisés
    c = re.sub(r"/+", "/", c)
    return c.rstrip("/") or "/"


def routes_appelees(cible: Path) -> Terme:
    """Ce que le code CLIENT appelle, lu littéralement. Terme « routes appelées »."""
    lus: list[str] = []
    appels: set[str] = set()
    for f in _fichiers(cible, SOURCES_CLIENT, exclus=IGNORES_SOURCES):
        texte = f.read_text(encoding="utf-8", errors="replace")
        trouves = {_normaliser_route(m) for m in _APPEL.findall(texte)}
        # On ne garde que ce qui ressemble à une route d'API : un `/assets/…` est une ressource,
        # jugée par l'autre paire. Confondre les deux ferait accuser un build de ne pas servir
        # une route.
        trouves = {r for r in trouves if not re.match(r"^/(assets|static|public)/", r)}
        if trouves:
            lus.append(f.relative_to(cible).as_posix())
            appels |= trouves
    if not appels:
        return Terme(
            "routes appelées", motif_absence=(
                f"aucun appel littéral de route dans les sources client "
                f"({', '.join(SOURCES_CLIENT)}) sous {cible} — un client qui construit ses URLs "
                "à l'exécution n'est pas lisible statiquement, et le supposer serait deviner"
            ),
        )
    return Terme("routes appelées", appels, sources=lus[:8])


def routes_servies(cible: Path) -> Terme:
    """Ce que l'HÔTE enregistre, décorateurs et préfixes de blueprints. Terme « routes servies ».

    On lit les décorateurs partout dans le backend, puis on les préfixe des `url_prefix` trouvés
    dans le MÊME fichier. C'est approximatif — un blueprint enregistré ailleurs avec un préfixe
    différent échappe — et c'est déclaré : la conséquence d'une lecture trop courte est un terme
    « servi » plus petit, donc de FAUSSES accusations. On la borne donc par l'asymétrie ET par
    une garde : une route appelée dont le SEGMENT FINAL existe côté serveur n'est pas accusée.
    """
    lus: list[str] = []
    routes: set[str] = set()
    for f in _fichiers(cible, (".py",), exclus=IGNORES_SOURCES):
        texte = f.read_text(encoding="utf-8", errors="replace")
        decorees = _ROUTE_DECOREE.findall(texte)
        if not decorees:
            continue
        prefixes = [a or b for a, b in _PREFIXE.findall(texte)] or [""]
        lus.append(f.relative_to(cible).as_posix())
        for chemin in decorees:
            for prefixe in prefixes:
                routes.add(_normaliser_route(prefixe.rstrip("/") + "/" + chemin.lstrip("/")))
            routes.add(_normaliser_route(chemin))
    if not routes:
        return Terme(
            "routes servies", motif_absence=(
                f"aucune route enregistrée lisible sous {cible} (décorateur `@bp.route` / "
                "`@app.get` …) — sans table de routes opposable, un 404 n'est pas distinguable "
                "d'une route que ce lecteur ne sait pas lire"
            ),
        )
    return Terme("routes servies", routes, sources=lus[:8])


def _suspendre_par_segment(appelees: set[str], servies: set[str]) -> dict[str, str]:
    """Garde contre la fausse accusation : appel dont le segment final EXISTE côté serveur.

    Mesuré nécessaire en écrivant ce module : la lecture des préfixes est partielle, donc une
    route réellement servie sous un préfixe qu'on n'a pas su reconstituer sortirait « non
    servie ». Suspendre ces cas est le prix d'un lecteur honnête — et le suspendre EN LE DISANT
    est la différence entre une limite et un silence.
    """
    finaux = {r.rsplit("/", 1)[-1] for r in servies if "/" in r}
    suspendus = {}
    for r in sorted(appelees - servies):
        final = r.rsplit("/", 1)[-1]
        if final and final in finaux:
            suspendus[r] = (
                f"segment final « {final} » enregistré côté serveur sous un autre préfixe — "
                "préfixe non reconstitué par ce lecteur, jugement suspendu plutôt que faux"
            )
    return suspendus


def confronter_routes(cible: Path) -> dict:
    """Paire (a) de TF-0371 : routes appelées par le client / routes servies par l'hôte."""
    appelees, servies = routes_appelees(cible), routes_servies(cible)
    suspendus = (
        _suspendre_par_segment(appelees.elements, servies.elements)
        if appelees.elements and servies.elements else {}
    )
    return confronter("routes appelées vs servies", appelees, servies, suspendus=suspendus)


def ressources_referencees(build: Path) -> Terme:
    """Ce que les artefacts SERVIS référencent : `url()` des CSS, `src`/`href` des HTML."""
    lus: list[str] = []
    refs: set[str] = set()
    for f in _fichiers(build, (".css", ".html")):
        texte = f.read_text(encoding="utf-8", errors="replace")
        brutes = (_URL_CSS.findall(texte) if f.suffix.lower() == ".css"
                  else _RESSOURCE_HTML.findall(texte))
        locales = {r.strip() for r in brutes if r.strip() and not _HORS_BUILD.match(r.strip())}
        if not locales:
            continue
        lus.append(f.relative_to(build).as_posix())
        for r in locales:
            # Résolution comme le NAVIGATEUR : un chemin relatif se résout depuis le dossier de
            # la feuille, pas depuis la racine du build. C'est exactement ce qui a produit
            # `/assets/src/assets/images/…` à partir d'un `url(src/assets/images/…)` dans
            # `/assets/AdvertCard-*.css` — la ressource est cherchée là où le navigateur la
            # cherche, pas là où l'auteur croyait l'écrire.
            base = f.parent if not r.startswith("/") else build
            refs.add((base / r.lstrip("/")).resolve().as_posix())
    if not refs:
        return Terme(
            "ressources référencées", motif_absence=(
                f"aucune ressource locale référencée dans les CSS/HTML de {build} — rien à "
                "confronter (un build qui ne référence que des URLs absolues est hors sujet)"
            ),
        )
    return Terme("ressources référencées", refs, sources=lus[:8])


def ressources_servies(build: Path, referencees: set[str]) -> Terme:
    """Les fichiers du build, restreints aux chemins référencés — on ne liste pas tout un build.

    L'ensemble est construit PAR TEST D'EXISTENCE sur les chemins attendus : parcourir tout le
    build pour le comparer entièrement produirait un terme énorme et une asymétrie illisible.
    Ce qui compte est « ce qui est demandé existe-t-il », pas « qu'y a-t-il ».
    """
    presentes = {chemin for chemin in referencees if Path(chemin).is_file()}
    return Terme("fichiers du build", presentes, sources=[build.name])


def confronter_ressources(build: Path | None) -> dict:
    """Paire (b) de TF-0371 : ressources référencées par le servi / présentes au build."""
    if build is None or not Path(build).is_dir():
        return confronter(
            "ressources référencées vs servies",
            Terme("ressources référencées", motif_absence="aucun build servi à lire"),
            Terme("fichiers du build"),
        )
    build = Path(build)
    referencees = ressources_referencees(build)
    if not referencees.elements:
        return confronter("ressources référencées vs servies", referencees,
                          Terme("fichiers du build"))
    servies = ressources_servies(build, referencees.elements)
    resultat = confronter("ressources référencées vs servies", referencees, servies)
    # Les chemins absolus sont illisibles au rapport : on les rend relatifs au build.
    resultat["manquantes"] = [
        Path(m).relative_to(build).as_posix() if str(m).startswith(str(build)) else m
        for m in resultat["manquantes"]
    ]
    return resultat


NON_JUGE = [
    "routes appelées : seuls les appels LITTÉRAUX absolus sont lus — un client qui compose son "
    "URL à l exécution (concaténation, table de configuration) n est pas lisible statiquement",
    "routes servies : les préfixes de blueprints sont lus dans le MÊME fichier que leurs "
    "décorateurs ; un blueprint enregistré ailleurs sous un autre préfixe fait suspendre les "
    "appels dont le segment final existe (jamais accuser à la place de savoir)",
    "ressources : dans un HTML, seules les balises qui chargent un FICHIER sont lues (link, "
    "img, script, source, video, audio, track, embed, use) — un `<a href>` est une destination "
    "de NAVIGATION, jugée par la paire nav et par le pan i18n, jamais cherchée comme un fichier",
    "ressources : les URLs absolues, `data:` et `blob:` ne sont pas suivies — elles ne sont pas "
    "des fichiers du build ; leur disponibilité RÉELLE relève d un contrôle réseau, pas d ici",
    "ni l une ni l autre paire n interroge l instance : ce sont des confrontations STATIQUES. "
    "Un 404 réel dont la cause n est ni une route absente ni un fichier manquant (règle de "
    "réécriture, proxy, cache) leur échappe",
]
