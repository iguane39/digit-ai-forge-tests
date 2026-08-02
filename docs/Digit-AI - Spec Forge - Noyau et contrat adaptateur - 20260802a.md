# Spécification du noyau — contrat d'adaptateur, référentiel, rapport

**Référence** : Digit-AI - Spec Forge - Noyau et contrat adaptateur - 20260802a
**Date** : 2026-08-02
**Amont** : CDC section 4 (architecture) et section 4.6 (reste à préciser) · décision **D-F** (montage B, produit autonome)
**Objet** : livrable **L4**. Ferme les quatre points laissés ouverts en 4.6 du CDC : environnements d'exécution, format du référentiel de tests, format du rapport, contrat d'adaptateur détaillé.

Spécification, pas implémentation : aucune ligne de code. Les structures sont décrites en tables de champs.

---

## 1. Périmètre du noyau

### 1.1 Ce que le noyau porte

| Composant | Rôle |
|---|---|
| **Cotation du risque** | Applique criticité × probabilité × coût de détection tardive à chaque élément de surface remonté par un adaptateur |
| **Référentiel de tests** | Persiste les tests connus, leur lien de traçabilité et leur statut. Versionné, complétable, avec journal de décisions |
| **Registre d'adaptateurs** | Liste les adaptateurs, leur couple pan × technologie, leur statut `todo` / `ok`, leur paire de fixtures |
| **Agrégateur de verdict** | Consolide les sorties d'adaptateurs, applique les seuils, produit le verdict global |
| **Producteur de rapport** | Rend la couverture, les findings, les pans non couverts, les écarts résiduels |
| **Boucle bornée** | Trois itérations, puis livraison avec écarts résiduels |
| **Interface en ligne de commande** | Point d'entrée unique du produit (montage B) |

### 1.2 Ce que le noyau ne porte pas

Le noyau **n'exécute aucun test**, **ne lit aucun code source applicatif**, **ne connaît aucune technologie**. Il ne sait rien de Playwright, de pytest ou de PostgreSQL. Toute connaissance de stack vit dans un adaptateur.

**Règle de non-contamination** : si une modification du noyau exige de nommer une technologie, c'est que la capacité appartient à un adaptateur. Cette règle est vérifiable — le nom d'un outil de test dans le noyau est un défaut.

### 1.3 Ce que le noyau réutilise plutôt que de le réécrire

Conformément aux verdicts de frontière du CDC section 2 :

| Besoin | Origine |
|---|---|
| Lancement de process portable | Patron de `conductor/process.py` — arguments en liste, résolution du binaire, pas de shell, délai borné |
| Contrat de sortie à verdict et `non_juge` | Standard des oracles de `quality-oracles` |
| Scaffolder transactionnel | Patron de `write-an-oracle` — validations avant écriture, refus sans modification partielle |
| Registre à statuts | Patron de `registre-oracles.json` |
| Boucle à 3 itérations | Valeur de `supervisor.py:GATE_MAX_RETRIES` |

---

## 2. Contrat d'adaptateur

### 2.1 Identité

Un adaptateur est identifié par un couple **(pan, technologie)**. Deux adaptateurs ne peuvent pas partager le même couple.

| Champ | Nature | Obligatoire |
|---|---|---|
| `nom` | Identifiant court, en minuscules à tirets | oui |
| `pan` | `front` · `api` · `back` · `data` · `batch` · `fichiers` · `nf` · `transverse` | oui |
| `technologie` | Marqueur de stack qu'il sait traiter | oui |
| `version` | Version de l'adaptateur | oui |
| `capacites` | Sous-ensemble des 5 capacités réellement fournies | oui |
| `statut` | `todo` · `ok` | oui |
| `fixtures` | Chemins de la paire rouge / verte | oui pour le statut `ok` |

### 2.2 Les cinq capacités

| # | Capacité | Obligatoire | Ce qu'elle produit |
|---|---|---|---|
| 1 | **Inventaire de surface** | **Oui — éliminatoire** | La liste des éléments testables, un identifiant stable par élément |
| 2 | **Génération de cas** | Non | Des cas de test rattachés à un élément de surface et à un risque |
| 3 | **Harnais d'exécution** | Non | Le résultat d'exécution d'une suite, sous contrainte de déterminisme |
| 4 | **Fabrique de données** | Non | Fixtures, seeding, teardown, cas limites |
| 5 | **Contre-oracle** | **Oui — au moins un des deux** | Un ratio de couverture de surface, ou un score de mutation |

**Loi d'admission** : *un adaptateur qui ne sait pas énumérer sa surface n'est pas un adaptateur.* La capacité 1 est éliminatoire. Une capacité absente est **déclarée**, jamais simulée : elle apparaît dans le champ `non_juge` de la sortie.

