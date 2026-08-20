"""Adaptateur Accessibilité (Q4) — câblage de `oracle-a11y.py`, une route à la fois.

L oracle existait et n était pas appelable : il charge un FICHIER dans Chromium, alors qu une
application à rendu client ne produit son DOM qu une fois servie et exécutée. Le verrou n était
donc pas l oracle mais le banc, qui n était jamais une application vivante.

Ici : on sert le front construit, on visite chaque route, on capture le DOM RENDU, et on donne
chaque capture à l oracle. Un pan entier de Q4 s ouvre sans qu une ligne de l oracle change.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "accessibilite-a11y", "accessibilite"

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "servir le front (build présent et `npm`/navigateur disponibles) ou déclarer l'instance "
    "SERVIE dans FORGE_TESTS_BASE_URL : le pan juge le DOM RENDU de chaque route, il n'a rien "
    "à lire tant qu'aucune page n'est rendue. Application rendue CÔTÉ SERVEUR (gabarits Jinja, "
    "Django, Rails : aucune table de routage sous `frontend/src`) : déclarer ses routes par "
    "FORGE_TESTS_QUALIF_ROUTES — à défaut elles sont relevées sur les liens de la racine servie"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "F4", "famille": "fonctionnel", "titre": "Accessibilité",
     "decoupe": "ecran", "axe_cas": "etats"},
)

# RT-13 : les champs de configuration qui debloquent CE pan, et eux seuls. Sans revendication,
# ils restaient dans le sac partage du domaine « acces » et etaient reclames a tous les pans en
# SKIP — y compris ceux qu aucun compte n aurait rendus mesurables.
CHAMPS_REQUIS = (
    "FORGE_TESTS_BASE_URL",
    "FORGE_TESTS_API_URL",
    "FORGE_TESTS_LOGIN",
    "FORGE_TESTS_PASSWORD",
)

_ORACLE = Path.home() / ".claude" / "skills" / "quality-oracles" / "scripts" / "oracle-a11y.py"

NON_JUGE = [
    "accessibilite : le DOM est capture a l etat INITIAL de chaque route ; les etats atteints "
    "apres interaction (menu ouvert, modale, message d erreur) ne sont pas audites",
    "accessibilite : sans compte configure (.env), les routes protegees redirigent vers la "
    "page publique — le nombre de PAGES DISTINCTES rendues le dit au rapport",
    # RF-6a (lot SCC-FR 20260820a, gravite BLOQUANT) : la version precedente de cette limite
    # disait « perimetre du seul oracle structurel », comme si la famille etait couverte
    # AILLEURS. Elle ne l est pas, et le lecteur cessait de la chercher — le mecanisme exact
    # de TF-0379 (oracle-calculs), paye cinq jours de run. Un non_juge est une promesse de
    # perimetre : il dit desormais QUI couvre quoi dans le parc, et qui ne couvre rien.
    # RF-6a puis TF-0409/O3 (20/08) : cette limite disait « couverts par AUCUN oracle du parc »
    # pour le clavier, et « mesure existante mais NON CABLEE » pour le contraste. Les deux sont
    # desormais des PANS — la limite dit donc QUI couvre quoi, et ce qui reste decouvert. Un
    # non_juge est une promesse de perimetre : le laisser perime le rendrait faux dans l autre
    # sens, en faisant chercher ailleurs ce qui est ici.
    "accessibilite : perimetre du seul oracle structurel. Le CONTRASTE est mesure par le pan "
    "`contraste` (render_page.py V2, luminance WCAG sur styles rendus) et la NAVIGATION "
    "CLAVIER par le pan `clavier` (focus visible, pieges de focus, lien d evitement). Restent "
    "DECOUVERTS : l ARIA avance (roles, ordre de focus coherent avec l ordre de lecture) et "
    "les etats atteints apres interaction — pour un site public francais, RGAA 4.1 est une "
    "obligation legale et ces ecarts se declarent au dossier MEP, ils ne se taisent pas. Et "
    "l audit RGAA complet reste un livrable HUMAIN : un tiers des criteres n est pas "
    "mecanisable, la machine prepare l audit, elle ne rend pas la declaration",
    "accessibilite : les routes RELEVEES sur l instance servie sont celles que la racine LIE — "
    "une page atteinte seulement apres une action (formulaire poste, menu ouvert) ou par une URL "
    "que rien ne lie n y figure pas ; la declarer par FORGE_TESTS_QUALIF_ROUTES (TF-0217)",
]


def _port_disponible() -> int:
    """Port libre choisi a chaque run : un serveur orphelin d un run precedent bloquerait un
    port fixe, et le suivant croirait le front injoignable."""
    with socket.socket() as prise:
        prise.bind(("127.0.0.1", 0))
        return int(prise.getsockname()[1])


def _repond(port: int) -> bool:
    with socket.socket() as prise:
        prise.settimeout(0.4)
        return prise.connect_ex(("127.0.0.1", port)) == 0


def _tuer_arbre(processus: subprocess.Popen) -> None:
    """Sur Windows, terminer le shim npx laisse le node fils VIVANT, qui garde le port."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(processus.pid)],
            capture_output=True, check=False, timeout=30,
        )
    processus.terminate()
    try:
        processus.wait(timeout=20)
    except subprocess.TimeoutExpired:
        processus.kill()


