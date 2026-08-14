"""Libellés et objectifs d'éléments — DÉRIVÉS de la forme de l'identifiant, jamais inventés.

« qualif:effet:/:0:form » n'explique rien à un lecteur (retour humain du 13/08, TF-0175).
Ce module porte les deux dérivations d'affichage partagées par le dashboard ET les cahiers :

  - `libelle_element`  : le nom humain (« formulaire n°1 de l'écran / ») ;
  - `objectif_element` : le périmètre précis du test (« vérifier que cette affordance est
    câblée… ») — retour humain du 14/08 : sans lui, le lecteur ne sait pas ce que la ligne
    vérifie.

Règle constante : forme inconnue → chaîne vide. L'affichage se dégrade (l'id technique reste
toujours rendu), la donnée ne ment pas.
"""

from __future__ import annotations

import re
from pathlib import Path

TAGS_FR = {
    "form": "formulaire", "button": "bouton", "a": "lien", "input": "champ",
    "select": "liste déroulante", "textarea": "zone de texte", "summary": "dépliant",
}

_LIBELLES: tuple[tuple[re.Pattern[str], object], ...] = (
    (re.compile(r"^qualif:effet:(?P<r>[^:]*):(?P<n>\d+):(?P<t>\w+)$"),
     lambda m: f"{TAGS_FR.get(m['t'], m['t'])} n°{int(m['n']) + 1} de l'écran {m['r'] or '/'}"),
    (re.compile(r"^qualif:route:(?P<r>\S+)$"), lambda m: f"chargement de l'écran {m['r']}"),
    (re.compile(r"^qualif:console:(?P<r>\S+)$"),
     lambda m: f"console de l'écran {m['r']} (zéro erreur attendue)"),
    (re.compile(r"^qualif:marqueur:(?P<r>\S+)$"),
     lambda m: f"rendu de l'écran {m['r']} (marqueur de contenu attendu)"),
    (re.compile(r"^element:(?P<x>\S+)$"), lambda m: f"élément d'interface « {m['x']} »"),
    (re.compile(r"^route:(?P<r>\S+)$"), lambda m: f"route {m['r']}"),
    (re.compile(r"^endpoint:(?P<v>[A-Z]+) (?P<p>\S+)$"), lambda m: f"API {m['v']} {m['p']}"),
    (re.compile(r"^code:(?P<v>[A-Z]+) (?P<p>[^=]+)=(?P<c>\d+)$"),
     lambda m: f"API {m['v']} {m['p']} — réponse {m['c']} attendue"),
    (re.compile(r"^divergence:(?:code|endpoint):(?P<v>[A-Z]+) (?P<p>\S+)"),
     lambda m: f"API {m['v']} {m['p']} — déclaré ≠ constaté"),
    (re.compile(r"^contrainte:(?P<x>\S+?)\.not_null$"),
     lambda m: f"colonne obligatoire « {m['x']} » (NOT NULL)"),
    (re.compile(r"^contrainte:(?P<x>\S+)$"), lambda m: f"contrainte de données « {m['x']} »"),
    (re.compile(r"^(?P<k>index|trigger):(?P<x>\S+)$"), lambda m: f"{m['k']} « {m['x']} »"),
    (re.compile(r"^migration:(?P<x>[^:]+):retour$"),
     lambda m: f"migration {m['x']} — retour arrière"),
    (re.compile(r"^migration:(?P<x>[^:]+):rejeu$"), lambda m: f"migration {m['x']} — rejeu"),
    (re.compile(r"^divergence:migration:(?P<x>[^:]+)"),
     lambda m: f"migration {m['x']} — défait la précédente"),
    (re.compile(r"^branche:(?P<f>[^:]+):(?P<l>\d+)$"),
     lambda m: f"branche de traitement {m['f']} ligne {m['l']}"),
    (re.compile(r"^chemin:(?P<f>[^:]+):(?P<l>\d+)$"),
     lambda m: f"chemin de lecture {m['f']} ligne {m['l']}"),
    (re.compile(r"^mutant:(?P<f>[^:]+):(?P<l>\d+):(?P<mut>\S+)$"),
     lambda m: f"robustesse : mutation {m['f']} ligne {m['l']} ({m['mut'].replace('->', ' → ')})"),
    (re.compile(r"^module(?:-non-exerce)?:(?P<x>\S+)$"), lambda m: f"module source {m['x']}"),
    (re.compile(r"^seuil:mutation-module:(?P<x>\S+)$"),
     lambda m: f"seuil de mutation du module {m['x']}"),
    (re.compile(r"^securite:sast:(?P<p>.+):(?P<l>\d+)$"),
     lambda m: f"analyse sécurité — {Path(m['p']).name} ligne {m['l']}"),
    (re.compile(r"^a11y:(?P<r>[^:]+)"), lambda m: f"accessibilité de l'écran {m['r']}"),
    (re.compile(r"^visuel:(?P<r>\S+)"), lambda m: f"rendu visuel de l'écran {m['r']}"),
    (re.compile(r"^interface:(?P<f>[^:]+):(?P<l>\d+):(?P<t>\w+)$"),
     lambda m: f"{TAGS_FR.get(m['t'], m['t'])} ligne {m['l']} de {m['f']}"),
    (re.compile(r"^rejet:"), lambda m: "codes de rejet du traitement par lot"),
    (re.compile(r"^seuil:(?P<x>\S+)$"), lambda m: f"seuil opposable « {m['x']} »"),
)


