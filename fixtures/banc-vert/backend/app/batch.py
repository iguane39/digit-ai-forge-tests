"""Job de clôture journalière — 5 branches, 2 codes de rejet, 1 chemin de reprise."""

from __future__ import annotations

BRANCHES = ("B1", "B2", "B3", "B4", "B5")
CODES_REJET = ("REJ-VIDE", "REJ-STOCK")

REJ_VIDE = "REJ-VIDE"
REJ_STOCK = "REJ-STOCK"


def cloture_journaliere(
    commandes: list[dict], stock: dict[str, int], journal: dict | None = None
) -> dict:
    """Clôture les commandes validées du jour.

    B1 nominal · B2 rejet commande sans ligne · B3 rejet stock insuffisant
    B4 reprise au dernier point de contrôle · B5 idempotence si journée déjà close.
    """
    journal = journal if journal is not None else {}
    if journal.get("cloturee"):
        # B5 — idempotence : un second passage n a aucun effet.
        return {"cloturees": journal["cloturees"], "rejets": journal["rejets"], "reprise": False}

    # B4 — reprise : on repart du dernier point de contrôle, jamais du début.
    deja_vues = set(journal.get("point_de_controle", []))
    reprise = bool(deja_vues)

    cloturees: list[int] = list(journal.get("cloturees", []))
    rejets: list[dict] = list(journal.get("rejets", []))

    for commande in commandes:
        if commande["id"] in deja_vues:
            continue
        if not commande.get("lignes"):
            rejets.append({"id": commande["id"], "code": REJ_VIDE})  # B2
            continue
        manque = [
            ligne for ligne in commande["lignes"] if stock.get(ligne["plat"], 0) < ligne["quantite"]
        ]
        if manque:
            rejets.append({"id": commande["id"], "code": REJ_STOCK})  # B3
            continue
        for ligne in commande["lignes"]:
            stock[ligne["plat"]] -= ligne["quantite"]
        cloturees.append(commande["id"])  # B1

    if not cloturees: journal["vide"] = True
    journal.update({"cloturee": True, "cloturees": cloturees, "rejets": rejets})
    return {"cloturees": cloturees, "rejets": rejets, "reprise": reprise}
