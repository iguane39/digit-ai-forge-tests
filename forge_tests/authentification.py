"""Authentification pour l audit d une instance servie — LECTURE SEULE.

Un projet reel protege ses routes. Sans jeton, tout redirige vers la page de login et
l auditeur ne voit qu une page (constate sur le premier deploiement). Ce module obtient un
jeton et l injecte dans le navigateur, ce qui donne acces aux routes protegees SANS jamais
declencher d action mutante : le seul appel emis est l authentification elle-meme, qui ne
modifie aucune donnee metier.

Les identifiants ne vivent JAMAIS dans le code ni dans un commit : ils sont lus dans un `.env`
gitignore que l operateur remplit. Aucune valeur n est journalisee.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

CLE_STOCKAGE = "access_token"  # cle localStorage utilisee par le front (constatee dans useAuth.ts)


def charger_env(depart: Path) -> None:
    """Charge un `.env` proche (projet analyse, puis dossier de Forge Tests). Ne surcharge pas."""
    candidats = [
        depart / ".env.forge-tests",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for chemin in candidats:
        if not chemin.exists():
            continue
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            cle, valeur = cle.strip(), valeur.strip().strip('"').strip("'")
            if cle and cle not in os.environ:
                os.environ[cle] = valeur


def obtenir_jeton(cible: Path) -> str | None:
    """Jeton JWT obtenu par la mire de login, ou None si non configure / echec.

    Aucun secret n est renvoye dans les logs : en cas d echec on rend None, l appelant le
    DECLARE (SKIP) plutot que de supposer.
    """
    charger_env(cible)
    api = os.environ.get("FORGE_TESTS_API_URL")
    login = os.environ.get("FORGE_TESTS_LOGIN")
    mdp = os.environ.get("FORGE_TESTS_PASSWORD")
    if not (api and login and mdp):
        return None

    chemin = os.environ.get("FORGE_TESTS_LOGIN_PATH", "/api/v1/login/access-token")
    corps = urllib.parse.urlencode({"username": login, "password": mdp}).encode()
    requete = urllib.request.Request(
        api.rstrip("/") + chemin,
        data=corps,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:  # noqa: S310 — URL de l operateur
            donnees = json.loads(reponse.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — echec d auth : declare par l appelant, jamais suppose
        return None
    return donnees.get("access_token")


def script_injection(jeton: str) -> str:
    """JS a jouer AVANT le premier rendu : pose le jeton la ou le front l attend."""
    valeur = json.dumps(jeton)
    return f'try {{ localStorage.setItem({json.dumps(CLE_STOCKAGE)}, {valeur}); }} catch (e) {{}}'
