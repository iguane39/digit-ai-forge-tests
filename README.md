# Forge Tests

> Rendre la qualité d'un projet vérifiable, reproductible et enrichissable dans le temps —
> sans dépendre de la mémoire d'un humain sur ce qu'il faut penser à vérifier.

**État : outil en service.** Le noyau, ses adaptateurs, le générateur de cas, le registre
de dette et la recette du corpus sont écrits et exécutables. La recette officielle
(`recette/verifier_corpus.py`) détecte **chacun** des défauts plantés au banc rouge — leur
compte vivant est celui de `CORPUS` dans ce fichier, jamais recopié ici (loi 4) — ne lève
**aucun finding bloquant** au banc vert, et vérifie sur pièces — en treize sections — le
lecteur SQL (RT-8), la qualification des non-testables (RT-6), l'analyse statique des
divergences (RT-9 / RT-10), la suite unitaire (TF-0006) et le linter (TF-0226).

*Ces deux derniers pas existent pour la même raison : un contrôle que rien ne joue n'est pas
un garde-fou. `pytest` puis `ruff` étaient configurés sans qu'aucune vérification ne les
appelle ; ils sont désormais des sections comme les autres, et leur échec fait tomber S-01.*

## Catalogue de services

> Section proposée par la campagne « catalogues » du pilot (2026-08-13) — générée depuis
> la source unique `catalogues/catalogue.jsonl` du pilot (v1.6.0, challengée état de
> l'art le 12/08/2026). **prouvé** = preuve exécutée ; *déclaré* = méthode documentée seulement.

| Service | Intention (« je veux… ») | Point d'entrée | Statut |
|---|---|---|---|
| **Auditer une suite de tests** | savoir ce que mes tests couvrent vraiment et ce qui n'est pas exercé | `uv run python -m forge_tests <racine> --json [--sortie <fichier>]` | prouvé (experimental) |
| **Générer des cas de tests à adopter et exécuter** | recevoir des cas de tests que j'adopte, j'exécute — ou que je solde motivés (R-40) — sans pollution de mon projet | `uv run python -m forge_tests <racine> --generer <dossier-cas-derives>` | prouvé (experimental) |
| **Livrables de tests dérivés (cas à adopter et exécuter)** | obtenir cahiers de tests, jeu de données synthétique et dashboard, chacun publiant son **solde** de cas non soldés | `uv run python -m forge_tests <racine> --livrables <dossier-cas-derives>` | prouvé (experimental) |
| **Tendance et reprise ciblée** | comparer deux audits et ne rejouer que ce qui n'était pas vert | `uv run python -m forge_tests <racine> --precedent <r.json> | --reprendre <r.json>` | prouvé (experimental) |
| **Inventaire sans exécution** | cartographier la surface de test sans rien exécuter | `env FORGE_TESTS_SANS_EXECUTION=1 + CLI` | déclaré (experimental) |
| **Impact par diff, flaky, propriétés, mutation par risque** | auditer moins mais juste : cibler par diff, isoler les flaky, proposer du property-based | `forge_tests\{impact,flaky,generateur_proprietes}.py · risque.repartir_mutants` | déclaré (experimental) |
| **Rapport exhaustif test-par-test** | obtenir le verdict et le pourquoi de CHAQUE test, pas seulement un agrégat par pan | `forge_tests
oyau.py (section essais) + forge_tests\junit.py` | prouvé (experimental) |

Le catalogue consolidé des dix forges vit chez le pilot :
[digit-ai-factory/catalogues/CATALOGUES.md](https://github.com/iguane39/digit-ai-factory/blob/main/catalogues/CATALOGUES.md).

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
| Ce qui est **promis** existe-t-il ? | Contrôle statique de l'interface | Bouton, lien, formulaire inertes — que nulle suite ne peut atteindre |
| Tout le **code** est-il seulement regardé ? | Inventaire de modules | Module jamais importé par la suite, module métier jamais muté |
| Ce que l'**utilisateur** ouvre tient-il debout ? | Parcours d'une instance servie et peuplée | Page en erreur, console rouge, écran vide, bouton sans effet en conditions réelles |

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
| `--pans <pan> [...]` | restreint l'audit à ces pans (`front interface api data migrations batch fichiers back securite accessibilite visuel qualif prompts`) |
| `--generer <dossier>` | dépose les cas de test générés dans ce dossier de **dépôt extérieur** — jamais dans le projet analysé. Ces cas sont **à adopter et exécuter** (R-40), pas un livrable en soi. Les messages partent sur stderr : `--generer --json` produit un stdout JSON pur |
| `--sortie <fichier>` | persiste le rapport dans ce fichier, **à l'identique** de stdout (le dossier parent est créé au besoin) |
| `--reprendre <rapport.json>` | relit un rapport antérieur et **ne rejoue que ce qui n'était pas vert** ; le rapport produit fusionne l'ancien et le neuf avec la provenance de chaque élément — voir « Audit de qualification avec reprise » |
| `--livrables <dossier>` | produit les **livrables dérivés** dans ce dossier de dépôt, **hors du projet audité** : deux cahiers de tests, un jeu de données synthétique, un dashboard HTML autonome. Régénérés à chaque audit, `--reprendre` compris. Messages sur stderr — voir « Cahiers de tests dérivés et dashboard d'exécution » |
| `--precedent <rapport.json>` | rapport antérieur servant de **point de comparaison** : le dashboard affiche alors la tendance de chaque compteur. Sans lui, l'onglet Synthèse le déclare |

### Codes de sortie

| Code | Signification |
|---|---|
| `0` | `PASS` — tous les pans attendus couverts, aucun défaut bloquant |
| `1` | `FAIL` — au moins un élément inventorié n'est pas exercé, ou un seuil n'est pas tenu |
| `2` | **Rapport refusé** (règle d'affichage conjoint) ou **erreur d'exécution**. Dans les deux cas stdout porte un JSON `{"verdict": "REFUSE"\|"ERREUR", "motif": "…"}` et la trace part sur stderr |
| `3` | `PARTIEL` — au moins un pan attendu n'a pas pu être couvert. Chaque pan non couvert est nommé **avec son motif ET son chemin de couverture**. Non bloquant par décision de conception : un projet dont un pan n'a pas d'adaptateur reste auditable |
| `4` | **Refus G-1** — le dossier passé à `--livrables` tombe dans le projet audité. Distinct du `2` : ce n'est pas une panne de génération mais un dossier mal désigné, et le remède n'est pas le même. Le motif est imprimé **en queue de sortie** : `G-1 : livrables HORS projet requis — chemin reçu : <chemin>`. Le rapport, lui, reste publié |

### Un pan non couvert sort une action, pas un constat

`pans_non_couverts[]` porte, pour chaque pan, trois champs — jamais un nom seul :

```json
{
  "pan": "qualif",
  "motif": "qualif : aucune instance servie declaree — le pan exige une application EN SERVICE et PEUPLEE…",
  "pour_couvrir": "servir une instance PEUPLEE du produit et declarer son URL dans FORGE_TESTS_QUALIF_URL ; fournir un compte par FORGE_TESTS_QUALIF_LOGIN / …"
}
```

Le motif dit **pourquoi la mesure n'a pas eu lieu** ; `pour_couvrir` dit **ce qu'il faut faire
pour qu'elle ait lieu** — adaptateur à écrire, configuration à fournir, convention à respecter.
La sortie d'un audit partiel devient ainsi une liste de travaux, pas un relevé de manques. Le
chemin est déclaré par l'adaptateur lui-même (constante `POUR_COUVRIR`), jamais par le noyau :
lui ne connaît aucune technologie et ne saurait pas quoi dire.

### `actions[]` — qui répare, et où

Un rapport nommait des défauts sans jamais dire **qui** les répare. Trois destinataires
existent réellement, et les confondre adresse le travail au mauvais interlocuteur :

| catégorie | ce qu'elle signifie |
|---|---|
| `auto_ia` | un agent de code sait le faire seul : la source qui fait foi (schéma OpenAPI, contrainte SQL, mutant survivant) dit exactement ce qu'il faut écrire. Reste une **proposition à relire** — la loi du générateur ne bouge pas |
| `manuelle_dev` | un développeur doit **trancher** : câbler ou retirer une affordance, aligner une déclaration sur un comportement, décider ce que le test doit affirmer |
| `manuelle_utilisateur` | personne d'autre que l'humain qui exploite le produit ne peut le faire : fournir un identifiant, servir une instance peuplée, **arbitrer** qu'un rendu modifié est bien le rendu voulu |

Et cinq **étapes cibles** qui disent où la correction atterrit : `development`, `tests-suite`,
`design`, `mep-config`, et `forge` — cette dernière réservée au **défaut d'auditeur** : la forge
ne sait pas classer la classe de finding, ou n'a pas d'adaptateur pour le pan. Un défaut de la
forge se nomme comme les autres, il ne se tait pas.

```json
{
  "finding_ref": "visuel/visuel:/accueil",
  "categorie": "manuelle_utilisateur",
  "etape_cible": "design",
  "attendu": "ARBITRER le rendu de « visuel:/accueil » : valider le nouveau golden si le changement est voulu, sinon corriger le rendu…"
}
```

Deux règles dures :

- **le champ vit au rapport JSON, pas au dashboard.** Si le HTML calculait la classification,
  deux lecteurs du même audit — l'un par la page, l'autre par `jq` — auraient deux vérités ;
- **tout finding a exactement une action.** Un constat sans destinataire est un constat qui ne
  sera pas traité. La recette le vérifie, classe par classe.

Les entrées qui ne viennent pas d'un finding portent un préfixe explicite : `non-testable:<pan>`
(configuration absente, regroupée par champs requis) et `pan-non-couvert:<pan>`.

Filtre attendu par le **DOSSIER-MEP** du pilot — une seule expression, sans traitement :

```bash
jq '.actions[] | select(.categorie=="manuelle_utilisateur")' rapport.json
```

## Cahiers de tests dérivés et dashboard d'exécution

`--livrables <dossier>` produit quatre fichiers datés, nommés à la convention Digit-AI
(`<Produit> - <Nature> - AAAAMMJJ<i>.<ext>`), dans un **dossier de dépôt extérieur au projet
audité**. Le garde-fou G-1 n'est pas une convention de nommage : le chemin est résolu, et
s'il tombe sous la racine auditée la production est **refusée avant d'écrire quoi que ce soit**.

| Livrable | Contenu |
|---|---|
| `… - Cahier de tests fonctionnels - …md` | chapitré par écran/parcours, sous-chapitré par état (nominal, vide, erreur, chargement). Chaque cas : préconditions, jeu de données associé, exigence(s) rattachée(s), étapes, résultat attendu |
| `… - Cahier de tests techniques - …md` | chapitré par pan puis module / table / fichier / job |
| `… - Jeu de donnees de tests - …json` | valeurs **synthétiques uniquement**, vérifiées avant écriture |
| `… - Dashboard tests - …html` | page autonome à six onglets, dérivée du **seul** rapport JSON |

### Un cas dérivé n'est pas un livrable — trois états, solde attendu zéro (R-40)

La voie « proposition de tests » est **fermée** (R-40 du pilot, 17/08, TF-0349 ; coût mesuré :
971 cas dérivés pour 0 adopté sur un produit réel — un contrôle jamais joué livré comme s'il
protégeait). Un cas dérivé **naît « à adopter et exécuter »** : état transitoire, jamais
terminal. Il se solde de **trois façons, aucune autre**, déclarées par le PROJET dans
`<projet>/forge/cas-adoptes.jsonl` (lu en lecture seule, G-1) :

| État | Ligne à déclarer | Vérification faite par la forge |
|---|---|---|
| **adopté et exécuté** | `{"cas": "F1-3025-3", "test": "frontend/tests/e2e/10-navigation.spec.ts"}` | le test cité doit **exister**, sinon la déclaration est refusée avec son motif |
| **`non_testable` motivé** (RT-6) | `{"cas": "T2-0481-1", "non_testable": true, "champs_requis": ["FORGE_TESTS_QUALIF_URL"]}` | `champs_requis` **non vide** — il se répare en fournissant, pas en écrivant un test |
| **écarté par décision humaine nommée** | `{"cas": "F1-3025-2", "ecarte_par": "<nom>", "date": "2026-08-17", "motif": "<pourquoi>"}` | `ecarte_par` **et** `motif` exigés — un écart anonyme est un silence déguisé |

Le **solde** `dérivés − adoptés − non_testables − écartés` est calculé par
`forge_tests.adoption` et **publié** en tête de chaque cahier, par chapitre, et sur le
dashboard. Le solde attendu est **zéro** : un cahier non soldé porte un **reste-à-faire**, ce
n'est pas un livrable clos. Une déclaration invérifiable reste **au** solde, avec son motif —
sinon le solde descendrait sur du vide (RT-13).

Les références de cas sont **stables** d'un audit à l'autre : elles sont citables depuis du
code. Antériorité : les fichiers et rapports écrits avant le 17/08 portent l'ancien vocabulaire
(`proposition`) — le lecteur l'accepte et l'affiche comme « à adopter », le producteur ne
l'émet plus.

### « Exhaustif » — une définition opposable, pas une intention

> Chaque élément de surface inventorié porte **au moins un cas**, ou figure en **« non couvert »
> avec sa raison**. Zéro absence silencieuse.

C'est la seule définition qui se contrôle : « tous les cas importants » ne se contrôle pas. Le
tableau d'exhaustivité est en tête de chaque cahier, et la recette vérifie que **chaque élément
du rapport** figure bien dans l'un des deux paniers.

Un élément qu'aucune exécution ne pouvait atteindre ici (configuration absente) ne reçoit **pas**
un cas de complaisance : il est déclaré non couvert, avec les champs à fournir. La loi du
générateur ne change pas d'un étage à l'autre — un cas qu'on sait injouable invite à assouplir
son assertion pour le faire passer, c'est-à-dire le test-fitting que G-2 interdit.

### Chapitres dérivés — un pan futur apparaît seul

Les chapitres ne sont écrits nulle part en dur. Chaque adaptateur déclare les siens :

```python
CHAPITRES = (
    {"code": "T2", "famille": "technique", "titre": "Données",
     "decoupe": "table", "axe_cas": "unitaire"},
)
```

Le cahier et le dashboard les **dérivent du registre**. Un pan ajouté demain apparaît avec son
chapitre sans qu'une ligne soit touchée ; un pan qui n'en déclare aucun reçoit quand même un
chapitre, nommé « pan sans chapitre déclaré » — visible, jamais absent. Un axe de découpe ou de
génération de cas inconnu ne casse rien : il retombe sur un repli, **déclaré dans le cahier**.

Les pans donnent aujourd'hui : `F1` parcours bout en bout, `F2` écrans × états, `F3`
affordances, `F4` accessibilité, `F5` rendu visuel (goldens × thèmes × largeurs, déclarés par le
pan `visuel` lui-même) ; `T1` API par routeur, `T2` données par table, `T3` migrations par
fichier (aller / retour / rejeu), `T4` batch par job, `T5` fichiers par format, `T6` robustesse
de la suite par module, `T7` sécurité, `T8` prompts & modèles.

### Sceau — une édition manuelle est un défaut, et ça se voit

Chaque cahier s'ouvre sur un bloc de sceau : empreintes SHA-256 des **sources** (rapport,
référentiel d'exigences, jeu de données) et du **corps** du document.

```
<!-- SCEAU FORGE-TESTS
  produit: ASD Mail Manager 2
  rapport_sha256: 96921e2aaa6ea9e4165acfa4bef54c8d…
  sceau_corps: 213f43122dd9bfe29ff8fdee5987296066c…
-->
```

Le cahier est **régénéré à chaque audit** : une correction faite dans le fichier serait écrasée
sans bruit à la passe suivante. Le sceau la trahit avant — `nommage.verifier_sceau()` recompare
l'empreinte du corps. Corollaire : deux productions du même rapport donnent le **même octet**
(vérifié par la recette, sha256 à l'appui), ce qui suppose qu'aucune valeur non déterministe
n'entre dans le document.

### Exigences — un rattachement déclaré, jamais deviné

`FORGE_TESTS_EXIGENCES=<chemin EXIGENCES.json>` (variable d'environnement ou
`<projet>/.env.forge-tests`). Deux provenances, et elles ne se valent pas :

- `declare` — le référentiel porte lui-même la clé technique (`"elements": ["code:GET /x=200"]`).
  C'est un **fait** ;
- `lexical` — le référentiel ne porte que du français et la surface que de la technique. Le
  rapprochement se fait sur les racines de mots (≥ 2 racines communes de 5 caractères), il est
  publié **avec sa provenance et la mention « À VALIDER »**.

Affirmer « ce cas vérifie E-014 » sans que rien ne l'établisse fabriquerait une traçabilité
fausse — pire que pas de traçabilité, parce qu'on cesse de la vérifier. Le référentiel absent
est **déclaré en tête du cahier** : les cas sont alors dérivés de la seule surface.

La réciproque, que personne ne regarde jamais, est en annexe : **les exigences qu'aucun cas ne
touche**, nommément. C'est le seul moyen de voir qu'un pan entier du besoin n'a pas de test
quand la couverture de surface, elle, est au vert.

### Jeux de données — synthétiques, et prouvés tels avant écriture

Un jeu de données déposé à côté d'un cahier est un fichier qui circule. Les valeurs sont
fabriquées à partir de listes fermées écrites dans le code, les courriels vivent sous `.test`
(TLD réservé RFC 6761 : aucune adresse n'est joignable), et un garde-fou **codé** relit la
production **avant** de l'écrire. Il lève — il ne signale pas : une fois le fichier posé, il est
trop tard.

Trois motifs de refus : un courriel hors domaine réservé ; une valeur qui ressemble à un secret
(clé `sk-…`, jeton GitHub, JWT, bloc PEM, empreinte hexadécimale longue, identifiants dans une
URL) ; une valeur qui figure dans la configuration du projet audité (`.env*`) ou dans une
variable d'environnement sensible.

### Dashboard — six onglets, une seule source

| Onglet | Contenu |
|---|---|
| 1 · Synthèse | verdict, compteurs (éléments, passés, échecs, dont bloquants, non joués, actions), seuils opposables avec leur état constaté, tendance vs `--precedent` |
| 2 · Fonctionnels | chapitres `F*` dérivés, sous-chapitres, éléments et constats |
| 3 · Techniques | chapitres `T*` dérivés, idem |
| 4 · Échecs | chaque finding avec sa **raison mesurée**, trié par risque |
| 5 · Non joués | `non_testables[]` (champs requis, motif) et `pans_non_couverts[]` (motif, `pour_couvrir`) |
| 6 · Actions | `actions[]` du rapport, filtrable par catégorie et par étape — la page **rend**, elle ne classe pas |

Trois contraintes dures, toutes vérifiées par la recette :

- **autonome** — double-cliquable, zéro requête réseau. Les liens Google Fonts du boilerplate
  `digit-ai-page-html` sont retirés (incompatibles avec la contrainte) ; le repli système est
  explicite dans chaque `font-family`, ce que le contrôle de charte exige. `check_html.py` du
  skill est joué en recette et doit sortir **PASS** ;
- **zéro secret** — aucune valeur de jeton, clé ou mot de passe n'entre dans la page ; les
  **noms** des champs manquants, oui, c'est l'information utile. La frontière est déclarée : le
  jeu de données interdit *toute* valeur de configuration (il doit être intégralement fabriqué),
  le dashboard interdit les **secrets** — l'URL de l'instance auditée figure au rapport, elle est
  le sujet de l'audit et la masquer rendrait les constats du pan `qualif` inintelligibles ;
- **totaux exacts** — chaque compteur affiché porte un `data-total="<clé>"`. La recette relit ce
  qui est **affiché**, le recompare au rapport, et vérifie que le contrôle **discrimine** en lui
  soumettant une page dont un total a été volontairement faussé.

Un pan non couvert n'est jamais absent : son chapitre sort **grisé**, avec son motif et son
chemin de couverture. Un chapitre absent laisserait croire que le sujet n'existe pas dans le
produit.

## Audit de qualification avec reprise

Un audit réel chez un client ne tient pas en une passe. La première bute sur ce qui n'est pas
configuré — une clé d'API tierce, un compte de recette, un jeton. Un humain les saisit. La
seconde passe ne devrait éclairer que ces trous-là. Deux mécanismes rendent ce cycle possible.

### `non_testables[]` — ce qu'aucune exécution ne pouvait atteindre ici

Section **toujours présente** au rapport, même vide (son absence serait indiscernable d'un
« rien à signaler », qui est exactement le silence que le framework interdit). Chaque entrée
porte `element`, `champs_requis[]`, `pan` et `motif` :

```json
"non_testables": [
  { "element": "endpoint:GET /api/factures", "champs_requis": ["ZZ_JETON_CLIENT"],
    "pan": "api", "motif": "api : non exercable sans configuration (constate) — fournir …" }
]
```

Trois sources, de la plus sûre à la plus prudente :

1. **constaté** — la trace du run en échec **cite** une variable absente : `KeyError: 'X'`,
   `X is not set`, `Field required` de `pydantic-settings`, `SKIPPED … X`. Le projet audité dit
   lui-même ce qui lui manque ;
2. **constaté** — un adaptateur le déclare (l'authentification déclare `FORGE_TESTS_API_URL`,
   `…_LOGIN`, `…_PASSWORD` quand aucun compte n'est configuré) ;
3. **présumé** — le projet déclare ses clés dans un `.env.example` et l'environnement ne les
   porte pas. Aucune exécution ne l'a dit : la provenance est marquée `presume`.

Un nom cité mais **correctement fourni** n'est jamais retenu : ce serait du bruit de trace, pas
un manque. Le mécanisme est générique — n'importe quel adaptateur peut remplir `non_testables`,
et le noyau les agrège comme il agrège les `non_juge`. Le remplissage automatique se fait en un
**point unique** au-dessus de tous les adaptateurs : un adaptateur futur en hérite sans une
ligne de code.

**Chaque champ appartient au pan qui le réclame.** Un domaine de configuration (`acces`,
`backend`, `front`) est un sac partagé : l'authentification y dépose le compte, le pan `qualif`
son URL d'instance peuplée. Tout pan en `SKIP` repartait avec le sac entier — le pan `data`
réclamait `FORGE_TESTS_QUALIF_URL`, qui ne l'aurait jamais débloqué (16 actions
`manuelle_utilisateur` fausses au rapport ASD du 07/08). Chaque adaptateur déclare donc sa
constante `CHAMPS_REQUIS` — les variables qui débloquent **ce** pan — et un champ revendiqué
n'est plus publié que pour ses revendicateurs. Un champ que **personne** ne revendique reste
partagé : c'est le cas des variables propres au projet audité, citées par une trace, dont aucun
adaptateur ne connaît le nom.

**Limites déclarées.** Un service tiers injoignable qui ne nomme jamais sa clé reste un pan non
mesuré ordinaire, pas un non-testable. Les champs tirés d'un `.env.example` sont présumés
requis : le fichier ne dit pas quel pan dépend de quelle clé.

### `--reprendre` — rejouer ce qui manque, garder ce qui était vert

```bash
uv run python -m forge_tests <projet> --json --sortie rapport-1.json   # première passe
# … l'humain saisit les identifiants manquants listés en non_testables …
uv run python -m forge_tests <projet> --reprendre rapport-1.json --json --sortie rapport-2.json
```

Sont rejoués les pans qui **n'étaient pas verts** : pans non couverts, pans dont le verdict
n'est pas `PASS`, pans porteurs d'éléments non exercés, de non-testables ou de findings. Les
autres ne sont **même pas lancés** — leur contenu est repris tel quel.

Le rapport fusionné porte une section `reprise` :

| Champ | Contenu |
|---|---|
| `rapport_repris` | chemin du rapport rechargé |
| `pans_rejoues` | pans réellement relancés par cette passe |
| `pans_repris_sans_rejeu` | pans déjà verts, **non relancés** |
| `provenance[pan]` | `exerce_le_run` : éléments exercés par cette passe · `repris_de` : éléments repris du rapport antérieur |

Chaque finding porte aussi sa `provenance` (`exerce_le_run` ou `repris_de:<chemin>`). Un
élément exercé au run précédent et non atteint par le nouveau reste **couvert**, et le finding
« jamais exercé » correspondant disparaît — c'est tout l'objet de la reprise.

`actions[]` est **recalculé** sur le rapport fusionné, jamais repris tel quel : une action
héritée d'un finding résorbé par la reprise réclamerait un travail déjà fait, et c'est le genre
de faux positif qui fait fermer la liste.

Si `--livrables` est passé, les livrables sont **régénérés après la fusion**, exactement comme
après un audit complet. Une reprise qui laisserait un dashboard périmé serait pire qu'aucun
dashboard : on lirait des chiffres d'avant en croyant lire ceux d'après.

```bash
uv run python -m forge_tests <projet> --reprendre rapport-1.json \
    --json --sortie rapport-2.json --livrables ../propositions --precedent rapport-1.json
```

**Limites déclarées.** La ré-exécution a la granularité du **pan** : un pan à rejouer l'est en
entier, c'est l'unité qu'un adaptateur sait lancer. La provenance, elle, est donnée élément par
élément. Et un élément repris atteste d'une mesure **passée** : si le code a changé entre les
deux passes, seule une passe complète fait foi.

## Contrôle statique de l'interface — pan `interface`

> *Une affordance est câblée, ou elle n'existe pas.*

La couverture endpoint × code ne voit pas les promesses d'interface non tenues. Une suite
n'atteint jamais un bouton mort : il n'y a rien à atteindre. Le pan `interface` mesure autre
chose, **en amont de toute exécution** — un `<button>` promet un effet, un `<a>` promet une
destination, un `<form>` promet un envoi ; le contre-oracle vérifie que la promesse est câblée
quelque part dans les sources et **nomme** celles qui ne le sont pas (fichier, ligne, élément,
libellé).

Périmètre : les gabarits rendus tels quels — `.html`, `.htm`, `.jinja`, `.jinja2`, `.j2`,
`.twig`, `.ejs`, `.hbs` — hors `node_modules`, `.venv`, `dist`, `build`, `.visuel` et autres
artefacts, **et les destinations littérales des liens des composants React** (`.jsx`, `.tsx`).
Aucune exécution, aucun navigateur : le pan est disponible là où Playwright ne l'est pas (projet
non constructible, front servi par le backend, gabarit rendu côté serveur).

Est déclaré **inerte** :

| Cas | Verdict |
|---|---|
| `<button>` hors formulaire, sans attribut de gestionnaire, dont ni l'`id`, ni une classe, ni un `data-*` n'est cité dans le JS du projet | inerte |
| `<button type="submit">` dans un formulaire lui-même sans `action` ni gestionnaire | inerte |
| `<a>` sans `href`, ou `href` valant `#`, vide, `javascript:;`, `javascript:void(0)` | inerte |
| `<form>` sans `action` ni gestionnaire de soumission | inerte |

Sont réputés câblés : tout attribut de gestionnaire (`onclick`, `@click`, `v-on:`, `x-on:`,
`hx-*`, `wire:`, `ng-*`, `data-action`, `formaction`…), un `href` réel, une `action` réelle,
`type="reset"` (effet natif), et un `id`/classe/`data-*` cité dans le JS du projet — script en
ligne du document compris. Un élément `disabled` ou `aria-disabled="true"` n'est pas accusé :
son inertie est **voulue et déclarée**.

### Liens des composants React — la destination, pas le câblage (TF-0283)

Les composants `.jsx`/`.tsx` étaient **entièrement** hors périmètre : « leur câblage est une
expression du langage, pas un attribut du gabarit ». C'est vrai du **câblage** ; c'était faux de
la **destination**. Le 15/08/2026, sur un produit legacy en production, quatre liens faux
vivaient dans des `.tsx` — logo anglais vers `/en/blog`, « Contact » de l'en-tête **et** du pied
de page anglais vers la page *française*, bascule « Français » vers `/blog`. Vrais `href`, pages
cibles existantes, aucune suite qui clique : invisibles à tout oracle, livrés, signalés deux fois
par l'humain.

Le pan lit donc aussi les `href`/`to` **littéraux** des `<a>`, `<Link>` et `<NavLink>` des
composants, et juge quatre choses :

| Contrôle | Constat |
|---|---|
| la destination existe dans l'arborescence (routes Next `app/` et `pages/`, tables react-router et TanStack, gabarits, fichiers de `public/`) | `destination absente de l'arborescence` |
| un composant qui sert une locale ne renvoie pas vers une autre **quand sa contrepartie existe** | `composant de la locale « en » pointant vers « /contact » alors que « /en/contact » existe` |
| le **logo** mène à l'accueil de sa locale — sa cible est connue d'avance | `lien du logo vers « /en/blog » au lieu de l'accueil « /en »` |
| la **bascule de langue** mène à l'accueil de la langue visée | `bascule de langue « Français » vers « /blog » au lieu de « / »` |

Classe de finding propre — `lien-casse`, jamais `affordance-inerte` : un lien qui pointe à côté
**a** un effet, et c'est le mauvais. Il n'y a rien à câbler, il y a une destination à corriger.

**Limites déclarées** (reprises telles quelles en `non_juge`) :

- contrôle **statique** : un gestionnaire posé à l'exécution par un framework, ou une
  délégation d'événement sur un ancêtre, est invisible ici. « Inerte » se lit *aucun câblage
  lisible dans les sources* ;
- un élément jugé câblé ne l'est que par **présomption** : la coïncidence de chaîne suffit à le
  blanchir. Le pan attrape l'inerte flagrant, il ne certifie pas le câblé ;
- le câblage prouve l'existence d'un gestionnaire, jamais que son **effet soit observable** —
  un handler vide passerait pour câblé ;
- le **câblage** des composants (`.jsx`, `.tsx`, `.vue`, `.svelte`) n'est pas analysé comme celui
  d'un gabarit ; leur surface interactive est inventoriée par le pan `front` via `data-testid`.
  Seule la **destination** de leurs liens est jugée — pour React (`.jsx`/`.tsx`), Vue (`.vue`) et
  Svelte (`.svelte`), chacun avec **sa** grammaire déclarée : les formes liées de Vue (`:to`,
  `v-bind:href`) et les interpolations Svelte (`href="{x}"`) sont comptées **exprimées**, jamais
  jugées, et à conflit c'est la liaison qui l'emporte comme à l'exécution (TF-0295). Un dialecte
  absent de la table — Angular, Astro, Solid — n'est pas lu ;
- les **locales opposables** sont lues dans l'arborescence littérale **et** dans la configuration
  du framework (`locales: [...]` de Next, nuxt, next-intl — TF-0295). Quand le produit route ses
  locales par un segment **dynamique** (`app/[locale]/…`) sans les déclarer, aucune racine de
  locale n'est connaissable : logo, bascule de langue et cohérence de locale sont alors **non
  jugés**, et le rapport le dit. Les deviner accusait un logo pourtant correct ;
- une destination **exprimée** (`href={chemin}`, template avec `${…}`, constante importée) n'est
  pas résolue : elle est **comptée** et déclarée non jugée. Un lien **relatif** (sans `/`
  initial) non plus — sa résolution dépend de l'URL de rendu ;
- si **aucune** route n'est énumérable, le contrôle d'existence est **désactivé** plutôt que
  deviné : accuser tous les liens d'un projet dont on n'a pas su lire les routes serait un faux
  positif massif ;
- « logo » et « bascule de langue » sont reconnus par **heuristique** (mention de `logo` dans le
  contenu du lien, libellé égal à un nom de langue, attribut `hrefLang`) — un constat ainsi
  produit se conteste comme tout autre (`.forge-tests-declarations.json`) ;
- une ancre `#nom` dont la cible n'existe pas dans le document n'est pas jugée morte : la cible
  peut être injectée au rendu.

### Écart SERVI ↔ VERSIONNÉ — ce que la production sert n'est pas ce que la source promet (TF-0288)

Le 15/08/2026, un menu anglais amputé, signalé **deux fois** par l'humain. La cause évidente était
fausse : `HeaderEn.tsx` portait bien ses **8 entrées** de premier niveau et ses 36 liens, et il
était utilisé par 36 pages EN sur 36. La production en servait **trois**. L'écart vivait entre la
source et le servi, et aucun oracle de l'écosystème ne comparait ces deux termes-là — le pan
`i18n` compare les locales du servi *entre elles*, le contrôle ci-dessus juge la cohérence
*interne* de la source, le pan `qualif` juge la *santé* du servi, et un menu amputé mais
fonctionnel n'est en erreur nulle part. Sans le bloc (b) de l'instruction, la réponse évidente
aurait été d'ajouter au composant des entrées qu'il portait déjà : un développement inutile sur un
défaut de **déploiement**.

Le contrôle tient les deux termes, avec des lecteurs déjà livrés — la grammaire de composants
ci-dessus pour la source, la lecture du build servi du pan `i18n` pour le servi. Il compare les
entrées de navigation **entrée par entrée**, par destination délocalisée, et rend un verdict de
machine :

| Issue | Quand | Ce qui est publié |
|---|---|---|
| `FAIL` | une entrée promise par la source n'est pas servie | un constat par locale, les entrées manquantes **nommées**, et la phrase qui compte : *le code est déjà correct, c'est le servi qui a dérivé* |
| `PASS` | chaque entrée promise est servie | la confrontation, avec le nombre d'entrées servies par locale |
| `SKIP` | un des deux termes manque | **lequel** manque : sans source, il n'y a pas de versionné opposable (l'aggravant du cas fondateur : le produit n'était pas sous git) ; sans build servi, il n'y a rien à confronter |

Classe de finding propre — `ecart-servi-versionne` — et destinataire propre : `manuelle_utilisateur`
/ `mep-config`, jamais `development`. La suite à donner est un **redéploiement depuis la source**,
avec la consigne explicite de *ne pas toucher au code*. Le classer en `development` renverrait le
développeur corriger un code déjà juste, c'est-à-dire refaire l'erreur qui a coûté deux
« toujours pas ».

Le contrôle se déclare au rapport dans les **trois** issues : un `SKIP` muet rendrait « aucun
écart » indiscernable de « la comparaison n'a pas eu lieu ».

Bancs d'essai (TF-0300) : la branche qui **accuse** est mesurée par la recette elle-même, entrée
de corpus `H-20`. `fixtures/banc-rouge/site/` porte la source du site servi par
`fixtures/banc-rouge/dist` — son menu anglais promet trois entrées de premier niveau quand la
production n'en sert que deux, la page des tarifs n'étant jamais arrivée au menu. Le banc vert n'a
pas de source de site : son contrôle reste en `SKIP`, et aucun constat nouveau n'y apparaît. Sans
cette entrée, seule la suite `pytest` prouvait la branche `FAIL` — exactement l'écart que TF-0293
venait de fermer pour le pan `i18n`.

**Limites déclarées** (reprises telles quelles en `non_juge`) :

- la comparaison porte sur les liens d'un `<nav>` **littéral**, des deux côtés. Un menu rendu par
  un composant `<Nav>`, marqué `role="navigation"` ou construit à l'exécution échappe aux deux
  lecteurs — c'est voulu : les deux côtés doivent voir la même chose, sous peine de mesurer
  l'écart des lecteurs et non celui du produit ;
- la comparaison n'est **pas symétrique** : une entrée servie qu'aucune source ne promet n'est pas
  jugée. Elle peut venir d'un autre composant ou d'un gabarit rendu côté serveur, et l'accuser
  serait accuser la limite du lecteur ;
- le « versionné » est le **working tree**, pas une référence git : un produit hors git n'a pas de
  version opposable, seulement des fichiers. Poser git est le préalable, pas ce contrôle ;
- la confrontation porte sur la page d'**accueil** de chaque locale servie ; un menu qui ne
  différerait que sur une page profonde n'est pas vu ;
- une destination **exprimée** n'entre pas dans les entrées promises — comparer ce qu'on n'a pas
  résolu accuserait un déploiement correct.

La **prévention** est l'autre volet du même sujet et elle vit chez `forge-ops` (empreinte scellée
au déploiement, comparée au servi) : chaque volet dans le domaine de sa forge, aucun ne singe
l'autre — verdict O3 de l'étude d'opportunité du 17/08.

## Seuils opposables — au-dessus des standards, et versionnés

Les valeurs usuelles du marché sont un **plancher de recevabilité**, pas une cible : un produit
qui les atteint tout juste a une suite qui accompagne son code, pas qui le contredit. Les
seuils de Forge Tests sont donc plus durs, déclarés dans `forge_tests/seuils.py`, et **publiés
au rapport** (section `seuils`) avec leur justification — un lecteur qui trouve le verdict
sévère lit pourquoi sans ouvrir le code.

| Seuil | Valeur | Sévérité | Porte sur | Pourquoi cette valeur |
|---|---|---|---|---|
| `mutation_globale` | **0,70** | bloquant | score de mutation agrégé du pan `back` | le standard de recevabilité (mutmut, Stryker) est de l'ordre de 0,60 ; 0,70 le dépasse sans exiger un 1,0 qui pousse à *supprimer* le mutant gênant plutôt qu'à écrire l'assertion manquante |
| `mutation_module_metier` | **0,50** | bloquant | score de **chaque** module de logique métier muté | un score global de 0,70 se tient très bien avec un module métier à 0,0 noyé dans la masse. Le seuil par module **interdit la compensation** — c'est exactement le défaut soldé par la campagne A-1/A-3. Dès sa mise en service il a attrapé **trois trous d'assertion réels dans la suite du banc vert**, jusque-là réputée saine |
| `branches_module_exerce` | **0,60** | signalé | couverture de **branches** de chaque module exercé | le standard usuel (0,70) porte sur l'ensemble du code et se laisse compenser ; par module il est plus dur à valeur nominale plus basse. Signalé et non bloquant : `coverage.py` ne voit pas les branches implicites (ternaire, court-circuit), le ratio est minoré par construction |
| `couverture_surface_api` | **1,00** | bloquant | endpoints × codes de retour | un code d'erreur déclaré que la suite n'émet jamais est un chemin non vérifié : sur la surface d'API, l'exhaustivité est le standard maison |
| `couverture_surface_interface` | **1,00** | bloquant | affordances câblées | « une affordance est câblée ou elle n'existe pas » n'a pas de fraction acceptable |
| `couverture_surface_qualif` | **1,00** | bloquant | routes UI parcourues sans erreur | une route qui rend une erreur est vue par le premier utilisateur |
| `couverture_surface_i18n` | **1,00** | bloquant | routes servies dans chaque locale, et dans la bonne langue | une locale publiée est une promesse : une route qui manque dans sa langue est une impasse, une route servie dans une autre langue est un mensonge. Mesuré le 15/08/2026 sur un produit en production : 1 route manquante sur 201, 9 pages sur 200 servies en français sous `/en` |
| `densite_mots_outils_francais` | **0,08** | bloquant | part de mots-outils français dans une page servie sous une locale non française (**heuristique**) | la marge est ce qui rend ce seuil opposable malgré sa nature : un texte français mesure 0,25 à 0,40 sur ce lexique, un texte anglais reste sous 0,02 — et le lexique exclut délibérément les mots ambigus (`on`, `en`, `a`, `plus`, `car`) |

**Ce qui est « logique métier ».** Le défaut est *oui* : l'exemption se déclare, jamais
l'exigence. Sont réputés infrastructure les modules nommés `main`, `db`, `database`, `migrate`,
`settings`, `config`, `conf`, `modeles`, `models`, `schemas`, `deps`, `dependencies`, `wsgi`,
`asgi` (liste `SOCLE` de `forge_tests/seuils.py`). **Tout le reste** — `services/`,
`fournisseurs/`, `auth`, `rbac`, adaptateurs — est soumis au seuil par module. Un projet dont
l'architecture diffère redéclare la liste ; il ne la contourne pas silencieusement.

## La mutation est une campagne À LA DEMANDE (D-34, décision humaine du 01/09/2026)

**La règle, mot pour mot** : « Tous les tests sont pleinement exécutés tout le temps, sauf les
tests sur les mutants qui sont exécutés à la demande, lors d'un passage en Prod sur proposition de
l'IA, et uniquement s'ils n'ont été exécutés depuis plusieurs modifications de code. »

Elle répond à une mesure : une campagne réelle du 01/09 tenait 67 minutes, dont **54 de mutation**,
à 28,2 s par mutant — chaque mutant relance la suite entière. L'étude qui l'a instruite cherchait à
rendre la mutation moins CHÈRE ; la décision la rend plus RARE, et le raisonnement est le plus
solide des deux : le coût d'une campagne ne devient un problème que parce qu'on la joue à chaque
fois. Jouée une fois avant une mise en production, 54 minutes ne sont plus un coût — c'est le prix
d'une porte, et une porte se franchit rarement.

**Ce que la règle interdit, et c'est le versant qu'on oublierait** : « pleinement exécutés tout le
temps » ferme la porte à toute SÉLECTION sur la suite ordinaire. Ne rejouer que les tests touchés
par un changement est **refusé**, et ne se représentera pas sous un autre nom.

| Variable | Défaut | Effet |
|---|---|---|
| `FORGE_TESTS_MUTATION` | absente | demande la campagne. Sans elle, le pan rend `SKIP` en DISANT ce qu'il n'a pas mesuré, publie quand même `modules[]`, et le seuil bloquant `mutation_globale` est déclaré **sans porteur** |
| `FORGE_TESTS_MUTATION_PEREMPTION` | `10` | nombre de commits touchant le **paquet de sources** au-delà duquel la campagne est proposée. « Plusieurs » est un mot ; le seuil est un chiffre, et il est publié au rapport |

La campagne jouée se **note** chez le produit (`forge\mutation-derniere-campagne.json` : commit,
date, score, survivants). Sans ce point de départ, « depuis plusieurs modifications » n'a rien à
compter et la porte proposerait la campagne à chaque passage — c'est-à-dire redeviendrait du bruit.

**Une ancienneté inconnue vaut périmée** — pas de dépôt git, pas de campagne antérieure notée, ou
compte en échec : la campagne est proposée. Le choix inverse ferait passer un projet neuf entre les
mailles pour toujours, sans que rien ne le dise.

Le rapport publie l'état complet sous `mutation.a_la_demande` — dernière campagne, modifications
depuis, seuil retenu, et la **proposition** rédigée. « Sur proposition de l'IA » n'a d'exécutant que
si le texte porte la proposition : un pan qui se contente de se taire ne propose rien.

> Un pan **non demandé** et un pan dont le score est **nul** sont deux choses différentes. Les
> confondre au tableau de bord ferait lire une absence de mesure comme un échec de mesure.

## Périmètre de mutation total et inventaire des modules

**Le périmètre n'est plus une liste blanche.** L'adaptateur de mutation lisait
`backend/app/*.py` — un `glob` **non récursif**. Sur le premier produit réel, il mutait sept
modules de socle et ignorait `services/` et `fournisseurs/`, c'est-à-dire toute la logique
métier : le rapport annonçait *« mutation 37/37, score 1,0 »* sur un produit dont les deux
tiers du code n'avaient jamais été touchés. La découverte est désormais **récursive sur toute
l'arborescence des sources**, et toute exclusion est **nominative, motivée et publiée**.

**Profondeur échantillonnée, périmètre total.** Le coût d'une mutation est une exécution de
suite par mutant. C'est donc la profondeur — combien de mutants par module — qui est bornée,
jamais le périmètre :

| Variable | Défaut | Effet |
|---|---|---|
| `FORGE_TESTS_MUTANTS_PAR_MODULE` | `3` | mutants joués **par module**, répartis à intervalle régulier sur tout le fichier (jamais les *n* premiers, qui seraient tous en tête) |
| `FORGE_TESTS_MUTATION_PLAFOND` | `400` | garde-fou global ; s'il mord, il est **déclaré** au rapport |
| `FORGE_TESTS_MUTATION_EXCLUT` | — | motifs `fnmatch` d'exclusion (`app/fournisseurs/*`) ; chaque module écarté est **nommé avec son motif** dans `modules[]` |

L'échantillon est **déterministe** : deux audits du même code jouent les mêmes mutants, et un
écart de score se lit comme un écart de suite, pas comme un effet du tirage. Il est tiré parmi
les mutants qui **compilent**, et non filtré après coup : l'ordre inverse laissait des modules
entiers sans score — sur ASD Mail Manager, huit modules dont `auth.py`, `rbac.py` et
`services/courrier.py` voyaient leurs trois mutants tirés tomber tous les trois à la
compilation. Filtrer avant coûte quelques millisecondes ; jouer un mutant coûte une exécution
complète de la suite.

Un module sans score sort donc avec la **cause exacte**, jamais un motif fourre-tout : aucun
mutant compilable, aucun échantillonné, ou échantillonné mais non joué (plafond ou délai).

**Ce qui n'est pas muté, et pourquoi.** Docstrings, chaînes, commentaires — et, depuis le
2026-08-06, le **texte des f-strings**. Sur Python 3.12+ celui-ci n'est plus un jeton `STRING`
mais une suite de `FSTRING_MIDDLE` : le filtre, écrit sous 3.11, ne le voyait plus. Chaque
`f"colonnes attendues plat/quantite"` offrait donc un mutant `/` → `*` qui ne change *que* le
libellé d'un message — équivalent par construction, survivant garanti. L'effet ne se voyait pas
tant que la mutation ne touchait que huit modules de socle ; le périmètre total l'a révélé en
plein, les modules `fournisseurs/` d'ASD Mail Manager — surtout faits de messages d'erreur —
sortant tous à 0,00, un score qui n'accusait pas la suite mais l'outil.

**Aucun module silencieux — section `modules[]`.** Le rapport porte l'inventaire des modules
sources avec l'état de chacun : exercé (lignes et branches couvertes), muté (score), ou
**jamais exercé et nommé**. C'est le principe fondateur de la forge appliqué à l'étage du
module — on nomme, on n'agrège pas.

```json
{
  "module": "app/services/courrier.py",
  "categorie": "metier",
  "exerce": true,
  "lignes_couvertes": 118, "lignes_total": 126, "ratio_lignes": 0.9365,
  "branches_couvertes": 38, "branches_total": 44, "ratio_branches": 0.8636,
  "mute": true, "mutants_viables": 3, "tues": 3, "score_mutation": 1.0
}
```

Trois classes de finding en sortent, toutes **nommées** : `module-non-exerce:<module>` (jamais
importé par la suite), `seuil:mutation-module:<module>` (module métier sous 0,50) et
`seuil:branches:<module>` (module exercé sous 0,60, signalé).

Une exclusion par défaut, et une seule : un module **sans aucune instruction exécutable** hors
imports, docstring et constantes de ré-export — le cas type du `__init__.py` de paquet. Elle
est décidée sur le **contenu**, pas sur le nom : un `__init__.py` porteur de logique reste dans
le périmètre. Elle apparaît quand même dans `modules[]`, avec son motif.

## Pan `qualif` — l'instance servie et peuplée

Généralisation du prototype `qualif_populee.py` d'ASD Mail Manager (14 pages, Playwright,
staging peuplé). Le prototype prouvait la valeur du contrôle mais était écrit *pour* un
produit : routes en dur, marqueurs en dur, peuplement en dur. Le pan reprend le contrôle et
laisse au projet ce qui lui appartient — **le peuplement**, car lui seul sait ce que « peuplé »
veut dire chez lui.

Contre une instance **servie et peuplée**, le pan parcourt les routes UI (exploration des liens
depuis la racine, plus les routes d'amorce déclarées) et vérifie, route par route :

| Contrôle | Défaut attrapé |
|---|---|
| statut HTTP | 5xx, ou 404 sur une route pourtant liée depuis une page |
| trace d'exception rendue | `Internal Server Error`, `Traceback`, `jinja2.exceptions`, `TemplateNotFound`… |
| erreur console | exception JavaScript non rattrapée, ressource manquante |
| marqueur de contenu | page qui répond 200 sans rien afficher d'identifiable |
| **élément interactif → effet, dynamique** | affordance sans aucun écouteur attaché, sans destination, sans soumission |

Le dernier contrôle est le **pendant dynamique de RT-7** : le pan `interface` lit les gabarits,
celui-ci interroge le DOM *rendu* via le protocole DevTools — il voit donc les gestionnaires
posés à l'exécution par un framework, que l'analyse statique déclare hors de sa portée. Quand
une **délégation d'événement** est posée sur `document` ou `body`, plus aucun élément ne peut
être déclaré inerte avec certitude : les éléments concernés sont alors **nommés en `non_juge`
au lieu d'être accusés**.

**Aucun clic n'est émis.** L'instance visée est peuplée : cliquer y déclencherait des écritures
réelles — suppression, envoi de courriel, appel d'API tierce facturée. Le pan lit les écouteurs
attachés, il ne les déclenche pas. C'est le prix de la non-destructivité, et il est déclaré.

Sans instance servie, le pan **ne devine rien** : `SKIP` avec son motif, ses champs à fournir
(publiés en `non_testables[]` par le mécanisme RT-6a, sans une ligne spécifique) et son
`pour_couvrir`. Une fois l'URL fournie, `--reprendre` rejoue ce seul pan.

| Variable | Rôle |
|---|---|
| `FORGE_TESTS_QUALIF_URL` | instance servie **et peuplée** à parcourir (à défaut, `FORGE_TESTS_BASE_URL`) |
| `FORGE_TESTS_QUALIF_LOGIN` / `_PASSWORD` | compte de lecture (à défaut, `FORGE_TESTS_LOGIN` / `_PASSWORD`) |
| `FORGE_TESTS_QUALIF_CONNEXION` | route de la mire, si elle n'est ni `/connexion` ni `/login` |
| `FORGE_TESTS_QUALIF_STORAGE_STATE` | session **déjà ouverte** (`storageState.json` Playwright) quand la forge ne peut pas rejouer la mire — IdP d'entreprise, MFA, accès conditionnel. La **provenance** est publiée au rapport, et une session capturée périme |
| `FORGE_TESTS_QUALIF_STORAGE_STATES` | **N sessions étiquetées** `role=chemin` (virgule) — un contexte navigateur par rôle, parcours rejoué par profil, **couverture par rôle** au rapport. L'étiquette est **déclarative** : la forge constate ce que la session VOIT, elle ne vérifie pas qu'elle EST ce rôle (dette déclarée au `non_juge`) |
| `FORGE_TESTS_QUALIF_BEARER` | en-tête `Authorization` ajouté aux requêtes (valeur **jamais publiée**) ; posé sur toutes les sessions étiquetées, ce qui est déclaré |
| `FORGE_TESTS_QUALIF_ROUTES` | routes d'amorce (virgule) — celles qu'aucun lien n'atteint |
| `FORGE_TESTS_QUALIF_MARQUEURS` | JSON `{"/route": "marqueur métier"}` ; à défaut le titre de la page (premier `h1` non vide, sinon `title`) |
| `FORGE_TESTS_QUALIF_PLAFOND` | nombre maximal de routes visitées (défaut `40`) |
| `FORGE_TESTS_QUALIF_REFUS` | routes (virgule) sur lesquelles le produit ATTERRIT pour dire « accès refusé » sans rendre 401/403 ni sa mire (`/erreur/403`, `/oups`). Déclarées, elles jugent ; absentes, seuls les segments nommant l'erreur d'autorisation (`403`, `acces-refuse`, `forbidden`…) sont reconnus, et un refus servi sous un nom quelconque reste **compté comme parcouru** plutôt qu'accusé à tort (TF-0325) |

## Pan `i18n` — la parité entre locales, sur le build servi

**Aucun oracle de l'écosystème ne jugeait le multilingue** — ni cette forge, ni
`quality-oracles`, ni les gates de forge-development. Étude du 15/08/2026, sur un produit en
production : une route française sur 201 sans équivalent anglais ; un menu anglais à **4
entrées** quand le français en portait **9**, non détecté depuis juin ; **9 pages sur 200**
servies sous `/en` avec du contenu **français** (câblage de données qui renvoyait la langue par
défaut quelle que soit la locale demandée). Les trois ont été trouvés à la main en quelques
minutes, et les trois sont scriptables sans le moindre modèle de langage.

Le pan lit le **build servi** — l'arborescence de pages telle que le visiteur la reçoit —
déclaré par `FORGE_TESTS_I18N_BUILD` ou découvert sous la racine. Ni le code source (une locale
peut être déclarée et jamais construite), ni un site distant : **aucun réseau, aucun
navigateur**.

| Contrôle | Nature | Constat |
|---|---|---|
| **parité de routes** — chaque route est servie dans chaque locale | comparaison exacte | `route « /en/tarifs » absente du build : servie dans 1 locale(s) sur 2` |
| **parité de navigation** — le menu de la page d'accueil de chaque locale, apparié **entrée par entrée** par destination délocalisée | comparaison exacte | `menu de la locale « en » : 2 entree(s) distincte(s) contre 4 en « defaut » — manquent 2 entree(s) : « /contact », « /tarifs »` |
| **langue du contenu** — densité des mots-outils d'une langue sous une locale qui n'est pas la sienne | **heuristique**, seuil `densite_mots_outils_francais` | `page servie sous « /en » dont le contenu est en « fr » : 30 % de mots-outils fr sur 89 mots (seuil 8 %)` |

L'appariement de navigation se fait par **destination délocalisée** et non par nombre d'entrées :
deux menus de même taille aux entrées différentes échouent, et les entrées manquantes sont
**nommées** — « manquent 2 entrées » ne disait rien à faire au lecteur (TF-0295). La clé ne peut
pas être le libellé : il est traduit, c'est tout l'objet du sujet.

Le lexique de langue est une **table** — `fr` et `en` livrés, extensible par
`FORGE_TESTS_I18N_LEXIQUES` (fichier JSON `{"de": ["der", "die", …]}`) — et la règle est
générale : sous la locale L, la densité du lexique d'une langue M ≠ L est un constat. Un lexique
déclaré de moins de 20 mots-outils est **refusé** avec son motif : il ne discrimine rien et
accuserait au hasard. Aucun mot n'est partagé entre deux lexiques, condition sans laquelle le
contrôle accuserait à tort des deux côtés. Le rapport **dit** contre quels lexiques il a mesuré :
« aucun anglais détecté » et « la langue n'a été mesurée contre aucun lexique » ne sont pas le
même rapport.

**Ce que le pan ne juge pas** (repris tels quels en `non_juge`) : une locale déclarée mais
jamais construite ; un sous-menu qui ne s'ouvre qu'au clic (absent du HTML servi) ; une entrée
sans destination lisible, appariée sur son libellé donc jamais entre deux langues ; une page de
moins de 40 mots visibles (sous ce volume la densité est du bruit, pas un signal) ; une langue
servie sans lexique opposable ; la **locale par défaut**, qui n'a pas de préfixe donc pas de
langue opposable. L'attribut `lang` du document n'est **jamais** opposé au contenu : un
`lang="en"` posé sur du français *est* le défaut, le croire reviendrait à interroger le suspect.

**Ce qui n'est pas un défaut** : ne pas être multilingue. Un produit sans build servi **et**
sans signe d'internationalisation (dépendance `next-intl`/`i18next`, dossier de traductions,
segment de route `[locale]`) sort en **NA** avec sa preuve. Un produit qui *se dit* multilingue
mais dont le build est absent sort en **SKIP** : le manque est le dossier, pas le sujet, et il
se répare en le fournissant.

Bancs d'essai : le **build servi** des bancs historiques — `fixtures/banc-rouge/dist` (les trois
défauts, entrées de corpus `H-17`, `H-18`, `H-19`) et `fixtures/banc-vert/dist` (les mêmes pages
corrigées). Joués de bout en bout par `tests/test_tf_0284_i18n.py` **et** par la section `corpus`
de la recette, seule à prononcer S-01 : le pan a d'abord vécu dans des bancs séparés, donc hors
du corpus, c'est-à-dire non mesuré par la recette du dépôt (TF-0293).

## Lecture du SQL — filtrer avant de découper

Un `;` posé **dans un commentaire** de migration fabriquait une instruction qui n'avait jamais
existé : jamais envoyée au moteur, donc jamais retrouvée dans le relevé de la sonde, donc
migration déclarée non exercée. Un `FAIL` à tort, produit par le lecteur et non par le projet
audité (constaté en production sur `0004_catalogues.sql`). Symétriquement, une **vraie**
instruction précédée d'un commentaire de tête était rejetée en bloc.

`forge_tests/sql.py` est désormais la source unique : commentaires `--` et `/* */` retirés
**avant** le découpage, littéraux `'…'` et identifiants `"…"` préservés (un `;` ou un `--` dans
une chaîne ne coupe rien et ne masque rien). Les quatre lecteurs SQL du dépôt en dépendent :
l'adaptateur `migrations` (instructions et objets annoncés), l'adaptateur `data` (inventaire des
tables, contraintes, index, triggers — une table mise en commentaire n'entre plus à
l'inventaire) et la sonde `verifier_schema.py` qui rejoue les migrations sur base neuve.

**Limite déclarée** : un `;` ou un `--` placé dans un littéral **dollar-quoté** (`$$…$$`, corps
de fonction PL/pgSQL) ou dans une chaîne à échappement backslash (`E'…\'…'`) reste hors de
portée — l'instruction serait coupée au mauvais endroit.

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

## Matrice des droits exécutable et recette multi-profils (TF-0343 / TF-0342)

**Un produit à rôles n'est pas vérifiable sous une identité unique.** Approval2 a passé un audit
complet le 12/08 : *pan qualif 8/8, ratio 1,00, zéro finding · suite e2e 10/10 verte* — le tout
sous **une** identité qui se désignait elle-même approbateur. Le cas nominal du cahier (« un
approbateur décide, le suivant est sollicité ») n'avait donc jamais été exécuté. Le trou n'a pas
été trouvé par l'outillage mais par une question humaine, cinq jours plus tard. La première
recette inter-profils a révélé un **défaut produit réel** — `canDecide` ne vérifie pas le tour,
l'IHM invite un approbateur hors tour à une action vouée au 409 — plus deux défauts d'ergonomie.

**Et une suite organisée par service ne peut pas dire ce qu'elle ne couvre pas.** Les 10 actions
× 4 profils du cahier étaient couvertes, dispersées dans 13 fichiers. Deux cases manquaient : le
profil « en copie » n'était jamais testé en lecture, et aucun admin n'était instancié sur une
décision — la règle « l'admin ne décide pas à la place d'un approbateur » était vraie *par
construction* et prouvée par rien.

**Le patron : une action × un profil = une cellule = une assertion**, dans UN fichier dédié.
La grille se déclare, le fichier se **dérive** :

```jsonc
// <projet>/forge/matrice-droits.json — une DÉCLARATION du projet (lui seul connaît son contrat)
{
  "profils": ["demandeur", "approbateur", "en copie", "admin"],
  "actions": [
    {"nom": "decider", "methode": "POST", "route": "/api/demandes/{id}/decision", "mute": true,
     "attendu": {"approbateur": 200, "demandeur": 403, "en copie": 403, "admin": 403}},
    {"nom": "relancer", "methode": "POST", "route": "/api/demandes/{id}/relance",
     "attendu": {"demandeur": 200, "approbateur": 403, "en copie": 403, "admin": 200},
     "non_tenues": ["demandeur", "admin"]}
  ]
}
```

`--generer <dossier>` y dépose `test_matrice_droits.py`, hors du projet (G-1). Trois propriétés
portées par le patron, pas par la vigilance :

- **la grille est le produit cartésien** — on énumère d'abord les cases, on regarde ensuite ce
  que le contrat en dit. Une case absente du contrat sort **nommée**, jamais omise ;
- **les cellules non tenues sont en `xfail(strict=True)`** — jamais commentées : le jour du
  correctif, XPASS fait échouer le test et **force** à retirer le marqueur. Un écart commenté,
  lui, survit à son correctif ;
- **une cellule `mute` reçoit un objet neuf** — c'est le piège 3 de TF-0344 (l'approbation du
  profil N ouvrait le tour du profil N+1, qui rendait 201 au lieu de 409) rendu **structurel**.
  C'est le seul des trois pièges qu'aucune revue statique ne sait voir.

*Coût mesuré sur Approval2 : 15 tests, ~340 lignes, 2 écarts rendus exécutables, 13 cellules
vertes.*

Dès qu'une matrice déclare des rôles, le pan `qualif` exige deux choses, et les constate sinon :
**autant d'identités outillées que de rôles** (`FORGE_TESTS_QUALIF_STORAGE_STATES`) et **au moins
un test où deux identités coexistent** — rejouer le même parcours sous N profils l'un après
l'autre ne montre jamais ce qu'un profil *voit* pendant qu'un autre *agit*.

## Revue statique de la suite — les faux verts avant de les payer (TF-0344 / TF-0345)

Trois faux verts le même jour, sur la même campagne, aucun vu par un oracle. Deux sont
détectables **sans rien exécuter** — et c'est décisif : un projet dont la suite ne peut pas
tourner est justement celui où un faux vert dort le plus longtemps. Le pan `front` les porte.

| Piège | Règle | Ce qu'il a coûté |
|---|---|---|
| **absence sans présence** | toute assertion d'absence est précédée d'une assertion de **présence** sur le même écran | `toHaveCount(0)` passe sur une page en chargement : vert en isolation, rouge en exécution complète |
| **motif satisfait par le déclencheur** | aucun motif d'assertion ne doit pouvoir être satisfait par le **déclencheur** de l'action qu'il vérifie | `getByText(/Refused\|Refus/i)` matchait le bouton « Refuse » : instabilité 1 run sur 2, 30 s de timeout par occurrence, **3,6 min → 36 s** après correction. Le même défaut dormait dans un spec vert depuis le 12/08 |
| **cellule mutante sur objet partagé** | toute cellule dont le succès **mute** l'état exige un objet neuf | 201 au lieu de 409 — faux échec. **Non détectable statiquement** : déclaré non jugé ici, rendu structurel par la matrice des droits |
| **donnée de test recopiée** (TF-0345) | une donnée partagée se **référence** (module dédié importé) et se **valide à la génération** | 80 caractères perdus dans la recopie d'un PNG base64 de 3316 : signature PNG intacte, taille plausible, **4 tests en timeout** et un diagnostic égaré vers la chaîne de conversion |

La revue est **textuelle** : un motif construit à l'exécution lui échappe, et les suites Python
ne sont pas relues (les trois pièges mesurés sont des idiomes de navigateur). Les deux écarts
sont déclarés au rapport, jamais tus.

## Une campagne se termine — définition de fin et journal de boucle (TF-0352 / TF-0353)

**Le trou, et son prix.** Rien dans le contrat de l'étape tests ne disait qu'une campagne
inclut la **correction** des anomalies remontées ni le **rejeu jusqu'à extinction**. Le verdict
`PARTIEL` du 12/08 — 121 findings, 127 actions classées — était donc une fin de mandat
*conforme*, alors que le produit sortait **inchangé**. La preuve par l'inverse, le 17/08 : la
même stratégie exécutée avec obligation de traiter a fermé **4 anomalies produit** et **3 faux
verts** (dont un dormant depuis le 12/08), et divisé par six la durée de la suite e2e
(3,6 min → 36 s).

**Ce que la boucle mesure**, tour par tour, sur cette journée-là :

| tour | anomalies | d'où elles viennent |
|---|---|---|
| 1 | 4 | l'audit |
| 2 | **9** | des correctifs du tour 1 (signature du port de messagerie, diffusion élargie, scission rappel/relance, export passé en 403, confirmation ajoutée) |
| 3 | 1 | une **course** — la classe la plus coûteuse à retrouver plus tard |
| 4 | 0 | trois passages verts consécutifs |

**69 % des anomalies n'existaient pas au tour 1.** Un mandat qui s'arrête au rapport en manque
4 sur 4 ; un mandat qui s'arrête après avoir corrigé une fois en laisse 10 sur 14 et rend une
suite rouge. Une clôture au tour 2 aurait livré la course du tour 3.

**La définition de fin, opposable** (`forge_tests/boucle.py`) — une campagne est TERMINÉE
quand, et seulement quand :

| | Point | Refusé sinon parce que |
|---|---|---|
| a | toutes les portes en exit 0 (`suites`, `lint`, `typage`, `e2e`) | une porte **absente du journal** n'est pas une porte verte : elle est manquante, et c'est dit |
| b | aucun `xfail` / `test.fail` sans arbitrage humain **daté** | un test désarmé sans décision est une anomalie masquée, pas un écart assumé |
| c | suite verte sur **N ≥ 2** passages consécutifs | un passage unique ne distingue pas une suite stable d'une instabilité qui n'est pas tombée (mesuré : 1 run sur 2) |
| d | chaque anomalie **corrigée**, ou portée en écart assumé et **écrit** (qui, quand, pourquoi) | un écart anonyme n'assume rien — même raison qu'une adoption invérifiable (RT-13) |
| e | le dernier tour **rejoué APRÈS** son dernier correctif | sinon « 0 anomalie » ne dit rien d'autre que « on n'a pas rejoué » : c'est la clôture que TF-0353 interdit |

Tant qu'un point manque, l'étape est `en_cours` — **jamais** `termine_avec_ecarts`.

**Le journal.** Une ligne JSON par tour dans `<projet>/forge/journal-boucle.jsonl`, tenue par
la campagne — jamais par la forge : un journal écrit par l'outil qu'il juge ne prouverait rien.

```json
{"tour": 3, "anomalies_entrantes": 1, "corrigees": 1, "nouvelles": 1, "restantes": 0,
 "dernier_correctif": "2026-08-17T16:00:00+02:00", "dernier_run_suite": "2026-08-17T16:20:00+02:00",
 "portes": {"suites": 0, "lint": 0, "typage": 0, "e2e": 0},
 "xfail_non_justifies": 0, "passages_verts_consecutifs": 3, "ecarts_assumes": []}
```

Chaque rapport d'audit porte la section **`boucle`** : elle juge la CAMPAGNE, quand `verdict`
juge CE run. Les confondre est exactement la faute du 12/08. Journal absent → la section le
**dit** (`aucun journal de boucle`), elle ne se tait pas.

**Le compteur de tours dit aussi quand s'arrêter pour de bonnes raisons** : une campagne dont
le tour N révèle autant que le tour N-1 ne converge pas. C'est publié (`convergence.signal`)
comme un signal à remonter — jamais utilisé pour refuser une clôture qui tient ses cinq points.

## Contrat du projet audité

Ce que Forge Tests **suppose** du projet pour pouvoir le mesurer. Chaque convention ci-dessous
est appliquée par un adaptateur ; jusqu'ici elles n'étaient découvrables qu'en lisant son code.
Aucune n'est obligatoire : ce qui manque produit un pan **motivé**, jamais un vert.

### Cycle de vie et provenance de l'instance servie — pans `front`, `qualif`, `accessibilite`, `visuel` (TF-0340 / TF-0341)

Quatre pans exigent une instance **servie**. Le montage reste délégué au projet — lui seul sait ce que « peuplée » veut dire chez lui — mais jusqu'au 18/08 le **démontage** n'était délégué à personne, et le rapport ne disait pas ce qu'il laissait debout.

*Mesuré le 17/08 sur bourse-aux-vacants : 3 conteneurs et un réseau laissés en service **2 h 25** après la fin de l'audit, tenant les ports 8091, 8092 et 5544, jusqu'à ce qu'un humain s'en étonne. Et la moitié grave : la topologie avait été bâtie à 10:47, le correctif D-14 écrit après — pendant cette fenêtre, un audit relancé aurait mesuré l'ancien code et publié ses chiffres comme l'état courant.*

La règle tient en une phrase, et le rapport la publie : **la forge démonte ce qu'elle a monté, et publie ce qu'elle laisse debout quand elle ne l'a pas monté.**

| Convention | Effet si elle n'est pas tenue |
|---|---|
| `FORGE_TESTS_INSTANCE_DEMONTER` — la commande qui démonte l'instance | l'audit dit ce qu'il laisse debout **et** que rien ne permet de le démonter : c'est cette absence qui a coûté les 2 h 25 |
| `FORGE_TESTS_INSTANCE_MONTER` — la commande qui la monte | déclarée pour le jour où la forge montera elle-même ; sans elle, la forge ne monte pas et ne démonte donc rien |
| `FORGE_TESTS_INSTANCE_PROVENANCE` — chemin d'un document disant **de quoi** l'instance a été bâtie | issue `non_determinable`, en disant que c'est le terme **servi** qui manque : rien ne distingue alors une instance fraîche d'une instance périmée |

Le format de provenance n'est **pas** propre à cette forge : le scellé `forge-ops/empreinte@1` produit par `ops.mjs deployer|canary` est lu tel quel (mêmes empreintes de fichiers que compare `oracle-ops.mjs --empreinte`, O-7). Un projet qui monte localement déclare la forme légère `forge-tests/instance@1` (`commit`, `construit_le`, `images[]`).

La section `instance` du rapport est **toujours présente**, même sans instance déclarée — une section qui disparaîtrait serait indiscernable d'une section qui a mesuré et n'a rien trouvé. La confrontation rend les **trois issues** de l'écart servi ↔ versionné (TF-0288), généralisé de la page à l'instance entière : `concordant` · `divergent`, l'écart nommé fichier par fichier et la phrase qui compte (*ce n'est pas le code qui est en retard, c'est l'instance*) · `non_determinable`, en disant **lequel** des deux termes manque. La comparaison n'est pas symétrique, et c'est déclaré : un fichier neuf que l'empreinte ne connaît pas ne déclenche rien.

