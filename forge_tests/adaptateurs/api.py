"""Adaptateur API (FastAPI) — endpoints x methodes x codes de retour depuis le code source."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.disposition import paquet_sources
from forge_tests.execution import codes_emis, motif_indisponibilite, schema_openapi
from forge_tests.invariants import NON_JUGE as NON_JUGE_INV
from forge_tests.invariants import codes_par_fonction, handlers
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "api-fastapi", "api", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "declarer l application ASGI du projet dans `<projet>/.env.forge-tests` "
    "(FORGE_TESTS_APP=« module:attribut ») et rendre la suite backend verte sous `coverage` — "
    "voir la section « Contrat du projet audite » du README"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T1", "famille": "technique", "titre": "API",
     "decoupe": "routeur", "axe_cas": "unitaire"},
)


# RT-13 : le seul champ qui debloque CE pan — la designation de l application ASGI a sonder.
CHAMPS_REQUIS = ("FORGE_TESTS_APP",)

_ROUTE = re.compile(r'@app\.(get|post|patch|put|delete)\(\s*"([^"]+)"(.*?)\)\s*\n', re.DOTALL)
_CODE = re.compile(r"(\d{3})\s*:")
_APPEL = re.compile(r'client\.(get|post|patch|put|delete)\(\s*f?"([^"]+)"')
_STATUT = re.compile(r"status_code\s*==\s*(\d{3})")

NON_JUGE = [
    "api : un code emis pendant la suite est repute couvert ; la sonde ne verifie pas qu une "
    "ASSERTION porte sur lui — c est le role du second contre-oracle",
]

# Piege le plus silencieux du premier produit reel : une suite batie sur une app factory
# (`creer_app()` par test) n exerce JAMAIS l instance module instrumentee. Le releve sort vide,
# la suite est verte, et le rapport accuse la suite de ne rien couvrir — alors que c est la
# sonde qui n a rien vu. Un releve vide sur suite verte doit donc DIRE cette hypothese.
AVERTISSEMENT_SONDE_MUETTE = (
    "api : suite verte mais sonde API muette — l app exercee n est pas l instance module "
    'designee ; la designer avec FORGE_TESTS_APP="module:attribut" (l attribut peut etre une '
    "fabrique). Voir « Contrat du projet audite » au README"
)


def _montages(cible: Path) -> list[str]:
    """Préfixes montés par `app.mount(...)` — fichiers statiques et sous-applications.

    RT-10. Un montage n est pas une route : il n a pas de décorateur, donc pas de `responses=`,
    et FastAPI n offre AUCUN moyen d en déclarer un. Le contrôle de divergence « code émis mais
    absent de sa déclaration `responses=` » y produisait donc un finding STRUCTURELLEMENT
    incorrigeable côté produit — constaté sur `GET /static/app.js` d ASD Mail Manager. Un
    montage est réputé émettre 200 (fichier servi) et 404 (fichier absent) ; les deux sont le
    comportement documenté de Starlette, pas une promesse du projet.
    """
    src = cible / "backend" / "app" / "main.py"
    if not src.exists():
        return []
    import ast

    try:
        arbre = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    except SyntaxError:
        return []
    prefixes: list[str] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call) or not isinstance(noeud.func, ast.Attribute):
            continue
        if noeud.func.attr != "mount" or not noeud.args:
            continue
        premier = noeud.args[0]
        if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
            prefixes.append(premier.value.rstrip("/") or "/")
    return sorted(set(prefixes))


def _sous_montage(identifiant: str, prefixes: list[str]) -> bool:
    """L identifiant `code:GET /static/{} =200` porte-t-il sur un chemin monté ?"""
    if not prefixes:
        return False
    signature = identifiant[len("code:") :].rsplit("=", 1)[0]
    _, _, chemin = signature.partition(" ")
    return any(chemin == prefixe or chemin.startswith(prefixe + "/") for prefixe in prefixes)


def _norm(chemin: str) -> str:
    chemin = chemin.split("?")[0]
    chemin = re.sub(r"\{[^}]*\}", "{}", chemin)
    return re.sub(r"/\d+", "/{}", chemin)


def _codes_declares(cible: Path) -> set[str]:
    """Codes ecrits A LA MAIN dans `responses=`, par opposition a ceux ajoutes par le cadre."""
    src = cible / "backend" / "app" / "main.py"
    if not src.exists():
        return set()
    declares: set[str] = set()
    for methode, chemin, reste in _ROUTE.findall(src.read_text(encoding="utf-8")):
        for code in _CODE.findall(reste):
            declares.add(f"{methode.upper()} {_norm(chemin)}={code}")
    return declares


def _inventaire_openapi(cible: Path) -> list[Element]:
    """Surface lue dans le schema que l application DECLARE — source primaire du CDC."""
    schema = schema_openapi(str(cible))
    if not schema:
        return []
    elements: list[Element] = []
    source = str(cible / "backend" / "app" / "main.py")
    for chemin, operations in schema.get("paths", {}).items():
        c = _norm(chemin)
        for methode, operation in operations.items():
            if methode not in ("get", "post", "put", "patch", "delete"):
                continue
            m = methode.upper()
            elements.append(Element(f"endpoint:{m} {c}", PAN, f"{m} {c}", source))
            declares_source = _codes_declares(cible)
            for code in operation.get("responses", {}):
                # FastAPI ajoute un 422 a toute route validee, sans que personne l ait declare.
                # Sur un GET sans corps il est inatteignable : l exiger accuse la suite d un
                # trou qui n existe pas. Retenu SEULEMENT s il est declare a la main.
                if code == "422" and f"{m} {c}=422" not in declares_source:
                    continue
                elements.append(
                    Element(f"code:{m} {c}={code}", PAN, f"{m} {c} -> {code}", source)
                )
    return elements


def inventaire(cible: Path) -> list[Element]:
    par_schema = _inventaire_openapi(cible)
    if par_schema:
        return par_schema
    src = cible / "backend" / "app" / "main.py"
    if not src.exists():
        return []
    texte = src.read_text(encoding="utf-8")
    elements: list[Element] = []
    for methode, chemin, reste in _ROUTE.findall(texte):
        m, c = methode.upper(), _norm(chemin)
        elements.append(Element(f"endpoint:{m} {c}", PAN, f"{m} {c}", str(src)))
        for code in dict.fromkeys(_CODE.findall(reste)):
            elements.append(Element(f"code:{m} {c}={code}", PAN, f"{m} {c} -> {code}", str(src)))
    return elements


def exerces(cible: Path) -> set[str] | None:
    """Couples et codes REELLEMENT emis pendant la suite (sonde ASGI), jamais deduits du texte.

    None = couverture NON MESURABLE (suite non executee). A ne pas confondre avec un ensemble
    vide, qui signifierait « rien n est couvert » — deux verdicts opposes.
    """
    releve = codes_emis(cible)
    if releve is None:
        return None
    couvert: set[str] = set()
    for entree in releve:
        methode = entree["methode"].upper()
        gabarit = _norm(entree["gabarit"])
        couvert.add(f"endpoint:{methode} {gabarit}")
        couvert.add(f"code:{methode} {gabarit}={entree['code']}")
    return couvert


def _fichiers_sources(cible: Path) -> list[Path]:
    """Tous les modules Python de l application — pas le seul `main.py` (TF-0135).

    Une app FastAPI a routeurs (`include_router`) declare son GET/POST et leurs gardes dans
    `app/api/routes_*.py` : main.py n y porte que les montages et les inclusions. Une table de
    handlers batie sur le seul main.py y ressortait donc VIDE, et `code in (400, 409) and code
    not in gardes` devenait vrai pour TOUT code declare — trois findings BLOQUANTS faux
    constates sur Approval2, pour un code dont les trois handlers levent bien leur code dans
    leur PROPRE corps. Le paquet est DECOUVERT (`forge_tests.disposition.paquet_sources`),
    avec le meme repli que les autres pans (TF-0116/TF-0117) : `backend/app`.
    """
    racine = paquet_sources(cible) or cible / "backend" / "app"
    if not racine.is_dir():
        return []
    return sorted(p for p in racine.rglob("*.py") if "__pycache__" not in p.parts)


def _divergences_gardes(
    inv: list[Element],
    table: dict[tuple[str, str], str],
    par_fonction: dict[str, set[int]],
    source: Path,
) -> tuple[list[Finding], list[str]]:
    """Un code 400/409 declare sans garde qui le leve est une divergence — SAUF si l analyse
    statique n a pas pu resoudre le handler (TF-0135).

    Le `?()` qui apparaissait au message quand `fonction` valait None ne disait PAS que le
    projet avait tort : il etait la trace meme de l echec de resolution de l analyseur. Un
    handler non resolu degrade donc desormais en avertissement NON_JUGE, motive et nomme,
    jamais en finding BLOQUANT sur un code que personne n a pu verifier.
    """
    findings: list[Finding] = []
    non_juge: list[str] = []
    for element in inv:
        if not element.id.startswith("code:"):
            continue
        signature, code_txt = element.id[len("code:") :].rsplit("=", 1)
        methode, chemin = signature.split(" ", 1)
        code = int(code_txt)
        if code not in (400, 409):
            continue
        fonction = table.get((methode, chemin))
        if fonction is None:
            non_juge.append(
                f"api : {signature} -> {code} declare, mais aucun handler n a pu etre resolu "
                "par l analyse statique des gardes (RT-9) — divergence NON JUGEE, jamais "
                "ecartee a tort contre le projet"
            )
            continue
        gardes = par_fonction.get(fonction, set())
        if code not in gardes:
            findings.append(
                Finding(
                    id=f"divergence:{element.id}",
                    classe="divergence",
                    localisation=str(source),
                    message=(
                        f"code {code} declare pour {signature} mais aucune garde de "
                        f"{fonction}() ne le leve"
                    ),
                    risque=coter(PAN, element.id, str(source)),
                )
            )
    return findings, non_juge


def analyser(cible: Path) -> SortieAdaptateur:
    inv = inventaire(cible)
    if exerces(cible) is None:
        # « 0 % couvert » et « couverture non mesurable » sont deux verdicts OPPOSES. Les
        # confondre accuse a tort une suite qu on n a simplement pas pu executer.
        endpoints = sum(1 for e in inv if e.id.startswith("endpoint:"))
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"api : {len(inv)} elements INVENTORIES ({endpoints} operations, "
                f"{len(inv) - endpoints} codes) mais couverture non mesurable — "
                + motif_indisponibilite(cible, "backend", "suite non executee sous sonde"),
            ],
        )
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"api : {len(inv)} elements INVENTORIES (OpenAPI) mais couverture non mesurable — "
                + motif_indisponibilite(
                    cible, "backend", "la suite du projet n a pas pu etre executee sous sonde"
                ),
            ],
        )
    # Le controle de divergence repose sur l analyse STATIQUE des gardes : ses limites (RT-9,
    # un seul niveau d appel resolu) appartiennent au rapport de CE pan, pas a un module que
    # personne ne lit. Elles etaient importees ici sans jamais etre publiees.
    sortie = evaluer_surface(
        NOM, PAN, str(cible), inv, couvert, SEUIL, [*NON_JUGE, *NON_JUGE_INV]
    )
    # `couvert` non nul veut dire que la suite a fini VERTE (sinon la mesure vaudrait None).
    # Vide malgre un inventaire fourni : la sonde n a vu passer aucune requete.
    if inv and not couvert:
        sortie.non_juge.insert(0, AVERTISSEMENT_SONDE_MUETTE)
        sortie.findings.insert(
            0,
            Finding(
                id="sonde-muette:api",
                classe="sonde-muette",
                localisation=str(cible / "backend" / "app" / "main.py"),
                message=AVERTISSEMENT_SONDE_MUETTE,
                severite="signale",
            ),
        )
    # Un code EMIS pendant la suite mais absent de `responses=` est une divergence entre ce que
    # la source declare et ce que le code fait. Ni un trou de couverture, ni un silence : un ecart.
    # Un code d invariant metier DECLARE mais qu aucune garde du code ne peut produire est une
    # divergence : la source promet une erreur que le comportement ne sait plus lever.
    source = cible / "backend" / "app" / "main.py"
    sources = _fichiers_sources(cible)
    par_fonction = codes_par_fonction(sources)
    table = handlers(sources)
    findings_gardes, non_juge_gardes = _divergences_gardes(inv, table, par_fonction, source)
    sortie.findings.extend(findings_gardes)
    sortie.non_juge.extend(non_juge_gardes)
    if findings_gardes:
        sortie.verdict = "FAIL"

    declares = {e.id for e in inv if e.id.startswith("code:")}
    prefixes = _montages(cible)
    if prefixes:
        sortie.non_juge.append(
            "api : montage(s) " + ", ".join(prefixes) + " EXCLUS du controle de divergence "
            "(RT-10) — un `app.mount()` ne peut pas declarer de `responses=`, ses codes sont "
            "reputes 200 (servi) et 404 (absent) par le cadre, pas promis par le projet"
        )
    for identifiant in sorted(couvert - declares):
        if not identifiant.startswith("code:"):
            continue
        if _sous_montage(identifiant, prefixes):
            continue
        sortie.findings.append(
            Finding(
                id=identifiant,
                classe="divergence",
                localisation=str(cible / "backend" / "app" / "main.py"),
                message="code emis par l application mais absent de sa declaration responses=",
                severite="signale",
                risque=coter(PAN, identifiant, str(cible / "backend" / "app" / "main.py")),
            )
        )
    return sortie
