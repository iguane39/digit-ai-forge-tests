"""Adaptateur Qualif populée — parcours navigateur d une instance SERVIE et PEUPLÉE (A-4).

Généralisation du prototype `forge/etapes/mep/qualif_populee.py` d ASD Mail Manager (14 pages,
Playwright, staging peuplé). Le prototype prouvait la valeur du contrôle ; il était écrit POUR
un produit — routes en dur, marqueurs en dur, peuplement en dur. Ici le même contrôle devient
un pan du framework : les routes se découvrent, les marqueurs se dérivent, le peuplement reste
la responsabilité du projet audité (c est lui qui sait ce que « peuplé » veut dire chez lui).

Ce que le pan mesure, et que rien d autre ne mesure :

  - **0 erreur serveur** — une route qui rend un 5xx, une trace Python ou une page d exception
    de gabarit. La couverture endpoint x code ne la voit pas : elle mesure ce que la SUITE
    atteint, et une suite verte n atteint pas la page que l utilisateur ouvre en premier ;
  - **0 erreur console** — une exception JavaScript non rattrapée casse l interface sans
    qu aucun test serveur ne bronche ;
  - **un marqueur de contenu par route** — une page qui répond 200 en n affichant rien est un
    faux vert. Le marqueur est configurable ; à défaut il est dérivé du titre de la page ;
  - **élément interactif -> effet, DYNAMIQUE** — pendant du contrôle statique RT-7. Le pan
    `interface` lit les gabarits ; celui-ci interroge le DOM RENDU par le navigateur, via le
    protocole DevTools : il voit donc les gestionnaires posés à l exécution par un framework,
    que l analyse statique déclare explicitement hors de sa portée.

**Aucun clic n est émis.** L instance visée est peuplée et servie : cliquer y déclencherait des
écritures réelles (suppression, envoi de courriel, appel d API tierce facturée). Le pan lit les
écouteurs attachés, il ne les déclenche pas — limite déclarée, et c est le prix de la
non-destructivité sur une instance de qualification.

Sans instance servie, le pan ne devine rien : il sort SKIP avec son motif et les champs à
fournir, que le mécanisme central de qualification (RT-6a) publie en `non_testables[]`. Une
fois l URL fournie, `--reprendre` rejoue ce seul pan.

**Garde de précondition (RT-16 / TF-0211) — un pan aveugle qui se tait est utile ; un pan
aveugle qui accuse coûte un audit entier à démentir.** Ce pan EXIGE un état pour mesurer quoi
que ce soit : une session ouverte sur l instance. Constaté en production : l authentification
n a jamais abouti — le pan l avait lui-même consigné (`401 UNAUTHORIZED` sur les six routes) —
et il a néanmoins photographié six fois l écran de connexion pour en tirer 13 findings (6
`route-en-defaut` « marqueur absent », 6 `affordance-sans-effet` citant mot pour mot le même
formulaire de connexion, 1 `seuil:qualif` qui n était que leur somme), tous au même risque, donc
tous remontés en bloc : 39 % des constats du rapport, tous faux, produits par un pan qui
regardait une page qui n était pas celle qu il croyait. Le pan `api` dans la même situation sort
un inventaire VIDE et zéro constat ; ce pan fait désormais de même.

Le critère est écrit dans `precondition_absente` et ne se déclenche QUE si la précondition est
manifestement absente pour TOUT le pan : une seule route en 401 parmi des routes saines reste
un défaut de cette route, et elle est conservée.

**Parcours d ENTRÉE, sans session (RT-7 / TF-0223).** Ce pan parcourait l instance AUTHENTIFIÉ,
et lui seul. Payé en production le 14/08 : `GET /` répondait 303 vers `/.auth/login/aad`, qui
rendait un **404 JSON de FastAPI** — Easy Auth n avait jamais été activée. Le login était mort
depuis le premier déploiement ; aucun test ne l a vu (le smoke du pipeline ne regarde que
`/health`, public), et c est l humain qui l a découvert EN CLIQUANT, quelques minutes après un
run conclu « boucle close, pans au vert ». Le pan joue donc AUSSI, dans un contexte de navigateur
VIERGE et AVANT toute session, la chaîne de redirections depuis la racine, et exige qu elle
aboutisse à une **mire identifiable** (2xx + marqueur de contenu). Trois règles, toutes prouvées
dans les deux sens :

  - le contrôle tourne **même quand aucune session n est fournie** — c est précisément son
    intérêt : la porte d entrée est ce que tout visiteur voit, session ou pas ;
  - il ne se déclenche **pas** sur une instance publique : sans saut d authentification dans la
    chaîne, il n y a rien à vérifier de ce côté, et le pan le DIT au lieu d accuser ;
  - il **survit à la garde de précondition** ci-dessous : un pan aveugle sur le contenu
    authentifié doit quand même pouvoir dire « et en plus, votre porte d entrée est murée ».
    L y soumettre reconstruirait, un étage plus bas, le silence que la garde vient de corriger.

**Session FOURNIE (RT-6 / TF-0222).** Le pan ne savait s authentifier que par mire formulaire ;
toute instance derrière un IdP d entreprise (Easy Auth Entra : redirections vers
`login.microsoftonline.com`, MFA, accès conditionnel) lui était inauditable — or c est là que
vivent les défauts de frontière. Il accepte désormais une session capturée ailleurs :
`FORGE_TESTS_QUALIF_STORAGE_STATE` (storage state Playwright, chargé dans le contexte) et/ou
`FORGE_TESTS_QUALIF_BEARER` (en-tête `Authorization` ajouté aux requêtes). La **provenance** de
la session est publiée au rapport à chaque exécution : un audit mené sous une session capturée
ne se confond pas avec un audit qui s est authentifié lui-même. Limite déclarée, et détectée
quand elle mord : une session capturée **périme** — sous session expirée, le pan mesure une
redirection, pas un produit. Ni le jeton ni le chemin complet du storage state ne sont publiés :
seuls le NOM du fichier et la NATURE de la session, parce que le rapport circule.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from forge_tests import seuils
from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "qualif-navigateur", "qualif"
SEUIL = seuils.valeur("couverture_surface_qualif")

POUR_COUVRIR = (
    "servir une instance PEUPLÉE du produit (jeu de démonstration injecté, traitements joués) "
    "et déclarer son URL dans FORGE_TESTS_QUALIF_URL ; fournir un compte par "
    "FORGE_TESTS_QUALIF_LOGIN / FORGE_TESTS_QUALIF_PASSWORD si les routes sont protégées. "
    "Options : FORGE_TESTS_QUALIF_ROUTES (routes d'amorce, virgule), "
    "FORGE_TESTS_QUALIF_MARQUEURS (JSON route -> marqueur de contenu), "
    "FORGE_TESTS_QUALIF_CONNEXION (route de la mire), FORGE_TESTS_QUALIF_PLAFOND (routes max), "
    "FORGE_TESTS_QUALIF_REFUS (routes d atterrissage de refus d autorisation propres au produit, "
    "virgule — sans elles, seuls 401/403, la mire et les segments nommant l erreur sont reconnus). "
    "FORGE_TESTS_QUALIF_ORIGINES (origines publiques declarees du produit, virgule — les URLs "
    "auto-referentes des pages y sont admises en plus de celle de l instance auditee). "
    "Instance derriere un IdP d entreprise (Entra, Okta, MFA) que la forge ne peut pas rejouer : "
    "fournir une session DEJA OUVERTE par FORGE_TESTS_QUALIF_STORAGE_STATE (storageState.json "
    "Playwright) et/ou FORGE_TESTS_QUALIF_BEARER (en-tete Authorization) — la provenance de la "
    "session est publiee au rapport, et une session capturee perime"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "F1", "famille": "fonctionnel", "titre": "Parcours bout en bout",
     "decoupe": "parcours", "axe_cas": "etats"},
    {"code": "F2", "famille": "fonctionnel", "titre": "Écrans × états",
     "decoupe": "ecran", "axe_cas": "etats"},
)


# RT-13 : les champs qui débloquent CE pan, et eux seuls — sans revendication, ils restent dans
# le sac partagé du domaine « acces » et sont réclamés à tous les pans en SKIP.
# TF-0222 : les deux champs de session FOURNIE y entrent, sinon ils seraient réclamés au nom du
# pan `data` (qui n en ferait rien) et jamais au nom de celui qu ils débloquent.
# TF-0315 : `FORGE_TESTS_QUALIF_CONNEXION` y entre parce que le pan la RÉCLAME désormais (état
# CONNEXION_ECHOUEE) — sans revendication, elle serait demandée au nom du pan `data`.
CHAMPS_REQUIS = (
    "FORGE_TESTS_QUALIF_URL",
    "FORGE_TESTS_QUALIF_LOGIN",
    "FORGE_TESTS_QUALIF_PASSWORD",
    "FORGE_TESTS_QUALIF_CONNEXION",
    "FORGE_TESTS_QUALIF_STORAGE_STATE",
    "FORGE_TESTS_QUALIF_BEARER",
)

# Ce qu il faut pour que le pan ait seulement un SUJET : une instance servie. Distinct de
# `CHAMPS_REQUIS` (ce qu il REVENDIQUE) — réclamer un compte à qui n a pas encore d URL serait
# demander deux gestes quand un seul est bloquant.
CHAMPS_REQUIS_INSTANCE = ("FORGE_TESTS_QUALIF_URL",)

NON_JUGE = [
    "qualif : le pan LIT les ecouteurs attaches a chaque affordance, il ne CLIQUE jamais — sur "
    "une instance peuplee un clic ecrit vraiment (suppression, envoi, appel tiers facture). Un "
    "gestionnaire attache mais dont le corps ne fait rien passerait donc pour un effet",
    "qualif : les routes sont decouvertes par exploration des liens depuis la racine ; une "
    "route atteignable seulement apres une action (formulaire poste, menu ouvert au clic) "
    "n est pas visitee — la declarer en amorce avec FORGE_TESTS_QUALIF_ROUTES",
    "qualif : le marqueur de contenu par defaut est le titre de la page (premier `h1` non vide, "
    "sinon `title`) ; il atteste qu une page a RENDU quelque chose, pas qu elle ait rendu les "
    "BONNES donnees — un marqueur metier se declare par FORGE_TESTS_QUALIF_MARQUEURS",
    "qualif : quand une delegation d evenement est posee sur `document` ou `body`, aucun "
    "element ne peut plus etre declare inerte avec certitude — les elements concernes sont "
    "NOMMES en non_juge au lieu d etre accuses",
    # TF-0292 : la REGLE, promue ici depuis le non_juge de SORTIE ou TF-0268 l avait laissee.
    # La sortie continue de publier le COMPTE d URLs confrontees et les origines admises — deux
    # mesures, propres a chaque run ; la regle, elle, borne le controle de la meme facon partout,
    # et c est a ce titre qu elle doit se compter au registre de dette.
    # TF-0314 : la REGLE du constat d ouverture. Ce que le pan sait voir borne ce qu il peut
    # affirmer — et c est la seule facon de ne plus annoncer une session qui n existe pas.
    "qualif : l ouverture d une session par la mire se CONSTATE — un cookie de session pose "
    "pendant la soumission, ou la mire qui rend la main (sortie de sa route, sans champ de mot "
    "de passe rendu). Un produit qui garde son jeton en MEMOIRE, sans cookie ni changement de "
    "route, reste indiscernable d un echec : la session est alors declaree NON OUVERTE plutot "
    "que supposee ouverte — un audit qui se croit authentifie est plus dangereux qu un audit "
    "anonyme",
    # TF-0316 : les deux dettes de la couverture par role, assumees par l etude 20260817c.
    "qualif : l etiquette de role d une session declaree est DECLARATIVE — la forge ne verifie "
    "PAS qu une session dite « admin » EST admin, elle constate ce que cette session VOIT ; une "
    "etiquette fausse produit une couverture faussement nommee, et c est l operateur qui repond "
    "de l etiquette",
    "qualif : les surfaces INVISIBLES a l identite exercee ne sont ni inventoriees ni comptees — "
    "une route qu aucun lien ne rend pour ce role, et qu aucune amorce ne declare, n apparait "
    "nulle part au rapport : son absence ne se voit pas. Seules les routes REFUSEES (401, 403, "
    "redirection d autorisation, atterrissage de refus reconnu) sont nommees, parce qu elles ont "
    "ete atteintes",
    # TF-0325 (1) — ce qui reste hors couverture APRES la levee : la frontiere s est deplacee, elle
    # ne s est pas evaporee, et une frontiere deplacee sans etre redite est une frontiere tue.
    "qualif : un refus rendu par une page MAISON n est reconnu que si sa route est DECLAREE "
    "(FORGE_TESTS_QUALIF_REFUS) ou si un de ses segments nomme l erreur d autorisation (403, "
    "acces-refuse, forbidden…). Un produit qui refuse en servant `/oups` ou `/erreur` sans plus "
    "de precision garde ce refus COMPTE COMME PARCOURU : le non-jugement est prefere au faux "
    "refus, qui sortirait du ratio une route peut-etre cassee. Declarer la route leve la limite",
    "qualif : le controle des URL auto-referentes ne connait que quatre formes — `canonical`, "
    "`og:url`, le `url`/`@id` du JSON-LD et les `loc` de sitemap — lues sur les seules routes "
    "PARCOURUES et dans les 20 000 premiers caracteres de chaque page ; une page plus longue, "
    "une route non atteinte ou une cinquieme facon de se designer echappent au controle. Les "
    "URLs RELATIVES ne portent aucune origine : elles ne sont pas jugees, et c est la forme saine",
]

# Affordances jugees, alignees sur le pan `interface` : meme loi, autre point d observation.
_SELECTEUR = (
    "button, a, form, input[type=submit], input[type=button], input[type=image], [role=button]"
)
_HREF_MORTS = {"", "#", "javascript:;", "javascript:void(0)", "javascript:void(0);"}
_PREFIXES_HANDLER = (
    "on", "@", "v-on:", "x-on:", "x-bind:", "hx-", "wire:", "ng-", "data-action",
    "data-controller", "data-bs-toggle", "data-toggle", "data-turbo", "up-", "formaction",
)
_TRACES = (
    "internal server error",
    "traceback (most recent call last)",
    "jinja2.exceptions",
    "templatenotfound",
    "werkzeug.debug",
    "django.core.exceptions",
)
_PLAFOND_DEFAUT = 40


# --- Session FOURNIE, et sa PROVENANCE (RT-6 / TF-0222) ---------------------------------------
# Une instance derrière un IdP d entreprise (Entra + MFA + accès conditionnel) ne s ouvre pas en
# remplissant un formulaire : la forge ne peut pas rejouer un second facteur. Elle accepte donc
# une session ouverte AILLEURS — c est l artefact que le produit produit déjà pour ses propres
# tests Azure (storage state Playwright, cookie `AppServiceAuthSession`).
#
# TF-0222 : quand la session a été FOURNIE et qu elle n a pas ouvert l instance, ce ne sont pas
# des identifiants qui manquent — c est la session capturée qu il faut RENOUVELER.
CHAMPS_REQUIS_SESSION_FOURNIE = (
    "FORGE_TESTS_QUALIF_STORAGE_STATE",
    "FORGE_TESTS_QUALIF_BEARER",
)
# En-têtes déjà porteurs de leur schéma : on ne les préfixe pas une seconde fois.
_SCHEMAS_AUTORISATION = ("bearer ", "basic ", "negotiate ", "digest ", "token ")


def session_fournie(config: dict) -> bool:
    """Une session capturée ailleurs a-t-elle été fournie à ce pan ?"""
    return bool(config.get("storage_state") or config.get("bearer"))


def _entete_autorisation(valeur: str) -> str:
    """En-tête `Authorization` à poser. Un jeton nu est un jeton `Bearer` — le cas courant."""
    valeur = (valeur or "").strip()
    if valeur.lower().startswith(_SCHEMAS_AUTORISATION):
        return valeur
    return f"Bearer {valeur}"


# --- État de session : CONSTATÉ, jamais déduit (TF-0314) ---------------------------------------
# `provenance_session` ne consultait que le dictionnaire de CONFIGURATION : elle ne pouvait
# structurellement pas savoir si la session avait été ouverte, elle constatait seulement qu un
# login et un mot de passe avaient été fournis. Payé dans le rapport BAV2 du 17/08 : non_juge[0]
# annonçait « session ouverte PAR LA FORGE elle-même » pendant que non_juge[1] disait « aucune
# mire de connexion trouvée » — deux phrases contradictoires, et c est la première qui se lit en
# tête. La phrase de provenance dépend désormais du RÉSULTAT de `_connecter`, et l ouverture se
# CONSTATE (un cookie de session posé, ou la mire qui rend la main) au lieu de se déduire d un
# clic émis.
SESSION_SANS_COMPTE = "sans_compte"  # aucun compte fourni : rien n a été tenté
SESSION_OUVERTE = "ouverte"  # tentée ET constatée
SESSION_ECHOUEE = "echouee"  # mire trouvée, remplie, soumise — ouverture NON constatée
SESSION_SANS_MIRE = "sans_mire"  # aucune mire trouvée, après attente d apparition


def provenance_session(config: dict, session: dict | None = None) -> str:
    """Sous QUELLE identité l audit a été mené — publié au rapport, à chaque exécution.

    TF-0222 : un audit fait sous une session CAPTURÉE ne se confond pas avec un audit qui s est
    authentifié lui-même. Le premier hérite des droits de l opérateur qui a capturé la session
    (souvent plus larges que ceux du compte d audit nominal) et il périme sans prévenir ; le
    second rejoue la mire à chaque run. Lire un rapport sans savoir lequel des deux on tient,
    c est ignorer ce que « exercé » veut dire dedans.

    Ni le jeton ni le chemin complet du storage state n apparaissent : le rapport CIRCULE, et
    ces deux valeurs portent une identité. Seuls la nature de la session et le NOM du fichier.

    TF-0314 : quand la session doit être ouverte PAR LA FORGE, la phrase suit le RÉSULTAT que
    `_connecter` a constaté (`session`), jamais la seule présence d un compte en configuration.
    Sans résultat relevé, elle dit qu il n a pas été relevé — elle n affirme pas une session.

    TF-0316 : quand la session porte une ÉTIQUETTE DE RÔLE, la phrase la nomme — sinon une
    couverture par rôle serait publiée sans qu on puisse dire laquelle vaut pour qui.
    """
    role = str((session or {}).get("role") or "")
    tete = "qualif : PROVENANCE DE SESSION" + (f" (role « {role} »)" if role else "") + " — "
    natures: list[str] = []
    if config.get("storage_state"):
        natures.append(
            f"storage state Playwright « {Path(str(config['storage_state'])).name} » "
            "(cookies et stockage local injectes dans le contexte)"
        )
    if config.get("bearer"):
        natures.append("en-tete Authorization fourni (valeur JAMAIS publiee)")
    if natures:
        rejouee = (
            " La mire formulaire n a PAS ete rejouee, meme si un compte est configure : la "
            "session fournie prime."
            if (config.get("login") and config.get("mdp"))
            else ""
        )
        return (
            tete + "audit mene sous une session CAPTUREE AILLEURS et "
            "fournie a la forge (" + " · ".join(natures) + ")." + rejouee + " Ce qui est mesure "
            "l est donc sous l identite de l operateur qui a capture la session, et une session "
            "capturee PERIME : sous session expiree, le pan mesure une redirection, pas un "
            "produit. A ne pas confondre avec un audit qui s est authentifie lui-meme"
        )
    if config.get("login") and config.get("mdp"):
        etat = (session or {}).get("etat")
        if etat == SESSION_OUVERTE:
            return (
                tete + "session ouverte PAR LA FORGE elle-meme, en "
                "rejouant la mire formulaire avec FORGE_TESTS_QUALIF_LOGIN, et l ouverture est "
                f"CONSTATEE ({(session or {}).get('preuve') or 'constat non detaille'}) ; ce que "
                "le pan voit est exactement ce que ce compte voit"
            )
        if etat in (SESSION_ECHOUEE, SESSION_SANS_MIRE):
            return (
                tete + "un compte a ete fourni "
                "(FORGE_TESTS_QUALIF_LOGIN) et la session N A PAS ete ouverte : "
                f"{(session or {}).get('motif') or 'echec non detaille'}. Le parcours qui suit "
                "est donc ANONYME DE FAIT — tout contenu place derriere l authentification reste "
                "hors de portee de ce releve, et un compte configure ne prouve pas une session"
            )
        return (
            tete + "un compte est configure "
            "(FORGE_TESTS_QUALIF_LOGIN) mais le RESULTAT de la mire n a pas ete releve : "
            "l ouverture de session n est donc PAS constatee ici, et elle n est pas affirmee"
        )
    return (
        tete + "AUCUNE session : l instance a ete parcourue en "
        "ANONYME. Tout contenu place derriere une authentification est hors de portee de ce "
        "relevé — fournir un compte (FORGE_TESTS_QUALIF_LOGIN / _PASSWORD) ou une session deja "
        "ouverte (FORGE_TESTS_QUALIF_STORAGE_STATE / _BEARER)"
    )


def _provenances(config: dict, sessions: list[dict]) -> list[str]:
    """La provenance de CHAQUE session exercée — une phrase par identité, jamais une moyenne.

    La vue de configuration est refaite par session : c est SON storage state qui décrit son
    identité. Une session sans clé `storage_state` (le cas mono, où rien n a été relevé) laisse la
    configuration intacte — la remplacer par du vide effacerait la session capturée du rapport.
    """
    lignes: list[str] = []
    for session in sessions:
        vue = dict(config)
        if "storage_state" in session:
            vue["storage_state"] = session.get("storage_state") or ""
        lignes.append(provenance_session(vue, session))
    return lignes


def _options_contexte(config: dict) -> tuple[dict, list[str]]:
    """Options du contexte Playwright AUTHENTIFIÉ, et ce qu il a fallu écarter en le disant.

    Un storage state introuvable ou illisible ne fait pas tomber le pan : il est ÉCARTÉ, la
    configuration est corrigée en mémoire pour que la provenance publiée dise la vérité (pas
    « audit sous session capturée » alors que le fichier n a jamais été lu), et l écart est
    déclaré. Un audit qui se croit authentifié est plus dangereux qu un audit anonyme.
    """
    alertes: list[str] = []
    options: dict = {}
    chemin = str(config.get("storage_state") or "").strip()
    if chemin:
        fichier = Path(chemin)
        motif = None
        if not fichier.is_file():
            motif = "fichier introuvable"
        else:
            try:
                json.loads(fichier.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as erreur:
                motif = f"illisible ({type(erreur).__name__})"
        if motif is None:
            options["storage_state"] = str(fichier)
        else:
            config["storage_state"] = ""
            alertes.append(
                f"qualif : FORGE_TESTS_QUALIF_STORAGE_STATE ecarte — « {fichier.name} » {motif} ; "
                "le parcours se poursuit SANS cette session, et la provenance publiee le dit"
            )
    return options, alertes


# --- Couverture PAR RÔLE : N sessions étiquetées, et ce qu aucune n a vu (TF-0316) -------------
# `FORGE_TESTS_QUALIF_STORAGE_STATE` est un chemin UNIQUE : un seul storage state, un seul
# contexte, donc une seule identité pour tout le parcours. Payé sur Approval2 le 12/08 : le pan a
# rendu « 8/8, ratio 1,00, ZÉRO finding » avec le compte unique `mock-user@example.com`, alors que
# le produit réserve trois surfaces par rôle (console d administration derrière `RequireAdmin`,
# écran de revue et décision, vue en lecture seule du destinataire en copie). Aucune n avait été
# parcourue sous son rôle propre, et le rapport ne le disait pas : « ratio 1,00 » se lit « tout est
# couvert ». Écart découvert cinq jours plus tard par une question humaine, pas par l outil.
#
# Étude d opportunité 20260817c, verdict O3 — les deux niveaux, la DÉCLARATION D ABORD :
#   (a) déclarer : le rapport dit combien de sessions ont été exercées et ce qu elles n ont pas
#       vu — N = 1 est le cas dégradé DÉCLARÉ, pas un cas à part — et les refus d autorisation
#       sortent en issue DISTINCTE d un succès ;
#   (b) mesurer : N sessions étiquetées, un contexte par session, parcours rejoué par profil,
#       couverture par rôle au rapport.
# La non-destructivité ne bouge pas : lire plus de surfaces, jamais agir.
CLASSE_REFUS_AUTORISATION = "acces-refuse-a-cette-identite"
# Le parcours d entrée (TF-0223) est relevé SANS session, dans un contexte vierge : il n appartient
# à aucun rôle, et la couverture par rôle le nomme pour ce qu il est plutôt que de le prêter au
# premier profil de la liste.
ROLE_ENTREE = "porte d entree (aucune session)"


def sessions_declarees(config: dict) -> tuple[list[dict], list[str]]:
    """Les sessions à exercer — étiquetées par rôle — et ce qu il a fallu écarter en le disant.

    `FORGE_TESTS_QUALIF_STORAGE_STATES` = `role=chemin`, séparés par des virgules. Le singulier
    `FORGE_TESTS_QUALIF_STORAGE_STATE` reste VALIDE et décrit LA session de l audit, sans
    prétendre à un rôle : c est le cas de tous les audits menés jusqu ici, et il ne change pas.

    Il y a TOUJOURS au moins une session, éventuellement sans étiquette et sans storage state (le
    pan rejoue alors la mire, ou parcourt en anonyme). Une session mal formée est ÉCARTÉE et
    déclarée : une couverture par rôle bâtie sur une étiquette illisible serait faussement nommée.
    """
    alertes: list[str] = []
    sessions: list[dict] = []
    for paire in config.get("storage_states") or []:
        role, _, chemin = paire.partition("=")
        role, chemin = role.strip(), chemin.strip()
        if not role or not chemin:
            alertes.append(
                f"qualif : entree « {paire[:60]} » de FORGE_TESTS_QUALIF_STORAGE_STATES ECARTEE — "
                "forme attendue « role=chemin » ; cette session n est pas exercee, et ce que ce "
                "role voit reste inconnu de cet audit"
            )
            continue
        if any(session["role"] == role for session in sessions):
            alertes.append(
                f"qualif : role « {role} » declare DEUX FOIS dans "
                "FORGE_TESTS_QUALIF_STORAGE_STATES — seule la premiere session de ce role est "
                "exercee ; une couverture par role exige une etiquette par role"
            )
            continue
        sessions.append({"role": role, "storage_state": chemin, "etat": None})
    if not sessions:
        return (
            [{"role": "", "storage_state": config.get("storage_state") or "", "etat": None}],
            alertes,
        )
    if config.get("storage_state"):
        alertes.append(
            "qualif : FORGE_TESTS_QUALIF_STORAGE_STATE (singulier) est IGNORE tant que "
            "FORGE_TESTS_QUALIF_STORAGE_STATES est declare — sans quoi une session sans etiquette "
            "se melangerait a des sessions etiquetees, et la couverture par role serait fausse"
        )
    if config.get("bearer"):
        alertes.append(
            "qualif : FORGE_TESTS_QUALIF_BEARER est pose sur TOUTES les sessions etiquetees — le "
            "MEME en-tete Authorization pour chaque role, ce qui peut contredire l etiquette ; "
            "n en fournir aucun quand les sessions portent deja leur identite"
        )
    return sessions, alertes


def _prefixe_role(session: dict) -> str:
    """« role:<etiquette>: » quand la session en porte une, rien sinon.

    Mono-session, les identifiants d élément restent INCHANGÉS : la cotation de risque, les
    déclarations RT-16 et tous les rapports antérieurs s y adossent. Le rôle n entre dans
    l identifiant que lorsqu il existe VRAIMENT plusieurs identités à distinguer.
    """
    role = str(session.get("role") or "")
    return f"role:{role}:" if role else ""


def _identifiant(page_vue: dict, suffixe: str) -> str:
    """Identifiant d élément de surface, préfixé du RÔLE quand la page a été vue sous un rôle."""
    return f"qualif:{_prefixe_role(page_vue)}{suffixe}"


def couverture_par_role(
    sessions: list[dict],
    inventaire: list[str],
    exerces: list[str],
    refuses: list[str],
    role_de: dict[str, str],
) -> list[dict]:
    """Ce que CHAQUE identité a inventorié, exercé et vu refuser — jamais une moyenne.

    Une session déclarée qui n a rien inventorié y figure quand même, à zéro : c est le cas d une
    session périmée ou d une étiquette dont le storage state a été écarté, et c est précisément ce
    qu il faut voir.
    """
    exerce, refuse = set(exerces), set(refuses)
    roles = [str(session.get("role") or "") for session in sessions]
    for element in [*inventaire, *refuses]:
        role = role_de.get(element, "")
        if role not in roles:
            roles.append(role)
    couverture: list[dict] = []
    for role in roles:
        elements = [e for e in inventaire if role_de.get(e, "") == role]
        tenus = [e for e in elements if e in exerce]
        prives = [e for e in refuses if role_de.get(e, "") == role and e in refuse]
        couverture.append(
            {
                "role": role or "(sans etiquette de role)",
                "inventorie": len(elements),
                "exerce": len(tenus),
                "ratio": round(len(tenus) / len(elements), 4) if elements else 0.0,
                "refuse": len(prives),
            }
        )
    return couverture


def declaration_couverture(
    config: dict,
    sessions: list[dict],
    refuses: list[str],
    role_de: dict[str, str],
    couverture: list[dict],
) -> list[str]:
    """Ce que le ratio NE dit PAS — publié à chaque rapport, N = 1 compris (TF-0316, niveau a).

    Trois phrases, et elles sont toutes des mesures de CE run : combien d identités ont parcouru
    et lesquelles, ce que ces identités n ont pas pu voir, et la couverture rôle par rôle. La
    quatrième — l étiquette de rôle est déclarative — est une RÈGLE, et vit donc au registre de
    dette (`NON_JUGE`), pas ici.
    """
    etiquettes = [str(session.get("role") or "") for session in sessions]
    nommees = ", ".join(f"« {role} »" for role in etiquettes if role)
    lignes = [
        f"qualif : {len(sessions)} session(s) exercee(s)"
        + (f" — role(s) : {nommees}" if nommees else " — SANS etiquette de role")
        + f" sur {config.get('base') or 'l instance'} : les routes REFUSEES ou INVISIBLES a cette "
        "ou ces identites NE SONT PAS JUGEES. Un ratio de 100 % ne dit donc pas « tout est "
        "couvert », il dit « tout ce que ces identites ont pu voir est couvert »"
        + (
            ""
            if len(sessions) > 1
            else " — declarer plusieurs sessions etiquetees par "
            "FORGE_TESTS_QUALIF_STORAGE_STATES (« role=chemin », virgule) pour parcourir chaque "
            "surface sous son role propre"
        )
    ]
    if refuses:
        par_role: dict[str, list[str]] = {}
        for element in refuses:
            par_role.setdefault(role_de.get(element, ""), []).append(element)
        detail = " · ".join(
            f"{role or 'session sans etiquette'} : {len(elements)} route(s) "
            f"({', '.join(sorted(elements)[:3])}{' …' if len(elements) > 3 else ''})"
            for role, elements in sorted(par_role.items())
        )
        lignes.append(
            f"qualif : {len(refuses)} route(s) REFUSEE(S) a l identite qui les a demandees "
            f"(401, 403, redirection d autorisation ou atterrissage de refus) — {detail}. "
            "Elles sortent du ratio en "
            "issue DISTINCTE d un succes : ce ne sont ni des routes saines, ni des defauts du "
            "produit, mais des surfaces qu il faut une AUTRE identite pour juger"
        )
    lignes.append(
        "qualif : couverture PAR ROLE — "
        + " · ".join(
            f"{entree['role']} : {entree['exerce']}/{entree['inventorie']} "
            f"({entree['ratio']:.0%}), {entree['refuse']} refusee(s)"
            for entree in couverture
        )
    )
    return lignes


# TF-0325 (1) — segments qui nomment une erreur d AUTORISATION, et rien d autre. Le mot doit être
# un segment ENTIER (`/erreur/403`, `/acces-refuse`), jamais une sous-chaîne : `/produits/403-w`
# n est pas un refus. Volontairement restreint à l autorisation : `/erreur`, `/oups` ou `/500`
# nomment une panne, et prendre une panne pour un refus SORTIRAIT du ratio une route cassée —
# exactement le silence que TF-0316 vient de fermer, retourné contre lui.
_SEGMENTS_REFUS = frozenset(
    {
        "401", "403", "forbidden", "unauthorized", "unauthorised", "access-denied",
        "accessdenied", "permission-denied", "acces-refuse", "acces-interdit", "non-autorise",
        "interdit", "denied",
    }
)


def _est_atterrissage_de_refus(route: str, config: dict) -> str | None:
    """Motif si `route` est la page d atterrissage d un refus d AUTORISATION, ou None — TF-0325.

    Deux sources, de la plus opposable à la plus prudente, comme partout ailleurs ici :

      - la route DÉCLARÉE par l opérateur (`FORGE_TESTS_QUALIF_REFUS`) — déclarée, elle juge ;
      - un segment qui NOMME l erreur d autorisation. Prudente par construction : le segment doit
        être entier et parler d autorisation, pas d erreur en général.

    Ce qu aucune des deux ne reconnaît n est pas jugé refus — la route reste comptée comme
    parcourue et le pan DÉCLARE la frontière. Un faux refus coûte plus cher qu un non-jugement :
    il fait sortir du ratio une route peut-être cassée.
    """
    declarees = {r.rstrip("/") or "/" for r in (config.get("refus") or [])}
    if route in declarees:
        return f"route de refus DÉCLARÉE ({route})"
    segments = {s for s in route.lower().split("/") if s}
    nommant = sorted(segments & _SEGMENTS_REFUS)
    if nommant:
        return f"page d atterrissage nommant l erreur d autorisation ({', '.join(nommant)})"
    return None


def refus_autorisation(page_vue: dict, config: dict) -> str | None:
    """Motif si CETTE route a été REFUSÉE à l identité qui l a demandée, ou None.

    Trois formes, et trois seulement :
      - la route rend 401 ou 403 — le refus est dit par le protocole ;
      - la navigation a ABOUTI AILLEURS, sur un saut d authentification — le refus est joué en
        REDIRECTION, et c est la forme qui se confondait avec un SUCCÈS : la mire répond 200 et
        porte un titre, donc la route comptait pour exercée. Un ratio de 1,00 pouvait ainsi ne
        rien dire de trois surfaces réservées ;
      - TF-0325 : la navigation a abouti sur une page de refus MAISON (`/erreur/403`,
        `/acces-refuse`) — ni 401/403, ni mire d authentification. Le produit dit « tu n as pas le
        droit » dans son propre dialecte, et le pan n en reconnaissait aucun : ces routes
        comptaient pour exercées, et le ratio d un rôle bridé annonçait 100 %.

    Ce n est PAS un défaut du produit : c est une surface que l identité exercée n a pas le droit
    de voir. Elle sort donc en issue DISTINCTE, hors du ratio, et le geste de réparation est de
    fournir la session du rôle qui y a droit — jamais de corriger la route.
    """
    statut = page_vue.get("statut")
    if statut in (401, 403):
        return f"HTTP {statut}"
    url = str(page_vue.get("url_finale") or "")
    if not url:
        return None
    base = config.get("base") or ""
    arrivee = _route(url, base)
    if arrivee is None or arrivee == _route(str(page_vue.get("route") or ""), base):
        return None
    if _est_saut_auth(url):
        return f"redirection d autorisation vers {arrivee}"
    atterrissage = _est_atterrissage_de_refus(arrivee, config)
    if atterrissage is not None:
        return f"redirection vers {arrivee} — {atterrissage}"
    return None


# --- Précondition du pan : une session ouverte (RT-16 / TF-0211) -------------------------------
# Ce qui DÉBLOQUE le pan quand sa précondition manque — publié en `non_testables[].champs_requis`.
CHAMPS_REQUIS_SESSION = ("FORGE_TESTS_QUALIF_LOGIN", "FORGE_TESTS_QUALIF_PASSWORD")

# Une seule route ne permet pas de distinguer « cette route est en défaut » de « le pan entier
# est aveugle ». En dessous de ce nombre de routes parcourues, la garde ne se déclenche jamais :
# on préfère laisser passer un constat douteux plutôt que taire un pan qu on n a pas su juger.
_ROUTES_MIN_GARDE = 2

# --- TF-0315 : le TROISIÈME état de réparation --------------------------------------------------
# Deux existaient : `CHAMPS_REQUIS_SESSION` (« il n y a pas de compte ») et
# `CHAMPS_REQUIS_SESSION_FOURNIE` (« la session capturée a péri, recapture-la »). Manquait celui
# qui a été mesuré le 17/08 : un compte FOURNI ET VALIDE, et la connexion qui n aboutit pas. Les
# six non_testables publiaient alors `[LOGIN, PASSWORD]` — « pas de compte » et « compte fourni,
# connexion échouée » étaient indiscernables, l opérateur refaisait trois gestes déjà faits puis
# concluait que son compte était mauvais. Ce que le pan a le droit de demander ici, c est la
# ROUTE de la mire (si celle qu il a essayée n était pas la bonne) ou une session ouverte AILLEURS
# (si la forge ne sait pas rejouer cette mire) — jamais le compte qu il a déjà reçu.
CHAMPS_REQUIS_CONNEXION_ECHOUEE = (
    "FORGE_TESTS_QUALIF_CONNEXION",
    "FORGE_TESTS_QUALIF_STORAGE_STATE",
    "FORGE_TESTS_QUALIF_BEARER",
)


def connexion_echouee(sessions: list[dict] | None) -> dict | None:
    """La session dont la connexion a été TENTÉE et n a pas abouti, ou None.

    « Aucune mire trouvée » en fait partie : dans les deux cas un compte a été fourni et le pan
    n a pas ouvert de session — c est la même réparation, et surtout ce n est pas le compte.
    """
    for session in sessions or []:
        if session.get("etat") in (SESSION_ECHOUEE, SESSION_SANS_MIRE):
            return session
    return None


def champs_a_fournir(config: dict, sessions: list[dict] | None = None) -> tuple[str, ...]:
    """Ce qui DÉBLOQUE le pan, selon ce qui a été constaté — trois états, trois demandes."""
    if session_fournie(config):
        return CHAMPS_REQUIS_SESSION_FOURNIE
    if connexion_echouee(sessions) is not None:
        return CHAMPS_REQUIS_CONNEXION_ECHOUEE
    return CHAMPS_REQUIS_SESSION


def detail_connexion(sessions: list[dict] | None) -> str:
    """CE QUI A ÉTÉ TENTÉ et OÙ ÇA S EST ARRÊTÉ — dans le champ que l opérateur lit pour réparer.

    L information était déjà produite par `_connecter` ; elle était diluée dans `non_juge`, hors
    du seul champ qu on relit quand on veut réparer. Elle est donc republiée ici, à l identique.
    """
    session = connexion_echouee(sessions)
    if session is None:
        return ""
    motif = str(session.get("motif") or "connexion echouee, sans detail")
    arret = str(session.get("arret") or "")
    detail = f" TENTE : {motif}"
    if arret and arret not in motif:
        detail += f" ; ARRET : {arret}"
    return detail + "."

_REFUS_CODES = re.compile(r"\b(?:401|403)\b")
_REFUS_MOTS = (
    "unauthorized",
    "forbidden",
    "non autorise",
    "non autorisé",
    "failed to load resource",
    "status of",
    "status code",
)


def _est_refus_auth(texte: str) -> bool:
    """Ce texte de console dit-il un refus d authentification ?

    Le code seul ne suffit pas : « 401 » peut être une donnée affichée. Il faut le code ET un
    mot de statut HTTP — c est la forme exacte que le navigateur écrit (« Failed to load
    resource: the server responded with a status of 401 (UNAUTHORIZED) »).
    """
    minuscule = (texte or "").lower()
    if not _REFUS_CODES.search(minuscule):
        return False
    return any(mot in minuscule for mot in _REFUS_MOTS)


def _signal_session_absente(page_vue: dict, config: dict) -> str | None:
    """Motif si CETTE route atteste d une session absente ; None si elle est saine.

    Trois attestations, de la plus directe à la plus indirecte :
      - la route elle-même rend 401/403 ;
      - la route rend 200 mais ses appels de données sont refusés en 401/403 (cas réel : la mire
        de connexion s affiche, le navigateur consigne le refus) ;
      - le marqueur de contenu DÉCLARÉ par le projet pour cette route est absent de la page —
        la page rendue n est pas celle qu on attendait. Seul un marqueur déclaré compte : un
        marqueur dérivé du titre n est pas « attendu », il est constaté.
    """
    statut = page_vue.get("statut")
    if statut in (401, 403):
        return f"HTTP {statut}"
    for ligne in page_vue.get("console") or []:
        if _est_refus_auth(ligne):
            return f"erreur console : {ligne[:120]}"
    marqueur = config["marqueurs"].get(page_vue["route"])
    if marqueur and marqueur.lower() not in (page_vue.get("corps") or "").lower():
        return f"marqueur déclaré {marqueur!r} absent de la page rendue"
    return None


def precondition_absente(
    releve: list[dict], config: dict, sessions: list[dict] | None = None
) -> str | None:
    """Motif si la précondition du pan — une session ouverte — manque POUR TOUT LE PAN.

    **Critère, et rien d autre** : au moins `_ROUTES_MIN_GARDE` routes parcourues, et CHACUNE
    d elles atteste d une session absente (`_signal_session_absente`). Une seule route saine
    suffit à écarter la garde : ce n est alors pas une précondition manquée, c est un défaut de
    la route qui échoue, et il doit être conservé. Une route dont on ne sait rien (navigation
    impossible) ne porte pas de signal, donc écarte la garde elle aussi — la garde ne se déduit
    jamais d une ignorance, seulement d un faisceau de constats concordants.
    """
    if len(releve) < _ROUTES_MIN_GARDE:
        return None
    signaux: list[str] = []
    for page_vue in releve:
        signal = _signal_session_absente(page_vue, config)
        if signal is None:
            return None
        signaux.append(f"{page_vue['route']} ({signal})")
    # TF-0222 : une session FOURNIE et pourtant refusee partout, c est le cas de peremption —
    # le geste de reparation n est alors pas « fournir un compte » mais « recapturer la session ».
    # TF-0315 : un compte fourni dont la connexion a echoue est un TROISIEME cas, et il ne se
    # repare pas en fournissant le compte qu on a deja donne.
    a_reparer = champs_a_fournir(config, sessions)
    echec_connexion = (
        " La connexion a ete TENTEE avec le compte fourni et elle n a PAS abouti : ce n est donc "
        "pas le compte qui manque ici." + detail_connexion(sessions)
        if connexion_echouee(sessions) is not None
        else ""
    )
    peremption = (
        " La session FOURNIE n a donc PAS ete acceptee par l instance : une session capturee "
        "PERIME (cookie expire, acces conditionnel rejoue), et un audit sous session expiree "
        "mesure une redirection, pas un produit — la recapturer avant de rejouer."
        if session_fournie(config)
        else ""
    )
    return (
        f"qualif : PRECONDITION NON ETABLIE — le pan exige une session ouverte sur l instance, "
        f"et les {len(releve)} route(s) parcourue(s) sur {config['base']} l attestent toutes "
        f"absente : " + " · ".join(signaux) + ". Le pan a donc photographie le meme ecran "
        "autant de fois qu il a visite de routes : son inventaire est declare NON MESURABLE et "
        "il n emet AUCUN constat produit." + peremption + echec_connexion
        + " Fournir ou corriger " + ", ".join(a_reparer)
        + (
            ""
            if "FORGE_TESTS_QUALIF_CONNEXION" in a_reparer
            else " (et FORGE_TESTS_QUALIF_CONNEXION si la mire n est pas sur /connexion ou /login)"
        )
        + ", puis `--reprendre` le rapport. Un pan aveugle qui se tait est utile ; un pan aveugle "
        "qui accuse coute un audit entier a dementir"
    )


# --- Parcours d ENTRÉE, sans session (RT-7 / TF-0223) -----------------------------------------
# Le pan regardait l instance de l INTÉRIEUR. La porte d entrée — ce que voit quiconque arrive
# sans rien — n était vue par personne : ni par ce pan (authentifié), ni par le smoke du pipeline
# (qui n interroge que `/health`, public). Résultat mesuré : un login mort depuis le premier
# déploiement, découvert par un humain qui a cliqué.
IDENT_ENTREE = "qualif:entree:/"
CLASSE_ENTREE = "chaine-authentification-en-impasse"
# TF-0268 : une page qui annonce aux tiers une origine qui n est pas la sienne.
CLASSE_URL_ETRANGERE = "url-auto-referente-etrangere"

# Ce qui fait d un maillon un SAUT D AUTHENTIFICATION. Sans un seul de ces sauts dans la chaîne,
# l instance ne demande rien à l entrée : il n y a pas de porte, donc pas de porte murée, et le
# contrôle se tait. C est la moitié du critère, et elle est aussi importante que l autre.
# Le chemin se lit par SEGMENTS, jamais par sous-chaîne : `/loginfo` contient « login » sans
# être une mire, et une page publique `/aide/se-connecter` n est pas une porte d entrée.
_SEGMENTS_AUTH = frozenset(
    {
        ".auth", "auth", "oauth", "oauth2", "authorize", "authorization", "saml", "saml2",
        "sso", "signin", "sign-in", "login", "log-in", "logon", "connexion", "adfs", "openid",
        "openid-connect", "idp",
    }
)
_HOTES_IDP = (
    "login.microsoftonline.com", "login.microsoft.com", "login.windows.net", "sts.windows.net",
    "accounts.google.com", "okta.com", "auth0.com", "onelogin.com", "pingidentity.com",
    "keycloak", "cas.", "idp.",
)
_CHAMP_MOTDEPASSE = re.compile(r"type\s*=\s*[\"']?password", re.IGNORECASE)
# Un titre d un ou deux caractères n identifie rien ; c est le seuil déjà retenu par `_JS_TITRE`.
_LONGUEUR_TITRE_MIN = 3


def _sans_secret(url: str) -> str:
    """URL réduite à `schéma://hôte/chemin` — la requête d un IdP porte `code`, `state`, `nonce`.

    Ces paramètres sont des fragments de session : les recopier au rapport, c est publier au
    rapport ce que le garde-fou anti-fuite existe pour retenir.
    """
    decoupe = urlparse(url or "")
    if not decoupe.scheme:
        # Une URL RELATIVE porte sa requête elle aussi (`/callback?code=…`) : la rendre telle
        # quelle republierait exactement ce que la branche absolue prend soin d ôter.
        return (decoupe.path or url or "")[:120]
    return f"{decoupe.scheme}://{decoupe.netloc}{decoupe.path}"[:120]


def _est_saut_auth(url: str) -> bool:
    """Ce maillon de la chaîne est-il un saut d authentification ?"""
    decoupe = urlparse((url or "").lower())
    if any(hote in decoupe.netloc for hote in _HOTES_IDP):
        return True
    return bool(set(decoupe.path.split("/")) & _SEGMENTS_AUTH)


def _marqueur_mire(entree: dict, config: dict) -> str | None:
    """Le marqueur de contenu qui fait de la page d arrivée une MIRE IDENTIFIABLE, ou None.

    Trois sources, de la plus opposable à la plus indulgente :
      - le marqueur DÉCLARÉ par le projet pour la route d arrivée (`FORGE_TESTS_QUALIF_MARQUEURS`)
        — s il est déclaré, il est le seul juge : une page qui ne le porte pas n est pas la mire
        attendue, même si elle affiche autre chose ;
      - un champ de mot de passe : une mire de connexion, quel qu en soit le titre ;
      - un titre non vide (premier `h1`, sinon `title`) : la page a RENDU quelque chose
        d identifiable. C est ce dernier point que le 404 JSON de production ne franchissait pas.
    """
    corps = entree.get("corps") or ""
    chaine = entree.get("chaine") or []
    url_finale = str(chaine[-1].get("url") or "") if chaine else ""
    route = _route(url_finale, config.get("base") or "") if config.get("base") else None
    declare = (config.get("marqueurs") or {}).get(route) if route else None
    if declare:
        return declare if declare.lower() in corps.lower() else None
    if _CHAMP_MOTDEPASSE.search(corps):
        return "champ de mot de passe"
    titre = (entree.get("titre") or "").strip()
    if len(titre) >= _LONGUEUR_TITRE_MIN:
        return f"titre « {titre[:60]} »"
    return None


def diagnostiquer_entree(entree: dict | None, config: dict) -> str | None:
    """Motif d impasse du parcours d entrée NON AUTHENTIFIÉ, ou None s il n y a rien à reprocher.

    **Critère, et rien d autre** : la chaîne de redirections partie de la racine comporte au
    moins un saut d authentification, et elle N ABOUTIT PAS à une mire identifiable — c est-à-dire
    à une réponse 2xx portant un marqueur de contenu. Les trois façons de ne rien dire :

      - aucun relevé, ou un relevé dont la navigation a échoué → le pan ne SAIT rien, et une
        ignorance n accuse jamais (même règle que la garde de précondition) ;
      - aucun saut d authentification → instance publique : il n y a pas de porte à vérifier ;
      - une arrivée en 2xx avec marqueur → chaîne SAINE, y compris quand elle passe par un IdP
        externe. Traverser `login.microsoftonline.com` est le fonctionnement NORMAL d Entra, pas
        un défaut : ce qui est jugé est le point d arrivée, jamais l itinéraire.
    """
    if not entree or entree.get("erreur"):
        return None
    chaine = [m for m in (entree.get("chaine") or []) if m]
    if not chaine:
        return None
    if not any(_est_saut_auth(str(m.get("url") or "")) for m in chaine):
        return None
    trace = " -> ".join(
        f"{_sans_secret(str(m.get('url') or ''))} ({m.get('statut') or 'sans statut'})"
        for m in chaine
    )
    statut = chaine[-1].get("statut")
    if statut is None or not 200 <= int(statut) < 300:
        return (
            f"la chaine d authentification depuis la racine n aboutit a AUCUNE mire : {trace}. "
            f"Le dernier maillon rend {statut if statut is not None else 'aucune reponse'} la ou "
            "un visiteur doit trouver un ecran de connexion — la porte d entree de l instance "
            "est muree, et aucun parcours authentifie ne peut le voir"
        )
    if _marqueur_mire(entree, config) is None:
        return (
            f"la chaine d authentification depuis la racine aboutit a un {statut} SANS marqueur "
            f"de contenu : {trace}. La page ne rend ni titre, ni champ de mot de passe, ni le "
            "marqueur declare pour cette route — elle repond, mais elle n affiche pas de mire "
            "identifiable, ce qu un controle de code HTTP seul declarerait vert"
        )
    return None


def mentions_entree(entree: dict | None, config: dict) -> list[str]:
    """Ce que le parcours d entrée a vu — publié MÊME quand il n a rien à reprocher.

    Un contrôle qui ne parle que lorsqu il accuse est indiscernable d un contrôle qui n a pas
    tourné : c est exactement le silence qui a coûté le login de production.
    """
    if not entree:
        return [
            "qualif : parcours d ENTREE non joue — la chaine de redirections depuis la racine n a "
            "pas ete relevee ; ce que voit un visiteur SANS session reste inconnu de cet audit"
        ]
    if entree.get("erreur"):
        return [
            "qualif : parcours d ENTREE non concluant sur "
            f"{config.get('base') or 'l instance'} ({entree['erreur']}) — la chaine n est pas "
            "jugee : une ignorance n accuse jamais"
        ]
    chaine = [m for m in (entree.get("chaine") or []) if m]
    trace = " -> ".join(
        f"{_sans_secret(str(m.get('url') or ''))} ({m.get('statut') or 'sans statut'})"
        for m in chaine
    ) or "aucun maillon"
    limite = (
        "qualif : le parcours d ENTREE suit les redirections HTTP et le rendu INITIAL de la page "
        "d arrivee ; une bascule d authentification operee en JavaScript apres chargement (ou une "
        "mire rendue derriere un second clic) n est pas suivie"
    )
    if not any(_est_saut_auth(str(m.get("url") or "")) for m in chaine):
        return [
            "qualif : parcours d ENTREE joue SANS session — la racine ne redirige vers aucune "
            f"authentification ({trace}) : instance publique de ce point de vue, il n y a pas de "
            "porte d entree a verifier et le pan n en invente pas",
            limite,
        ]
    marqueur = _marqueur_mire(entree, config)
    if diagnostiquer_entree(entree, config) is None:
        return [
            "qualif : parcours d ENTREE joue SANS session — la chaine aboutit a une mire "
            f"IDENTIFIABLE ({marqueur}) : {trace}. Un itineraire passant par un IdP externe est "
            "sain des lors qu il arrive quelque part",
            limite,
        ]
    return [limite]


def _relever_entree(navigateur, config: dict) -> dict:  # noqa: ANN001
    """Relève la chaîne de redirections depuis la racine, dans un contexte VIERGE.

    Contexte neuf et sans storage state : c est la condition du contrôle, pas un détail
    d implémentation. Rejouer cette navigation dans le contexte authentifié mesurerait ce que
    voit quelqu un qui est déjà entré — précisément la mesure qui n a rien vu.
    """
    contexte = navigateur.new_context()
    vide = {"chaine": [], "corps": "", "titre": "", "erreur": None}
    try:
        page = contexte.new_page()
        reponse = page.goto(config["base"] + "/", wait_until="domcontentloaded", timeout=45000)
        if reponse is None:
            return {**vide, "erreur": "aucune reponse HTTP observee sur la racine"}
        chaine: list[dict] = []
        requete = reponse.request
        while requete is not None:
            reponse_maillon = requete.response()
            chaine.append(
                {
                    "url": requete.url,
                    "statut": reponse_maillon.status if reponse_maillon is not None else None,
                }
            )
            requete = requete.redirected_from
        chaine.reverse()
        try:
            titre = page.evaluate(_JS_TITRE) or ""
        except Exception:  # noqa: BLE001
            titre = ""
        try:
            corps = page.content()[:20000]
        except Exception:  # noqa: BLE001
            corps = ""
        return {"chaine": chaine, "corps": corps, "titre": titre, "erreur": None}
    except Exception as erreur:  # noqa: BLE001 — une entree injoignable se DECLARE, sans accuser
        return {**vide, "erreur": f"{type(erreur).__name__}: {erreur}"}
    finally:
        with contextlib.suppress(Exception):
            contexte.close()


# Descripteur de chaque affordance, lu dans le DOM RENDU (et non dans le gabarit source).
_JS_AFFORDANCES = """
() => Array.from(document.querySelectorAll(__SELECTEUR__)).map((e, i) => {
  const attributs = {};
  for (const a of e.attributes) attributs[a.name.toLowerCase()] = a.value;
  const formulaire = e.closest('form');
  return {
    rang: i,
    tag: e.tagName.toLowerCase(),
    attributs,
    libelle: (e.getAttribute('aria-label') || e.textContent || e.value || '').trim().slice(0, 60),
    dans_formulaire: formulaire !== null,
    action_formulaire: formulaire ? (formulaire.getAttribute('action') || '') : null,
    handler_formulaire: formulaire
      ? Array.from(formulaire.attributes).some(a => a.name.toLowerCase().startsWith('on'))
      : false,
  };
})
""".replace("__SELECTEUR__", json.dumps(_SELECTEUR))

_JS_LIENS = (
    "() => Array.from(document.querySelectorAll('a[href]'))"
    ".map(a => a.getAttribute('href'))"
)
_JS_TITRE = """
() => {
  const h = Array.from(document.querySelectorAll('h1'))
    .map(e => (e.textContent || '').trim()).find(t => t.length > 2);
  return h || (document.title || '').trim();
}
"""


def _config(cible: Path) -> dict:
    from forge_tests.authentification import charger_env

    charger_env(cible)
    base = (
        os.environ.get("FORGE_TESTS_QUALIF_URL")
        or os.environ.get("FORGE_TESTS_BASE_URL")
        or ""
    ).strip()
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    marqueurs: dict[str, str] = {}
    brut = (os.environ.get("FORGE_TESTS_QUALIF_MARQUEURS") or "").strip()
    if brut:
        try:
            lu = json.loads(brut)
            if isinstance(lu, dict):
                marqueurs = {str(k): str(v) for k, v in lu.items()}
        except json.JSONDecodeError:
            marqueurs = {}
    plafond = (os.environ.get("FORGE_TESTS_QUALIF_PLAFOND") or "").strip()
    return {
        "base": base.rstrip("/"),
        "amorces": [
            r.strip()
            for r in (os.environ.get("FORGE_TESTS_QUALIF_ROUTES") or "").split(",")
            if r.strip()
        ],
        "marqueurs": marqueurs,
        "connexion": (os.environ.get("FORGE_TESTS_QUALIF_CONNEXION") or "").strip(),
        # TF-0268 : origines publiques DÉCLARÉES du produit — celles qu une URL auto-référente
        # a le droit de porter en plus de celle de l instance auditée. Absente par défaut : le
        # repère est alors l instance elle-même, et rien d autre.
        "origines": [
            o.strip()
            for o in (os.environ.get("FORGE_TESTS_QUALIF_ORIGINES") or "").split(",")
            if o.strip()
        ],
        "login": (os.environ.get("FORGE_TESTS_QUALIF_LOGIN") or os.environ.get(
            "FORGE_TESTS_LOGIN"
        ) or "").strip(),
        "mdp": (os.environ.get("FORGE_TESTS_QUALIF_PASSWORD") or os.environ.get(
            "FORGE_TESTS_PASSWORD"
        ) or "").strip(),
        # TF-0222 : session ouverte AILLEURS. Aucun repli sur une variable non préfixée : ces
        # deux valeurs portent une identité, elles ne se ramassent pas par accident.
        "storage_state": (os.environ.get("FORGE_TESTS_QUALIF_STORAGE_STATE") or "").strip(),
        # TF-0316 : N sessions ÉTIQUETÉES (`role=chemin`, virgule). Le singulier ci-dessus reste
        # valide ; le pluriel est ce qui rend une couverture PAR RÔLE mesurable.
        "storage_states": [
            paire.strip()
            for paire in (os.environ.get("FORGE_TESTS_QUALIF_STORAGE_STATES") or "").split(",")
            if paire.strip()
        ],
        "bearer": (os.environ.get("FORGE_TESTS_QUALIF_BEARER") or "").strip(),
        # TF-0325 (1) : les routes d ATTERRISSAGE que le produit sert pour dire « accès refusé »
        # quand il ne rend ni 401 ni 403 et que sa page n est pas une mire (`/erreur/403`,
        # `/oups`…). Déclarées, elles sont le juge ; absentes, seule l heuristique prudente
        # ci-dessous parle, et ce qu elle ne reconnaît pas reste NON JUGÉ plutôt qu accusé.
        "refus": [
            r.strip()
            for r in (os.environ.get("FORGE_TESTS_QUALIF_REFUS") or "").split(",")
            if r.strip()
        ],
        "plafond": int(plafond) if plafond.isdigit() else _PLAFOND_DEFAUT,
    }


def _route(url: str, base: str) -> str | None:
    """Chemin interne d une URL, ou None si elle sort du domaine audité."""
    if url.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    absolu = urljoin(base + "/", url)
    depart, arrivee = urlparse(base), urlparse(absolu)
    if (arrivee.scheme, arrivee.netloc) != (depart.scheme, depart.netloc):
        return None
    return (arrivee.path or "/").rstrip("/") or "/"


# --- URLs auto-référentes : ce par quoi une page SERVIE se désigne elle-même (TF-0268) --------
# Une page se nomme de quatre façons, toutes destinées à des TIERS (moteurs, réseaux sociaux,
# agrégateurs, robots), toutes absolues par nature : la canonique, `og:url`, le `url`/`@id` du
# JSON-LD, les `loc` d un sitemap. Aucun test unitaire ne peut les juger — un TestClient ne sert
# aucune origine, il n a rien à quoi les comparer. Seul un auditeur d instance SERVIE tient les
# deux termes : ce que la page ANNONCE, et où elle est RÉELLEMENT servie. C est donc ici, et
# nulle part ailleurs, que le contrôle a un sens.
#
# Constaté le 15/08 : 184 routes sur 184 au vert sur une instance dont la canonique, les sept
# `loc` du sitemap, le `url` du JSON-LD et `og:url` pointaient tous `http://localhost:8000` —
# une valeur de développement figée dans les gabarits. Le produit était prêt à publier, à tout
# tiers qui le lit, l adresse d une machine qui n existe pas ailleurs que sur le poste qui l a
# construit. Le pan VOYAIT ces URLs dans le corps des pages ; il ne les confrontait à rien.
_BALISE_CANONIQUE = re.compile(
    r"<link\b[^>]*\brel\s*=\s*[\"']?canonical[\"']?[^>]*>", re.IGNORECASE
)
_BALISE_OG_URL = re.compile(
    r"<meta\b[^>]*\b(?:property|name)\s*=\s*[\"']og:url[\"'][^>]*>", re.IGNORECASE
)
_BALISE_LOC = re.compile(r"<loc\b[^>]*>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_BLOC_JSONLD = re.compile(
    r"<script\b[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_ATTRIBUT_HREF = re.compile(r"\bhref\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_ATTRIBUT_CONTENT = re.compile(r"\bcontent\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
# Les deux clés par lesquelles une entité JSON-LD donne SON adresse. `name`, `image` ou `logo`
# désignent autre chose qu elle-même : les juger accuserait un produit pour l URL d un tiers.
_CLES_JSONLD = ("url", "@id")


def _urls_du_jsonld(bloc: str) -> list[str]:
    """`url` et `@id` d un bloc JSON-LD, à toute profondeur. Un bloc illisible ne dit rien."""
    try:
        donnees = json.loads(bloc.strip())
    except json.JSONDecodeError:
        # Un JSON-LD malformé est un défaut d un AUTRE contrôle : ici il n atteste rien, et
        # l inventer serait pire que le taire.
        return []
    trouvees: list[str] = []
    restants: list = [donnees]
    while restants:
        noeud = restants.pop()
        if isinstance(noeud, dict):
            for cle, valeur in noeud.items():
                if cle in _CLES_JSONLD and isinstance(valeur, str):
                    trouvees.append(valeur)
                else:
                    restants.append(valeur)
        elif isinstance(noeud, list):
            restants.extend(noeud)
    return trouvees


def urls_auto_referentes(corps: str) -> list[tuple[str, str]]:
    """(nature, URL) des URLs ABSOLUES par lesquelles la page se désigne elle-même.

    Les URLs RELATIVES sont hors de ce contrôle, et c est voulu : elles ne portent aucune
    origine, donc elles ne peuvent pas en annoncer une fausse. C est même la forme saine.
    """
    trouvees: list[tuple[str, str]] = []
    for balise in _BALISE_CANONIQUE.findall(corps):
        trouvees.extend(("canonical", url) for url in _ATTRIBUT_HREF.findall(balise))
    for balise in _BALISE_OG_URL.findall(corps):
        trouvees.extend(("og:url", url) for url in _ATTRIBUT_CONTENT.findall(balise))
    for bloc in _BLOC_JSONLD.findall(corps):
        trouvees.extend(("json-ld", url) for url in _urls_du_jsonld(bloc))
    trouvees.extend(("sitemap-loc", url) for url in _BALISE_LOC.findall(corps))
    return [
        (nature, url)
        for nature, url in trouvees
        if url.lower().startswith(("http://", "https://"))
    ]


def _par_nature(corps: str) -> list[tuple[str, list[str]]]:
    """Les URLs auto-référentes d une page, groupées par nature, dans l ordre de découverte."""
    groupes: dict[str, list[str]] = {}
    for nature, url in urls_auto_referentes(corps):
        groupes.setdefault(nature, []).append(url)
    return list(groupes.items())


def _origine(url: str) -> str:
    """`schéma://hôte:port` — l origine au sens strict, celle que le navigateur compare."""
    morceaux = urlparse(url)
    return f"{morceaux.scheme.lower()}://{morceaux.netloc.lower()}"


def origines_admises(config: dict) -> set[str]:
    """Les origines qu une URL auto-référente a le droit de porter.

    Deux sources, aucune devinée : l instance RÉELLEMENT auditée (`FORGE_TESTS_QUALIF_URL`), et
    les origines publiques que le produit DÉCLARE (`FORGE_TESTS_QUALIF_ORIGINES`). La seconde
    existe pour le cas légitime — un produit audité en `http://…:8000` derrière un proxy TLS se
    publie en `https://…` — mais elle se déclare : sans déclaration, l origine auditée est le
    seul repère, et une URL qui s en écarte est un défaut.
    """
    candidates = [config.get("base") or "", *(config.get("origines") or [])]
    return {_origine(url) for url in candidates if url} - {"://"}


# --- Écouteurs réellement attachés, via le protocole DevTools ---------------------------------
def _ecouteurs(page) -> tuple[list[set[str]] | None, bool, str | None]:  # noqa: ANN001
    """(types d événements par affordance, délégation détectée, motif d indisponibilité).

    `None` en premier membre veut dire « le protocole n a pas répondu » : le jugement retombe
    alors sur les seuls attributs, comme le pan statique, et le dit.
    """
    try:
        session = page.context.new_cdp_session(page)
        session.send("DOM.enable")
        session.send("Runtime.enable")
        racine = session.send("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]
        noeuds = session.send(
            "DOM.querySelectorAll", {"nodeId": racine, "selector": _SELECTEUR}
        )["nodeIds"]
        par_element: list[set[str]] = []
        for noeud in noeuds:
            if not noeud:
                par_element.append(set())
                continue
            objet = session.send("DOM.resolveNode", {"nodeId": noeud})["object"]["objectId"]
            listes = session.send("DOMDebugger.getEventListeners", {"objectId": objet})
            par_element.append({e.get("type", "") for e in listes.get("listeners", [])})
        delegation = False
        for expression in ("document", "document.body"):
            objet = session.send("Runtime.evaluate", {"expression": expression})["result"].get(
                "objectId"
            )
            if not objet:
                continue
            listes = session.send("DOMDebugger.getEventListeners", {"objectId": objet})
            types = {e.get("type", "") for e in listes.get("listeners", [])}
            delegation = delegation or bool(types & {"click", "submit", "mousedown", "pointerdown"})
        session.detach()
    except Exception as erreur:  # noqa: BLE001 — le protocole se DECLARE indisponible, il ne tue rien
        return None, False, f"{type(erreur).__name__}: {erreur}"
    return par_element, delegation, None


def _a_un_effet(descripteur: dict, types: set[str] | None) -> str | None:
    """None si l affordance a un effet observable ; sinon le motif de son inertie, en clair."""
    table = descripteur["attributs"]
    if "disabled" in table or table.get("aria-disabled") == "true":
        return None  # inertie VOULUE et déclarée
    if any(nom.startswith(_PREFIXES_HANDLER) for nom in table):
        return None
    if types and (types & {"click", "submit", "mousedown", "pointerdown", "keydown"}):
        return None

    tag = descripteur["tag"]
    if tag == "a":
        href = table.get("href")
        if href is None:
            return "lien sans attribut href : aucune destination, aucun effet"
        if href.strip().lower() in _HREF_MORTS:
            return f"lien dont href vaut « {href.strip() or '(vide)'} » et sans écouteur attaché"
        return None
    if tag == "form":
        if (table.get("action") or "").strip() not in ("", "#"):
            return None
        return "formulaire sans action ni écouteur de soumission : rien n'est envoyé"

    type_ = table.get("type", "").lower()
    if type_ == "reset":
        return None  # effet natif garanti par le navigateur
    soumet = type_ == "submit" or (type_ == "" and descripteur["dans_formulaire"])
    if soumet and descripteur["dans_formulaire"]:
        action = (descripteur.get("action_formulaire") or "").strip()
        if action not in ("", "#") or descripteur.get("handler_formulaire"):
            return None
        return (
            "bouton de soumission d'un formulaire sans action ni écouteur : le clic n'envoie rien"
        )
    if soumet and table.get("form"):
        return None  # rattaché à un formulaire nommé ailleurs
    return "élément interactif sans écouteur attaché, sans destination et sans soumission"


# --- Parcours ---------------------------------------------------------------------------------
# TF-0313 : `domcontentloaded` ne dit RIEN du rendu d une application qui rend en JavaScript, et
# la SPA est le cas MAJORITAIRE de la cible de ce pan. Rejoué à l identique contre l instance
# servie de BAV2 (React 18 + Ant Design, `/login`) : à l instant du `domcontentloaded` le DOM est
# vide — ni champ mot de passe, ni identifiant, pas même un `button`. Le pan épuisait ses
# candidats et concluait « aucune mire de connexion trouvée » sur la BONNE route, avec un compte
# VALIDE. Contre-épreuve : la même mire, attendue, s ouvre (deux cookies JWT posés). L absence de
# mire ne se constate donc qu APRÈS expiration d une attente d APPARITION, jamais à l instant du
# chargement — et chaque candidat dit désormais OÙ il s est arrêté (TF-0315 le republie).
_SELECTEUR_MOTDEPASSE = "input[type=password]"
_SELECTEUR_IDENTIFIANT = (
    "input[type=email], input[name*=mail i], input[name*=login i], "
    "input[name*=user i], input[type=text]"
)
_SELECTEUR_SOUMISSION = "button[type=submit], input[type=submit], button"
# Le délai laissé au bundle pour MONTER la mire avant qu on ait le droit de dire qu il n y en a
# pas. Un pan qui n attend pas ne mesure pas l application, il mesure sa propre impatience.
ATTENTE_MIRE_MS = 10000


def _attendre(page, selecteur: str, timeout: int = ATTENTE_MIRE_MS):  # noqa: ANN001
    """Le premier élément correspondant, attendu jusqu à son APPARITION ; None à l expiration.

    Sans attente, « pas encore rendu » et « jamais rendu » sont le même constat — et le pan
    publiait le second en n ayant observé que le premier.
    """
    try:
        return page.wait_for_selector(selecteur, timeout=timeout)
    except Exception:  # noqa: BLE001 — expiration : l element n a PAS paru, et c est le constat
        return None


def _cookies(page) -> set[str]:  # noqa: ANN001
    """NOMS des cookies posés dans le contexte — les valeurs ne sortent jamais d ici."""
    try:
        return {str(biscuit.get("name") or "") for biscuit in page.context.cookies()}
    except Exception:  # noqa: BLE001 — un contexte muet n atteste rien, il n invente rien
        return set()


def _url_courante(page) -> str:  # noqa: ANN001
    try:
        return str(page.url or "")
    except Exception:  # noqa: BLE001
        return ""


def _constater_ouverture(
    page,  # noqa: ANN001
    route: str,
    cookies_avant: set[str],
    config: dict,
) -> dict:
    """L ouverture de session se CONSTATE (TF-0314) — deux attestations, aucune déduction.

    Dans l ordre de force :
      - un cookie de session a été POSÉ pendant la soumission (cas réel BAV2 : deux cookies JWT,
        `access_token_cookie` et `refresh_token_cookie`) ;
      - la mire a RENDU LA MAIN : la page a quitté la route de la mire et n y rend plus de champ
        de mot de passe — un jeton peut vivre en stockage local, où aucun cookie ne l atteste.

    Tout le reste est un ÉCHEC constaté, y compris « le clic a été émis » : c est précisément la
    déduction que ce constat remplace.
    """
    poses = sorted(nom for nom in _cookies(page) - cookies_avant if nom)
    if poses:
        return {
            "etat": SESSION_OUVERTE,
            "preuve": (
                f"{len(poses)} cookie(s) de session pose(s) par la soumission de {route} : "
                + ", ".join(poses[:4])
            ),
        }
    # Une URL courante ILLISIBLE ne dit rien : la résoudre quand même la ramènerait à « / », donc
    # à « ce n est plus la mire » — un constat d ouverture fabriqué par une ignorance.
    url = _url_courante(page)
    arrivee = _route(url, config["base"]) if url else None
    mire = _route(route, config["base"])
    if arrivee is not None and arrivee != mire:
        if page.query_selector(_SELECTEUR_MOTDEPASSE) is None:
            return {
                "etat": SESSION_OUVERTE,
                "preuve": (
                    f"la mire {mire} a rendu la main : arrivee sur {arrivee}, sans champ de mot "
                    "de passe rendu et sans cookie de session observe (jeton hors cookie)"
                ),
            }
        return {
            "etat": SESSION_ECHOUEE,
            "motif": (
                f"la mire {mire} a ete remplie et soumise, la page a navigue vers {arrivee} et la "
                "mire y est TOUJOURS rendue — aucun cookie de session pose"
            ),
            "arret": f"{mire} : soumission suivie d une mire encore rendue sur {arrivee}",
        }
    return {
        "etat": SESSION_ECHOUEE,
        "motif": (
            f"la mire {mire} a ete remplie et soumise, et l ouverture de session n est PAS "
            "constatee : aucun cookie pose, aucune sortie de la mire"
        ),
        "arret": f"{mire} : soumission sans effet observable",
    }


def _connecter(page, config: dict) -> dict:  # noqa: ANN001
    """Tente d ouvrir une session, et rend ce qui a été CONSTATÉ (TF-0313, TF-0314).

    Renvoie l état (`SESSION_*`), la preuve de l ouverture quand elle est constatée, sinon le
    motif de l échec et le point d ARRÊT exact — que `champs_requis` republie (TF-0315).
    """
    if not (config["login"] and config["mdp"]):
        return {"etat": SESSION_SANS_COMPTE}
    candidates = [config["connexion"]] if config["connexion"] else ["/connexion", "/login"]
    arrets: list[str] = []
    for route in candidates:
        if not route:
            continue
        cookies_avant = _cookies(page)
        try:
            page.goto(config["base"] + route, wait_until="domcontentloaded", timeout=30000)
        except Exception as erreur:  # noqa: BLE001
            arrets.append(f"{route} : navigation impossible ({type(erreur).__name__})")
            continue
        mdp = _attendre(page, _SELECTEUR_MOTDEPASSE)
        if mdp is None:
            arrets.append(
                f"{route} : aucun « {_SELECTEUR_MOTDEPASSE} » apparu en "
                f"{ATTENTE_MIRE_MS // 1000} s"
            )
            continue
        identifiant = _attendre(page, _SELECTEUR_IDENTIFIANT)
        if identifiant is None:
            arrets.append(f"{route} : champ mot de passe present, aucun champ identifiant")
            continue
        identifiant.fill(config["login"])
        mdp.fill(config["mdp"])
        bouton = _attendre(page, _SELECTEUR_SOUMISSION)
        if bouton is None:
            arrets.append(f"{route} : mire remplie, aucun bouton de soumission")
            continue
        bouton.click()
        page.wait_for_load_state("networkidle")
        return _constater_ouverture(page, route, cookies_avant, config)
    return {
        "etat": SESSION_SANS_MIRE,
        "motif": (
            "aucune mire de connexion trouvee, APRES attente d apparition du champ mot de passe "
            f"({ATTENTE_MIRE_MS // 1000} s par route) — routes essayees : "
            + " · ".join(arrets or [", ".join(c for c in candidates if c)])
            + " ; la declarer par FORGE_TESTS_QUALIF_CONNEXION"
        ),
        "arret": " · ".join(arrets),
    }


def _avec_role(alertes: list[str], role: str | None) -> list[str]:
    """Les mêmes alertes, ÉTIQUETÉES du rôle qui les a rencontrées — TF-0325 (2).

    L étiquette suit l idiome déjà posé pour le motif de session (« (role « admin ») … ») : ce sont
    deux constats de la même nature, et le lecteur du rapport ne doit pas apprendre deux formes.
    Sans rôle (N = 1 non étiqueté), l alerte est rendue telle quelle — ajouter « (role «  ») »
    fabriquerait une dimension que l opérateur n a pas déclarée.
    """
    if not role:
        return list(alertes)
    return [f"qualif : (role « {role} ») {alerte.removeprefix('qualif : ')}" for alerte in alertes]


def _visiter(page, config: dict) -> tuple[list[dict], list[str]]:  # noqa: ANN001
    """Visite chaque route atteignable et relève tout ce qui s y voit."""
    base = config["base"]
    a_visiter: deque[str] = deque(["/", *config["amorces"]])
    vues: set[str] = set()
    releve: list[dict] = []
    avertissements: list[str] = []
    journal: list[str] = []
    page.on("console", lambda m: journal.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: journal.append(str(e)))

    while a_visiter and len(vues) < config["plafond"]:
        route = a_visiter.popleft()
        if route in vues:
            continue
        vues.add(route)
        journal.clear()
        problemes: list[str] = []
        statut: int | None = None
        try:
            reponse = page.goto(base + route, wait_until="networkidle", timeout=45000)
            statut = reponse.status if reponse is not None else None
        except Exception as erreur:  # noqa: BLE001 — une route injoignable est un CONSTAT
            problemes.append(f"navigation impossible : {type(erreur).__name__}")
            releve.append(
                {"route": route, "statut": None, "problemes": problemes, "affordances": [],
                 "corps": "", "console": [], "url_finale": ""}
            )
            continue
        corps = page.content()
        if statut is None:
            problemes.append("aucune réponse HTTP observée")
        elif statut >= 500:
            problemes.append(f"erreur serveur HTTP {statut}")
        elif statut >= 400:
            problemes.append(f"route atteignable par un lien mais HTTP {statut}")
        minuscule = corps.lower()
        for trace in _TRACES:
            if trace in minuscule:
                problemes.append(f"trace d'exception rendue dans la page (« {trace} »)")
                break
        marqueur = config["marqueurs"].get(route)
        if marqueur is None:
            try:
                marqueur = page.evaluate(_JS_TITRE) or ""
            except Exception:  # noqa: BLE001
                marqueur = ""
            if not marqueur.strip():
                problemes.append(
                    "aucun marqueur de contenu : ni `h1` ni `title` non vide — la page répond "
                    "mais n'affiche rien d'identifiable"
                )
        elif marqueur.lower() not in minuscule:
            problemes.append(f"marqueur de contenu absent : {marqueur!r}")

        affordances: list[dict] = []
        if statut is not None and statut < 400:
            try:
                descripteurs = page.evaluate(_JS_AFFORDANCES)
            except Exception:  # noqa: BLE001
                descripteurs = []
            types, delegation, motif = _ecouteurs(page)
            if motif is not None:
                avertissements.append(
                    f"qualif : protocole DevTools indisponible sur {route} ({motif}) — "
                    "affordances jugees sur leurs seuls attributs, comme en statique"
                )
            for descripteur in descripteurs:
                rang = descripteur["rang"]
                attaches = types[rang] if types is not None and rang < len(types) else None
                affordances.append(
                    {
                        "rang": rang,
                        "tag": descripteur["tag"],
                        "libelle": " ".join((descripteur["libelle"] or "").split())[:60],
                        "motif": _a_un_effet(descripteur, attaches),
                        "delegation": delegation,
                    }
                )
            if delegation:
                avertissements.append(
                    f"qualif : delegation d evenement posee sur document/body de {route} — les "
                    "affordances sans ecouteur propre y sont NON JUGEES, jamais accusees"
                )
            # Les liens de cette page alimentent le parcours.
            try:
                for href in page.evaluate(_JS_LIENS):
                    suivant = _route(href or "", base)
                    if suivant is not None and suivant not in vues:
                        a_visiter.append(suivant)
            except Exception:  # noqa: BLE001
                pass
        releve.append(
            {
                "route": route,
                "statut": statut,
                # TF-0316 : OÙ la navigation a réellement abouti. Un refus d autorisation joué en
                # redirection rend 200 sur la mire : sans cette URL, il se comptait pour un succès.
                "url_finale": _url_courante(page),
                "problemes": problemes,
                "affordances": affordances,
                # Tronque : sur une instance reelle, garder 40 pages entieres en memoire pour
                # n en relire que le debut a la recherche d une variable citee serait un cout
                # sans contrepartie.
                "corps": corps[:20000],
                "console": list(journal),
            }
        )
    return releve, avertissements


def analyser(cible: Path) -> SortieAdaptateur:
    from forge_tests.qualification import declarer

    config = _config(cible)
    if not config["base"]:
        declarer(cible, "acces", CHAMPS_REQUIS_INSTANCE)
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "qualif : aucune instance servie declaree — le pan exige une application EN "
                "SERVICE et PEUPLEE, il ne peut ni la construire ni la peupler lui-meme ; "
                "fournir FORGE_TESTS_QUALIF_URL puis `--reprendre` le rapport",
            ],
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "qualif : Playwright absent de l environnement de Forge Tests — "
                "`uv sync` puis `uv run playwright install chromium`",
                # Y compris le parcours d entree : sans navigateur, la porte n est pas regardee
                # non plus, et le taire ferait croire qu elle l a ete.
                *mentions_entree(None, config),
            ],
        )

    non_juge = list(NON_JUGE)
    entree: dict | None = None
    # TF-0314 : la session est un objet dont l état se remplit par CONSTAT, et il est publié même
    # quand le parcours s effondre ensuite — une provenance non relevée se DIT, elle ne se devine
    # pas. `etat` à None veut dire « pas encore relevé », et la provenance le dira ainsi.
    sessions: list[dict] = [{"role": "", "etat": None}]
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            # TF-0223 — la porte d entree D ABORD, dans un contexte VIERGE : toute session ouverte
            # ensuite (mire rejouee ou storage state charge) rendrait ce releve aveugle a ce qu il
            # existe pour voir. L ordre n est pas un confort, c est le controle lui-meme.
            entree = _relever_entree(navigateur, config)
            # TF-0316 — UNE session, ou N sessions etiquetees par role. Meme boucle dans les deux
            # cas : le cas mono n est pas un cas a part, c est N = 1, et il se declare comme tel.
            declarees, alertes_sessions = sessions_declarees(config)
            sessions[:] = declarees
            non_juge.extend(alertes_sessions)
            releve, avertissements = [], []
            for session in sessions:
                # UN CONTEXTE PAR SESSION : deux identites dans le meme contexte melangeraient
                # leurs cookies, et la couverture par role ne voudrait plus rien dire.
                vue = {**config, "storage_state": session["storage_state"]}
                options, alertes = _options_contexte(vue)
                # L ecart declare par `_options_contexte` corrige la vue : la provenance publiee
                # ensuite ne peut pas annoncer une session que le fichier n a jamais portee.
                session["storage_state"] = vue["storage_state"]
                non_juge.extend(alertes)
                contexte = navigateur.new_context(**options)
                if config["bearer"]:
                    contexte.set_extra_http_headers(
                        {"Authorization": _entete_autorisation(config["bearer"])}
                    )
                page = contexte.new_page()
                # Une session FOURNIE prime : rejouer la mire par-dessus ecraserait l identite
                # qu on nous a confiee, et le rapport annoncerait une provenance qui n est plus
                # la bonne.
                if not session_fournie(vue):
                    session.update(_connecter(page, vue))
                    if session.get("motif"):
                        etiquette = f"(role « {session['role']} ») " if session["role"] else ""
                        non_juge.append(f"qualif : {etiquette}{session['motif']}")
                vues, alertes_visite = _visiter(page, vue)
                for page_vue in vues:
                    page_vue["role"] = session["role"]
                releve.extend(vues)
                # TF-0325 (2) — l avertissement par ROUTE porte son RÔLE. `sorted(set(...))` plus
                # bas dédoublonne : deux profils dont la même route est muette au DevTools ne
                # produisaient qu une ligne, et la dimension rôle — la seule qui compte dès que N
                # sessions sont déclarées — était perdue. « /admin non jugée » ne dit pas POUR QUI.
                avertissements.extend(_avec_role(alertes_visite, session["role"]))
                with contextlib.suppress(Exception):
                    contexte.close()
            navigateur.close()
    except Exception as erreur:  # noqa: BLE001 — un pan qui ne peut pas voir le DECLARE
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            # TF-0223 : le constat d entree survit MEME ici. Une instance dont l interieur est
            # inaccessible est justement celle dont la porte merite d etre regardee.
            findings=[f for f in (finding_entree(entree, config, cible),) if f is not None],
            non_juge=[
                *non_juge,
                *_provenances(config, sessions),
                *mentions_entree(entree, config),
                f"qualif : instance {config['base']} non parcourable "
                f"({type(erreur).__name__}: {erreur})",
            ],
        )
    if not releve:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            findings=[f for f in (finding_entree(entree, config, cible),) if f is not None],
            non_juge=[
                *non_juge,
                *_provenances(config, sessions),
                *mentions_entree(entree, config),
                f"qualif : aucune route atteinte sur {config['base']}",
            ],
        )
    non_juge.extend(sorted(set(avertissements)))
    return conclure(cible, config, releve, non_juge, entree, sessions)


def finding_entree(entree: dict | None, config: dict, cible: Path) -> Finding | None:
    """Le constat d impasse de la porte d entrée, ou None. Un seul point de fabrication."""
    motif = diagnostiquer_entree(entree, config)
    if motif is None:
        return None
    return Finding(
        id=IDENT_ENTREE,
        classe=CLASSE_ENTREE,
        localisation=f"{config.get('base') or ''}/",
        message=f"parcours d entree SANS session — {motif}",
        risque=coter(PAN, IDENT_ENTREE, str(cible)),
    )


def conclure(
    cible: Path,
    config: dict,
    releve: list[dict],
    non_juge: list[str],
    entree: dict | None = None,
    sessions: list[dict] | None = None,
) -> SortieAdaptateur:
    """Traduit le relevé de parcours en verdict — SEUL endroit où ce pan accuse le produit.

    Séparé de `analyser` pour que la garde de précondition et les constats qu elle retient
    soient prouvables sans navigateur : c est le relevé qui décide, et un relevé s écrit. Il en
    va de même du parcours d entrée (`entree`, TF-0223) : une chaîne de redirections est une
    donnée, et son jugement se prouve sans Chromium.

    `sessions` porte ce qui a été CONSTATÉ de chaque session exercée (TF-0314) ; absent, il vaut
    « une session, dont le résultat n a pas été relevé » — et la provenance le dira ainsi plutôt
    que d affirmer une identité.
    """
    from forge_tests.noyau import NonTestable
    from forge_tests.qualification import declarer, detecter

    sessions = list(sessions or [{"role": "", "etat": None}])
    non_juge = [
        *non_juge,
        *_provenances(config, sessions),
        *mentions_entree(entree, config),
    ]
    # TF-0223 — fabriqué AVANT la garde, et volontairement pas soumis à elle : la garde dit que
    # le pan n a pas vu l INTÉRIEUR de l instance ; le parcours d entrée, lui, s est joué sans
    # session et n avait rien à établir. Le taire ici reconstruirait un étage plus bas le silence
    # que la garde vient de corriger — un pan aveugle au contenu authentifié doit quand même
    # pouvoir dire « et en plus, votre porte d entrée est murée ».
    constat_entree = finding_entree(entree, config, cible)

    # RT-16 : AVANT tout constat TIRÉ DU PARCOURS AUTHENTIFIÉ. Un pan qui n a pas pu établir
    # l état qu il exige ne mesure pas le produit, il mesure son propre échec — le publier comme
    # un défaut du produit fabrique un bloc de findings identiques, tous au même risque, qu il
    # faut un audit entier pour démentir.
    motif = precondition_absente(releve, config, sessions)
    if motif is not None:
        # TF-0315 : la demande de réparation suit CE QUI A ÉTÉ CONSTATÉ. Réclamer un compte déjà
        # fourni et valide envoie l opérateur refaire trois gestes faits, puis douter de son
        # compte — c est le temps perdu mesuré sur l audit du 17/08.
        requis = champs_a_fournir(config, sessions)
        tente = detail_connexion(sessions)
        declarer(cible, "acces", requis)
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            findings=[constat_entree] if constat_entree is not None else [],
            non_juge=[*non_juge, motif],
            # L inventaire est NOMMÉ route par route — non mesurable, jamais « rien à voir ici ».
            non_testables=[
                NonTestable(
                    element=_identifiant(page_vue, f"route:{page_vue['route']}"),
                    champs_requis=list(requis),
                    pan=PAN,
                    motif=(
                        f"qualif : {page_vue['route']} non mesurable — precondition du pan "
                        f"(session ouverte) non etablie ;{tente} Aucun constat produit n en est "
                        "tire"
                    ),
                )
                for page_vue in releve
            ],
        )

    inventaire: list[str] = []
    exerces: list[str] = []
    findings: list[Finding] = []
    non_testables: list = []
    admises = origines_admises(config)
    # TF-0316 : le rôle de chaque élément inventorié, pour rendre une couverture PAR RÔLE ; et les
    # routes REFUSÉES à l identité qui les a demandées, qui sortent du ratio pour ne plus se
    # confondre avec un succès.
    role_de: dict[str, str] = {}
    refuses: list[str] = []

    # TF-0223 — la porte d entrée est un ÉLÉMENT DE SURFACE comme une route : inventoriée quand
    # elle a été relevée, exercée quand elle aboutit à une mire. Hors inventaire, un contrôle qui
    # se tait redevient indiscernable d un contrôle qui n a pas tourné.
    if entree is not None and not entree.get("erreur"):
        inventaire.append(IDENT_ENTREE)
        # La porte d entrée est relevée dans un contexte VIERGE : elle n appartient à aucune
        # session, et la couverture par rôle la range donc à part plutôt que de la prêter à un rôle.
        role_de[IDENT_ENTREE] = ROLE_ENTREE
        if constat_entree is None:
            exerces.append(IDENT_ENTREE)
        else:
            findings.append(constat_entree)

    for page_vue in releve:
        route = page_vue["route"]
        role = str(page_vue.get("role") or "")
        identifiant = _identifiant(page_vue, f"route:{route}")
        # TF-0316 — une route REFUSÉE à cette identité n est pas un défaut du produit et n est pas
        # un succès : elle sort du ratio, en issue DISTINCTE. Avant, un 403 comptait comme une
        # route en défaut du produit, et un refus joué en REDIRECTION (200 sur la mire, avec son
        # titre) comptait pour EXERCÉ — indiscernable d une route saine dans le ratio.
        refus = refus_autorisation(page_vue, config)
        if refus is not None:
            refuses.append(identifiant)
            role_de[identifiant] = role
            findings.append(
                Finding(
                    id=identifiant,
                    classe=CLASSE_REFUS_AUTORISATION,
                    localisation=f"{config['base']}{route}",
                    message=(
                        f"{route} — REFUSEE a l identite exercee"
                        + (f" (role « {role} »)" if role else " (session unique de cet audit)")
                        + f" : {refus}. La route existe et n est PAS jugee sous ce profil — elle "
                        "est hors du ratio, qui ne mesure que ce que cette identite a pu voir"
                    ),
                    risque=coter(PAN, identifiant, str(cible)),
                )
            )
            continue
        inventaire.append(identifiant)
        role_de[identifiant] = role
        # RT-6a : une route qui echoue en CITANT une configuration absente n accuse pas le
        # projet — elle nomme ce qu il manque ici, et `--reprendre` la rejouera une fois fourni.
        manquants = detecter(cible, "acces", f"{page_vue['corps']}\n" + "\n".join(
            page_vue["console"]
        )) if page_vue["problemes"] or page_vue["console"] else set()
        if manquants:
            non_testables.append(
                NonTestable(
                    element=identifiant,
                    champs_requis=sorted(manquants),
                    pan=PAN,
                    motif=(
                        f"qualif : {route} échoue en citant une configuration absente — "
                        f"fournir {', '.join(sorted(manquants))}, puis `--reprendre` le rapport"
                    ),
                )
            )
            continue
        ennuis = list(page_vue["problemes"])
        if page_vue["console"]:
            ennuis.append(f"erreur console : {page_vue['console'][0][:120]}")
        if ennuis:
            findings.append(
                Finding(
                    id=identifiant,
                    classe="route-en-defaut",
                    localisation=f"{config['base']}{route}",
                    message=f"{route} — " + " · ".join(ennuis),
                    risque=coter(PAN, identifiant, str(cible)),
                )
            )
        else:
            exerces.append(identifiant)

        # TF-0268 — chaque façon dont la page se NOMME est un élément de surface, confronté à
        # l origine réellement servie. Groupé par nature : sept `loc` de sitemap figés sur la
        # même mauvaise origine sont UN défaut de gabarit, pas sept ; les remonter en bloc
        # rejouerait exactement RT-16 (des constats identiques au même risque, qu il faut un
        # audit entier pour démentir).
        for nature, urls in _par_nature(page_vue["corps"]):
            cle = _identifiant(page_vue, f"url:{route}:{nature}")
            inventaire.append(cle)
            role_de[cle] = role
            etrangeres = sorted({url for url in urls if _origine(url) not in admises})
            if not etrangeres:
                exerces.append(cle)
                continue
            findings.append(
                Finding(
                    id=cle,
                    classe=CLASSE_URL_ETRANGERE,
                    localisation=f"{config['base']}{route}",
                    message=(
                        f"{route} — {nature} : {len(etrangeres)} URL(s) auto-référente(s) hors "
                        f"de l origine servie ({', '.join(sorted(admises))}) — "
                        f"{', '.join(_sans_secret(url) for url in etrangeres[:3])}"
                        + (" …" if len(etrangeres) > 3 else "")
                        + ". Publiée telle quelle à tout tiers qui la lit (moteur, réseau "
                        "social, robot) ; déclarer l origine publique par "
                        "FORGE_TESTS_QUALIF_ORIGINES si elle est légitime"
                    ),
                    risque=coter(PAN, cle, str(cible)),
                )
            )

        for affordance in page_vue["affordances"]:
            cle = _identifiant(
                page_vue, f"effet:{route}:{affordance['rang']}:{affordance['tag']}"
            )
            inventaire.append(cle)
            role_de[cle] = role
            if affordance["motif"] is None:
                exerces.append(cle)
            elif affordance["delegation"]:
                exerces.append(cle)  # non jugeable : deja NOMME en non_juge, jamais accuse
            else:
                findings.append(
                    Finding(
                        id=cle,
                        classe="affordance-sans-effet",
                        localisation=f"{config['base']}{route}",
                        message=(
                            f"{affordance['tag']} « {affordance['libelle'] or 'sans libellé'} » "
                            f"sur {route} — {affordance['motif']}"
                        ),
                        risque=coter(PAN, cle, str(cible)),
                    )
                )

    total = len(inventaire)
    ratio = len(exerces) / total if total else 0.0
    if total and ratio < SEUIL:
        findings.insert(
            0,
            Finding(
                id=f"seuil:{PAN}",
                classe="seuil-non-tenu",
                localisation=config["base"],
                message=(
                    f"qualification {ratio:.0%} sous le seuil {SEUIL:.0%} — "
                    f"{total - len(exerces)} élément(s) en défaut sur {total}"
                ),
                severite=seuils.severite("couverture_surface_qualif"),
                risque=coter(PAN, f"seuil:{PAN}", str(cible)),
            ),
        )
    findings.sort(key=lambda f: f.risque or 0, reverse=True)
    non_juge.append(
        f"qualif : {len(releve)} route(s) parcourue(s) sur {config['base']} — "
        f"{sum(len(p['affordances']) for p in releve)} affordance(s) lue(s) dans le DOM rendu"
    )
    # TF-0316, niveau (a) — la DÉCLARATION, celle qui reste vraie quel que soit N : « 8/8, ratio
    # 1,00 » s est lu « tout est couvert » pendant cinq jours alors qu une seule identité avait
    # parcouru et que trois surfaces réservées n avaient jamais été visitées.
    couverture = couverture_par_role(sessions, inventaire, exerces, refuses, role_de)
    non_juge.extend(declaration_couverture(config, sessions, refuses, role_de, couverture))
    # TF-0268 : le contrôle DIT ce qu il a confronté et à quoi, y compris quand il n a rien
    # trouvé — « aucune URL auto-référente » et « URLs jamais regardées » ne sont pas le même
    # rapport, et seul le premier se vérifie.
    lues = sum(len(urls) for page_vue in releve for _, urls in _par_nature(page_vue["corps"]))
    non_juge.append(
        f"qualif : {lues} URL(s) auto-referente(s) confrontee(s) a l origine servie "
        f"({', '.join(sorted(admises))}) — canonical, og:url, url/@id du JSON-LD et loc de "
        "sitemap, sur les seules routes PARCOURUES et les 20 000 premiers caracteres de chaque "
        "page ; les URLs RELATIVES ne portent pas d origine et ne sont pas jugees"
    )
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if [f for f in findings if f.severite == "bloquant"] else "PASS",
        findings=findings,
        non_juge=non_juge,
        non_testables=non_testables,
        surface={
            "inventorie": total,
            "exerce": len(exerces),
            "ratio": round(ratio, 4),
            "seuil": SEUIL,
            "elements_exerces": sorted(exerces),
            "elements_non_exerces": sorted(set(inventaire) - set(exerces)),
            # TF-0316 : la couverture par RÔLE, seule dimension qui compte pour un produit dont le
            # domaine est l autorisation multi-acteurs. Publiée même à N = 1 : le cas dégradé se
            # déclare, il ne se devine pas.
            "couverture_par_role": couverture,
            "elements_refuses": sorted(refuses),
        },
    )
