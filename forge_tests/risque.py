"""Cotation du risque — criticité métier x probabilité de défaillance x coût de détection tardive.

P1 : le modèle existait au noyau mais n était appelé nulle part. Sans lui, tous les findings
se valent et la liste devient illisible dès la première centaine. Le tri par risque est ce qui
transforme un inventaire en priorisation.

Ce qui est DÉCLARÉ (criticité, coût) est un choix de conception, assumé et versionné ici.
Ce qui est MESURÉ (probabilité) vient du dépôt : nombre de commits touchant le fichier source.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

# Criticité métier et coût de détection tardive, par pan. Notés de 1 à 5, déclarés.
# Data et migrations en tête : une contrainte absente corrompt durablement, et se découvre tard.
COTATION_PAN: dict[str, tuple[int, int]] = {
    "data": (5, 5),
    "migrations": (4, 5),
    "api": (5, 4),
    "batch": (4, 4),
    "back": (4, 3),
    "fichiers": (3, 4),
    "front": (3, 3),
}
_DEFAUT_PAN = (3, 3)

# Majoration par classe d élément : un chemin d erreur casse plus souvent qu un chemin passant.
MAJORATION_CLASSE: dict[str, int] = {
    "code": 1,
    "contrainte": 1,
    "rejet": 1,
    "mutant": 1,
}

PROBABILITE_DEFAUT = 3
NON_JUGE = [
    "risque : la criticité et le coût de détection tardive sont DÉCLARÉS par pan, pas mesurés — "
    "un projet dont les enjeux diffèrent doit redéclarer la table COTATION_PAN",
    "risque : la probabilité de défaillance est approchée par le nombre de commits touchant le "
    "fichier ; hors dépôt git, elle retombe sur une valeur neutre",
]


@lru_cache(maxsize=512)
def probabilite(fichier: str) -> int:
    """Probabilité de défaillance 1-5, approchée par la fréquence de modification du fichier.

    Signal réel quand le dépôt est disponible ; valeur neutre déclarée sinon (jamais inventée).
    """
    chemin = Path(fichier)
    if not chemin.exists():
        return PROBABILITE_DEFAUT
    try:
        resultat = subprocess.run(
            ["git", "log", "--oneline", "--", chemin.name],
            cwd=chemin.parent,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return PROBABILITE_DEFAUT
    if resultat.returncode != 0:
        return PROBABILITE_DEFAUT
    commits = len([ligne for ligne in resultat.stdout.splitlines() if ligne.strip()])
    # Un fichier vu une seule fois n est pas STABLE, il est INCONNU : sans historique, le signal
    # n est pas exploitable et la valeur neutre déclarée vaut mieux qu une fausse confiance.
    if commits <= 1:
        return PROBABILITE_DEFAUT
    return min(5, commits)


def coter(pan: str, identifiant: str, source: str) -> int:
    """Score de risque 1-125 d un élément de surface."""
    criticite, cout = COTATION_PAN.get(pan, _DEFAUT_PAN)
    classe = identifiant.split(":", 1)[0]
    criticite = min(5, criticite + MAJORATION_CLASSE.get(classe, 0))
    return criticite * probabilite(source) * cout
