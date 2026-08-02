"""Adaptateur Migrations — chaque migration doit être exercée à l ALLER, au RETOUR et en REJEU."""

from __future__ import annotations

from pathlib import Path

import re

from forge_tests.execution import instructions_sql, schema_obtenu
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
    "migrations : l effet verifie est l EXISTENCE des objets nommes (tables, contraintes, "
    "index) apres application ; ni leur definition exacte, ni les donnees migrees",
    "migrations : le rejeu est déduit d une seconde exécution de TOUTES les instructions de "
    "la section ; deux migrations rigoureusement identiques resteraient indiscernables",
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


def _instructions(section: str) -> list[str]:
    """Instructions normalisées d une section de migration, comparables au relevé du moteur."""
    brutes = [" ".join(s.split()) for s in section.split(";")]
    return [s for s in brutes if s and not s.startswith("--")]


def exerces(cible: Path) -> set[str] | None:
    """Sens exercés : les instructions de la section ont-elles ÉTÉ ENVOYÉES au moteur ?

    Écart avec le recoupement textuel : un test qui nomme « retour » sans jamais appliquer la
    section de retour ne couvre plus rien. C est le fait d exécution qui compte, pas le mot.
    """
    executees_ = instructions_sql(cible)
    if executees_ is None:
        return None
    vues = [" ".join(s.split()) for s in executees_]

    def comptees(instructions: list[str]) -> int:
        """Nombre de fois ou la section ENTIERE a ete envoyee.

        Se fier a la premiere instruction confondait deux migrations qui commencent pareil.
        On exige desormais que TOUTES les instructions de la section aient ete vues, et on
        compte les passages par la moins frequente d entre elles.
        """
        if not instructions:
            return 0
        passages = []
        for instruction in instructions:
            reference = instruction[:200]
            passages.append(sum(1 for vue in vues if reference and reference in vue))
        return min(passages)

    couvert: set[str] = set()
    for fichier in _fichiers(cible):
        haut, bas = _sections(fichier)
        occurrences_aller = comptees(_instructions(haut))
        if occurrences_aller >= 1:
            couvert.add(f"migration:{fichier.stem}:aller")
        if occurrences_aller >= 2:
            couvert.add(f"migration:{fichier.stem}:rejeu")
        if comptees(_instructions(bas)) >= 1:
            couvert.add(f"migration:{fichier.stem}:retour")
    return couvert


def _sections(fichier: Path) -> tuple[str, str]:
    texte = fichier.read_text(encoding="utf-8")
    haut, _, bas = texte.partition("-- +migrate Down")
    return haut.replace("-- +migrate Up", ""), bas


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
    # Effet REEL : un objet qu une section pretend creer doit exister apres application.
    schema = schema_obtenu(str(cible))
    if schema is None:
        sortie.non_juge.append("migrations : schema reel non introspectable, effet non verifie")
        return sortie
    presents = set(schema["tables"]) | set(schema["contraintes"]) | set(schema["index"])
    for fichier in _fichiers(cible):
        haut = _sections(fichier)[0]
        # `DROP CONSTRAINT x` n ANNONCE pas x, il le retire : le compter serait accuser la
        # migration qui defait au lieu de celle qui promet.
        annonces = set(re.findall(r"(?<!DROP )CONSTRAINT (\w+)", haut, re.IGNORECASE))
        annonces |= set(re.findall(r"CREATE (?:UNIQUE )?INDEX (\w+)", haut, re.IGNORECASE))
        annonces |= set(re.findall(r"CREATE TABLE (\w+)", haut, re.IGNORECASE))
        for nom in sorted(annonces - presents):
            sortie.findings.append(
                Finding(
                    id=f"divergence:migration:{fichier.stem}:{nom}",
                    classe="divergence",
                    localisation=str(fichier),
                    message=(
                        f"{nom} annonce par la migration mais absent du schema obtenu : "
                        "l instruction s execute sans produire son objet"
                    ),
                    risque=coter(PAN, f"migration:{nom}", str(fichier)),
                )
            )
            sortie.verdict = "FAIL"
    return sortie
