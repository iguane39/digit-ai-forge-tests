# CDC de cadrage — Forge Tests

**Référence** : Digit-AI - CDC Forge - Framework Tests - 20260802a
**Date** : 2026-08-02
**Entrant** : `input/Digit-AI - Prompt Forge - Framework Tests Cadrage - 20260731a.md`
**Statut** : cadrage. Aucune ligne de code produite à ce stade.

---

## Avertissement de lecture — faits, hypothèses, non vérifié

Trois marqueurs sont employés dans tout le document et jamais mélangés :

| Marqueur | Sens |
|---|---|
| **[FAIT]** | Constaté par inspection ou exécution, avec la trace en section 1 |
| **[HYP]** | Hypothèse de conception, non constatée — à confirmer ou infirmer par exécution |
| **[NV]** | Non vérifié à ce jour, faute d'accès ou de source consultée |

---

## Journal des décisions

Décisions prises par l'opérateur, reportées dans les sections concernées. Les questions correspondantes sont closes en fin de document.

| Id | Date | Décision | Sections impactées |
|---|---|---|---|
| **D-A** | 2026-08-02 | **La SaaS Forge construit Forge Tests**, en mode brownfield sur un dépôt initialisé à part. Le mode greenfield est écarté (verrou V-3) | 4.4, 6 phase 0, question (e) close |
| **D-B** | 2026-08-02 | **Le verrou V-1 est levé** : priorité donnée au manifeste `.forge/profile.toml` dans `select_onramp`, avant l'appel à `detect_stack` | 6 phase 0, question (f) close |
| **D-C** | 2026-08-02 | **Les adaptateurs #15 (Batch) et #16 (Fichiers) entrent en phase 1.** Le corpus de la section 0 couvre les pans Batch et Fichiers ; le critère S-01 à 100 % les rend nécessaires. Restreindre le corpus à la vague P1 aurait reproduit D-01 au niveau du framework — mesurer la couverture sur ce qu'on a choisi de couvrir | 4.3, 6 phase 1 |
| **D-D** | 2026-08-02 | **Forge Tests vit dans un dépôt dédié**, distinct de `digit-ai-saas-forge`. Visibilité non précisée à ce jour → **privé par défaut**, à confirmer | 4.4, question (k) close |
| **D-E** | 2026-08-02 | **Le correctif V-1 s'applique sur une branche dédiée avec pull request** sur `digit-ai-saas-forge`, jamais sur la branche principale — garde-fou G-1 appliqué à la forge elle-même | 6 phase 0, question (n) close |
| **D-F** | 2026-08-02 | **Montage B retenu** : Forge Tests est un produit autonome, doté de sa propre interface en ligne de commande, que la SaaS Forge invoque. Il n'est pas un module de `conductor/gates/` | 4.4, question (j) close |
| **D-G** | 2026-08-02 | **L'angle mort JavaScript de la phase 1 est accepté et déclaré** : #2, #9 et #11 restent hors périmètre de phase 1. Le rapport de phase 1 marque le pan comme partiellement instrumenté plutôt que d'élargir le périmètre pour faire disparaître la limite | 6 phase 1, question (l) close |
| **D-H** | 2026-08-02 | **Le contrat de sortie du présent CDC est outillé en oracle rejouable**, au standard de `quality-oracles` via `write-an-oracle`. Décision de l'opérateur, contraire à la recommandation formulée — le contrôle manuel des 10 points n'est pas reproductible, et le patron a vocation à servir aux CDC suivants | Protocole de vérification, question (m) close |

---

## SECTION 0 — Autopsie des échecs constatés

### 0.1 Corpus de calibration documenté

Corpus réel : **n = 1**. Un seul défaut est constaté ; tout le reste de cette section en dérive par hypothèse.

| Champ | Contenu |
|---|---|
| **Identifiant** | D-01 |
| **Statut** | **[FAIT]** — rapporté par l'opérateur, non rejoué à ce jour |
| **Pan** | Front |
| **Nature** | Suite de tests d'interface existante, restée sur les premières pages de l'application. Pages suivantes jamais atteintes ; types de boutons et de fonctions jamais tous exercés |
| **Pourquoi la suite existante ne l'a pas attrapé** | La suite *est* le défaut. Elle ne portait aucune mesure de ce qu'elle n'atteignait pas : l'absence de couverture ne produisait aucun signal rouge, seulement un silence vert |
| **Cause** | Biais de disponibilité de l'agent générateur — les tests sont écrits depuis ce que l'agent a sous les yeux (premier écran, composant courant) et non depuis un inventaire mécanique de la surface |
| **Conséquence de conception** | Le sens de la génération est inversé : énumérer la surface depuis le code source, générer ensuite, mesurer le ratio couvert / inventorié, échouer sous seuil |

D-01 est la **première fixture rouge de recette** du framework. Le critère d'acceptation de la phase 1 est sa détection **par exécution**, pas par relecture.

### 0.2 Extension aux autres pans — hypothèses, pas constats

Aucun défaut réel n'est documenté sur les pans API, Data, Batch, Fichiers. Les entrées ci-dessous sont des **frères hypothétiques** de D-01 : même mécanisme causal supposé, aucun cas rapporté. Elles servent à construire les fixtures rouges de la phase 1, jamais à justifier une affirmation sur l'existant.

| Id | Pan | Défaut supposé | Mécanisme supposé | Statut |
|---|---|---|---|---|
| H-02 | API | Endpoints testés en succès seulement ; codes d'erreur jamais exercés | L'agent teste le chemin qu'il vient d'écrire, pas la table des codes de retour | **[HYP]** |
| H-03 | API | Méthodes secondaires (PATCH, DELETE, HEAD) d'une route testée en GET/POST jamais atteintes | Disponibilité : la méthode sous les yeux est celle testée | **[HYP]** |
| H-04 | Data | Contraintes (unicité, clé étrangère, non-nullité) jamais violées volontairement | Les tests exercent le cas passant, pas le rejet attendu | **[HYP]** |
| H-05 | Data | Migrations testées à l'aller, jamais au retour ni en rejeu | La migration est vue comme un acte unique, pas comme une fonction réversible | **[HYP]** |
| H-06 | Batch | Branches de rejet et chemins de reprise jamais parcourus | Le job est testé sur son cas nominal, le rejet est un cas « rare » | **[HYP]** |
| H-07 | Fichiers | Un seul encodage, un seul séparateur, un seul volume testés | L'échantillon disponible devient l'univers testé | **[HYP]** |
| H-08 | Transverse | Assertions présentes mais permissives (statut 200 vérifié, contenu non vérifié) | Le test passe, donc il est réputé tester | **[HYP]** |

