"""Confronter une PROMESSE à un SERVICE — le mécanisme, une seule fois.

TF-0371 (lot Produit-11 20260818a, 18/08/2026), et c'est l'item lui-même qui a nommé
le vrai sujet : « c'est la TROISIÈME généralisation demandée du même comparateur — il y a
probablement un mécanisme unique à en tirer plutôt que trois ».

Trois paires de termes, une seule forme de raisonnement :

| # | Ce que quelque chose PROMET | Ce qui est SERVI | Né de |
|---|---|---|---|
| 1 | les entrées de menu d'un composant | le menu du build servi | TF-0288, TF-0312, TF-0333 |
| 2 | les routes que le code client APPELLE | les routes que l'hôte ENREGISTRE | TF-0371 (a) |
| 3 | les ressources qu'une feuille RÉFÉRENCE | les fichiers présents au build | TF-0371 (b) |

**Les trois propriétés qui font la valeur du comparateur**, écrites ici une fois au lieu d'être
réinventées à chaque paire :

1. **Trois issues, jamais une quatrième.** SKIP quand un terme manque — et le motif DIT lequel,
   parce que « pas de source » et « pas de servi » ne se réparent pas de la même façon. FAIL
   quand une promesse n'est pas servie, **les manquantes NOMMÉES**. PASS sinon.
2. **L'asymétrie est voulue.** Une chose SERVIE que rien ne promet n'est pas jugée : elle peut
   venir d'un terme que le lecteur ne sait pas lire. L'accuser serait accuser la limite du
   lecteur — c'est la faute que TF-0312 a payée une fois (trois entrées « manquantes » sur un
   servi qui les rendait toutes).
3. **Un total anonyme n'est pas un constat.** Ce qui manque se lit élément par élément, sinon
   on ne sait pas si l'écart est un défaut de déploiement ou de code — la distinction qui a
   fondé TF-0288.

Ce module ne lit rien : il ne sait ni ce qu'est une route, ni ce qu'est une feuille de style.
Les deux termes lui sont donnés déjà lus. C'est ce qui lui permet de servir les trois paires
sans savoir laquelle il sert.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Terme:
    """Un côté de la confrontation, avec de quoi expliquer son absence.

    `elements` vide ne veut pas dire « rien à dire » : ça veut dire que ce terme n'a pas pu
    être lu, et `motif_absence` est alors la seule chose utile qu'on puisse rendre.
    """

    nom: str
    elements: set[str] = field(default_factory=set)
    motif_absence: str = ""
    #: Ce qui a été LU pour constituer ce terme — publié au motif. Sans ça, un PASS ne dit pas
    #: sur quoi il porte, et un PASS qui ne dit pas ce qu'il a regardé est un PASS de confiance.
    sources: list[str] = field(default_factory=list)


def confronter(
    domaine: str,
    promesse: Terme,
    service: Terme,
    *,
    suspendus: dict[str, str] | None = None,
) -> dict:
    """Confronte ce que `promesse` annonce à ce que `service` rend. Trois issues, pas quatre.

    `suspendus` : éléments dont le jugement est SUSPENDU, avec leur motif — ni promis ni servi
    de façon déterminable. Ils sortent du calcul ET sont dits, parce qu'un jugement suspendu en
    silence est indiscernable d'un jugement rendu (patron TF-0312, levée 4).
    """
    suspendus = suspendus or {}
    lisible = f"{domaine} : "

    if not promesse.elements and promesse.motif_absence:
        return {
            "domaine": domaine, "verdict": "SKIP", "manquantes": [], "comparees": 0,
            "suspendus": suspendus,
            "motif": lisible + f"terme « {promesse.nom} » ILLISIBLE — {promesse.motif_absence}. "
                     "Sans promesse opposable, la comparaison n'a pas d'objet",
        }
    if not service.elements and service.motif_absence:
        return {
            "domaine": domaine, "verdict": "SKIP", "manquantes": [], "comparees": 0,
            "suspendus": suspendus,
            "motif": lisible + f"terme « {service.nom} » ILLISIBLE — {service.motif_absence}. "
                     f"La promesse est lue ({len(promesse.elements)} élément(s) dans "
                     f"{', '.join(promesse.sources) or 'sources non nommées'}) mais rien ne lui "
                     "est opposé",
        }

    attendues = set(promesse.elements) - set(suspendus)
    manquantes = sorted(attendues - set(service.elements))
    rappel_suspension = (
        "" if not suspendus
        else f" — jugement SUSPENDU sur {len(suspendus)} élément(s) : "
             + " · ".join(f"« {e} » ({m})" for e, m in sorted(suspendus.items()))
    )

    if not attendues:
        return {
            "domaine": domaine, "verdict": "SKIP", "manquantes": [], "comparees": 0,
            "suspendus": suspendus,
            "motif": lisible + "AUCUN élément comparable après suspension — un PASS ici dirait "
                     "« tout ce qui est promis est servi » sans avoir rien confronté"
                     + rappel_suspension,
        }

    detail = (
        f"{len(attendues)} élément(s) promis par « {promesse.nom} » "
        f"({', '.join(promesse.sources) or 'sources non nommées'}) confrontés à "
        f"{len(service.elements)} servi(s) par « {service.nom} »"
        f"{' (' + ', '.join(service.sources) + ')' if service.sources else ''}"
    )
    if manquantes:
        return {
            "domaine": domaine, "verdict": "FAIL", "manquantes": manquantes,
            "comparees": len(attendues), "suspendus": suspendus,
            "motif": lisible + detail + f" — {len(manquantes)} PROMIS ET NON SERVI(S) : "
                     + ", ".join(f"« {e} »" for e in manquantes) + rappel_suspension,
        }
    return {
        "domaine": domaine, "verdict": "PASS", "manquantes": [],
        "comparees": len(attendues), "suspendus": suspendus,
        "motif": lisible + detail + " — chaque promesse est servie" + rappel_suspension,
    }


#: Ce que le mécanisme ne juge pas, quelle que soit la paire — déclaré ici plutôt que répété.
NON_JUGE = [
    "confrontation : le sens est ASYMÉTRIQUE — ce qui est SERVI sans être promis n est jamais "
    "accusé ; il peut venir d un terme que le lecteur ne sait pas lire, et l accuser serait "
    "accuser la limite du lecteur (faute payée une fois, TF-0312)",
    "confrontation : la LECTURE des deux termes n est pas jugée ici — ce module reçoit deux "
    "ensembles déjà constitués. Un lecteur qui manque des éléments produit une promesse plus "
    "courte, donc un PASS plus faible, et c est au lecteur de déclarer sa portée",
]
