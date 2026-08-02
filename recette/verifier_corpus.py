"""Recette de la phase 1 — critère de sortie S-01, vérifié PAR EXÉCUTION.

Rejoue le framework sur la paire de bancs et vérifie, défaut par défaut :
  - sur le banc ROUGE : chaque défaut du corpus produit au moins un finding NOMMÉ ;
  - sur le banc VERT  : aucun finding, quel qu il soit.

Un défaut détecté « globalement » ne compte pas : la détection doit porter sur des éléments
identifiés, sinon on retombe sur l absence silencieuse que le framework existe pour supprimer.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_tests.__main__ import analyser  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
ROUGE = RACINE / "fixtures" / "banc-rouge"
VERT = RACINE / "fixtures" / "banc-vert"

# Chaque défaut du corpus, et le préfixe d identifiant qui prouve sa détection.
CORPUS = [
    ("D-01", "front", "parcours Front tronqué", ("route:", "element:")),
    ("H-02", "api", "codes d erreur jamais exercés", ("code:",)),
    ("H-03", "api", "méthodes HTTP jamais atteintes", ("endpoint:",)),
    ("H-04", "data", "contraintes jamais violées", ("contrainte:",)),
    ("H-05", "migrations", "migrations ni inversées ni rejouées", ("migration:",)),
    ("H-06", "batch", "branches de rejet et reprise non parcourues", ("branche:", "rejet:")),
    ("H-07", "fichiers", "variantes de format non soumises", ("variante:",)),
    ("H-08", "back", "assertions permissives", ("mutant:", "seuil:back")),
]


def _findings(rapport: dict, prefixes: tuple[str, ...]) -> list[dict]:
    return [f for f in rapport["findings"] if f["id"].startswith(prefixes)]


def main() -> int:
    rouge = analyser(ROUGE)
    vert = analyser(VERT)

    print("=" * 78)
    print("RECETTE PHASE 1 — critère de sortie S-01")
    print("=" * 78)

    detectes = 0
    for code, pan, libelle, prefixes in CORPUS:
        trouves = _findings(rouge, prefixes)
        ok = bool(trouves)
        detectes += ok
        marque = "DETECTE" if ok else "MANQUE "
        print(f"  [{marque}] {code} ({pan:<10}) {libelle}")
        for f in trouves[:2]:
            print(f"             -> {f['id']}")
        if len(trouves) > 2:
            print(f"             -> ... et {len(trouves) - 2} autre(s) élément(s) nommé(s)")

    print("-" * 78)
    print(f"  banc ROUGE : {detectes}/8 défauts détectés · {len(rouge['findings'])} findings nommés")
    print(f"  banc VERT  : {len(vert['findings'])} finding(s) — attendu 0")
    print(f"  verdicts   : rouge={rouge['verdict']} · vert={vert['verdict']}")

    succes = detectes == 8 and not vert["findings"]
    print("=" * 78)
    print("  S-01 TENU" if succes else "  S-01 NON TENU")
    return 0 if succes else 1


if __name__ == "__main__":
    sys.exit(main())
