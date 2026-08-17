"""Surface inventoriée, telle que le RAPPORT la porte — et chapitrage dérivé du registre.

Deux dérivations, aucune liste écrite à la main :

  - **les chapitres** viennent du registre des adaptateurs (`CHAPITRES` déclaré par chaque
    module). Un pan ajouté demain apparaît seul, avec son chapitre, sans qu une ligne soit
    touchée ici. Un pan qui n en déclare pas reçoit quand même un chapitre — nommé « pan sans
    chapitre déclaré », donc visible, jamais absent ;
  - **les éléments** viennent du rapport et de lui seul : couverture de surface, findings,
    non-testables, inventaire de modules. Le rapport EST l inventaire ; en relire une autre
    source ferait diverger le cahier de l audit qu il prétend restituer.

L état d un élément est l une de cinq valeurs, et jamais rien d autre :

    exerce · non_exerce · non_testable · defaut · exclu

`defaut` couvre l élément qu aucune surface n inventorie mais qu un finding NOMME (un mutant
survivant, une divergence, un contrôle d accessibilité). Sans lui, ces éléments n auraient pas
de chapitre — c est-à-dire disparaîtraient du cahier tout en figurant au rapport.
"""

from __future__ import annotations

import re

ETATS = ("exerce", "non_exerce", "non_testable", "defaut", "exclu")

CHAPITRE_SANS_DECLARATION = {
    "famille": "technique",
    "decoupe": "element",
}

# Axe de sous-chapitrage -> règles de rattachement, essayées dans l ordre. Chaque règle est un
# couple (motif, gabarit) : le premier motif qui reconnaît l identifiant donne le sous-chapitre.
# `entree` (TF-0223) rejoint les axes qualif : la porte d entrée est un écran et un parcours au
# même titre qu une route — sans elle, `qualif:entree:/` tombait en « éléments non rattachés ».
# TF-0316 : le segment `role:<etiquette>:` est OPTIONNEL. Sans lui, les éléments d un audit joué
# sous plusieurs identités tombaient tous en « éléments non rattachés » — la même route vue par
# deux rôles est le même ÉCRAN, et c est à cet écran qu elle se range.
_AXES_QUALIF = (
    r"^qualif:(?:role:[^:]+:)?(?:route|effet|console|marqueur|entree):(?P<v>/[^:]*)"
)
_REGLES: dict[str, tuple[tuple[re.Pattern[str], str], ...]] = {
    "ecran": (
        (re.compile(_AXES_QUALIF), "écran {v}"),
        (re.compile(r"^route:(?P<v>/\S*)$"), "écran {v}"),
        (re.compile(r"^(?:a11y|visuel):(?P<v>\S+)$"), "écran {v}"),
    ),
    "parcours": (
        (re.compile(_AXES_QUALIF), "parcours {v}"),
        (re.compile(r"^route:(?P<v>/\S*)$"), "parcours {v}"),
    ),
    "routeur": (
        (re.compile(r"^(?:code|endpoint):[A-Z]+ (?P<v>/[^=]*)"), "routeur {v}"),
        (re.compile(r"^divergence:(?:code|endpoint):[A-Z]+ (?P<v>/[^=]*)"), "routeur {v}"),
    ),
    "table": (
        (re.compile(r"^table:(?P<v>\w+)$"), "table {v}"),
        (re.compile(r"^(?:contrainte|index|trigger):(?P<v>\w+?)_\w+$"), "table {v}"),
        (re.compile(r"^contrainte:(?P<v>\w+)\.not_null$"), "colonne {v}"),
    ),
    # TF-0284 : le pan i18n range par LOCALE — c est le seul axe où l on veut lire, d un coup
    # d oeil, tout ce qui manque à l anglais. Ranger ses constats par écran les aurait dispersés
    # sur deux cents lignes, exactement là où ils étaient déjà invisibles.
    "locale": (
        (re.compile(r"^i18n:(?:route|navigation|langue):(?P<v>[^:]+)"), "locale {v}"),
    ),
    "fichier": (
        (re.compile(r"^migration:(?P<v>[^:]+):"), "migration {v}"),
        (re.compile(r"^divergence:migration:(?P<v>[^:]+)"), "migration {v}"),
        (re.compile(r"^interface:(?P<v>[^:]+):"), "gabarit {v}"),
    ),
    "job": (
        (re.compile(r"^branche:(?P<v>[^:]+):"), "job {v}"),
        (re.compile(r"^rejet:"), "codes de rejet"),
    ),
    "format": ((re.compile(r"^chemin:(?P<v>[^:]+):"), "format lu par {v}"),),
    "prompt": (
        (re.compile(r"^prompt:(?P<v>[^:]+)"), "prompt {v}"),
        (re.compile(r"^modele:(?P<v>\S+)$"), "modèle {v}"),
        (re.compile(r"^corpus:(?P<v>\S+)$"), "corpus {v}"),
    ),
    "module": (
        (re.compile(r"^mutant:(?P<v>[^:]+):"), "module {v}"),
        (re.compile(r"^seuil:mutation-module:(?P<v>\S+)$"), "module {v}"),
        (re.compile(r"^module(?:-non-exerce)?:(?P<v>\S+)$"), "module {v}"),
        (re.compile(r"^securite:(?P<v>[^:]+):"), "module {v}"),
    ),
}

