# Corpus de recette — banc d'essai et fiches de défauts

**Référence** : Digit-AI - Corpus Forge - Fiches de defauts - 20260802a
**Date** : 2026-08-02
**Amont** : `Digit-AI - CDC Forge - Framework Tests - 20260802a.md`, section 0 et section 6 phase 1
**Objet** : livrable **L3**. Spécifie le banc d'essai, sa surface de référence, et les 8 défauts à y planter avec leur critère de détection.

Aucune ligne de code dans ce document : il décrit **quoi** planter et **quel finding** doit sortir, pas comment l'écrire.

---

## 1. Principe de conception du corpus

### 1.1 Un défaut du corpus n'est pas un bug applicatif

Le corpus de la section 0 du CDC porte sur des **suites de tests déficientes**, pas sur des applications cassées. D-01 est un défaut de la suite : l'application marchait, c'est la suite qui ne regardait pas.

Chaque fiche plante donc **deux choses**, et le banc d'essai les porte ensemble :

| Élément planté | Où | Ce qu'il démontre |
|---|---|---|
| **Un trou de couverture** — un élément de surface que la suite fournie n'exerce pas | Dans la suite de tests du banc d'essai | Le contre-oracle sait nommer ce qui n'est pas atteint |
| **Un bug latent** — un défaut applicatif logé exactement dans ce trou | Dans le code du banc d'essai | Le test généré pour combler le trou échoue effectivement |

### 1.2 Deux niveaux de détection, un seul est le critère de sortie

| Niveau | Ce qui est mesuré | Statut |
|---|---|---|
| **Niveau 1** | Le framework **nomme l'élément non couvert** (ou le mutant survivant, pour H-08) | **Critère de sortie S-01 de la phase 1.** 8 sur 8 exigés |
| **Niveau 2** | Le test généré pour cet élément **échoue** sur le bug latent | Démonstration de la capacité de génération. Mesuré et rapporté, **pas** critère de sortie de la phase 1 |

Séparer les deux niveaux évite une confusion coûteuse : un framework qui inventorie sans générer tient déjà S-01, et c'est voulu — S-01 mesure le contre-oracle, pas le générateur.

### 1.3 La paire de fixtures

Le banc d'essai est livré en **deux exemplaires** :

- **`banc-rouge`** — les 8 défauts plantés. Tout défaut non détecté est un échec de phase 1.
- **`banc-vert`** — le jumeau sain : même surface, suite qui couvre, aucun bug latent. **Tout finding émis sur `banc-vert` est un échec de phase 1**, au même titre qu'un défaut manqué.

Le second exemplaire n'est pas un confort. Sans lui, un framework qui signale tout tiendrait S-01 à 100 %.

---

## 2. Le banc d'essai — surface de référence

Application de démonstration : **gestion de commandes de repas**. Périmètre restreint, choisi pour porter les 6 pans avec le moins de code possible.

Stack : Python (FastAPI) + JavaScript (React) + PostgreSQL — cible native `fastapi-saas` de la SaaS Forge, générable par elle.

### 2.1 Surface Front — 5 routes

| Route | Écran | Éléments interactifs attendus |
|---|---|---|
| `/` | Accueil | 2 — lien connexion, lien commandes |
| `/login` | Connexion | 3 — champ email, champ mot de passe, bouton valider |
| `/commandes` | Liste | 5 — filtre statut, tri date, bouton nouvelle, bouton export, pagination |
| `/commandes/:id` | Détail | 6 — champ quantité, sélecteur plat, bouton enregistrer, bouton annuler, bouton supprimer, bouton dupliquer |
| `/admin` | Administration | 4 — import fichier, bouton clôture, bouton purge, filtre utilisateur |

**Total de référence : 5 routes, 20 éléments interactifs.**

### 2.2 Surface API — 7 couples endpoint × méthode

