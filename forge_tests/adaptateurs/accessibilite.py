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

from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "accessibilite-a11y", "accessibilite"

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "servir le front (build présent et `npm`/navigateur disponibles) ou déclarer l'instance "
    "SERVIE dans FORGE_TESTS_BASE_URL : le pan juge le DOM RENDU de chaque route, il n'a rien "
    "à lire tant qu'aucune page n'est rendue"
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
    "accessibilite : perimetre du seul oracle structurel — ni audit axe-core complet, ni "
    "contraste, ni navigation clavier (limites propres de l oracle, reprises telles quelles)",
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


def _routes(cible: Path) -> list[str]:
    from forge_tests.adaptateurs.front import inventaire

    return [e.id.split(":", 1)[1] for e in inventaire(cible) if e.id.startswith("route:")]


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


def inventaire(cible: Path) -> list[Element]:
    """Une route = un artefact a auditer."""
    source = str(cible / "frontend" / "src" / "routes.jsx")
    return [
        Element(f"a11y:{route}", PAN, f"accessibilite de la route {route}", source)
        for route in _routes(cible)
    ]


def analyser(cible: Path) -> SortieAdaptateur:
    routes = _routes(cible)
    if not routes:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=[*NON_JUGE, "aucune route"])
    with tempfile.TemporaryDirectory() as temporaire:
        captures, motifs_ecartees = _capturer(cible, routes, Path(temporaire))
        # TF-0122 : `motifs_ecartees` NOMME chaque route ecartee (joker non concretisable) ou
        # injoignable (navigation en echec) — l absence de TOUTE capture n est un « front non
        # servi » que si AUCUNE route n a meme ete tentee (aucun motif) ; sinon, le front a bien
        # repondu et c est chaque route qui porte sa propre raison, publiee ci-dessous.
        if not captures and not motifs_ecartees:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[*NON_JUGE, "front non servi : build absent, npm ou navigateur manquant"],
            )
        findings: list[Finding] = []
        non_juge = [*NON_JUGE, *motifs_ecartees]
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
                        classe="accessibilite",
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