# Sous-chapitre d accueil des éléments qu aucune règle ne rattache. Il est NOMMÉ : un élément
# rangé nulle part est un élément qu on cesse de lire.
NON_RATTACHE = "éléments non rattachés à un {axe}"


def sous_chapitre(decoupe: str, identifiant: str) -> tuple[str, bool]:
    """(libellé du sous-chapitre, rattachement dérivé ?)."""
    for motif, gabarit in _REGLES.get(decoupe, ()):
        trouve = motif.match(identifiant)
        if trouve:
            valeurs = trouve.groupdict()
            return gabarit.format(**{k: v for k, v in valeurs.items() if v}), True
    return NON_RATTACHE.format(axe=decoupe), False


def chapitres(registre: dict) -> list[dict]:
    """Chapitres du cahier, dérivés du registre des adaptateurs. Ordonnés par code."""
    par_code: dict[str, dict] = {}
    for module in registre.values():
        pan = getattr(module, "PAN", None)
        if not pan:
            continue
        declares = getattr(module, "CHAPITRES", ())
        if not declares:
            code = f"X-{pan}"
            declares = (
                {
                    "code": code,
                    "titre": f"Pan « {pan} » — chapitre non déclaré par son adaptateur",
                    **CHAPITRE_SANS_DECLARATION,
                },
            )
        for chapitre in declares:
            entree = par_code.setdefault(
                chapitre["code"],
                {
                    # Les clés déclarées par l adaptateur sont reportées TELLES QUELLES : un pan
                    # qui a besoin d un réglage propre (les combinaisons de rendu du pan visuel)
                    # le déclare chez lui, et le cahier le lit sans le connaître d avance.
                    **{k: v for k, v in chapitre.items() if k not in ("code", "titre")},
                    "code": chapitre["code"],
                    "titre": chapitre.get("titre", chapitre["code"]),
                    "famille": chapitre.get("famille", "technique"),
                    "decoupe": chapitre.get("decoupe", "element"),
                    "axe_cas": chapitre.get("axe_cas", "unitaire"),
                    "pans": [],
                },
            )
            if pan not in entree["pans"]:
                entree["pans"].append(pan)
    for entree in par_code.values():
        entree["pans"].sort()
        entree["axe_connu"] = entree["decoupe"] in _REGLES
    return sorted(par_code.values(), key=lambda c: c["code"])


def _element(identifiant: str, etat: str, **extra: object) -> dict:
    return {"id": identifiant, "etat": etat, **extra}