### Application ASGI — pan `api`

| Convention | Effet si elle n'est pas tenue |
|---|---|
| L'application est l'**instance module** `app.main:app`, dans `<projet>/backend/app/main.py` | la sonde ASGI ne se greffe sur rien |
| Sinon, la désigner par `FORGE_TESTS_APP="module:attribut"` — l'attribut peut être l'instance **ou une fabrique** (`app.main:creer_app`) | — |
| La suite passe par cette application (ou par les applications rendues par la fabrique) | relevé vide |

Quand `FORGE_TESTS_APP` est déclarée, la greffe a lieu **avant** le chargement des
`conftest.py` : chaque application rendue par la fabrique est instrumentée, y compris quand un
`tests/conftest.py` importe la fabrique par son nom. Sans déclaration, la greffe reste au
démarrage de session — importer l'application plus tôt la ferait précéder l'environnement que
le projet installe lui-même. L'extraction du schéma OpenAPI suit la même désignation et
**appelle la fabrique sans argument**.

Une suite qui finit **verte** avec un relevé **vide** produit un avertissement explicite —
finding `sonde-muette:api` (sévérité `signale`) et entrée `non_juge` — parce qu'un « 0 %
couvert » est alors plus probablement une sonde aveugle qu'une suite qui n'appelle rien.

