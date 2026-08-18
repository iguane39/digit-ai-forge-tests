"""Aller-retour : ce que le produit accepte d'écrire est-il ce qu'il relit ? — TF-0369.

Lot bourse-aux-vacants 20260818a, 18/08/2026.

**La classe de défaut** : le produit répond 200 et range autre chose. Ni la couverture, ni la
mutation (0,90 sur ce produit), ni un parcours ne la voient — **le parcours passe parce que le
produit fait ce que le parcours regarde.**

Deux défauts mesurés, tous deux DANS le périmètre couvert (parcours 6 « alertes », 69 tests
verts) :

  (1) `alerts.created_at` porte `default=datetime.now(timezone.utc)` : l'appel est évalué **une
      fois au chargement du module**, donc toute alerte est datée de l'instant de démarrage du
      conteneur. Écart mesuré par l'utilisateur : « alerte créée le 29/07, enregistrée au
      24/07 » — cinq jours, exactement l'âge du processus (anomalie 9870). Même défaut sur
      `push_subscriptions.created_at`.
  (2) `POST /alerts` écrase `email_notifications` à `False` EN DUR alors que l'écran envoie le
      choix de l'utilisateur : la case cochée disparaît sans un mot.

**Pourquoi c'était invisible**, et c'est ce qui fait la valeur des deux contrôles ci-dessous :

  · le parcours relit les CRITÈRES de l'objet, jamais ses SCALAIRES ;
  · une valeur figée reste **cohérente avec elle-même** tant qu'on n'observe qu'une occurrence ;
  · sur un poste local, le processus vient de naître — l'écart serait de quelques secondes,
    invisible **même en regardant**.

Ce module tient donc deux choses de nature différente, et il faut les distinguer :

  **(A) une lecture STATIQUE** — un défaut de type (1) se voit dans le code, sans rien exécuter :
  un défaut de champ évalué à l'import est une erreur de langage, pas un comportement. C'est le
  contrôle qui aurait attrapé l'anomalie 9870 le jour où elle a été écrite.

  **(B) un AXE DE CAS DÉRIVÉ** — un défaut de type (2) ne se voit pas dans le code (écraser une
  valeur peut être voulu) : il se voit en RELISANT ce qu'on vient d'écrire, champ par champ. Cet
  axe est dérivable sans spécification, puisque la surface d'écriture est déjà inventoriée.
"""

from __future__ import annotations

import ast
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Finding
from forge_tests.risque import coter

PAN = "data"

IGNORES = {"node_modules", ".venv", "__pycache__", ".git", ".oracles", ".pytest_cache",
           "dist", "build", "out", "tests", "test"}

#: Les appels dont la valeur DÉPEND DE L'INSTANT. Passés en défaut de champ, ils figent cet
#: instant à l'import du module. La liste est nominative : deviner « toute fonction pourrait
#: dépendre du temps » ferait dénoncer chaque défaut calculé, donc plus rien de lisible.
APPELS_TEMPORELS = {
    "now", "utcnow", "today", "time", "monotonic", "perf_counter", "date", "datetime",
    "uuid1", "uuid4", "random", "randint",
}

#: Ce qui déclare un DÉFAUT de champ, tous ORM confondus — on ne devine pas la bibliothèque.
MOTS_DEFAUT = {"default", "server_default", "default_factory", "missing"}


def _fichiers_modeles(cible: Path) -> list[Path]:
    if not cible.is_dir():
        return []
    return [
        f for f in sorted(cible.rglob("*.py"))
        if not (IGNORES & {p.name for p in f.parents})
    ]


def _nom_appele(noeud: ast.AST) -> str | None:
    """Le nom de la fonction appelée, ou None si ce n'est pas un appel."""
    if not isinstance(noeud, ast.Call):
        return None
    fonction = noeud.func
    if isinstance(fonction, ast.Attribute):
        return fonction.attr
    if isinstance(fonction, ast.Name):
        return fonction.id
    return None