| Endpoint | Méthode | Codes de retour déclarés |
|---|---|---|
| `/api/login` | POST | 200, 401, 422 |
| `/api/commandes` | GET | 200, 401 |
| `/api/commandes` | POST | 201, 400, 401, 422 |
| `/api/commandes/{id}` | GET | 200, 401, 404 |
| `/api/commandes/{id}` | PATCH | 200, 401, 404, 409, 422 |
| `/api/commandes/{id}` | DELETE | 204, 401, 404, 409 |
| `/api/import` | POST | 202, 400, 401, 415 |

**Total de référence : 7 couples, 26 codes de retour déclarés dont 19 codes d'erreur.**

### 2.3 Surface Data — 3 tables, 8 contraintes, 3 migrations

| Table | Colonnes | Contraintes |
|---|---|---|
| `utilisateur` | id, email, mot_de_passe_hash, actif | PK id · UNIQUE email · NOT NULL email · NOT NULL mot_de_passe_hash |
| `commande` | id, utilisateur_id, statut, cree_le | PK id · FK utilisateur_id → utilisateur.id · CHECK statut ∈ (brouillon, validee, annulee) |
| `ligne_commande` | id, commande_id, plat, quantite | PK id · FK commande_id → commande.id · CHECK quantite > 0 |

**Total de référence : 3 tables, 11 colonnes, 8 contraintes hors clés primaires, 3 migrations.**

Migrations : `001_socle` (les 3 tables), `002_statut_commande` (ajout de la contrainte CHECK), `003_index_email` (index unique sur email).

### 2.4 Surface Batch — 1 job, 5 branches

Job `cloture_journaliere` : passe les commandes `validee` du jour en `cloturee`, produit un récapitulatif.

| Branche | Nature |
|---|---|
| B1 | Nominal — commandes valides clôturées |
| B2 | Rejet — commande sans ligne : rejetée avec code `REJ-VIDE` |
| B3 | Rejet — quantité incohérente avec le stock : code `REJ-STOCK` |
| B4 | Reprise — job interrompu, reprise au dernier point de contrôle |
| B5 | Idempotence — second passage sur une journée déjà close : aucun effet |

**Total de référence : 5 branches, 2 codes de rejet, 1 chemin de reprise.**

### 2.5 Surface Fichiers — 1 format, 6 variantes

Import CSV des commandes, via `/api/import`.

| Variante | Nature |
|---|---|
| F1 | UTF-8, séparateur `,` — cas nominal |
| F2 | UTF-8 avec BOM |
| F3 | Latin-1 avec caractères accentués |
| F4 | Séparateur `;` |
| F5 | Ligne vide en fin de fichier |
| F6 | Rapprochement de totaux — la ligne de total du fichier doit égaler la somme des lignes importées |

**Total de référence : 1 format, 6 variantes, 1 règle de rapprochement.**

### 2.6 Surface consolidée — l'inventaire attendu

Ce tableau est **l'oracle de la capacité 1 du contrat d'adaptateur**. Un adaptateur qui énumère la surface du banc d'essai doit produire ces nombres. Un écart est un défaut de l'adaptateur, pas du banc.

