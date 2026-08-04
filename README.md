# Forge Tests

> Rendre la qualité d'un projet vérifiable, reproductible et enrichissable dans le temps —
> sans dépendre de la mémoire d'un humain sur ce qu'il faut penser à vérifier.

**État : outil en service.** Le noyau, dix adaptateurs, le générateur de cas, le registre de
dette et la recette du corpus sont écrits et exécutables. La recette officielle
(`recette/verifier_corpus.py`) détecte **12/12** des défauts plantés au banc rouge et ne lève
**aucun finding bloquant** au banc vert.

## Le problème

Une suite de tests verte ne dit rien de ce qu'elle n'atteint pas. Le défaut fondateur du
projet, constaté sur un cas réel : une suite d'interface qui restait sur les premières pages
d'une application, sans jamais atteindre les suivantes ni exercer tous les types de boutons.
La suite passait. Rien, dans son exécution, ne signalait les écrans qu'elle ignorait.

Cause : **biais de disponibilité du générateur** — les tests sont écrits depuis ce que l'agent
a sous les yeux, pas depuis un inventaire mécanique de la surface de l'application.

Conséquence de conception : **inverser le sens de la génération**. Énumérer d'abord la surface
depuis le code source, générer ensuite, mesurer le ratio couvert / inventorié, échouer sous
seuil — et nommer chaque élément non exercé plutôt que de produire un total agrégé.

## Les deux contre-oracles

| Question | Contre-oracle | Défaut attrapé |
|---|---|---|
| A-t-on **atteint** tout ce qui existe ? | Couverture de surface | Parcours tronqué, élément jamais exercé |
| Ce qu'on atteint, le **vérifie**-t-on ? | Score de mutation | Assertion affaiblie, doublure trop permissive |

**Règle dure** : le score de mutation ne peut jamais être publié seul. Il se calcule sur le
seul périmètre atteint et flatte d'autant plus que la suite est lacunaire. Un rapport qui
porterait un score de mutation sans aucune couverture de surface est **refusé** (code 2).

## Usage

```bash
uv sync                                        # environnement de Forge Tests
uv run python -m forge_tests <projet>          # rapport lisible
uv run python -m forge_tests <projet> --json   # rapport machine
```

| Option | Effet |
|---|---|
| `--json` | rapport complet en JSON sur stdout (sinon résumé lisible) |
| `--pans <pan> [...]` | restreint l'audit à ces pans (`front api data migrations batch fichiers back securite accessibilite visuel`) |
| `--generer <dossier>` | dépose les cas de test générés dans ce dossier de **proposition** — jamais dans le projet analysé. Les messages partent sur stderr : `--generer --json` produit un stdout JSON pur |
| `--sortie <fichier>` | persiste le rapport dans ce fichier, **à l'identique** de stdout (le dossier parent est créé au besoin) |

### Codes de sortie

