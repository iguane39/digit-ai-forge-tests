"""Reprise d un audit — rejouer ce qui manque, garder ce qui était vert (RT-6b).

Le cycle réel d un audit chez un client n est pas « une passe et un verdict ». C est : une
première passe qui bute sur ce qui n est pas configuré, un humain qui saisit les identifiants
manquants, puis une seconde passe. Sans reprise, cette seconde passe coûte l audit ENTIER —
migrations rejouées sur base neuve, suite e2e complète — pour n éclairer que trois éléments.
Le coût pousse alors à ne pas la faire, et la couverture reste durablement partielle : ce n est
pas un confort, c est ce qui décide si le trou est comblé ou oublié.

Ce module fusionne un rapport antérieur et un rapport neuf. Deux règles :

  - **on ne rejoue pas ce qui était vert.** Un pan dont tous les éléments étaient exercés, sans
    finding et sans non-testable, est repris tel quel — il n est même pas lancé ;
  - **rien n est repris en silence.** Chaque élément du rapport final porte sa PROVENANCE :
    `exerce_le_run` s il vient de la passe qui vient d avoir lieu, `repris_de` s il vient du
    rapport rechargé. Un lecteur qui doute peut refaire une passe complète et comparer.

La granularité de la ré-exécution est le PAN — c est l unité qu un adaptateur sait lancer. La
granularité de la PROVENANCE est l élément : c est celle dont le lecteur a besoin.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests.actions import classifier
from forge_tests.noyau import POUR_COUVRIR_DEFAUT, bande

NON_JUGE = [
    "reprise : la re-execution a la granularite du PAN — un pan qui doit etre rejoue l est en "
    "entier. La provenance, elle, est donnee element par element",
    "reprise : un element repris d un rapport anterieur atteste d une mesure PASSEE, pas de "
    "l etat courant du projet — si le code a change entre les deux passes, seule une passe "
    "complete fait foi",
]


def charger(chemin: Path) -> dict:
    """Rapport antérieur, tel qu écrit par `--json --sortie`."""
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if not isinstance(donnees, dict) or "findings" not in donnees:
        raise ValueError(
            f"{chemin} n est pas un rapport Forge Tests exploitable "
            "(attendu la sortie de `--json`, refus plutot que fusion approximative)"
        )
    return donnees


def _surface(rapport: dict, pan: str) -> dict:
    return (rapport.get("couverture_par_pan") or {}).get(pan) or {}


def _exerces(rapport: dict, pan: str) -> set[str]:
    return set(_surface(rapport, pan).get("elements_exerces") or [])


def _noms_non_couverts(rapport: dict) -> list[str]:
    """Noms des pans non couverts, quelle que soit la FORME du champ.

    A-5 a enrichi `pans_non_couverts` de `[pan]` en `[{pan, motif, pour_couvrir}]`. Un rapport
    produit avant ce changement reste relisible : une reprise qui refuserait les anciens
    rapports transformerait une amélioration de rapport en rupture d outil.
    """
    noms: list[str] = []
    for entree in rapport.get("pans_non_couverts") or []:
        nom = entree.get("pan") if isinstance(entree, dict) else entree
        if nom:
            noms.append(str(nom))
    return noms


def pans_a_rejouer(ancien: dict) -> list[str]:
    """Pans qui ne sont PAS déjà verts : non couverts, incomplets, en échec, ou non testables."""
    a_rejouer: set[str] = set(_noms_non_couverts(ancien))
    for entree in ancien.get("adaptateurs") or []:
        if entree.get("verdict") != "PASS":
            a_rejouer.add(entree.get("pan", ""))
    for pan, surface in (ancien.get("couverture_par_pan") or {}).items():
        if (surface or {}).get("elements_non_exerces"):
            a_rejouer.add(pan)
    for entree in ancien.get("non_testables") or []:
        if entree.get("pan"):
            a_rejouer.add(entree["pan"])
    for finding in ancien.get("findings") or []:
        if finding.get("pan"):
            a_rejouer.add(finding["pan"])
    return sorted(p for p in a_rejouer if p)


def fusionner(
    ancien: dict, nouveau: dict, origine: str, rejoues: list[str], pans_attendus: list[str]
) -> dict:
    """Rapport fusionné : le neuf pour les pans rejoués, l ancien pour les autres."""
    rejoues_ = set(rejoues)
    non_juge = set(ancien.get("non_juge") or []) | set(nouveau.get("non_juge") or [])
    non_juge |= set(NON_JUGE)

    couverture: dict[str, dict] = {}
    provenance: dict[str, dict] = {}
    repris_par_pan: dict[str, set[str]] = {}

    for pan, surface in (ancien.get("couverture_par_pan") or {}).items():
        if pan in rejoues_ or not surface:
            continue
        couverture[pan] = surface
        provenance[pan] = {
            "exerce_le_run": [],
            "repris_de": sorted(surface.get("elements_exerces") or []),
        }

    for pan, surface in (nouveau.get("couverture_par_pan") or {}).items():
        if not surface:
            continue
        neufs = set(surface.get("elements_exerces") or [])
        manquants = list(surface.get("elements_non_exerces") or [])
        # Ce que la passe neuve n a pas atteint mais que le rapport repris avait DEJA exerce :
        # c est tout l objet de la reprise. Borne a l inventaire courant — un element disparu
        # du projet ne se reprend pas.
        repris = (_exerces(ancien, pan) - neufs) & set(manquants)
        repris_par_pan[pan] = repris
        restants = [e for e in manquants if e not in repris]
        total = int(surface.get("inventorie") or (len(neufs) + len(manquants)))
        exerce = total - len(restants)
        seuil = float(surface.get("seuil") or 1.0)
        couverture[pan] = {
            **surface,
            "exerce": exerce,
            "ratio": round(exerce / total, 4) if total else 0.0,
            "seuil": seuil,
            "elements_exerces": sorted(neufs | repris),
            "elements_non_exerces": restants,
        }
        provenance[pan] = {"exerce_le_run": sorted(neufs), "repris_de": sorted(repris)}

    findings: list[dict] = []
    sans_pan = 0
    for finding in ancien.get("findings") or []:
        pan = finding.get("pan")
        if pan is None:
            sans_pan += 1
            continue
        if pan not in rejoues_:
            findings.append({**finding, "provenance": f"repris_de:{origine}"})
    for finding in nouveau.get("findings") or []:
        pan = finding.get("pan") or ""
        if finding["id"] in repris_par_pan.get(pan, set()):
            continue  # element couvert par la reprise : le reprocher serait un faux positif
        surface = couverture.get(pan) or {}
        if (
            finding["id"] == f"seuil:{pan}"
            and surface.get("ratio", 0) >= surface.get("seuil", 1.0)
        ):
            continue  # le seuil est tenu APRES fusion : le finding n a plus d objet
        findings.append({**finding, "provenance": "exerce_le_run"})
    if sans_pan:
        non_juge.add(
            f"reprise : {sans_pan} finding(s) du rapport repris n ont pas de pan (rapport "
            "produit par une version anterieure) — ils sont ECARTES de la fusion, seule une "
            "passe complete les retablirait"
        )
    findings.sort(key=lambda f: f.get("risque") or 0, reverse=True)

    bandes = {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0}
    for finding in findings:
        risque = finding.get("risque")
        bandes["non_cote" if risque is None else bande(risque)] += 1

    non_testables = [
        entree for entree in (ancien.get("non_testables") or [])
        if entree.get("pan") not in rejoues_
    ] + list(nouveau.get("non_testables") or [])

    adaptateurs: dict[str, dict] = {
        entree["pan"]: entree for entree in (ancien.get("adaptateurs") or [])
    }
    for entree in nouveau.get("adaptateurs") or []:
        pan = entree["pan"]
        garde = dict(entree)
        if garde.get("verdict") == "FAIL" and not any(f.get("pan") == pan for f in findings):
            # Tous ses findings ont ete resorbes par la reprise : le pan est vert.
            garde["verdict"] = "PASS"
        adaptateurs[pan] = garde

    motifs = {
        **(ancien.get("motifs_non_couverture") or {}),
        **(nouveau.get("motifs_non_couverture") or {}),
    }
    couverts = {pan for pan, e in adaptateurs.items() if e.get("verdict") != "SKIP"}
    # A-5 : le chemin de couverture de chaque pan est repris du rapport qui le portait — le
    # neuf d abord, l ancien à défaut. Il n est jamais réinventé ici.
    chemins: dict[str, str] = {}
    for source in (ancien, nouveau):
        for entree in source.get("pans_non_couverts") or []:
            if isinstance(entree, dict) and entree.get("pan") and entree.get("pour_couvrir"):
                chemins.setdefault(entree["pan"], entree["pour_couvrir"])
    non_couverts = [
        {
            "pan": p,
            "motif": motifs.get(p, "adaptateur absent : aucun module ne traite ce pan"),
            "pour_couvrir": chemins.get(p, POUR_COUVRIR_DEFAUT),
        }
        for p in pans_attendus
        if p not in couverts
    ]

    mutation = {
        pan: valeur for pan, valeur in (ancien.get("mutation") or {}).items()
        if pan not in rejoues_
    }
    mutation.update(nouveau.get("mutation") or {})

    return {
        "adaptateurs": [adaptateurs[p] for p in sorted(adaptateurs)],
        "couverture_par_pan": couverture,
        "mutation": mutation,
        # A-3/A-2 : les seuils et l inventaire de modules viennent du rapport qui les a
        # MESURES — le neuf s il a rejoue le pan back, l ancien sinon. Jamais recalcules ici.
        "seuils": nouveau.get("seuils") or ancien.get("seuils") or {},
        "modules": nouveau.get("modules") or ancien.get("modules") or [],
        "pans_non_couverts": non_couverts,
        "motifs_non_couverture": {
            e["pan"]: motifs[e["pan"]] for e in non_couverts if e["pan"] in motifs
        },
        "bandes_de_risque": bandes,
        "findings": findings,
        "non_testables": non_testables,
        # Les actions sont RECALCULEES sur le rapport fusionne, jamais reprises telles quelles :
        # une action heritee d un finding resorbe par la reprise reclamerait un travail deja
        # fait — le genre de faux positif qui fait fermer la liste.
        "actions": classifier(findings, non_testables, non_couverts),
        "non_juge": sorted(non_juge),
        "reprise": {
            "rapport_repris": origine,
            "pans_rejoues": sorted(rejoues_),
            # Tous les pans que le rapport repris connaissait et que l on n a PAS relances —
            # y compris ceux sans couverture de surface, comme la securite : les omettre
            # laisserait croire qu ils ont ete rejoues.
            "pans_repris_sans_rejeu": sorted(
                {e.get("pan", "") for e in (ancien.get("adaptateurs") or [])}
                - rejoues_
                - {""}
            ),
            "provenance": provenance,
        },
        "verdict": (
            "PARTIEL"
            if non_couverts
            else (
                "FAIL"
                if any(e.get("verdict") == "FAIL" for e in adaptateurs.values())
                else "PASS"
            )
        ),
    }
