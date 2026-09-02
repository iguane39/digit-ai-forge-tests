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

    Un rapport SANS AUCUN cas est REFUSÉ (TF-0605) : un exécuteur qui ne collecte rien n est pas
    un succès, c est une mesure absente — et une liste vide se lirait « aucun défaut ».

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

    # TF-0605 (lot Produit-01 20260824d) — UN EXECUTEUR QUI NE COLLECTE RIEN N EST PAS UN SUCCES.
    # Le fait : `npx playwright test` a rendu « No tests found » avec un CODE DE SORTIE 0, sur un
    # conflit de motif entre deux executeurs. Une suite ENTIERE etait absente, et la chaine l a
    # rapportee comme un succes. C est le defaut le plus silencieux de toute la famille des faux
    # verts : il ne casse rien, il ne signale rien, et il fait disparaitre la mesure elle-meme.
    #
    # Le refus est ici et pas ailleurs parce que c est ici qu on SAIT : un rapport JUnit sans un
    # seul `<testcase>` est un rapport dont personne ne peut rien conclure. Rendre une liste vide
    # le ferait passer pour « aucun defaut », exactement comme le code de sortie 0. Meme choix que
    # pour le XML illisible, deux lignes plus haut — refus, jamais une liste vide.
    cas = list(racine.iter("testcase"))
    if not cas:
        raise JunitIllisible(
            "rapport JUnit sans AUCUN cas — un executeur qui ne collecte rien n est pas un succes, "
            "c est une mesure absente. Verifier le motif de selection des tests et la racine "
            "d execution (cas reel : « No tests found » rendu avec un code de sortie 0, une suite "
            "entiere disparue sans que rien ne le dise)"
        )

    essais: list[Essai] = []
    for noeud in cas:
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
