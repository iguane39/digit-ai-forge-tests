"""Un SECOND terme de comparaison externe : les anomalies déclarées — TF-0372.

Lot Produit-11 20260818a, 18/08/2026.

**Le fait.** Le sceau de tous les cahiers du produit portait `exigences_source: (absent)` et la
ligne « les cas sont dérivés de la SEULE SURFACE inventoriée ». C'est honnête, c'est déclaré, et
c'est même la limite fondatrice que `forge_tests/invariants.py` énonce lui-même : « on extrait
l'invariant TEL QU'IMPLÉMENTÉ, pas tel que voulu ; si la garde est fausse, le cas généré
confirmera le bug au lieu de le révéler ».

**Mais** un référentiel d'exigences est rare, alors qu'une LISTE D'ANOMALIES OUVERTES existe sur
presque tout produit vivant. Sur celui-ci elle existait : treize anomalies dans Azure Boards,
ouvertes les 29 et 30/07, priorités 1 à 3.

**Coût mesuré de leur absence** : six campagnes d'audit entre le 11 et le 18/08, 131 entrées au
ledger, verdict PARTIEL — et **pas une ligne, dans aucun rapport, aucun cahier, aucun ledger, ne
mentionne un seul de ces treize identifiants**. Au 18/08, huit sont toujours servies, dont quatre
visibles par n'importe quel utilisateur à chaque écran. Le recouvrement fortuit qui a eu lieu
(trois défauts trouvés recoupent deux anomalies) prouve la valeur du contrôle sans le rendre
fiable : il tenait au hasard de la séquence de test.

**Ce module RÉEMPLOIE `exigences.py`, il n'en écrit pas un second.** C'est l'exigence explicite
de l'item, et elle est juste : ce module-là calcule déjà le rattachement déclaré ou lexical avec
sa provenance, et — c'est la partie qui compte — **la réciproque que personne ne regarde jamais :
ce qu'AUCUN cas ne touche**. Une anomalie est, pour cette mécanique, une exigence d'une autre
sorte : un énoncé auquel des cas se rattachent, ou pas. Le refus déjà en place vaut tel quel —
un chemin déclaré et introuvable est un refus, pas un silence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from forge_tests.livrables import exigences as _exigences

VARIABLE = "FORGE_TESTS_ANOMALIES"

#: Format : JSONL, une anomalie par ligne — `id`, `titre`, `statut`, `priorite`. JSONL parce que
#: c'est ce qu'un export de gestionnaire de tickets produit le plus facilement, et parce qu'une
#: ligne illisible n'empêche pas de lire les autres (contrairement à un JSON global).
CHAMPS = ("id", "titre", "statut", "priorite")

#: Les statuts qui comptent. Une anomalie FERMÉE n'a pas à être couverte par un cas : l'exiger
#: ferait grossir le reste-à-faire de tout l'historique du produit, et le rendrait illisible.
STATUTS_OUVERTS = {"ouvert", "ouverte", "open", "new", "active", "a-faire", "en-cours", "doing"}


def chemin_declare(cible: Path | None = None) -> Path | None:
    """Le chemin déclaré par `FORGE_TESTS_ANOMALIES`, ou None. Même contrat que les exigences."""
    brut = (os.environ.get(VARIABLE) or "").strip()
    if not brut:
        return None
    chemin = Path(brut)
    return chemin if chemin.is_absolute() or cible is None else (cible / chemin)


def charger(chemin: Path | None) -> dict | None:
    """Les anomalies déclarées, normalisées EN RÉFÉRENTIEL — donc lisibles par `exigences`.

    Le retour a exactement la forme qu'`exigences.rattacher` et `exigences.sans_cas` attendent :
    une liste d'entrées portant `id`, `enonce`, `critere`, `elements` et `_racines`. C'est ce qui
    permet de ne pas écrire une seconde mécanique de rattachement — et donc de ne pas avoir deux
    façons divergentes de décider qu'un cas « touche » quelque chose.

    Un fichier déclaré et introuvable est un REFUS, pas un silence (même règle qu'`exigences`) :
    croire qu'il n'y a pas d'anomalies parce que le chemin est faux serait le pire des deux.
    """
    if chemin is None:
        return None
    if not chemin.is_file():
        raise FileNotFoundError(
            f"{VARIABLE} désigne « {chemin} », qui n existe pas — corriger le chemin ou retirer "
            "la variable ; une liste d anomalies introuvable ne se remplace pas par « aucune "
            "anomalie », qui est exactement l état où six campagnes ont tourné"
        )
    entrees, illisibles = [], []
    for rang, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            brut = json.loads(ligne)
        except json.JSONDecodeError:
            illisibles.append(rang)
            continue
        if not isinstance(brut, dict) or not str(brut.get("id") or "").strip():
            illisibles.append(rang)
            continue
        statut = str(brut.get("statut") or "").strip().lower()
        titre = str(brut.get("titre") or "")
        entrees.append({
            "id": str(brut["id"]).strip(),
            # `enonce` et `critere` sont les noms que `exigences` lit : une anomalie porte son
            # titre comme énoncé, et son statut+priorité comme critère de clôture lisible.
            "enonce": titre,
            "critere": f"statut {statut or 'non déclaré'} · priorité "
                       f"{brut.get('priorite') or 'non déclarée'}",
            "palier": str(brut.get("priorite") or ""),
            "surface": [],
            "libelles_surface": [],
            "elements": [str(e) for e in (brut.get("elements") or [])],
            "_racines": _exigences.racines(titre),
            "_statut": statut,
            "_ouverte": statut in STATUTS_OUVERTS or not statut,
        })
    return {
        "chemin": str(chemin),
        "projet": "",
        # La clé s'appelle `exigences` parce que c'est le nom que la mécanique réemployée lit.
        # La renommer obligerait à dupliquer `rattacher` et `sans_cas` — c'est-à-dire à créer la
        # seconde mécanique que l'item demande justement d'éviter.
        "exigences": entrees,
        "besoins": [],
        "illisibles": illisibles,
    }


def ouvertes(referentiel: dict | None) -> list[dict]:
    """Les seules qui comptent au reste-à-faire. Une anomalie fermée n'a pas à être couverte."""
    if not referentiel:
        return []
    return [a for a in referentiel["exigences"] if a.get("_ouverte")]


def restreindre_aux_ouvertes(referentiel: dict | None) -> dict | None:
    """Le référentiel réduit aux anomalies OUVERTES, prêt pour `exigences.sans_cas`.

    Passer le référentiel entier à la réciproque ferait sortir « non couverte » toute anomalie
    fermée du produit — un reste-à-faire qui grossit avec l'historique cesse d'être lu.
    """
    if not referentiel:
        return None
    return {**referentiel, "exigences": ouvertes(referentiel)}


def chapitre(referentiel: dict | None, rattachements: dict[str, list[dict]]) -> dict:
    """Le chapitre qui manquait : « anomalie déclarée → couverte par tel cas / non couverte ».

    `rattachements` est l'index que le cahier construit déjà : **élément de surface → liste des
    entrées rattachées**. On l'INVERSE ici plutôt que de le recalculer, pour la même raison qu'on
    ne réécrit pas `rattacher` — deux calculs du même rattachement finiraient par ne plus dire la
    même chose. C'est aussi ce qui garantit que « couverte » veut ici exactement ce qu'il veut
    pour une exigence.
    """
    if referentiel is None:
        return {
            "declare": False,
            "titre": "Anomalies déclarées",
            "resume": (
                f"aucune liste d anomalies déclarée (`{VARIABLE}`) — les cas sont dérivés de la "
                "SEULE surface inventoriée, donc AUCUN terme de comparaison externe. Ce n est "
                "pas un défaut du produit : c est l état dans lequel six campagnes ont tourné "
                "sans savoir que treize anomalies clients existaient (TF-0372)"
            ),
            "couvertes": [], "non_couvertes": [], "illisibles": [],
        }
    ouvertes_ = ouvertes(referentiel)
    non_couvertes = _exigences.sans_cas(restreindre_aux_ouvertes(referentiel), rattachements)
    ids_non_couvertes = {a["id"] for a in non_couvertes}
    # Inversion de l index : élément → entrées devient entrée → éléments.
    par_anomalie: dict[str, list[str]] = {}
    for element, liste in rattachements.items():
        for entree in liste:
            par_anomalie.setdefault(entree["id"], []).append(element)
    couvertes = [
        {"id": a["id"], "titre": a["enonce"], "elements": sorted(par_anomalie.get(a["id"], []))}
        for a in ouvertes_ if a["id"] not in ids_non_couvertes
    ]
    return {
        "declare": True,
        "titre": "Anomalies déclarées",
        "resume": (
            f"{len(ouvertes_)} anomalie(s) OUVERTE(S) déclarée(s) ({referentiel['chemin']}) : "
            f"{len(couvertes)} couverte(s) par au moins un cas dérivé, "
            f"{len(non_couvertes)} NON couverte(s)"
            + (f" · {len(referentiel['illisibles'])} ligne(s) illisible(s) au fichier, "
               f"rang(s) {', '.join(map(str, referentiel['illisibles']))} — refusée(s), jamais "
               "comptée(s) comme absentes"
               if referentiel["illisibles"] else "")
        ),
        "couvertes": couvertes,
        # `sans_cas` rend {id, enonce, palier} — on n invente pas de champ qu il ne donne pas :
        # relire l anomalie complète ici recalculerait ce qu il a déjà décidé.
        "non_couvertes": [{"id": a["id"], "titre": a["enonce"], "priorite": a["palier"]}
                          for a in non_couvertes],
        "illisibles": referentiel["illisibles"],
    }


NON_JUGE = [
    "anomalies : le rattachement est celui d `exigences` — déclaré (`elements`) ou LEXICAL. Un "
    "rattachement lexical est une PISTE, pas une preuve : qu un cas partage des mots avec une "
    "anomalie ne prouve pas qu il la couvre, et c est pourquoi la provenance est publiée",
    "anomalies : seules les anomalies OUVERTES entrent au reste-à-faire. Une anomalie fermée "
    "n a pas à être couverte — l exiger ferait grossir le reste avec tout l historique du "
    "produit, et un reste-à-faire qui grossit cesse d être lu",
    "anomalies : ce module ne va PAS chercher les anomalies dans un gestionnaire de tickets. "
    "C est le projet qui exporte sa liste — aucune API tierce, aucun secret en transit",
]