def libelle_element(identifiant: str) -> str:
    for motif, gabarit in _LIBELLES:
        m = motif.match(identifiant)
        if m:
            return gabarit(m)  # type: ignore[operator]
    return ""


# --- Objectif du test (retour humain du 14/08) --------------------------------------------------
# Chaque ligne de chapitre annonce SON périmètre : ce que le test vérifie exactement — dérivé
# de la même forme d'identifiant que le libellé, donc jamais deux vérités.
_OBJECTIFS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^qualif:effet:[^:]*:\d+:form$"),
     "vérifier que ce formulaire est câblé : sa soumission doit produire un effet observable "
     "(requête émise, navigation ou message) — jamais une soumission qui ne part nulle part"),
    (re.compile(r"^qualif:effet:[^:]*:\d+:(?:button|a|summary)$"),
     "vérifier que cette affordance est câblée : son activation doit produire un effet "
     "observable — une affordance est câblée ou elle n'existe pas"),
    (re.compile(r"^qualif:effet:"),
     "vérifier que cet élément interactif est câblé : un écouteur ou une action doit lui "
     "attacher un effet observable"),
    (re.compile(r"^qualif:route:"),
     "vérifier que l'écran se charge : réponse sans code d'erreur et contenu réellement rendu"),
    (re.compile(r"^qualif:console:"),
     "vérifier que la console de l'écran reste vide d'erreurs au chargement"),
    (re.compile(r"^qualif:marqueur:"),
     "vérifier que l'écran rend son contenu attendu (marqueur présent : titre ou repère "
     "déclaré), pas une page techniquement servie mais vide"),
    (re.compile(r"^code:[A-Z]+ [^=]+=\d+$"),
     "vérifier que l'API répond le code déclaré dans son contrat, une assertion à l'appui"),
    (re.compile(r"^endpoint:"),
     "vérifier que cet endpoint est réellement atteint par la suite et que son résultat "
     "(corps compris) est affirmé"),
    (re.compile(r"^divergence:"),
     "vérifier que la déclaration (contrat, schéma) et le comportement constaté coïncident"),
    (re.compile(r"^contrainte:"),
     "vérifier que la base REJETTE une écriture qui viole la contrainte — une contrainte "
     "jamais violée n'est pas une contrainte vérifiée"),
    (re.compile(r"^(?:table|index|trigger):"),
     "vérifier que l'objet de schéma existe après migration et qu'au moins un chemin de la "
     "suite s'en sert"),
    (re.compile(r"^migration:"),
     "vérifier que la migration s'applique sans erreur (et se rejoue à l'identique pour un "
     "aller) sur une base neuve"),
    (re.compile(r"^mutant:"),
     "vérifier que la suite DÉTECTE la mutation : au moins un test doit échouer sur le code "
     "muté — sinon l'assertion n'affirme pas ce qu'elle prétend"),
    (re.compile(r"^module"),
     "vérifier que le module source est importé et exercé par la suite du projet"),
    (re.compile(r"^(?:branche|chemin):"),
     "vérifier que cette branche de traitement est parcourue et que son effet propre est "
     "affirmé — un chemin d'erreur non parcouru échouera le jour où il servira"),
    (re.compile(r"^rejet:"),
     "vérifier que le traitement émet ce code de rejet sur une entrée violante, le journalise "
     "et poursuit ou s'arrête comme spécifié"),
    (re.compile(r"^interface:"),
     "vérifier que l'affordance du gabarit est câblée à un gestionnaire — statiquement, "
     "l'effet réel relevant du pan d'exécution"),
    (re.compile(r"^securite:"),
     "vérifier que le point signalé est supprimé, encadré par une validation, ou déclaré "
     "inoffensif avec son argument"),
    (re.compile(r"^a11y:"),
     "vérifier l'accessibilité de l'écran : noms accessibles, contrastes, ordre des titres"),
    (re.compile(r"^visuel:"),
     "vérifier que le rendu correspond au golden accepté — toute différence est arbitrée par "
     "un humain, jamais entérinée seule"),
    (re.compile(r"^seuil:"),
     "vérifier que l'engagement chiffré du contrat de tests est tenu"),
    (re.compile(r"^(?:route|element):"),
     "vérifier que cet élément d'interface répond et que son état est affirmé"),
)


def objectif_element(identifiant: str) -> str:
    for motif, texte in _OBJECTIFS:
        if motif.match(identifiant):
            return texte
    return ""
