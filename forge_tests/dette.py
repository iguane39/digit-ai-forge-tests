"""Registre de dette — P5.

Les `non_juge` étaient des chaînes en dur dans chaque module : de la prose, donc du silence
à retardement. Ici ils deviennent des entrées VERSIONNÉES à statut, sur le patron du registre
d oracles de quality-oracles (règle §4 : un domaine non couvert reçoit une entrée, pas une
phrase). Le registre est REGÉNÉRÉ depuis le code — impossible de le laisser diverger — et les
statuts déjà posés à la main sont PRÉSERVÉS.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REGISTRE = Path(__file__).resolve().parent.parent / "registre-dette.json"
STATUTS = ("todo", "assume", "ok")


def _identifiant(domaine: str, enonce: str) -> str:
    empreinte = hashlib.sha256(enonce.encode("utf-8")).hexdigest()[:8]
    return f"{domaine}-{empreinte}"


def collecter() -> list[dict]:
    """Rassemble les non_juge déclarés par le noyau, le risque, l exécution et les adaptateurs."""
    from forge_tests import (
        actions,
        execution,
        generateur,
        generateur_data,
        invariants,
        qualification,
        reprise,
        risque,
        sql,
    )
    from forge_tests.adaptateurs import REGISTRE as ADAPTATEURS
    from forge_tests.livrables import cahiers, dashboard, exigences, jeux

    sources: list[tuple[str, list[str]]] = [
        ("risque", list(risque.NON_JUGE)),
        ("execution", list(execution.NON_JUGE)),
        # Les limites de l analyse STATIQUE des gardes (RT-9 : un seul niveau d appel resolu)
        # etaient declarees dans `invariants` et collectees nulle part : elles ne figuraient au
        # registre d aucun domaine. Une dette qui n entre pas au registre est de la prose.
        ("invariants", list(invariants.NON_JUGE)),
        ("generateur", list(generateur.NON_JUGE)),
        ("generateur-data", list(generateur_data.NON_JUGE)),
        ("sql", list(sql.NON_JUGE)),
        ("qualification", list(qualification.NON_JUGE)),
        ("reprise", list(reprise.NON_JUGE)),
        ("actions", list(actions.NON_JUGE)),
        ("cahiers", list(cahiers.NON_JUGE)),
        ("jeux-de-donnees", list(jeux.NON_JUGE)),
        ("exigences", list(exigences.NON_JUGE)),
        ("dashboard", list(dashboard.NON_JUGE)),
    ]
    for nom, module in ADAPTATEURS.items():
        sources.append((nom, list(getattr(module, "NON_JUGE", []))))

    entrees: list[dict] = []
    vus: set[str] = set()
    for domaine, enonces in sources:
        for enonce in enonces:
            identifiant = _identifiant(domaine, enonce)
            if identifiant in vus:
                continue
            vus.add(identifiant)
            entrees.append(
                {
                    "id": identifiant,
                    "domaine": domaine,
                    "enonce": enonce.strip(),
                    "statut": "todo",
                }
            )
    return entrees


def regenerer(chemin: Path | None = None) -> dict:
    """Régénère le registre depuis le code, en préservant les statuts déjà posés.

    Une entrée disparue du code passe en `resolue` plutôt que d être effacée : on garde la
    trace de ce qui a été comblé.
    """
    cible = chemin or REGISTRE
    ancien = {}
    if cible.exists():
        ancien = {e["id"]: e for e in json.loads(cible.read_text(encoding="utf-8"))["dette"]}

    courant = collecter()
    for entree in courant:
        precedent = ancien.get(entree["id"])
        if precedent:
            entree["statut"] = precedent.get("statut", "todo")
            if precedent.get("note"):
                entree["note"] = precedent["note"]

    ids_courants = {e["id"] for e in courant}
    resolues = [
        {**e, "statut": "resolue"} for i, e in ancien.items() if i not in ids_courants
    ]

    donnees = {
        "version": 1,
        "note": (
            "Dette de jugement du framework. `todo` = à outiller · `assume` = limite acceptée "
            "et déclarée pour toujours · `ok` = comblée. Régénéré depuis le code : ne pas "
            "éditer les énoncés à la main, seulement les statuts et les notes."
        ),
        "dette": sorted(courant + resolues, key=lambda e: (e["statut"], e["domaine"])),
    }
    cible.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return donnees


def charger(chemin: Path | None = None) -> list[dict]:
    cible = chemin or REGISTRE
    if not cible.exists():
        return []
    return json.loads(cible.read_text(encoding="utf-8"))["dette"]


def resume() -> dict[str, int]:
    compte = dict.fromkeys((*STATUTS, "resolue"), 0)
    for entree in charger():
        compte[entree["statut"]] = compte.get(entree["statut"], 0) + 1
    return compte


if __name__ == "__main__":
    donnees = regenerer()
    par_statut: dict[str, int] = {}
    for entree in donnees["dette"]:
        par_statut[entree["statut"]] = par_statut.get(entree["statut"], 0) + 1
    print(f"registre de dette regenere : {len(donnees['dette'])} entrees")
    for statut, compte in sorted(par_statut.items()):
        print(f"  {statut:<10} {compte}")
    print(f"  -> {REGISTRE}")