Codes de retour :

- l'inventaire des codes vient des `responses` du **schéma OpenAPI** que l'application produit
  elle-même — donc du `status_code=` du décorateur et des `responses={…}` explicites ;
- le `422` que FastAPI ajoute d'office n'est retenu que s'il est écrit **à la main** dans le
  décorateur ;
- un `400` ou `409` déclaré qu'aucun `raise HTTPException(status_code=…)` du handler ne peut
  lever est une **divergence bloquante** ;
- un code **émis** pendant la suite mais absent de la déclaration est une divergence `signale` ;
- **aucune assertion de test n'est lue** : seul le couple réellement émis compte.

#### Où la garde doit être écrite pour être reconnue (RT-9)

L'analyse ne lisait que le `raise … status_code=<littéral>` écrit **dans le corps de la
route**. Un produit qui factorise son refus dans un helper (`_refuser_doublon()` levant le 409)
voyait donc son 409 déclaré « jamais levé » — deux passes de correction sur produit réel avant
de retrouver la forme attendue : l'outil imposait un style d'écriture au lieu de lire le
comportement. Depuis, **un niveau d'appel est résolu**.

| Forme de la garde | Reconnue ? |
|---|---|
| `raise HTTPException(status_code=409, …)` dans la route | oui |
| `_refuser_doublon()` — helper du **même module**, appelé **par son nom simple**, dont le corps lève avec un `status_code` **constant** | **oui (RT-9)** |
| helper qui appelle lui-même un autre helper (deux niveaux) | non |
| helper **importé** d'un autre module | non |
| appel par attribut : `self.refuser()`, `service.refuser()` | non |
| `status_code` calculé (variable, expression, table de correspondance) | non |

