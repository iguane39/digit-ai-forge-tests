"""Jeux de données des cahiers — SYNTHÉTIQUES, et prouvés tels avant écriture.

Un cahier de tests sans jeu de données n est pas exécutable : « créer une commande » ne dit
pas laquelle. Mais un jeu de données déposé à côté d un cahier est un fichier qui circule —
par courriel, dans un ticket, dans un dépôt. La tentation de le remplir avec un extrait de
production est constante, et c est la fuite de données la plus banale d un projet.

D où la règle : **rien de ce qui sort d ici ne vient du produit audité.** Les valeurs sont
fabriquées à partir de listes fermées écrites ici, les courriels vivent sous `.test` (TLD
réservé par la RFC 6761, il ne peut désigner personne), et un garde-fou CODÉ relit la
production avant de l écrire :

  - un courriel dont le domaine n est pas réservé → refus ;
  - une valeur qui ressemble à un secret (clé, jeton, empreinte, bloc PEM) → refus ;
  - une valeur qui figure dans la configuration du projet audité ou dans une variable
    d environnement sensible → refus, c est une fuite en train de se produire.

Le refus est une EXCEPTION, pas un avertissement : un jeu de données douteux ne s écrit pas
« en signalant ». Une fois le fichier posé, il est trop tard.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

NON_JUGE = [
    "jeux de donnees : le garde-fou compare aux valeurs de configuration LISIBLES (env "
    "sensibles, `.env*` du projet) — une donnee reelle recopiee a la main qui ne figure dans "
    "aucune de ces sources ne serait pas reconnue ; la synthese, elle, est integrale",
    "jeux de donnees : les valeurs sont derivees de l IDENTIFIANT de l element, pas de son "
    "type metier — un jeu couvre la FORME du cas (nominal, vide, erreur), pas la semantique "
    "d un domaine que le rapport ne connait pas",
]


class DonneeNonSynthetique(RuntimeError):
    """Une valeur du jeu de données ne peut pas être prouvée synthétique. Rien n est écrit."""


# TLD réservés : aucun ne peut être enregistré, donc aucun ne peut désigner une personne réelle.
DOMAINES_RESERVES = ("exemple.test", "example.test", "exemple.invalid", "example.invalid")
DOMAINE = DOMAINES_RESERVES[0]

_COURRIEL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_SECRETS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "bloc de clé privée PEM"),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "clé d API au format `sk-…`"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "jeton GitHub"),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}"), "identifiant de clé AWS"),
    (re.compile(r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "jeton JWT"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "empreinte ou clé hexadécimale de 32 caractères ou plus"),
    (re.compile(r"://[^/\s:]+:[^/\s@]+@"), "identifiants dans une URL de connexion"),
)

# Deux cercles, et la distinction porte une décision — elle n est pas cosmétique :
#
#   - `_NOM_SECRET` : ce qui ne doit JAMAIS sortir, nulle part. Un jeton, une clé, un mot de
#     passe n a aucune raison légitime de figurer dans un livrable d audit ;
#   - `_NOM_CONFIG` : le cercle plus large, qui ajoute ce qui identifie l exploitation (URL,
#     compte, adresse). Interdit dans un JEU DE DONNÉES — qui doit être intégralement
#     fabriqué — mais admis dans un rapport et donc dans le dashboard : l URL de l instance
#     auditée est le SUJET de l audit, la masquer rendrait le constat inintelligible.
#
# Confondre les deux menait à l impasse : soit on laissait fuir des jetons, soit on refusait de
# publier un audit d instance servie.
_NOM_SECRET = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|MDP|CRED|AUTH|JETON|CLE)", re.IGNORECASE
)
_NOM_CONFIG = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|MDP|CRED|AUTH|JETON|CLE|API|DSN|URL|LOGIN|MAIL|USER)",
    re.IGNORECASE,
)
_LONGUEUR_COMPARABLE = 8

# Vocabulaire fermé — écrit ici, donc opposable, donc jamais issu d un produit.
_PRENOMS = ("Alix", "Camille", "Dominique", "Élie", "Fabien", "Gaëlle", "Hakim", "Inès")
_NOMS = ("Dupont", "Martel", "Nguyen", "Ostrowski", "Perrin", "Quintard", "Rossi", "Sanchez")
_LIBELLES = ("Alpha", "Bravo", "Charlie", "Delta", "Écho", "Foxtrot", "Golf", "Hôtel")
JOUR_PIVOT = "2026-01-15"


def _valeurs_de_configuration(cible: Path | None, secrets_seulement: bool = False) -> set[str]:
    """Valeurs qu il serait grave de recopier : env sensibles et `.env*` du projet audité.

    `secrets_seulement` restreint au premier cercle — c est le réglage du dashboard, qui rend
    un rapport et doit pouvoir nommer l instance auditée.
    """
    motif = _NOM_SECRET if secrets_seulement else _NOM_CONFIG
    valeurs: set[str] = set()
    for nom, valeur in os.environ.items():
        valeur = (valeur or "").strip()
        if len(valeur) >= _LONGUEUR_COMPARABLE and motif.search(nom):
            valeurs.add(valeur)
    if cible is not None:
        for fichier in sorted(Path(cible).glob(".env*")) + sorted(
            Path(cible).glob("*/.env*")
        ):
            if not fichier.is_file():
                continue
            for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#") or "=" not in ligne:
                    continue
                nom, _, valeur = ligne.partition("=")
                valeur = valeur.strip().strip('"').strip("'")
                if secrets_seulement and not _NOM_SECRET.search(nom):
                    continue
                if len(valeur) >= _LONGUEUR_COMPARABLE:
                    valeurs.add(valeur)
    return valeurs


def _textes(valeur: object, chemin: str = "") -> list[tuple[str, str]]:
    if isinstance(valeur, dict):
        return [t for cle, sous in valeur.items() for t in _textes(sous, f"{chemin}.{cle}")]
    if isinstance(valeur, (list, tuple)):
        return [t for i, sous in enumerate(valeur) for t in _textes(sous, f"{chemin}[{i}]")]
    if isinstance(valeur, str):
        return [(chemin or ".", valeur)]
    return []


def verifier(donnees: object, cible: Path | None = None) -> None:
    """Lève `DonneeNonSynthetique` au PREMIER doute. Ne renvoie rien : le silence vaut preuve."""
    interdites = _valeurs_de_configuration(cible)
    for chemin, texte in _textes(donnees):
        for domaine in _COURRIEL.findall(texte):
            if domaine.lower() not in DOMAINES_RESERVES:
                raise DonneeNonSynthetique(
                    f"{chemin} : courriel du domaine « {domaine} », qui n est pas un domaine "
                    f"réservé ({', '.join(DOMAINES_RESERVES)}) — un jeu de données de cahier ne "
                    "porte jamais d adresse joignable"
                )
        for motif, quoi in _SECRETS:
            if motif.search(texte):
                raise DonneeNonSynthetique(
                    f"{chemin} : la valeur ressemble à un secret ({quoi}) — refus d écrire un "
                    "jeu de données qui ferait circuler une clé"
                )
        for valeur in interdites:
            if valeur and valeur in texte:
                raise DonneeNonSynthetique(
                    f"{chemin} : la valeur reprend une donnée de configuration du projet audité "
                    "(variable sensible ou `.env`) — c est une fuite, pas un jeu de test"
                )


def _rang(identifiant: str) -> int:
    """Rang stable dérivé de l identifiant — deux runs sur le même rapport donnent le même jeu."""
    return sum(ord(c) for c in identifiant)


def _acteur(identifiant: str) -> dict[str, str]:
    rang = _rang(identifiant)
    prenom, nom = _PRENOMS[rang % len(_PRENOMS)], _NOMS[(rang // 7) % len(_NOMS)]
    return {
        "identifiant": f"u{1000 + rang % 9000}",
        "nom_affiche": f"{prenom} {nom}",
        "courriel": f"{prenom.lower()}.{nom.lower()}@{DOMAINE}".replace("é", "e").replace("è", "e"),
        "role": "administrateur" if rang % 2 else "collaborateur",
    }


ETATS_FONCTIONNELS = ("nominal", "vide", "erreur", "chargement")

_PRECONDITIONS = {
    "nominal": "le jeu nominal est chargé ; l acteur est authentifié et autorisé",
    "vide": "aucune donnée n est chargée pour cet écran (collection vide, filtres neutres)",
    "erreur": "la dépendance sollicitée par l écran répond en erreur (5xx) ou expire",
    "chargement": "la réponse de la dépendance est différée (latence injectée) et l écran est "
    "observé AVANT résolution",
}


def jeu_fonctionnel(identifiant: str) -> dict:
    """Bloc de données d un écran : un acteur, un ensemble peuplé, et ses trois dégradations."""
    acteur = _acteur(identifiant)
    rang = _rang(identifiant)
    lignes = [
        {
            "id": 100 + rang % 800 + i,
            "libelle": _LIBELLES[(rang + i) % len(_LIBELLES)],
            "cree_le": JOUR_PIVOT,
            "montant": round(10.0 + ((rang + i * 13) % 990), 2),
        }
        for i in range(3)
    ]
    return {
        "acteur": acteur,
        "nominal": {"lignes": lignes},
        "vide": {"lignes": []},
        "erreur": {"dependance": "en erreur", "code_simule": 503},
        "chargement": {"dependance": "différée", "latence_ms": 3000},
    }


def jeu_technique(identifiant: str) -> dict:
    """Bloc de données d un élément technique : une valeur conforme et une valeur violante."""
    rang = _rang(identifiant)
    return {
        "conforme": {
            "cle": f"k{rang % 10000}",
            "libelle": _LIBELLES[rang % len(_LIBELLES)],
            "valeur_numerique": 1 + rang % 100,
            "date": JOUR_PIVOT,
        },
        "violant": {
            "cle": f"k{rang % 10000}",  # doublon volontaire : viole une unicité
            "libelle": "",  # vide : viole une non-nullité applicative
            "valeur_numerique": -1,  # négatif : viole une vérification usuelle
            "date": "31/02/2026",  # date impossible : viole un format
        },
    }


def construire(chapitres: list[dict], produit: str) -> dict:
    """Jeu de données complet, dérivé des chapitres — une entrée par sous-chapitre garni."""
    blocs = []
    for chapitre in chapitres:
        for sous in chapitre["sous_chapitres"]:
            if not sous["elements"]:
                continue
            cle = f"JD-{chapitre['code']}-{sous['libelle']}"
            fonctionnel = chapitre["famille"] == "fonctionnel"
            blocs.append(
                {
                    "cle": cle,
                    "chapitre": chapitre["code"],
                    "sous_chapitre": sous["libelle"],
                    "porte_sur": [e["id"] for e in sous["elements"]],
                    "donnees": jeu_fonctionnel(cle) if fonctionnel else jeu_technique(cle),
                }
            )
    return {
        "produit": produit,
        "nature": "jeu de données SYNTHÉTIQUE — aucune donnée réelle, aucune PII",
        "domaine_courriel": DOMAINE,
        "avertissement": (
            "Valeurs fabriquées par Forge Tests à partir d un vocabulaire fermé. Le domaine de "
            "courriel est réservé (RFC 6761) : aucune adresse n est joignable. Ne jamais "
            "remplacer une valeur par un extrait de production — le cahier circule."
        ),
        "etats_fonctionnels": list(ETATS_FONCTIONNELS),
        "preconditions_par_etat": dict(_PRECONDITIONS),
        "jeux": blocs,
    }
