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


@dataclass(frozen=True)
class NonTestable:
    """Un element inventorie qu AUCUNE execution ne peut atteindre FAUTE DE CONFIGURATION.

    RT-6 : distinguer « la suite ne l exerce pas » de « personne ne PEUT l exercer ici ». Le
    premier est un trou de couverture, imputable au projet. Le second est un manque
    d identifiants, de jeton ou de cle, imputable a l environnement d audit — et il se repare
    en saisissant `champs_requis`, pas en ecrivant un test. Les confondre, c est soit accuser a
    tort, soit taire un pan entier.
    """

    element: str
    champs_requis: list[str]
    pan: str = ""
    motif: str = ""


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
    # RT-6a : tout adaptateur peut en declarer ; le noyau les agrege, comme les `non_juge`.
    non_testables: list[NonTestable] = field(default_factory=list)
    # A-2 : inventaire des modules SOURCES du projet, avec l etat de chacun. Porte par
    # l adaptateur qui connait l arborescence du code ; agrege tel quel par le noyau.
    modules: list[dict] = field(default_factory=list)

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
    from forge_tests.risque import coter

    if not inventaire:
        # Un inventaire vide ne prouve pas que tout est couvert : il prouve que l adaptateur
        # n a RIEN SU ENUMERER ici. Conclure « 100 % OK » serait l absence silencieuse que le
        # framework existe pour interdire — revele par la phase 2, premier projet reel.
        return SortieAdaptateur(
            adaptateur, pan, cible, "SKIP",
            non_juge=[*non_juge, f"{pan} : inventaire VIDE — surface non enumerable sur ce projet"],
        )
    manquants = [e for e in inventaire if e.id not in exerces]
    total = len(inventaire)
    ratio = (total - len(manquants)) / total
    findings = [
        Finding(
            id=e.id,
            classe="element-non-exerce",
            localisation=e.source,
            message=f"{e.libelle} : inventorie, jamais exerce par la suite",
            risque=coter(pan, e.id, e.source),
        )
        for e in manquants
    ]
    # P1 — le plus risque d abord : sans tri, 83 findings egaux forment une liste qu on ne lit pas.
    findings.sort(key=lambda f: f.risque or 0, reverse=True)
    if total and ratio < seuil:
        findings.insert(
            0,
            Finding(
                id=f"seuil:{pan}",
                classe="seuil-non-tenu",
                localisation=cible,
                message=f"couverture de surface {ratio:.0%} sous le seuil {seuil:.0%}",
                risque=coter(pan, f"seuil:{pan}", inventaire[0].source if inventaire else cible),
            ),
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
            # RT-6b : la LISTE des elements exerces, pas seulement leur compte. Sans elle, une
            # reprise ne saurait pas quel element etait deja vert et devrait tout rejouer.
            "elements_exerces": sorted(e.id for e in inventaire if e.id in exerces),
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


POUR_COUVRIR_DEFAUT = (
    "écrire l adaptateur du pan, ou fournir au projet la convention qu il attend — voir "
    "« Contrat du projet audité » au README"
)


def rapport(
    sorties: list[SortieAdaptateur],
    pans_attendus: list[str],
    pour_couvrir: dict[str, str] | None = None,
    modules: list[dict] | None = None,
) -> dict:
    """Assemble le rapport. Un pan sans adaptateur est NOMME, jamais omis.

    A-5 : un pan non couvert ne sort plus un simple motif — il sort ce qu il FAUDRAIT pour le
    couvrir. Un motif seul est un constat ; le couple motif + chemin est une action.
    """
    from forge_tests.actions import classifier
    from forge_tests.risque import NON_JUGE as NON_JUGE_RISQUE
    from forge_tests.seuils import au_rapport as seuils_au_rapport

    verifier_regle_conjointe(sorties)
    chemins = pour_couvrir or {}
    couverts = {s.pan for s in sorties if s.verdict != "SKIP"}
    motifs_skip = {
        s.pan: s.non_juge[-1] if s.non_juge else "sans motif"
        for s in sorties
        if s.verdict == "SKIP"
    }
    non_couverts = [
        {
            "pan": p,
            "motif": motifs_skip.get(p, "adaptateur absent : aucun module ne traite ce pan"),
            "pour_couvrir": chemins.get(p, POUR_COUVRIR_DEFAUT),
        }
        for p in pans_attendus
        if p not in couverts
    ]
    # Le PAN de chaque finding est porte au rapport : sans lui, une reprise ne sait pas quels
    # findings d un rapport anterieur appartiennent a un pan qu elle ne rejoue pas (RT-6b).
    tous = sorted(
        ((f, s.pan) for s in sorties for f in s.findings),
        key=lambda couple: couple[0].risque or 0,
        reverse=True,
    )
    bandes = {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0}
    for f, _ in tous:
        bandes["non_cote" if f.risque is None else bande(f.risque)] += 1
    findings_json = [{**asdict(f), "pan": pan} for f, pan in tous]
    non_testables_json = [
        asdict(n)
        for n in sorted(
            (n for s in sorties for n in s.non_testables),
            key=lambda n: (n.pan, n.element),
        )
    ]
    return {
        "adaptateurs": [
            {"nom": s.adaptateur, "pan": s.pan, "verdict": s.verdict} for s in sorties
        ],
        "couverture_par_pan": {
            s.pan: s.surface for s in sorties if s.surface is not None
        },
        "mutation": {s.pan: s.mutation for s in sorties if s.mutation is not None},
        # A-3 : les seuils opposables, valeur ET justification, dans le rapport lui-meme.
        "seuils": seuils_au_rapport(),
        # A-2 : l inventaire des modules SOURCES — exerce, mute, ou jamais exerce et NOMME.
        "modules": modules if modules is not None else [
            m for s in sorties for m in s.modules
        ],
        "pans_non_couverts": non_couverts,
        "motifs_non_couverture": motifs_skip,
        "bandes_de_risque": bandes,
        "findings": findings_json,
        # RT-6a : ce qu aucune execution ne POUVAIT atteindre ici, et ce qu il faut fournir
        # pour que la prochaine passe le puisse. Section toujours presente, meme vide.
        "non_testables": non_testables_json,
        # Mandat 2 : la suite a donner, CLASSEE, portee par le rapport lui-meme. Le dashboard
        # ne fait que la rendre — s il la calculait, deux lecteurs du meme audit auraient deux
        # verites. Filtre MEP : `jq '.actions[] | select(.categorie=="manuelle_utilisateur")'`.
        "actions": classifier(findings_json, non_testables_json, non_couverts),
        "non_juge": sorted({n for s in sorties for n in s.non_juge} | set(NON_JUGE_RISQUE)),
        "verdict": (
            "PARTIEL"
            if non_couverts
            else ("FAIL" if any(s.verdict == "FAIL" for s in sorties) else "PASS")
        ),
    }