Les quatre dernières lignes sont la **contrainte résiduelle**, déclarée aussi au registre de
dette : dans ces cas le code déclaré paraîtra « jamais levé ». Le remède côté projet est
d'écrire la levée dans la route, ou dans un helper local appelé par son nom.

#### Ce qui n'est pas une route (RT-10)

Les montages — `app.mount("/static", StaticFiles(…))`, sous-application ASGI — sont **exclus du
contrôle de divergence**. Un montage n'a pas de décorateur, donc pas de `responses=`, et
FastAPI n'offre aucun moyen d'en déclarer un : le finding « code émis absent de `responses=` »
y était **structurellement incorrigeable** côté produit (constaté sur `GET /static/app.js`).
Les codes d'un montage sont réputés `200` (fichier servi) et `404` (fichier absent) — c'est le
comportement documenté de Starlette, pas une promesse du projet. Les préfixes exclus sont
**nommés en `non_juge`** au rapport ; une vraie route dont le chemin commence par les mêmes
lettres (`/statistiques` face au montage `/static`) n'est **pas** exclue.

### Couche SQL observable — pans `data` et `migrations`

Deux points d'observation, dans cet ordre :

| Point | Ce qu'il relève |
|---|---|
| SQLAlchemy (`before_cursor_execute`, `handle_error`) | instructions **et** violations de contrainte |
| Repli `sqlite3` stdlib (`Connection.set_trace_callback`) | instructions seulement |

