"""Parcours d une instance SERVIE, mutualise entre les pans qui jugent le rendu reel.

Pourquoi ce module existe (TF-0409, option O3). Le pan accessibilite avait resolu le vrai
verrou : servir le front, visiter chaque route, et donner la page RENDUE a un oracle. Ce
verrou vaut pour toute famille qui se mesure sur le rendu — contraste, navigation clavier,
demain autre chose — et le mecanisme etait enferme dans un seul adaptateur. Deux pans de plus
auraient signifie deux copies de la meme sequence : serveur vite, sonde de port, jeton
d authentification, garde par route, arret d arbre de processus. Une copie, c est une
divergence a terme.

Ici : la sequence est ecrite UNE fois et prend une ACTION. Chaque pan fournit ce qu il fait
d une page vivante — ecrire son DOM, evaluer une mesure, piloter le clavier — et herite du
reste. Les gardes de TF-0122 sont conserves tels quels : une route innavigable est un constat
NOMME, jamais une fin de run.

Ce que le module NE fait pas : choisir les routes (c est `accessibilite.routes_a_auditer`,
source unique), ni juger. Il ouvre une page et la donne.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from forge_tests.adaptateurs.accessibilite import (
    _concretiser,
    _port_disponible,
    _repond,
    _tuer_arbre,
)

#: Une action recoit la page vivante et le nom de la route ; elle rend (valeur, motif). Elle ne
#: leve JAMAIS — le parcours la protege, mais un pan qui compte sur cette protection pour
#: ignorer ses propres erreurs se prive du constat.
Action = Callable[[Any, str], "tuple[Any, str | None]"]


def _visiter(
    page: Any, base: str, route: str, action: Action, prefixe: str, timeout: int | None
) -> tuple[Any, str | None]:
    """Concretise, navigue, execute l action. Ne leve jamais (garde TF-0122)."""
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
            f"{prefixe} : route {route} non visitee — navigation impossible "
            f"({type(erreur).__name__})"
        )
    try:
        return action(page, route)
    except Exception as erreur:  # noqa: BLE001 — idem : une mesure ratee nomme sa route
        return None, (
            f"{prefixe} : route {route} visitee mais non mesuree "
            f"({type(erreur).__name__}) — page non jugee"
        )


def parcourir(
    cible: Path, routes: list[str], action: Action, *, prefixe: str
) -> tuple[dict[str, Any], list[str]]:
    """Sert l instance (ou rejoint celle qui est declaree) et applique `action` a chaque route.

    ({}, []) si le rendu est globalement impossible — front non servi, navigateur absent :
    c est un SKIP pour le pan appelant, jamais un echec. Sinon (resultats, motifs), ou `motifs`
    NOMME chaque route ecartee, injoignable ou non mesurable.
    """
    from forge_tests.authentification import charger_env

    charger_env(cible)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}, []

    base_declaree = os.environ.get("FORGE_TESTS_BASE_URL")
    if base_declaree:
        return _parcourir_distant(base_declaree.rstrip("/"), routes, action, cible, prefixe)

    front = cible / "frontend"
    npx = shutil.which("npx")
    if npx is None or not (front / "dist").is_dir():
        return {}, []

    port = _port_disponible()
    serveur = subprocess.Popen(
        # `--host 127.0.0.1` : sans lui vite ecoute sur localhost, resolu en IPv6, et la sonde
        # IPv4 conclut a tort que le serveur ne repond pas.
        [npx, "vite", "preview", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=front, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "CI": "1"},
    )
    resultats: dict[str, Any] = {}
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
            base = f"http://127.0.0.1:{port}"
            for route in routes:
                valeur, motif = _visiter(page, base, route, action, prefixe, None)
                if valeur is not None:
                    resultats[route] = valeur
                else:
                    motifs.append(motif or f"{prefixe} : route {route} non mesuree")
            navigateur.close()
    finally:
        _tuer_arbre(serveur)
    return resultats, motifs


def _motif_instance_injoignable(base: str, prefixe: str) -> str:
    """TF-1210 : la forge ne monte pas l instance declaree a distance — si elle ne repond pas,
    le motif cite la commande de demarrage declaree par le projet plutot que de laisser chaque
    route echouer avec un « navigation impossible » generique qui ne dit ni l un ni l autre."""
    from forge_tests.instance import CHAMP_MONTER, contrat

    monter = contrat()["monter"]
    consigne = (
        f"demarrer l instance avec la commande declaree dans {CHAMP_MONTER} : `{monter}`"
        if monter
        else f"aucune commande de demarrage declaree — la fournir dans {CHAMP_MONTER}"
    )
    return (
        f"{prefixe} : instance non joignable sur {base} — {consigne}, puis rejouer"
    )


def _parcourir_distant(
    base: str, routes: list[str], action: Action, cible: Path, prefixe: str
) -> tuple[dict[str, Any], list[str]]:
    """Instance servie ailleurs (recette, preproduction). GET seulement, aucune action mutante.

    TF-1210 : l adresse de base est SONDEE avant le premier rendu. Sans cette garde, une
    instance non demarree faisait echouer CHAQUE route avec le meme motif generique
    (« navigation impossible : Error »), qui ne disait ni qu il fallait demarrer l instance ni
    quelle commande jouer — un audit complet perdu pour un motif illisible.

    Le jeton est pose AVANT le premier rendu : sans lui, les routes protegees redirigent toutes
    vers la meme page et la mesure ne porte sur rien.
    """
    from playwright.sync_api import sync_playwright

    from forge_tests.authentification import obtenir_jeton, script_injection
    from forge_tests.instance import PORT_LIBRE, sonder_port

    # TF-1210 : seul le constat SUR (port confirme LIBRE) refuse tot. Un port INDETERMINABLE
    # (DNS resolu, mais sonde impossible pour une autre raison) ne bloque pas — la garde ne se
    # deduit jamais d une ignorance, meme doctrine que `precondition_absente` du pan qualif.
    if sonder_port(base)["etat"] == PORT_LIBRE:
        return {}, [_motif_instance_injoignable(base, prefixe)]

    jeton = obtenir_jeton(cible)
    resultats: dict[str, Any] = {}
    motifs: list[str] = []
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch()
        contexte = navigateur.new_context()
        if jeton:
            contexte.add_init_script(script_injection(jeton))
        page = contexte.new_page()
        for route in routes:
            valeur, motif = _visiter(page, base, route, action, prefixe, 45000)
            if valeur is not None:
                resultats[route] = valeur
            else:
                motifs.append(motif or f"{prefixe} : route {route} non mesuree")
        navigateur.close()
    return resultats, motifs