# --- Découverte des routes : le POINT DE PARTAGE (TF-0217) ------------------------------------
#
# RT-3 (lot COMPTA, 14/08) : ce pan et le pan `visuel` lisaient UNIQUEMENT l inventaire de
# `front.py`, qui cherche `frontend/src/routes.jsx`, la convention TanStack ou `<Route path=…>`.
# Sur une application servie par son backend (FastAPI + gabarits Jinja), aucun de ces trois
# chemins n existe : « aucune route » — alors que `FORGE_TESTS_BASE_URL` était servie et que le
# pan `qualif` venait d y parcourir 33 puis 42 éléments. Deux pans perdus pour toute application
# rendue côté serveur, sur une instance pourtant déjà parcourue.
#
# La découverte vit ICI, en fonction unique et publique, et `visuel` l appelle — il importait
# déjà `_capturer` de ce module. Le sens de la dépendance est inchangé (`visuel` → `accessibilite`
# → `front`), et l ajout `accessibilite` → `qualif` ne referme aucun cycle : `qualif` n importe ni
# l un ni l autre. Rien n est recopié de `qualif` : la normalisation d un href en route interne et
# le JS de relevé des liens sont RÉUTILISÉS tels quels, pour qu une seule définition de « route
# interne » existe dans le framework.
PROVENANCE_FRONT = "sources du front"
PROVENANCE_DECLAREE = "déclaration du projet (FORGE_TESTS_QUALIF_ROUTES)"
PROVENANCE_SERVIE = "parcours de l instance servie (FORGE_TESTS_BASE_URL)"

# Le champ par lequel un projet DÉCLARE ses routes. C est celui du pan `qualif`, à dessein : un
# projet ne renseigne pas deux listes pour la même application.
CHAMP_ROUTES = "FORGE_TESTS_QUALIF_ROUTES"
# Découverte bornée : la page racine et ses liens. Le parcours EXHAUSTIF est le métier du pan
# `qualif` ; ici il ne s agit que de savoir QUOI rendre, et une nef de liens suffit à le dire.
PLAFOND_DECOUVERTE = 40


def _base_servie(cible: Path) -> str:
    """URL de l instance que CE pan capturera, ou "" — `FORGE_TESTS_BASE_URL`, et elle seule.

    Volontairement pas de repli sur `FORGE_TESTS_QUALIF_URL` : `_capturer` ne sait servir que
    `BASE_URL`. Découvrir les routes d une instance et rendre celles d une autre produirait un
    audit qui ne porte sur rien.
    """
    from forge_tests.authentification import charger_env

    charger_env(cible)
    base = (os.environ.get("FORGE_TESTS_BASE_URL") or "").strip().rstrip("/")
    return base


def _routes_declarees(cible: Path) -> list[str]:
    """Routes que le PROJET déclare, dans l ordre déclaré. Toute route est ramenée à `/…`."""
    from forge_tests.authentification import charger_env

    charger_env(cible)
    brut = (os.environ.get(CHAMP_ROUTES) or "").split(",")
    routes: list[str] = []
    for morceau in brut:
        route = morceau.strip()
        if not route:
            continue
        route = route if route.startswith("/") else f"/{route}"
        if route not in routes:
            routes.append(route)
    return routes