Le repli couvre les backends écrits sans ORM. Il s'arme en enveloppant `sqlite3.connect` dans
le processus de test — **aucun fichier du projet n'est modifié** — et exclut la base de
`coverage`. Sa limite est déclarée : sans violation captée, **les contraintes ne sont pas
attribuables** sur un projet sans SQLAlchemy ; tables, index et triggers, eux, sont mesurés.

Si **ni** SQLAlchemy **ni** le repli ne voient passer d'instruction, le rapport le dit :
*« projet sans couche SQL observable — … : pans data/migrations non mesurables »*. Et quand des
instructions sont observées sans qu'il y ait de surface à inventorier, le motif le dit aussi,
avec le nombre d'instructions vues et le point d'observation utilisé.

### Migrations

- Fichiers `<projet>/backend/migrations/*.sql`, au format `-- +migrate Up` / `-- +migrate Down`.
- Trois sens par migration, **tous mesurés pendant la suite** : `aller` (toutes les instructions
  de la section Up envoyées au moteur au moins une fois), `rejeu` (les mêmes envoyées **deux**
  fois), `retour` (section Down envoyée au moins une fois).
- Une migration sans section `-- +migrate Down` est une **divergence bloquante**.
- Alembic (`backend/app/alembic/versions`, `backend/alembic/versions`, `alembic/versions`) est
  **inventorié** et ses `downgrade` vides sont détectés, mais l'exercice n'est mesuré que pour
  les `.sql` : une suite Alembic sort à 0 % exercé. **Écart connu, pas un verdict.**
