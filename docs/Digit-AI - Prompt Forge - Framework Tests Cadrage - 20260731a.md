# Prompt de cadrage — Forge Tests

> Prompt autoportant destiné à un agent d'exécution outillé (Claude Code).
> Tout copier-coller à partir de la ligne suivante.

---

## CONTEXTE

Je construis un accélérateur de tests, nom de travail **Forge Tests**, sur le modèle
d'un pipeline typé à gates (référence interne : SaaS Forge). Objectif de fond :
rendre la qualité d'un projet **vérifiable, reproductible et enrichissable dans le
temps**, sans dépendre de la mémoire d'un humain sur ce qu'il faut penser à vérifier.

Le framework doit s'appliquer à **n'importe quel projet**, construit ou non avec la
forge interne : aucun artefact de la forge n'est un prérequis d'entrée. Quand des cas
de tests ou jeux de données produits en amont existent, ils sont consommés comme
entrées **optionnelles et vérifiées**, jamais supposés suffisants.

---

## LIVRABLE ATTENDU DE CE TOUR — et rien d'autre

Un **CDC de cadrage en markdown**, nommé selon la convention
`Digit-AI - CDC Forge - Framework Tests - {AAAAMMJJ}{a,b,c…}.md` (date réelle du jour,
jamais codée en dur), contenant les **7 sections** ci-dessous.

**Aucune ligne de code, aucun skill, aucun test généré à ce stade.** Si tu es tenté de
produire du code, arrête-toi et signale-le.

---

## ENTRÉES

Déjà tranchées :

- **Cible d'exécution du premier adaptateur** : application web Python + JavaScript,
  base PostgreSQL, déploiement Railway.
- **Architecture** : noyau universel mince + adaptateurs par écosystème, avec
  couverture réellement atteinte **déclarée** et non masquée.
- **Degré d'autonomie** : autonomie sur le **diagnostic** (scan, priorisation,
  génération, exécution, preuve). La **correction** du code d'autrui se fait sous feu
  vert humain, sur branche dédiée.
- **Phase 1** : banc d'essai à défauts plantés (petit projet Python / JavaScript /
  PostgreSQL construit pour l'occasion), nécessaire de toute façon pour les fixtures.

À renseigner :

- **Projet réel de confrontation (phase 2)** : `[À RENSEIGNER — placeholder assumé]`
- **Accès disponibles** : `[dépôt / CI / base / environnement de recette]`
- **Régime des jeux de données** : `[synthétiques uniquement | prod anonymisée | à trancher]`
- **Budget de suite acceptable en CI** : `[durée max] / [nombre de tests max]`

Si une entrée marquée `[À RENSEIGNER]` manque et bloque, pose la question en liste
indicée a/b/c et **ne devine pas**.

---

## SECTION 0 — Autopsie des échecs constatés

Corpus de calibration documenté, **n = 1** :

> Sur un projet dont la suite de tests d'interface existait, les tests restaient
> uniquement sur les **premières pages** de l'application, sans atteindre les pages
> suivantes ni exercer tous les types de boutons et de fonctions.

Cause identifiée : **biais de disponibilité de l'agent générateur** — les tests sont
écrits depuis ce que l'agent a sous les yeux (le premier écran, le composant courant)
au lieu de partir d'un inventaire mécanique de la surface de l'application.

Conséquence de conception : le sens de la génération doit être **inversé** — énumérer
d'abord la surface depuis le code source, générer ensuite, mesurer le ratio couvert /
inventorié, échouer sous seuil.

Ce cas est la **première fixture rouge de recette** du framework : la recette doit
démontrer **par exécution** qu'il détecte ce trou.

**Limite assumée** : n = 1, un seul pan. Toute extension de cette classe aux autres
pans (API, Data, Batch, Fichiers) est une **hypothèse de conception**, à marquer comme
telle dans le CDC et jamais présentée comme un fait constaté.

Si tu disposes d'autres défauts réellement survenus, ajoute-les avec, pour chacun :
nature, pan, et raison précise pour laquelle la suite existante ne l'a pas attrapé.

---

## SECTION 1 — Inventaire exécuté du projet cible (obligatoire, en premier)

