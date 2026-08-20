"""Adaptateur API (FastAPI) — endpoints x methodes x codes de retour depuis le code source."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from forge_tests import classes
from forge_tests.disposition import paquet_sources
from forge_tests.execution import codes_emis, motif_indisponibilite, schema_openapi
from forge_tests.invariants import NON_JUGE as NON_JUGE_INV
from forge_tests.invariants import codes_par_fonction, handlers
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "api-fastapi", "api", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "déclarer l'application ASGI du projet dans `<projet>/.env.forge-tests` "
    "(FORGE_TESTS_APP=« module:attribut ») et rendre la suite backend verte sous `coverage` — "
    "voir la section « Contrat du projet audité » du README"
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

# TF-0244 — la lecture de secours, et ce qu elle ne sait PAS voir. Publiee au rapport dès qu on
# y retombe : un constat de divergence produit sous ce régime peut être un défaut de la LECTURE
# et non du projet, et le lecteur doit pouvoir le savoir avant d instruire.
NON_JUGE_SANS_SCHEMA = (
    "api : schema OpenAPI indisponible — les codes DECLARES ont ete lus par expression "
    "reguliere sur les decorateurs `@app.<methode>(…)` du module principal (lecture de "
    "SECOURS). Elle ne voit ni les routeurs (`@router.get`, `include_router`), ni un "
    "`responses=` qu un argument multiligne referme avant lui : sous ce regime, « code emis "
    "mais absent de responses= » peut denoncer la lecture plutot que le projet. Designer "
    'l application avec FORGE_TESTS_APP="module:attribut" pour que le schema fasse foi'
)

# Ce que FastAPI ajoute D OFFICE a toute route validee : le 422 de validation de corps. Il n est
# promis par personne — l exiger de la suite accuse d un trou qui n existe pas (voir plus bas).
# Un 422 que le projet a, lui, ECRIT se reconnait a ce qu il s ecarte de cette forme.
_422_CADRE_DESCRIPTION = "Validation Error"
_422_CADRE_MODELE = "HTTPValidationError"

NON_JUGE_422 = (
    "api : un 422 declare a l identique du 422 automatique de FastAPI (description "
    f"« {_422_CADRE_DESCRIPTION} » et modele {_422_CADRE_MODELE}) est indiscernable de celui du "
    "cadre dans le schema — il est traite comme le cadre, donc NON exige de la suite"
)


def _module_principal(cible: Path) -> Path:
    """Fichier où LOCALISER un constat de ce pan — DÉCOUVERT, jamais supposé (TF-0244).

    `backend/app/main.py` était écrit en dur ici, en six endroits. Sur un projet à racine plate
    (`app/` à la racine, disposition très répandue — TF-0216), chaque constat de ce pan
    désignait donc un chemin INEXISTANT : le lecteur ouvrait un fichier absent pour vérifier un
    constat, et le constat devenait invérifiable. Un audit dont on ne peut pas ouvrir la preuve
    ne vaut pas mieux qu une opinion.

    L ancre est celle que tout le reste du framework utilise déjà (`paquet_sources`), et les
    noms de module d entrée sont essayés dans un ordre FIXE. Rien à découvrir : on rend le
    dossier du paquet, qui existe, plutôt qu un fichier qui n existe pas.
    """
    paquet = paquet_sources(cible)
    if paquet is None:
        return cible / "backend" / "app" / "main.py"
    for nom in ("main.py", "app.py", "asgi.py", "api.py", "__init__.py"):
        if (paquet / nom).is_file():
            return paquet / nom
    return paquet


def _localisation_par_route(sources: list[Path]) -> dict[tuple[str, str], str]:
    """(METHODE, chemin normalisé) -> fichier qui porte le décorateur de cette route.

    Le schéma OpenAPI déclare la surface mais ne dit pas OÙ elle est écrite. La table des
    handlers (`invariants.handlers`) résout déjà le décorateur ; ici on retient le FICHIER,
    pour qu un constat sur `POST /factures` pointe le module du routeur qui la déclare et non
    un `main.py` générique qui ne la mentionne pas.
    """
    par_route: dict[tuple[str, str], str] = {}
    for fichier in sources:
        try:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in noeud.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                methode = deco.func.attr.upper()
                if methode not in ("GET", "POST", "PUT", "PATCH", "DELETE") or not deco.args:
                    continue
                premier = deco.args[0]
                if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
                    par_route.setdefault((methode, _norm(premier.value)), str(fichier))
    return par_route


def _localiser(
    methode: str, chemin: str, par_route: dict[tuple[str, str], str], defaut: str
) -> str:
    """Fichier où lire la route `<methode> <chemin>` telle que le schéma la PUBLIE.

    Un routeur monté sous préfixe (`include_router(prefix="/api/v1")`) publie `/api/v1/factures`
    là où son décorateur écrit `/factures` : la correspondance exacte échoue précisément sur la
    disposition la plus répandue. Le chemin du décorateur est alors un SUFFIXE du chemin publié
    — on retient le plus long, et seulement s il désigne un fichier UNIQUE. Deux fichiers en
    concurrence ne se départagent pas sans deviner : on retombe sur le module principal, qui
    existe, plutôt que de nommer le mauvais.
    """
    if (methode, chemin) in par_route:
        return par_route[(methode, chemin)]
    suffixes = [
        (declare, fichier)
        for (m, declare), fichier in par_route.items()
        if m == methode and declare != "/" and chemin.endswith(declare)
    ]
    if not suffixes:
        return defaut
    plus_long = max(len(declare) for declare, _ in suffixes)
    fichiers = {fichier for declare, fichier in suffixes if len(declare) == plus_long}
    return fichiers.pop() if len(fichiers) == 1 else defaut


def _montages(cible: Path) -> list[str]:
    """Préfixes montés par `app.mount(...)` — fichiers statiques et sous-applications.

    RT-10. Un montage n est pas une route : il n a pas de décorateur, donc pas de `responses=`,
    et FastAPI n offre AUCUN moyen d en déclarer un. Le contrôle de divergence « code émis mais
    absent de sa déclaration `responses=` » y produisait donc un finding STRUCTURELLEMENT
    incorrigeable côté produit — constaté sur `GET /static/app.js` d ASD Mail Manager. Un
    montage est réputé émettre 200 (fichier servi) et 404 (fichier absent) ; les deux sont le
    comportement documenté de Starlette, pas une promesse du projet.

    TF-0244 : lu dans TOUTES les sources découvertes, plus dans le seul `backend/app/main.py`.
    Sur un projet à racine plate ce fichier n existe pas — l exemption RT-10 ne s appliquait
    donc jamais, et les faux constats qu elle existe pour éteindre revenaient tous.
    """
    prefixes: list[str] = []
    for src in _fichiers_sources(cible):
        try:
            arbre = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
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


def _422_du_cadre(reponse: dict) -> bool:
    """Ce 422 est-il celui que FastAPI ajoute d office, ou un 422 que le projet a ÉCRIT ?

    FastAPI attache à toute route validée une réponse 422 de forme FIXE : description
    « Validation Error » et corps `HTTPValidationError`. Quand le projet déclare son propre 422
    — `responses={422: {"description": "période invalide"}}` ou un modèle d erreur maison —,
    le cadre fusionne la déclaration par-dessus la sienne : la description ou le `$ref` change,
    et la promesse redevient discernable DANS LE SCHÉMA.

    C est ce qui permet de faire foi à `app.openapi()` sans réintroduire une lecture de source :
    le schéma porte, dans sa forme même, la trace de qui a écrit la réponse.
    """
    if (reponse.get("description") or "") != _422_CADRE_DESCRIPTION:
        return False
    contenu = (reponse.get("content") or {}).get("application/json") or {}
    ref = (contenu.get("schema") or {}).get("$ref") or ""
    return not ref or ref.rsplit("/", 1)[-1] == _422_CADRE_MODELE


def _inventaire_openapi(cible: Path) -> list[Element]:
    """Surface lue dans le schema que l application DECLARE — source primaire du CDC.

    TF-0244 : les codes DÉCLARÉS y sont lus aussi, `app.openapi()` faisant foi (règle R3). La
    lecture de source qui les fournissait avant ratait toute application à routeurs et tout
    `responses=` refermé par un argument multiligne — d où un 422 pourtant déclaré compté comme
    « émis mais non déclaré », faux constat instruit au run du 15/08 (contestation RT-18
    retenue).
    """
    schema = schema_openapi(str(cible))
    if not schema:
        return []
    elements: list[Element] = []
    defaut = str(_module_principal(cible))
    par_route = _localisation_par_route(_fichiers_sources(cible))
    for chemin, operations in schema.get("paths", {}).items():
        c = _norm(chemin)
        for methode, operation in operations.items():
            if methode not in ("get", "post", "put", "patch", "delete"):
                continue
            m = methode.upper()
            # Le constat se localise LÀ OÙ la route est écrite (TF-0244), pas dans un `main.py`
            # supposé : sur un projet à routeurs, ce fichier ne la mentionne même pas.
            source = _localiser(m, c, par_route, defaut)
            elements.append(Element(f"endpoint:{m} {c}", PAN, f"{m} {c}", source))
            for code, reponse in (operation.get("responses") or {}).items():
                # FastAPI ajoute un 422 a toute route validee, sans que personne l ait declare.
                # Sur un GET sans corps il est inatteignable : l exiger accuse la suite d un
                # trou qui n existe pas. Retenu SEULEMENT quand le projet l a ecrit lui-meme.
                if code == "422" and _422_du_cadre(reponse if isinstance(reponse, dict) else {}):
                    continue
                elements.append(
                    Element(f"code:{m} {c}={code}", PAN, f"{m} {c} -> {code}", source)
                )
    return elements


def inventaire(cible: Path) -> list[Element]:
    par_schema = _inventaire_openapi(cible)
    if par_schema:
        return par_schema
    src = _module_principal(cible)
    if not src.is_file():
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
            # TF-0244 — la localisation SUIT l élément, qui la tient du fichier où sa route est
            # écrite. `source` (le module principal) ne sert plus que d ancre de dernier
            # recours : un constat sur `POST /api/v1/factures` désignait `main.py`, qui ne
            # mentionne même pas cette route sur un projet à routeurs.
            ou = element.source or str(source)
            findings.append(
                Finding(
                    id=f"divergence:{element.id}",
                    classe=classes.DIVERGENCE,
                    localisation=ou,
                    message=(
                        f"code {code} déclaré pour {signature} mais aucune garde de "
                        f"{fonction}() ne le lève"
                    ),
                    risque=coter(PAN, element.id, ou),
                )
            )
    return findings, non_juge


def analyser(cible: Path) -> SortieAdaptateur:
    inv = inventaire(cible)
    # TF-0403 (RF-5, lot SCC-FR) — ce pan exige un objet ASGI importable (`FORGE_TESTS_APP`) là
    # où il n'a besoin que d'une SURFACE (routes × codes). Un back Node/Koa (Strapi) n'est pas
    # un back mal configuré : aucun `module:attribut` Python n'existera jamais chez lui, et
    # réclamer cette configuration est une action sans issue. Le motif distingue donc les deux
    # cas — et nomme la voie de sortie : une sonde HTTP sur instance servie (schéma OpenAPI
    # exporté ou routes déclarées, `FORGE_TESTS_QUALIF_ROUTES`), la provenance étant
    # indifférente à un pan qui compare des routes et des codes.
    from forge_tests.disposition import racine_execution as _racine

    _rex = _racine(cible)
    if (_rex / "package.json").is_file() and not (_rex / "pyproject.toml").is_file():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "api : ÉCOSYSTÈME NON COUVERT — le back de ce projet est Node "
                f"(`{(_rex / 'package.json').as_posix()}`), et cet adaptateur exige une "
                "application ASGI Python importable (`FORGE_TESTS_APP = module:attribut`). Ce "
                "n'est PAS une configuration manquante : aucune valeur de FORGE_TESTS_APP ne "
                "rendra ce pan mesurable ici. Voie de sortie (RF-5) : une sonde HTTP sur "
                "instance servie — schéma OpenAPI exporté, ou routes déclarées via "
                "FORGE_TESTS_QUALIF_ROUTES — le pan compare des routes et des codes, la "
                "provenance lui est indifférente",
            ],
        )
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
                classe=classes.SONDE_MUETTE,
                localisation=str(_module_principal(cible)),
                message=AVERTISSEMENT_SONDE_MUETTE,
                severite="signale",
            ),
        )
    # TF-0244 — QUELLE source a fourni les declarations. Sans schema, le controle de divergence
    # ci-dessous s appuie sur une lecture partielle : le dire est la condition pour qu un de ses
    # constats puisse etre instruit sans faire perdre un cycle a qui le recoit.
    if not schema_openapi(str(cible)):
        sortie.non_juge.append(NON_JUGE_SANS_SCHEMA)
    else:
        sortie.non_juge.append(NON_JUGE_422)
    # Un code EMIS pendant la suite mais absent de `responses=` est une divergence entre ce que
    # la source declare et ce que le code fait. Ni un trou de couverture, ni un silence : un ecart.
    # Un code d invariant metier DECLARE mais qu aucune garde du code ne peut produire est une
    # divergence : la source promet une erreur que le comportement ne sait plus lever.
    source = _module_principal(cible)
    sources = _fichiers_sources(cible)
    localisations = _localisation_par_route(sources)
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
        # TF-0244 — le constat pointe le fichier qui declare la route, pas un `main.py` suppose :
        # c est la que le lecteur ira ajouter le `responses=` manquant.
        signature = identifiant[len("code:") :].rsplit("=", 1)[0]
        methode, _, chemin = signature.partition(" ")
        ou = _localiser(methode, chemin, localisations, str(source))
        sortie.findings.append(
            Finding(
                id=identifiant,
                classe=classes.DIVERGENCE,
                localisation=ou,
                message="code émis par l'application mais absent de sa déclaration responses=",
                severite="signale",
                risque=coter(PAN, identifiant, ou),
            )
        )
    return sortie