### 2.3 Identifiant stable d'élément de surface

Chaque élément inventorié porte un identifiant reproductible d'une exécution à l'autre. C'est ce qui permet de dire « cet élément précis n'est pas couvert » plutôt que « il manque 15 éléments ».

| Pan | Forme de l'identifiant | Exemple |
|---|---|---|
| Front | `route:<chemin>` · `element:<chemin>#<sélecteur stable>` | `element:/commandes/:id#bouton-dupliquer` |
| API | `endpoint:<méthode> <chemin>` · `code:<méthode> <chemin>=<code>` | `code:POST /api/commandes=422` |
| Data | `table:<nom>` · `contrainte:<table>.<nom>` · `migration:<id>:<sens>` | `contrainte:ligne_commande.quantite_positive` |
| Batch | `branche:<job>/<id>` · `rejet:<job>/<code>` | `rejet:cloture_journaliere/REJ-VIDE` |
| Fichiers | `variante:<format>/<id>` | `variante:csv-commandes/F2-bom` |
| Back | `fonction:<module>.<nom>` · `mutant:<fichier>:<ligne>:<opérateur>` | `mutant:calcul.py:42:swap-ordre` |

**Règle de stabilité** : un identifiant qui change parce que le code a été reformaté — indentation, renommage de variable locale, déplacement de ligne — est un identifiant défectueux. La conséquence pratique : un élément apparaîtrait comme « nouvellement non couvert » à chaque reformatage, et le référentiel deviendrait illisible.

### 2.4 Contrat de sortie

Sortie unique, en JSON, sur la sortie standard. Champs :