def defauts_evalues_a_l_import(cible: Path) -> list[Finding]:
    """Un défaut de champ dont la valeur dépend de l'INSTANT, et qui est APPELÉ (TF-0369).

    `default=datetime.now(timezone.utc)` et `default=datetime.now` se lisent presque pareil et
    ne font pas du tout la même chose : le premier est évalué une fois, à l'import ; le second
    est un callable, évalué à chaque insertion. La différence est un couple de parenthèses, et
    elle vaut cinq jours d'écart sur une date affichée à l'utilisateur.

    Lecture par AST, pas par expression régulière : `default=f(g())` ou un appel réparti sur
    trois lignes doivent être vus comme ce qu'ils sont. Un motif textuel aurait manqué les deux.
    """
    findings: list[Finding] = []
    for fichier in _fichiers_modeles(cible):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        try:
            arbre = ast.parse(texte)
        except SyntaxError:
            # Un fichier qui ne parse pas n'est pas un défaut de ce contrôle : c'est un défaut
            # du projet, que son propre lint dira mieux. On ne le double pas ici.
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            for argument in noeud.keywords:
                if argument.arg not in MOTS_DEFAUT:
                    continue
                appele = _nom_appele(argument.value)
                if appele is None or appele not in APPELS_TEMPORELS:
                    continue
                relatif = fichier.relative_to(cible).as_posix()
                ligne = getattr(argument.value, "lineno", noeud.lineno)
                identifiant = f"data:defaut-evalue-a-l-import:{relatif}:{ligne}"
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.DEFAUT_EVALUE_A_L_IMPORT,
                        localisation=f"{relatif}:{ligne}",
                        message=(
                            f"`{argument.arg}=` reçoit le RÉSULTAT de `{appele}(…)`, pas la "
                            f"fonction : l appel est évalué UNE FOIS au chargement du module, "
                            f"donc chaque ligne écrite portera l instant du DÉMARRAGE du "
                            f"processus, pas le sien. Passer `{appele}` sans parenthèses (ou "
                            "`default_factory=`). Le défaut est invisible en local — le "
                            "processus vient de naître, l écart est de quelques secondes ; en "
                            "service il vaut l âge du conteneur (5 jours mesurés, anomalie 9870)"
                        ),
                        risque=coter(PAN, identifiant, relatif),
                    )
                )
    return findings


# --- (B) l'axe de cas dérivé ----------------------------------------------------------------------
#: Méthodes qui ÉCRIVENT : seules celles-là ont un aller-retour à vérifier.
METHODES_ECRITURE = ("POST", "PUT", "PATCH")


def cas_aller_retour(identifiant: str) -> dict | None:
    """Le cas dérivé « ce que je viens d'écrire, je le relis CHAMP PAR CHAMP ».

    Rendu pour un `endpoint:<MÉTHODE> <route>` d'écriture, sinon None. Dérivable sans
    spécification : la surface d'écriture est déjà inventoriée par le pan `api`.

    La règle temporelle est dans l'attendu, et elle est le cœur du cas : **un champ de date se
    compare à L'HORLOGE, jamais à lui-même.** Comparer une date à elle-même est exactement ce
    qui rendait le défaut (1) invisible — une valeur figée est cohérente avec elle-même.
    """
    if not identifiant.startswith("endpoint:"):
        return None
    reste = identifiant[len("endpoint:"):].strip()
    methode, _, route = reste.partition(" ")
    if methode.upper() not in METHODES_ECRITURE or not route:
        return None
    return {
        "suffixe": "aller-retour",
        "titre": f"{methode.upper()} {route} — ce qui est écrit est ce qui est relu",
        "preconditions": "le jeu de données du sous-chapitre est chargé ; l horloge du poste est "
                         "celle de référence",
        "gestes": [
            f"écrire un objet complet par {methode.upper()} {route}, en renseignant CHAQUE champ "
            "que l écran peut envoyer — surtout les booléens et les choix, pas seulement les "
            "champs obligatoires",
            "relire l objet par sa route de lecture",
            "comparer CHAMP PAR CHAMP l envoyé et le relu, y compris les scalaires (booléens, "
            "énumérations, compteurs) — un parcours qui ne relit que les critères ne voit pas "
            "qu un scalaire a été écrasé",
            "pour chaque champ de DATE, comparer à l horloge du test (écart attendu de quelques "
            "secondes), JAMAIS à la valeur relue d un autre objet ni à elle-même",
            "écrire un SECOND objet et vérifier que ses champs de date DIFFÈRENT de ceux du "
            "premier — deux dates identiques à la seconde révèlent une valeur figée à l import",
        ],
        "resultat_attendu": (
            "chaque champ envoyé est relu à l identique ; aucun champ n est remplacé en silence "
            "par une valeur du serveur (un écrasement VOULU se déclare dans le contrat, et le "
            "cas cite alors la ligne qui le déclare) ; chaque date relue est à quelques secondes "
            "de l horloge, et deux objets créés à des instants différents portent des dates "
            "différentes"
        ),
    }


NON_JUGE = [
    "aller-retour (statique) : la liste des appels dépendant de l INSTANT est NOMINATIVE "
    f"({', '.join(sorted(APPELS_TEMPORELS))}) — un défaut calculé par une fonction maison du "
    "projet n est pas reconnu, et le deviner ferait dénoncer chaque défaut calculé",
    "aller-retour (statique) : un `default=` correct dans un contexte qui n est pas un modèle "
    "(configuration, valeur de test) est signalé quand même — la lecture ne sait pas ce qui est "
    "persisté ; c est un faux positif ASSUMÉ, moins coûteux que le silence sur une date figée",
    "aller-retour (cas dérivé) : le cas est DÉRIVÉ, pas exécuté — il entre au cahier et se solde "
    "par R-40 comme les autres. Ce module ne relit rien lui-même : relire exige une instance",
]