Ne rédige rien avant d'avoir **réellement inspecté** le projet : arborescence,
manifestes de dépendances, stack détectée, tests existants, pipeline CI, points
d'entrée (routes, endpoints, jobs, imports/exports de fichiers), schéma de base.

Restitue les **commandes exécutées et leurs sorties**.

Si tu n'as pas d'accès réel : écris `inventaire impossible — accès manquant` et
**arrête-toi**. Aucune stratégie ne se dérive d'un projet non inspecté.

---

## SECTION 2 — Frontière avec l'existant (décision structurante)

Pour chaque capacité visée — scan, modèle de risque, génération de cas, jeux de
données, exécution, correction, itération bornée, reporting, création d'adaptateurs —
statue : **RÉUTILISÉ** (quel composant existant), **ÉTENDU** (lequel, comment), ou
**CRÉÉ** (pourquoi rien d'existant ne couvre).

Composants à examiner nommément **s'ils sont présents dans l'environnement** :

- `quality-oracles` — registre d'oracles, fixtures rouge/verte, boucle bornée, profils
- `oracle-visual-diff` — régression visuelle par goldens, masques, seuil calibré
- `oracle-sast` — sécurité applicative
- `audite-et-corrige-l-appli` — cycle détecter → corriger → redéployer
- `karpathy-coding-discipline` — chirurgie du code, anti-drive-by
- `data-quality-auditor` — qualité de données (≠ tests logiciels : deux disciplines)
- `write-an-oracle` / `write-an-expert` — scaffolders transactionnels, patron de
  registre à statuts `todo` / `ok`

**Règle dure** : toute capacité classée CRÉÉ sans justification de non-recouvrement
est un défaut de conception, pas une fonctionnalité.

Recouvrements déjà identifiés à confirmer ou infirmer par inspection :
régression visuelle → ÉTENDU ; qualité de données → RÉUTILISÉ ; sécurité applicative →
RÉUTILISÉ ; scaffolder d'adaptateur → ÉTENDU (même patron que les deux scaffolders
existants).

---

## SECTION 3 — Modèle de risque, contre-oracles, critères d'arrêt

### 3.1 Remplacer l'exhaustivité par la couverture du risque

L'exhaustivité des tests est **impossible par principe** (explosion combinatoire) :
elle ne peut pas être un objectif. Lui substituer une cotation
**criticité métier × probabilité de défaillance × coût de détection tardive**,
appliquée aux pans Back, Front, API, Data, Batch, Fichiers, plus les axes non
fonctionnels (performance, sécurité, résilience et reprise, accessibilité si UI).

### 3.2 Doublet de contre-oracles — jamais un seul

| Question | Contre-oracle | Défaut attrapé |
|---|---|---|
| A-t-on **atteint** tout ce qui existe ? | Couverture de **surface** | Parcours tronqué, éléments jamais exercés |
| Ce qu'on atteint, le **vérifie**-t-on ? | Score de **mutation** | Assertion faible, doublure trop permissive |

**Règle dure** : un score de mutation calculé sans couverture de surface mesurée est
un indicateur trompeur — il se calcule sur le seul périmètre atteint et flatte
d'autant plus que la suite est incomplète. Il ne peut jamais être publié seul.

### 3.3 Inventaire de surface obligatoire, par pan

| Pan | Surface à énumérer |
|---|---|
| Front | routes, écrans, éléments interactifs, états |
| API | endpoints × méthodes × codes de retour (succès **et** erreurs) |
| Data | tables, colonnes, contraintes, migrations |
| Batch | branches de traitement, codes de rejet, chemins de reprise |
| Fichiers | formats, encodages, séparateurs, cas limites |

Tout élément inventorié et non exercé est un **FAIL nommé**, jamais une absence
silencieuse.

### 3.4 Seuils chiffrés (à proposer, puis à faire valider)

- Ratio cible unitaire / intégration / E2E — pyramide assumée, pas subie
- Score de mutation cible sur le périmètre critique
- Taux de couverture de surface minimal, par pan
- **Taux de détection du corpus section 0 : cible 100 %** — critère d'acceptation du
  framework, pas indicateur de confort
- Durée maximale de suite en CI et budget de tests par pan
- Taux de tests instables toléré + politique de quarantaine

Chaque test porte un **lien de traçabilité** vers le risque ou l'exigence qu'il
couvre ; un test sans lien est supprimable.

