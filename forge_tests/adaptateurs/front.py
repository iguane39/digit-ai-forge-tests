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
    "installer les dependances du front (`frontend/node_modules`), rendre la suite Playwright "
    "du projet verte, et marquer les elements manipules par `data-testid` — la trace "
    "Playwright est la source de ce qui a ete REELLEMENT atteint"
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


def exerces(cible: Path) -> set[str] | None:
    """Routes visitees et elements manipules REELLEMENT, lus dans la trace du navigateur."""
    mesure = front_execute(str(cible))
    if mesure is None:
        return None
    couvert = {f"element:{tid}" for tid in mesure["testids"]}
    couvert |= {f"route:{re.sub(r'/\d+', '/:id', url)}" for url in mesure["routes"]}
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        inv = inventaire(cible)
        routes = sum(1 for e in inv if e.id.startswith("route:"))
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"front : {len(inv)} elements INVENTORIES ({routes} routes, "
                f"{len(inv) - routes} elements interactifs) mais couverture non mesurable — "
                + motif_indisponibilite(cible, "front", "suite e2e non executee"),
            ],
        )
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), couvert, SEUIL, NON_JUGE)
