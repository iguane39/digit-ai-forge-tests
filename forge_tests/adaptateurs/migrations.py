"""Adaptateur Migrations — chaque migration doit être exercée à l ALLER, au RETOUR et en REJEU."""

from __future__ import annotations

from pathlib import Path

from forge_tests.execution import executees
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
    "migrations : un sens est exercé si une ligne de test RÉELLEMENT EXÉCUTÉE le nomme ; "
    "l oracle ne vérifie pas que la migration a été appliquée dans ce sens, seulement que le "
    "code qui la nomme a tourné",
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


def exerces(cible: Path) -> set[str] | None:
    """Sens exercés : seules comptent les lignes de test qui ont REELLEMENT tourné.

    Un test mort, sauté ou jamais collecté ne couvre plus rien — c est tout l écart avec le
    recoupement textuel, qui comptait la simple présence du mot dans un fichier.
    """
    fichiers = sorted((cible / "backend" / "tests").glob("test_*.py"))
    lignes_vues: list[str] = []
    for fichier in fichiers:
        executees_ = executees(cible, fichier.name)
        if executees_ is None:
            return None
        source = fichier.read_text(encoding="utf-8").splitlines()
        lignes_vues.extend(
            source[i - 1].lower() for i in sorted(executees_) if 0 < i <= len(source)
        )
    texte = " ".join(lignes_vues)
    sens_couverts = {s for s in SENS if any(mot in texte for mot in _MOTS[s])}
    return {e.id for e in inventaire(cible) if e.id.rsplit(":", 1)[1] in sens_couverts}


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, "couverture d exécution indisponible : suite rouge ou env absent"],
        )
    sortie = evaluer_surface(
        NOM, PAN, str(cible), inventaire(cible), couvert, SEUIL, list(NON_JUGE)
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
