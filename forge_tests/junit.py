"""Lecteur JUnit XML — traduit la sortie native de pytest en `noyau.Essai`, ligne à ligne.

TF-0146 : le rapport exhaustif test-par-test exige un verdict PASSANT / NON-PASSANT /
NON-EXÉCUTÉ, motivé, pour CHAQUE cas exécuté. `pytest --junitxml=...` est la source qui fait
foi côté Python — native, sans plugin tiers (contrairement à `--report-log`) — et porte déjà
tout ce qu il faut : le nom du cas, et, s il n a pas simplement réussi, l enfant `<failure>`,
`<error>` ou `<skipped>` qui dit pourquoi.

Ce module ne sait qu une chose : lire ce XML. Il ne sait pas comment un adaptateur invoque
pytest, ni comment brancher le résultat sur la mutation ou la couverture (le champ `couvert`
d `Essai` reste `None` ici — c est à l appelant de le renseigner s il dispose du signal). Le
brancher sur `execution.mesurer` (ajouter `--junitxml`, lire le fichier, construire les `Essai`
par pan) est le jalon d intégration réelle, non couvert par cette version : cf. `restes` du
rapport de campagne TF-0146.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from forge_tests.noyau import Essai


class JunitIllisible(RuntimeError):
    """Le texte fourni n est pas un rapport JUnit exploitable — refus, jamais une liste vide."""


def _nom_cas(noeud: ET.Element) -> str:
    classe = noeud.get("classname") or ""
    nom = noeud.get("name") or ""
    return f"{classe}::{nom}" if classe else nom


def _motif(enfant: ET.Element) -> str:
    message = (enfant.get("message") or "").strip()
    texte = (enfant.text or "").strip()
    if message and texte:
        return f"{message} — {texte.splitlines()[0][:200]}"
    return message or (texte.splitlines()[0][:200] if texte else "sans message")


def _essai_non_passant(identifiant: str, pan: str, enfant: ET.Element) -> Essai:
    return Essai(
        id=identifiant, pan=pan, verdict="non_passant",
        pourquoi=_motif(enfant), details=(enfant.text or "").strip() or None,
    )


def depuis_junit(xml_texte: str, pan: str) -> list[Essai]:
    """Un `Essai` par `<testcase>` du rapport JUnit fourni.

    Règle de traduction, dans l ordre : un `<skipped>` -> `non_execute` (le cas n a jamais
    tourné, quelle qu en soit la cause) ; un `<failure>` ou `<error>` -> `non_passant` (le cas a
    tourné et n a pas confirmé ce qu il affirme) ; sinon -> `passant`. Le POURQUOI est TOUJOURS
    extrait de l enfant XML réel, jamais reformulé — un `pourquoi` inventé ici trahirait
    exactement ce que ce module existe pour rapporter fidèlement.
    """
    try:
        racine = ET.fromstring(xml_texte)  # noqa: S314 — texte produit par pytest, pas untrusted
    except ET.ParseError as erreur:
        raise JunitIllisible(f"XML JUnit invalide : {erreur}") from erreur

    essais: list[Essai] = []
    for noeud in racine.iter("testcase"):
        identifiant = _nom_cas(noeud)
        skip = noeud.find("skipped")
        echec = noeud.find("failure")
        en_erreur = noeud.find("error")
        if skip is not None:
            essais.append(
                Essai(id=identifiant, pan=pan, verdict="non_execute", pourquoi=_motif(skip))
            )
        elif echec is not None:
            essais.append(_essai_non_passant(identifiant, pan, echec))
        elif en_erreur is not None:
            essais.append(_essai_non_passant(identifiant, pan, en_erreur))
        else:
            essais.append(Essai(id=identifiant, pan=pan, verdict="passant"))
    return essais
