"""Authentification pour l audit d une instance servie — LECTURE SEULE.

Un projet reel protege ses routes. Sans jeton, tout redirige vers la page de login et
l auditeur ne voit qu une page (constate sur le premier deploiement). Ce module obtient un
jeton et l injecte dans le navigateur, ce qui donne acces aux routes protegees SANS jamais
declencher d action mutante : le seul appel emis est l authentification elle-meme, qui ne
modifie aucune donnee metier.

Les identifiants ne vivent JAMAIS dans le code ni dans un commit : ils sont lus dans un `.env`
gitignore. Aucune valeur n est journalisee.

Et depuis TF-0620 (mesure du pilot du 25/08/2026), la ligne qui l ignore est LIVREE par la forge
et non supposee remplie par l operateur : `gabarit_env.proteger()` l ajoute au `.gitignore` du
projet audite, denonce une negation `!.env.forge-tests` sans jamais la retirer, et le flux
d audit l appelle a chaque passage. La phrase precedente disait « gitignore que l operateur
remplit » : c etait une protection SUPPOSEE, et le tirage a rendu 1 projet conforme sur 3 —
les deux autres versionnes, l un publie sur origin/main. Une affordance est cablee ou elle
n existe pas.
"""

from __future__ import annotations

import json
import os
import re
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

# TF-2161 (Produit-86, RT-12, 04/11/2026) — la configuration d'audit d'un produit ne vivait que
# dans la transcription de la session qui l'avait posée : l'audit suivant, sans `FORGE_TESTS_APP`
# ni `FORGE_TESTS_MUTATION` ni `FORGE_TESTS_QUALIF_URL`, a rendu api 0/150 et deux pans en SKIP
# contre 144/144 la veille. `.env.forge-tests` n'y suffisait pas : il porte des identifiants, donc
# il n'est PAS versionné (TF-0620), donc il ne voyage pas avec le produit.
#
# Ce fichier-ci est VERSIONNÉ, chez le produit, au chemin que le retour proposait. Il porte le
# réglage de l'audit (application désignée, campagne de mutation demandée, instance de qualif),
# jamais un secret : une clé de secret y est écartée et le rapport le dit. Cascade, du plus fort
# au plus faible : environnement de l'opérateur, `.env.forge-tests` (privé), ce fichier, puis le
# `.env` du dépôt forge-tests (hors clés d'instance).
ENV_AUDIT = "forge/etapes/tests/audit.env"

# Une clé qui porte une identité ou un secret n'a pas sa place dans un fichier versionné. Le motif
# vise le NOM de la clé (la valeur ne se lit jamais) ; `FORGE_TESTS_LOGIN` n'en fait pas partie,
# c'est un identifiant de démonstration.
_CLE_DE_SECRET = re.compile(
    r"PASSWORD|MDP|SECRET|TOKEN|BEARER|COOKIE|PRIVATE|(?:^|_)KEY(?:_|$)", re.IGNORECASE
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


def est_cle_de_secret(cle: str) -> bool:
    """Le nom de cette cle designe-t-il un secret ou une identite ? (TF-2161)"""
    return bool(_CLE_DE_SECRET.search(cle))


def cles_secretes_ignorees(depart: Path) -> list[str]:
    """Cles de secret portees par le fichier d audit VERSIONNE, et donc ecartees (TF-2161).

    Rendue publique pour que l ecart soit DECLARABLE : un operateur qui a range un mot de passe
    dans un fichier versionne doit apprendre qu il n est pas lu, et pourquoi, au lieu de voir un
    compte qui ne se connecte pas. Les noms seulement : une valeur ne voyage jamais.
    """
    return [
        cle for cle in _valeurs(Path(depart) / ENV_AUDIT) if est_cle_de_secret(cle)
    ]


def configuration_lue(depart: Path) -> dict:
    """Ce que le chargement a lu chez le projet, pour le rapport (TF-2161) — noms, jamais valeurs.

    Un rapport qui ne dit pas d ou vient sa configuration laisse le lecteur refaire le chemin qui
    a coute 48 minutes : retrouver, dans une transcription, les variables du run precedent.
    """
    racine = Path(depart)
    return {
        "fichier_attendu": ENV_AUDIT,
        "fichiers_lus": [nom for nom in (ENV_PROJET, ENV_AUDIT) if (racine / nom).is_file()],
        "cles_du_fichier": [
            cle for cle in _valeurs(racine / ENV_AUDIT) if not est_cle_de_secret(cle)
        ],
        "cles_secretes_ecartees": cles_secretes_ignorees(racine),
    }


def charger_env(depart: Path) -> None:
    """Charge la configuration d audit. Ne surcharge jamais une variable deja posee.

    Trois sources, et elles n ont pas le meme statut (TF-0243, TF-2161). L ordre de lecture EST la
    priorite, puisqu une variable posee n est jamais ecrasee :

      1. `<projet>/.env.forge-tests` — la configuration PRIVEE du projet audite (identifiants de
         demonstration), non versionnee. Tout y est admis : c est le projet qui declare
         l instance sur laquelle il veut etre mesure ;
      2. `<projet>/forge/etapes/tests/audit.env` — le reglage d audit VERSIONNE avec le produit
         (application designee, mutation demandee, instance de qualif). Tout y est admis SAUF les
         cles de secret, ecartees (`cles_secretes_ignorees`) : le fichier est publie avec le depot ;
      3. `<depot forge-tests>/.env` — la configuration de l OPERATEUR, commune a tous ses
         audits. Les cles de `CLES_INSTANCE` y sont IGNOREES : elles designeraient une instance
         que le projet courant n a jamais revendiquee.
    """
    sources = (
        (Path(depart) / ENV_PROJET, False, False),
        (Path(depart) / ENV_AUDIT, False, True),
        (ENV_DEPOT, True, False),
    )
    for chemin, depot_forge, versionne in sources:
        for cle, valeur in _valeurs(chemin).items():
            if depot_forge and cle in CLES_INSTANCE:
                continue
            if versionne and est_cle_de_secret(cle):
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