- L'effet réel (« l'objet annoncé existe-t-il après application ? ») est vérifié en rejouant les
  sections Up sur une base neuve, ce qui exige `sqlalchemy` + `testcontainers` **dans le venv du
  projet** et **Docker**. Sans eux : *« schéma réel non introspectable »*, et les divergences
  sont jugées sur le texte des migrations.

### Contraintes de données

Une contrainte est réputée exercée **quand la suite la fait violer** — pas quand un test la
mentionne. Ce qui suppose des contraintes **nommées**, car l'attribution passe par le message
du moteur :

| Moteur | Attribution |
|---|---|
| PostgreSQL | toute contrainte nommée (y compris clé étrangère) est attribuée directement |
| SQLite — `CHECK` | le moteur rapporte le **nom** : une contrainte anonyme n'est pas attribuable |
| SQLite — `NOT NULL` | rapporté en `table.colonne`, attribué à la colonne |
| SQLite — `UNIQUE` | rapporté en `table.colonne`, attribué à la contrainte dont le **nom contient à la fois la table et la colonne** — d'où la forme `uq_<table>_<colonne>` / `ck_<table>_<colonne>` |
| SQLite — clé étrangère | **non attribuable** : le moteur ne nomme pas la contrainte violée |

Tables, index et triggers sont exercés si une instruction envoyée au moteur les **nomme**.
Une contrainte déclarée dans l'ORM (`UniqueConstraint` / `CheckConstraint` / `ForeignKey` avec
`name="…"` dans `backend/app/models.py`) mais absente des migrations est une **divergence
bloquante** : le code croit la base protégée, la base ne l'est pas.

