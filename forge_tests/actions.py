"""Classification TERNAIRE des suites à donner — au RAPPORT d'abord, jamais au seul affichage.

Un rapport d audit nomme des défauts ; il ne dit pas QUI les répare. Trois destinataires
existent réellement et se confondent tout le temps :

  - `auto_ia` — un agent de code sait le faire seul, sans arbitrage : la source qui fait foi
    (schéma, contrainte, mutant survivant) dit exactement ce qu il faut écrire ;
  - `manuelle_dev` — un développeur doit trancher : câbler ou retirer une affordance, aligner
    une déclaration sur un comportement, décider ce que le test doit affirmer ;
  - `manuelle_utilisateur` — personne d autre que l humain qui exploite le produit ne peut le
    faire : fournir un identifiant, servir une instance peuplée, valider qu un rendu modifié
    est bien le rendu voulu. Aucun agent ne peut se substituer à lui.

Et cinq étapes cibles, qui disent OÙ la correction atterrit : `development`, `tests-suite`,
`design`, `mep-config`, et `forge` — cette dernière étant réservée au défaut d AUDITEUR : la
forge ne sait pas classer, ou n a pas d adaptateur. Un défaut de la forge se nomme comme les
autres, il ne se tait pas.

**Le champ vit au rapport JSON.** Le dashboard ne fait que le rendre : s il le calculait,
deux lecteurs du même audit — l un par le HTML, l autre par `jq` — auraient deux vérités.

Extraction du filtre attendu par le DOSSIER-MEP (mandat 4) :

    jq '.actions[] | select(.categorie=="manuelle_utilisateur")' rapport.json
"""

from __future__ import annotations

CATEGORIES = ("auto_ia", "manuelle_dev", "manuelle_utilisateur")
ETAPES = ("development", "tests-suite", "design", "mep-config", "forge")

NON_JUGE = [
    "actions : la categorie et l etape sont derivees de la CLASSE du finding, pas de son "
    "contenu — deux findings de meme classe recoivent la meme suite, meme si l un est trivial "
    "et l autre profond ; l attendu, lui, cite l element",
    "actions : `auto_ia` signifie « derivable d une source qui fait foi », pas « sans "
    "relecture » — un cas genere reste une PROPOSITION soumise a relecture (loi du generateur)",
]

# Préfixes d identifiant des actions qui ne viennent pas d un finding. Ils existent parce que
# les deux plus grosses causes d inaction d un audit — la configuration absente et le pan sans
# adaptateur — ne produisent AUCUN finding : sans entrée dédiée, elles sortiraient de la liste
# des travaux au moment précis où elles la dominent.
PREFIXE_NON_TESTABLE = "non-testable:"
PREFIXE_PAN_NON_COUVERT = "pan-non-couvert:"


def _pans_generables() -> set[str]:
    """Pans dont un GÉNÉRATEUR sait produire le cas manquant — lu sur les générateurs eux-mêmes.

    Écrite en dur, la liste aurait divergé au premier générateur ajouté : un pan nouvellement
    générable serait resté classé `manuelle_dev`, c est-à-dire du travail humain réclamé pour
    une chose que la forge sait déjà faire.
    """
    from forge_tests import generateur, generateur_data

    return {
        pan
        for pan in (getattr(generateur, "PAN", None), getattr(generateur_data, "PAN", None))
        if pan
    }