def inventaire(rapport: dict) -> dict[str, list[dict]]:
    """Éléments de surface par pan, tels que le rapport les porte. Aucune autre source."""
    par_pan: dict[str, dict[str, dict]] = {}

    def poser(pan: str, element: dict) -> dict:
        elements = par_pan.setdefault(pan, {})
        existant = elements.get(element["id"])
        if existant is None:
            elements[element["id"]] = element
            return element
        existant.update({k: v for k, v in element.items() if v not in (None, "", [])})
        return existant

    for pan, surface in (rapport.get("couverture_par_pan") or {}).items():
        for identifiant in (surface or {}).get("elements_exerces") or []:
            poser(pan, _element(identifiant, "exerce"))
        for identifiant in (surface or {}).get("elements_non_exerces") or []:
            poser(pan, _element(identifiant, "non_exerce"))

    for finding in rapport.get("findings") or []:
        pan = str(finding.get("pan") or "")
        element = par_pan.get(pan, {}).get(str(finding.get("id")))
        constat = {
            "classe": finding.get("classe"),
            "message": finding.get("message"),
            "localisation": finding.get("localisation"),
            "risque": finding.get("risque"),
            "severite": finding.get("severite"),
        }
        if element is None:
            poser(pan, _element(str(finding.get("id")), "defaut", **constat))
        else:
            element.update(constat)
            # Retour humain du 14/08 : un élément avec un constat rattaché affichait « Non
            # joué » (ou « Passé ») — illisible. Un finding NOMME un défaut : l'état suit.
            if constat.get("classe"):
                element["etat"] = "defaut"

    for entree in rapport.get("non_testables") or []:
        poser(
            str(entree.get("pan") or ""),
            _element(
                str(entree.get("element") or ""),
                "non_testable",
                champs_requis=list(entree.get("champs_requis") or []),
                message=entree.get("motif"),
            ),
        )

    # Les modules SOURCES sont l inventaire du pan `back` : la mutation ne publie pas de
    # surface, et sans eux le chapitre « robustesse de la suite » serait vide alors que le
    # rapport nomme chaque module et son état.
    for module in rapport.get("modules") or []:
        nom = str(module.get("module") or "")
        if not nom:
            continue
        if module.get("exclu"):
            etat, message = "exclu", str(module.get("exclu"))
        elif module.get("exerce") is False:
            etat, message = "non_exerce", "module source jamais importé par la suite"
        else:
            etat, message = "exerce", "module source importé par la suite"
        poser("back", _element(f"module:{nom}", etat, message=message, mute=module.get("mute")))

    _rattacher_porteurs(par_pan)
    return {
        pan: sorted(elements.values(), key=lambda e: e["id"])
        for pan, elements in par_pan.items()
    }


# RT-12 (lot bourse-aux-vacants 20260814a) : le constat qui EXPLIQUE un élément vit souvent sur
# la route qui le porte, deux sous-chapitres plus loin. Sur `qualif:effet:/:0:form`, la cellule
# affichait « formulaire sans action ni écouteur » sans le `401` de `qualif:route:/` qui en est
# la cause — le cahier imprimait les deux, la mise en écran perdait le lien. On rattache donc le
# constat porteur À LA SOURCE : dashboard et cahiers le lisent au même endroit.
_PORTE_PAR_ROUTE = re.compile(r"^qualif:(?:effet|console|marqueur|a11y|visuel):(?P<route>[^:]*)")
_EST_UNE_ROUTE = re.compile(r"^qualif:route:(?P<route>.+)$")


def _rattacher_porteurs(par_pan: dict[str, dict[str, dict]]) -> None:
    porteurs: dict[str, dict] = {}
    for elements in par_pan.values():
        for element in elements.values():
            trouve = _EST_UNE_ROUTE.match(element["id"])
            if trouve and element.get("message"):
                porteurs[trouve["route"]] = element
    for elements in par_pan.values():
        for element in elements.values():
            trouve = _PORTE_PAR_ROUTE.match(element["id"])
            if not trouve:
                continue
            porteur = porteurs.get(trouve["route"] or "/")
            if porteur is None or porteur["id"] == element["id"]:
                continue
            element["porteur"] = {
                "id": porteur["id"],
                "route": trouve["route"] or "/",
                "classe": porteur.get("classe"),
                "message": porteur.get("message"),
            }


def repartir(rapport: dict, registre: dict) -> list[dict]:
    """Chapitres dérivés, garnis de leurs sous-chapitres et de leurs éléments.

    Un chapitre dont AUCUN pan n a été mesuré n est pas retiré : il sort grisé, avec le motif
    et le chemin de couverture du rapport. Un chapitre absent laisserait croire que le sujet
    n existe pas dans le produit.
    """
    elements_par_pan = inventaire(rapport)
    non_couverts = {
        str(e.get("pan")): e
        for e in (rapport.get("pans_non_couverts") or [])
        if isinstance(e, dict)
    }
    sortie: list[dict] = []
    for chapitre in chapitres(registre):
        groupes: dict[str, list[dict]] = {}
        rattaches = 0
        total = 0
        for pan in chapitre["pans"]:
            for element in elements_par_pan.get(pan, []):
                libelle, derive = sous_chapitre(chapitre["decoupe"], element["id"])
                groupes.setdefault(libelle, []).append({**element, "pan": pan})
                rattaches += derive
                total += 1
        manquants = [non_couverts[p] for p in chapitre["pans"] if p in non_couverts]
        sortie.append(
            {
                **chapitre,
                "sous_chapitres": [
                    {"libelle": libelle, "elements": sorted(elements, key=lambda e: e["id"])}
                    for libelle, elements in sorted(groupes.items())
                ],
                "pans_non_couverts": manquants,
                "elements": total,
                "rattaches": rattaches,
                # Grisé = mesuré par personne. Ce n est pas « rien à dire », c est « rien mesuré ».
                "grise": total == 0,
            }
        )
    return sortie
