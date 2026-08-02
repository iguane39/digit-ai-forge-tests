# Runbook — phase 1, banc d'essai à défauts plantés

**Référence** : Digit-AI - Runbook Forge - Banc d essai phase 1 - 20260802a
**Date** : 2026-08-02
**Amont** : CDC section 6 phase 1 · corpus des 8 défauts · décisions D-A à D-H
**Objet** : la séquence opératoire de la phase 1, et le relevé honnête de ce qui n'a **pas** pu être exécuté dans la session du 2026-08-02.

---

## 1. État à la fin de la session du 2026-08-02

### 1.1 Fait, et vérifié par exécution

| Livrable | État | Preuve |
|---|---|---|
| **L1** — spec du correctif V-1 | Livré | `Digit-AI - Spec Forge - Correctif V1 manifeste opposable - 20260802a.md` |
| **L2** — correctif V-1 appliqué | Livré | Branche `fix/manifeste-opposable-avant-detection-stack`, PR **#39** sur `iguane39/digit-ai-saas-forge`. `ruff` : passed · `mypy --strict` : no issues in 95 files · `pytest` : **265 passed, 1 skipped**. Les 3 tests ajoutés ont été **vérifiés rouges** patch retiré |
| **L3** — corpus des 8 défauts | Livré | `Digit-AI - Corpus Forge - Fiches de defauts - 20260802a.md` |
| **L4** — spec du noyau | Livré | `Digit-AI - Spec Forge - Noyau et contrat adaptateur - 20260802a.md` |
| **L5** — dépôt Forge Tests | Créé | `iguane39/digit-ai-forge-tests`, **privé**, branche `main`, manifeste + docs, sans code |
| **L8** — oracle du contrat CDC | Livré | `quality-oracles/scripts/oracle-cdc-cadrage.mjs`, statut `ok` au registre, paire de fixtures probante au self-test |

**Vérification de bout en bout du couple correctif + manifeste**, exécutée sur le dépôt Forge Tests avec la forge corrigée :

> bretelle : BuilderOnramp · profil : forge-tests · confiance : manifest · has_ui : False
> enforceable : {'code': True, 'design': False} · DESIGN.md créé : False

Le gate design est déclaré non applicable, et rien n'est écrit dans le dépôt. C'est le comportement que V-1 devait rendre atteignable.

### 1.2 Non fait, et pourquoi — relevé factuel

**Le banc d'essai n'a pas été généré.** Trois obstacles, tous constatés, aucun contournable par une décision de ma part.

| # | Obstacle | Constat |
|---|---|---|
| **O-1** | `uv` absent de la machine | `which uv` → absent. Le démarrage rapide de la forge (`uv sync`, `uv run pytest`) et les commandes du profil `fastapi-saas` en dépendent. J'ai contourné pour **vérifier** le correctif, avec un environnement virtuel jetable et `pip` — ce contournement ne convient pas pour un run de production de la forge |
| **O-2** | Le moteur de développement autonome n'est pas invocable depuis Python | `supervisor.py:DefaultBadRunner.run_sprint` lève `NotImplementedError` avec un message explicite : le skill `/bad` doit être invoqué **dans le harnais Claude Code**, hors du processus Python. Ce skill n'est pas installé dans l'environnement courant |
| **O-3** | La chaîne s'arrête aux points de validation humaine, **par conception** | `governance.py:ManualGate.approve` renvoie `False` en mode sans interface et la chaîne lève `HitlPending`. HITL 1 (approbation du PRD et de l'architecture) et HITL 2 (revue avant fusion) ne peuvent pas être franchis par un agent. Ce n'est pas une limite technique à lever : c'est la garantie que la forge existe pour offrir |

**O-3 mérite d'être lu deux fois.** Un agent qui « ferait tout » jusqu'au bout aurait nécessairement contourné les deux points de contrôle humain de la forge — c'est-à-dire cassé la propriété qui rend cette forge déployable en contexte client. La chaîne s'arrête ici parce qu'elle est faite pour s'arrêter ici.

---

## 2. Préconditions à réunir avant la phase 1

| # | Précondition | État constaté | Action |
|---|---|---|---|
| P-1 | `uv` installé et dans le PATH | **Absent** | À installer |
| P-2 | Node et npm | Présents — Node v25.2.1, npm 11.6.2 | Rien |
| P-3 | `gh` authentifié | Présent — compte `iguane39`, portées `repo` et `workflow` | Rien |
| P-4 | Python ≥ 3.11 | Présent — 3.14.2 | Rien |
| P-5 | Identité git | Configurée | Rien |
| P-6 | Session Claude Code interactive | Requise pour O-2 et O-3 | À ouvrir par l'opérateur |
| P-7 | PR #39 fusionnée | **Ouverte, non fusionnée** | Décision humaine — sans elle, la reprise en brownfield du dépôt Forge Tests appliquera le profil `fastapi-saas` et son gate design |

---

## 3. La séquence de la phase 1

### Étape 1a — générer le banc d'essai

Le banc est une application de gestion de commandes de repas, Python + React + PostgreSQL : la cible native `fastapi-saas` de la forge. Il se **génère**, il ne s'écrit pas à la main.

