"""Adaptateur parcours-personas — un parcours de bout en bout PAR persona déclaré (TF-2123).

Fait remonté (lot Produit-86 du 03/11/2026) : les parcours de bout en bout par profil ont dû être
écrits par la session à la demande du porteur. Aucun pan ne les exigeait : un produit qui déclare
des personas pouvait passer l audit avec une suite qui ne joue qu une identité, ou aucun parcours.

Ce pan lit deux choses, SANS EXÉCUTION et sans réseau :

  - **les personas ou rôles que le produit DÉCLARE** — jamais devinés. Trois sources, réunies :
    les clés `personas` et `roles` de `EXIGENCES.json` (chemin de `FORGE_TESTS_EXIGENCES`, sinon
    `EXIGENCES.json`, `forge/EXIGENCES.json` ou `forge/etapes/conception/EXIGENCES.json`), les
    `profils` de `forge/matrice-droits.json`, et les comptes de test par rôle de
    `FORGE_TESTS_QUALIF_STORAGE_STATES` (`role=chemin`, virgules). Un élément `persona:<clé>` par
    persona, qui porte ses sources ;
  - **les parcours de bout en bout** : un fichier de test qui PILOTE UN NAVIGATEUR (Playwright,
    Cypress, Selenium, Puppeteer), navigue (`goto`, `cy.visit`…) et CITE le persona, par son nom
    de fichier ou dans son texte. Un persona qu aucun parcours ne cite est `non exercé` : un
    FAIL nommé, avec le persona.

CE QUE LE VOLET STATIQUE NE FAISAIT PAS, et que le jeu fait désormais (TF-2123, suite) : un
persona « exercé » par citation signifiait « un parcours le cite », pas « ce parcours passe ». Quand
une instance servie est déclarée (`FORGE_TESTS_QUALIF_URL`, à défaut `FORGE_TESTS_BASE_URL`) et que
le rôle du persona a un compte (`FORGE_TESTS_QUALIF_STORAGE_STATES`, `role=chemin`), le pan JOUE les
routes que son parcours navigue, sous les cookies et le jeton de ce compte, en GET seulement. Un
élément `joue:<persona>` s ajoute à l inventaire ; il est exercé quand chaque route répond sans
refus, sans erreur et sans renvoi vers la mire. Sans instance, sans compte pour un rôle, ou instance
injoignable, le persona n est PAS joué, et le rapport le dit : ni succès ni échec du produit.

Ce que le jeu ne fait toujours pas, et il le dit à chaque rapport : il ne clique pas, ne remplit
aucun formulaire et n exécute aucun JavaScript. C est un parcours HTTP des routes navigées ; le pan
qualif multi-sessions (TF-0316) parcourt l application rendue.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from forge_tests import classes, droits, exclusions
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "parcours-personas", "parcours-personas", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publié tel quel au rapport.
POUR_COUVRIR = (
    "écrire, pour chaque persona ou rôle déclaré (clés `personas` ou `roles` d EXIGENCES.json, "
    "`profils` de forge/matrice-droits.json, comptes de FORGE_TESTS_QUALIF_STORAGE_STATES), au "
    "moins un test de bout en bout qui pilote un navigateur, navigue, et nomme ce persona dans son "
    "nom de fichier ou son texte ; fournir l instance servie (FORGE_TESTS_QUALIF_URL ou "
    "FORGE_TESTS_BASE_URL) et un compte par rôle (FORGE_TESTS_QUALIF_STORAGE_STATES) pour que le "
    "pan JOUE ce parcours sous l identité du rôle"
)

# Chapitre de cahier que ce pan alimente, DÉRIVÉ du registre par le cahier et le dashboard.
CHAPITRES = (
    {"code": "F7", "famille": "fonctionnel", "titre": "Parcours par persona",
     "decoupe": "persona", "axe_cas": "unitaire"},
)

NON_JUGE = [
    "parcours-personas : statique — un persona est tenu pour exercé (`persona:<clé>`) quand un "
    "fichier de test de bout en bout (navigateur piloté, navigation) le CITE par son nom de "
    "fichier ou dans son texte ; la citation seule ne prouve pas qu un parcours cité passe, le "
    "jeu contre l instance est un élément à part (`joue:<clé>`), présent quand il a lieu",
    "parcours-personas : quand le jeu a lieu (instance et compte par rôle fournis), il rejoue en "
    "GET les routes que le parcours NAVIGUE (littéraux de `goto`, `visit`…), sous les cookies et "
    "le jeton du storage state du rôle ; il ne joue ni clic ni formulaire ni JavaScript. Une "
    "application à page unique qui répond 200 sur son enveloppe et renvoie vers la mire côté "
    "client n est pas vue ici : c est le pan qualif multi-sessions qui parcourt l application "
    "rendue",
    "parcours-personas : une citation n est pas un parcours DÉDIÉ — un persona au nom courant "
    "(« admin ») cité dans un parcours écrit pour un autre est tenu pour exercé ; la lecture "
    "du fichier désigné reste humaine",
    "parcours-personas : seuls les pilotes Playwright, Cypress, Selenium et Puppeteer sont "
    "reconnus ; un parcours écrit avec un autre outil n est pas vu",
    "parcours-personas : les personas ne sont lus que dans EXIGENCES.json (clés `personas` et "
    "`roles`, convention de cette forge : le schéma du référentiel ne les définit pas), la matrice "
    "des droits et les comptes par rôle ; un persona seulement décrit en prose n est pas vu",
]

_CLES_EXIGENCES = ("personas", "roles")
_CHAMPS_NOM = ("nom", "libelle", "role", "persona", "name", "id")
_EXIGENCES = ("EXIGENCES.json", "forge/EXIGENCES.json", "forge/etapes/conception/EXIGENCES.json")
# Littéral de `forge_tests.livrables.exigences.VARIABLE`, recopié pour ne pas importer le paquet
# `livrables` depuis un adaptateur (`livrables/__init__` importe le REGISTRE des adaptateurs :
# l import serait circulaire). L égalité des deux est TESTÉE.
_VARIABLE_EXIGENCES = "FORGE_TESTS_EXIGENCES"
_ENV_COMPTES = "FORGE_TESTS_QUALIF_STORAGE_STATES"
_ENV_INSTANCE = "FORGE_TESTS_BASE_URL"
_ENV_INSTANCE_QUALIF = "FORGE_TESTS_QUALIF_URL"
_PLAFOND_OCTETS = 512 * 1024

# --- Parcours de bout en bout -------------------------------------------------------------------
_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")
_NOM_DE_TEST = re.compile(
    r"(?:\.(?:spec|test|e2e|cy)\.[cm]?[jt]sx?|(?:^|/)test_[^/]*\.py|_test\.py)$", re.IGNORECASE
)
_DOSSIERS_E2E = {"e2e", "cypress", "playwright", "parcours", "end-to-end"}
_PILOTE_NAVIGATEUR = re.compile(
    r"@playwright/test|\bplaywright\b|\bcypress\b|\bcy\.visit\s*\(|\bselenium\b|\bpuppeteer\b",
    re.IGNORECASE,
)
_NAVIGATION = re.compile(r"\.goto\s*\(|\bcy\.visit\s*\(|\bdriver\.get\s*\(|\.navigate\s*\(")


def _sans_accent(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def _cle(texte: str) -> str:
    """Clé stable d un persona : minuscules, sans accent, séparateurs réduits à un tiret."""
    return re.sub(r"[^a-z0-9]+", "-", _sans_accent(texte).lower()).strip("-")


def _motif(cle: str) -> re.Pattern[str]:
    """Le persona cité en MOT ENTIER dans un texte normalisé (`gestionnaire-rh` ~ `gestionnaire
    rh`, `gestionnaire_rh`), jamais comme fragment d un autre mot (`administrateur` ≠ `admin`)."""
    morceaux = [re.escape(m) for m in cle.split("-") if m]
    return re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]{1,3}".join(morceaux) + r"(?![a-z0-9])")


# --- Personas déclarés --------------------------------------------------------------------------
def _noms_de(entree: object) -> list[str]:
    """Le nom d un persona, puis ses alias : `{"id": "P1", "nom": "Approbateur"}` se cite par
    l un ou l autre. Une chaîne seule est son propre nom."""
    if isinstance(entree, str):
        return [entree.strip()] if entree.strip() else []
    noms: list[str] = []
    if isinstance(entree, dict):
        for champ in _CHAMPS_NOM:
            valeur = entree.get(champ)
            if isinstance(valeur, str) and valeur.strip() and valeur.strip() not in noms:
                noms.append(valeur.strip())
    return noms


def _chemin_exigences(cible: Path) -> Path | None:
    brut = (os.environ.get(_VARIABLE_EXIGENCES) or "").strip()
    if brut:
        return Path(brut)
    for relatif in _EXIGENCES:
        if (cible / relatif).is_file():
            return cible / relatif
    return None


def _comptes_par_role(cible: Path) -> list[str]:
    """Rôles des comptes de test : `role=chemin`, séparés par des virgules (environnement, puis
    `.env.forge-tests` du projet). Lus sans rien écrire dans l environnement du processus."""
    brut = _valeur_declaree(cible, _ENV_COMPTES)
    roles = []
    for paire in brut.split(","):
        role, separateur, _chemin = paire.partition("=")
        if separateur and role.strip():
            roles.append(role.strip())
    return roles


def declares(cible: Path) -> tuple[dict[str, dict], list[str]]:
    """({clé: {"libelle", "sources": [...]}}, notes sur ce qui n a pas pu être lu).

    Une source illisible est une NOTE, jamais un silence : le pan ne prétend pas « aucun persona »
    sur un fichier qu il n a pas pu lire.
    """
    trouves: dict[str, dict] = {}
    notes: list[str] = []

    def ajouter(noms: list[str], source: str) -> None:
        cles = [c for c in (_cle(n) for n in noms) if c]
        if not cles:
            return
        entree = trouves.setdefault(cles[0], {"libelle": noms[0], "sources": [], "alias": []})
        for alias in cles[1:]:
            if alias not in entree["alias"]:
                entree["alias"].append(alias)
        if source not in entree["sources"]:
            entree["sources"].append(source)

    chemin = _chemin_exigences(cible)
    if chemin is not None:
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erreur:
            notes.append(
                f"parcours-personas : {chemin.name} illisible ({type(erreur).__name__}) — les "
                "personas qu il déclare ne sont pas connus, donc pas exigés"
            )
        else:
            if isinstance(donnees, dict):
                for cle in _CLES_EXIGENCES:
                    liste = donnees.get(cle)
                    for entree in liste if isinstance(liste, list) else []:
                        ajouter(_noms_de(entree), f"{chemin.name}:{cle}")

    matrice = droits.lire(cible)
    if matrice.get("_illisible"):
        notes.append(
            f"parcours-personas : {matrice['_illisible']} — les profils qu elle déclare ne "
            "sont pas connus, donc pas exigés"
        )
    for profil in matrice.get("profils") or []:
        ajouter([str(profil)], droits.FICHIER)

    for role in _comptes_par_role(cible):
        ajouter([role], _ENV_COMPTES)
    return trouves, notes


# --- Parcours de bout en bout trouvés -----------------------------------------------------------
def _est_un_parcours_e2e(relatif: str, texte: str) -> bool:
    nom_de_test = bool(_NOM_DE_TEST.search(relatif)) or bool(
        {p.lower() for p in Path(relatif).parts[:-1]} & _DOSSIERS_E2E
    )
    pilote = bool(_PILOTE_NAVIGATEUR.search(texte))
    return nom_de_test and pilote and bool(_NAVIGATION.search(texte))


def _parcours_bruts(cible: Path) -> list[tuple[str, str]]:
    """(chemin relatif, texte BRUT) de chaque parcours de bout en bout — la casse des routes que le
    jeu rejoue doit survivre, la normalisation du repérage la détruit."""
    trouves: list[tuple[str, str]] = []
    for racine, dossiers, fichiers in os.walk(cible):
        # Élagage : on ne descend ni dans les dépendances ni dans ce que git ignore.
        dossiers[:] = sorted(
            d for d in dossiers
            if not exclusions.dossier_exclu(d)
            and not exclusions.ignore_par_git(Path(racine, d), cible)
        )
        for nom in sorted(fichiers):
            chemin = Path(racine, nom)
            if chemin.suffix.lower() not in _EXTENSIONS:
                continue
            try:
                if chemin.stat().st_size > _PLAFOND_OCTETS:
                    continue
                texte = chemin.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relatif = chemin.relative_to(cible).as_posix()
            if _est_un_parcours_e2e(relatif, texte):
                trouves.append((relatif, texte))
    return trouves


def _parcours(cible: Path) -> list[tuple[str, str]]:
    """(chemin relatif, texte normalisé nom+contenu) de chaque parcours de bout en bout."""
    return [
        (relatif, _sans_accent(f"{relatif}\n{texte}").lower())
        for relatif, texte in _parcours_bruts(cible)
    ]


def parcours_par_persona(cible: Path, personas: dict[str, dict]) -> dict[str, list[str]]:
    """{clé du persona: [chemins des parcours qui le citent]} — liste vide : aucun parcours."""
    parcours = _parcours(cible)
    resultat: dict[str, list[str]] = {}
    for cle, entree in personas.items():
        motifs = [_motif(c) for c in (cle, *entree.get("alias", ()))]
        resultat[cle] = [
            relatif for relatif, texte in parcours if any(m.search(texte) for m in motifs)
        ]
    return resultat


# --- Le jeu des parcours contre l instance servie (TF-2123, suite) ------------------------------
#: Nombre maximal de routes jouées par persona. Au-delà, le rapport le dit : un parcours qui navigue
#: plus de routes que cela est une exploration, pas un parcours, et le jeu s'arrête à la borne.
PLAFOND_ROUTES = 12
_DELAI_REQUETE_S = 15
_SAUTS_MAX = 5
# Une adresse dont le NOM porte une action. Un GET n'est sûr que par convention : jouer `/logout`
# fermerait la session du compte d'audit, `/supprimer` ou `/reset` modifierait l'instance. Ces
# routes ne sont pas jouées, et le rapport les nomme.
_ROUTE_A_EFFET = re.compile(
    r"(?:^|[/_-])(?:logout|log-out|signout|sign-out|deconnexion|deconnecter|se-deconnecter"
    r"|delete|supprimer|suppression|remove|reset|destroy|purge)(?:$|[/_.-])",
    re.IGNORECASE,
)
_GOTO_LITTERAL = re.compile(
    r"""(?:\.goto|\bcy\.visit|\bdriver\.get|\.navigate)\s*\(\s*(?P<q>['"`])(?P<route>[^'"`]*)(?P=q)"""
)
# Premier segment d une adresse qui est la mire de connexion : y atterrir, c est ne pas avoir de
# session acceptée. Un jeu dont la route demandée EST la mire n y voit pas un échec.
_MIRES = {
    "login", "connexion", "signin", "sign-in", "auth", "authentification", "se-connecter",
    "log-in", "identification",
}


def routes_du_parcours(brut: str) -> list[str]:
    """Les routes que ce parcours NAVIGUE, dans l ordre, sans doublon — littéraux seulement.

    Une adresse construite (`${id}`, concaténation), une adresse absolue vers un autre hôte ou une
    chaîne vide ne sont pas des routes que le jeu peut rejouer sans deviner : elles sont écartées,
    et un parcours qui n en garde aucune joue la racine (le rapport le dit).
    """
    routes: list[str] = []
    for trouve in _GOTO_LITTERAL.finditer(brut):
        route = trouve.group("route").strip()
        if not route.startswith("/") or "${" in route or route.startswith("//"):
            continue
        route = route.split("#")[0]
        chemin = route.split("?")[0] or "/"
        if chemin not in routes:
            routes.append(chemin)
    return routes


def _valeur_declaree(cible: Path, cle: str) -> str:
    """Une clé de configuration, SANS rien écrire dans l environnement du processus.

    Dans l ordre : l environnement de l opérateur, `.env.forge-tests`, puis le fichier d audit
    versionné du produit."""
    from forge_tests.authentification import ENV_AUDIT, ENV_PROJET, _valeurs

    brut = os.environ.get(cle)
    if brut and brut.strip():
        return brut.strip()
    for fichier in (ENV_PROJET, ENV_AUDIT):
        valeur = _valeurs(Path(cible) / fichier).get(cle, "").strip()
        if valeur:
            return valeur
    return ""


def instance_declaree(cible: Path) -> str:
    """L instance servie que le jeu joint : `FORGE_TESTS_QUALIF_URL`, à défaut `..._BASE_URL`
    (même ordre que le pan qualif, qui parcourt l instance peuplée)."""
    for cle in (_ENV_INSTANCE_QUALIF, _ENV_INSTANCE):
        valeur = _valeur_declaree(cible, cle)
        if valeur:
            return valeur if valeur.startswith(("http://", "https://")) else f"https://{valeur}"
    return ""


def identites(cible: Path) -> dict[str, str]:
    """{étiquette de rôle: chemin du storage state} — `role=chemin`, séparés par des virgules."""
    brut = _valeur_declaree(cible, _ENV_COMPTES)
    trouvees: dict[str, str] = {}
    for paire in brut.split(","):
        role, separateur, chemin = paire.partition("=")
        if separateur and role.strip() and chemin.strip():
            trouvees.setdefault(role.strip(), chemin.strip())
    return trouvees


def _identite_du_persona(
    cle: str, entree: dict, trouvees: dict[str, str]
) -> tuple[str, str] | None:
    """(étiquette, chemin) du compte de ce persona : l étiquette du rôle, normalisée comme la
    clé du persona, égale à sa clé ou à l un de ses alias."""
    voulues = {cle, *entree.get("alias", ())}
    for role, chemin in trouvees.items():
        if _cle(role) in voulues:
            return role, chemin
    return None


def _lire_etat(cible: Path, chemin: str) -> tuple[dict | None, str | None]:
    fichier = Path(chemin)
    if not fichier.is_absolute():
        fichier = Path(cible) / fichier
    try:
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return None, f"« {fichier.name} » illisible ({type(erreur).__name__})"
    if not isinstance(donnees, dict):
        return None, f"« {fichier.name} » n est pas un storage state (objet JSON attendu)"
    return donnees, None


def _cookie_vaut_pour(cookie: dict, hote: str, chemin: str, https: bool) -> bool:
    domaine = str(cookie.get("domain") or "")
    if not domaine and cookie.get("url"):
        domaine = urlsplit(str(cookie["url"])).hostname or ""
    domaine = domaine.lstrip(".").lower()
    if not domaine or not (hote == domaine or hote.endswith("." + domaine)):
        return False
    portee = str(cookie.get("path") or "/")
    if not chemin.startswith(portee):
        return False
    boucle_locale = hote in ("localhost", "127.0.0.1", "::1")
    return not (cookie.get("secure") and not https and not boucle_locale)


def _en_tetes(etat: dict, base: str, chemin: str) -> dict[str, str]:
    """Les en-têtes d identité d un storage state pour cette requête : les cookies dont le domaine
    et le chemin portent, et le jeton du stockage local de la même origine en `Authorization`."""
    from forge_tests.authentification import CLE_STOCKAGE

    morceaux = urlsplit(base)
    hote = (morceaux.hostname or "").lower()
    https = morceaux.scheme == "https"
    cookies = [
        f"{c['name']}={c['value']}"
        for c in etat.get("cookies") or []
        if isinstance(c, dict) and "name" in c and "value" in c
        and _cookie_vaut_pour(c, hote, chemin, https)
    ]
    en_tetes: dict[str, str] = {}
    if cookies:
        en_tetes["Cookie"] = "; ".join(cookies)
    origine = f"{morceaux.scheme}://{morceaux.netloc}".lower()
    for entree in etat.get("origins") or []:
        if not isinstance(entree, dict):
            continue
        if str(entree.get("origin", "")).lower().rstrip("/") != origine:
            continue
        for element in entree.get("localStorage") or []:
            if isinstance(element, dict) and element.get("name") == CLE_STOCKAGE:
                en_tetes["Authorization"] = f"Bearer {element.get('value', '')}"
    return en_tetes


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Les redirections sont suivies À LA MAIN : chaque saut est lu, et le dernier dit où la route
    a atterri (la mire de connexion, ou un autre hôte)."""

    def redirect_request(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN201
        return None


def _est_la_mire(chemin: str) -> bool:
    premier = chemin.strip("/").split("/")[0].lower()
    return premier in _MIRES


def _jouer_route(base: str, route: str, etat: dict) -> tuple[str, str]:
    """(issue, détail) d un GET de `route` sous l identité de `etat`.

    Issues : `ok` · `refuse` (401, 403) · `mire` (renvoyée vers la mire, ou hors de l instance) ·
    `erreur` (404, 5xx, autre code) · `injoignable`. GET seulement.
    """
    ouvreur = urllib.request.build_opener(_SansRedirection)
    courant = base.rstrip("/") + route
    for _saut in range(_SAUTS_MAX + 1):
        morceaux = urlsplit(courant)
        origine_base = urlsplit(base)
        if morceaux.netloc.lower() != origine_base.netloc.lower():
            return "mire", f"renvoyée hors de l instance ({morceaux.netloc})"
        requete = urllib.request.Request(  # noqa: S310 — l URL est celle que l opérateur déclare
            courant, headers=_en_tetes(etat, base, morceaux.path or "/"), method="GET"
        )
        try:
            with ouvreur.open(requete, timeout=_DELAI_REQUETE_S) as reponse:  # noqa: S310
                code, lieu = reponse.status, ""
        except urllib.error.HTTPError as erreur:
            code, lieu = erreur.code, erreur.headers.get("Location", "")
        except (urllib.error.URLError, OSError, ValueError) as erreur:
            cause = getattr(erreur, "reason", erreur)
            return "injoignable", f"{type(cause).__name__}"
        if 300 <= code < 400 and lieu:
            courant = urljoin(courant, lieu)
            continue
        if code in (401, 403):
            return "refuse", f"{code}"
        if 200 <= code < 300:
            arrivee = urlsplit(courant).path or "/"
            if _est_la_mire(arrivee) and not _est_la_mire(route):
                return "mire", f"renvoyée vers la mire {arrivee}"
            return "ok", f"{code}"
        return "erreur", f"{code}"
    return "erreur", f"plus de {_SAUTS_MAX} redirections"


def jouer(cible: Path, personas_: dict[str, dict]) -> dict:
    """Joue, pour chaque persona qu un parcours cite ET dont le rôle a un compte, les routes de
    ce parcours contre l instance déclarée. Aucun effet de bord sur l instance : GET seulement.

    Rend `{"instance", "joues", "sans_identite", "illisibles", "injoignables", "sans_parcours"}`.
    `joues[cle]` porte le rôle, le fichier du compte (son NOM, jamais son contenu), les routes
    avec leur issue, `ok` et la liste des parcours dont elles viennent.
    """
    base = instance_declaree(cible)
    jeu: dict = {"instance": base, "joues": {}, "sans_identite": [], "illisibles": {},
                 "injoignables": [], "sans_parcours": [], "ecartees": {}, "sans_route_jouable": []}
    if not base:
        return jeu
    comptes = identites(cible)
    bruts = dict(_parcours_bruts(cible))
    cites = parcours_par_persona(cible, personas_)
    for cle, entree in sorted(personas_.items()):
        fichiers = cites.get(cle) or []
        if not fichiers:
            jeu["sans_parcours"].append(cle)
            continue
        compte = _identite_du_persona(cle, entree, comptes)
        if compte is None:
            jeu["sans_identite"].append(cle)
            continue
        role, chemin = compte
        etat, motif = _lire_etat(cible, chemin)
        if etat is None:
            jeu["illisibles"][cle] = motif
            continue
        routes: list[str] = []
        for relatif in fichiers:
            for route in routes_du_parcours(bruts.get(relatif, "")):
                if route not in routes:
                    routes.append(route)
        a_effet = [r for r in routes if _ROUTE_A_EFFET.search(_sans_accent(r))]
        if a_effet:
            jeu["ecartees"][cle] = a_effet
            routes = [r for r in routes if r not in a_effet]
            if not routes:
                jeu["sans_route_jouable"].append(cle)
                continue
        sans_route = not routes
        total = len(routes)
        routes = (routes or ["/"])[:PLAFOND_ROUTES]
        issues = []
        for route in routes:
            issue, detail = _jouer_route(base, route, etat)
            issues.append({"route": route, "issue": issue, "detail": detail})
        if all(i["issue"] == "injoignable" for i in issues):
            jeu["injoignables"].append(cle)
            continue
        jeu["joues"][cle] = {
            "role": role,
            "compte": Path(chemin).name,
            "routes": issues,
            "ok": all(i["issue"] == "ok" for i in issues),
            "parcours": fichiers,
            "routes_navigees": total,
            "racine_par_defaut": sans_route,
        }
    return jeu


# --- Contrat d adaptateur -----------------------------------------------------------------------
def _fichier_source(cible: Path, source: str) -> str:
    """Le fichier qui porte la déclaration (jamais un nom de variable), pour localiser."""
    brut = source.split(":")[0]
    if brut == _ENV_COMPTES:
        return str(cible / ".env.forge-tests")
    return str(cible / brut)


def inventaire(cible: Path) -> list[Element]:
    personas, _ = declares(cible)
    return [
        Element(
            f"persona:{cle}",
            PAN,
            f"persona « {entree['libelle']} » (déclaré par {', '.join(entree['sources'])}) — "
            "exige au moins un parcours de bout en bout",
            _fichier_source(cible, entree["sources"][0]),
        )
        for cle, entree in sorted(personas.items())
    ]


def exerces(cible: Path) -> set[str]:
    personas, _ = declares(cible)
    cites = parcours_par_persona(cible, personas)
    return {f"persona:{cle}" for cle, parcours in cites.items() if parcours}


def _elements_du_jeu(cible: Path, jeu: dict, personas_: dict[str, dict]) -> list[Element]:
    """Un élément `joue:<persona>` par persona dont le parcours a pu être joué sous son identité.

    Un persona sans compte, au compte illisible ou dont l instance est injoignable n a PAS
    d élément : il n a pas été joué, et le dire (non_juge) est plus honnête que l accuser d un
    échec du produit ou le compter pour un succès.
    """
    elements = []
    for cle, joue in sorted(jeu["joues"].items()):
        libelle = personas_[cle]["libelle"]
        elements.append(
            Element(
                f"joue:{cle}",
                PAN,
                f"parcours de « {libelle} » joué contre l instance sous l identité du rôle "
                f"« {joue['role']} »",
                str(Path(cible) / joue["parcours"][0]),
            )
        )
    return elements


_PHRASES_ISSUE = {
    "refuse": lambda d: f"refusée à ce rôle (HTTP {d})",
    "mire": lambda d: d,
    "erreur": lambda d: f"en erreur (HTTP {d})" if d.isdigit() else d,
    "injoignable": lambda d: f"injoignable ({d})",
}


def _message_du_jeu(libelle: str, joue: dict, instance: str) -> str:
    """La phrase d un constat de jeu : le persona, le rôle, les routes en défaut et pourquoi."""
    fautives = [r for r in joue["routes"] if r["issue"] != "ok"]
    montrees = "; ".join(
        f"{r['route']} : {_PHRASES_ISSUE[r['issue']](r['detail'])}" for r in fautives[:5]
    )
    reste = f"; … et {len(fautives) - 5} autre(s)" if len(fautives) > 5 else ""
    return (
        f"persona « {libelle} » : parcours joué sous l identité du rôle « {joue['role']} » "
        f"contre {instance} — {len(fautives)} route(s) sur {len(joue['routes'])} en défaut : "
        f"{montrees}{reste}"
    )


def _jeu_non_realise() -> str:
    return (
        "parcours-personas : le jeu de chaque parcours contre l instance servie, sous l identité "
        "du rôle, n est PAS réalisé ici — il exige l instance servie (FORGE_TESTS_QUALIF_URL ou "
        f"FORGE_TESTS_BASE_URL) et un compte par rôle ({_ENV_COMPTES}, `role=chemin`)"
    )


def _mentions_du_jeu(jeu: dict, personas_: dict[str, dict]) -> list[str]:
    """Ce que le jeu a fait, et surtout ce qu il n a pas fait : une ligne par réserve."""
    nom = {cle: entree["libelle"] for cle, entree in personas_.items()}
    base = jeu["instance"]
    if not base:
        return [
            "parcours-personas : aucune instance servie déclarée (FORGE_TESTS_QUALIF_URL ou "
            "FORGE_TESTS_BASE_URL) — le jeu des parcours par persona contre une instance est "
            "impossible tant qu elle n est pas fournie",
            _jeu_non_realise(),
        ]
    lignes: list[str] = []
    joues = jeu["joues"]
    if joues:
        detail = " · ".join(
            f"{cle} sous « {j['role']} » : "
            + ", ".join(f"{r['route']} {r['detail']}" for r in j["routes"])
            for cle, j in sorted(joues.items())
        )
        lignes.append(
            f"parcours-personas : JEU RÉEL — {len(joues)} parcours joué(s) contre {base} sous "
            f"l identité du rôle de chaque persona, en GET seulement (l instance n est jamais "
            f"modifiée) : {detail}"
        )
    else:
        lignes.append(
            "parcours-personas : une instance servie est déclarée (FORGE_TESTS_QUALIF_URL ou "
            "FORGE_TESTS_BASE_URL) mais ce pan n y joue AUCUN parcours — aucun persona cité par "
            f"un parcours n a pu être joué sous son identité ({_ENV_COMPTES}, `role=chemin`)"
        )
    if jeu["sans_identite"]:
        lignes.append(
            f"parcours-personas : {len(jeu['sans_identite'])} persona(s) cité(s) par un parcours "
            f"mais SANS identité — non joué(s) : "
            + ", ".join(nom[c] for c in jeu["sans_identite"])
            + f" ; fournir un compte par rôle dans {_ENV_COMPTES} (`role=chemin`, un storage state "
            "par rôle). Ce n est pas un échec du produit"
        )
    for cle, motif in sorted(jeu["illisibles"].items()):
        lignes.append(
            f"parcours-personas : le compte du persona « {nom[cle]} » est {motif} — non joué ; "
            "ce n est ni un succès ni un échec du produit"
        )
    if jeu["injoignables"]:
        lignes.append(
            f"parcours-personas : instance {base} INJOIGNABLE pour "
            + ", ".join(nom[c] for c in jeu["injoignables"])
            + " — non joué(s) ; ce n est ni un succès ni un échec du produit. Démarrer l instance "
            "(commande de démarrage déclarée par le projet) puis `--reprendre` le rapport"
        )
    for cle, ecartees in sorted(jeu["ecartees"].items()):
        lignes.append(
            f"parcours-personas : {len(ecartees)} route(s) du parcours de « {nom[cle]} » NON "
            f"JOUÉE(S) ({', '.join(ecartees[:5])}) : leur nom porte une action (fermer la session, "
            "supprimer, réinitialiser), et un GET sur une telle adresse peut modifier l instance "
            "ou fermer la session du compte d audit"
            + (" ; plus aucune route à jouer, le persona n est pas joué"
               if cle in jeu["sans_route_jouable"] else "")
        )
    for cle, joue in sorted(joues.items()):
        if joue["racine_par_defaut"]:
            lignes.append(
                f"parcours-personas : le parcours de « {nom[cle]} » ne navigue aucune route "
                "littérale : le jeu a joué la racine (`/`) sous son identité, et rien d autre"
            )
        if joue["routes_navigees"] > PLAFOND_ROUTES:
            lignes.append(
                f"parcours-personas : le parcours de « {nom[cle]} » navigue "
                f"{joue['routes_navigees']} routes ; le jeu en rejoue {PLAFOND_ROUTES} (plafond), "
                "les suivantes ne sont pas jouées"
            )
    return lignes


def analyser(cible: Path) -> SortieAdaptateur:
    personas_, notes = declares(cible)
    if not personas_:
        if notes:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[*NON_JUGE, *notes],
            )
        return evaluer_surface(
            NOM, PAN, str(cible), [], set(), SEUIL, NON_JUGE,
            sans_objet=(
                "aucun persona ni rôle déclaré — ni clé `personas` ou `roles` dans EXIGENCES.json, "
                "ni profils dans forge/matrice-droits.json, ni compte par rôle dans "
                f"{_ENV_COMPTES} : ce projet ne déclare pas de persona à parcourir"
            ),
        )
    # Le jeu contre l instance servie (TF-2123, suite) : il ajoute un élément `joue:<persona>` par
    # parcours effectivement joué, exercé quand chacune de ses routes a répondu sous l identité.
    jeu = jouer(cible, personas_)
    exerce = exerces(cible) | {f"joue:{cle}" for cle, j in jeu["joues"].items() if j["ok"]}
    sortie = evaluer_surface(
        NOM, PAN, str(cible),
        [*inventaire(cible), *_elements_du_jeu(cible, jeu, personas_)],
        exerce, SEUIL, NON_JUGE,
    )
    for constat in sortie.findings:
        if constat.id.startswith("joue:"):
            cle = constat.id[len("joue:"):]
            constat.classe = classes.PARCOURS_PERSONA_REFUSE
            constat.message = _message_du_jeu(
                personas_[cle]["libelle"], jeu["joues"][cle], jeu["instance"]
            )
    sortie.non_juge = [*sortie.non_juge, *notes, *_mentions_du_jeu(jeu, personas_)]
    return sortie
