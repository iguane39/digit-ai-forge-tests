"""Adaptateur Front (React) — inventaire de surface depuis le code source.

Capacite 1 : routes depuis la table de routage, elements interactifs depuis les pages.
Capacite 5 : couverture de surface par recoupement avec la suite e2e.
"""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.execution import front_execute, motif_indisponibilite
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "front-react", "front", 0.90

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "installer les dépendances du front (`frontend/node_modules`), rendre la suite Playwright "
    "du projet verte, et marquer les éléments manipulés par `data-testid` — la trace "
    "Playwright est la source de ce qui a été RÉELLEMENT atteint"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "F2", "famille": "fonctionnel", "titre": "Écrans × états",
     "decoupe": "ecran", "axe_cas": "etats"},
)

# RT-13 : le seul champ qui debloque CE pan — l instance servie exportee en BASE_URL vers la
# suite e2e du projet. Sans revendication, le pan reclamait aussi le compte et l URL de qualif.
CHAMPS_REQUIS = ("FORGE_TESTS_BASE_URL",)

_ROUTE = re.compile(r'path:\s*"([^"]+)"')
_TESTID = re.compile(r'data-testid="([^"]+)"')
_GOTO = re.compile(r'goto\(\s*"([^"]+)"')
_BYTESTID = re.compile(r'getByTestId\(\s*"([^"]+)"')
# TF-0100 : `<Route path="...">` (react-router), l un des routeurs React les plus repandus,
# n etait reconnu ni par `routes.jsx` ni par la convention TanStack — un produit en react-router
# s inventoriait a zero route, et la surface front tombait a zero en cascade (accessibilite,
# visuel).
_ROUTE_JSX = re.compile(r'<Route\b[^>]*\bpath\s*=\s*(["\'])(.*?)\1', re.DOTALL)

NON_JUGE = [
    "front : un element manipule pendant la suite est repute exerce ; la trace dit qu il a ete "
    "atteint, pas qu une ASSERTION porte sur son effet",
    "front : elements rendus dynamiquement sans data-testid statique (non inventoriables ici)",
]


def _racine(cible: Path) -> Path:
    return cible / "frontend"


def _routes_tanstack(racine: Path) -> list[tuple[str, Path]]:
    """Routes par convention de fichiers (TanStack Router) : un .tsx sous src/routes = une route.

    `__root` et `_layout` structurent sans etre des destinations ; `index` -> `/` ;
    `$param` -> `:param`. Constate sur le premier projet reel."""
    dossier = racine / "src" / "routes"
    if not dossier.is_dir():
        return []
    routes: list[tuple[str, Path]] = []
    for fichier in sorted(dossier.rglob("*.tsx")):
        nom = fichier.relative_to(dossier).with_suffix("").as_posix()
        segments = [s for s in nom.split("/") if not s.startswith(("__", "_"))]
        if not segments:
            continue
        if segments[-1] == "index":
            segments = segments[:-1]
        chemin = "/" + "/".join(s.replace("$", ":") for s in segments)
        routes.append((chemin if chemin != "//" else "/", fichier))
    return routes


def _routes_react_router(racine: Path) -> list[tuple[str, Path]]:
    """Routes déclarées par `<Route path="…">` (react-router), recherchées dans tout `src/`.

    Contrairement à la convention TanStack (un fichier = une route), react-router déclare ses
    routes dans le JSX d un composant quelconque (souvent `App.tsx`) : il n y a pas de chemin
    conventionnel unique à lire, il faut chercher le motif dans les sources.
    """
    dossier = racine / "src"
    if not dossier.is_dir():
        return []
    routes: list[tuple[str, Path]] = []
    for fichier in sorted(dossier.rglob("*.tsx")) + sorted(dossier.rglob("*.jsx")):
        if "routeTree.gen" in fichier.name:
            continue
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for _guillemet, chemin in _ROUTE_JSX.findall(texte):
            routes.append((chemin, fichier))
    return routes


def inventaire(cible: Path) -> list[Element]:
    racine = _racine(cible)
    elements: list[Element] = []
    routes_src = racine / "src" / "routes.jsx"
    if routes_src.exists():
        for chemin in _ROUTE.findall(routes_src.read_text(encoding="utf-8")):
            elements.append(Element(f"route:{chemin}", PAN, f"route {chemin}", str(routes_src)))
    deja: set[str] = {e.id for e in elements}
    for chemin, fichier in _routes_tanstack(racine):
        # route.tsx et index.tsx d une meme section designent la MEME destination : dedupliquer.
        if f"route:{chemin}" not in deja:
            deja.add(f"route:{chemin}")
            elements.append(Element(f"route:{chemin}", PAN, f"route {chemin}", str(fichier)))
    for chemin, fichier in _routes_react_router(racine):
        if f"route:{chemin}" not in deja:
            deja.add(f"route:{chemin}")
            elements.append(Element(f"route:{chemin}", PAN, f"route {chemin}", str(fichier)))
    sources_tid = sorted((racine / "src").rglob("*.jsx")) + sorted((racine / "src").rglob("*.tsx"))
    vus: set[str] = set()
    for page in sources_tid:
        if "routeTree.gen" in page.name:
            continue
        for tid in _TESTID.findall(page.read_text(encoding="utf-8", errors="replace")):
            if tid not in vus:
                vus.add(tid)
                elements.append(
                    Element(f"element:{tid}", PAN, f"element interactif {tid}", str(page))
                )
    return elements


