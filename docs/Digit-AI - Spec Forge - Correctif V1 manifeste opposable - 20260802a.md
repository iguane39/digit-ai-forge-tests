# Spécification du correctif V-1 — le manifeste opposable doit primer sur le marqueur curé

**Référence** : Digit-AI - Spec Forge - Correctif V1 manifeste opposable - 20260802a
**Date** : 2026-08-02
**Dépôt visé** : `iguane39/digit-ai-saas-forge`, snapshot `20f3f0a` (2026-07-09)
**Amont** : CDC section 1.5 verrou V-1 · décisions **D-B** (méthode) et **D-E** (branche dédiée + pull request)
**Objet** : livrable **L1**. Décrit le défaut, la correction, le plan de test et le risque de régression.

---

## 1. Le défaut

### 1.1 Ce qui est constaté

`conductor/onramp/__init__.py:select_onramp` route le mode brownfield en interrogeant d'abord `detect_stack(repo)` :

| Stack détectée | Route prise | Profil appliqué | `resolve_profile` appelé ? |
|---|---|---|---|
| `fastapi` (un `pyproject.toml` à la racine) | `NoOnramp` ou `AdapterOnramp` | `FASTAPI_SAAS`, codé en dur, `has_ui = True` | **Non** |
| `node-ts` (un `package.json` à la racine) | `BuilderOnramp()` sans profil | `NODE_TS`, curé, `has_ui = True` | **Non** |
| `generic` | `BuilderOnramp(profile=…)` | Profil résolu par cascade | Oui |

Or `resolve_profile` est **le seul point du code où le manifeste `.forge/profile.toml` est lu** — c'est sa branche ①, celle qui rend le manifeste « opposable » au sens de P-18.

### 1.2 Conséquence

Un dépôt qui déclare explicitement son profil par manifeste voit cette déclaration **ignorée** dès lors qu'il porte un `pyproject.toml` ou un `package.json` à la racine. Le profil curé s'impose, avec `has_ui = True`, et par voie de conséquence :

- le gate design devient applicable à un produit sans interface ;
- `AdapterOnramp.prepare` **écrit un `design/DESIGN.md` par défaut** dans le dépôt de l'utilisateur (verrou V-2) ;
- la baseline capturée inclut un gate qui n'a pas d'objet, et son résultat entre dans le gate de non-régression.

### 1.3 Portée réelle du défaut

Le défaut ne concerne pas que Forge Tests. Il touche **tout dépôt Python ou Node sans interface** : bibliothèque, outil en ligne de commande, service sans front, travailleur asynchrone. C'est-à-dire une part importante des dépôts sur lesquels la forge peut être invoquée en brownfield.

### 1.4 Ce qui n'est pas en cause

`resolve_profile` **fonctionne correctement** : sa branche ① lit le manifeste et le fait primer, y compris devant un marqueur curé. Le test `test_manifest_wins_over_inference` le démontre déjà.

Le défaut est une **inversion de priorité dans le routage**, pas une capacité manquante. La correction n'ajoute aucune fonctionnalité : elle rend atteignable un chemin qui existe et qui est testé.

### 1.5 Pourquoi la suite existante ne l'attrape pas

`test_manifest_wins_over_inference` construit son dépôt avec la fonction `_fullstack`, dont le commentaire précise : *« backend Flask + frontend React, AUCUN marqueur racine »*. Le dépôt est donc classé `generic`, et le test n'exerce que la branche où `resolve_profile` est déjà appelé.

**Aucun test ne construit un dépôt portant à la fois un marqueur curé à la racine et un manifeste.** Le trou de couverture est exactement le trou du corpus de la section 0 du CDC — un élément de surface, ici une combinaison d'entrées, jamais exercé, et donc silencieux.

---

## 2. La correction

### 2.1 Principe

**Le manifeste est opposable : il prime sur tout autre signal, marqueur curé compris.**

Formulé en négatif, ce qui est plus vérifiable : aucune détection de stack ne doit être consultée tant que la présence du manifeste n'a pas été écartée.

### 2.2 Changement dans `conductor/profiles.py`

Extraire le chemin du manifeste, aujourd'hui écrit en dur au milieu de `resolve_profile`, vers une constante de module et un prédicat exposé.

| Élément | Nature | Rôle |
|---|---|---|
| `MANIFEST_RELPATH` | Constante de module | Chemin relatif `.forge/profile.toml`, défini une seule fois |
| `has_manifest(repo)` | Prédicat public | Vrai si le dépôt porte un manifeste |

`resolve_profile` utilise le prédicat au lieu de reconstruire le chemin. Aucun changement de comportement pour cette fonction.

**Motif** : sans cette extraction, le chemin `.forge/profile.toml` serait écrit dans deux modules. Deux définitions d'un même chemin finissent par diverger.

