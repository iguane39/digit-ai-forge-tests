"""TF-1211 — la clé `format` du document de provenance n'était pas documentée dans sa forme
légère, alors que `instance.py` l'exige (`doc.get("format")` ligne 343, `doc["format"]` ligne
386) et que la forme lourde la cite dans la même phrase du README.

Constat du 02/10/2026 : README.md ligne 1168 énumérait la forme légère `forge-tests/instance@1`
par ses champs (`commit`, `construit_le`, `images[]`) sans jamais nommer `format`, alors que
c'est la toute première clé lue par `_lire_provenance` — un document écrit avec une clé voisine
(`schema` par exemple) sort en provenance `non_determinable` sans que la documentation n'ait
prévenu de l'exigence. Correction : nommer `format` dans l'énumération. Ce fichier confronte la
phrase du README à la réalité du code, dans les deux sens.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
README = RACINE / "README.md"

# La phrase cible, ancrée sur la forme légère — motif étroit : il ne doit pas capturer la forme
# lourde (`forge-ops/empreinte@1`), citée juste avant dans la même phrase du README.
_LIGNE_FORME_LEGERE = re.compile(
    r"forme légère `forge-tests/instance@1` \(([^)]*)\)"
)


def _champs_forme_legere(texte: str) -> list[str]:
    trouve = _LIGNE_FORME_LEGERE.search(texte)
    assert trouve is not None, (
        "la phrase décrivant la forme légère `forge-tests/instance@1` a changé de forme : ce "
        "motif ne la trouve plus — l'adapter, pas le supprimer"
    )
    return [champ.strip("` ") for champ in trouve.group(1).split(",")]


def test_le_champ_format_est_nomme_dans_la_forme_legere() -> None:
    """Le défaut du 02/10 : `format` manquait à l'énumération alors que le code l'exige."""
    champs = _champs_forme_legere(README.read_text(encoding="utf-8"))
    assert "format" in champs, (
        f"la forme légère `forge-tests/instance@1` est documentée avec les champs {champs}, "
        "sans `format` — pourtant `instance.py` lit `doc.get(\"format\")` (ligne ~343) avant "
        "tout autre champ ; un document qui ne le porte pas sort en provenance "
        "non_determinable sans que la documentation n'ait prévenu de l'exigence"
    )


def test_le_verrou_ATTRAPE_la_phrase_PERIMEE_du_02_10_2026() -> None:
    """Second sens, indispensable : sans lui, ce fichier passerait vert sur la phrase fautive
    qui a motivé l'item. Phrase telle que trouvée avant correction, mot pour mot."""
    fautif = (
        "Un projet qui monte localement déclare la forme légère `forge-tests/instance@1` "
        "(`commit`, `construit_le`, `images[]`)."
    )
    champs = _champs_forme_legere(fautif)
    assert "format" not in champs, (
        "la fixture historique ne doit plus manquer `format` si elle doit encore attraper le "
        "défaut du 02/10 — la relire si PANS_ATTENDUS ou la phrase ont changé de forme"
    )