**Limite assumée, non contournée** : n = 1, un seul pan. Le taux de détection de 100 % exigé en phase 1 porte sur un corpus dont 7 entrées sur 8 sont fabriquées. Un corpus fabriqué démontre que le framework détecte ce qu'on lui a appris à détecter ; il ne démontre pas qu'il détecte ce qu'on n'a pas imaginé. Ce point est repris en section 6 comme limite de la preuve de phase 1.

---

## SECTION 1 — Inventaire exécuté

### 1.1 Périmètre de l'inventaire — et ce qui est déclaré impossible

Deux objets distincts doivent être inventoriés. Un seul l'a été.

| Objet | Statut |
|---|---|
| **Environnement de construction** (les deux forges disponibles) | **Inventorié par exécution** — commandes et sorties en 1.2 à 1.4 |
| **Projet cible de confrontation, phase 2** | **Inventaire impossible — projet non désigné.** Aucune stratégie de la phase 2 n'est dérivée dans ce CDC |
| **Projet cible de la phase 1** (banc d'essai à défauts plantés) | **Inexistant à ce jour** — il est à construire, c'est le livrable de la phase 1 |

Le répertoire de travail `c:\dev\Digit-AI - SaaS Tests` ne contient que `input/`. Il n'y a donc pas de projet cible à inspecter, et aucune section de ce CDC ne prétend en décrire un.

### 1.2 Commande — état du répertoire de travail

Commande : `ls -la "c:/dev/Digit-AI - SaaS Tests"`

> drwxr-xr-x 1 Sébastien 197609 0 Aug 2 14:07 .
> drwxr-xr-x 1 Sébastien 197609 0 Aug 2 14:07 input

**[FAIT]** Un seul sous-répertoire, `input/`, contenant le prompt de cadrage. Aucun code, aucun test, aucun manifeste de dépendances, aucun pipeline CI.

### 1.3 Commandes — inventaire de la SaaS Forge

Commande : `git clone --depth 1 https://github.com/iguane39/digit-ai-saas-forge.git`

> Cloning into 'saas-forge'... (succès)

Commande : `git log -1 --format="%H %ad %s" --date=short`

> 20f3f0a5c564e3351759ba5faa7ca0ac8383cd57 2026-07-09 feat(onramp): résolution de profil générique — toute techno sans énumération (P-14…P-18) (#38)

Commande : `find . -path ./.git -prune -o -type f -print | wc -l`

> 183

Commande : `find digitai-saas-forge/conductor -name "*.py" | wc -l` puis `find digitai-saas-forge/tests -name "test_*.py" | wc -l` puis comptage des lignes du conductor

> 49 fichiers Python dans `conductor/`
> 45 fichiers de tests dans `tests/`
> 3 788 lignes dans `conductor/`

Commande : `ls digitai-saas-forge/targets`

> fastapi-saas

Commande : `grep -n "name:|run:" .github/workflows/double-gate.yml`

> Install uv · uv sync --dev · Ruff (lint) : uv run ruff check . · Mypy (strict) : uv run mypy · Pytest : uv run pytest · design.md lint (JSON) · Politique de sévérité (gate bloquant) : uv run python -m conductor.gates.design\_gate findings.json

Commande : `which uv`

> uv ABSENT

**[FAIT]** — Ce qui est établi par cette inspection :

- La forge est un **conducteur** de 3 788 lignes qui séquence des moteurs tiers épinglés et non forkés : BMAD-METHOD (planification), bmad-autonomous-development (développement autonome, un worktree git par story), full-stack-fastapi-template (cible de scaffold), `@google/design.md` (lint de design).
- Chaîne typée **A → E** : cadrage (`cadrage.py`) → scaffold-first (`scaffold.py`) → pont BMAD (`bmad_bridge.py`) → configuration de sprint (`sprint_config.py`) → supervision (`supervisor.py`). Contrats en modèles Pydantic dans `contracts.py`.
- **Double gate** : gate code (`gates/code_gate.py`, délégation à la commande de test du profil) et gate design (`gates/design_gate.py`, politique de sévérité bloquante), plus un **gate de non-régression** (`gates/regression_gate.py`) qui bloque tout check passé de vert à rouge par rapport à une baseline capturée à l'entrée.
- **Deux points de validation humaine** : `governance.py` lève `HitlPending` (une pause, pas un échec) ; `BadConfig.auto_pr_merge` est typé `Literal[False]` et `SprintReport.merged` est verrouillé à `False`. Le merge autonome est interdit par le typage, pas par convention.
- **Remédiation bornée** : `supervisor.py` porte `GATE_MAX_RETRIES = 3`, puis escalade.
- **Registre de findings persistant** : `findings.py` écrit un `SPEC_FINDINGS.md` à statut `traité` / `non-traité`, rien n'est effacé.
- **Conformité au spec** : `contracts.py:SpecVerdict` distingue `under-build` (critère d'acceptation non tenu — bloquant) de `over-build` (comportement non demandé — consultatif).
- **Dégradation déclarée** : `profiles.py:TargetProfile.enforceable` expose la part du contrat réellement applicable ; `onramp/base.py:Substrate.declared_degradation` porte la liste des limites, et chaque onramp l'alimente.
- **Résolution de profil en cascade** (`profiles.py:resolve_profile`) : ① manifeste opposable `.forge/profile.toml` → ② profil curé → ③ inférence depuis les capacités détectées → ④ analyse LLM en opt-in. Chaque résolution porte un niveau de confiance (`curated` / `manifest` / `inferred` / `analyzed`).
- **Exécution portable** : `process.py` impose `list[str]`, résolution par `shutil.which`, `shell=False`, timeout borné.
- Un seul target existe : `fastapi-saas`. **[FAIT]**
- La suite de tests **n'a pas été exécutée** : `uv` est absent de la machine. La mention « les deux gates verts sur GitHub Actions » du README est **déclarée par le dépôt, non rejouée ici**. **[NV]**

### 1.4 Commandes — inventaire de la forge de skills

Commande : `ls -d */ | wc -l` dans `~/.claude/skills`

> 30

Commande : `ls quality-oracles/scripts/oracle-*.* | wc -l`

> 25

**[FAIT]** — 30 skills montés, 25 oracles CLI exécutables. Le registre `quality-oracles/references/registre-oracles.md` est en version 2.6.0 et porte des statuts (`exécutable` / `partiel` / `manuel` / `à outiller` / `dormant` / `broken`). Sont présents et exécutables : `oracle-sast.mjs`, `oracle-sca.mjs`, `oracle-secrets.mjs`, `oracle-visual-diff.py`, `oracle-a11y.py`, `oracle-code.mjs`, `oracle-perf.mjs`. L'orchestrateur `run-oracles.mjs` porte un contrôle de couverture et écrit un journal ; `self-test.mjs` rejoue toutes les paires de fixtures rouge / verte.

Le scaffolder `write-an-oracle/scripts/scaffold-oracle.mjs` est **transactionnel** : toutes les validations avant toute écriture, refus en code de sortie 2, sauvegarde `.bak` des fichiers modifiés, aucune modification partielle.

**Écart relevé** : le registre déclare le skill `data-quality-auditor` en statut exécutable, mais ce skill **n'est pas présent** dans les 30 skills montés. Référence non résolue. **[FAIT]**

### 1.5 Trois verrous relevés par inspection du code

Ces trois points sont des **faits de code**, pas des opinions. Ils conditionnent la section 2.

**V-1 — Le manifeste opposable est court-circuité pour tout dépôt Python.**
`onramp/detect.py:detect_stack` classe en stack `fastapi` tout dépôt portant un `pyproject.toml` à la racine. `onramp/__init__.py:select_onramp` route alors vers `NoOnramp` ou `AdapterOnramp` **sans jamais appeler `resolve_profile`**. Or `resolve_profile` est le seul point où le manifeste `.forge/profile.toml` est lu. Conséquence : un outil Python sans interface déclarant `has_ui = false` par manifeste se voit tout de même appliquer le profil `FASTAPI_SAAS`, codé en dur dans `no_onramp.py` et `adapter_onramp.py`, avec `has_ui = True`. **[FAIT]**

**V-2 — La normalisation greffe un système de design non demandé.**
`onramp/adapter_onramp.py` écrit un `design/DESIGN.md` par défaut s'il est absent, puis capture une baseline incluant le gate design. Pour un produit sans interface, ce gate n'a pas d'objet. **[FAIT]**

**V-3 — Le mode greenfield impose trois briques SaaS non désactivables.**
`cadrage.py:_merge_t0` force `multi-tenancy`, `rbac` et `auth-sso` en décision `build`, et `catalog.py:resolve_bricks` les réintègre même si l'appelant les marque `skip`. Les actions associées ajoutent Authlib, Casbin et une migration Alembic de tenancy. Un framework de tests n'a ni locataires, ni rôles, ni fédération d'identité. **[FAIT]**

---

## SECTION 2 — Frontière avec l'existant

Règle appliquée : toute capacité classée **CRÉÉ** porte le nom du composant examiné et la raison précise de non-recouvrement. Une capacité classée CRÉÉ sans cette justification serait un défaut de conception.

### 2.1 Les neuf capacités visées

| # | Capacité | Verdict | Composant examiné | Justification |
|---|---|---|---|---|
| C1 | **Scan / inventaire de surface** | **CRÉÉ** | `conductor/capabilities.py`, `conductor/onramp/analyzer.py`, `quality-oracles/scripts/oracle-inventaire-interop.mjs` | Les deux premiers détectent des **rôles, gestionnaires de paquets et commandes** — jamais des routes, endpoints, tables ou branches. Le troisième **vérifie** un inventaire de connecteurs déjà rédigé, il ne l'énumère pas. Aucun composant des deux forges ne parcourt un code source pour en extraire la surface testable |
| C2 | **Modèle de risque** | **CRÉÉ** | `conductor/catalog.py`, `conductor/gates/*.py` | Le catalogue porte une décision build/buy par brique, pas une cotation. Les gates rendent un verdict binaire sans pondération. Aucune notion de criticité, de probabilité ni de coût de détection tardive n'existe dans les deux forges |
| C3 | **Génération de cas de test** | **ÉTENDU** | `conductor/harness/bmad_planner.py`, `conductor/harness/epics_parser.py`, `conductor/harness/bad_runner.py` | La forge sait déjà dériver des stories depuis un PRD, les parser et les faire implémenter par un agent sous gate. L'extension porte sur la **source de dérivation** : partir de l'inventaire de surface et du modèle de risque au lieu d'un document produit par un humain. Le mécanisme de descente vers un agent d'exécution est réutilisé tel quel |
| C4 | **Jeux de données** | **CRÉÉ** | `conductor/scaffold.py`, `targets/fastapi-saas/copier.yml`, `conductor/catalog.py` | Le scaffold greffe des dépendances et un squelette ; il ne fabrique ni fixtures, ni seeding, ni teardown, ni cas limites. Aucune fabrique de données n'existe dans les deux forges |
| C5 | **Harnais d'exécution** | **ÉTENDU** | `conductor/process.py`, `conductor/gates/code_gate.py` | `process.py` fournit déjà un lancement portable (`list[str]`, `shutil.which`, `shell=False`, timeout borné) et `code_gate.py` exécute une commande **par rôle** dans son répertoire, avec skip tracé quand la commande manque. Ce socle est réutilisé ; l'extension porte sur ce qu'il ne fait pas : imposer le déterminisme (graine figée, horloge figée, indépendance à l'ordre), l'isolation et le nettoyage |
| C6 | **Correction sous feu vert** | **RÉUTILISÉ** | `conductor/supervisor.py`, `conductor/planners/remediation.py`, `conductor/governance.py`, skills `audite-et-corrige-l-appli` et `karpathy-coding-discipline` | La forge porte déjà la remédiation par agent, l'escalade après échec, la validation humaine bloquante et l'interdiction de merge autonome. Le skill de cycle détecter → corriger → redéployer et la discipline de chirurgie du code prennent le relais côté agent. Rien à créer |
| C7 | **Itération bornée** | **RÉUTILISÉ** | `conductor/supervisor.py` (`GATE_MAX_RETRIES = 3`), skill `la-boucle` | La borne de 3 itérations exigée par le cahier des garde-fous est déjà la constante en vigueur dans le superviseur. Valeur identique, aucune adaptation |
| C8 | **Reporting** | **ÉTENDU** | `conductor/findings.py`, `conductor/contracts.py:GateVerdict`, `conductor/onramp/base.py:Substrate.declared_degradation`, `conductor/profiles.py:TargetProfile.enforceable`, `quality-oracles/scripts/run-oracles.mjs` | Le patron « part du contrat réellement applicable + liste des limites déclarées » est **exactement** la limite de couverture exigée en section 4. Le registre `SPEC_FINDINGS.md` à statut `traité` / `non-traité` est le format attendu pour les écarts résiduels. L'extension porte sur l'ajout du ratio couvert / inventorié par pan, absent des deux forges |
| C9 | **Création d'adaptateurs** | **ÉTENDU** | `write-an-oracle/scripts/scaffold-oracle.mjs`, skill `write-an-expert`, `conductor/scaffold.py` | Le patron transactionnel demandé existe déjà et fonctionne : validations avant écriture, refus en code 2, `.bak`, entrée de registre à statut. Le scaffolder d'adaptateur en est une déclinaison, pas une invention |

### 2.2 Recouvrements pressentis — confirmés ou infirmés par inspection

| Recouvrement pressenti | Verdict après inspection | Composant |
|---|---|---|
| Régression visuelle → ÉTENDU | **Confirmé — ÉTENDU** | `quality-oracles/scripts/oracle-visual-diff.py` : captures contre goldens versionnés, masques, acceptation hors boucle. Statut exécutable au registre |
| Qualité de données → RÉUTILISÉ | **Infirmé en l'état** | `data-quality-auditor` est déclaré au registre mais **absent des 30 skills montés**. Verdict provisoire : RÉUTILISÉ **sous condition** de retrouver le skill ; à défaut, la capacité bascule en CRÉÉ. Question ouverte (g) |
| Sécurité applicative → RÉUTILISÉ | **Confirmé — RÉUTILISÉ** | `oracle-sast.mjs` (injection SQL et commande, eval/exec, désérialisation), `oracle-sca.mjs` (pip-audit / npm audit / OSV), `oracle-secrets.mjs`. Trois oracles exécutables |
| Scaffolder d'adaptateur → ÉTENDU | **Confirmé — ÉTENDU** | Même patron que `write-an-oracle` et `write-an-expert` |

### 2.3 Capacités supplémentaires réutilisées de la SaaS Forge

Ces capacités ne figuraient pas dans la liste du cadrage. Elles sont relevées parce qu'elles couvrent des exigences de la section 5 sans qu'aucun développement soit nécessaire.

| Exigence du cadrage | Verdict | Composant qui la porte |
|---|---|---|
| Lecture seule par défaut, écriture sur branche dédiée, jamais de merge autonome | **RÉUTILISÉ** | `BadConfig.auto_pr_merge: Literal[False]`, `SprintReport.merged: Literal[False]`, un worktree git par story |
| Validation humaine bloquante, pause et non échec | **RÉUTILISÉ** | `governance.py:HitlPending`, `ManualGate` refusant par défaut en mode headless |
| Interdiction du test-fitting | **ÉTENDU** | `contracts.py:SpecVerdict` : `under-build` bloquant, `over-build` consultatif, via `harness/spec_reviewer.py`. Le mécanisme existe ; l'extension consiste à l'appliquer au sens inverse — détecter l'assertion affaiblie, pas le critère non tenu |
| Ne pas dégrader l'existant | **RÉUTILISÉ** | `gates/regression_gate.py` : tout check vert passé au rouge par rapport à la baseline est bloquant |
| Aucune dépendance à un artefact de la forge en entrée | **RÉUTILISÉ** | `profiles.py:resolve_profile`, cascade à 4 niveaux avec niveau de confiance journalisé — **sous réserve du verrou V-1** |
| Gate d'intégration continue | **RÉUTILISÉ** | `.github/workflows/double-gate.yml` : ruff, mypy strict, pytest, lint de design à politique de sévérité |

### 2.4 Conclusion de frontière

Sur neuf capacités : **3 RÉUTILISÉ, 4 ÉTENDU, 2 CRÉÉ**. Les deux capacités créées — inventaire de surface et modèle de risque — sont précisément celles qui portent le défaut D-01. Ce n'est pas une coïncidence : la SaaS Forge sait faire exécuter une suite de tests et lire son code de sortie, elle n'a aucun moyen de savoir si cette suite atteint quoi que ce soit. C'est le trou que Forge Tests comble, et c'est ce qui justifie qu'il soit un produit et non une option du conducteur.

---

## SECTION 3 — Modèle de risque, contre-oracles, critères d'arrêt

### 3.1 Ce qui remplace la recherche de couverture totale

Tester toutes les combinaisons est impossible par principe : le nombre de chemins croît de façon combinatoire avec le nombre d'états. Aucun objectif de volume de tests n'est donc fixé dans ce CDC — ni nombre de cas, ni pourcentage de lignes couvertes pris isolément.

Ce qui est fixé à la place : une **cotation du risque**, appliquée à chaque élément de surface inventorié.

**Score de risque = criticité métier × probabilité de défaillance × coût de détection tardive**, chaque axe noté de 1 à 5. Score compris entre 1 et 125.

| Axe | 1 | 3 | 5 |
|---|---|---|---|
| **Criticité métier** | Confort d'usage | Fonction utilisée quotidiennement | Perte de données, d'argent, ou blocage d'activité |
| **Probabilité de défaillance** | Code stable, sans dépendance externe | Modifié dans les 90 derniers jours, ou dépendance interne | Modifié dans les 30 derniers jours, ou dépendance externe, ou historique d'incident |
| **Coût de détection tardive** | Détecté en développement | Détecté en recette | Détecté en production, par le client |

Bandes de traitement :

| Bande | Score | Traitement |
|---|---|---|
| **Critique** | ≥ 36 | Génération obligatoire, mutation obligatoire, surface à 100 % |
| **Standard** | 12 à 35 | Génération obligatoire, mutation facultative |
| **Différé** | < 12 | Non généré, **inscrit au référentiel avec sa cotation** — un différé silencieux est interdit |

Pans couverts : Back, Front, API, Data, Batch, Fichiers. Axes non fonctionnels : performance, sécurité, résilience et reprise, accessibilité lorsqu'une interface existe.

**Traçabilité** : chaque test porte un lien vers le risque ou l'exigence qu'il couvre. Un test sans lien est supprimable — c'est une règle d'hygiène du référentiel, pas une recommandation.

### 3.2 Doublet de contre-oracles — jamais un seul

| Question posée | Contre-oracle | Défaut qu'il attrape |
|---|---|---|
| A-t-on **atteint** tout ce qui existe ? | **Couverture de surface** = éléments exercés / éléments inventoriés, par pan | Parcours tronqué, élément jamais exercé — le défaut D-01 |
| Ce qu'on atteint, le **vérifie**-t-on ? | **Score de mutation** = mutants tués / mutants viables | Assertion affaiblie, doublure trop permissive — le défaut H-08 |

**Règle dure, non négociable** : un score de mutation calculé sans couverture de surface mesurée est un indicateur trompeur. Il se calcule sur le seul périmètre atteint, et il flatte d'autant plus que la suite est incomplète — une suite qui n'exerce que la page d'accueil peut afficher 95 % de mutation. **Le score de mutation ne peut jamais être publié seul.** Tout rapport qui affiche un score de mutation affiche, sur la même vue, le taux de couverture de surface du même périmètre. Un rapport qui n'affiche que l'un des deux est un rapport refusé.

### 3.3 Inventaire de surface obligatoire, par pan

| Pan | Surface à énumérer | Source d'énumération |
|---|---|---|
| **Front** | Routes, écrans, éléments interactifs, états | Table de routage, arbre de composants, crawl du navigateur |
| **API** | Endpoints × méthodes × codes de retour, succès **et** erreurs | Spécification OpenAPI si présente, sinon décorateurs de routage du code source |
| **Data** | Tables, colonnes, contraintes, migrations | Schéma de base, fichiers de migration |
| **Batch** | Branches de traitement, codes de rejet, chemins de reprise | Code source des jobs, table des codes de rejet |
| **Fichiers** | Formats, encodages, séparateurs, cas limites | Spécification d'échange si présente, sinon code de parsing |

**Règle dure** : tout élément inventorié et non exercé produit un **FAIL nommé**, avec l'identifiant de l'élément. Jamais une absence silencieuse, jamais un total agrégé qui masque l'élément manquant.

### 3.4 Seuils chiffrés proposés

Ces onze seuils sont **proposés pour validation**. Aucun n'est un objectif de volume : ce sont des planchers de couverture, des plafonds de coût et des critères binaires.

| Id | Seuil | Valeur proposée | Nature |
|---|---|---|---|
| **S-01** | Taux de détection du corpus de la section 0 | **100 %** — les 8 défauts D-01 et H-02 à H-08 détectés | Critère d'acceptation du framework, binaire |
| **S-02** | Répartition de la pyramide, en nombre de cas | **70 % unitaire / 20 % intégration / 10 % bout en bout**, tolérance ± 5 points | Forme assumée, mesurée, non subie |
| **S-03** | Score de mutation sur le périmètre critique (risque ≥ 36) | **≥ 70 %** de mutants viables tués | Plancher |
| **S-04** | Couverture de surface — pan API | **100 %** des couples endpoint × méthode ; **100 %** des codes d'erreur déclarés | Plancher |
| **S-05** | Couverture de surface — pan Front | **100 %** des routes atteintes ; **≥ 90 %** des éléments interactifs exercés | Plancher |
| **S-06** | Couverture de surface — pan Data | **100 %** des tables et contraintes ; **100 %** des migrations rejouées à l'aller et au retour | Plancher |
| **S-07** | Couverture de surface — pans Batch et Fichiers | **≥ 90 %** des branches de traitement ; **100 %** des formats déclarés | Plancher |
| **S-08** | Durée de la suite en intégration continue | **≤ 15 min** au total : ≤ 8 min unitaire et intégration, ≤ 7 min bout en bout | Plafond de coût |
| **S-09** | Taux de tests instables toléré | **≤ 1 %** des cas. Quarantaine ≤ 5 jours ouvrés, sortie de quarantaine après **3 exécutions consécutives vertes** | Plafond + politique |
| **S-10** | Boucle de correction | **3 itérations**, puis livraison avec la liste des écarts résiduels | Borne dure |
| **S-11** | Traçabilité | **100 %** des tests générés portent un lien vers un risque ou une exigence | Plancher |

**Ce qui n'est pas un seuil** : le nombre de tests. Un plafond de durée (S-08) borne le coût sans encourager la production de cas. Le budget par pan se lit dans la durée d'exécution, pas dans un compte de cas — un compte de cas serait un objectif de volume, donc interdit.

### 3.5 Critères d'arrêt

Le diagnostic s'arrête quand l'une de ces conditions est vraie — jamais « quand c'est bon » :

- Tous les seuils S-01 à S-11 applicables au périmètre sont tenus, **ou**
- La borne S-10 de 3 itérations est atteinte : livraison avec les écarts résiduels nommés, chacun avec son élément de surface et son score de risque, **ou**
- Un pan n'a pas d'adaptateur : le diagnostic est marqué **partiel** sur ce pan, et le pan est listé comme non couvert dans le rapport.

---

## SECTION 4 — Architecture

### 4.1 Trilemme tranché

Universel, couvrant toutes les combinaisons, et autonome : ces trois propriétés ne peuvent pas être tenues ensemble. Sortie retenue : **noyau universel mince + adaptateurs par écosystème**.

**Le noyau** porte ce qui ne dépend pas de la stack :

- Le modèle de risque et sa cotation (3.1)
- La traçabilité test → risque (S-11)
- Les critères d'arrêt (3.5) et la boucle bornée à 3 itérations (S-10)
- Le doublet de contre-oracles et la règle de non-publication isolée du score de mutation (3.2)
- Le reporting et le référentiel de tests versionné
- Le registre d'adaptateurs à statuts

**Les adaptateurs** portent la profondeur d'exécution, par couple pan × technologie.

**Limite de couverture, déclarée et jamais masquée** : le niveau réellement atteint dépend de l'existence de l'adaptateur. Un projet dont un pan n'a pas d'adaptateur produit un diagnostic **partiel explicitement marqué sur ce pan**. Le rapport ne produit jamais un vert global qui recouvrirait un pan non instrumenté.

Ce mécanisme n'est pas à inventer : `TargetProfile.enforceable` et `Substrate.declared_degradation` de la SaaS Forge le portent déjà pour les gates code et design (verdict C8, section 2). Forge Tests l'étend au ratio couvert / inventorié par pan.

### 4.2 Contrat d'adaptateur — cinq capacités

Un adaptateur = un couple **(pan × technologie)** fournissant :

1. **Inventaire de surface** — énumérer mécaniquement ce qui existe à tester
2. **Génération de cas** — dériver depuis la surface et le modèle de risque
3. **Harnais d'exécution** — lancer, isoler, nettoyer ; déterminisme imposé : graine figée, horloge figée, indépendance à l'ordre d'exécution
4. **Fabrique de données** — fixtures, seeding, teardown, cas limites
5. **Contre-oracle** — surface, mutation, ou les deux selon le pan

**Loi d'admission** : *un adaptateur qui ne sait pas énumérer sa surface n'est pas un adaptateur.* La capacité 1 est éliminatoire ; les autres peuvent être partielles et déclarées comme telles.

**Admission conditionnée à une paire de fixtures** : un projet-jouet à défaut planté, qui **doit** être détecté, et un projet sain, qui **ne doit pas** être signalé. C'est la porte P1 de `write-an-oracle`, transposée — un mécanisme déjà éprouvé dans la forge de skills, pas une invention.

**Contrat de sortie d'un adaptateur** — repris à l'identique du standard des oracles de `quality-oracles`, verdict `PASS` / `FAIL` / `SKIP`, findings localisants au format `fichier:ligne` ou `élément:identifiant`, champ **`non_juge` obligatoire**, codes de sortie 0 / 1 / 2. Ce qui n'est pas jugé est déclaré, jamais tu.

### 4.3 Socle initial — 19 adaptateurs

Le cadrage annonce 18 adaptateurs et en énumère 19. **[FAIT]** Le tableau ci-dessous en conserve 19 ; l'écart est signalé pour arbitrage.

Outillages **indicatifs**, à confirmer par essai. P1 = première vague produit, alignée sur la stack cible Python + JavaScript + PostgreSQL, **et sur le corpus de la section 0** depuis la décision D-C.

**Deux périmètres à ne pas confondre** : la colonne Prio est la feuille de route produit ; le **périmètre de la phase 1** en est dérivé autrement — un adaptateur y entre s'il est nécessaire à la détection d'un défaut du corpus, ou au fonctionnement d'un adaptateur qui l'est. Les deux ne coïncident pas, et l'écart est explicité en section 6.

| # | Pan | Adaptateur | Outillage indicatif | Prio | Frontière |
|---|---|---|---|---|---|
| 1 | Front | Navigateur bout en bout + crawl de surface | Playwright | P1 | CRÉÉ |
| 2 | Front | Composants JS/TS | Vitest ou Jest + Testing Library | P1 | CRÉÉ |
| 3 | Front | Accessibilité | axe-core ; `oracle-a11y.py` en complément | P2 | ÉTENDU |
| 4 | Front | Régression visuelle | `oracle-visual-diff.py` | P2 | ÉTENDU |
| 5 | API | Contrat REST depuis OpenAPI | Schemathesis | P1 | CRÉÉ |
| 6 | API | Contrat consommateur ↔ fournisseur | Pact | P3 | CRÉÉ |
| 7 | API | GraphQL par schéma | à instruire | P3 | CRÉÉ |
| 8 | Back | Unitaire Python | pytest | P1 | ÉTENDU (`code_gate.py`) |
| 9 | Back | Unitaire JS/TS | Vitest ou Jest | P1 | ÉTENDU (`code_gate.py`) |
| 10 | Back | Mutation Python | mutmut ou cosmic-ray | P1 | CRÉÉ |
| 11 | Back | Mutation JS/TS | Stryker | P2 | CRÉÉ |
| 12 | Data | Base relationnelle éphémère | Testcontainers + PostgreSQL | P1 | CRÉÉ |
| 13 | Data | Migrations — aller, retour, rejeu | Alembic ou équivalent | P1 | CRÉÉ |
| 14 | Data | Qualité de données | `data-quality-auditor` **sous réserve** — voir question (g) | P2 | RÉUTILISÉ sous condition |
| 15 | Batch | Jobs et workers — idempotence, rejeu, reprise | à instruire | **P1** (D-C) | CRÉÉ |
| 16 | Fichiers | Import/export — encodages, séparateurs, volumétrie, rapprochement de totaux | à instruire | **P1** (D-C) | CRÉÉ |
| 17 | NF | Charge et performance | k6 ou Locust ; `oracle-perf.mjs` sur le poids statique | P3 | ÉTENDU |
| 18 | NF | Sécurité applicative et dépendances | `oracle-sast.mjs` + `oracle-sca.mjs` + `oracle-secrets.mjs` | P2 | RÉUTILISÉ |
| 19 | Transverse | Environnement éphémère et intégration continue | conteneurs, base jetable, Railway | P1 | ÉTENDU (`.github/workflows/double-gate.yml`, `process.py`) |

**Point à lever avant de figer #19** : les capacités de Railway en matière d'environnements éphémères par pull request **n'ont pas été vérifiées** — la documentation courante n'a pas été consultée dans ce tour. **[NV]** Question ouverte (h).

### 4.4 Position de Forge Tests par rapport à la SaaS Forge

Deux montages étaient possibles. **Le montage B est retenu (D-F).**

| Montage | Description | Conséquence |
|---|---|---|
| **A — troisième gate du conducteur** | Forge Tests devient un module de `conductor/gates/` | Couplage fort. Forge Tests ne s'appliquerait qu'aux projets passant par le conducteur, ce qui contredit l'exigence « n'importe quel projet, construit ou non avec la forge » |
| **B — produit autonome, consommé par la SaaS Forge** *(retenu, D-F)* | Forge Tests est un dépôt dédié (D-D), doté de sa propre interface en ligne de commande ; la SaaS Forge l'invoque comme n'importe quel outil de son gate code | Découplage. Forge Tests s'applique à tout projet. La SaaS Forge gagne un gate de test réel, là où son gate code se limite aujourd'hui à lire un code de sortie sans savoir ce que la suite atteint |

**Réciprocité** : le gate code actuel de la SaaS Forge (`code_gate.py`) exécute la commande de test du profil et conclut `passed = exit 0`. Une suite qui ne teste que la page d'accueil produit exit 0. La SaaS Forge est donc, en l'état, **structurellement vulnérable au défaut D-01** sur tous les projets qu'elle produit. **[FAIT]** Forge Tests est la réponse à cette vulnérabilité, ce qui fait du montage B un échange à double sens et non une dépendance à sens unique.

### 4.5 Création d'adaptateurs à la demande, et contribution en retour

Scaffolder **transactionnel**, calqué sur `write-an-oracle/scripts/scaffold-oracle.mjs` : toutes les validations avant toute écriture, refus en code de sortie 2, aucune modification partielle, sauvegarde des fichiers modifiés. Registre versionné, statuts `todo` et `ok`.

Un adaptateur né sur un projet client reste **local, en statut `todo`**. Il ne rejoint le socle qu'après rejeu de sa paire de fixtures rouge / verte sur la machine du socle.

### 4.6 Reste à préciser

Ces points sont identifiés et **non tranchés** dans ce tour : environnements d'exécution (local, intégration continue, conteneur, base éphémère, doublures contre bac à sable) ; spécificités des pans Batch et Fichiers ; format de persistance du référentiel de tests, versionné, complétable, avec journal de décisions ; format du rapport lisible par un humain, au-delà du vert et du rouge.

---

## SECTION 5 — Garde-fous

Non négociables. Ceux marqués **[porté]** sont déjà tenus par un mécanisme de code existant, identifié en section 2.

| # | Garde-fou | Mécanisme |
|---|---|---|
| G-1 | **Lecture seule par défaut** sur le code du projet cible. Toute écriture se fait sur une branche dédiée, jamais sur la branche principale, et sous feu vert humain | **[porté]** un worktree git par story ; `auto_pr_merge: Literal[False]` ; `SprintReport.merged: Literal[False]` |
| G-2 | **Interdiction du test-fitting** : ne jamais assouplir une assertion ni modifier le code testé pour faire passer un test rouge, sans justification écrite et tracée | **[porté partiellement]** `SpecVerdict` distingue déjà `under-build` bloquant de `over-build` consultatif ; l'extension consiste à détecter l'assertion affaiblie |
| G-3 | **Boucle de correction bornée à 3 itérations.** Au-delà, livraison avec la liste des écarts résiduels — jamais de boucle sans fin | **[porté]** `supervisor.py:GATE_MAX_RETRIES = 3` puis escalade ; `findings.py` écrit les écarts avec leur statut |
| G-4 | **Aucune donnée de production non anonymisée** dans les jeux d'essai | À porter par la fabrique de données (capacité 4 du contrat d'adaptateur) |
| G-5 | **Aucun chiffrage, aucun tarif journalier, aucun montant inventé.** Placeholder si nécessaire | Ce CDC n'en contient aucun |
| G-6 | Toute donnée affichée trace à une **source citée ou à un calcul rejoué**, sinon elle est marquée « à vérifier » | Marqueurs [FAIT] / [HYP] / [NV] appliqués dans tout ce document |
| G-7 | L'autonomie porte sur le **diagnostic**, pas sur l'écriture dans le code d'autrui — condition de déployabilité en contexte client | **[porté]** `governance.py:HitlPending` : la chaîne se met en pause, elle n'échoue pas et ne passe pas outre |
| G-8 | **Ne pas dégrader l'existant** : un check vert avant intervention qui passe au rouge est bloquant | **[porté]** `gates/regression_gate.py` |

---

## SECTION 6 — Plan phasé et gates

Chaque phase porte un critère de sortie **binaire**, un oracle de vérification, et l'indication d'un point de validation humaine.

### Phase 0 — Levée du verrou de profil

**Véhicule tranché (D-A)** : la SaaS Forge construit Forge Tests, en mode brownfield sur un dépôt initialisé à part. Le mode greenfield est écarté — les trois briques imposées par `_merge_t0` (verrou V-3) n'ont pas d'objet dans un framework de tests. La question du véhicule ne fait plus partie de l'objectif de cette phase.

| Champ | Contenu |
|---|---|
| **Objectif** | Lever le verrou V-1 : donner la priorité au manifeste `.forge/profile.toml` dans `select_onramp`, avant l'appel à `detect_stack` (D-B) |
| **Livrable** | Un dépôt sans interface est résolu avec le profil qu'il déclare, quel que soit son marqueur de stack racine |
| **Critère de sortie binaire** | Un dépôt Python sans interface, portant un `.forge/profile.toml` déclarant `has_ui = false`, est résolu avec ce profil et **non** avec `FASTAPI_SAAS` — vérifié par exécution |
| **Oracle** | Rejeu de la suite `tests/test_profile_resolution.py` et `tests/test_onramp.py` de la SaaS Forge, plus un cas ajouté pour ce scénario |
| **Validation humaine** | **Requise** — modification du conducteur |

### Phase 1 — Banc d'essai à défauts plantés

| Champ | Contenu |
|---|---|
| **Objectif** | Démontrer par exécution que le framework détecte les 8 défauts du corpus de la section 0 |
| **Livrable** | Projet-jouet Python + JavaScript + PostgreSQL, 8 défauts plantés, plus un jumeau sain ; noyau + les 9 adaptateurs du périmètre de phase 1 en état de rendre un verdict |
| **Critère de sortie binaire** | **S-01 tenu : 8 défauts sur 8 détectés sur le projet à défauts, 0 signalement sur le projet sain.** 7 sur 8 est un échec de phase |
| **Oracle** | Exécution du framework sur la paire de projets, comparaison de la liste des findings à la liste des défauts plantés, par identifiant |
| **Validation humaine** | Non requise pour la mesure ; requise pour passer en phase 2 |

**Périmètre d'adaptateurs de la phase 1, dérivé du corpus (D-C).** Règle d'entrée : un adaptateur entre en phase 1 s'il est nécessaire à la détection d'un défaut du corpus, ou au fonctionnement d'un adaptateur qui l'est.

| Adaptateur | Défaut du corpus qu'il couvre | Raison d'entrée |
|---|---|---|
| #1 — crawl de surface Front | **D-01** — le seul défaut constaté | Détection directe |
| #5 — contrat REST depuis OpenAPI | H-02, H-03 | Détection directe |
| #8 — unitaire Python | — | Substrat d'exécution de #10 |
| #10 — mutation Python | H-08 | Détection directe |
| #12 — base relationnelle éphémère | H-04 | Détection directe |
| #13 — migrations aller / retour / rejeu | H-05 | Détection directe |
| #15 — jobs et workers | H-06 | Détection directe — **promu P1 par D-C** |
| #16 — import/export fichiers | H-07 | Détection directe — **promu P1 par D-C** |
| #19 — environnement éphémère et intégration continue | — | Condition d'exécution de #12 et #13 |

**Écart assumé avec la vague produit P1 (D-G)** : #2 (composants JS), #9 (unitaire JS/TS) et #11 (mutation JS/TS) restent en vague P1 produit mais **ne sont pas au périmètre de la phase 1** — aucun défaut du corpus ne les exige. Cet écart est déclaré, pas résorbé : il signifie que la phase 1 ne dit rien de la profondeur d'inspection côté JavaScript, et le rapport de phase 1 doit le mentionner comme pan partiellement instrumenté.

**Sous-étape 1a — génération du banc d'essai.** Le projet-jouet est un SaaS Python + React + PostgreSQL : c'est **exactement** la cible native de la SaaS Forge en mode greenfield, avec son target `fastapi-saas`. Le banc d'essai peut donc être produit par la forge elle-même, en une chaîne A → E, plutôt qu'écrit à la main. Les trois briques imposées (multi-tenancy, rôles, fédération d'identité — verrou V-3) sont ici un **avantage** et non une gêne : elles augmentent la surface à inventorier et rendent le banc plus représentatif d'une application réelle.

**Limite de la preuve de phase 1, assumée** : 7 des 8 défauts du corpus sont fabriqués par nous. Réussir S-01 démontre que le framework détecte ce qu'on lui a appris à chercher. Cela ne démontre pas qu'il détecte ce qui n'a pas été imaginé. La phase 2 est la seule qui puisse produire cette seconde preuve. **[HYP]** sur toute généralisation avant phase 2.

### Phase 2 — Confrontation à un projet réel

| Champ | Contenu |
|---|---|
| **Objectif** | Exécuter le framework sur un projet non conçu pour lui |
| **Projet** | `[À DÉSIGNER — placeholder assumé]` — question ouverte (a) |
| **Livrable** | Rapport de diagnostic, ratio couvert / inventorié par pan, liste des pans marqués partiels |
| **Critère de sortie binaire** | Le rapport nomme, pour chaque pan, le ratio couvert / inventorié **ou** la mention explicite « pan non couvert, adaptateur absent ». Aucun pan silencieux |
| **Oracle** | Relecture du rapport contre la liste des pans ; tout pan absent du rapport est un échec |
| **Validation humaine** | **Requise** — accès à un dépôt tiers |

Cette phase **n'est pas planifiable** tant que le projet n'est pas désigné et les accès connus. Aucune date, aucune charge, aucun chiffrage n'en est dérivé ici.

### Phase 3 — Contribution en retour à la SaaS Forge

| Champ | Contenu |
|---|---|
| **Objectif** | Brancher Forge Tests comme gate de test réel du conducteur, en remplacement de la seule lecture du code de sortie |
| **Critère de sortie binaire** | Sur le banc d'essai de la phase 1, le gate du conducteur **échoue** alors que la commande de test du profil renvoie 0 — c'est la démonstration que le gate mesure autre chose qu'un code de sortie |
| **Oracle** | Exécution comparée : code de sortie de la commande de test, puis verdict du gate étendu |
| **Validation humaine** | **Requise** |

### Phase 4 — Adaptateurs P2 puis P3

Ouverture des vagues P2 et P3 du tableau 4.3, un adaptateur à la fois, chacun admis par sa paire de fixtures. Aucune ouverture avant que la phase 1 soit tenue.

**Règle d'ordre** : aucune généralisation avant preuve d'exécution en phase 1.

---

## Vérification du contrat de sortie

Vérifié point par point avant remise.

| # | Point du contrat | Vérification | Verdict |
|---|---|---|---|
| 1 | Les 7 sections 0 à 6 présentes et non vides | Comptées, toutes renseignées | **OK** |
| 2 | Section 1 : commandes réellement exécutées et sorties, ou inventaire impossible déclaré | 9 commandes avec leurs sorties en 1.2 à 1.4 ; inventaire du projet cible de phase 2 déclaré impossible en 1.1 | **OK** |
| 3 | Chaque capacité de la section 2 porte un verdict avec justification nommant le composant | 9 capacités + 4 recouvrements + 6 capacités supplémentaires, chacun avec fichier ou skill nommé | **OK** |
| 4 | Section 3 sans objectif de volume brut, au moins 6 seuils chiffrés | 11 seuils S-01 à S-11 ; aucun objectif de nombre de tests, explicité en 3.4 | **OK** |
| 5 | Deux contre-oracles distincts + règle de non-publication isolée du score de mutation | Tableau 3.2, règle dure reprise en gras | **OK** |
| 6 | Section 4 distingue noyau et adaptateurs, déclare la limite de couverture sans adaptateur | 4.1, limite déclarée et rattachée au mécanisme existant | **OK** |
| 7 | Aucun critère subjectif comme critère de succès | Recherche des cinq termes interdits : aucun employé comme critère | **OK** |
| 8 | Hypothèses non constatées marquées, distinctes des faits | Marqueurs [FAIT] / [HYP] / [NV] définis en tête et appliqués | **OK** |
| 9 | Zéro ligne de code produite | Aucun bloc de code dans le document ; les transcriptions de commandes sont des sorties d'exécution, pas du code produit | **OK** |
| 10 | Questions ouvertes regroupées en fin, indicées, une par ligne, avec option recommandée et défaut appliqué | Section suivante — 14 entrées a à n, dont 7 closes le 2026-08-02 et reportées au journal des décisions | **OK** |

---

## Questions ouvertes

Une par ligne. Chacune porte l'option recommandée et le **défaut appliqué en l'absence de réponse** — le CDC reste exploitable sans réponse, avec ces défauts.

**a) Projet réel de confrontation, phase 2 ?** — Recommandé : un dépôt Digit-AI existant, avec accès en lecture et une suite de tests déjà présente, pour que le ratio couvert / inventorié soit mesurable dès le premier passage. **Défaut appliqué** : phase 2 non planifiée, placeholder maintenu, aucune date ni charge dérivée.

**b) Accès disponibles — dépôt, intégration continue, base, environnement de recette ?** — Recommandé : lecture du dépôt et de l'intégration continue au minimum ; la base et la recette conditionnent les adaptateurs #12, #13 et #19. **Défaut appliqué** : lecture du dépôt seule ; les pans Data et Batch sont marqués non couverts en phase 2.

