"""Noyau — contrat de sortie, cotation du risque, agregation, rapport.

Le noyau ne connait AUCUNE technologie : il ne sait rien de pytest, Playwright ou PostgreSQL.
Toute connaissance de stack vit dans un adaptateur. Un nom d outil de test ici est un defaut.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from forge_tests import classes

# « NA » (sans objet) — décision humaine du 14/08 : « les pans qui n'ont pas de périmètre dans
# un projet doivent ressortir en Non Applicable lors des tests, puisqu'il n'y a rien à tester ».
#
# NA n'est PAS un synonyme de SKIP, et la distinction est tout l'intérêt :
#   - SKIP  = il y a quelque chose à mesurer et je n'ai PAS PU (configuration absente, suite non
#             exécutée, précondition non établie). C'est un manque, il compte, il rend PARTIEL ;
#   - NA    = il n'y a RIEN à mesurer ici, et je le PROUVE (le projet n'a pas de migrations, pas
#             de front, pas de prompt). Ce n'est pas un manque : ne pas avoir de traitement par
#             lot n'est pas un défaut.
#
# Garde-fou hérité, non négociable : un inventaire vide ne suffit PAS à conclure NA. Le
# framework tient depuis l'origine qu'« un inventaire vide ne prouve pas que tout est couvert :
# il prouve que l'adaptateur n'a RIEN SU ÉNUMÉRER ici ». NA exige donc une preuve POSITIVE
# d'absence, fournie par l'adaptateur (`sans_objet=` d'`evaluer_surface`) : il a cherché aux
# endroits qu'il déclare, et ces endroits n'existent pas. Sans cette preuve, on reste en SKIP.
Verdict = Literal["PASS", "FAIL", "SKIP", "NA"]
# TF-0146 — verdict d un ESSAI individuel (un cas exécuté), distinct du Verdict d ADAPTATEUR
# ci-dessus (un pan entier). Trois valeurs, jamais un vert par défaut : un cas dont l issue
# n a pas été observée est NON_EXECUTE, jamais tacitement PASSANT.
VerdictEssai = Literal["passant", "non_passant", "non_execute"]


@dataclass(frozen=True)
class Element:
    """Un element de surface inventorie, porteur d un identifiant stable."""

    id: str
    pan: str
    libelle: str
    source: str
    #: TF-0380 (lot SCC_ALX 20260818b) — `produit` (le projet le fabrique et le modifie) ou
    #: `entrant` (une donnee recue, que le projet ne produit ni ne modifie jamais). Laissee VIDE,
    #: elle est deduite du chemin par `provenance_de` au moment de l evaluation : aucun adaptateur
    #: n a a connaitre le mecanisme, et un adaptateur futur en herite sans une ligne (meme
    #: principe que `qualifier`). Un adaptateur qui sait mieux la pose explicitement.
    provenance: str = ""


#: Familles d ENTRANTS de la convention pilot : « tout entrant est une DONNEE ». Un element
#: inventorie sous l une d elles n est pas de la surface du produit — le projet ne l a pas ecrit
#: et n a aucun moyen de le corriger.
#:
#: LE FAIT (TF-0380) : sur un audit reel, le SEUL pan couvert affichait « interface 15/15,
#: ratio 1,0, PASS » — et ses 15 elements etaient les 15 ancres de deux fichiers `input/*.html`,
#: des documents RECUS du client. Au meme commit, les trois livrables HTML de `output/` portaient
#: 27 ancres, dont aucune n etait inventoriee (`output/` est exclu depuis RT-9/RT-10, a juste
#: titre : auditer ses propres artefacts est un auto-audit). Le seul PASS de l audit portait donc
#: sur ce que le projet ne produit pas. Un ratio de 1,0 sur des entrants est PLUS TROMPEUR qu un
#: pan franchement non couvert : le second se voit, le premier se lit comme une reussite.
FAMILLES_ENTRANTES = ("input",)


def provenance_de(source: str | Path) -> str:
    """`entrant` si le chemin traverse une famille d entrants declaree, `produit` sinon.

    Deduite du CHEMIN et non d une liste tenue a la main : une famille ajoutee a la convention
    profite a tous les pans sans qu un adaptateur change. Le sens de l erreur est voulu — ce qui
    n est pas reconnu comme entrant reste `produit`, donc COMPTE dans la couverture : mieux vaut
    exiger a tort la couverture d un fichier recu que de dispenser a tort celle d un livrable.
    """
    parties = {p.lower() for p in Path(str(source)).parts}
    return "entrant" if parties & {f.lower() for f in FAMILLES_ENTRANTES} else "produit"


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
    #: TF-0381 (lot SCC_ALX 20260818b) — `element` nomme-t-il un élément INVENTORIÉ, ou est-il le
    #: marque-place d un pan dont rien n est énumérable ? Nommer le pan reste juste (loi 3 : un
    #: silence ressemblerait à « rien à tester ici »), mais l APPELER un élément inventorié est
    #: faux, et c est ce que l action générée disait : « 1 élément(s) sont inventoriés » sur un
    #: pan dont le motif, deux champs plus haut, annonçait « 0 elements INVENTORIES ».
    inventorie: bool = True
    #: `constate` (le projet ou une trace d exécution a nommé le champ) ou `presume` (déduit d un
    #: `.env.example` que personne ne revendique). Un champ présumé pour un pan sans élément ne
    #: mène nulle part : c est la combinaison que TF-0381 a payée, dix actions manuelles pour dix
    #: pans, toutes réclamant six variables Databricks sur un projet d ANALYSE.
    provenance: str = "constate"


@dataclass(frozen=True)
class Essai:
    """TF-0146 — UN cas exécuté (ou non), avec son verdict et son POURQUOI.

    Le noyau ne sait toujours rien de la technologie qui l a produit (pytest, Playwright...) :
    un `Essai` est une ligne neutre, comme `Finding`. Ce que sait la technologie (nom du test,
    trace de l échec, message de skip) vit dans l adaptateur ou la sonde qui construit la liste
    — voir `forge_tests.sondes.junit` pour un exemple qui lit du JUnit XML réel.
    """

    id: str
    pan: str
    verdict: VerdictEssai
    pourquoi: str | None = None
    details: str | None = None
    # None = inconnu (aucun signal disponible) ; False = un « passant » explicitement NON
    # adossé à une mesure (mutation nulle sur ce module, ou aucune ligne couverte) — c est ce
    # deuxième cas que « aucun ✓ sans oracle » existe pour rendre visible, jamais silencieux.
    couvert: bool | None = None


class EssaiSansMotif(RuntimeError):
    """TF-0146 — un essai NON PASSANT ou NON EXÉCUTÉ sans `pourquoi`.

    Un verdict qui ne se motive pas n est pas un verdict exploitable — c est un silence qui
    porte un vernis de mesure. Refusé avant toute agrégation, comme `RapportRefuse` pour la
    règle conjointe.
    """


def resume_essais(essais: list[Essai]) -> dict[str, object]:
    """Agrège une liste d essais en la section `essais` du rapport.

    Oracle « aucun ✓ sans oracle » : un essai PASSANT dont `couvert is False` est un vert que
    rien ne soutient (mutation nulle, ligne jamais exécutée sous mesure) — il rejoint
    `signales`, visible, jamais fondu dans le total des passants sans distinction.
    """
    manques = [
        e.id for e in essais if e.verdict != "passant" and not (e.pourquoi or "").strip()
    ]
    if manques:
        raise EssaiSansMotif(
            "essai(s) sans POURQUOI motivé, non PASSANT : " + ", ".join(sorted(manques))
        )
    totaux = {"passant": 0, "non_passant": 0, "non_execute": 0}
    for e in essais:
        totaux[e.verdict] += 1
    signales = [
        {
            "id": e.id,
            "pan": e.pan,
            "motif": "vert non couvert par la mutation ni par la couverture — aucun ✓ sans "
            "oracle",
        }
        for e in essais
        if e.verdict == "passant" and e.couvert is False
    ]
    return {
        "cas": [
            {
                "id": e.id,
                "pan": e.pan,
                "verdict": e.verdict,
                "pourquoi": e.pourquoi,
                "details": e.details,
                "couvert": e.couvert,
            }
            for e in sorted(essais, key=lambda e: (e.pan, e.id))
        ],
        "totaux": totaux,
        "signales": signales,
        "fourni": True,
    }


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
    notes = (("criticite", criticite), ("probabilite", probabilite), ("cout", cout_tardif))
    for nom, valeur in notes:
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
    sans_objet: str | None = None,
) -> SortieAdaptateur:
    """Compare l inventaire au perimetre exerce. Tout element non exerce est un FAIL NOMME.

    `sans_objet` (14/08) : PREUVE POSITIVE que le projet n a pas ce perimetre — « aucun dossier
    `frontend\\`, aucun fichier de migration ». Fournie, et l inventaire etant vide, le pan sort
    **NA** : il n y a rien a tester, ce n est pas un manque. Absente, l inventaire vide reste un
    SKIP : l adaptateur n a rien su enumerer, et c est autre chose.
    """
    from forge_tests.risque import coter

    if not inventaire:
        if sans_objet:
            # Sans objet, et PROUVE : le pan a cherche aux endroits qu il declare, ils n existent
            # pas. Ne pas avoir de traitement par lot n est pas un defaut de traitement par lot.
            return SortieAdaptateur(
                adaptateur, pan, cible, "NA",
                non_juge=[*non_juge, f"{pan} : SANS OBJET sur ce projet — {sans_objet}"],
            )
        # Un inventaire vide ne prouve pas que tout est couvert : il prouve que l adaptateur
        # n a RIEN SU ENUMERER ici. Conclure « 100 % OK » serait l absence silencieuse que le
        # framework existe pour interdire — revele par la phase 2, premier projet reel.
        return SortieAdaptateur(
            adaptateur, pan, cible, "SKIP",
            non_juge=[*non_juge, f"{pan} : inventaire VIDE — surface non enumerable sur ce projet"],
        )
    # TF-0380 — la couverture se mesure sur ce que le projet PRODUIT. Les entrants restent
    # inventories et NOMMES (les taire ferait disparaitre ce qui a ete lu), mais ils ne comptent
    # ni au numerateur ni au denominateur : exiger d un projet qu il teste un document recu du
    # client est un reproche qu il ne peut pas honorer, et le compter comme couvert est pire —
    # c est le « ratio 1,0 » qui a fait passer un audit pour vert.
    def _provenance(e: Element) -> str:
        return e.provenance or provenance_de(e.source)

    entrants = [e for e in inventaire if _provenance(e) == "entrant"]
    produits = [e for e in inventaire if _provenance(e) != "entrant"]
    mention_entrants = (
        f"{pan} : {len(entrants)} element(s) INVENTORIE(S) mais ENTRANT(S) — recu(s), jamais "
        f"produit(s) par ce projet, donc hors du ratio de couverture "
        f"({', '.join(sorted(e.id for e in entrants)[:8])}"
        f"{' …' if len(entrants) > 8 else ''})"
        if entrants else ""
    )
    if entrants and not produits:
        # Tout l inventaire est entrant : il n y a rien du produit a couvrir ici. NA, et le motif
        # le DIT — « 15/15 ratio 1,0 PASS » sur des entrants etait le pire des rapports possibles.
        return SortieAdaptateur(
            adaptateur, pan, cible, "NA",
            non_juge=[
                *non_juge,
                f"{pan} : SANS OBJET sur ce projet — les {len(entrants)} element(s) enumere(s) "
                "sont TOUS des entrants (familles "
                f"{', '.join(FAMILLES_ENTRANTES)}), donc aucun element PRODUIT a couvrir. "
                "Un ratio de 1,0 sur des entrants est plus trompeur qu un pan franchement non "
                "couvert (TF-0380)",
            ],
            surface={
                "inventorie": 0, "exerce": 0, "ratio": 1.0, "seuil": seuil,
                "elements_exerces": [], "elements_non_exerces": [],
                "entrants_hors_ratio": sorted(e.id for e in entrants),
            },
        )
    if mention_entrants:
        non_juge = [*non_juge, mention_entrants]
    inventaire = produits
    manquants = [e for e in inventaire if e.id not in exerces]
    total = len(inventaire)
    ratio = (total - len(manquants)) / total
    findings = [
        Finding(
            id=e.id,
            classe=classes.ELEMENT_NON_EXERCE,
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
                classe=classes.SEUIL_NON_TENU,
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
            # TF-0380 : ce qui a ete ECARTE du ratio se publie. Un ecart tu se lirait comme un
            # perimetre complet — exactement ce que ce champ existe pour empecher.
            "entrants_hors_ratio": sorted(e.id for e in entrants),
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
    essais: list[Essai] | None = None,
    instance: dict | None = None,
    boucle: dict | None = None,
    gabarit_env: dict | None = None,
    vendorisation: list[dict] | None = None,
) -> dict:
    """Assemble le rapport. Un pan sans adaptateur est NOMME, jamais omis.

    A-5 : un pan non couvert ne sort plus un simple motif — il sort ce qu il FAUDRAIT pour le
    couvrir. Un motif seul est un constat ; le couple motif + chemin est une action.

    TF-0146 : `essais`, s il est fourni, porte le détail test-par-test (section `essais` du
    rapport, agrégée par `resume_essais`). Paramètre optionnel et rétro-compatible : aucun
    adaptateur actuel n en fournit encore (l intégration réelle — un adaptateur qui lit sa
    propre trace d exécution, ex. JUnit — est un jalon ultérieur, cf. `forge_tests.sondes.junit`
    pour le lecteur déjà prêt). Sans lui, la section reste PRÉSENTE mais déclare son absence :
    un rapport qui l omettrait silencieusement serait indiscernable d un rapport qui l a
    mesurée et n a rien trouvé, exactement le silence que ce framework interdit ailleurs.
    """
    from forge_tests.actions import classifier
    from forge_tests.risque import NON_JUGE as NON_JUGE_RISQUE
    from forge_tests.seuils import au_rapport as seuils_au_rapport

    verifier_regle_conjointe(sorties)
    chemins = pour_couvrir or {}
    couverts = {s.pan for s in sorties if s.verdict not in ("SKIP", "NA")}
    # NA — sans objet, PROUVE : le pan sort du calcul de couverture sans compter comme manque.
    # Il reste NOMME au rapport avec son motif : un pan qui disparaitrait laisserait croire que
    # le sujet n existe pas dans le framework, exactement l absence silencieuse interdite.
    sans_objet = {
        s.pan: (s.non_juge[-1] if s.non_juge else "sans motif")
        for s in sorties
        if s.verdict == "NA"
    }
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
        if p not in couverts and p not in sans_objet
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
        # TF-0340/TF-0341 — le cycle de vie et la PROVENANCE de l instance servie. Section
        # toujours presente : absente quand aucune instance n est declaree, elle serait
        # indiscernable d une section qui a mesure et n a rien trouve. Un audit qui laisse une
        # instance debout le DIT, et un audit qui mesure un code plus ancien que le depot le dit
        # aussi — c est la generalisation du terme de comparaison de TF-0288 a l instance entiere.
        "instance": instance if instance is not None else {
            "cycle_de_vie": None, "provenance": None,
            "non_juge": ["instance : section non alimentee par cet appelant (`rapport(..., "
                         "instance=...)`) — ni le cycle de vie ni la provenance n ont ete mesures"],
        },
        # A-2 : l inventaire des modules SOURCES — exerce, mute, ou jamais exerce et NOMME.
        "modules": modules if modules is not None else [
            m for s in sorties for m in s.modules
        ],
        "pans_non_couverts": non_couverts,
        # « NA » (14/08) : les pans SANS OBJET sur ce projet, nommés avec leur preuve d absence.
        # Distincts des non couverts : ceux-ci sont un manque, ceux-là n en sont pas un.
        "pans_sans_objet": [
            {"pan": p, "motif": motif} for p, motif in sorted(sans_objet.items())
        ],
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
        # TF-0146 — détail test-par-test. Présente même sans `essais` fourni : `fourni: False`
        # dit explicitement « non mesuré ici », jamais confondu avec « mesuré, rien à signaler ».
        "essais": resume_essais(essais) if essais is not None else {
            "cas": [], "totaux": {}, "signales": [], "fourni": False,
        },
        # TF-0352/0353 — la CAMPAGNE peut-elle clore ? Le verdict ci-dessous juge CE run ; la
        # section `boucle` juge la campagne qui l entoure. Les confondre est exactement la
        # faute du 12/08 : un rapport PARTIEL conforme, 121 findings, produit inchangé. Section
        # toujours présente : « pas de journal » se lit, il ne se devine pas.
        "boucle": boucle if boucle is not None else _boucle_non_mesuree(),
        # TF-0539 : ce que la forge a depose (ou pourquoi elle ne l'a pas fait) — le lecteur
        # du rapport apprend qu'un gabarit l'attend, sans avoir a le deviner.
        "gabarit_env": gabarit_env if gabarit_env is not None else {"depose": False, "motif": "non mesure (audit hors flux principal)", "fichier": None},
        # TF-0580 : les copies vendorisees et leur ecart a l amont — « non comparable » n est
        # JAMAIS « a jour », sinon l outil reproduit le defaut qu il detecte.
        "vendorisation": vendorisation if vendorisation is not None else [],
        "verdict": (
            "PARTIEL"
            if non_couverts
            else ("FAIL" if any(s.verdict == "FAIL" for s in sorties) else "PASS")
        ),
    }


def _boucle_non_mesuree() -> dict:
    from forge_tests import boucle as _boucle

    return _boucle.verdict([])
