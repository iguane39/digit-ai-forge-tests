"""Référentiel d exigences — rattachement DÉCLARÉ, jamais deviné en silence.

Le cahier fonctionnel doit citer, pour chaque cas, l exigence qu il vérifie. Encore faut-il
que le lien existe. Deux situations, et la seconde est la plus fréquente :

  1. le référentiel porte lui-même la clé technique (`elements: ["code:GET /api/x=200"]`) —
     le rattachement est un FAIT, provenance `declare` ;
  2. le référentiel ne porte que du français (« Page des boîtes mail »), et la surface du
     rapport ne porte que de la technique (`route:/boites`). Aucun lien n est dérivable
     rigoureusement. On en tente un LEXICAL, borné et déclaré comme tel — provenance
     `lexical`, à valider par un humain.

Ce que ce module refuse : présenter un rattachement lexical comme un fait. Un cahier qui
affirme « ce cas vérifie E-014 » sans que rien ne l établisse fabrique une traçabilité fausse,
c est-à-dire pire que pas de traçabilité — on cesse de la vérifier.

Et la réciproque, que personne ne regarde jamais : **les exigences qu AUCUN cas ne touche.**
Elles sont listées, nommément. C est le seul moyen de voir qu un pan entier du besoin n a pas
de test, quand la couverture de surface, elle, est au vert.

Chemin du référentiel : `FORGE_TESTS_EXIGENCES` (variable d environnement ou
`<projet>/.env.forge-tests`). Absent, le cahier le DÉCLARE en tête et dérive de la seule surface.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

NON_JUGE = [
    "exigences : sans cle technique au referentiel, le rattachement d un cas a une exigence "
    "est LEXICAL (deux racines de 5 caracteres communes au minimum) — il est publie avec sa "
    "provenance et doit etre valide par un humain, jamais lu comme un fait",
    "exigences : la reciproque (exigence sans aucun cas rattache) est calculee sur le meme "
    "rattachement lexical — une exigence declaree « sans cas » peut en avoir un que le "
    "vocabulaire n a pas rapproche",
]

VARIABLE = "FORGE_TESTS_EXIGENCES"
_RACINE = 5
_TAILLE_MINIMALE = 4
_COMMUNES_MINIMUM = 2

# Mots trop fréquents pour rattacher quoi que ce soit : ils apparieraient tout avec tout.
# Écrits en un bloc puis découpés : une liste de littéraux ferait trente lignes pour trente mots.
_MOTS_VIDES = """
    dans avec pour sans sous leur leurs elle elles cette cettes ceux celui celle plus moins
    tout tous toute toutes chaque autre autres meme memes etre avoir fait faire est sont
    doit doivent peut peuvent depuis apres avant entre selon quand alors ainsi donc mais
    page pages ecran ecrans liste listes champ champs bouton boutons lien liens test tests
    user users data code codes null true false none self none type types
    """
_VIDES = frozenset(_MOTS_VIDES.split())


def _sans_accent(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def racines(texte: str) -> set[str]:
    """Racines significatives d un texte — minuscules, sans accent, tronquées à 5 caractères."""
    mots = re.split(r"[^0-9A-Za-zÀ-ÿ]+", _sans_accent(texte or "").lower())
    return {
        mot[:_RACINE]
        for mot in mots
        if len(mot) >= _TAILLE_MINIMALE and mot not in _VIDES and not mot.isdigit()
    }


def chemin_declare(cible: Path | None = None) -> Path | None:
    """Chemin du référentiel, lu dans l environnement (ou le `.env.forge-tests` du projet)."""
    if cible is not None:
        from forge_tests.authentification import charger_env

        charger_env(cible)
    brut = (os.environ.get(VARIABLE) or "").strip()
    return Path(brut) if brut else None


def charger(chemin: Path | None) -> dict | None:
    """Référentiel normalisé, ou None. Un fichier illisible est un REFUS, pas un silence."""
    if chemin is None:
        return None
    if not chemin.is_file():
        raise FileNotFoundError(
            f"{VARIABLE} désigne « {chemin} », qui n existe pas — corriger le chemin ou retirer "
            "la variable ; un référentiel introuvable ne se remplace pas par une supposition"
        )
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    surface = {
        str(s.get("id")): s for s in (donnees.get("surface") or []) if isinstance(s, dict)
    }
    entrees = []
    for exigence in donnees.get("exigences") or []:
        if not isinstance(exigence, dict):
            continue
        libelles = [
            str(surface[ref].get("libelle") or "")
            for ref in (exigence.get("surface") or [])
            if ref in surface
        ]
        entrees.append(
            {
                "id": str(exigence.get("id") or ""),
                "enonce": str(exigence.get("enonce") or ""),
                "critere": str(exigence.get("critere") or ""),
                "palier": str(exigence.get("palier") or ""),
                "surface": list(exigence.get("surface") or []),
                "libelles_surface": libelles,
                # Clé technique explicite : le seul rattachement qui soit un FAIT.
                "elements": [str(e) for e in (exigence.get("elements") or [])],
                "_racines": racines(
                    " ".join(
                        [
                            exigence.get("enonce") or "",
                            exigence.get("critere") or "",
                            *libelles,
                        ]
                    )
                ),
            }
        )
    return {
        "chemin": str(chemin),
        "projet": str(donnees.get("projet") or ""),
        "exigences": entrees,
        "besoins": donnees.get("besoins") or [],
    }


def rattacher(referentiel: dict | None, element: dict) -> list[dict]:
    """Exigences rattachées à un élément de surface, chacune avec sa PROVENANCE."""
    if not referentiel:
        return []
    identifiant = str(element.get("id") or "")
    texte = " ".join(
        str(element.get(cle) or "") for cle in ("id", "libelle", "message", "localisation")
    )
    racines_element = racines(texte)
    trouves: list[dict] = []
    for exigence in referentiel["exigences"]:
        if identifiant in exigence["elements"]:
            trouves.append({"id": exigence["id"], "provenance": "declare"})
            continue
        communes = racines_element & exigence["_racines"]
        if len(communes) >= _COMMUNES_MINIMUM:
            trouves.append(
                {
                    "id": exigence["id"],
                    "provenance": "lexical",
                    "racines": sorted(communes)[:4],
                }
            )
    return trouves


def sans_cas(referentiel: dict | None, rattachements: dict[str, list[dict]]) -> list[dict]:
    """Exigences qu AUCUN élément de surface ne touche — nommées, jamais tues."""
    if not referentiel:
        return []
    touchees = {r["id"] for liste in rattachements.values() for r in liste}
    return [
        {"id": e["id"], "enonce": e["enonce"], "palier": e["palier"]}
        for e in referentiel["exigences"]
        if e["id"] not in touchees
    ]
