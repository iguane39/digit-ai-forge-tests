"""Livrables d audit — cahiers de tests dérivés et jeux de données synthétiques.

Un audit produisait jusqu ici un rapport : une liste de constats, lisible par qui connaît le
framework. Ce paquet en tire les documents qu une équipe utilise réellement — deux cahiers de
tests et leur jeu de données — sans qu aucun ne soit écrit à la main.

Garde-fou G-1, appliqué ici comme au générateur de cas : **rien n est écrit dans le projet
audité.** Le dossier de dépôt est une PROPOSITION désignée par l opérateur, et la vérification
n est pas une convention de nommage : le chemin est résolu, et s il tombe sous la racine
auditée, la production est refusée avant d écrire quoi que ce soit.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from forge_tests.adaptateurs import REGISTRE
from forge_tests.livrables import cahiers as _cahiers
from forge_tests.livrables import exigences as _exigences
from forge_tests.livrables import jeux as _jeux
from forge_tests.livrables import surface as _surface
from forge_tests.livrables.nommage import (
    empreinte,
    empreinte_fichier,
    nommer,
    serialiser_rapport,
)

VARIABLE_PRODUIT = "FORGE_TESTS_PRODUIT"


class DepotInterdit(RuntimeError):
    """G-1 — le dossier de livrables tombe dans le projet audité. Rien n est écrit."""


def _verifier_hors_projet(dossier: Path, cible: Path) -> None:
    racine, depot = Path(cible).resolve(), Path(dossier).resolve()
    if depot == racine or racine in depot.parents:
        raise DepotInterdit(
            f"G-1 : « {depot} » est dans le projet audité (« {racine} »). Les livrables sont des "
            "PROPOSITIONS : les déposer dans le projet reviendrait à ce que la forge écrive chez "
            "l audité, puis s auditise elle-même au run suivant. Choisir un dossier extérieur"
        )


def nom_du_produit(cible: Path, referentiel: dict | None) -> str:
    """Nom du produit — déclaré, sinon lu au référentiel, sinon le dossier. Jamais inventé."""
    from forge_tests.authentification import charger_env

    charger_env(cible)
    declare = (os.environ.get(VARIABLE_PRODUIT) or "").strip()
    if declare:
        return declare
    if referentiel and referentiel.get("projet"):
        return str(referentiel["projet"])
    return Path(cible).resolve().name


def produire(
    rapport: dict,
    cible: Path,
    dossier: Path,
    precedent: dict | None = None,
    jour: _dt.date | None = None,
    rapport_nom: str | None = None,
) -> dict[str, Path]:
    """Écrit les livrables et renvoie leurs chemins, par nature.

    L ordre n est pas arbitraire : le jeu de données est écrit AVANT les cahiers, parce que
    ceux-ci scellent son empreinte. Un cahier qui citerait un jeu non encore produit
    scellerait une promesse au lieu d un fait.
    """
    cible, dossier = Path(cible).resolve(), Path(dossier).resolve()
    _verifier_hors_projet(dossier, cible)
    dossier.mkdir(parents=True, exist_ok=True)

    referentiel = _exigences.charger(_exigences.chemin_declare(cible))
    produit = nom_du_produit(cible, referentiel)
    date = (jour or _dt.date.today()).strftime("%Y-%m-%d")
    canonique = serialiser_rapport(rapport)

    chapitres_bruts = _surface.repartir(rapport, REGISTRE)

    # 1. Jeu de données — vérifié synthétique AVANT écriture, jamais après.
    jeu = _jeux.construire(chapitres_bruts, produit)
    _jeux.verifier(jeu, cible)
    chemin_jeu = nommer(produit, "Jeu de donnees de tests", ".json", dossier, jour)
    texte_jeu = json.dumps(jeu, ensure_ascii=False, indent=2) + "\n"
    chemin_jeu.write_text(texte_jeu, encoding="utf-8", newline="\n")

    contexte = {
        "produit": produit,
        "date": date,
        "verdict": rapport.get("verdict"),
        "rapport_nom": rapport_nom or "(rapport produit par ce run)",
        "rapport_sha": empreinte(canonique),
        "exigences_chemin": referentiel["chemin"] if referentiel else "",
        "exigences_sha": empreinte_fichier(Path(referentiel["chemin"])) if referentiel else "",
        "exigences_nombre": len(referentiel["exigences"]) if referentiel else 0,
        "jeu_nom": chemin_jeu.name,
        "jeu_sha": empreinte(texte_jeu),
    }

    # 2. Cahiers — un chapitre par déclaration d adaptateur, un cas ou un « non couvert » par
    #    élément. L exhaustivité est une propriété vérifiable, pas une intention.
    chapitres = [_cahiers.cas_du_chapitre(c, referentiel) for c in chapitres_bruts]
    chemins: dict[str, Path] = {"jeu": chemin_jeu}
    for famille, nature in (
        ("fonctionnel", "Cahier de tests fonctionnels"),
        ("technique", "Cahier de tests techniques"),
    ):
        corps = _cahiers.construire(
            famille, f"{produit} — {nature.lower()}", chapitres, contexte, referentiel
        )
        chemin = nommer(produit, nature, ".md", dossier, jour)
        chemins[famille] = _cahiers.ecrire(chemin, corps, contexte)

    return chemins


def resume(chemins: dict[str, Path]) -> str:
    ordre = ("fonctionnel", "technique", "jeu")
    etiquettes = {
        "fonctionnel": "cahier fonctionnel",
        "technique": "cahier technique",
        "jeu": "jeu de donnees",
    }
    return "\n".join(
        f"livrable {etiquettes[cle]:<20} -> {chemins[cle]}" for cle in ordre if cle in chemins
    )