def _routes_depuis_liens(hrefs: list[str], base: str) -> list[str]:
    """Liens relevés dans une page -> routes internes, dédupliquées et triées.

    Fonction PURE : c est elle qui rend la découverte servie vérifiable sans navigateur. La
    normalisation est celle du pan `qualif` (`_route`) — externe, `mailto:`, ancre et requête
    sont écartés là-bas, une seule fois pour tout le framework.
    """
    from forge_tests.adaptateurs.qualif import _route

    routes = {"/"}
    for href in hrefs:
        interne = _route(href or "", base)
        if interne is not None:
            routes.add(interne)
    return sorted(routes)[:PLAFOND_DECOUVERTE]


def _relever_liens(page, base: str) -> list[str] | None:  # noqa: ANN001
    """Liens de la racine, ou None si la RACINE ELLE-MÊME n a pas été atteinte. Ne lève jamais.

    La distinction porte une décision : racine atteinte sans aucun lien = une route (`/`), et
    elle mérite d être auditée ; racine INJOIGNABLE = aucune route, et le pan doit alors dire
    qu il n a rien pu découvrir plutôt que d inventer un `/` qui ne répond pas.
    """
    from forge_tests.adaptateurs.qualif import _JS_LIENS

    try:
        page.goto(f"{base}/", wait_until="networkidle", timeout=45000)
    except Exception:  # noqa: BLE001 — une instance injoignable est un CONSTAT, pas une panne
        return None
    try:
        return list(page.evaluate(_JS_LIENS) or [])
    except Exception:  # noqa: BLE001 — page rendue mais liens illisibles : la racine reste une route
        return []


