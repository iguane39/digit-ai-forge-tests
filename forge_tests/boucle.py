"""Boucle de correction d'une campagne de tests — la définition de FIN, et son journal.

TF-0352 / TF-0353 (campagnes des 12 et 17/08/2026).

**Le trou.** Rien dans le contrat de l'étape tests ne disait qu'une campagne inclut la
CORRECTION des anomalies remontées ni le REJEU jusqu'à extinction. Conséquence mesurée :
la campagne du 12/08 se clôt CONFORME avec 121 findings et 127 actions classées — produit
inchangé. La preuve par l'inverse est du 17/08 : la même stratégie, exécutée avec obligation
de traiter, a fermé 4 anomalies produit et 3 faux verts (dont un dormant depuis le 12/08) et
divisé par six la durée de la suite e2e.

**Ce que la boucle a mesuré, tour par tour, sur une journée :**

    tour 1 : 4 anomalies
    tour 2 : 9 NOUVELLES, nées des correctifs du tour 1
    tour 3 : 1 nouvelle — une course, la classe la plus coûteuse à retrouver plus tard
    tour 4 : 0, avec trois passages verts consécutifs

Soit **69 % des anomalies qui n'existaient pas au tour 1**. Un mandat qui s'arrête au rapport
en manque 4 sur 4 ; un mandat qui s'arrête après avoir corrigé en laisse 10 sur 14 et rend une
suite rouge. Une clôture au tour 2 aurait livré la course du tour 3.

**Le second trou, celui de TF-0353 :** le ledger porte les findings du DERNIER rapport, pas
l'histoire des tours. « 0 anomalie parce que tout est traité » et « 0 anomalie parce qu'on n'a
pas rejoué après le dernier correctif » s'écrivent donc pareil. Ce module refuse la seconde.

**La définition de fin, opposable.** Une campagne est TERMINÉE quand, et seulement quand :

  a. toutes les portes sortent en exit 0 (suites, lint, typage, e2e) ;
  b. il ne reste aucun `xfail` / `test.fail` non justifié par un arbitrage humain DATÉ ;
  c. la suite est verte sur N passages consécutifs, N >= 2 ;
  d. chaque anomalie remontée est soit corrigée, soit portée en écart assumé et ÉCRIT ;
  e. (TF-0353) le dernier tour a été REJOUÉ APRÈS son dernier correctif.

Tant qu'un point manque, l'étape est `en_cours` — jamais `termine_avec_ecarts`.

**Le compteur de tours dit aussi quand s'arrêter pour de BONNES raisons** : une campagne qui
ne converge pas (tour N aussi fourni que le tour N-1) est un signal à remonter, pas un échec à
masquer. `verdict()` le publie sans jamais l'utiliser pour autoriser une clôture.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

#: Le journal d'une campagne, une ligne JSON par tour. Chez le projet audité, jamais chez la
#: forge : c'est SA campagne, et le journal doit survivre à l'audit qui l'a déclenchée.
FICHIER = "forge/journal-boucle.jsonl"

#: Les quatre portes de TF-0352 (a). Une porte absente du journal n'est pas une porte verte :
#: elle est MANQUANTE, et le dire est tout l'objet de ce module.
PORTES = ("suites", "lint", "typage", "e2e")

#: TF-0352 (c) — le minimum de passages verts consécutifs. Deux, parce qu'un seul passage vert
#: ne distingue pas une suite stable d'une suite dont l'instabilité n'est pas tombée ce coup-ci
#: (mesuré : instabilité 1 run sur 2 sur la suite e2e du 17/08).
PASSAGES_VERTS_MINIMUM = 2

EN_COURS = "en_cours"
TERMINEE = "terminee"


def _horodatage(valeur: object) -> datetime | None:
    """Un horodatage ISO, ou None — un champ illisible n'est jamais lu comme « tout va bien »."""
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except ValueError:
        return None


def lire(cible: Path | str) -> list[dict]:
    """Les tours du journal de boucle du projet, dans l'ordre. Absent = liste vide.

    Une ligne illisible n'est pas ignorée : elle entre comme tour invalide, et `verdict` la
    refuse. Un journal qu'on peut corrompre pour clore plus vite ne serait pas un contrôle.
    """
    source = Path(cible) / FICHIER
    if not source.exists():
        return []
    tours: list[dict] = []
    for rang, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            entree = json.loads(ligne)
        except json.JSONDecodeError:
            tours.append({"tour": rang, "_illisible": f"ligne {rang} : JSON invalide"})
            continue
        tours.append(entree if isinstance(entree, dict) else {"tour": rang, "_illisible": ligne})
    return tours


def _ecarts_ecrits(tour: dict) -> tuple[int, list[str]]:
    """Les écarts assumés qui sont réellement ÉCRITS — qui, quand, pourquoi.

    TF-0352 (d) : « porté en écart assumé et ÉCRIT ». Un écart anonyme ne solde rien, pour la
    raison exacte qui fait qu'une adoption invérifiable ne solde rien (RT-13).
    """
    valides, refuses = 0, []
    for rang, ecart in enumerate(tour.get("ecarts_assumes") or [], 1):
        if not isinstance(ecart, dict):
            refuses.append(f"écart {rang} : ce n'est pas un objet")
            continue
        manquants = [c for c in ("anomalie", "assume_par", "date", "motif") if not ecart.get(c)]
        if manquants:
            refuses.append(
                f"écart « {ecart.get('anomalie') or f'n°{rang}'} » : {', '.join(manquants)} "
                "manquant(s) — un écart anonyme n'assume rien"
            )
            continue
        valides += 1
    return valides, refuses