---

## SECTION 4 — Architecture

### 4.1 Trilemme tranché

Universel × exhaustif × autonome ne peuvent pas être tenus ensemble. Sortie retenue :
**noyau universel mince + adaptateurs par écosystème**.

- **Le noyau** porte ce qui est indépendant de la stack : modèle de risque,
  traçabilité test → risque, critères d'arrêt, boucle bornée, doublet de
  contre-oracles, reporting, référentiel de tests versionné.
- **Les adaptateurs** portent la profondeur d'exécution.
- Le niveau de couverture réellement atteint dépend de l'existence de l'adaptateur :
  cette limite est **déclarée dans le rapport**, jamais masquée par un vert global.
  Un projet sans adaptateur produit un diagnostic **partiel explicitement marqué**.

### 4.2 Contrat d'adaptateur — 5 capacités

Un adaptateur = un couple **(pan × technologie)** fournissant :

1. **Inventaire de surface** — énumérer mécaniquement ce qui existe à tester
2. **Génération de cas** — dériver depuis la surface et le modèle de risque
3. **Harnais d'exécution** — lancer, isoler, nettoyer ; déterminisme imposé (graine
   figée, horloge figée, indépendance à l'ordre)
4. **Fabrique de données** — fixtures, seeding, teardown, cas limites
5. **Contre-oracle** — surface et/ou mutation selon le pan

**Loi d'admission** : *un adaptateur qui ne sait pas énumérer sa surface n'est pas un
adaptateur.* Admission conditionnée à une **paire de fixtures** — projet-jouet à
défaut planté (doit être détecté) et projet sain (ne doit pas être signalé).

### 4.3 Socle initial — 18 adaptateurs

Outillages **indicatifs**, à confirmer par inspection au moment du CDC. P1 = première
vague, alignée sur la stack cible.

| # | Pan | Adaptateur | Outillage indicatif | Prio |
|---|---|---|---|---|
| 1 | Front | Navigateur E2E + crawl de surface | Playwright | P1 |
| 2 | Front | Composants JS/TS | Vitest ou Jest + Testing Library | P1 |
| 3 | Front | Accessibilité | axe-core | P2 |
| 4 | Front | Régression visuelle | ÉTENDU depuis l'oracle de goldens existant | P2 |
| 5 | API | Contrat REST depuis OpenAPI | Schemathesis | P1 |
| 6 | API | Contrat consommateur ↔ fournisseur | Pact | P3 |
| 7 | API | GraphQL par schéma | — | P3 |
| 8 | Back | Unitaire Python | pytest | P1 |
| 9 | Back | Unitaire JS/TS | Vitest ou Jest | P1 |
| 10 | Back | Mutation Python | mutmut ou cosmic-ray | P1 |
| 11 | Back | Mutation JS/TS | Stryker | P2 |
| 12 | Data | Base relationnelle éphémère | Testcontainers + PostgreSQL | P1 |
| 13 | Data | Migrations (aller/retour, rejeu) | Alembic ou équivalent | P1 |
| 14 | Data | Qualité de données | RÉUTILISÉ : auditeur de qualité de données | P2 |
| 15 | Batch | Jobs et workers — idempotence, rejeu, reprise | — | P2 |
| 16 | Fichiers | Import/export — encodages, séparateurs, volumétrie, rapprochement de totaux | — | P2 |
| 17 | NF | Charge et performance | k6 ou Locust | P3 |
| 18 | NF | Sécurité applicative + dépendances | RÉUTILISÉ : oracle SAST ; + SCA | P2 |
| 19 | Transverse | Environnement éphémère & CI | conteneurs, base jetable, Railway | P1 |

**À vérifier avant de figer #19** : les capacités exactes de Railway en matière
d'environnements éphémères par pull request — à lire dans la documentation courante,
jamais à supposer.

### 4.4 Création d'adaptateurs à la demande, et contribution en retour

Scaffolder **transactionnel** calqué sur les scaffolders existants de la forge :
toutes les validations avant toute écriture, un refus ne laisse aucune modification
partielle. Registre versionné, statuts `todo` / `ok`.

Un adaptateur né sur un projet client reste **local en statut `todo`** ; il ne rejoint
le socle qu'après rejeu de sa paire de fixtures.

### 4.5 Reste à préciser