**c) Régime des jeux de données ?** — Recommandé : synthétiques uniquement, ce qui rend le garde-fou G-4 automatiquement tenu et supprime toute question d'anonymisation. **Défaut appliqué** : synthétiques uniquement.

**d) Budget de suite acceptable en intégration continue ?** — Recommandé : 15 minutes au total, conformément à S-08. **Défaut appliqué** : S-08 tel que proposé, à réviser après la première mesure réelle en phase 1.

**e) La SaaS Forge construit-elle Forge Tests ?** — **CLOSE le 2026-08-02 (D-A)** : oui, en mode brownfield sur un dépôt initialisé à part. Le mode greenfield est écarté à cause du verrou V-3.

**f) Comment lever le verrou V-1 ?** — **CLOSE le 2026-08-02 (D-B)** : priorité au manifeste `.forge/profile.toml` dans `select_onramp`, avant l'appel à `detect_stack`. Correction d'une inversion de priorité, et non ajout d'un profil curé.

**g) Le skill `data-quality-auditor` existe-t-il ailleurs que dans le registre ?** — Recommandé : le retrouver et le remonter, plutôt que recréer un adaptateur #14. **Défaut appliqué** : adaptateur #14 reclassé CRÉÉ et repoussé en vague P2, et l'entrée du registre `quality-oracles` est marquée à vérifier.