### Ordre des tests dans la suite

Le relevé d'instructions SQL est borné, pour ne pas croître sans limite sur une grosse suite :
au plus **trois passages** par instruction identique (le seuil le plus exigeant est « vue deux
fois », pour le rejeu), et les instructions **non structurantes** sont bornées aux 4 000
dernières. Le DDL (`CREATE`, `ALTER`, `DROP`, `TRUNCATE`) n'est **jamais évincé** : une migration
exercée tôt dans la suite reste visible quel que soit le volume de requêtes qui la suit.

Contrainte résiduelle assumée : une section de migration qui contient du **DML** (`INSERT`,
`UPDATE`, `DELETE`) et qui s'exécute avant plus de 4 000 autres instructions non structurantes
peut sortir de la fenêtre — la section entière compte alors pour non exercée. Placer les tests
de migrations tôt ne suffit pas ; c'est le volume qui SUIT qui décide.

### Autres pans

| Pan | Conventions appliquées | Seuil |
|---|---|---|
| `front` | routes dans `frontend/src/routes.jsx` (`path: "…"`) ou convention TanStack `frontend/src/routes/**.tsx` ; éléments interactifs = attributs `data-testid="…"` **statiques** dans `src/**.{jsx,tsx}` ; exercé = trace Playwright (navigations et sélecteurs `data-testid`) | 90 % |
| `interface` | gabarits `.html/.htm/.jinja/.jinja2/.j2/.twig/.ejs/.hbs` hors artefacts ; « exercé » = **câblé** (gestionnaire, destination ou identifiant cité dans le JS) — voir « Contrôle statique de l'interface » | 100 % |
| `batch` | branches dérivées de l'AST de `backend/app/batch.py` (à défaut, inventaire de `backend/app/worker/*.py` — mais **la mesure ne porte que sur `batch.py`**) ; codes de rejet = littéraux de la forme `XXX-YYY` en majuscules | 90 % |
| `fichiers` | chemins de parsing dérivés de l'AST de `backend/app/importer.py` | 100 % |
| `back` | mutation réelle : altération de **tous** les modules de `backend/app` (récursif, `services/` et `fournisseurs/` compris), relance de `tests`, échantillon de 3 mutants par module (paramétrable, déclaré au rapport) ; inventaire `modules[]` | 70 % global **et** 50 % par module métier |
| `qualif` | instance **servie et peuplée** déclarée par `FORGE_TESTS_QUALIF_URL` ; routes découvertes par les liens depuis la racine — voir « Pan `qualif` » | 100 % |
| `securite` | oracles `quality-oracles` présents sur la machine ; leurs `non_juge` sont repris tels quels | — |
| `prompts` | **statique et gratuit — aucun appel modèle, aucun réseau** : prompts adressables (`*.prompt`, dossiers `prompts/`, `gabarits/`, `SKILL.md`, constantes Python `*PROMPT*`), modèles nommés dans une chaîne littérale ou une clé `modele:`, corpus de cas (`evals/`, `*.eval.jsonl`, `cas.json`). « Exercé » = **cité par au moins un cas versionné** ; un modèle désigné par un alias mouvant (`*-latest`, `gpt-4o`) au lieu d'une version épinglée `nom-AAAAMMJJ` est un finding `modele-non-epingle` ; un corpus déclaré mais introuvable rend son prompt `non_testable` | 100 % |
| `accessibilite`, `visuel` | front **servi** : `FORGE_TESTS_BASE_URL`, ou build local présent dans `frontend/dist` plus `npx` et un navigateur Playwright ; un golden absent produit un SKIP motivé, jamais une référence créée pendant le run | — |
| `i18n` | **build servi** (dossier de pages) déclaré par `FORGE_TESTS_I18N_BUILD` ou découvert (`out/`, `dist/`, `_site/`…) ; locales = préfixes de route ISO 639-1 réellement servis — voir « Pan `i18n` » | 100 % |

La suite backend est lancée depuis `<projet>/backend` avec `coverage run --branch
--source=app,tests` : le paquet `app` doit être importable depuis ce dossier.

## Variables d'environnement

Lues dans `<projet>/.env.forge-tests` puis dans le `.env` de Forge Tests (gitignoré, jamais
journalisé). Modèle : `.env.exemple`.

