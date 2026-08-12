"""Détection de tests INSTABLES (flaky) — TF-0104, sous-item 2/4.

Aucun rejeu multiple n existait pour isoler la non-déterminisme : un test flaky change de
verdict d une exécution à l autre sans qu aucun mutant n y soit pour rien, et fausse en
silence le score de mutation (un mutant peut sembler « tué » ou « survivant » selon le hasard
du rejeu, pas selon ce qu il a réellement changé). Ce module rejoue une commande plusieurs fois
et relève les tests dont le VERDICT a varié entre deux rejeux à code source IDENTIQUE.

Loi de ce module : il **détecte et déclare**, il ne décide jamais tout seul d exclure un test
du calcul de mutation — l exclusion reste un choix explicite de l appelant, journalisé.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

NON_JUGE = [
    "flaky : la detection repose sur la lecture des lignes de verdict par test dans la sortie "
    "de la commande rejouee (motif `id::test VERDICT` ou `VERDICT id::test`) — un harnais qui "
    "n imprime pas ce format par test n est pas mesurable ici",
    "flaky : deux rejeux identiques ne prouvent pas l ABSENCE de non-determinisme, seulement "
    "qu il ne s est pas manifeste sur cet echantillon de repetitions",
]

_VERDICTS = ("PASSED", "FAILED", "ERROR", "SKIPPED")
_APRES = re.compile(
    r"^(?P<id>\S+::\S+)\s+(?:" + "|".join(_VERDICTS) + r")\b", re.MULTILINE
)
_AVANT = re.compile(
    r"^(?:" + "|".join(_VERDICTS) + r")\s+(?P<id>\S+::\S+)", re.MULTILINE
)


def resultats_par_test(sortie: str) -> dict[str, str]:
    """Verdict par identifiant de test, lu dans une sortie de suite (pytest `-rA`, JUnit texte…).

    Les deux ORDRES d écriture existent selon l outil (« id VERDICT » ou « VERDICT id ») : les
    deux motifs sont essayés, sans supposer lequel le harnais du projet utilise.
    """
    releves: dict[str, str] = {}
    for ligne in sortie.splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        m = _APRES.match(ligne)
        if m:
            for verdict in _VERDICTS:
                if verdict in ligne:
                    releves[m.group("id")] = verdict
                    break
            continue
        m = _AVANT.match(ligne)
        if m:
            for verdict in _VERDICTS:
                if ligne.startswith(verdict):
                    releves[m.group("id")] = verdict
                    break
    return releves


def rejouer(
    commande: list[str], cwd: Path, repetitions: int = 3, **kwargs: object
) -> dict:
    """Relance `commande` `repetitions` fois et relève les tests dont le verdict a VARIÉ.

    Retour : `{"repetitions", "tests_instables": {id: [verdicts...]}, "tous_ids": [...]}`.
    `tests_instables` est vide si rien n a varié — jamais l absence de la clé, pour que
    l appelant n ait pas à distinguer « non mesuré » de « rien trouvé ».
    """
    if repetitions < 2:
        raise ValueError("la detection de flaky exige au moins 2 repetitions")
    releves: list[dict[str, str]] = []
    for _ in range(repetitions):
        resultat = subprocess.run(
            commande,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        releves.append(resultats_par_test((resultat.stdout or "") + "\n" + (resultat.stderr or "")))
    tous_ids: set[str] = set()
    for releve in releves:
        tous_ids |= set(releve)
    instables = {
        identifiant: [releve.get(identifiant, "absent") for releve in releves]
        for identifiant in sorted(tous_ids)
        if len({releve.get(identifiant, "absent") for releve in releves}) > 1
    }
    return {
        "repetitions": repetitions,
        "tests_instables": instables,
        "tous_ids": sorted(tous_ids),
    }