def _parcourir_racine(cible: Path, base: str) -> list[str]:
    """Ouvre un navigateur, relève la racine, rend ses routes. [] si rien n est possible.

    Le jeton est posé s il est configuré, exactement comme pour la capture : sans lui, la racine
    d une application protégée ne montre que les liens de la mire.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    from forge_tests.authentification import obtenir_jeton, script_injection

    jeton = obtenir_jeton(cible)
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch()
        contexte = navigateur.new_context()
        if jeton:
            contexte.add_init_script(script_injection(jeton))
        liens = _relever_liens(contexte.new_page(), base)
        routes = [] if liens is None else _routes_depuis_liens(liens, base)
        navigateur.close()
    return routes


# Mémoire du parcours, par (cible, instance). Un audit ouvre l inventaire PLUSIEURS fois — pan
# accessibilité, pan visuel, dérivation des livrables — et la découverte servie coûte un
# navigateur à chaque appel, là où la lecture d un `routes.jsx` était gratuite. Les routes d une
# instance ne changent pas pendant un run : elles se relèvent une fois. La clé porte la cible ET
# l URL, pour que deux projets audités dans le même processus ne se prêtent jamais leurs routes.
_PARCOURS_MEMOIRE: dict[tuple[str, str], list[str]] = {}


def _routes_servies(cible: Path, base: str, page=None) -> list[str]:  # noqa: ANN001
    """Routes découvertes SUR l instance servie. `page` injectable : la mécanique est testable.

    Avec `page`, rien n est mémorisé : l appelant fournit le banc, il en maîtrise le contenu.
    """
    if page is not None:
        liens = _relever_liens(page, base)
        return [] if liens is None else _routes_depuis_liens(liens, base)
    cle = (str(cible), base)
    if cle not in _PARCOURS_MEMOIRE:
        _PARCOURS_MEMOIRE[cle] = _parcourir_racine(cible, base)
    return list(_PARCOURS_MEMOIRE[cle])


def _routes_du_front(cible: Path) -> list[str]:
    from forge_tests.adaptateurs.front import inventaire

    return [e.id.split(":", 1)[1] for e in inventaire(cible) if e.id.startswith("route:")]


def provenance_des_routes(cible: Path) -> str:
    """QUELLE source fournira les routes de ce projet — sans rien parcourir.

    L ordre des trois sources est écrit ICI et nulle part ailleurs, pour que la liste et son
    étiquette ne puissent pas diverger :

    1. **sources du front** — la table de routage du code (`front.inventaire`). Elle prime :
       c est la déclaration la plus proche du produit, et elle ne coûte rien ;
    2. **déclaration du projet** — `FORGE_TESTS_QUALIF_ROUTES`, quand aucune source front ne
       porte de routes (application rendue côté serveur, gabarits Jinja) ;
    3. **parcours de l instance servie** — les liens de la racine de `FORGE_TESTS_BASE_URL`.
    """
    if _routes_du_front(cible):
        return PROVENANCE_FRONT
    if _routes_declarees(cible):
        return PROVENANCE_DECLAREE
    if _base_servie(cible):
        return PROVENANCE_SERVIE
    return ""


def routes_a_auditer(cible: Path) -> tuple[list[str], str]:
    """(routes à rendre, PROVENANCE de la liste) — la découverte partagée par les deux pans.

    La provenance est rendue avec la liste, et publiée au rapport : « 12 routes » ne veut pas
    dire la même chose selon qu elles sont lues dans le code, déclarées par le projet ou
    relevées sur une instance servie. Un parcours qui ne trouve rien ne rend PAS
    `PROVENANCE_SERVIE` avec une liste vide : sans route, il n y a pas de provenance.
    """
    provenance = provenance_des_routes(cible)
    if provenance == PROVENANCE_FRONT:
        return _routes_du_front(cible), provenance
    if provenance == PROVENANCE_DECLAREE:
        return _routes_declarees(cible), provenance
    if provenance == PROVENANCE_SERVIE:
        servies = _routes_servies(cible, _base_servie(cible))
        return (servies, provenance) if servies else ([], "")
    return [], ""


# Ce qui atteste qu on regarde un PROJET, et non un dossier vide ou une cible mal désignée.
# Volontairement borné à deux niveaux : il ne s agit pas d inventorier, seulement de constater
# qu il y a du code ici.
_MANIFESTES = (
    "pyproject.toml", "setup.py", "requirements.txt", "package.json", "go.mod", "Gemfile",
    "pom.xml", "build.gradle", "Cargo.toml", "composer.json",
)
_SOURCES = ("*.py", "*.js", "*.ts", "*.jsx", "*.tsx", "*.rb", "*.go", "*.php", "*.java")


def _code_visible(cible: Path) -> bool:
    """Le projet montre-t-il du code à cet emplacement ?"""
    if any((cible / manifeste).is_file() for manifeste in _MANIFESTES):
        return True
    return any(
        next(cible.glob(motif), None) is not None
        or next(cible.glob(f"*/{motif}"), None) is not None
        for motif in _SOURCES
    )


def sans_objet(cible: Path) -> str | None:
    """PREUVE POSITIVE qu il n y a AUCUNE page à rendre — pas une supposition (TF-0217).

    Le choix, déclaré : **NA quand rien ne PEUT rendre une page, SKIP quand quelque chose le
    pourrait et que la liste reste vide.** Un lot batch, une bibliothèque, une API sans gabarit
    n ont ni accessibilité ni rendu : ce n est pas un trou de mesure, c est l absence du sujet.
    Mais dès qu une instance est SERVIE (ou qu un `frontend\\` existe), il y a bien quelque chose
    à auditer : n avoir rien su énumérer est alors un NON MESURABLE, qui doit rester un manque
    visible — et se répare en déclarant `FORGE_TESTS_QUALIF_ROUTES`.

    Troisième condition, celle qui empêche NA de devenir un vert de complaisance : le projet doit
    MONTRER du code ici. Un dossier vide — cible mal désignée, sources ailleurs (le cas d une
    racine plate mal ancrée) — ne prouve pas qu il n y a rien à rendre : il prouve qu on n a rien
    regardé. Ce cas reste un SKIP, exactement comme l inventaire vide du noyau.
    """
    if (cible / "frontend").is_dir():
        return None
    if _base_servie(cible):
        return None
    if _routes_declarees(cible):
        return None
    if not _code_visible(cible):
        return None
    return (
        "aucun dossier `frontend\\`, aucune instance servie (FORGE_TESTS_BASE_URL) et aucune "
        "route déclarée (FORGE_TESTS_QUALIF_ROUTES) : ce projet ne rend aucune page"
    )


def _routes(cible: Path) -> list[str]:
    return routes_a_auditer(cible)[0]


_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_VALEUR_EXEMPLE = "1"


def _concretiser(route: str) -> tuple[str | None, str | None]:
    """Rend une route navigable, ou l ecarte AVEC son motif si elle ne peut pas l etre.

    TF-0122 : avant ce correctif, seul `:id` etait substitue (`route.replace(":id", "1")`) —
    un `:slug`, `:demandeId` ou `:userId` navigait vers une URL contenant le deux-points
    LITTERAL, une 404 imputee au produit a tort. Ici, TOUT segment `:nom` est substitue. Le
    joker `*` de react-router (route attrape-tout) n a pas d equivalent navigable : il est
    ECARTE, jamais tente — c est le motif nomme, pas un echec silencieux.
    """
    if "*" in route:
        return None, f"accessibilite : route {route} ecartee — joker `*` non concretisable"
    return _PARAM.sub(_VALEUR_EXEMPLE, route), None


# Caracteres qu un nom de fichier Windows refuse. Le `:` etait le cas constate (une route
# `/login/reset-password/:token/:email` donnait un nom impossible et l OSError emportait
# l AUDIT ENTIER, verdict ERREUR code 2). TF-0122 a supprime cette cause en substituant les
# parametres ; ceci couvre les autres — `?` d une chaine de requete, `*`, `|`, guillemets.
_INTERDITS = str.maketrans({c: "_" for c in ':?*<>|"\\'})


def _nom_fichier(concret: str) -> str:
    """Nom de fichier sur pour une route, quel que soit ce qu elle contient."""
    return concret.strip("/").replace("/", "_").translate(_INTERDITS) or "racine"


def _capturer_une_route(
    page, base: str, route: str, dossier: Path, timeout: int | None = None
) -> tuple[Path | None, str | None]:
    """Concretise puis navigue UNE route ; ne leve JAMAIS. (fichier, None) en succes,
    (None, motif) si ecartee ou injoignable.

    TF-0122 : c est CET isolement qui manquait. Avant, `page.goto` n etait protege par aucun
    garde (contrairement a `_capturer_distant`, qui en avait deja un) : une seule route
    innavigable (le `*` react-router, par ex.) propageait son exception jusqu au noyau et
    faisait tomber l audit ENTIER — exit 2, zero rapport, douze pans perdus pour une route.
    Chaque route est desormais jugee isolement : son echec est un constat NOMME, jamais une
    fin de run.
    """
    concret, motif = _concretiser(route)
    if concret is None:
        return None, motif
    try:
        if timeout is not None:
            page.goto(f"{base}{concret}", wait_until="networkidle", timeout=timeout)
        else:
            page.goto(f"{base}{concret}", wait_until="networkidle")
    except Exception as erreur:  # noqa: BLE001 — route isolee : l echec est un constat
        return None, (
            f"accessibilite : route {route} non capturee — navigation impossible "
            f"({type(erreur).__name__})"
        )
    fichier = (dossier / _nom_fichier(concret)).with_suffix(".html")
    try:
        fichier.write_text(page.content(), encoding="utf-8")
    except OSError as erreur:
        # Un pan ne fait pas tomber l audit. Avant ce garde-fou, une seule route au nom
        # impossible emportait les onze autres pans avec elle (verdict ERREUR, code 2).
        return None, (
            f"accessibilite : route {route} capturee mais non ecrite sur disque "
            f"({type(erreur).__name__}) — page non auditee"
        )
    return fichier, None


def _capturer(cible: Path, routes: list[str], dossier: Path) -> tuple[dict[str, Path], list[str]]:
    """Sert le front, visite chaque route, ecrit le DOM rendu.

    ({}, []) si le rendu est globalement impossible (front non servi). Sinon, un couple
    (captures, motifs) : `motifs` NOMME chaque route ecartee ou injoignable (TF-0122) — une
    route en echec n empeche jamais les autres d etre capturees.

    `FORGE_TESTS_BASE_URL` pointe vers une instance DEJA SERVIE (recette, preproduction). Le
    parcours reste en LECTURE : navigation et capture, aucune ecriture. C est ce qui rend le
    pan front auditable sur un projet qu on ne peut pas construire localement.
    """
    from forge_tests.authentification import charger_env

    charger_env(cible)
    base = os.environ.get("FORGE_TESTS_BASE_URL")
    if base:
        return _capturer_distant(base.rstrip("/"), routes, dossier, cible)
    front = cible / "frontend"
    npx = shutil.which("npx")
    if npx is None or not (front / "dist").is_dir():
        return {}, []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}, []

    port = _port_disponible()
    serveur = subprocess.Popen(
        # `--host 127.0.0.1` : sans lui vite ecoute sur localhost, resolu en IPv6, et la sonde
        # IPv4 conclut a tort que le serveur ne repond pas.
        [npx, "vite", "preview", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=front, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "CI": "1"},
    )
    captures: dict[str, Path] = {}
    motifs: list[str] = []
    try:
        for _ in range(60):
            if _repond(port):
                break
            time.sleep(0.5)
        else:
            return {}, []
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            page = navigateur.new_page()
            base_locale = f"http://127.0.0.1:{port}"
            for route in routes:
                fichier, motif = _capturer_une_route(page, base_locale, route, dossier)
                if fichier is not None:
                    captures[route] = fichier
                else:
                    motifs.append(motif or f"accessibilite : route {route} non capturee")
            navigateur.close()
    finally:
        _tuer_arbre(serveur)
    return captures, motifs


def _capturer_distant(
    base: str, routes: list[str], dossier: Path, cible: Path
) -> tuple[dict[str, Path], list[str]]:
    """Visite une instance servie ailleurs. GET seulement, aucune action mutante.

    Si un compte est configure (.env), le jeton est pose AVANT le premier rendu : sans lui,
    les routes protegees redirigent toutes vers la meme page et l audit ne mesure rien.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}, []
    from forge_tests.authentification import obtenir_jeton, script_injection

    jeton = obtenir_jeton(cible)
    captures: dict[str, Path] = {}
    motifs: list[str] = []
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch()
        contexte = navigateur.new_context()
        if jeton:
            contexte.add_init_script(script_injection(jeton))
        page = contexte.new_page()
        for route in routes:
            fichier, motif = _capturer_une_route(page, base, route, dossier, timeout=45000)
            if fichier is not None:
                captures[route] = fichier
            else:
                motifs.append(motif or f"accessibilite : route {route} non capturee")
        navigateur.close()
    return captures, motifs