| # | Geste | Point d'arrêt |
|---|---|---|
| 1 | Ouvrir une session Claude Code dans un dossier vide, destiné au banc | — |
| 2 | Suivre `docs/run-playbook.md` de la SaaS Forge, mode greenfield | Le playbook propose avant d'exécuter |
| 3 | Cadrage (A) : idée = l'application du corpus, section 2 des fiches de défauts | Confirmation de la `MissionConfig` |
| 4 | Scaffold-first (B) | — |
| 5 | Planification BMAD (C) | **HITL 1 — approbation humaine du PRD et de l'architecture** |
| 6 | Configuration de sprint (D) | — |
| 7 | Sprint supervisé (E), double gate, remédiation bornée à 3 essais | **HITL 2 — revue humaine, aucune fusion automatique** |

**Note sur les briques imposées.** Le mode greenfield force `multi-tenancy`, `rbac` et `auth-sso` en `build`, sans possibilité de les désactiver. Pour le banc d'essai, c'est un **avantage** : elles augmentent la surface à inventorier et rendent le banc plus représentatif d'une application réelle. C'est la raison pour laquelle le greenfield est écarté pour Forge Tests mais retenu pour son banc.

**Critère de sortie de 1a** : la surface effectivement produite correspond au tableau 2.6 du corpus — 5 routes, 20 éléments interactifs, 7 couples endpoint × méthode, 26 codes de retour, 3 tables, 8 contraintes, 3 migrations, 5 branches de batch, 6 variantes de fichier. **Tout écart se corrige sur le banc, jamais en révisant le tableau de référence** : ce tableau est l'oracle de la capacité d'inventaire.

### Étape 1b — dédoubler et planter

| # | Geste |
|---|---|
| 1 | Créer deux branches, `vert` et `rouge`, à partir du banc généré (question p du corpus, défaut appliqué : deux branches d'un même dépôt) |
| 2 | Sur `vert` : compléter la suite pour couvrir la surface entière, et vérifier qu'aucun des 8 bugs latents n'y est présent |
| 3 | Sur `rouge` : planter les 8 trous de couverture **et** les 8 bugs latents, fiche par fiche |

Le jumeau sain n'est pas un confort : sans lui, un framework qui signalerait tout tiendrait le critère de sortie à 100 %.

### Étape 1c — construire, dans cet ordre

L'ordre découle du corpus, pas de la stack.

| # | Composant | Raison de la position |
|---|---|---|
| 1 | Noyau : contrat de sortie, registre, agrégateur, rapport | Tout adaptateur en dépend. Écrire un adaptateur avant le format du rapport, c'est le réécrire ensuite |
| 2 | Adaptateur #1 — crawl de surface Front | Porte **D-01**, le seul défaut réellement constaté |
| 3 | Adaptateur #5 — contrat REST | Porte H-02 et H-03, deux défauts pour un adaptateur |
| 4 | Adaptateurs #12 et #13 — base éphémère et migrations | Portent H-04 et H-05 ; #19 est leur condition d'exécution |
| 5 | Adaptateurs #8 puis #10 — unitaire puis mutation Python | #8 est le substrat de #10, qui porte H-08 |
| 6 | Adaptateurs #15 et #16 — batch et fichiers | Portent H-06 et H-07 ; promus en phase 1 par la décision D-C |

Chaque adaptateur est admis par **sa** paire de fixtures avant de passer au suivant. Un adaptateur qui ne sait pas énumérer sa surface n'est pas admis.

### Étape 1d — mesurer

| Mesure | Attendu |
|---|---|
| Sur la branche `rouge` | **8 défauts sur 8 détectés au niveau 1**, chacun avec les éléments nommés listés au tableau 4 du corpus |
| Sur la branche `vert` | **Zéro finding** |
| Niveau 2 | Nombre de bugs latents effectivement mis en échec par les tests générés — **mesuré et rapporté, pas critère de sortie** |

**Critère de sortie de la phase 1, binaire** : 8/8 sur `rouge` et 0 sur `vert`. Sept sur huit est un échec de phase.

---

## 4. Les limites de la preuve de phase 1

À reprendre telles quelles dans le rapport final, au titre de la limite déclarée — elles ne sont pas des réserves de style.

- **7 des 8 défauts sont fabriqués par nous.** Tenir le critère démontre que le framework détecte ce qu'on lui a appris à chercher. La phase 2, sur un projet non conçu pour lui, est la seule qui puisse produire l'autre preuve.
- **Le pan JavaScript reste partiellement instrumenté** — décision D-G : #2, #9 et #11 sont hors périmètre de phase 1.
- **Les axes non fonctionnels ne sont pas éprouvés par ce corpus** — performance, sécurité, résilience, accessibilité.
- **Le banc est petit par construction.** Tenir le critère sur 5 routes et 3 tables ne dit rien du comportement sur 200 routes et 80 tables. La montée en taille est un risque de phase 2, pas une propriété acquise.

---

## 5. Ce qui reste ouvert avant de lancer

| Id | Question | Défaut appliqué faute de réponse |
|---|---|---|
| **(k bis)** | Visibilité du dépôt Forge Tests | **Privé** — appliqué. Réversible en une commande |
| **(P-7)** | Fusion de la PR #39 | Non fusionnée. Décision humaine, cohérente avec le verrouillage de fusion de la forge |
| **(a)** | Projet réel de phase 2 | Non désigné — phase 2 non planifiée |
| **(b)** | Accès dépôt, intégration continue, base, recette | Dépôt seul — pans Data et Batch déclarés non couverts en phase 2 |
| **(g)** | `data-quality-auditor` absent du montage | Confirmé absent par le self-test de `quality-oracles`. Adaptateur #14 reclassé CRÉÉ, repoussé en P2 |
| **(h)** | Environnements éphémères Railway par pull request | Non vérifié — #19 s'appuie sur conteneurs et base jetable |

---

*Fin du runbook.*