| Champ | Nature | Obligatoire | Contenu |
|---|---|---|---|
| `adaptateur` | chaîne | oui | Nom et version |
| `pan` | chaîne | oui | Pan traité |
| `cible` | chaîne | oui | Chemin ou identifiant du projet analysé |
| `verdict` | `PASS` · `FAIL` · `SKIP` | oui | `SKIP` uniquement si une dépendance externe manque, avec la raison |
| `surface` | objet | si capacité 5 par surface | `inventorie` (entier), `exerce` (entier), `ratio` (réel), `seuil` (réel), `elements_non_exerces` (liste d'identifiants) |
| `mutation` | objet | si capacité 5 par mutation | `mutants_viables`, `tues`, `score`, `survivants` (liste d'identifiants avec ligne) |
| `findings` | liste | oui, éventuellement vide | Un objet par défaut constaté — voir 2.5 |
| `non_juge` | liste | **oui** | Ce que l'adaptateur ne couvre pas, en clair. Une liste vide est un refus d'admission |
| `duree_s` | réel | oui | Temps d'exécution, pour le contrôle du plafond S-08 |

**Codes de sortie** : `0` verdict PASS · `1` verdict FAIL · `2` erreur d'exécution de l'adaptateur lui-même.

La distinction entre `1` et `2` est structurante : un adaptateur qui plante n'est pas un projet en défaut. Confondre les deux produirait des rouges qui ne veulent rien dire.

### 2.5 Structure d'un finding

| Champ | Obligatoire | Contenu |
|---|---|---|
| `id` | oui | Identifiant stable de l'élément concerné (2.3) |
| `classe` | oui | `element-non-exerce` · `mutant-survivant` · `seuil-non-tenu` · `divergence` |
| `localisation` | oui | `fichier:ligne` quand elle existe, sinon l'identifiant seul |
| `message` | oui | Une phrase, factuelle, sans jugement |
| `risque` | si coté | Score de risque de l'élément |
| `severite` | oui | `bloquant` · `signale` |

**Règle du finding nommé** : un finding porte toujours un élément identifié. Un finding du type « couverture insuffisante » sans liste d'éléments est refusé par le noyau — c'est précisément l'absence silencieuse que le framework existe pour supprimer.

### 2.6 Déterminisme imposé

Un adaptateur portant la capacité 3 déclare, dans sa sortie, comment il tient les trois contraintes :

| Contrainte | Ce qui est exigé |
|---|---|
| **Graine figée** | Toute source d'aléa reçoit une graine fixée, journalisée dans la sortie |
| **Horloge figée** | Toute lecture d'horloge passe par un point unique, substituable |
| **Indépendance à l'ordre** | La suite rend le même verdict quel que soit l'ordre d'exécution — vérifié par une exécution en ordre inversé |

Une contrainte non tenue est déclarée en `non_juge`, jamais tue. **[HYP]** L'indépendance à l'ordre est la plus coûteuse à vérifier ; son coût réel sera mesuré en phase 1 et le seuil de vérification pourra être revu.

---

## 3. Référentiel de tests versionné

### 3.1 Ce qu'il est, et pourquoi il existe

Le référentiel est la mémoire du framework. Sans lui, chaque exécution repart de zéro et le CDC perd sa promesse — rendre la qualité **enrichissable dans le temps**, sans dépendre de la mémoire d'un humain.

Deux fichiers, versionnés avec le projet analysé ou à côté de lui :

| Fichier | Rôle |
|---|---|
| `referentiel-tests.json` | L'état courant : un enregistrement par test connu |
| `journal-decisions.md` | L'historique des arbitrages : ce qui a été écarté, quand, et pourquoi |

Séparer l'état et l'historique évite le travers du fichier unique qui grossit sans être relu.

### 3.2 Enregistrement d'un test

| Champ | Obligatoire | Contenu |
|---|---|---|
| `id` | oui | Identifiant du test |
| `element` | oui | Identifiant de l'élément de surface couvert (2.3) |
| `risque` | **oui** | Identifiant du risque ou de l'exigence couverte — **seuil S-11 à 100 %** |
| `score_risque` | oui | Cotation au moment de la génération |
| `adaptateur` | oui | Adaptateur qui l'a produit |
| `origine` | oui | `genere` · `existant` · `humain` |
| `statut` | oui | `actif` · `quarantaine` · `retire` |
| `empreinte` | oui | Empreinte du contenu du test, pour détecter une modification hors framework |
| `cree_le`, `vu_le` | oui | Dates de création et de dernière exécution |

**Règle de suppression** : un test sans champ `risque` est supprimable. Ce n'est pas une recommandation d'hygiène — c'est la condition qui empêche le référentiel de se remplir de tests que personne ne sait pourquoi il exécute.

### 3.3 Quarantaine

| Règle | Valeur |
|---|---|
| Entrée en quarantaine | Test instable au sens du seuil S-09 |
| Durée maximale | **5 jours ouvrés** |
| Sortie de quarantaine | **3 exécutions consécutives vertes** |
| Dépassement de durée | Passage en `retire`, inscrit au journal de décisions avec son motif |

Un test en quarantaine **n'est pas compté** dans la couverture de surface : son élément redevient non exercé. Le compter serait masquer un trou derrière un test qu'on a cessé de croire.

### 3.4 Journal de décisions

Une entrée par arbitrage, en append seul, jamais réécrite. Champs : date, élément concerné, décision, motif, auteur — humain ou framework.

Sont journalisés : le passage d'un test en `retire`, l'acceptation d'un écart résiduel après épuisement de la boucle, la mise hors périmètre d'un élément, la révision d'un seuil.

---

## 4. Format du rapport

### 4.1 Sections obligatoires, dans cet ordre

| # | Section | Contenu |
|---|---|---|
| 1 | **En-tête** | Projet, date, version du noyau, liste des adaptateurs actifs avec leur version et leur statut |
| 2 | **Couverture par pan** | Une ligne par pan : inventorié, exercé, ratio, seuil, verdict |
| 3 | **Pans non couverts** | Un pan sans adaptateur figure ici, nommé, avec la mention « adaptateur absent ». **Jamais omis** |
| 4 | **Findings nommés** | Un par élément, triés par score de risque décroissant |
| 5 | **Contre-oracles** | Surface et mutation, **côte à côte** — voir 4.2 |
| 6 | **Écarts résiduels** | Après épuisement de la boucle : ce qui reste ouvert, avec son motif |
| 7 | **Non jugé** | Consolidation des `non_juge` de tous les adaptateurs |
| 8 | **Traçabilité** | Part des tests portant un lien vers un risque, seuil S-11 |

### 4.2 La règle d'affichage conjoint

**Le score de mutation ne peut jamais être publié seul.** Le rapport affiche, sur la même vue et pour le même périmètre, le score de mutation **et** le taux de couverture de surface qui lui correspond.

Cette règle est vérifiable mécaniquement : un rapport contenant un champ `mutation` sans champ `surface` pour le même pan est un rapport refusé par le noyau, avant émission.

Motif, à rappeler dans le rapport lui-même : un score de mutation se calcule sur le seul périmètre atteint. Une suite qui n'exerce que la page d'accueil peut afficher 95 %. Publié seul, il flatte d'autant plus que la suite est incomplète.

### 4.3 La règle de non-masquage

| Interdit | Exigé à la place |
|---|---|
| Un verdict vert global sur un projet dont un pan n'a pas d'adaptateur | Verdict **partiel**, avec la liste nommée des pans non instrumentés |
| Un pourcentage agrégé tous pans confondus | Un ratio par pan, plus le détail des éléments non exercés |
| Une absence de section pour un pan sans donnée | Une section présente portant « aucune donnée — adaptateur absent » |

### 4.4 Deux rendus, une source

Le rapport est produit une fois, en JSON, et rendu en deux formes : un fichier lisible par un humain, et la sortie machine consommée par un gate d'intégration continue. Les deux dérivent de la même source — un écart entre les deux serait un défaut du noyau.

---

## 5. Environnements d'exécution

Quatrième point ouvert de la section 4.6 du CDC.

| Environnement | Usage | Contrainte |
|---|---|---|
| **Local** | Développement d'un adaptateur, mise au point | Aucune donnée réelle |
| **Conteneur** | Exécution reproductible d'un adaptateur | Image épinglée par version |
| **Base éphémère** | Adaptateurs #12 et #13 | Base créée et détruite par exécution, jamais partagée entre deux exécutions parallèles |
| **Intégration continue** | Gate | Plafond S-08 de 15 minutes, découpage possible en tâches parallèles |

**Doublure ou bac à sable** : la règle par défaut est la **doublure** pour tout service tiers — payant, distant, ou à effet de bord. Le bac à sable réel n'est employé que si le contrat du service ne peut pas être doublé fidèlement, et cet emploi est journalisé. Motif : un test qui appelle un service tiers réel est un test dont le verdict dépend d'un tiers.

**Aucune donnée de production non anonymisée**, en application du garde-fou G-4 et de la décision (c) — jeux synthétiques uniquement.

---

## 6. Interface en ligne de commande

Montage B (décision D-F) : Forge Tests est invocable comme n'importe quel outil, y compris par le gate code de la SaaS Forge.

| Commande | Effet | Écrit dans le projet analysé |
|---|---|---|
| `inventaire` | Énumère la surface, écrit l'inventaire | Non |
| `coter` | Applique le modèle de risque à l'inventaire | Non |
| `generer` | Produit les cas de test manquants | **Oui — branche dédiée, sous feu vert** |
| `executer` | Lance les suites via les harnais | Non |
| `rapport` | Produit le rapport | Non |
| `adaptateur creer` | Scaffolder transactionnel | Non — écrit dans Forge Tests |
| `adaptateur admettre` | Rejoue la paire de fixtures, passe le statut à `ok` | Non |

**Lecture seule par défaut** : seule `generer` écrit dans le projet analysé, sur une branche dédiée et sous feu vert humain — garde-fou G-1 et G-7. Toutes les autres commandes sont sans effet sur la cible.

**Codes de sortie** : `0` tous les seuils tenus · `1` au moins un seuil non tenu · `2` erreur d'exécution · `3` diagnostic partiel, un pan au moins sans adaptateur. Le code `3` est distinct de `0` : un diagnostic partiel n'est pas un succès.

---

## 7. Ce que cette spécification laisse ouvert

- **Le format d'échange entre `generer` et le harnais** : la façon dont un cas généré devient un fichier de test relève de chaque adaptateur, et n'est pas normalisée ici. **[HYP]** Une normalisation prématurée coûterait plus qu'elle ne rapporte tant qu'un seul adaptateur générateur existe.
- **La cotation automatique du risque** : le CDC fixe la grille, mais l'attribution des notes de probabilité repose sur des signaux — date de dernière modification, historique d'incident — dont la disponibilité dépend du projet. **[NV]** À mesurer en phase 1.
- **La parallélisation en intégration continue** : le plafond S-08 de 15 minutes peut exiger un découpage. Le mécanisme n'est pas spécifié ici.

---

## 8. Questions ouvertes propres à ce livrable

**r) Le référentiel de tests vit-il dans le projet analysé ou à côté ?** — Recommandé : **dans le projet analysé**, versionné avec lui, pour que l'historique de couverture suive le code plutôt que la machine qui l'a analysé. Contrepartie assumée : cela suppose un droit d'écriture, donc un feu vert, sur un projet client. **Défaut appliqué** : dans le projet, avec repli à côté si l'écriture est refusée.

**s) Le code de sortie `3` (diagnostic partiel) est-il bloquant en intégration continue ?** — Recommandé : **non bloquant par défaut, configurable**. Le rendre bloquant d'emblée rendrait le framework inutilisable sur tout projet dont un pan n'a pas encore d'adaptateur, c'est-à-dire sur tous au début. **Défaut appliqué** : non bloquant, et la liste des pans non couverts remonte dans le rapport.

**t) L'empreinte de test sert-elle à bloquer une modification hors framework ?** — Recommandé : **non, seulement à la signaler**. Bloquer reviendrait à s'approprier les tests du projet. **Défaut appliqué** : signalement au rapport, section écarts.

---

*Fin de la spécification. Aucune ligne de code produite.*