def motif_de_route(chemin: str) -> re.Pattern[str]:
    """Motif de route DÉCLARÉ -> expression qui apparie une URL, comme le routeur lui-même.

    RT-11 (lot bourse-aux-vacants 20260814a) : une route déclarée est un MOTIF, pas une URL.
    Comparer `/login/reset-password/:token/:email` à l'URL réellement visitée sans le templater
    ne rapproche jamais rien — toute route paramétrée d'une SPA sortait « inventoriée, jamais
    exercée » alors que la suite la visitait, jeton réel en main. Un `:param` capte un segment,
    un `*` capte le reste ; tout autre segment est littéral.
    """
    morceaux = []
    for segment in [s for s in chemin.split("/") if s]:
        if segment.startswith(":"):
            morceaux.append(r"[^/]+")
        elif segment == "*":
            morceaux.append(r".*")
        else:
            morceaux.append(re.escape(segment))
    return re.compile("^/" + "/".join(morceaux) + "$")


def _routes_appariees(inventaire_elements: list[Element], urls: list[str]) -> set[str]:
    """Ids de routes DÉCLARÉES qu'au moins une URL visitée apparie (RT-11)."""
    couvert: set[str] = set()
    for element in inventaire_elements:
        if not element.id.startswith("route:"):
            continue
        motif = motif_de_route(element.id.split(":", 1)[1])
        if any(motif.match(url) for url in urls):
            couvert.add(element.id)
    return couvert


def exerces(cible: Path, inventaire_elements: list[Element] | None = None) -> set[str] | None:
    """Routes visitees et elements manipules REELLEMENT, lus dans la trace du navigateur.

    `inventaire_elements` (RT-11) : quand l'inventaire est fourni, les routes DÉCLARÉES y sont
    appariées aux URL visitées par leur motif. Sans lui, seul le repli historique joue.
    """
    mesure = front_execute(str(cible))
    if mesure is None:
        return None
    couvert = {f"element:{tid}" for tid in mesure["testids"]}
    # Une URL porte parfois une requête ou une ancre : ni l'une ni l'autre n'est la route.
    urls = [str(url).split("?")[0].split("#")[0] or "/" for url in mesure["routes"]]
    # motif hors f-string : un backslash dans une f-string est invalide en 3.11
    # (requires-python >= 3.11) — la syntaxe n'arrive qu'en 3.12
    motif_id = r"/\d+"
    # Repli historique conservé : il apparie les identifiants numériques quand l'inventaire
    # n'est pas fourni. L'appariement par motif ci-dessous le couvre et va plus loin.
    couvert |= {f"route:{re.sub(motif_id, '/:id', url)}" for url in urls}
    if inventaire_elements:
        couvert |= _routes_appariees(inventaire_elements, urls)
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    # TF-0344/0345 — la revue STATIQUE de la suite tourne d abord, et surtout : elle ne depend
    # ni de l instance servie ni de l execution de la suite. Un projet dont la suite ne peut pas
    # tourner est justement celui ou un faux vert dort le plus longtemps.
    from forge_tests import couverture, revue

    faux_verts = revue.analyser_suite(cible)
    # TF-0589 (24/08) — la CONFIGURATION qui produit le chiffre, lue avant le chiffre lui-meme.
    # Meme raison que la revue de suite : elle ne depend ni de l instance servie ni de l execution,
    # et le projet dont la couverture est mal configuree est justement celui dont le chiffre
    # rassure le plus. Trois defauts vivaient ensemble sous un seuil VERT le 24/08.
    faux_verts = faux_verts + couverture.analyser_configuration(cible)
    inv = inventaire(cible)
    couvert = exerces(cible, inv)
    if couvert is None:
        routes = sum(1 for e in inv if e.id.startswith("route:"))
        return SortieAdaptateur(
            NOM, PAN, str(cible), "FAIL" if faux_verts else "SKIP",
            findings=faux_verts,
            non_juge=[
                *NON_JUGE,
                *revue.NON_JUGE,
                *couverture.NON_JUGE,
                f"front : {len(inv)} elements INVENTORIES ({routes} routes, "
                f"{len(inv) - routes} elements interactifs) mais couverture non mesurable — "
                + motif_indisponibilite(cible, "front", "suite e2e non executee"),
            ],
        )
    sortie = evaluer_surface(
        NOM, PAN, str(cible), inv, couvert, SEUIL,
        [*NON_JUGE, *revue.NON_JUGE, *couverture.NON_JUGE],
        sans_objet=sans_objet(cible),
    )
    if faux_verts:
        sortie.findings.extend(faux_verts)
        sortie.verdict = "FAIL"
    return sortie


def sans_objet(cible: Path) -> str | None:
    """PREUVE d absence de périmètre front (NA, 14/08) — pas une supposition.

    Un projet purement API, un lot batch, un outil en ligne de commande n ont pas de front :
    leur absence de routes n est pas un trou de couverture, c est l absence du sujet. La preuve
    est positive : le dossier que ce pan déclare lire n existe pas.
    """
    racine = _racine(cible)
    if not racine.is_dir():
        return "aucun dossier `frontend\\` : ce projet n a pas de front à parcourir"
    if not (racine / "src").is_dir():
        return "`frontend\\` présent mais aucun `src\\` : aucune source de routes à lire"
    return None