| Pan | Grandeur inventoriée | Valeur de référence | Mesuré le 2026-08-02 |
|---|---|---|---|
| Front | Routes | 5 | 5 |
| Front | Éléments interactifs | 20 | 20 |
| API | Couples endpoint × méthode | 7 | 7 |
| API | Codes de retour déclarés | 26 (dont 19 d'erreur) | 26 |
| Data | Tables | 3 | 3 |
| Data | Contraintes hors clés primaires | **13** | 13 |
| Data | Migrations × sens (aller, retour, rejeu) | 9 | 9 |
| Batch | Branches | 5 | 5 |
| Batch | Codes de rejet | 2 | 2 |
| Fichiers | Variantes de format | 6 | 6 |

**Deux corrections apportées après construction du banc, par mesure et non par arbitrage :**

1. **Contraintes Data : 13, pas 8.** Le décompte initial ne retenait que les contraintes *nommées* (`UNIQUE`, `FOREIGN KEY`, `CHECK`). L'adaptateur énumère aussi les **8 colonnes `NOT NULL`**, qui sont des contraintes à part entière et méritent d'être exercées par violation. 5 nommées + 8 `NOT NULL` = 13. La valeur de référence est corrigée à la hausse : elle décrivait moins que ce qui existe.
2. **Codes API : le décompte initial tombait à 25.** L'endpoint `GET /api/commandes` ne déclarait que `200` et `401` ; un `400` (filtre de statut inconnu) a été ajouté pour que la surface tienne les 26 codes annoncés, dont 19 d'erreur.

Les valeurs de la colonne « mesuré » sont la sortie de `forge-tests` sur `banc-vert`, pas une relecture du code.

---

## 3. Les 8 fiches de défauts

Chaque fiche est autoportante : elle dit ce qu'on plante dans le code, ce qu'on plante dans la suite, ce que le framework doit émettre, et ce que contient le jumeau sain.

---

### Fiche D-01 — Parcours Front tronqué

| Champ | Contenu |
|---|---|
| **Statut** | **[FAIT]** — seul défaut réellement constaté du corpus |
| **Pan** | Front |
| **Adaptateur qui doit le détecter** | #1 — crawl de surface Front |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** La suite fournie ne contient que des tests sur `/` et `/login`. Les routes `/commandes`, `/commandes/:id` et `/admin` ne sont jamais atteintes. Sur les 20 éléments interactifs, 5 seulement sont exercés — ceux des deux premières pages.

**Bug latent planté.** Sur `/commandes/:id`, le bouton **dupliquer** crée la commande dupliquée sans recopier ses lignes : la copie est vide. Aucun test ne l'atteint.

**Détection attendue — niveau 1.** Le rapport nomme les **3 routes non atteintes** et les **15 éléments interactifs non exercés**, individuellement. Le ratio de couverture de surface Front sort à 2/5 routes et 5/20 éléments, sous le seuil S-05 (100 % des routes, ≥ 90 % des éléments) → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré pour le bouton dupliquer échoue : la commande dupliquée porte 0 ligne au lieu de n.

**Jumeau sain.** Les 5 routes atteintes, les 20 éléments exercés, le bouton dupliquer recopie les lignes. Aucun finding.

**Pourquoi une suite existante ne l'attrape pas.** La suite est verte : elle passe sur tout ce qu'elle contient. Rien dans son exécution ne signale les 15 éléments qu'elle ignore. L'absence de couverture est silencieuse — c'est le mécanisme central que le framework doit briser.

---

### Fiche H-02 — Codes d'erreur API jamais exercés

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** — frère hypothétique de D-01, aucun cas réel documenté |
| **Pan** | API |
| **Adaptateur** | #5 — contrat REST depuis OpenAPI |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** La suite exerce les 7 couples endpoint × méthode, mais uniquement en **chemin passant** : 7 codes de succès sur 7, **0 code d'erreur sur 19**.

**Bug latent planté.** `POST /api/commandes` renvoie **500** au lieu de **422** quand la quantité est absente du corps de requête : l'exception de validation n'est pas interceptée.

**Détection attendue — niveau 1.** Le rapport nomme les **19 codes d'erreur déclarés et jamais obtenus**, par couple endpoint × méthode × code. Couverture des codes de retour : 7/26, sous le seuil S-04 (100 % des codes d'erreur déclarés) → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré pour `POST /api/commandes` → 422 obtient 500.

**Jumeau sain.** Les 26 codes obtenus au moins une fois ; la validation renvoie 422. Aucun finding.

**Pourquoi une suite existante ne l'attrape pas.** Le générateur écrit le test du cas qu'il vient d'implémenter — le cas passant. La table des codes de retour n'est jamais lue comme une liste à couvrir.

---

### Fiche H-03 — Méthodes HTTP secondaires jamais atteintes

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** |
| **Pan** | API |
| **Adaptateur** | #5 |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** Sur `/api/commandes/{id}`, la suite exerce `GET` mais jamais `PATCH` ni `DELETE`. Sur `/api/import`, `POST` n'est jamais exercé du tout.

**Bug latent planté.** `DELETE /api/commandes/{id}` supprime la commande **sans supprimer ni détacher ses lignes** : les lignes deviennent orphelines et la contrainte de clé étrangère est violée au prochain contrôle d'intégrité.