# classe de finding -> (categorie, etape_cible, gabarit d attendu).
# `{id}` est l identifiant de l element, `{message}` le constat mesuré.
_REGLES: dict[str, tuple[str, str, str]] = {
    "element-non-exerce": (
        "manuelle_dev",
        "tests-suite",
        "ajouter à la suite un cas qui exerce « {id} » et affirme son résultat ; l'élément est "
        "inventorié et jamais atteint ({message})",
    ),
    "seuil-non-tenu": (
        "manuelle_dev",
        "tests-suite",
        "ramener la couverture au seuil opposable : {message}. Décider quels éléments non "
        "exercés couvrir en priorité (ils sont triés par risque au rapport)",
    ),
    "mutant-survivant": (
        "auto_ia",
        "tests-suite",
        "renforcer l'assertion qui laisse survivre le mutant « {id} » : le test passe avec le "
        "code muté, il n'affirme donc pas ce qu'il prétend ({message})",
    ),
    "module-non-exerce": (
        "manuelle_dev",
        "tests-suite",
        "importer et exercer le module « {id} », ou déclarer pourquoi il n'a pas à l'être ; "
        "aucun test ne le charge aujourd'hui ({message})",
    ),
    "affordance-inerte": (
        "manuelle_dev",
        "development",
        "câbler l'affordance « {id} » ou la retirer du gabarit — une affordance est câblée ou "
        "elle n'existe pas ({message})",
    ),
    "affordance-sans-effet": (
        "manuelle_dev",
        "development",
        "attacher un effet à « {id} » sur l'instance servie, ou retirer l'affordance "
        "({message})",
    ),
    "divergence": (
        "manuelle_dev",
        "development",
        "aligner la déclaration et le comportement pour « {id} » : {message}",
    ),
    "route-en-defaut": (
        "manuelle_dev",
        "development",
        "corriger la route « {id} » : {message}",
    ),
    "securite": (
        "manuelle_dev",
        "development",
        "traiter le signalement de sécurité sur « {id} » : {message}",
    ),
    "accessibilite": (
        "manuelle_dev",
        "design",
        "corriger l'accessibilité de « {id} » (nom accessible, contraste, ordre de titres) : "
        "{message}",
    ),
    "regression-visuelle": (
        "manuelle_utilisateur",
        "design",
        "ARBITRER le rendu de « {id} » : valider le nouveau golden si le changement est voulu, "
        "sinon corriger le rendu. Aucun agent ne peut décider à la place de l'humain si un "
        "écran est conforme à l'intention ({message})",
    ),
    "sonde-muette": (
        "manuelle_utilisateur",
        "mep-config",
        "déclarer au projet ce que la sonde doit observer (FORGE_TESTS_APP=« module:attribut » "
        "dans `<projet>/.env.forge-tests`), puis `--reprendre` le rapport : la mesure est "
        "aveugle tant que la configuration manque ({message})",
    ),
}


def _defaut_auditeur(classe: str) -> tuple[str, str, str]:
    """Suite d'une classe de finding que la forge ne sait PAS classer — un défaut d'auditeur.

    Sans cette branche, une classe nouvelle sortirait sans action : elle disparaîtrait de la
    liste des travaux tout en restant au rapport, c est-à-dire l absence silencieuse d un
    étage plus haut.
    """
    return (
        "manuelle_dev",
        "forge",
        f"DÉFAUT D'AUDITEUR : la classe de finding « {classe} » n'a pas de règle de "
        "classification. Déclarer sa suite dans `forge_tests/actions.py` (_REGLES), puis "
        "rejouer l'audit — le constat est mesuré, seule sa suite manque",
    )


def _action(finding: dict, pans_generables: set[str]) -> dict:
    classe = str(finding.get("classe") or "")
    identifiant = str(finding.get("id") or "")
    pan = str(finding.get("pan") or "")
    if classe in _REGLES:
        categorie, etape, gabarit = _REGLES[classe]
        if classe == "element-non-exerce" and pan in pans_generables:
            categorie = "auto_ia"
            gabarit = (
                "générer le cas qui exerce « {id} » (`--generer`) puis le relire et l'adopter : "
                "la source qui fait foi (schéma, contrainte) dit comment l'atteindre ({message})"
            )
    else:
        categorie, etape, gabarit = _defaut_auditeur(classe)
    return {
        "finding_ref": f"{pan}/{identifiant}" if pan else identifiant,
        "categorie": categorie,
        "etape_cible": etape,
        "attendu": gabarit.format(id=identifiant, message=str(finding.get("message") or "")),
    }


