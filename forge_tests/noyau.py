"""Noyau — contrat de sortie, cotation du risque, agregation, rapport.

Le noyau ne connait AUCUNE technologie : il ne sait rien de pytest, Playwright ou PostgreSQL.
Toute connaissance de stack vit dans un adaptateur. Un nom d outil de test ici est un defaut.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal

Verdict = Literal["PASS", "FAIL", "SKIP"]


@dataclass(frozen=True)
class Element:
    """Un element de surface inventorie, porteur d un identifiant stable."""

    id: str
    pan: str
    libelle: str
    source: str


@dataclass
class Finding:
    """Un defaut constate, toujours rattache a un element identifie."""

    id: str
    classe: str
    localisation: str
    message: str
    severite: str = "bloquant"
    risque: int | None = None


@dataclass
class SortieAdaptateur:
    """Contrat de sortie commun a tous les adaptateurs."""

    adaptateur: str
    pan: str
    cible: str
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)
    non_juge: list[str] = field(default_factory=list)
    surface: dict | None = None
    mutation: dict | None = None

    def json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# --- Cotation du risque (criticite x probabilite x cout de detection tardive) ------------------
BANDE_CRITIQUE = 36
BANDE_STANDARD = 12


def score_risque(criticite: int, probabilite: int, cout_tardif: int) -> int:
    for nom, valeur in (("criticite", criticite), ("probabilite", probabilite), ("cout", cout_tardif)):
        if not 1 <= valeur <= 5:
            raise ValueError(f"{nom} doit etre note de 1 a 5 (recu {valeur})")
    return criticite * probabilite * cout_tardif


def bande(score: int) -> str:
    if score >= BANDE_CRITIQUE:
        return "critique"
    if score >= BANDE_STANDARD:
        return "standard"
    return "differe"


# --- Agregation de surface --------------------------------------------------------------------
def evaluer_surface(
    adaptateur: str,
    pan: str,
    cible: str,
    inventaire: list[Element],
    exerces: set[str],
    seuil: float,
    non_juge: list[str],
) -> SortieAdaptateur:
    """Compare l inventaire au perimetre exerce. Tout element non exerce est un FAIL NOMME."""
    manquants = [e for e in inventaire if e.id not in exerces]
    total = len(inventaire)
    ratio = (total - len(manquants)) / total if total else 1.0
    findings = [
        Finding(
            id=e.id,
            classe="element-non-exerce",
            localisation=e.source,
            message=f"{e.libelle} : inventorie, jamais exerce par la suite",
        )
        for e in manquants
    ]
    if total and ratio < seuil:
        findings.append(
            Finding(
                id=f"seuil:{pan}",
                classe="seuil-non-tenu",
                localisation=cible,
                message=f"couverture de surface {ratio:.0%} sous le seuil {seuil:.0%}",
            )
        )
    return SortieAdaptateur(
        adaptateur=adaptateur,
        pan=pan,
        cible=cible,
        verdict="FAIL" if findings else "PASS",
        findings=findings,
        non_juge=non_juge,
        surface={
            "inventorie": total,
            "exerce": total - len(manquants),
            "ratio": round(ratio, 4),
            "seuil": seuil,
            "elements_non_exerces": [e.id for e in manquants],
        },
    )


# --- Regle d affichage conjoint ----------------------------------------------------------------
class RapportRefuse(RuntimeError):
    """Un score de mutation publie sans couverture de surface est un indicateur trompeur."""


def verifier_regle_conjointe(sorties: list[SortieAdaptateur]) -> None:
    """Interdit la publication d un score de mutation sans couverture de surface au rapport.

    Le score de mutation se calcule sur le SEUL perimetre atteint : publie seul, il flatte
    d autant plus que la suite est incomplete.
    """
    a_mutation = any(s.mutation is not None for s in sorties)
    a_surface = any(s.surface is not None for s in sorties)
    if a_mutation and not a_surface:
        raise RapportRefuse(
            "score de mutation present sans aucune couverture de surface : rapport refuse"
        )


def rapport(sorties: list[SortieAdaptateur], pans_attendus: list[str]) -> dict:
    """Assemble le rapport. Un pan sans adaptateur est NOMME, jamais omis."""
    verifier_regle_conjointe(sorties)
    couverts = {s.pan for s in sorties}
    non_couverts = [p for p in pans_attendus if p not in couverts]
    return {
        "adaptateurs": [
            {"nom": s.adaptateur, "pan": s.pan, "verdict": s.verdict} for s in sorties
        ],
        "couverture_par_pan": {
            s.pan: s.surface for s in sorties if s.surface is not None
        },
        "mutation": {s.pan: s.mutation for s in sorties if s.mutation is not None},
        "pans_non_couverts": non_couverts,
        "findings": [asdict(f) for s in sorties for f in s.findings],
        "non_juge": sorted({n for s in sorties for n in s.non_juge}),
        "verdict": (
            "PARTIEL"
            if non_couverts
            else ("FAIL" if any(s.verdict == "FAIL" for s in sorties) else "PASS")
        ),
    }