**Détection attendue — niveau 1.** Le rapport nomme les **3 couples endpoint × méthode non exercés** : `PATCH /api/commandes/{id}`, `DELETE /api/commandes/{id}`, `POST /api/import`. Couverture : 4/7 couples, sous S-04 → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré pour `DELETE` échoue au contrôle d'intégrité qui suit.

**Jumeau sain.** Les 7 couples exercés ; la suppression est en cascade ou refusée avec 409. Aucun finding.

**Distinction avec H-02, à ne pas confondre.** H-02 est un trou sur l'axe **codes de retour**, H-03 sur l'axe **méthodes**. Un framework qui ne détecterait que l'un des deux tiendrait 1 sur 2, pas 2 sur 2. Les deux sont comptés séparément dans S-01.

---

### Fiche H-04 — Contraintes de base jamais violées volontairement

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** |
| **Pan** | Data |
| **Adaptateur** | #12 — base relationnelle éphémère |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** La suite insère des données valides et vérifie qu'elles sont relues. Aucune des **8 contraintes** n'est testée par violation : jamais d'email dupliqué, jamais de clé étrangère orpheline, jamais de quantité nulle ou négative, jamais de statut hors liste.

**Bug latent planté.** La contrainte `CHECK quantite > 0` **est déclarée dans le modèle applicatif mais absente de la migration** : la base accepte une quantité de 0. Le modèle et le schéma divergent.

**Détection attendue — niveau 1.** Le rapport nomme les **8 contraintes jamais exercées par violation**, une par une, avec table et nom de contrainte. Couverture Data : 0/8, sous le seuil S-06 (100 % des contraintes) → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré insère une quantité de 0 en attendant un rejet ; l'insertion réussit. Le finding nomme la divergence entre le modèle et le schéma.

**Jumeau sain.** Les 8 contraintes exercées par violation avec rejet attendu ; la contrainte CHECK présente dans la migration. Aucun finding.

**Pourquoi une suite existante ne l'attrape pas.** Une contrainte est perçue comme une propriété du schéma, donc « vraie par construction ». Personne ne teste ce qui est réputé garanti — et c'est exactement là que la divergence modèle / schéma se loge.

---

### Fiche H-05 — Migrations jamais rejouées ni inversées

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** |
| **Pan** | Data |
| **Adaptateur** | #13 — migrations aller / retour / rejeu |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** La suite applique les 3 migrations à l'aller, sur base vide, une seule fois. Jamais de retour, jamais de rejeu, jamais d'application sur une base déjà peuplée.

**Bug latent planté.** La migration `003_index_email` **n'a pas de fonction de retour** : le retour échoue, et la base reste dans un état intermédiaire non rejouable.