| Variable | Rôle |
|---|---|
| `FORGE_TESTS_APP` | désignation `module:attribut` de l'application ASGI auditée (défaut `app.main:app`). L'attribut peut être une **fabrique** — voir « Contrat du projet audité ». Lue par la sonde API **et** par l'extraction du schéma OpenAPI |
| `FORGE_TESTS_BASE_URL` | instance **servie** à auditer (recette, préproduction). Utilisée pour le rendu des pans `accessibilite` et `visuel`, et exportée en `BASE_URL` vers la suite e2e — sans quoi celle-ci retombe sur son `localhost` et audite un serveur de développement local au lieu de la cible |
| `FORGE_TESTS_API_URL` | API délivrant le jeton d'authentification |
| `FORGE_TESTS_LOGIN` / `FORGE_TESTS_PASSWORD` | compte de **lecture** dédié ; sans jeton, toutes les routes protégées redirigent vers la mire et l'audit ne mesure qu'une page |
| `FORGE_TESTS_LOGIN_PATH` | point d'authentification si le projet s'écarte de la convention FastAPI |
| `FORGE_TESTS_SANS_EXECUTION=1` | inventaire seul, sans exécuter la suite du projet — la non-mesure est déclarée |
| `FORGE_TESTS_ORACLES` | racine des scripts d'oracles |
| `FORGE_TESTS_PROMPTS_CORPUS` | racine d'un corpus de cas (questions / réponses attendues) qui vit **hors** du dépôt audité — champ publié par le pan `prompts` quand un prompt déclare un corpus introuvable |
| `FORGE_TESTS_MUTANTS_PAR_MODULE` | profondeur de mutation par module (défaut `3`) — le **périmètre** reste total, seule la profondeur est échantillonnée, et le taux est publié au rapport |
| `FORGE_TESTS_MUTATION_PLAFOND` | garde-fou global du nombre de mutants joués (défaut `400`) ; s'il mord, il est déclaré |
| `FORGE_TESTS_MUTATION_EXCLUT` | motifs `fnmatch` de modules à exclure du périmètre (`app/fournisseurs/*`) — chaque exclusion est **nommée avec son motif** dans `modules[]`, jamais silencieuse |
| `FORGE_TESTS_QUALIF_URL` | instance **servie et peuplée** parcourue par le pan `qualif` (à défaut, `FORGE_TESTS_BASE_URL` — donc à vérifier avant d'auditer un autre projet que celui que `.env` décrit) |
| `FORGE_TESTS_QUALIF_LOGIN` / `_PASSWORD` | compte du pan `qualif` (à défaut `FORGE_TESTS_LOGIN` / `_PASSWORD`) |
| `FORGE_TESTS_QUALIF_CONNEXION` | route de la mire si elle n'est ni `/connexion` ni `/login` |
| `FORGE_TESTS_QUALIF_STORAGE_STATE` / `_BEARER` | session ouverte **ailleurs** (storage state Playwright, en-tête `Authorization`) pour une instance derrière un IdP d'entreprise |
| `FORGE_TESTS_QUALIF_STORAGE_STATES` | `role=chemin` (virgule) : **N sessions étiquetées**, un contexte par rôle, couverture **par rôle** au rapport — voir « Pan `qualif` » |
| `FORGE_TESTS_QUALIF_ROUTES` | routes d'amorce du parcours (virgule) — celles qu'aucun lien n'atteint |
| `FORGE_TESTS_QUALIF_MARQUEURS` | JSON `{"/route": "marqueur métier"}` ; à défaut le titre de la page |
| `FORGE_TESTS_QUALIF_PLAFOND` | nombre maximal de routes visitées (défaut `40`) |
| `FORGE_TESTS_QUALIF_REFUS` | routes d'atterrissage de refus d'autorisation propres au produit (virgule) — voir « Pan `qualif` » |
| `FORGE_TESTS_I18N_BUILD` | dossier du **build servi** lu par le pan `i18n` (l'arborescence de pages telle que le visiteur la reçoit). À défaut, le pan cherche `out/`, `dist/`, `build/`, `_site/`, `site/`, `www/`, `public/` sous la racine, puis un `index.html` à la racine elle-même. Aucun réseau, aucun navigateur |
| `FORGE_TESTS_EXIGENCES` | chemin d'un `EXIGENCES.json` : les cas des cahiers y sont rattachés, **avec leur provenance** (`declare` ou `lexical`). Absent, le cahier le déclare en tête et dérive de la seule surface. Un chemin qui n'existe pas est un **refus**, pas un silence |
| `FORGE_TESTS_PRODUIT` | nom du produit dans les noms de fichiers des livrables. À défaut : le champ `projet` du référentiel d'exigences, puis le nom du dossier audité |
| `FORGE_TESTS_PLAYWRIGHT_TRACE` | mode `--trace` imposé à la suite e2e (`on`, `off`, `retain-on-failure`…) — à défaut, le mode déjà réglé dans le `playwright.config` du projet est respecté (rien n'est passé en ligne de commande), sinon replié sur `on`. Utile pour désactiver la trace si son écriture bloque sur un poste (TF-0132) — la couverture front devient alors non mesurable, déclarée telle |

## Recette et dette

```bash
uv run python recette/verifier_corpus.py   # critère de sortie S-01 — exit 0 attendu
uv run python recette/verifier_corpus.py --section sql qualification   # une poignée de secondes
uv run pytest                              # suite unitaire du dépôt (jouée aussi par la recette)
uv run python recette/precision_generateur.py
uv run python -m forge_tests.dette             # régénère registre-dette.json depuis le code
uv run python -m forge_tests.dette --verifier  # exit 1 si le registre committé a divergé
```

La recette rejoue le framework sur la paire de bancs de `fixtures/` : **chacune** des entrées de
`CORPUS` (`recette/verifier_corpus.py` — la liste est la seule source du compte, et la recette
l'imprime au verdict) doit produire un finding **nommé** par SON propre défaut planté au banc
rouge, le banc vert aucun finding bloquant.

Le pan `qualif` juge une application **en service** : il ne pourrait donc pas être exercé par
un banc de fichiers, comme les autres pans. La recette **sert elle-même** `fixtures/banc-*/
qualif-web/` sur un port libre (serveur de la bibliothèque standard) et déclare l'URL au pan.
Le serveur est réel, le navigateur est réel, les erreurs console et les 404 sont réels — seul
le *peuplement* est écrit en dur dans les pages du banc, parce que peupler une application est
la responsabilité du projet audité, pas du framework. Les défauts plantés côté rouge : lien
vers une page absente (404), trace d'exception rendue dans une page qui répond 200, page sans
aucun marqueur de contenu, erreur console au chargement, bouton sans le moindre écouteur.

Elle ajoute six vérifications **sur pièces**, pour des mécanismes qu'aucun banc ne peut
exercer : le lecteur SQL (`;` dans un commentaire, en fin de ligne commentée, dans un bloc,
dans un littéral — RT-8) ; la qualification des non-testables (variable absente citée par une
trace, refus de compter une variable pourtant fournie — RT-6) ; l'analyse des divergences
(garde déportée dans un helper local, montage `StaticFiles` exclu — RT-9 / RT-10) ; les
chemins de couverture des pans non couverts (A-5), qu'aucun banc n'exerce puisque tous les
pans y sont couverts ; la relecture des rapports **antérieurs** à A-5 par `--reprendre` ; et la
restauration byte-exacte après mutation (G-1, fichier en LF et en CRLF). Sans elles, ces
mécanismes pourraient pourrir sans que rien ne le dise. La recette empreinte en outre les
sources des deux bancs en SHA-256 **avant et après** l'audit : aucun octet ne doit bouger.

Quatre vérifications portent sur les **livrables**, et chacune a sa contrepartie rouge — un
contrôle qu'on ne voit jamais échouer ne contrôle rien :

| Vérification | Le vert | Le rouge qui prouve qu'elle discrimine |
|---|---|---|
| `actions[]` | ≥ 1 action par catégorie **et** par étape cible ; tout finding en porte exactement une | une classe de finding **inventée** sort un défaut d'auditeur (`etape_cible: forge`), jamais un finding sans suite |
| jeux de données | un jeu produit par la forge passe le garde-fou ; un courriel du domaine réservé aussi | courriel de domaine réel, clé `sk-…`, jeton GitHub, JWT, empreinte hexadécimale, URL à identifiants, valeur du `.env` du projet — **six refus** |
| cahiers | sceau valide, deux runs identiques au sha256, chaque élément inventorié présent, douze chapitres dérivés | une édition manuelle d'un caractère est trahie par le sceau ; un élément non testable sort **nommé** en « non couvert » avec le champ à fournir ; un dépôt dans le projet audité est refusé (G-1) |
| dashboard | totaux égaux au rapport, aucune ressource distante, deux thèmes, six onglets, `check_html.py` **PASS** | un total volontairement faussé et un total retiré sont tous deux détectés ; une valeur de jeton dans la page lève avant écriture |

Le contrôle des totaux relit ce qui est **affiché** (`data-total="<clé>"`), pas une variable
interne : un dashboard peut mentir sans que le code qui l'a produit ait tort.

### `--section` — payer le prix de ce qu'on vérifie

La recette entière coûte **3 minutes** sur une machine de développement, et ce prix est celui
des **audits des bancs** (mutation, navigateur, conteneur) — les contrôles sur pièces, eux,
coûtent quelques centièmes. Un correctif d'une ligne au lecteur SQL payait donc trois minutes
pour vérifier une seconde de code, ce qui a un effet mesurable : on rejoue moins souvent.

`--section <nom> [...]` ne joue que les sections demandées, et **n'audite que les bancs dont
elles ont besoin** :

| Sélection | Bancs audités | Durée mesurée (09/08) |
|---|---|---|
| aucune (recette entière) | rouge + vert | **181 s** |
| les 8 sections sur pièces (`sql qualification dette divergences chemins lecture-seule actions jeux`) | aucun | **1 s** |
| `cahiers` ou `dashboard` | rouge seul | **100 s** |
| `corpus` | rouge + vert | ~180 s |

Sections : `corpus`, `unitaire`, `sql`, `qualification`, `dette`, `divergences`, `chemins`,
`lecture-seule`, `actions`, `jeux`, `cahiers`, `dashboard` (`--help` les liste avec leur coût).

**Une recette partielle ne prononce jamais S-01.** Elle sort `RECETTE PARTIELLE — S-01 NON
PRONONCÉ` en nommant les sections non jouées : un « vert » sur trois sections et un silence sur
toutes les autres serait exactement le mensonge que le sélecteur rendrait facile. Le critère de
sortie reste la recette entière ; le sélecteur sert la boucle de correction, pas le verdict.

Elle exige un venv sous `fixtures/banc-*/backend` (`uv sync --directory
fixtures/banc-rouge/backend`), les dépendances des fronts (`npm ci` puis `npm run build` dans
`fixtures/banc-*/frontend`), un navigateur Playwright et Docker. Elle neutralise
`FORGE_TESTS_BASE_URL` : elle porte sur les bancs locaux, jamais sur l'instance de l'opérateur.

`registre-dette.json` est **régénéré depuis le code** : les `non_juge` déclarés par le noyau,
le risque, l'exécution et les adaptateurs y deviennent des entrées à statut. Ne pas éditer les
énoncés à la main, seulement les statuts, les preuves et les notes.

| Statut | Ce qu'il affirme |
|---|---|
| `todo` | à outiller |
| `assume` | limite acceptée et déclarée pour toujours |
| `ok` | **comblée** — le champ `preuve` nomme le test ou le contrôle de recette qui la tient. Sans `preuve`, le statut est **refusé** |
| `retiree` | l'énoncé a disparu du code, sans preuve. Posé par la machine, et **ce n'est pas une fermeture** |

Deux règles de sémantique, posées après le constat du 08/08 — 89 entrées, **zéro** fermeture,
27 « résolues » qui n'étaient que des phrases réécrites :

- **l'identifiant est stable et découplé de l'énoncé.** Il valait `<domaine>-<sha8(énoncé)>` :
  reformuler une phrase fabriquait une entrée neuve en `todo` et faisait passer l'ancienne pour
  comblée. Il vaut désormais `<domaine>-<rang>`, attribué une fois et conservé. Un énoncé
  reformulé garde son identité, son statut et sa note — le rapprochement se fait sur la
  ressemblance (≥ 70 % dans le même domaine) et il est **déclaré** à la régénération ;
- **la synchronisation est vérifiée en recette.** Régénéré à la main, le registre n'est pas
  régénéré : la dette du jour se lirait dans un fichier qui décrit le code d'avant-hier.
  `--verifier` compare le fichier committé à la projection du code et **échoue** — il ne
  signale pas. Ses deux contreparties rouges (registre amputé, `ok` sans preuve) sont jouées
  par la recette.

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

Deux filets, et ils ne mesurent pas la même chose :

- **la recette du corpus** éprouve le framework *par exécution*, sur une paire de bancs. C'est
  elle qui prononce le critère de sortie S-01 ;
- **la suite unitaire** (`tests/`, `uv run pytest`) porte sur les **bords** que les bancs
  n'exercent pas : littéral SQL non fermé, variable de configuration citée mais fournie, action
  d'une classe de finding inconnue. Elle couvre aujourd'hui les trois modules dont dépend tout
  le reste — `sql.py` (les quatre lecteurs SQL du dépôt en dépendent), `qualification.py` (ce
  qu'on demande à un humain de fournir) et `actions.py` (à qui l'audit adresse son travail).

**Ce qui reste sans suite unitaire est nommé, jamais tu** : `noyau.py`, `reprise.py`,
`execution.py`, `invariants.py`, les adaptateurs et les livrables n'ont pour filet que la
recette. C'est un écart connu, pas un vert.

La suite est jouée **par la recette** (section `unitaire`) : une suite unitaire qu'aucune
vérification ne lance serait exactement l'écart qu'elle est censée combler.

## Garde-fous

- **Lecture seule par défaut sur le code analysé.** Les artefacts produits par Forge Tests
  (relevé `coverage`, traces et captures Playwright) sont écrits dans un dossier temporaire
  **hors du projet**, jamais dans son arbre.
- Trois écritures restent **déclarées, pas masquées** : la configuration Playwright d'un
  projet peut démarrer son propre `webServer`, qui écrit chez lui (build, code généré) ; le
  pan mutation modifie le source du projet le temps d'un mutant avant de le **restaurer** ; le
  pan visuel dépose ses captures et ses goldens dans `<projet>/.visuel/` — par conception, un
  golden est une référence **versionnée avec le projet**, pas un artefact jetable.
- **La restauration après mutation est byte-exacte, fins de ligne comprises.** Le 2026-08-06,
  le premier audit à périmètre total a laissé **23 fichiers source du produit modifiés** : la
  mutation était bien défaite, mais la restauration passait par `Path.write_text`, qui traduit
  `\n` en `os.linesep` — les modules en LF revenaient en CRLF. Une lecture seule qui réécrit
  les fins de ligne n'est pas une lecture seule. L'écart avait dormi depuis l'origine parce que
  le périmètre d'avant A-1 ne touchait que huit modules déjà convertis en CRLF par un audit
  antérieur. L'écriture et la restauration passent désormais par un point unique **en octets**,
  et la restauration est **vérifiée** avant d'être déclarée. La recette le contrôle sur pièces
  (fichier en LF *et* en CRLF, avec un témoin qui montre que l'ancien chemin altérait le
  premier) et empreinte en SHA-256 les sources des deux bancs avant et après chaque audit.
- Le pan visuel ne crée plus `<projet>/.visuel/` quand le projet **n'a aucune route** à
  capturer : un projet purement API, ou dont le front est servi par le backend, se voyait créer
  un dossier vide dans son arbre pour un pan qui allait conclure `SKIP`.
- **Les deux recettes neutralisent `FORGE_TESTS_BASE_URL`.** `precision_generateur.py` ne le
  faisait pas : le lancer capturait le DOM de l'instance cliente décrite par le `.env` de
  l'opérateur et l'écrivait dans `fixtures/banc-*/.visuel/`. Un outil qui pollue ses propres
  bancs de référence perd la seule chose qui rend ses verdicts comparables.
- Un délai dépassé, un outil absent ou une suite rouge **dégradent le pan concerné avec son
  motif** — jamais l'audit entier, jamais en silence.
- Interdiction d'assouplir une assertion pour faire passer un test rouge
- Boucle de correction bornée à 3 itérations, puis livraison avec les écarts résiduels nommés
- Aucune donnée de production non anonymisée dans les jeux d'essai
- L'autonomie porte sur le diagnostic, pas sur l'écriture dans le code d'autrui

---

*Digit-AI · 2026*
