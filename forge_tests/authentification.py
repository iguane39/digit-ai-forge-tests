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

# Nom du fichier de configuration PORTE PAR LE PROJET audite : la seule source legitime des
# cles qui designent une instance.
ENV_PROJET = ".env.forge-tests"

# `.env` du DEPOT forge-tests — configuration de l OPERATEUR (compte de lecture), commune a
# tous les audits joues depuis ce poste.
ENV_DEPOT = Path(__file__).resolve().parent.parent / ".env"

# TF-0243 — cles qui DESIGNENT l instance auditee. Elles ne peuvent venir que du projet ou de
# l environnement pose explicitement par l operateur pour CE run ; jamais du `.env` du depot.
#
# Fait mesure le 15/08/2026 (lot 20260815a, ledger seq 15) : un produit neuf, sans
# `.env.forge-tests`, a herite du `FORGE_TESTS_BASE_URL` laisse dans le `.env` du depot par un
# audit precedent. Le pan `qualif` est alle parcourir l instance Railway d un AUTRE produit et
# en a rapporte 9 constats `qualif:effet` plus 2 constats d accessibilite sur `/login`,
# `/recover-password` et `/admin/*` — des routes qui n existent pas chez l audite — avec un
# seuil de 67 % calcule sur cette surface etrangere. Un cycle entier de boucle de fermeture a
# ete consomme a instruire des constats qui ne portaient sur rien.
#
# La regle est donc absolue et sans repli : SANS designation d instance par le projet, la forge
# REFUSE d auditer une instance servie (NA ou SKIP motive, selon qu il y ait ou non un sujet)
# plutot que d en auditer une au hasard. Un refus explicite coute une ligne de configuration ;
# un audit du mauvais site coute la confiance dans toute la mesure.
#
# Les trois cles sont retenues pour la meme raison — chacune pointe une instance DEPLOYEE :
# `BASE_URL` ce que le navigateur parcourt, `QUALIF_URL` ce que le pan qualif parcourt, et
# `API_URL` le point d authentification, auquel un `.env` egare ferait POSTER les identifiants
# de l operateur sur le service d un tiers.
CLES_INSTANCE = (
    "FORGE_TESTS_BASE_URL",
    "FORGE_TESTS_QUALIF_URL",
    "FORGE_TESTS_API_URL",
)


def _valeurs(chemin: Path) -> dict[str, str]:
    """Paires `CLE=valeur` d un fichier d environnement, dans l ordre du fichier.

    Fonction PURE : elle n ecrit pas dans `os.environ`, ce qui rend le filtrage de
    `charger_env` verifiable sans manipuler l environnement du processus de test.
    """
    valeurs: dict[str, str] = {}
    if not chemin.exists():
        return valeurs
    for brut in chemin.read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        cle, valeur = cle.strip(), valeur.strip().strip('"').strip("'")
        if cle:
            valeurs[cle] = valeur
    return valeurs


def cles_instance_ignorees(depart: Path) -> list[str]:
    """Cles d instance presentes dans le `.env` du DEPOT et volontairement ecartees (TF-0243).

    Rendue publique pour que l ecart soit DECLARABLE : un operateur qui a rempli le mauvais
    fichier doit apprendre pourquoi son URL n est pas prise, au lieu de constater un pan sans
    objet qu il ne s explique pas. La liste est vide des que le projet porte sa propre
    configuration — les cles du projet, elles, sont toujours honorees.
    """
    du_projet = _valeurs(Path(depart) / ENV_PROJET)
    return [
        cle
        for cle in CLES_INSTANCE
        if cle in _valeurs(ENV_DEPOT) and cle not in du_projet and cle not in os.environ
    ]


def charger_env(depart: Path) -> None:
    """Charge la configuration d audit. Ne surcharge jamais une variable deja posee.

    Deux sources, et elles n ont pas le meme statut (TF-0243) :

      1. `<projet>/.env.forge-tests` — la configuration DU PROJET audite. Tout y est admis :
         c est le projet qui declare l instance sur laquelle il veut etre mesure ;
      2. `<depot forge-tests>/.env` — la configuration de l OPERATEUR, commune a tous ses
         audits. Les cles de `CLES_INSTANCE` y sont IGNOREES : elles designeraient une instance
         que le projet courant n a jamais revendiquee.
    """
    for chemin, depot_forge in ((Path(depart) / ENV_PROJET, False), (ENV_DEPOT, True)):
        for cle, valeur in _valeurs(chemin).items():
            if depot_forge and cle in CLES_INSTANCE:
                continue
            if cle not in os.environ:
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
        # RT-6a — l absence de compte n est plus un `None` muet : les champs a fournir sont
        # DECLARES, et les pans qui en dependent les publient en `non_testables`.
        from forge_tests.qualification import declarer

        declarer(
            cible,
            "acces",
            ("FORGE_TESTS_API_URL", "FORGE_TESTS_LOGIN", "FORGE_TESTS_PASSWORD"),
        )
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
