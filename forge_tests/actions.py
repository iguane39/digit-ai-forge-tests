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

**La règle du destinataire (TF-2294, écrite pour que les 28 classes de TF-2285 se relisent contre
elle) :**

  1. `manuelle_utilisateur` quand la suite se ferme par un geste que le code du produit ne
     contient pas — une identité, une instance, un déploiement, un arbitrage — et que seul
     l humain qui exploite le produit détient. L étape est alors `mep-config` ou `design`, jamais
     `development` ni `tests-suite` ;
  2. `auto_ia` quand le constat nomme la source qui fait foi et que cette source dicte la
     correction sans choix de conception ni secret : la ligne à retirer, l argument à passer ;
  3. `manuelle_dev` pour tout le reste : la suite se ferme par une modification du code, de la
     suite de tests ou de la déclaration du produit, et il faut choisir laquelle.

Une classe dont les constats se ferment par les gestes de destinataires DIFFÉRENTS se scinde, une
classe par destinataire : une règle unique imposerait à l un le geste de l autre (`matrice-des-
droits` et `identites-de-roles-manquantes`). `tests/test_tf_2294_destinataires.py` tient cette
règle et la relecture des 28 classes.

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
    "actions : un pan SANS element inventorie dont la configuration n est que PRESUMEE ne "
    "produit plus d action humaine (TF-0381) — l entree reste au rapport avec son motif, mais "
    "reclamer une configuration pour un pan qui n a rien a mesurer usait la credibilite des "
    "actions qui comptent. Le pan reste NOMME : ce qui disparait est la demande, pas le constat",
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
    # TF-0283 — un lien de composant qui pointe à côté. Ce n est PAS une affordance inerte : il a
    # un effet, et c est le mauvais. Il n y a rien à câbler, il y a une destination à corriger —
    # et le destinataire est le développeur, jamais la forge.
    "lien-casse": (
        "manuelle_dev",
        "development",
        "corriger la destination du lien « {id} » : {message}. Un lien tient sa promesse ou il "
        "trompe — il n'y a pas d'entre-deux pour l'utilisateur qui clique",
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
    # TF-0223 : la porte d'entrée, et rien d'autre. Sans règle propre, la classe tombait au
    # « défaut d'auditeur » et repartait vers la forge — alors que le défaut qui l'a fait naître
    # (login de production en impasse, 303 puis 404, mort depuis le premier déploiement) était
    # un défaut de DÉPLOIEMENT du produit. Le mauvais destinataire, sur le constat le plus grave.
    "chaine-authentification-en-impasse": (
        "manuelle_dev",
        "development",
        "rétablir la chaîne d'authentification de « {id} » : la porte d'entrée doit aboutir à "
        "une mire identifiable (2xx + marqueur de contenu), pas à une erreur ni à une boucle "
        "({message})",
    ),
    "securite": (
        "manuelle_dev",
        "development",
        "traiter le signalement de sécurité sur « {id} » : {message}",
    ),
    # TF-0316 — une route REFUSÉE à l identité qui l a demandée. Ce n est PAS un défaut du produit :
    # la garde d autorisation fait précisément son travail. Il n y a rien à corriger dans le code,
    # il y a une identité à fournir — et personne d autre que l humain qui tient les comptes ne
    # peut la fournir. Classer ce constat en `manuelle_dev`/`development` enverrait un développeur
    # « corriger » une protection qui fonctionne.
    "acces-refuse-a-cette-identite": (
        "manuelle_utilisateur",
        "mep-config",
        "fournir une session du RÔLE qui a le droit de voir « {id} » "
        "(FORGE_TESTS_QUALIF_STORAGE_STATES = « role=chemin », virgule) puis `--reprendre` : la "
        "route existe et la garde d'autorisation la refuse à l'identité exercée ({message}). Ne "
        "PAS toucher au code : c'est la couverture de l'audit qui manque, pas la protection",
    ),
    # TF-0288 — l écart entre la source VERSIONNÉE et ce que la production SERT. La classe est
    # distincte de `lien-casse` et le destinataire aussi : ici le code est CORRECT, c est le
    # déploiement qui a dérivé. Le confondre avec un défaut de développement est exactement
    # l erreur qu'INS-0001 a coûtée — sans le bloc (b) de l'instruction, on aurait ajouté au
    # composant des entrées qu'il portait déjà. L'étape cible est donc `mep-config`, jamais
    # `development`, et le geste est un redéploiement, pas un correctif.
    "ecart-servi-versionne": (
        "manuelle_utilisateur",
        "mep-config",
        "REDÉPLOYER depuis la source versionnée : « {id} » — {message}. Ne PAS toucher au code : "
        "il porte déjà ce que le servi ne rend pas. Vérifier quel artefact la production "
        "exécute et d'où il vient (aucun agent ne peut le faire à la place de qui tient le "
        "déploiement)",
    ),
    # TF-0284 — parité entre locales. Le destinataire est le développeur : une route manquante
    # se construit, un menu incomplet se complète, un contenu servi dans la mauvaise langue est
    # un câblage de données à corriger. Aucun des trois ne se règle par un test de plus.
    "i18n": (
        "manuelle_dev",
        "development",
        "rétablir la parité entre locales sur « {id} » : {message}. Une locale publiée est une "
        "promesse faite au visiteur",
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
    "modele-non-epingle": (
        "manuelle_dev",
        "development",
        "épingler « {id} » sur une version datée (`nom-AAAAMMJJ`) là où le projet la désigne : "
        "un alias change le système sous test sans qu'aucun commit ne bouge, et la régression "
        "arrive un matin sans auteur ({message})",
    ),
    # TF-2110 — un test qui appelle le fournisseur LLM reel. Le remede est ecrit dans le code du
    # produit (un double HTTP qui verifie l adresse appelee) : ni derivable, ni arbitrage humain.
    "appel-fournisseur-llm-reel-dans-un-test": (
        "manuelle_dev",
        "development",
        "poser un double (`monkeypatch`, `respx`, `nock`, `msw`, `vi.mock`…) sous l'appel du "
        "fournisseur dans « {id} » : une suite qui appelle le fournisseur réel dépense des "
        "jetons à chaque exécution et dépend du réseau et d'une clé ({message})",
    ),
    # TF-0708 — la FORME de l ecran de creation. Ce n est pas une affordance inerte : tout est
    # cable, c est le motif qui manque. Et c est un arbitrage de conception, pas une correction
    # derivable : seul un humain sait si le formulaire porte des branches exclusives — donc
    # lequel des deux motifs est le bon. `manuelle_dev` / `design`, jamais `auto_ia`.
    "ecran-de-creation-sans-motif": (
        "manuelle_dev",
        "design",
        "choisir et poser l'un des DEUX motifs de creation sur « {id} » : formulaire replie "
        "(`<details>` + `data-cible`) si le formulaire est court et sans branche, panneau "
        "adressable (`?nouveau=…`) s'il porte des branches exclusives — le repli les MASQUE "
        "au lieu de les resoudre. Aucun agent ne peut trancher ce critere a la place de qui "
        "connait la tache ({message})",
    ),
    # TF-2269 — un test du projet est rouge. Le remède est dans le code ou le test du produit : ni
    # dérivable par la forge, ni un arbitrage humain. La couverture de ce pan se mesure à nouveau
    # dès que la suite repasse au vert.
    # TF-2286 — la suite e2e Playwright rouge rend la même classe (pan front) : même destinataire.
    "suite-du-projet-rouge": (
        "manuelle_dev",
        "development",
        "rendre la suite verte : « {id} » — {message}. Tant qu'un test échoue, aucune "
        "couverture n'est mesurée sur les pans qui lisent cette suite (backend : api, data, "
        "migrations, batch, fichiers ; e2e Playwright : front) ; rejouer l'audit une fois le "
        "test corrigé",
    ),
    # TF-2270 — le test attend la fin d'un traitement sans affirmer son résultat. La vérité de
    # référence (ce que le traitement DOIT produire) est connue du produit seul : le geste est
    # écrit par le développeur, avec son cas qui doit être refusé.
    "traitement-attendu-sans-resultat-assert": (
        "manuelle_dev",
        "development",
        "affirmer le RÉSULTAT du traitement attendu dans « {id} » : comparer son contenu à une "
        "vérité de référence connue d'avance, et jouer sa contre-épreuve (un jeu où le résultat "
        "attendu diffère doit échouer) — l'état terminal seul ne prouve rien ({message})",
    ),
    # TF-2229 — un réglage de plateforme exigé n'a pas la valeur du registre. La commande
    # d'application est écrite au registre : la voie automatique (loi n° 5) est de la rejouer, puis
    # de relire. Le jeton qui l'autorise relève de qui tient la plateforme.
    "reglage-plateforme-hors-attendu": (
        "auto_ia",
        "mep-config",
        "rejouer la commande `cmd_appliquer` du registre des réglages sûrs pour « {id} », puis "
        "relire avec `cmd_lire` et rejouer l'audit : {message}",
    ),
    # TF-2229 — l'écart accepté par le porteur n'est pas tenu tel que décidé, ou la décision manque.
    # Ni le registre ni la forge ne peuvent trancher : la décision est humaine (R-29).
    "reglage-decide-non-tenu": (
        "manuelle_utilisateur",
        "mep-config",
        "TRANCHER pour « {id} » : consigner la décision (appliquer le réglage, ou accepter l'écart "
        "avec sa valeur et son motif) ou rétablir l'état décidé : {message}",
    ),
    "sonde-muette": (
        "manuelle_utilisateur",
        "mep-config",
        "déclarer au projet ce que la sonde doit observer (FORGE_TESTS_APP=« module:attribut » "
        "dans `<projet>/.env.forge-tests`), puis `--reprendre` le rapport : la mesure est "
        "aveugle tant que la configuration manque ({message})",
    ),
    # TF-2285 — les 28 classes de constats qui sortaient « DÉFAUT D'AUDITEUR » faute de règle. Une
    # règle par classe de `classes.CLASSES` ; `tests/test_tf_2285_regles_par_classe.py` compare les
    # deux ensembles et devient rouge à la première classe déclarée sans suite.
    #
    # --- Revue statique de la suite de tests du projet (TF-0344 / TF-0345) ------------------------
    # Le correctif d'un faux vert s'écrit dans la suite du produit, et seul qui connaît l'écran ou
    # la route sait quelle assertion de présence ou quelle cible exacte poser : `manuelle_dev`.
    "faux-vert-absence-sans-presence": (
        "manuelle_dev",
        "tests-suite",
        "faire précéder l'assertion d'ABSENCE de « {id} » d'une assertion de PRÉSENCE sur le même "
        "écran : sur une page encore en chargement, rien n'est affiché parce que rien n'est encore "
        "là, et le test passe à vide ({message})",
    ),
    "faux-vert-motif-du-declencheur": (
        "manuelle_dev",
        "tests-suite",
        "resserrer le motif d'assertion de « {id} » pour qu'il ne puisse pas être satisfait par le "
        "libellé de l'élément cliqué avant toute action : le test est instable et attend son "
        "délai à chaque occurrence ({message})",
    ),
    "faux-vert-prefixe-d-un-chemin-valide": (
        "manuelle_dev",
        "tests-suite",
        "affirmer la cible EXACTE dans « {id} » (égalité, ou ensemble énuméré) : un préfixe est "
        "vert pour le comportement voulu comme pour le défectueux ({message})",
    ),
    "donnee-de-test-recopiee": (
        "manuelle_dev",
        "tests-suite",
        "ne garder qu'une source de la donnée de test recopiée (« {id} ») — fixture ou module "
        "partagé — : deux copies divergent sans qu'aucun test ne le dise ({message})",
    ),
    "trou-de-couverture-inter-suites": (
        "manuelle_dev",
        "tests-suite",
        "trancher pour « {id} » : ajouter à cette suite les assertions que ses suites sœurs "
        "portent, ou déclarer pourquoi la variante diffère. Trou SIGNALÉ, pas un échec : deux "
        "variantes peuvent différer légitimement ({message})",
    ),
    "session-fabriquee-hors-parcours-d-entree": (
        "manuelle_dev",
        "tests-suite",
        "obtenir la session de « {id} » par le parcours d'entrée réel (connexion, puis "
        "`storageState`) au lieu de l'écrire de toutes pièces dans le stockage : une session "
        "composée sur place ne rejoue pas ce que le navigateur désérialise ({message})",
    ),
    "cle-de-relecture-hors-du-stockage-de-la-session": (
        "manuelle_dev",
        "tests-suite",
        "ranger la clé qui permet de RELIRE la session au même endroit que la session persistée "
        "(« {id} ») : `storageState` ne sauvegarde pas le `sessionStorage`, la clé est perdue au "
        "rejeu ({message})",
    ),
    "saut-conditionnel-en-integration-continue": (
        "manuelle_dev",
        "tests-suite",
        "remplacer le saut conditionnel de « {id} » par un préalable garanti par le harnais, ou "
        "par un échec explicite qui nomme ce qui manque ; un saut inconditionnel et motivé reste "
        "licite ({message})",
    ),
    "assertion-de-test-executee-zero-fois": (
        "manuelle_dev",
        "tests-suite",
        "faire exécuter l'assertion de « {id} » : ajouter une assertion de non-vacuité sur la "
        "collection ou l'attente (≥ 1 itération), ou déclarer la boucle vide licite avec son "
        "motif. Un test qui n'exécute aucune assertion passe sans rien prouver ({message})",
    ),
    # --- Configuration de couverture : le chiffre avant la mesure (TF-0604) -----------------------
    "couverture-perimetre-non-declare": (
        "manuelle_dev",
        "tests-suite",
        "déclarer le périmètre de la couverture EN POSITIF (`include`, `source` ou "
        "`collectCoverageFrom`) dans « {id} » : sans lui, le dénominateur dérive à chaque fichier "
        "ajouté ou retiré et le chiffre n'est pas une mesure ({message})",
    ),
    "couverture-seuil-global-sans-seuil-par-fichier": (
        "manuelle_dev",
        "tests-suite",
        "ajouter un seuil PAR FICHIER (`perFile: true` ou l'équivalent de l'outil) dans « {id} », "
        "calé SOUS le niveau atteint et non dessus : un seuil global ne peut pas échouer sur un "
        "écran non testé ({message})",
    ),
    "couverture-fonctions-sans-seuil": (
        "manuelle_dev",
        "tests-suite",
        "poser un seuil sur les FONCTIONS à côté de celui sur les instructions dans « {id} » : "
        "une ligne couverte par un simple rendu ne prouve rien d'un geste utilisateur. Constat "
        "SIGNALÉ, non bloquant ({message})",
    ),
    # --- Matrice des droits (TF-0343 / TF-0342) ---------------------------------------------------
    # Deux classes, deux destinataires (TF-2294). La cellule manquante (refus ou succès), la matrice
    # illisible et l'absence de coexistence s'écrivent dans la suite du produit : le développeur.
    "matrice-des-droits": (
        "manuelle_dev",
        "tests-suite",
        "compléter la matrice des droits pour « {id} » : ajouter la cellule manquante (profil "
        "refusé ou profil autorisé) ou déclarer la garde ouverte à tous avec son motif ; un "
        "produit à rôles se vérifie sous une identité par rôle, pas sous une seule ({message})",
    ),
    # Le constat « rôle sans identité » (`qualif:multi-profils:identites-manquantes`) ne s'écrit
    # dans aucune suite : il demande un compte par rôle, que seul qui tient les comptes fournit.
    "identites-de-roles-manquantes": (
        "manuelle_utilisateur",
        "mep-config",
        "fournir une session par RÔLE déclaré pour « {id} » (FORGE_TESTS_QUALIF_STORAGE_STATES = "
        "« role=chemin », virgule) puis `--reprendre` : un produit à rôles n'est pas vérifiable "
        "sous une identité unique, et aucun agent ne peut ouvrir un compte à la place de qui "
        "les tient ({message})",
    ),
    # --- Instance servie et surface appelée (qualif, interface) -----------------------------------
    "etat-perdu-a-la-navigation": (
        "manuelle_dev",
        "development",
        "conserver l'état saisi sur « {id} » à travers l'aller-retour de navigation : le "
        "visiteur perd ce qu'il vient de remplir en ouvrant une autre page puis en revenant "
        "({message})",
    ),
    "destination-non-pertinente": (
        "manuelle_dev",
        "development",
        "aligner la destination réellement atteinte par « {id} » et l'attente déclarée pour cette "
        "affordance : corriger la cible, ou corriger la déclaration si c'est elle qui a dérivé "
        "({message})",
    ),
    "identifiants-affiches-dans-le-texte-servi": (
        "manuelle_dev",
        "development",
        "retirer de la page servie le couple identifiant / mot de passe affiché en texte (« {id} »)"
        " avant toute exposition publique, et tenir ce mot de passe pour exposé s'il ouvre un "
        "compte réel ({message})",
    ),
    "url-auto-referente-etrangere": (
        "manuelle_dev",
        "development",
        "corriger l'origine que la page publie d'elle-même (« {id} ») : elle est annoncée à tout "
        "tiers qui la lit. Si l'origine est légitime, la déclarer par "
        "FORGE_TESTS_QUALIF_ORIGINES ({message})",
    ),
    "parcours-persona-refuse-sous-son-identite": (
        "manuelle_dev",
        "development",
        "aligner le parcours du persona et les droits de son rôle pour « {id} » : une route que "
        "le parcours navigue est refusée à ce rôle, renvoie vers la connexion ou répond en erreur "
        "sur l'instance servie ({message})",
    ),
    "route-appelee-non-servie": (
        "manuelle_dev",
        "development",
        "enregistrer à l'hôte la route que le code client appelle (« {id} »), ou retirer l'appel : "
        "la requête rend 404 en service, c'est une fonction morte ({message})",
    ),
    "ressource-referencee-absente": (
        "manuelle_dev",
        "development",
        "livrer au build la ressource que la page référence (« {id} »), ou retirer la référence : "
        "le navigateur obtient 404 au moment où le repli devrait servir ({message})",
    ),
    # --- Pans spécialisés -------------------------------------------------------------------------
    "fournisseur-jetons-sans-identifiant": (
        "manuelle_dev",
        "development",
        "passer l'identifiant de l'identité assignée (`client_id` / `managed_identity_client_id`) "
        "au fournisseur de jetons de « {id} » : sans lui il résout l'identité SYSTÈME de l'hôte, "
        "ou échoue ({message})",
    ),
    # TF-0369 — le correctif est mécanique (passer la fonction, pas son résultat) et la source qui
    # fait foi, le constat lui-même, nomme l'appel. La contre-épreuve (un second enregistrement
    # porte un autre instant) reste à relire : `auto_ia` ne dit pas « sans relecture ».
    "defaut-evalue-a-l-import": (
        "auto_ia",
        "development",
        "passer la FONCTION et non son résultat à l'argument par défaut de « {id} » "
        "(`default=now`, ou `default_factory=`), puis vérifier que deux enregistrements "
        "successifs portent deux instants différents ({message})",
    ),
    # --- Supabase (TF-2008) -----------------------------------------------------------------------
    # Activer la RLS sans politique ferme l'accès : le gabarit dit quoi écrire, la politique qui
    # suit est un arbitrage du produit (qui lit, qui écrit) — `manuelle_dev`, pas `auto_ia`.
    "rls-absente": (
        "manuelle_dev",
        "development",
        "activer la RLS de « {id} » dans une migration (`alter table … enable row level "
        "security`) ET écrire les politiques qui disent qui lit et qui écrit : une table d'un "
        "schéma exposé sans RLS est lisible et modifiable par tout rôle qui a un droit dessus "
        "({message})",
    ),
    # Le correctif est la suppression d'une ligne que le constat désigne au fichier et à la ligne.
    "realtime-rls-reactivee": (
        "auto_ia",
        "development",
        "retirer de la migration (« {id} ») la ligne `alter table realtime.messages … enable row "
        "level security` : la RLS y est déjà active, la migration échoue en 42501 et arrête "
        "les politiques qui suivent ({message})",
    ),
    # --- Lots et déclencheurs (batch) -------------------------------------------------------------
    "job-sans-declencheur": (
        "manuelle_dev",
        "development",
        "câbler un déclencheur au traitement par lot (« {id} »), ou déclarer qu'il est enclenché "
        "hors du dépôt : sans l'un des deux, rien ne le fait tourner ({message})",
    ),
    "trigger-non-cable": (
        "manuelle_dev",
        "development",
        "pointer le déclencheur « {id} » vers une cible qui existe dans le dépôt, ou le retirer : "
        "le lot ne partira jamais et rien ne le signale au déploiement ({message})",
    ),
    "cron-invalide": (
        "manuelle_dev",
        "development",
        "corriger l'expression de planification « {id} » (5 ou 6 champs, ou un raccourci nommé) : "
        "illisible, la planification est silencieusement inopérante ({message})",
    ),
    # --- Défaut de l'outil (TF-1747) --------------------------------------------------------------
    # `forge` : le constat dit lui-même « défaut de l'outil ou de la désignation, pas du produit ».
    "enumeration-incomplete": (
        "manuelle_dev",
        "forge",
        "compléter l'énumération du pan (« {id} ») : des routes servies et déclarées au schéma "
        "manquent à l'inventaire, donc la couverture calculée ne mesure pas l'application. "
        "Vérifier d'abord la désignation FORGE_TESTS_APP du projet, puis l'énumération de la "
        "forge ({message})",
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


def _action_configuration(
    reference: str, portee: str, elements: set[str], champs: tuple[str, ...]
) -> dict:
    """Le geste « renseigner de la configuration », qu'il vaille pour un pan ou pour tous.

    Retour humain du 14/08 : la phrase précédente était incompréhensible (liste de 20
    variables en tête, grammaire cassée). Structure fixe : quoi faire → pourquoi → ce qu'on
    obtient. Les CHAMPS restent nommés (jamais leurs valeurs), mais en fin de phrase.

    TF-0381 (lot Produit-10 20260818b) : `elements` peut contenir des MARQUE-PLACES `pan:<x>`, posés
    quand un pan n a rien d énumérable. Les compter comme des éléments inventoriés faisait dire à
    l action « 1 élément(s) sont inventoriés » alors que le motif du même pan, deux champs plus
    haut dans le même rapport, annonçait « 0 elements INVENTORIES ». Le rapport se contredisait
    sur le même pan.
    """
    reels = {e for e in elements if not e.startswith("pan:")}
    pourquoi = (
        f"{len(reels)} élément(s) sont inventoriés mais aucune exécution ne pouvait "
        "les atteindre ici — manque de configuration, pas trou de couverture du projet. "
        "Vous obtiendrez : ces éléments mesurés au prochain audit, et le verdict PARTIEL "
        "pourra se prononcer."
        if reels
        else (
            "aucun élément n est inventorié sur ce périmètre — le pan est nommé pour n être pas "
            "tu, et la configuration est réclamée parce qu une TRACE D EXÉCUTION l a nommée. "
            "Vous obtiendrez : de quoi savoir s il y a quelque chose à mesurer."
        )
    )
    return {
        "finding_ref": reference,
        "categorie": "manuelle_utilisateur",
        "etape_cible": "mep-config",
        "attendu": (
            f"renseigner la configuration d'audit {portee} dans `<projet>/.env.forge-tests`, "
            f"puis relancer avec `--reprendre <rapport.json>`. Pourquoi : {pourquoi} "
            f"Champs à fournir ({len(champs)}) : "
            f"{', '.join(champs) or 'la configuration manquante'}"
        ),
        # R-48 (retour humain du 23/08) : une sollicitation dit pourquoi la reponse NE SE DEDUIT
        # PAS du contexte. Sans cette phrase, un lecteur ne distingue pas ce que l outil aurait pu
        # trancher seul de ce que lui seul peut fournir — et il apprend a survoler la liste.
        "non_deductible": (
            "ces valeurs sont des ACCES au systeme sous test — hote, jeton, entrepot, identifiant. "
            "Aucune information du depot ne permet de les deduire : deux personnes competentes "
            "n arriveraient pas a la meme valeur sans les avoir, et un defaut invente ferait "
            "mesurer autre chose que le produit. C est la seule categorie de manque que l outil ne "
            "peut pas combler de lui-meme"
        ),
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

    # Configuration absente : une action par ÉLÉMENT produirait des centaines de lignes
    # identiques pour un seul geste humain. Deux regroupements, et le second n'est pas un
    # confort de lecture.
    #
    # RT-8 (lot COMPTA du 14/08) : regrouper par pan ne suffit pas. Un élément de
    # configuration PARTAGÉ — typiquement une variable de `.env.example` que personne ne
    # revendique — est publié par CHACUN des pans qui l'a vu : 33 variables × 12 pans ont
    # donné 12 actions quasi identiques, qui noyaient l'onglet Actions du dashboard. Or
    # c'est UN geste : renseigner la variable une fois la sert partout. On agrège donc ce
    # qu'au moins deux pans réclament, en NOMMANT les pans concernés — sans quoi
    # l'agrégation ferait disparaître à qui le manque profite. Le détail par pan reste
    # intact au rapport (`non_testables`) : c'est la présentation du travail qui change,
    # jamais la mesure.
    # TF-0381 — LA COMBINAISON QUI NE MÈNE NULLE PART : aucun élément inventorié, et une
    # configuration seulement PRÉSUMÉE (déduite d un `.env.example` que nul adaptateur ne
    # revendique). Mesuré sur un projet d ANALYSE : dix actions manuelles, une par pan, toutes
    # réclamant les six mêmes variables Databricks — y compris pour `prompts` (0 prompt trouvé)
    # et `qualif` (qui attend une URL servie, pas un entrepôt). Une configuration réclamée pour
    # un pan inexistant use la crédibilité des actions qui, elles, comptent.
    #
    # L entrée RESTE au rapport (`non_testables`), avec son motif : ce qui disparaît est la
    # DEMANDE ADRESSÉE À UN HUMAIN, pas le constat. Nommer une limite n est pas réclamer un geste.
    def _mene_quelque_part(entree: dict) -> bool:
        return bool(entree.get("inventorie", True)) or entree.get("provenance") != "presume"

    exploitables = [e for e in (non_testables or []) if _mene_quelque_part(e)]
    vu_par: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    for entree in exploitables:
        cle = (str(entree.get("element") or ""), tuple(entree.get("champs_requis") or []))
        vu_par.setdefault(cle, set()).add(str(entree.get("pan") or ""))
    pans_non_testables = {pan for pans in vu_par.values() for pan in pans}

    partages: dict[tuple[str, ...], tuple[set[str], set[str]]] = {}
    propres: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    for (element, champs), pans in vu_par.items():
        if len(pans) > 1:
            elements_vus, pans_vus = partages.setdefault(champs, (set(), set()))
            elements_vus.add(element)
            pans_vus |= pans
        else:
            propres.setdefault((next(iter(pans)), champs), set()).add(element)

    for champs, (elements, pans) in sorted(partages.items()):
        portee = (
            f"partagée par {len(pans)} pans ({', '.join(sorted(pans))})"
            if len(pans) > 3
            else f"partagée par les pans {', '.join(sorted(pans))}"
        )
        actions.append(
            _action_configuration(
                f"{PREFIXE_NON_TESTABLE}partages:{'+'.join(champs)}", portee, elements, champs
            )
        )
    for (pan, champs), elements in sorted(propres.items()):
        actions.append(
            _action_configuration(
                f"{PREFIXE_NON_TESTABLE}{pan}:{'+'.join(champs)}",
                f"du pan « {pan} »",
                elements,
                champs,
            )
        )

    for entree in pans_non_couverts or []:
        pan = str(entree.get("pan") or "")
        chemin = str(entree.get("pour_couvrir") or "")
        # TF-2311 — une suite qui a dépassé son DÉLAI n est ni un défaut d auditeur ni un arbitrage
        # de conception : le geste est un réglage mécanique, que le motif chiffre (délai atteint,
        # valeur suggérée). Sans cette branche l action tombait en `manuelle_dev` / `forge`.
        if entree.get("cause") == "delai-depasse":
            actions.append(
                {
                    "finding_ref": f"{PREFIXE_PAN_NON_COUVERT}{pan}",
                    "categorie": "auto_ia",
                    "etape_cible": "mep-config",
                    "attendu": (
                        f"laisser à la suite du projet le temps de finir pour le pan « {pan} », "
                        f"aujourd'hui NON MESURÉ (DELAI_DEPASSE). Pourquoi : "
                        f"{entree.get('motif') or 'sans motif'}. Comment (vous obtiendrez le pan "
                        f"mesuré au prochain audit) : {chemin}"
                    ),
                }
            )
            continue
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
                # R-48 : la non-deductibilite depend du DESTINATAIRE, et la confondre serait
                # reproduire le defaut que ce bloc corrige plus haut.
                "non_deductible": (
                    "l acces au systeme sous test manque : aucun agent ne peut inventer un hote, "
                    "un jeton ou une base, et personne d autre que qui tient l environnement ne "
                    "peut les fournir"
                    if categorie == "manuelle_utilisateur"
                    else "ecrire la couverture d un pan est un ARBITRAGE de conception : quoi "
                    "mesurer, a quel niveau, avec quel cout de maintenance. Deux developpeurs "
                    "competents ne trancheraient pas identiquement, et l outil ne dispose pas de "
                    "l intention du projet"
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
