"""Recette du générateur (P4) — mesure sa PRÉCISION, pas son volume.

Un cas généré qui échoue sur du code CORRECT n est pas une découverte : c est un défaut du
générateur. Sur un projet réel il n existe pas de jumeau sain, donc cette mesure ne peut se
faire qu ici — et c est précisément à quoi sert la paire de fixtures.

    précision = cas qui échouent sur le banc ROUGE ET passent sur le banc VERT
                --------------------------------------------------------------
                                    cas générés

Un cas qui échoue des deux côtés est un faux positif. Le publier comme un défaut du projet
inviterait à assouplir l assertion pour le faire passer — exactement le test-fitting que le
garde-fou G-2 interdit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Le garde-fou que `verifier_corpus.py` posait et que celui-ci avait oublie. Sans lui, les pans
# `accessibilite` et `visuel` visent l instance SERVIE decrite par le `.env` de l operateur —
# et, plus grave que de fausser la mesure, ils ECRIVENT le DOM de cette instance etrangere dans
# `fixtures/banc-*/.visuel/`. Constate le 2026-08-06 : lancer cette recette remplacait les
# captures des bancs par celles d un projet client, sans que rien ne le dise. Un outil qui
# pollue ses propres bancs de reference perd la seule chose qui rend ses verdicts comparables.
os.environ["FORGE_TESTS_BASE_URL"] = ""

from forge_tests.__main__ import analyser  # noqa: E402
from forge_tests.execution import schema_openapi  # noqa: E402
from forge_tests.generateur import ecrire  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
ROUGE = RACINE / "fixtures" / "banc-rouge"
VERT = RACINE / "fixtures" / "banc-vert"
PROPOSITIONS = RACINE / "propositions"
_ECHEC = re.compile(r"^FAILED \S+::(\S+)", re.MULTILINE)


def _python(banc: Path) -> Path:
    for candidat in (
        banc / "backend" / ".venv" / "Scripts" / "python.exe",
        banc / "backend" / ".venv" / "bin" / "python",
    ):
        if candidat.exists():
            return candidat
    raise RuntimeError(f"environnement absent pour {banc}")


def _collectable(banc: Path, fichier: Path) -> tuple[bool, str]:
    """TF-0143 — oracle « collectable », seconde moitie : `pytest --collect-only` REUSSIT
    reellement sur ce banc (imports resolus, fixtures presentes), pas seulement « compile ».

    Sans ce controle, une erreur de COLLECTE (import cassé, fixture absente) ne remonte nulle
    part : `_echecs` ne reconnait que les lignes `FAILED ...` du texte pytest, et une erreur de
    collecte s imprime en `ERROR ...` — un defaut du generateur qui ne ferait ni echouer ni
    reussir la mesure de precision, silencieusement absent des deux compteurs.
    """
    destination = banc / "backend" / "tests" / fichier.name
    shutil.copy(fichier, destination)
    try:
        resultat = subprocess.run(
            [
                str(_python(banc)), "-m", "pytest", "--collect-only", "-q",
                f"tests/{fichier.name}", "-p", "no:cacheprovider", "-p", "no:warnings",
            ],
            cwd=banc / "backend", capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        return resultat.returncode == 0, (resultat.stdout + resultat.stderr)[-1500:]
    finally:
        destination.unlink(missing_ok=True)


def _echecs(banc: Path, fichier: Path) -> set[str]:
    """Noms des cas en échec quand le fichier généré est exécuté sur ce banc."""
    destination = banc / "backend" / "tests" / fichier.name
    shutil.copy(fichier, destination)
    try:
        resultat = subprocess.run(
            [
                str(_python(banc)), "-m", "pytest", f"tests/{fichier.name}",
                "-q", "--no-header", "-p", "no:warnings", "-p", "no:cacheprovider",
            ],
            cwd=banc / "backend", capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace",
        )
        return set(_ECHEC.findall(resultat.stdout))
    finally:
        destination.unlink(missing_ok=True)


def main() -> int:
    rapport = analyser(ROUGE)
    genere = ecrire(rapport, PROPOSITIONS, schema=schema_openapi(str(ROUGE)))
    if genere is None:
        print("aucun cas genere")
        return 1

    total = len(re.findall(r"^def (test_genere_\w+)", genere.read_text(encoding="utf-8"), re.M))

    # TF-0143 — un cas genere n est un cas que s il COLLECTE reellement sous pytest. Verifie sur
    # les DEUX bancs : le fichier est le meme, l environnement (deps, app) doit le rendre
    # collectable partout ou il est depose, pas seulement la ou la mesure de precision passe.
    for banc, nom in ((ROUGE, "ROUGE"), (VERT, "VERT")):
        collectable, sortie = _collectable(banc, genere)
        print(f"  collectable (pytest --collect-only) sur banc {nom:<5} : "
              f"{'OUI' if collectable else 'NON'}")
        if not collectable:
            print(sortie)
            print("=" * 78)
            print("  NON COLLECTABLE : le fichier genere ne passe pas la collecte pytest — "
                  "defaut du generateur, mesure de precision non poursuivie")
            return 1

    echecs_rouge = _echecs(ROUGE, genere)
    echecs_vert = _echecs(VERT, genere)

    vrais = echecs_rouge - echecs_vert
    faux = echecs_vert
    # Precision = part des ACCUSATIONS qui sont justes. Sans accusation, elle est INDEFINIE :
    # la noter 0 % confondrait « accuse a tort » et « n accuse pas ». Deux etats opposes.
    precision = (len(vrais) / len(echecs_rouge)) if echecs_rouge else None

    print("=" * 78)
    print("RECETTE DU GENERATEUR — precision")
    print("=" * 78)
    print(f"  cas generes                      : {total}")
    print(f"  echouent sur le banc ROUGE       : {len(echecs_rouge)}")
    print(f"  echouent AUSSI sur le banc VERT  : {len(faux)}  <- defauts du generateur")
    print(f"  vrais positifs (rouge seulement) : {len(vrais)}")
    lisible = "indefinie (aucune accusation)" if precision is None else f"{precision:.0%}"
    print(f"  precision                        : {lisible}")
    refuses = json.loads((PROPOSITIONS / "non-generables.json").read_text(encoding="utf-8"))
    print(f"  elements DECLARES non generables : {len(refuses)}")
    print("  -> rappel : aucun cas ne peut cibler ces elements, par construction")
    if vrais:
        print("  defauts reellement attrapes :")
        for nom in sorted(vrais):
            print(f"    - {nom}")
    print("=" * 78)
    sur = not faux
    print("  SUR (aucun faux positif)" if sur else "  NON SUR : il accuse a tort")
    print(f"  UTILE : {len(vrais)} defaut(s) reel(s) attrape(s) — rappel nul sur ce banc"
          if not vrais else f"  UTILE : {len(vrais)} defaut(s) reel(s) attrape(s)")
    return 0 if sur else 1


if __name__ == "__main__":
    sys.exit(main())