def classifier(
    findings: list[dict],
    non_testables: list[dict] | None = None,
    pans_non_couverts: list[dict] | None = None,
) -> list[dict]:
    """Une action par finding, plus une par manque de configuration et par pan sans adaptateur.

    Invariant vérifié en recette : **tout finding a exactement une action**. Un finding sans
    suite serait un constat sans destinataire, c est-à-dire un constat qui ne sera pas traité.
    """
    generables = _pans_generables()
    actions = [_action(f, generables) for f in findings]

    # Configuration absente : regroupée par (pan, champs requis). Une action par ÉLÉMENT
    # produirait des centaines de lignes identiques pour un seul geste humain.
    groupes: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for entree in non_testables or []:
        cle = (str(entree.get("pan") or ""), tuple(entree.get("champs_requis") or []))
        groupes.setdefault(cle, []).append(str(entree.get("element") or ""))
    pans_non_testables = {pan for pan, _ in groupes}
    for (pan, champs), elements in sorted(groupes.items()):
        actions.append(
            {
                "finding_ref": f"{PREFIXE_NON_TESTABLE}{pan}:{'+'.join(champs)}",
                "categorie": "manuelle_utilisateur",
                "etape_cible": "mep-config",
                "attendu": (
                    # Retour humain du 14/08 : la phrase précédente était incompréhensible
                    # (liste de 20 variables en tête, grammaire cassée). Structure fixe :
                    # quoi faire → pourquoi → ce qu'on obtient. Les CHAMPS restent nommés
                    # (jamais leurs valeurs), mais en fin de phrase, pas en ouverture.
                    f"renseigner la configuration d'audit du pan « {pan} » dans "
                    f"`<projet>/.env.forge-tests`, puis relancer avec `--reprendre "
                    f"<rapport.json>`. Pourquoi : {len(elements)} élément(s) de ce pan sont "
                    "inventoriés mais aucune exécution ne pouvait les atteindre ici — manque "
                    "de configuration, pas trou de couverture du projet. Vous obtiendrez : "
                    "ces éléments mesurés au prochain audit, et le verdict PARTIEL pourra se "
                    f"prononcer. Champs à fournir ({len(champs)}) : "
                    f"{', '.join(champs) or 'la configuration manquante'}"
                ),
            }
        )

    for entree in pans_non_couverts or []:
        pan = str(entree.get("pan") or "")
        chemin = str(entree.get("pour_couvrir") or "")
        # Un pan non couvert FAUTE DE CONFIGURATION est un geste d exploitant ; un pan non
        # couvert faute d ADAPTATEUR est un défaut de la forge. Les confondre adresserait le
        # travail au mauvais destinataire — le reproche exact que ce module existe pour ôter.
        if pan in pans_non_testables:
            categorie, etape = "manuelle_utilisateur", "mep-config"
        else:
            categorie, etape = "manuelle_dev", "forge"
        actions.append(
            {
                "finding_ref": f"{PREFIXE_PAN_NON_COUVERT}{pan}",
                "categorie": categorie,
                "etape_cible": etape,
                "attendu": (
                    f"couvrir le pan « {pan} », aujourd'hui NON MESURÉ. Pourquoi : "
                    f"{entree.get('motif') or 'sans motif'}. Comment (vous obtiendrez le pan "
                    f"mesuré au prochain audit) : {chemin}"
                ),
            }
        )
    return actions


def repartition(actions: list[dict]) -> dict[str, dict[str, int]]:
    """Compte par catégorie et par étape — les deux axes, toujours présents même à zéro."""
    par_categorie = dict.fromkeys(CATEGORIES, 0)
    par_etape = dict.fromkeys(ETAPES, 0)
    for action in actions:
        categorie, etape = action.get("categorie", ""), action.get("etape_cible", "")
        par_categorie[categorie] = par_categorie.get(categorie, 0) + 1
        par_etape[etape] = par_etape.get(etape, 0) + 1
    return {"par_categorie": par_categorie, "par_etape": par_etape}