def _juger(capture: Path) -> dict | None:
    python = shutil.which("python") or shutil.which("python3")
    if python is None or not _ORACLE.exists():
        return None
    try:
        resultat = subprocess.run(
            [python, str(_ORACLE), str(capture)],
            capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace",
            # Sans cela l oracle plante en ECRIVANT son verdict : console cp1252, JSON accentue.
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        # Delai depasse : le pan se declare non mesure, il n emporte pas l audit entier.
        return None
    sortie = (resultat.stdout or "").strip()
    try:
        return json.loads(sortie) if sortie else None
    except json.JSONDecodeError:
        return None


def source_des_routes(cible: Path, provenance: str) -> str:
    """D OÙ vient la liste, dit dans le vocabulaire du lecteur du rapport (TF-0217).

    Publier `frontend/src/routes.jsx` pour une application à gabarits Jinja désignait un fichier
    qui n existe pas : le constat devenait invérifiable.
    """
    if provenance == PROVENANCE_FRONT:
        return str(cible / "frontend" / "src" / "routes.jsx")
    if provenance == PROVENANCE_DECLAREE:
        return CHAMP_ROUTES
    if provenance == PROVENANCE_SERVIE:
        return _base_servie(cible) or str(cible)
    return str(cible)


def verdict_sans_route(
    nom: str, pan: str, cible: Path, non_juge: list[str]
) -> SortieAdaptateur:
    """Sortie des deux pans quand AUCUNE route n a été découverte — NA ou SKIP, jamais au hasard.

    Le même arbitrage sert `accessibilite` et `visuel` : deux pans qui regardent la même surface
    ne peuvent pas conclure différemment sur son existence.
    """
    motif = sans_objet(cible)
    if motif:
        # Le motif est le DERNIER `non_juge` : c est celui que le rapport publie en
        # `pans_sans_objet` (`noyau.rapport`), comme le fait `evaluer_surface`.
        return SortieAdaptateur(
            nom, pan, str(cible), "NA",
            non_juge=[*non_juge, f"{pan} : SANS OBJET sur ce projet — {motif}"],
        )
    return SortieAdaptateur(
        nom, pan, str(cible), "SKIP",
        non_juge=[
            *non_juge,
            f"{pan} : aucune route découverte — ni table de routage sous `frontend\\src`, ni "
            f"`{CHAMP_ROUTES}`, ni lien relevé sur l instance servie. Une application rendue "
            f"côté serveur déclare ses routes par `{CHAMP_ROUTES}` (le champ du pan qualif), "
            "puis `--reprendre` le rapport",
        ],
    )


def inventaire(cible: Path) -> list[Element]:
    """Une route = un artefact a auditer."""
    routes = _routes(cible)
    source = source_des_routes(cible, provenance_des_routes(cible))
    return [
        Element(f"a11y:{route}", PAN, f"accessibilite de la route {route}", source)
        for route in routes
    ]


def analyser(cible: Path) -> SortieAdaptateur:
    # `_routes` reste le point d entrée (et le point d injection des tests de TF-0122) ; la
    # provenance se relit à côté, sans reparcourir quoi que ce soit.
    routes = _routes(cible)
    if not routes:
        return verdict_sans_route(NOM, PAN, cible, NON_JUGE)
    provenance = provenance_des_routes(cible)
    # La provenance est PUBLIÉE : « 12 routes » ne dit pas la même chose selon qu elles sont
    # lues dans le code, déclarées par le projet, ou relevées sur l instance servie.
    socle = [
        *NON_JUGE,
        f"accessibilite : {len(routes)} route(s) a auditer — provenance : "
        + (provenance or "inventaire fourni a l adaptateur"),
    ]
    with tempfile.TemporaryDirectory() as temporaire:
        captures, motifs_ecartees = _capturer(cible, routes, Path(temporaire))
        # TF-0122 : `motifs_ecartees` NOMME chaque route ecartee (joker non concretisable) ou
        # injoignable (navigation en echec) — l absence de TOUTE capture n est un « front non
        # servi » que si AUCUNE route n a meme ete tentee (aucun motif) ; sinon, le front a bien
        # repondu et c est chaque route qui porte sa propre raison, publiee ci-dessous.
        if not captures and not motifs_ecartees:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[*socle, "front non servi : build absent, npm ou navigateur manquant"],
            )
        findings: list[Finding] = []
        non_juge = [*socle, *motifs_ecartees]
        audites: list[str] = []
        for route, capture in captures.items():
            rapport = _juger(capture)
            if rapport is None:
                non_juge.append(f"accessibilite : route {route} non auditee (oracle injoignable)")
                continue
            audites.append(route)
            non_juge.extend(f"a11y : {ligne}" for ligne in rapport.get("non_juge", []))
            for brut in rapport.get("findings", []):
                if brut.get("sev") == "info":
                    continue
                identifiant = f"a11y:{route}:{brut.get('msg', '')[:40]}"
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.ACCESSIBILITE,
                        localisation=f"{route}",
                        message=f"[{route}] {brut.get('msg', '')}",
                        severite="bloquant" if brut.get("sev") == "bloquant" else "signale",
                        risque=coter(PAN, identifiant, str(cible / "frontend")),
                    )
                )
        # N routes rendant le MEME DOM = une seule page reellement auditee. Sans ce controle,
        # 13 redirections vers /login se lisent « 13 routes conformes » — un vert qui ne mesure
        # rien. Constate sur le premier deploiement reel, faute d authentification.
        empreintes = {
            hashlib.sha256(page.read_bytes()).hexdigest() for page in captures.values()
        }
        if len(captures) > len(empreintes):
            non_juge.append(
                f"accessibilite : {len(captures)} routes visitees mais seulement "
                f"{len(empreintes)} PAGES DISTINCTES rendues — les autres redirigent (sans "
                "authentification, les routes protegees renvoient toutes la meme page). "
                "Le verdict ne porte que sur les pages distinctes"
            )
        if len(captures) > 1 and len(empreintes) == 1:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[
                    *non_juge,
                    f"accessibilite : les {len(captures)} routes rendent un DOM IDENTIQUE — "
                    "aucune route demandee n a reellement ete auditee",
                ],
            )
    if not audites:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=non_juge)
    non_juge.append(f"accessibilite : routes auditees — {', '.join(audites)}")
    bloquants = [f for f in findings if f.severite == "bloquant"]
    return SortieAdaptateur(
        adaptateur=NOM, pan=PAN, cible=str(cible),
        verdict="FAIL" if bloquants else "PASS",
        findings=findings, non_juge=sorted(set(non_juge)),
    )
