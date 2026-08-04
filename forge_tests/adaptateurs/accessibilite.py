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
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "accessibilite-a11y", "accessibilite"
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


def _capturer(cible: Path, routes: list[str], dossier: Path) -> dict[str, Path]:
    """Sert le front, visite chaque route, ecrit le DOM rendu. {} si le rendu est impossible.

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
        return {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}

    port = _port_disponible()
    serveur = subprocess.Popen(
        # `--host 127.0.0.1` : sans lui vite ecoute sur localhost, resolu en IPv6, et la sonde
        # IPv4 conclut a tort que le serveur ne repond pas.
        [npx, "vite", "preview", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=front, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "CI": "1"},
    )
    captures: dict[str, Path] = {}
    try:
        for _ in range(60):
            if _repond(port):
                break
            time.sleep(0.5)
        else:
            return {}
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            page = navigateur.new_page()
            for route in routes:
                concret = route.replace(":id", "1")
                page.goto(f"http://127.0.0.1:{port}{concret}", wait_until="networkidle")
                fichier = dossier / (concret.strip("/").replace("/", "_") or "racine")
                fichier = fichier.with_suffix(".html")
                fichier.write_text(page.content(), encoding="utf-8")
                captures[route] = fichier
            navigateur.close()
    finally:
        _tuer_arbre(serveur)
    return captures


def _capturer_distant(
    base: str, routes: list[str], dossier: Path, cible: Path
) -> dict[str, Path]:
    """Visite une instance servie ailleurs. GET seulement, aucune action mutante.

    Si un compte est configure (.env), le jeton est pose AVANT le premier rendu : sans lui,
    les routes protegees redirigent toutes vers la meme page et l audit ne mesure rien.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}
    from forge_tests.authentification import obtenir_jeton, script_injection

    jeton = obtenir_jeton(cible)
    captures: dict[str, Path] = {}
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch()
        contexte = navigateur.new_context()
        if jeton:
            contexte.add_init_script(script_injection(jeton))
        page = contexte.new_page()
        for route in routes:
            concret = route.replace(":id", "1")
            try:
                page.goto(f"{base}{concret}", wait_until="networkidle", timeout=45000)
            except Exception:  # noqa: BLE001 — route injoignable : declaree, pas supposee
                continue
            fichier = dossier / (concret.strip("/").replace("/", "_") or "racine")
            fichier = fichier.with_suffix(".html")
            fichier.write_text(page.content(), encoding="utf-8")
            captures[route] = fichier
        navigateur.close()
    return captures


def _juger(capture: Path) -> dict | None:
    python = shutil.which("python") or shutil.which("python3")
    if python is None or not _ORACLE.exists():
        return None
    resultat = subprocess.run(
        [python, str(_ORACLE), str(capture)],
        capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace",
        # Sans cela l oracle plante en ECRIVANT son verdict : console cp1252, JSON accentue.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
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
        captures = _capturer(cible, routes, Path(temporaire))
        if not captures:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[*NON_JUGE, "front non servi : build absent, npm ou navigateur manquant"],
            )
        findings: list[Finding] = []
        non_juge = list(NON_JUGE)
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
