"""Glossaire d affichage du dashboard — libellés parlants sur identifiants GELÉS.

Table de correspondance au sens du contrat d interface du pilot (§3 bis) : les IDENTIFIANTS
techniques (noms de seuils, clés de compteurs, états, catégories d actions) sont des
référentiels opposables — la recette, la traçabilité exigences→tests et le filtre `jq` du
DOSSIER-MEP les consomment. Ils ne changent JAMAIS ici. Ce module ne porte que la COUCHE
D AFFICHAGE : libellé humain + descriptif, validés par l humain (campagne TF-0153, 13/08/2026).

Un identifiant absent du glossaire s affiche tel quel : l affichage se dégrade, la donnée ne
ment pas. L inverse — un libellé sans identifiant — n existe pas : le glossaire ne crée rien.
"""

from __future__ import annotations

# --- Seuils opposables (clé = nom du seuil au rapport, GELÉ) -----------------------------------
SEUILS: dict[str, str] = {
    "branches_module_exerce": "Couverture de branches des modules exercés",
    "couverture_surface_api": "Surface API exercée — endpoints × codes de retour",
    "couverture_surface_interface": "Affordances câblées — boutons, liens, formulaires",
    "couverture_surface_qualif": "Routes UI parcourues sans erreur",
    "mutation_globale": "Robustesse de la suite — score de mutation global",
    "mutation_module_metier": "Robustesse de la suite — modules métier",
}

# --- Compteurs de synthèse et de tendance (clé = data-total, GELÉE) ----------------------------
COMPTEURS: dict[str, tuple[str, str]] = {
    # cle: (libellé, descriptif — ce que le nombre compte, pour qu il ne soit jamais seul)
    "elements": (
        "Éléments inventoriés",
        "tout ce que l audit a trouvé à tester : routes, boutons, tables, modules, migrations",
    ),
    "passes": (
        "Passés",
        "éléments exercés par la suite sans aucun constat d échec",
    ),
    "echecs": (
        "Constats d échec",
        "défauts mesurés, chacun rattaché à un élément nommé",
    ),
    "echecs_bloquants": (
        "… dont bloquants",
        "constats de sévérité « bloquant » — à traiter avant mise en production",
    ),
    "non_joues": (
        "Non joués",
        "éléments non testables ici (configuration absente) + pans sans adaptateur",
    ),
    "non_testables": (
        "Non testables ici",
        "la configuration requise est absente de cet environnement — personne ne POUVAIT tester",
    ),
    "pans_non_couverts": (
        "Pans non couverts",
        "domaines entiers sans banc d essai, avec motif et chemin de couverture",
    ),
    "actions": (
        "Actions proposées",
        "suites à donner, classées : automatisable par l IA, développeur, ou vous",
    ),
}

# --- États d un élément (clé = état du rapport, GELÉ — surface.ETATS) --------------------------
# picto, libellé, classe de badge, descriptif. Jamais la couleur seule (loi : picto + libellé).
ETATS: dict[str, tuple[str, str, str, str]] = {
    "exerce": ("✓", "Passé", "b-pass", "exercé par la suite, aucun constat d échec"),
    "defaut": ("✕", "KO", "b-fail", "un constat d échec mesuré est rattaché à cet élément"),
    "non_exerce": ("○", "Non joué", "b-part", "inventorié mais jamais atteint par la suite"),
    "non_testable": (
        "⊘",
        "Non testable ici",
        "b-info",
        "la configuration requise est absente de cet environnement",
    ),
    "exclu": ("–", "Exclu", "b-info", "écarté du périmètre, motif porté par le rapport"),
}

# --- En-têtes de colonnes : libellé affiché + tooltip (l id de colonne reste data-label) -------
ENTETES: dict[str, tuple[str, str]] = {
    "élément": ("Élément testé", "identifiant de l élément dans l inventaire de surface"),
    "objectif": (
        "Objectif du test",
        "ce que le test vérifie exactement — son périmètre précis, dérivé de la forme de "
        "l élément (retour humain du 14/08)",
    ),
    "état": ("Résultat", "état mesuré : ✓ Passé · ✕ KO · ○ Non joué · ⊘ Non testable · – Exclu"),
    "classe": ("Type de constat", "famille du défaut mesuré ; vide = passé, sans objet"),
    "constat mesuré": (
        "Constat mesuré — pourquoi",
        "la preuve : ce qui a été observé ; pour un KO ou un non-joué, c est le pourquoi",
    ),
    "risque": (
        "Risque",
        "criticité × probabilité × coût tardif (notes 1-5, score 1-125) — calculé au rapport",
    ),
    "sévérité": ("Sévérité", "classe déclarée par la règle : bloquant · majeur · mineur"),
}

# --- Catégories d actions (clé = categorie du rapport, GELÉE — actions.CATEGORIES) -------------
CATEGORIES_ACTIONS: dict[str, tuple[str, str]] = {
    "auto_ia": (
        "Automatisable par l IA",
        "dérivable d une source qui fait foi — corrigeable en boucle de fermeture bornée",
    ),
    "manuelle_dev": (
        "Manuelle — développeur",
        "un développeur doit trancher (câbler, retirer, aligner, décider quoi affirmer)",
    ),
    "manuelle_utilisateur": (
        "Manuelle — à faire par vous",
        "personne d autre ne peut le faire : identifiants, instance peuplée, validation visuelle",
    ),
}

# --- Étapes cibles des actions (clé = etape_cible du rapport, GELÉE — actions.ETAPES) ----------
ETAPES_ACTIONS: dict[str, str] = {
    "development": "Développement",
    "tests-suite": "Suite de tests",
    "design": "Design",
    "mep-config": "Configuration MEP",
    "forge": "Forge (défaut d auditeur)",
}


def seuil(nom: str) -> str:
    return SEUILS.get(nom, nom)


def compteur(cle: str) -> tuple[str, str]:
    return COMPTEURS.get(cle, (cle, ""))


def etat(valeur: str) -> tuple[str, str, str, str]:
    return ETATS.get(valeur, ("·", valeur, "b-info", ""))


def entete(nom: str) -> tuple[str, str]:
    return ENTETES.get(nom, (nom, ""))


def categorie_action(cle: str) -> tuple[str, str]:
    return CATEGORIES_ACTIONS.get(cle, (cle, f"catégorie {cle}"))


def etape_action(cle: str) -> str:
    return ETAPES_ACTIONS.get(cle, cle)