| Code | Signification |
|---|---|
| `0` | `PASS` — tous les pans attendus couverts, aucun défaut bloquant |
| `1` | `FAIL` — au moins un élément inventorié n'est pas exercé, ou un seuil n'est pas tenu |
| `2` | **Rapport refusé** (règle d'affichage conjoint) ou **erreur d'exécution**. Dans les deux cas stdout porte un JSON `{"verdict": "REFUSE"\|"ERREUR", "motif": "…"}` et la trace part sur stderr |
| `3` | `PARTIEL` — au moins un pan attendu n'a pas pu être couvert. Chaque pan non couvert est nommé **avec son motif**. Non bloquant par décision de conception : un projet dont un pan n'a pas d'adaptateur reste auditable |

## Prérequis

**Sur la machine**

- `uv` et Python ≥ 3.11 ; `uv sync` installe Playwright et Pillow, indispensables aux pans
  `accessibilite` et `visuel` (sans eux les deux pans répondent « front non servi »).
- Navigateur Playwright : `uv run playwright install chromium`.
- `node` / `npx` pour le pan `front` (la suite e2e du projet est lancée telle quelle).
- Les oracles de `quality-oracles` dans `~/.claude/skills/quality-oracles/scripts/`
  (`oracle-a11y.py`, `oracle-visual-diff.py`, oracles de sécurité). Racine surchargeable par
  `FORGE_TESTS_ORACLES`.
- Docker seulement pour rejouer la recette des bancs (leur suite monte un PostgreSQL éphémère).

**Dans le projet ANALYSÉ**

- Un environnement Python en `<projet>/backend/.venv` ou `<projet>/.venv`.
- **`coverage` installé dans cet environnement** : c'est l'outil du projet qui fait foi, pas
  celui de Forge Tests. Son absence ne produit plus « suite non exécutée » mais le motif
  explicite *« coverage absent du venv du projet — installer coverage dans … »*.
  Correctif : `uv pip install coverage` (ou l'équivalent) depuis `<projet>/backend`.
- Pour le pan `front` : `<projet>/frontend/node_modules` installé et une suite Playwright.

## Structure attendue du projet cible

```
<projet>/
  backend/
    .venv/            environnement du projet (coverage + pytest dedans)
    app/              code applicatif — main.py, batch.py, importer.py, models.py…
    tests/            suite du projet
    migrations/       *.sql (sens aller / retour / rejeu)
  frontend/
    src/routes.jsx    ou src/routes/*.tsx (convention TanStack Router)
    src/**            data-testid="…" = éléments interactifs inventoriés
    tests/            suite Playwright
    node_modules/
```

Rien de tout cela n'est obligatoire : chaque élément manquant produit un pan **non couvert et
motivé**, jamais un vert par défaut.

## Variables d'environnement

Lues dans `<projet>/.env.forge-tests` puis dans le `.env` de Forge Tests (gitignoré, jamais
journalisé). Modèle : `.env.exemple`.

| Variable | Rôle |
|---|---|
| `FORGE_TESTS_BASE_URL` | instance **servie** à auditer (recette, préproduction). Utilisée pour le rendu des pans `accessibilite` et `visuel`, et exportée en `BASE_URL` vers la suite e2e — sans quoi celle-ci retombe sur son `localhost` et audite un serveur de développement local au lieu de la cible |
| `FORGE_TESTS_API_URL` | API délivrant le jeton d'authentification |
| `FORGE_TESTS_LOGIN` / `FORGE_TESTS_PASSWORD` | compte de **lecture** dédié ; sans jeton, toutes les routes protégées redirigent vers la mire et l'audit ne mesure qu'une page |
| `FORGE_TESTS_LOGIN_PATH` | point d'authentification si le projet s'écarte de la convention FastAPI |
| `FORGE_TESTS_SANS_EXECUTION=1` | inventaire seul, sans exécuter la suite du projet — la non-mesure est déclarée |
| `FORGE_TESTS_ORACLES` | racine des scripts d'oracles |

## Recette et dette

```bash
uv run python recette/verifier_corpus.py   # critère de sortie S-01 — exit 0 attendu
uv run python recette/precision_generateur.py
uv run python -m forge_tests.dette         # régénère registre-dette.json depuis le code
```

La recette rejoue le framework sur la paire de bancs de `fixtures/` : chaque défaut planté du
banc rouge doit produire un finding **nommé**, le banc vert aucun finding bloquant. Elle exige
un venv sous `fixtures/banc-*/backend` (`uv sync --directory fixtures/banc-rouge/backend`), les
dépendances des fronts (`npm ci` puis `npm run build` dans `fixtures/banc-*/frontend`) et
Docker. Elle neutralise `FORGE_TESTS_BASE_URL` : elle porte sur les bancs locaux, jamais sur
l'instance de l'opérateur.

`registre-dette.json` est **régénéré depuis le code** : les `non_juge` déclarés par le noyau,
le risque, l'exécution et les adaptateurs y deviennent des entrées à statut (`todo`, `assume`,
`ok`, `resolue`). Ne pas éditer les énoncés à la main, seulement les statuts et les notes.

## Architecture

**Noyau universel mince + adaptateurs par écosystème.** Le noyau porte le modèle de risque,
la traçabilité test → risque, les critères d'arrêt et le reporting ; il ne connaît aucune
technologie. Les adaptateurs portent la profondeur d'exécution, par couple pan × technologie.

Un pan sans adaptateur produit un diagnostic **partiel explicitement marqué** — jamais un vert
global qui masquerait le trou.

**Loi d'admission** : *un adaptateur qui ne sait pas énumérer sa surface n'est pas un
adaptateur.* Admission conditionnée à une paire de fixtures — projet à défaut planté qui doit
être détecté, projet sain qui ne doit pas être signalé.

## Documents de conception

| Document | Contenu |
|---|---|
| `docs/Digit-AI - CDC Forge - Framework Tests - 20260802a.md` | Le CDC de cadrage : 7 sections, verdicts de frontière, 11 seuils chiffrés, plan phasé, journal des décisions |
| `docs/Digit-AI - Corpus Forge - Fiches de defauts - 20260802a.md` | Le banc d'essai, sa surface de référence, et les 8 défauts à y planter |
| `docs/Digit-AI - Spec Forge - Noyau et contrat adaptateur - 20260802a.md` | Contrat d'adaptateur, référentiel de tests versionné, format du rapport |
| `docs/Digit-AI - Spec Forge - Correctif V1 manifeste opposable - 20260802a.md` | Le correctif appliqué en amont à `digit-ai-saas-forge` pour que ce dépôt soit constructible |
| `docs/Digit-AI - Prompt Forge - Framework Tests Cadrage - 20260731a.md` | Le prompt de cadrage d'origine |

## Rapport avec digit-ai-saas-forge

Forge Tests est un **produit autonome**, pas un module du conducteur — c'est ce qui lui permet
de s'appliquer à n'importe quel projet, construit ou non avec la forge. La SaaS Forge l'invoque
comme n'importe quel outil de son gate code.

L'échange va dans les deux sens. Le gate code du conducteur conclut aujourd'hui `passed` sur le
seul code de sortie de la commande de test du projet. Une suite qui n'exerce que la page
d'accueil renvoie 0. La SaaS Forge est donc, en l'état, exposée au défaut fondateur sur tout ce
qu'elle produit — et Forge Tests est la réponse à cette exposition.

## État du harnais

Forge Tests n'a **pas encore de suite unitaire à lui** : son harnais est la recette du corpus,
qui l'éprouve par exécution sur une paire de bancs. Un `pytest` à la racine ne collecte rien
aujourd'hui — c'est un écart connu, pas un vert.

## Garde-fous

- **Lecture seule par défaut sur le code analysé.** Les artefacts produits par Forge Tests
  (relevé `coverage`, traces et captures Playwright) sont écrits dans un dossier temporaire
  **hors du projet**, jamais dans son arbre.
- Trois écritures restent **déclarées, pas masquées** : la configuration Playwright d'un
  projet peut démarrer son propre `webServer`, qui écrit chez lui (build, code généré) ; le
  pan mutation modifie le source du projet le temps d'un mutant avant de le **restaurer** ; le
  pan visuel dépose ses captures et ses goldens dans `<projet>/.visuel/` — par conception, un
  golden est une référence **versionnée avec le projet**, pas un artefact jetable.
- Un délai dépassé, un outil absent ou une suite rouge **dégradent le pan concerné avec son
  motif** — jamais l'audit entier, jamais en silence.
- Interdiction d'assouplir une assertion pour faire passer un test rouge
- Boucle de correction bornée à 3 itérations, puis livraison avec les écarts résiduels nommés
- Aucune donnée de production non anonymisée dans les jeux d'essai
- L'autonomie porte sur le diagnostic, pas sur l'écriture dans le code d'autrui

---

*Digit-AI · 2026*
