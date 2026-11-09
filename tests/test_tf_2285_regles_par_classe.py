"""TF-2285 — chaque classe de constat déclarée porte une règle d'action.

Fait remonté (campagne du 06/11/2026) : `forge_tests/actions.py` (`_REGLES`) couvrait 24 classes sur
52 ; les 28 autres (faux-vert-*, saut-conditionnel-en-integration-continue,
assertion-de-test-executee-zero-fois, rls-absente…) sortaient « DÉFAUT D'AUDITEUR » : un constat
mesuré, adressé à la forge elle-même, alors que son destinataire réel est connu. Mesure du
09/11/2026 : 52 classes, 24 règles, 28 sans règle, 0 règle sans classe.

La branche « défaut d'auditeur » reste le filet des classes que personne n'a prévues. Elle n'est
plus le sort des classes déclarées : ce test compare les deux ensembles et devient rouge à la
première classe ajoutée à `classes.py` sans sa règle (la rouge d'origine : 28 classes manquantes).
"""

from __future__ import annotations

import pytest

from forge_tests import actions, classes
from forge_tests.actions import CATEGORIES, ETAPES, classifier


def _finding(classe: str) -> dict:
    return {
        "classe": classe,
        "id": "element-x",
        "pan": "pan-x",
        "message": "constat mesuré",
    }


def test_chaque_classe_declaree_a_une_regle_d_action() -> None:
    """Rouge dès qu'une classe de `classes.CLASSES` n'est pas dans `_REGLES`. Le message nomme
    les classes, pas leur nombre : c'est la liste qui dit quoi écrire."""
    sans_regle = sorted(classes.CLASSES - set(actions._REGLES))

    assert not sans_regle, (
        f"{len(sans_regle)} classe(s) sur {len(classes.CLASSES)} sans règle dans "
        f"actions._REGLES : {', '.join(sans_regle)}"
    )


def test_aucune_regle_ne_vise_une_classe_qui_n_existe_pas() -> None:
    """Sens inverse : une règle dont la classe a été renommée ou retirée ne sert plus personne."""
    orphelines = sorted(set(actions._REGLES) - classes.CLASSES)

    assert not orphelines, f"règle(s) sans classe déclarée dans classes.py : {orphelines}"


@pytest.mark.parametrize("classe", sorted(classes.CLASSES))
def test_aucune_classe_declaree_ne_sort_un_defaut_d_auditeur(classe: str) -> None:
    """Vu de la sortie : l'action d'un constat de cette classe a un destinataire et une étape du
    vocabulaire, et ne dit pas « DÉFAUT D'AUDITEUR »."""
    action = classifier([_finding(classe)])[0]

    assert "DÉFAUT D'AUDITEUR" not in action["attendu"]
    assert action["categorie"] in CATEGORIES
    assert action["etape_cible"] in ETAPES
    assert "element-x" in action["attendu"] or "constat mesuré" in action["attendu"], (
        "l'attendu doit citer l'élément ou le constat, pas une consigne générique"
    )


def test_le_filet_reste_pour_une_classe_que_personne_n_a_prevue() -> None:
    """Contre-épreuve : le test ne retire pas le filet. Une classe hors `classes.py` sort encore
    un défaut d'auditeur nommé, adressé à l'étape `forge`."""
    action = classifier([_finding("classe-inventee-demain")])[0]

    assert action["etape_cible"] == "forge"
    assert "DÉFAUT D'AUDITEUR" in action["attendu"]


def test_la_comparaison_devient_rouge_si_une_classe_est_declaree_sans_regle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le test lui-même est prouvé : une classe nouvelle dans l'ensemble déclaré, sans règle,
    rend la comparaison rouge et nomme la classe."""
    monkeypatch.setattr(classes, "CLASSES", classes.CLASSES | {"classe-nouvelle-sans-regle"})

    with pytest.raises(AssertionError, match="classe-nouvelle-sans-regle"):
        test_chaque_classe_declaree_a_une_regle_d_action()