**h) Railway propose-t-il des environnements éphémères par pull request ?** — Recommandé : lire la documentation courante avant de figer l'adaptateur #19 ; ne rien supposer. **Défaut appliqué** : #19 s'appuie sur des conteneurs et une base jetable en local et en intégration continue ; l'hypothèse Railway est marquée [NV] et n'est pas au chemin critique.

**i) Le socle initial compte-t-il 18 ou 19 adaptateurs ?** — Recommandé : 19, l'énumération du cadrage faisant foi sur son propre titre. **Défaut appliqué** : 19, écart signalé en 4.3.

**j) Forge Tests est-il un gate du conducteur ou un produit autonome ?** — **CLOSE le 2026-08-02 (D-F)** : produit autonome, montage B en 4.4.

**k) Où vit le dépôt Forge Tests ?** — **CLOSE le 2026-08-02 (D-D)** : dépôt dédié, distinct de `digit-ai-saas-forge`. **Point non tranché** : sa visibilité. **Défaut appliqué** : privé.

**l) Que faire de l'angle mort JavaScript de la phase 1 ?** — **CLOSE le 2026-08-02 (D-G)** : accepté et déclaré au rapport ; #2, #9, #11 hors périmètre de phase 1.

**m) Outiller le contrat de sortie du CDC en oracle rejouable ?** — **CLOSE le 2026-08-02 (D-H)** : oui, via `write-an-oracle`, au standard de `quality-oracles`.

**n) Où appliquer le correctif V-1 ?** — **CLOSE le 2026-08-02 (D-E)** : branche dédiée et pull request sur `digit-ai-saas-forge`, jamais sur la branche principale.

---

*Fin du CDC. Aucune ligne de code produite. Aucun montant, aucun tarif, aucune charge.*