Environnements d'exécution (local, CI, conteneur, base éphémère, doublures vs
sandbox), spécificités Batch et Fichiers, format de persistance du référentiel de
tests (versionné, complétable, avec journal de décisions), format du rapport lisible
par un humain — pas seulement un vert/rouge.

---

## SECTION 5 — Garde-fous (non négociables)

- **Lecture seule par défaut** sur le code du projet. Toute écriture se fait sur une
  branche dédiée, jamais sur la branche principale, et sous feu vert humain.
- **Interdiction du test-fitting** : ne jamais assouplir une assertion ni modifier le
  code testé pour faire passer un test rouge, sans justification écrite et tracée.
- **Boucle de correction bornée à 3 itérations.** Au-delà : livrer avec la liste des
  écarts résiduels — jamais boucler indéfiniment.
- **Aucune donnée de production non anonymisée** dans les jeux d'essai.
- **Aucun chiffrage, aucun TJM, aucun montant inventé** — placeholder si nécessaire.
- Toute donnée affichée trace à une **source citée ou à un calcul rejoué**, sinon elle
  est marquée « à vérifier ».
- L'autonomie porte sur le **diagnostic**, pas sur l'écriture dans le code d'autrui —
  condition de déployabilité en contexte client.

---

## SECTION 6 — Plan phasé et gates

Pour chaque phase : objectif, livrable, **critère de sortie binaire**, oracle de
vérification, checkpoint humain requis ou non.

- **Phase 1 — banc d'essai à défauts plantés.** Périmètre restreint. Construire le
  projet-jouet Python / JavaScript / PostgreSQL, y planter le défaut de la section 0
  (et ses frères hypothétiques par pan), démontrer par exécution que le framework les
  détecte. Critère de sortie : 100 % du corpus section 0 détecté.
- **Phase 2 — confrontation à un projet réel** non conçu pour le framework.
  `[projet à désigner]`
- Phases suivantes : à proposer.

Aucune généralisation avant preuve d'exécution en phase 1.

---

## CONTRAT DE SORTIE — le CDC est refusé s'il manque un seul point

1. Les 7 sections (0 à 6) sont présentes et non vides.
2. La section 1 contient des **commandes réellement exécutées et leurs sorties**, ou
   la mention explicite d'inventaire impossible.
3. Chaque capacité de la section 2 porte un verdict **RÉUTILISÉ / ÉTENDU / CRÉÉ** avec
   justification nommant le composant examiné.
4. La section 3 ne contient **aucun objectif de volume brut** et fournit au moins
   **6 seuils chiffrés**.
5. Les deux contre-oracles sont présents et distincts ; la règle d'interdiction du
   score de mutation publié seul est reprise.
6. La section 4 distingue explicitement noyau et adaptateurs, et déclare la limite de
   couverture en l'absence d'adaptateur.
7. Aucun critère subjectif (« optimal », « exhaustif », « robuste », « de qualité »,
   « complet ») n'apparaît comme critère de succès ; chaque critère est binaire ou
   chiffré.
8. Les hypothèses non constatées sont marquées comme telles, distinctes des faits.
9. **Zéro ligne de code produite.**
10. Les questions ouvertes sont regroupées **en fin de document**, en liste indicée
    a/b/c, une par ligne, avec option recommandée et défaut appliqué en l'absence de
    réponse.

---

## PROTOCOLE DE TESTS DU LIVRABLE

Le CDC est un document : l'oracle est le **contrat de sortie ci-dessus**, vérifié
point par point avant remise — présence des sections, comptage des seuils chiffrés,
recherche des mots-clés subjectifs interdits, absence de bloc de code, présence des
verdicts de frontière.

**Jeu d'essai** : (1) cas nominal — projet accessible et inspecté ; (2) cas limite —
projet sans aucun test existant ; (3) cas limite — accès au dépôt indisponible, qui
doit produire un **arrêt déclaré** et non un CDC inventé.

**Boucle** : générer → vérifier contre le contrat → corriger. **3 itérations
maximum** ; au-delà, livrer avec les écarts résiduels listés.

**Composition, pas duplication** : si les skills `quality-oracles` ou `la-boucle` sont
disponibles dans l'environnement, leur déléguer la vérification et l'itération plutôt
que de les réimplémenter.