def _controler_le_dernier_tour(dernier: dict) -> list[str]:
    """Les cinq points de la définition de fin, sur le tour qui prétend clore."""
    manques: list[str] = []

    # (a) les portes
    portes = dernier.get("portes") or {}
    for porte in PORTES:
        if porte not in portes:
            manques.append(
                f"porte « {porte} » ABSENTE du journal — une porte qu'on ne joue pas n'est pas "
                "une porte verte (a)"
            )
        elif int(portes[porte] or 0) != 0:
            manques.append(f"porte « {porte} » en exit {portes[porte]}, attendu 0 (a)")

    # (b) les xfail non justifiés
    non_justifies = int(dernier.get("xfail_non_justifies") or 0)
    if non_justifies:
        manques.append(
            f"{non_justifies} xfail/test.fail sans arbitrage humain daté (b) — un test désarmé "
            "sans décision est une anomalie masquée, pas un écart assumé"
        )

    # (c) les passages verts consécutifs
    passages = int(dernier.get("passages_verts_consecutifs") or 0)
    if passages < PASSAGES_VERTS_MINIMUM:
        manques.append(
            f"{passages} passage(s) vert(s) consécutif(s), {PASSAGES_VERTS_MINIMUM} exigés (c) — "
            "un passage unique ne distingue pas une suite stable d'une instabilité non tombée"
        )

    # (d) les anomalies restantes, corrigées ou assumées PAR ÉCRIT
    restantes = int(dernier.get("restantes") or 0)
    assumes, refuses = _ecarts_ecrits(dernier)
    manques.extend(refuses)
    if restantes > assumes:
        manques.append(
            f"{restantes} anomalie(s) restante(s) pour {assumes} écart(s) assumé(s) et écrit(s) "
            "(d) — le solde est une anomalie que personne n'a ni corrigée ni assumée"
        )

    # (e) le rejeu APRÈS le dernier correctif — TF-0353
    correctif = _horodatage(dernier.get("dernier_correctif"))
    rejeu = _horodatage(dernier.get("dernier_run_suite"))
    if correctif is None and (dernier.get("corrigees") or 0):
        manques.append(
            "`dernier_correctif` absent ou illisible alors que ce tour a corrigé (e) — sans lui, "
            "« rejoué après » n'est pas vérifiable"
        )
    elif rejeu is None:
        manques.append("`dernier_run_suite` absent ou illisible (e) — rien ne prouve un rejeu")
    elif correctif is not None and rejeu <= correctif:
        manques.append(
            f"dernier rejeu ({rejeu.isoformat()}) ANTÉRIEUR au dernier correctif "
            f"({correctif.isoformat()}) (e) — « 0 anomalie » ne dit alors rien d'autre que "
            "« on n'a pas rejoué » : c'est exactement la clôture que TF-0353 interdit"
        )
    return manques


def convergence(tours: list[dict]) -> dict:
    """Le signal de non-convergence — publié, jamais utilisé pour autoriser une clôture.

    Une campagne dont le tour N révèle autant de nouvelles anomalies que le tour N-1 ne
    converge pas : elle est à remonter comme telle. La masquer en clôturant serait la même
    faute que celle du 12/08, un cran plus loin.
    """
    revelees = [int(t.get("nouvelles") or 0) for t in tours]
    converge = len(revelees) < 2 or revelees[-1] < revelees[-2] or revelees[-1] == 0
    return {
        "tours": len(tours),
        "revelees_par_tour": revelees,
        "nees_des_correctifs": sum(revelees[1:]),
        "converge": converge,
        "signal": (
            ""
            if converge
            else (
                f"NON CONVERGENTE : le tour {len(tours)} révèle {revelees[-1]} anomalie(s) "
                f"contre {revelees[-2]} au tour précédent — à remonter, pas à masquer"
            )
        ),
    }


def verdict(tours: list[dict]) -> dict:
    """L'étape tests est-elle TERMINÉE ? Cinq points, et le silence n'en vaut aucun.

    Retour : `statut` (`en_cours` / `terminee`), `manques` (nommés, jamais un total anonyme),
    `convergence` et `libelle` — la phrase publiée telle quelle par les appelants, pour que
    deux lecteurs de la même campagne n'aient pas deux vérités.
    """
    if not tours:
        return {
            "statut": EN_COURS,
            "manques": [
                "aucun tour au journal de boucle — une campagne sans journal ne peut pas "
                f"prouver son rejeu (TF-0353). Journal attendu : `{FICHIER}`"
            ],
            "convergence": convergence([]),
            "libelle": (
                "étape tests EN COURS : aucun journal de boucle — « 0 anomalie » et « pas "
                "rejoué » s'écrivent pareil tant que les tours ne sont pas tracés"
            ),
        }

    manques = [t["_illisible"] for t in tours if t.get("_illisible")]
    manques += _controler_le_dernier_tour(tours[-1])
    mesure = convergence(tours)

    if manques:
        return {
            "statut": EN_COURS,
            "manques": manques,
            "convergence": mesure,
            "libelle": (
                f"étape tests EN COURS après {len(tours)} tour(s) : {len(manques)} point(s) de "
                "la définition de fin non tenus — " + " ; ".join(manques)
            ),
        }
    rappel = f" · {mesure['signal']}" if mesure["signal"] else ""
    return {
        "statut": TERMINEE,
        "manques": [],
        "convergence": mesure,
        "libelle": (
            f"étape tests TERMINÉE en {len(tours)} tour(s) : portes à 0, aucun xfail non "
            f"justifié, {tours[-1].get('passages_verts_consecutifs')} passages verts "
            "consécutifs, aucune anomalie ni non corrigée ni non assumée, dernier rejeu "
            f"postérieur au dernier correctif{rappel}"
        ),
    }
