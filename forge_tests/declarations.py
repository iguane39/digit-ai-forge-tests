"""Déclarations du projet sur les CONSTATS d audit — le canal de réponse qui manquait.

RT-18 (majeur, 14/08) : « un constat réfuté par le projet revient à chaque audit,
indéfiniment ». Fait mesuré par le produit : RT-1 et RT-2 remis le 13/08, les 13 findings
correspondants revenus identiques le 14/08, sur six audits successifs. Rien ne permettait au
projet de dire une fois « ce constat est contesté, voici la contre-preuve », et rien ne
permettait à l auditeur d en tenir compte. Le projet tenait donc sa déclaration à côté
(`forge/constats-contestes.jsonl`, 14 lignes), invisible au rapport.

C est le TROISIÈME retour du même manque, et un seul mécanisme les couvre tous les trois :

  - **RT-13** — un cas dérivé écrit par le projet doit pouvoir être ADOPTÉ. Déjà livré :
    `forge_tests.adoption` (`forge/cas-adoptes.jsonl`). Ce module ne le refait pas — il le
    CITE : le motif `adopte` est du vocabulaire connu ici, mais sa déclaration vit là-bas, et
    une ligne `adopte` déposée dans ce fichier-ci est refusée en le disant ;
  - **RT-15** — un mutant d un module que le point d entrée déployé SUPPLANTE
    (`azure/standalone_backend.py` redéfinit trois routes), ou un élément qu une configuration
    laisse `disabled` : le tuer demanderait d exercer du code que le produit livré n atteint
    jamais. Motifs `bloque-code-supplante` et `bloque-configuration` ;
  - **RT-18** — le constat CONTESTÉ, avec le test qui établit le contraire. Motif `conteste`.

**Le contrat, tenu par ce module :**

    <projet>/forge/constats-contestes.jsonl   — une ligne JSON par constat déclaré :
    {"constat": "qualif/qualif:effet:/:0:form", "motif": "conteste",
     "preuve": "frontend/tests/e2e/10-formulaire.spec.ts", "par": "equipe-front",
     "date": "2026-08-14", "expire_le": "2026-11-14", "explication": "…"}

`constat` est la clé de jointure du rapport : `<pan>/<id du finding>` — la MÊME que
`actions[].finding_ref`. La forme courte `<id>` est acceptée (elle vise alors le constat quel
que soit son pan) ; `classe` restreint la déclaration à une classe de finding précise quand un
même élément en porte plusieurs. C est le PROJET qui déclare, jamais la forge, et le fichier
est lu en LECTURE SEULE (G-1) : rien n est jamais écrit chez l audité.

**Quatre règles, toutes vérifiées, sans lesquelles ce canal deviendrait un bouton « faire
taire » :**

  1. **contre-preuve obligatoire** — la déclaration cite un chemin (`preuve`) qui doit
     EXISTER dans le projet : le test qui établit le contraire pour `conteste`, le point
     d entrée qui supplante ou le fichier de configuration qui désactive pour les motifs
     bloqués. Introuvable → déclaration REFUSÉE avec son motif, exactement comme
     `adoption.charger` refuse une adoption dont le test n existe pas, et le constat reste au
     décompte principal ;
  2. **motif TYPÉ** — hors du vocabulaire `MOTIFS`, la déclaration est refusée. Une prose
     libre ne se relit pas et ne se compte pas ;
  3. **datée et signée** — `par` (qui déclare) et `date` (quand) sont obligatoires. Sans date,
     une déclaration se périmerait sans que personne le sache : elle est donc bornée, par
     `expire_le` si le projet le fixe, sinon à `PEREMPTION_JOURS` jours. Passé ce terme la
     déclaration est PÉRIMÉE — le constat revient au décompte principal, en le disant ;
  4. **comptabilisé à part, jamais supprimé** — un constat déclaré RESTE dans `findings`
     (donc dans l inventaire de surface, donc au dashboard) : il porte un champ `declaration`
     et sort du décompte principal (`bandes_de_risque`, tuile « Constats d échec », liste des
     actions). La mesure reste opposable, et la contestation aussi : un relecteur la lit, avec
     sa contre-preuve, et peut l attaquer.

Ce module ne juge pas si la contre-preuve DIT ce qu elle prétend — il constate une déclaration
et l existence de son support. Vérifier qu un test affirme ce qu il annonce est le rôle de la
mutation, pas d une déclaration.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from forge_tests import adoption as _adoption

FICHIER = "forge/constats-contestes.jsonl"

# Terme par défaut d une déclaration qui n en fixe pas. Une contestation sans fin serait un
# effacement : au bout de ce délai, le constat revient au décompte et la déclaration se renouvelle.
PEREMPTION_JOURS = 180

RETENUE, REFUSEE, PERIMEE, AUCUNE = "retenue", "refusee", "perimee", "aucune"

# Vocabulaire des motifs. Une déclaration hors de cette table est refusée : c est ce qui rend
# les trois familles de RT comptables séparément au lieu de se fondre en « ignoré ».
MOTIFS: dict[str, dict[str, str]] = {
    "conteste": {
        "libelle": "constat contesté",
        "retour": "RT-18",
        "preuve_attendue": "le chemin du test qui établit le CONTRAIRE du constat",
    },
    "bloque-configuration": {
        "libelle": "bloqué par une configuration absente ou désactivée",
        "retour": "RT-15",
        "preuve_attendue": "le chemin du fichier de configuration qui montre l élément "
        "désactivé ou non déployé",
    },
    "bloque-code-supplante": {
        "libelle": "bloqué par du code supplanté au déploiement",
        "retour": "RT-15",
        "preuve_attendue": "le chemin du point d entrée déployé qui redéfinit ou supplante le "
        "code visé — le produit livré ne l atteint jamais",
    },
    "adopte": {
        "libelle": "cas dérivé adopté par le projet",
        "retour": "RT-13",
        "preuve_attendue": "le chemin du test qui joue le cas",
        # Déjà livré : ce module ne le refait pas, il y renvoie.
        "delegue": _adoption.FICHIER,
    },
}

NON_JUGE = [
    "declarations : le fichier `forge/constats-contestes.jsonl` est une DECLARATION du projet — "
    "ce module verifie que la preuve citee EXISTE, jamais qu elle etablit ce qu elle pretend "
    "(c est le role de la mutation et de l execution)",
    "declarations : un constat ecarte reste MESURE et reste au rapport ; il sort du decompte "
    "principal, il ne sort pas de l inventaire — la mesure demeure opposable, la declaration aussi",
    "declarations : la peremption se juge sur la DATE DECLAREE par le projet, jamais sur une "
    "horloge externe — une date postee en avant differe le terme d autant, et cela se lit",
    "declarations : une declaration qui ne vise aucun constat du rapport courant sort en "
    "INCONNUE, declaree telle quelle — le constat a pu disparaitre, ou l identifiant changer",
]


# --- Lecture de la déclaration ------------------------------------------------------------------
def _date(valeur: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(valeur)
    except ValueError:
        return None


def _refus(entree: dict, pourquoi: str, statut: str = REFUSEE) -> dict:
    return {**entree, "statut": statut, "motif_du_refus": pourquoi}


def charger(cible: Path, aujourdhui: _dt.date | None = None) -> dict[str, dict]:
    """Déclarations du projet, chacune avec son verdict de vérification.

    Renvoie `{constat: entrée}` où l entrée porte toujours `statut` (`retenue`, `refusee`,
    `perimee`) et, pour les deux derniers, `motif_du_refus`. Fichier absent = aucune
    déclaration : ce n est pas une faute, c est l état initial — et c est aussi le cas de tous
    les projets qui ignorent que ce canal existe.
    """
    source = Path(cible) / FICHIER
    if not source.is_file():
        return {}
    jour = aujourdhui or _dt.date.today()
    declarations: dict[str, dict] = {}
    for rang, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        base = {"ligne": rang, "constat": "", "motif": "", "preuve": "", "par": "", "date": "",
                "expire_le": "", "explication": "", "classe": ""}
        try:
            brut = json.loads(ligne)
        except json.JSONDecodeError:
            declarations[f"(ligne {rang})"] = _refus(
                base, f"ligne {rang} de {FICHIER} : JSON invalide — declaration ignoree"
            )
            continue
        if not isinstance(brut, dict):
            declarations[f"(ligne {rang})"] = _refus(
                base, f"ligne {rang} de {FICHIER} : objet JSON attendu — declaration ignoree"
            )
            continue
        entree = {
            **base,
            **{
                cle: str(brut.get(cle) or "").strip()
                for cle in ("constat", "motif", "preuve", "par", "date", "expire_le",
                            "explication", "classe")
            },
        }
        cle = entree["constat"] or f"(ligne {rang})"
        if cle in declarations:
            # Le doublon ne remplace pas silencieusement : deux déclarations sur un même constat
            # sont un désaccord interne au projet, et il se lit.
            declarations[f"(ligne {rang})"] = _refus(
                entree,
                f"doublon : « {entree['constat']} » est deja declare ligne "
                f"{declarations[cle].get('ligne')} — la premiere declaration fait foi",
            )
            continue
        declarations[cle] = _verifier(entree, Path(cible), jour)
    return declarations


def _verifier(entree: dict, cible: Path, jour: _dt.date) -> dict:
    """Verdict d UNE déclaration : les quatre règles, dans l ordre où elles se lisent."""
    if not entree["constat"]:
        return _refus(entree, "aucun constat vise — une declaration sans cible ne s applique pas")

    motif = entree["motif"]
    if not motif:
        return _refus(
            entree,
            "aucun motif type — motifs admis : " + ", ".join(sorted(MOTIFS)),
        )
    if motif not in MOTIFS:
        return _refus(
            entree,
            f"motif « {motif} » hors vocabulaire — motifs admis : " + ", ".join(sorted(MOTIFS)),
        )
    delegue = MOTIFS[motif].get("delegue")
    if delegue:
        return _refus(
            entree,
            f"le motif « {motif} » se declare dans `{delegue}` (RT-13), pas ici — "
            "un cas adopte est verifie par `forge_tests.adoption`, ce fichier porte les "
            "constats ecartes",
        )

    if not entree["par"]:
        return _refus(
            entree, "declaration non signee (`par` absent) — qui declare fait partie de la preuve"
        )
    if not entree["date"]:
        return _refus(
            entree,
            "declaration non datee (`date` absente, format AAAA-MM-JJ) — sans date, elle se "
            "perimerait sans que personne le sache",
        )
    posee = _date(entree["date"])
    if posee is None:
        return _refus(
            entree, f"date « {entree['date']} » illisible — format attendu AAAA-MM-JJ"
        )

    if not entree["preuve"]:
        return _refus(
            entree,
            "aucune preuve citee — "
            + MOTIFS[motif]["preuve_attendue"]
            + " ; un constat conteste sans preuve a l appui reste au rapport",
        )
    if not (Path(cible) / entree["preuve"]).exists():
        return _refus(
            entree,
            f"la preuve citee est introuvable ({entree['preuve']}) — declaration refusee, le "
            "constat reste au decompte",
        )

    if entree["expire_le"]:
        terme = _date(entree["expire_le"])
        if terme is None:
            return _refus(
                entree,
                f"date de peremption « {entree['expire_le']} » illisible — format attendu "
                "AAAA-MM-JJ",
            )
    else:
        terme = posee + _dt.timedelta(days=PEREMPTION_JOURS)
    if terme < jour:
        return _refus(
            entree,
            f"declaration perimee le {terme.isoformat()} (posee le {entree['date']}"
            + (
                f", terme declare {entree['expire_le']}"
                if entree["expire_le"]
                else f", terme par defaut a {PEREMPTION_JOURS} jours"
            )
            + ") — a renouveler ou a retirer ; le constat revient au decompte",
            statut=PERIMEE,
        )
    return {**entree, "statut": RETENUE, "motif_du_refus": "", "terme": terme.isoformat()}


# --- Rapprochement avec les constats du rapport --------------------------------------------------
def cles_du_finding(finding: dict) -> tuple[str, str]:
    """Les deux clés sous lesquelles un constat est citable : `<pan>/<id>` et `<id>` seul."""
    pan = str(finding.get("pan") or "")
    identifiant = str(finding.get("id") or "")
    return (f"{pan}/{identifiant}" if pan else identifiant, identifiant)


def statut(declarations: dict[str, dict], finding: dict) -> dict:
    """Déclaration qui vise ce constat, ou `{"statut": "aucune"}`. La clé longue prime."""
    for cle in cles_du_finding(finding):
        entree = declarations.get(cle)
        if entree is None:
            continue
        classe = entree.get("classe") or ""
        if classe and classe != str(finding.get("classe") or ""):
            continue
        return entree
    return {"statut": AUCUNE, "motif": "", "preuve": "", "par": "", "date": "",
            "motif_du_refus": ""}


def est_ecarte(finding: dict) -> bool:
    """Ce constat sort-il du décompte principal ? Vrai pour la SEULE déclaration retenue."""
    declaration = finding.get("declaration")
    return bool(declaration) and declaration.get("statut") == RETENUE


def constats_inconnus(declarations: dict[str, dict], findings: list[dict]) -> list[str]:
    """Déclarations qui ne visent aucun constat du rapport courant — jamais silencieuses."""
    vises = {cle for f in findings for cle in cles_du_finding(f)}
    return sorted(
        cle
        for cle, entree in declarations.items()
        if not cle.startswith("(ligne ") and cle not in vises and entree.get("constat")
    )


# --- Application au rapport ----------------------------------------------------------------------
def reintegrer(rapport: dict) -> dict:
    """Défait `appliquer` : les constats écartés redeviennent des constats comme les autres.

    Sans elle, `--reprendre` sur un rapport déjà traité repartirait d un décompte amputé, et
    une déclaration retirée du projet ne rendrait jamais son constat au rapport.
    """
    for finding in rapport.get("findings") or []:
        finding.pop("declaration", None)
    reprises = rapport.pop("actions_declarees", None) or []
    if reprises:
        actions = list(rapport.get("actions") or [])
        connues = {a.get("finding_ref") for a in actions}
        actions.extend(a for a in reprises if a.get("finding_ref") not in connues)
        rapport["actions"] = actions
    rapport.pop("declarations", None)
    rapport.pop("bandes_de_risque_declares", None)
    _recompter_bandes(rapport)
    return rapport


def _bandes(findings: list[dict]) -> dict[str, int]:
    from forge_tests.noyau import bande

    comptes = {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0}
    for finding in findings:
        risque = finding.get("risque")
        comptes["non_cote" if risque is None else bande(int(risque))] += 1
    return comptes


def _recompter_bandes(rapport: dict) -> None:
    """`bandes_de_risque` ne compte QUE les constats opposables ; les écartés ont la leur.

    Les deux sections existent toujours : un lecteur `jq` qui n additionnerait que la première
    doit pouvoir constater que la somme ne fait pas le total des findings, et trouver l autre.
    """
    if "findings" not in rapport:
        return
    findings = rapport.get("findings") or []
    ecartes = [f for f in findings if est_ecarte(f)]
    rapport["bandes_de_risque"] = _bandes([f for f in findings if not est_ecarte(f)])
    if ecartes:
        rapport["bandes_de_risque_declares"] = _bandes(ecartes)


def appliquer(rapport: dict, cible: Path, aujourdhui: _dt.date | None = None) -> dict:
    """Applique au rapport les déclarations du projet. Idempotent, et LECTURE SEULE (G-1).

    Le rapport gagne une section `declarations` — toujours présente une fois ce point
    d application franchi, y compris quand le projet n a rien déclaré : un canal que le projet
    ignore est un canal qui n existe pas.
    """
    reintegrer(rapport)
    source = Path(cible) / FICHIER
    declarations = charger(cible, aujourdhui)
    findings = rapport.get("findings") or []

    ecartes = 0
    for finding in findings:
        entree = statut(declarations, finding)
        if entree["statut"] == AUCUNE:
            continue
        finding["declaration"] = {
            cle: entree.get(cle, "")
            for cle in ("statut", "motif", "preuve", "par", "date", "expire_le", "explication",
                        "motif_du_refus")
        }
        finding["declaration"]["libelle_motif"] = MOTIFS.get(entree.get("motif", ""), {}).get(
            "libelle", entree.get("motif", "")
        )
        ecartes += entree["statut"] == RETENUE

    # L action d un constat écarté n a plus de destinataire : elle est MISE À PART, jamais
    # perdue. Un constat non déclaré qui partagerait la même référence garde la sienne.
    refs_ecartees = {
        cles_du_finding(f)[0] for f in findings if est_ecarte(f)
    } - {cles_du_finding(f)[0] for f in findings if not est_ecarte(f)}
    actions, mises_a_part = [], []
    for action in rapport.get("actions") or []:
        (mises_a_part if action.get("finding_ref") in refs_ecartees else actions).append(action)
    if mises_a_part:
        rapport["actions"] = actions
        rapport["actions_declarees"] = mises_a_part

    _recompter_bandes(rapport)
    comptes = {
        statut_: sum(1 for e in declarations.values() if e.get("statut") == statut_)
        for statut_ in (RETENUE, REFUSEE, PERIMEE)
    }
    inconnus = constats_inconnus(declarations, findings)
    rapport["declarations"] = {
        "fichier": FICHIER,
        "present": source.is_file(),
        "motifs": {cle: valeur["libelle"] for cle, valeur in MOTIFS.items()},
        "compte": {
            **comptes,
            "constats_ecartes": ecartes,
            "inconnues": len(inconnus),
        },
        "inconnues": inconnus,
        "entrees": sorted(declarations.values(), key=lambda e: (e.get("ligne") or 0)),
        # Ce que le projet doit écrire pour se servir du canal — au rapport, pas dans une doc
        # qu il faudrait connaître d avance.
        "pour_declarer": (
            f"deposer une ligne JSON par constat dans `{FICHIER}` : "
            '{"constat": "<pan>/<id du finding>", "motif": "<'
            + "|".join(sorted(MOTIFS))
            + '>", "preuve": "<chemin qui existe>", "par": "<qui declare>", '
            '"date": "AAAA-MM-JJ"}. La preuve est verifiee ; sans elle le constat reste au '
            "decompte"
        ),
    }
    return rapport