**Détection attendue — niveau 1.** Le rapport nomme les **3 migrations jamais inversées** et les **3 jamais rejouées**, individuellement. Couverture des migrations aller/retour : 0/3, sous S-06 (100 % rejouées à l'aller et au retour) → **FAIL nommé**.

**Détection attendue — niveau 2.** Le retour de `003_index_email` échoue ; le finding nomme la migration et l'état laissé derrière.

**Jumeau sain.** Les 3 migrations passées à l'aller, au retour, et rejouées sur base peuplée ; `003` porte sa fonction de retour. Aucun finding.

---

### Fiche H-06 — Branches de rejet et reprise du batch jamais parcourues

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** |
| **Pan** | Batch |
| **Adaptateur** | #15 — jobs et workers *(promu en phase 1 par la décision D-C)* |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** La suite exerce la branche nominale B1 seulement. B2 (rejet commande vide), B3 (rejet stock), B4 (reprise après interruption) et B5 (idempotence) ne sont jamais parcourues.

**Bug latent planté.** Le job **n'est pas idempotent** : un second passage sur une journée déjà close re-clôture les commandes et double le récapitulatif. B5 est fausse dans le code.

**Détection attendue — niveau 1.** Le rapport nomme les **4 branches non parcourues** et les **2 codes de rejet jamais obtenus** (`REJ-VIDE`, `REJ-STOCK`). Couverture Batch : 1/5 branches, sous le seuil S-07 (≥ 90 % des branches) → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré pour B5 lance le job deux fois et constate le doublement du récapitulatif.

**Jumeau sain.** Les 5 branches parcourues, les 2 codes de rejet obtenus ; second passage sans effet. Aucun finding.

**Pourquoi une suite existante ne l'attrape pas.** Le rejet et la reprise sont perçus comme des cas rares. Ils sont en réalité les seuls chemins qui s'exécutent un jour d'incident — c'est-à-dire le jour où le test aurait servi.

---

### Fiche H-07 — Une seule variante de format de fichier testée

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** |
| **Pan** | Fichiers |
| **Adaptateur** | #16 — import/export fichiers *(promu en phase 1 par la décision D-C)* |
| **Contre-oracle** | Couverture de surface |

**Trou de couverture planté.** La suite importe un seul fichier : UTF-8, séparateur `,`, sans BOM, sans ligne vide, sans contrôle de total. Les variantes F2 à F6 ne sont jamais soumises.

**Bug latent planté.** Le parseur ne retire pas le **BOM UTF-8** : la première colonne de la première ligne est lue avec un caractère invisible en préfixe, et la commande correspondante est rejetée silencieusement — sans erreur, sans ligne dans le récapitulatif.

**Détection attendue — niveau 1.** Le rapport nomme les **5 variantes non soumises** (F2 à F6) et la **règle de rapprochement de totaux jamais vérifiée**. Couverture Fichiers : 1/6, sous S-07 (100 % des formats déclarés) → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré pour F2 constate qu'une ligne du fichier n'arrive pas en base, et le test F6 constate l'écart entre le total déclaré et la somme importée.

**Jumeau sain.** Les 6 variantes soumises, le rapprochement vérifié ; le parseur retire le BOM. Aucun finding.

**Note sur le rejet silencieux.** Ce bug latent est le plus proche d'un incident réel : il ne produit ni exception, ni journal, ni alerte. Seul le rapprochement de totaux le révèle. C'est la raison pour laquelle F6 est une variante à part entière et non un raffinement.

---

### Fiche H-08 — Assertions permissives

| Champ | Contenu |
|---|---|
| **Statut** | **[HYP]** |
| **Pan** | Transverse — planté côté Back Python |
| **Adaptateur** | #10 — mutation Python |
| **Contre-oracle** | **Score de mutation** — le seul défaut du corpus que la couverture de surface ne voit pas |

**Trou de couverture planté — aucun.** C'est le point de la fiche. La fonction de calcul du montant d'une commande **est exercée** par la suite : elle apparaît couverte à 100 %.

**Ce qui est planté à la place.** Les assertions de ses tests vérifient uniquement que le résultat **n'est pas nul** et que l'appel **ne lève pas d'exception**. Aucune n'en vérifie la valeur.

**Bug latent planté.** La fonction applique la remise **avant** la taxe au lieu de l'appliquer après : le montant est faux d'environ 2 %, jamais nul, jamais exceptionnel. La suite reste verte.

**Détection attendue — niveau 1.** Le score de mutation sur la fonction de calcul sort **très en dessous** du seuil S-03 (≥ 70 % sur le périmètre critique) : les mutants qui changent l'ordre des opérations, l'opérateur, ou la valeur du taux **survivent tous**. Le rapport nomme **chaque mutant survivant** avec sa ligne → **FAIL nommé**.

**Détection attendue — niveau 2.** Le test généré vérifie la valeur exacte sur un cas de référence calculé à la main, et échoue.

**Jumeau sain.** Mêmes tests, mais assertions sur la valeur exacte ; la fonction applique la remise après la taxe. Score de mutation au-dessus du seuil. Aucun finding.

**Ce que cette fiche démontre, et qu'aucune autre ne démontre.** H-08 est la justification opérationnelle du doublet de contre-oracles du CDC §3.2. La couverture de surface est **verte** sur ce défaut : l'élément est atteint. Sans le score de mutation, le framework le manque. Et symétriquement, sur D-01 à H-07, le score de mutation seul aurait été flatteur — calculé sur le périmètre étroit réellement atteint. **Un framework qui ne porterait qu'un seul des deux contre-oracles échouerait à S-01, par construction.**

---

## 4. Traçabilité — défaut, adaptateur, seuil, finding attendu

| Défaut | Pan | Adaptateur | Contre-oracle | Seuil franchi | Finding attendu, niveau 1 |
|---|---|---|---|---|---|
| **D-01** | Front | #1 | Surface | S-05 | 3 routes + 15 éléments nommés |
| **H-02** | API | #5 | Surface | S-04 | 19 codes d'erreur nommés |
| **H-03** | API | #5 | Surface | S-04 | 3 couples endpoint × méthode nommés |
| **H-04** | Data | #12 | Surface | S-06 | 8 contraintes nommées |
| **H-05** | Data | #13 | Surface | S-06 | 3 migrations × 2 sens nommées |
| **H-06** | Batch | #15 | Surface | S-07 | 4 branches + 2 codes de rejet nommés |
| **H-07** | Fichiers | #16 | Surface | S-07 | 5 variantes + 1 règle de rapprochement nommées |
| **H-08** | Transverse | #10 | **Mutation** | S-03 | Mutants survivants nommés avec leur ligne |

**Lecture de ce tableau** : 7 défauts sur 8 relèvent de la couverture de surface, 1 seul de la mutation. Cette asymétrie reflète le corpus, pas l'importance relative des deux contre-oracles — elle découle du fait que le seul défaut réellement constaté, D-01, est un défaut de surface. **[HYP]** Toute conclusion du type « la surface compte davantage que la mutation » serait une extrapolation depuis un corpus de calibration à n = 1, et n'est pas soutenue par ce document.

---

## 5. Ce que ce corpus ne démontre pas

À reprendre tel quel dans le rapport de phase 1, au titre de la limite déclarée.

- **7 des 8 défauts sont fabriqués par nous.** Réussir S-01 démontre que le framework détecte ce qu'on lui a appris à chercher. La phase 2, sur un projet réel non conçu pour lui, est la seule qui puisse produire l'autre preuve.
- **Aucun défaut ne porte sur les pans non fonctionnels** — performance, sécurité, résilience, accessibilité. Ces axes sont couverts par des adaptateurs réutilisés du registre `quality-oracles`, dont la recette est déjà faite ailleurs, mais ils ne sont pas éprouvés par ce corpus.
- **Aucun défaut ne porte sur le JavaScript en profondeur** — conséquence assumée de la décision D-G : les adaptateurs #2, #9 et #11 sont hors périmètre de phase 1. Le pan est marqué partiellement instrumenté.
- **Le banc d'essai est petit par construction.** Un framework qui tient S-01 sur 5 routes et 3 tables n'a pas démontré qu'il tient sur 200 routes et 80 tables. La montée en taille est un risque à traiter en phase 2, pas une propriété acquise en phase 1.

---

## 6. Questions ouvertes propres à ce livrable

**o) Le banc d'essai est-il généré par la SaaS Forge ou écrit à la main ?** — Recommandé : généré par la forge en greenfield, la cible `fastapi-saas` correspondant exactement à la stack voulue, puis dégradé à la main pour y planter les 8 défauts. **Défaut appliqué** : génération par la forge, avec repli sur une écriture manuelle si la chaîne A→E n'aboutit pas.

**p) Les deux exemplaires du banc sont-ils deux dépôts ou deux branches ?** — Recommandé : **deux branches** d'un même dépôt, `rouge` et `vert`, pour que la surface de référence reste identique par construction et que toute dérive entre les deux soit visible dans un écart de branche. **Défaut appliqué** : deux branches.

**q) Le bug latent de niveau 2 est-il obligatoire pour chaque fiche ?** — Recommandé : oui, il est déjà spécifié pour les 8. Il ne conditionne pas S-01 mais rend la démonstration de génération mesurable dès la phase 1. **Défaut appliqué** : les 8 bugs latents sont plantés.

---

*Fin du corpus. Aucune ligne de code produite.*
