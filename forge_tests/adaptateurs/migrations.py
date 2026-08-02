"""Adaptateur Migrations — chaque migration doit être exercée à l ALLER, au RETOUR et en REJEU."""

from __future__ import annotations

from pathlib import Path

from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "migrations-sql", "migrations", 1.0
SENS = ("aller", "retour", "rejeu")
_MOTS = {
    "aller": ("aller", "up", "upgrade"),
    "retour": ("retour", "down", "downgrade"),
    "rejeu": ("rejeu", "replay", "rejouer"),
}

NON_JUGE = [
    "migrations : un sens est réputé exercé si un test le nomme ; l oracle ne vérifie pas que "
    "la migration a réellement été appliquée dans ce sens",
]


def _fichiers(cible: Path) -> list[Path]:
    return sorted((cible / "backend" / "migrations").glob("*.sql"))


def inventaire(cible: Path) -> list[Element]:
    return [
        Element(
            f"migration:{fichier.stem}:{sens}",
            PAN,
            f"migration {fichier.stem} au {sens}",
            str(fichier),
        )
        for fichier in _fichiers(cible)
        for sens in SENS
    ]


def exerces(cible: Path) -> set[str]:
    textes = " ".join(
        f.read_text(encoding="utf-8").lower()
        for f in sorted((cible / "backend" / "tests").glob("test_*.py"))
    )
    sens_couverts = {s for s in SENS if any(mot in textes for mot in _MOTS[s])}
    return {
        e.id for e in inventaire(cible) if e.id.rsplit(":", 1)[1] in sens_couverts
    }


def analyser(cible: Path) -> SortieAdaptateur:
    sortie = evaluer_surface(
        NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, list(NON_JUGE)
    )
    # Une migration sans section de retour est une DIVERGENCE de la source, pas un trou de suite.
    for fichier in _fichiers(cible):
        if "-- +migrate Down" not in fichier.read_text(encoding="utf-8"):
            sortie.findings.append(
                Finding(
                    id=f"migration:{fichier.stem}:retour",
                    classe="divergence",
                    localisation=str(fichier),
                    message="migration sans section de retour : elle ne peut pas être inversée",
                    risque=coter(PAN, "migration:retour", str(fichier)),
                )
            )
            sortie.verdict = "FAIL"
    return sortie