### 2.3 Changement dans `conductor/onramp/__init__.py`

Dans `select_onramp`, sur le chemin brownfield, **avant** l'appel à `detect_stack` : si le dépôt porte un manifeste, résoudre le profil par la cascade et retourner un `BuilderOnramp` portant ce profil et la confiance `manifest`.

Le reste du routage est inchangé : un dépôt sans manifeste suit exactement le chemin actuel.

### 2.4 Pourquoi `BuilderOnramp` et pas `NoOnramp`

`BuilderOnramp` est la seule bretelle qui accepte un profil injecté, qui conditionne l'écriture du `DESIGN.md` à `profile.has_ui`, et qui alimente `declared_degradation` et `profile_confidence`. `NoOnramp` et `AdapterOnramp` codent leur profil en dur — les router sur un profil déclaré exigerait de les modifier, alors que la bretelle adéquate existe.

### 2.5 Amélioration de libellé — optionnelle, à trancher

`BuilderOnramp.prepare` produit systématiquement la note : *« Profil 'X' synthétisé (confiance : … ) »*. Pour un profil issu d'un manifeste, le mot **synthétisé** est faux : le profil est **déclaré** par l'utilisateur, il n'est le fruit d'aucune inférence.

Une note inexacte dans `declared_degradation` remonte au point de validation humaine HITL-0 et invite à valider une dégradation qui n'en est pas une.

**Recommandation** : distinguer les deux libellés selon la confiance. **Défaut appliqué si non tranché** : correction incluse dans la même pull request, car elle touche la même fonction et le même sujet.

---

## 3. Plan de test

Trois cas à ajouter dans `tests/test_profile_resolution.py`, section §7.2 « Manifeste prioritaire (P-18) », au plus près du test existant.

| # | Cas | Ce qu'il vérifie | Ce qu'il aurait attrapé |
|---|---|---|---|
| **T-1** | Dépôt portant `pyproject.toml` **et** un manifeste déclarant `has_ui = false` | `select_onramp` retourne un `BuilderOnramp` ; le profil porte le nom déclaré ; la confiance est `manifest` | Le verrou V-1 sur la branche `fastapi` |
| **T-2** | Le même dépôt, après `prepare` | **Aucun `design/DESIGN.md` n'est créé** ; le substrat porte `profile_confidence == "manifest"` | Le verrou V-2 — l'écriture non sollicitée dans le dépôt de l'utilisateur |
| **T-3** | Dépôt portant `package.json` **et** un manifeste | Même conclusion que T-1 | Le même verrou sur la branche `node-ts`, qui serait sinon corrigée sans être couverte |

**Non-régression** : les tests existants `test_curated_fastapi_resolves_curated`, `test_curated_fastapi_distance_a_no_hitl0_degradation`, `test_manifest_wins_over_inference` et `test_fullstack_is_generic_and_does_not_raise` doivent rester verts sans modification. Aucun ne construit de dépôt à manifeste **et** marqueur racine ; aucun n'est donc affecté par le changement de routage.

**Gate à repasser** : `ruff check`, `mypy --strict`, `pytest` — les trois étapes du workflow `double-gate`.

---

## 4. Risques

| Risque | Évaluation | Traitement |
|---|---|---|
| Un dépôt aujourd'hui routé vers `NoOnramp` bascule vers `BuilderOnramp` | **Seulement s'il porte un manifeste.** Un dépôt sans manifeste suit le chemin inchangé | Aucun traitement nécessaire ; le comportement change uniquement pour qui l'a explicitement demandé en écrivant un manifeste |
| Perte du catalogue de briques pour un dépôt à manifeste | Réel : `BuilderOnramp` déclare un catalogue vide | Déjà déclaré dans `declared_degradation`. C'est le comportement attendu : un dépôt qui déclare son profil ne demande pas le scaffold SaaS |
| Perte de la distance A / C pour un dépôt FastAPI à manifeste | Réel | Assumé : écrire un manifeste, c'est refuser la normalisation automatique vers la cible |
| Régression de non-détection sur la branche `generic` | Nul — la branche est inchangée, `resolve_profile` y était déjà appelé | Couvert par les tests existants |

---

## 5. Modalités de livraison

Conformément à la décision **D-E** et au garde-fou **G-1** du CDC :

| Point | Modalité |
|---|---|
| Branche | Dédiée, nommée d'après le correctif |
| Base | Branche principale du dépôt, jamais modifiée directement |
| Livraison | Pull request, description reprenant les sections 1 à 4 du présent document |
| Fusion | **Non automatique** — décision humaine, cohérente avec le verrouillage `auto_pr_merge` de la forge elle-même |

---

*Fin de la spécification. Aucune ligne de code dans ce document ; l'implémentation est le livrable L2.*
