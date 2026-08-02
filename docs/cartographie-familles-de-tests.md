# Cartographie des familles de tests — ce que Forge Tests sait faire, et ce qu'il ne sait pas

**Date** : 2026-08-02 · **Source de l'état** : exécution de `forge-tests` sur la paire de bancs.

Ce document répond à une question que le registre de dette **ne peut pas** trancher. Le registre
recense des *limites de mesure* ; il ne contient aucune famille de tests. Le vider entièrement
laisserait les tests de charge, de contrat consommateur et d'accessibilité exactement où ils sont
aujourd'hui : absents.

## Taxonomie retenue, et pourquoi

**Les quadrants d'Agile Testing** (Brian Marick, repris par Crispin & Gregory), croisés avec la
pyramide pour l'axe de granularité.

Motif du choix : cette taxonomie sépare les tests selon deux axes — *technique / métier* et
*soutien à l'équipe / critique du produit*. C'est exactement la ligne de partage entre ce qu'un
outil automatique peut porter et ce qu'il ne portera jamais. La pyramide seule (unitaire /
intégration / bout en bout) ne dit rien des tests non fonctionnels ni des tests exploratoires,
et l'aurait donc laissée invisible.

---

## Q1 — Technique · soutien à l'équipe · automatisé

| Famille | État | Adaptateur porteur | Ce qui manque |
|---|---|---|---|
| Unitaire Python | **partielle** | #8, non construit | La suite est exécutée et mutée, mais **aucun inventaire de la surface unitaire** : ni fonctions, ni branches par module. On mesure la force des assertions sans savoir ce qui n'est pas testé du tout |
| Unitaire JS/TS | **absente** | #9 | Rien. Le pan JavaScript n'a aucun adaptateur |
| Intégration de composants | **absente** | — | Aucun inventaire des points de jonction entre modules |

---

## Q2 — Métier · soutien à l'équipe · automatisé et manuel

| Famille | État | Adaptateur porteur | Ce qui manque |
|---|---|---|---|
| Fonctionnel API | **couverte** | #5 `api-fastapi` | Inventaire depuis OpenAPI, couverture par sonde ASGI, génération partielle. La famille la mieux servie |
| Fonctionnel UI | **partielle** | #1 `front-react` | Inventaire statique des routes et éléments ; couverture encore **textuelle**. Manque un crawl navigateur |
| Données et migrations | **couverte** | #12, #13 | Inventaire migrations + ORM, couverture par violations réellement levées, migrations par exécution |
| Batch | **partielle** | #15 `batch-python` | Branches par AST + exécution. Manquent les branches implicites (ternaire, court-circuit) |
| Fichiers | **partielle** | #16 `fichiers-python` | Chemins de parsing par AST + exécution. Une variante sans branche dédiée reste invisible |
| **ATDD / exemples métier** | **absente** | — | **Le mur du générateur.** Produire un cas pour un code 400 ou 409 exige des invariants métier que ni le schéma ni le code ne déclarent. C'est la famille qui bloque le passage du diagnostic à la complétion |

---

## Q3 — Métier · critique du produit · manuel par nature

| Famille | État | Position assumée |
|---|---|---|
| Exploratoire | **hors périmètre** | Un outil qui énumère mécaniquement ne peut pas explorer : l'exploration est la recherche de ce qu'on n'a pas pensé à inventorier |
| Utilisabilité | **hors périmètre** | Aucun instrument automatique n'en juge |
| Recette utilisateur, alpha/bêta | **hors périmètre** | Relève de la décision humaine |

**À déclarer au produit, pas à construire.** Ce quadrant entier est une limite définitive de
Forge Tests. La promesse « assurer une qualité de produit exceptionnelle » bute ici : la moitié
métier de la critique du produit n'est pas automatisable, et aucun tour de boucle ne la rendra
telle.

---

## Q4 — Technique · critique du produit · outillé

| Famille | État | Ce qui existe déjà, ailleurs |
|---|---|---|
| Performance et charge | **absente** | #17 (k6 ou Locust) non construit |
| Sécurité applicative | **réutilisable, non câblée** | `oracle-sast.mjs`, `oracle-sca.mjs`, `oracle-secrets.mjs` du registre `quality-oracles` — exécutables aujourd'hui, jamais invoqués par Forge Tests |
| Accessibilité | **réutilisable, non câblée** | `oracle-a11y.py`, idem |
| Régression visuelle | **réutilisable, non câblée** | `oracle-visual-diff.py`, idem |
| Résilience et reprise | **partielle** | La branche de reprise du batch est inventoriée ; aucun test de panne, de coupure ni de rejeu sous erreur |
| Contrat consommateur ↔ fournisseur | **absente** | #6 (Pact) non construit |

---

## Ce que cette carte dit, et que le registre de dette ne disait pas

**Trois familles sont couvertes sur seize.** API, Données, et le contre-oracle de mutation.

**Quatre familles sont déjà outillées ailleurs et attendent un câblage, pas une construction.**
Sécurité, dépendances, accessibilité, régression visuelle : les oracles existent, sont exécutables,
et sont référencés au registre `quality-oracles`. Les brancher est le meilleur rapport valeur/effort
du produit — et **aucune entrée du registre de dette ne le mentionne**, parce que ce n'est pas une
limite de mesure : c'est une capacité qui n'a jamais été appelée.

**Un quadrant entier est hors de portée par nature.** Q3 — exploratoire, utilisabilité, recette.
Ce n'est pas un manque à combler, c'est une frontière à déclarer.

**Et le vrai verrou n'est pas dans le registre non plus** : l'absence d'ATDD, c'est-à-dire de
source d'invariants métier. C'est elle qui plafonne le générateur, qui interdit de produire les
cas 400 et 409, et donc qui empêche de passer du diagnostic à la complétion.

## Conséquence pour la conduite du projet

Vider le registre de dette ne fera avancer aucune des quatre lignes ci-dessus. Ce sont deux
chantiers distincts :

| Instrument | Ce qu'il pilote |
|---|---|
| `registre-dette.json` | La **fiabilité** de ce que le framework mesure déjà |
| Cette cartographie | L'**étendue** de ce qu'il mesure |

Un framework parfaitement fiable sur trois familles sur seize reste un framework qui couvre trois
familles sur seize.
