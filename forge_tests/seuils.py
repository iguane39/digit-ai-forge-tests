"""Seuils opposables — au-dessus des standards du marché, versionnés ici, affichés au rapport.

A-3. Un seuil qui vit en constante privée d un adaptateur n est pas opposable : personne ne
peut le citer, le contester, ni constater qu il a bougé entre deux audits. Trois conséquences
tirées de la campagne du 2026-08-06 :

  1. **un seul endroit.** Tous les seuils du framework sont déclarés ici, avec leur
     justification. Un adaptateur qui en invente un ailleurs est un défaut ;
  2. **au rapport.** La section `seuils` du rapport JSON porte la valeur ET la justification :
     un lecteur qui trouve le verdict sévère lit pourquoi, sans ouvrir le code ;
  3. **au-dessus du plancher.** Les valeurs usuelles du marché (80 % de lignes, 70 % de
     branches, 60 % de mutation) sont un PLANCHER de recevabilité, pas une cible. Le produit
     qui les atteint tout juste a une suite qui accompagne le code, pas qui le contredit.

Arbitrage du 2026-08-06 (mandaté par la campagne, proposition A-3 retenue telle quelle et
complétée) :

  - `mutation_globale = 0,70` — le standard de l état de l art (mutmut, Stryker) place la barre
    de recevabilité vers 0,60. Retenu 0,70 : au-dessus, sans exiger un 1,0 qui pousserait à
    supprimer les mutants gênants plutôt qu à écrire l assertion manquante ;
  - `mutation_module_metier = 0,50` — un score GLOBAL de 0,70 se tient très bien avec un module
    métier à 0,0 noyé dans la masse. C est exactement le défaut que la campagne solde : le
    seuil par module interdit la compensation. 0,50 = « au moins un mutant sur deux est vu » ;
  - `branches_module_exerce = 0,60` — porte sur les seuls modules qu une suite exerce
    RÉELLEMENT (un module jamais importé relève de `module-non-exerce`, pas d un ratio). Le
    standard usuel est 0,70 de branches sur l ENSEMBLE du code, moyenne qui laisse un module
    entier à 0 ; ici la contrainte est par module, donc plus dure à ratio nominalement plus bas.
    Elle est volontairement plus basse que 0,70 parce qu elle ne se compense pas.

La sévérité de chaque seuil est déclarée avec lui : `bloquant` fait échouer l audit, `signale`
le nomme sans le bloquer. Aucun seuil n est `signale` par confort — seulement quand la mesure
elle-même est trop grossière pour condamner (cas de l échantillonnage de mutants, voir
`mutation_module_metier`).
"""

from __future__ import annotations

# Modules d infrastructure : leur logique est celle du cadre technique, pas celle du métier.
# Tout ce qui n est PAS dans cette liste est réputé porter de la logique métier — le défaut est
# donc l exigence, jamais l exemption. Un projet dont l architecture diffère la redéclare ici.
SOCLE = frozenset(
    {
        "main", "db", "database", "migrate", "settings", "config", "conf",
        "modeles", "models", "schemas", "schema", "deps", "dependencies", "wsgi", "asgi",
    }
)

SEUILS: dict[str, dict] = {
    "mutation_globale": {
        "valeur": 0.70,
        "severite": "bloquant",
        "porte_sur": "score de mutation agrégé du pan back",
        "justification": (
            "le standard de recevabilité du marché (mutmut, Stryker) est de l ordre de 0,60 ; "
            "0,70 le dépasse sans exiger un 1,0 qui pousse à supprimer le mutant plutôt qu à "
            "écrire l assertion"
        ),
    },
    "mutation_module_metier": {
        "valeur": 0.50,
        "severite": "bloquant",
        "porte_sur": "score de mutation de CHAQUE module de logique métier muté",
        "justification": (
            "un score global de 0,70 se tient avec un module métier à 0,0 noyé dans la masse ; "
            "le seuil par module interdit la compensation — c est le défaut que la campagne "
            "A-1/A-3 solde"
        ),
    },
    "branches_module_exerce": {
        "valeur": 0.60,
        "severite": "signale",
        "porte_sur": "couverture de BRANCHES de chaque module réellement exercé par la suite",
        "justification": (
            "le standard usuel (0,70 de branches) porte sur l ensemble du code et se laisse "
            "compenser ; porté par module il est plus dur à valeur nominale plus basse. "
            "`signale` et non `bloquant` : coverage.py ne voit pas les branches implicites "
            "(ternaire, court-circuit), le ratio est donc minoré par construction"
        ),
    },
    "couverture_surface_api": {
        "valeur": 1.0,
        "severite": "bloquant",
        "porte_sur": "endpoints x codes de retour inventoriés et exercés",
        "justification": (
            "un code de retour déclaré que la suite n émet jamais est un chemin d erreur non "
            "vérifié : sur la surface d API, le standard du framework est l exhaustivité"
        ),
    },
    "couverture_surface_interface": {
        "valeur": 1.0,
        "severite": "bloquant",
        "porte_sur": "affordances (bouton, lien, formulaire) câblées",
        "justification": (
            "« une affordance est câblée, ou elle n existe pas » — une promesse d interface non "
            "tenue n a pas de fraction acceptable"
        ),
    },
    "couverture_surface_qualif": {
        "valeur": 1.0,
        "severite": "bloquant",
        "porte_sur": "routes UI parcourues sans erreur sur une instance servie et peuplée",
        "justification": (
            "une route qui rend une erreur serveur, une trace ou une console en échec est vue "
            "par le premier utilisateur : aucune fraction n est acceptable"
        ),
    },
}


def valeur(nom: str) -> float:
    """Valeur du seuil nommé. Une clé inconnue est une erreur de programmation, pas un défaut."""
    return float(SEUILS[nom]["valeur"])


def severite(nom: str) -> str:
    return str(SEUILS[nom]["severite"])


def est_metier(nom_module: str) -> bool:
    """Un module porte-t-il de la logique métier ? Le défaut est OUI (l exemption se déclare).

    `nom_module` est le nom de fichier sans extension (`courrier`, `db`…). Les modules
    d infrastructure sont énumérés dans `SOCLE` — nominatifs, donc contestables.
    """
    return nom_module not in SOCLE


def au_rapport() -> dict:
    """Table des seuils telle qu elle est publiée au rapport JSON."""
    return {
        nom: {
            "valeur": detail["valeur"],
            "severite": detail["severite"],
            "porte_sur": detail["porte_sur"],
            "justification": detail["justification"],
        }
        for nom, detail in SEUILS.items()
    }
