"""TF-0590 — les tests qui ne s'exécutent pas, et que le reporting rend invisibles.

Lot Approval2 20260824d. Quatre occurrences distinctes sur un même produit, toutes vertes :
trois tests d'intégration silencieusement ignorés en intégration continue PENDANT DES MOIS —
dont un écrit *parce qu'une régression réelle était déjà passée* ; un saut conditionnel dans la
recette d'accessibilité rapporté « 27 passés, 1 sauté » sans que personne regarde lequel ; un
exécuteur rendant « No tests found » avec un CODE DE SORTIE 0, c'est-à-dire une suite entière
absente rapportée comme un succès ; et un rapport qui n'énumérait aucun périmètre non couvert.

La distinction porte toute la règle et sans elle elle serait fausse : un saut INCONDITIONNEL et
motivé est une décision lisible. Un saut CONDITIONNEL peut cesser de tester sans que rien ne
change dans le fichier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import revue
from forge_tests.junit import JunitIllisible, depuis_junit


def _fichier(racine: Path, nom: str, corps: str) -> Path:
    chemin = racine / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(corps, encoding="utf-8")
    return chemin


# --- Le saut conditionnel, dans les deux sens ---------------------------------------------------
def test_un_skipif_Python_est_denonce(tmp_path: Path) -> None:
    """La forme exacte du cas fondateur : trois tests d'intégration disparus pendant des mois."""
    _fichier(
        tmp_path, "tests/test_integration.py",
        "import pytest\n\n"
        '@pytest.mark.skipif(not AZURITE.exists(), reason="azurite absent")\n'
        "def test_depot_de_document():\n    pass\n",
    )

    findings = revue.saut_conditionnel(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert findings[0].classe == "saut-conditionnel-en-integration-continue"
    assert "MENT sur la couverture" in findings[0].message
    assert ":3" in findings[0].localisation, "le constat ne dit pas SUR QUELLE LIGNE il porte"


def test_un_skip_INCONDITIONNEL_et_motive_reste_licite(tmp_path: Path) -> None:
    """La nuance sans laquelle la règle serait fausse — et se ferait désactiver.

    Un saut assumé est une décision que quelqu'un a écrite, avec son motif. La condamner
    reviendrait à interdire de déclarer, ce qui pousse à taire plutôt qu'à dire.
    """
    _fichier(
        tmp_path, "tests/test_differe.py",
        "import pytest\n\n"
        '@pytest.mark.skip(reason="attend la bascule du fournisseur, ticket AP-412")\n'
        "def test_futur():\n    pass\n",
    )

    assert revue.saut_conditionnel(tmp_path) == []


def test_un_test_skip_conditionnel_de_navigateur_est_denonce(tmp_path: Path) -> None:
    """La seconde forme du cas réel : le garde qui ne se déclenchait jamais, dans la recette
    d'accessibilité — et le test qui, du coup, ne testait rien."""
    _fichier(
        tmp_path, "frontend/tests/e2e/10-a11y.spec.ts",
        "import { test, expect } from '@playwright/test';\n\n"
        "test('ecran de decision accessible', async ({ page }) => {\n"
        "  test.skip(approbations === 0, 'aucune approbation en attente');\n"
        "  await expect(page.getByRole('main')).toBeVisible();\n"
        "});\n",
    )

    findings = revue.saut_conditionnel(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]


def test_un_test_skip_NU_de_navigateur_reste_licite(tmp_path: Path) -> None:
    _fichier(
        tmp_path, "frontend/tests/e2e/10-a11y.spec.ts",
        "import { test } from '@playwright/test';\n\n"
        "test('a rediger', async ({ page }) => {\n  test.skip();\n});\n",
    )

    assert revue.saut_conditionnel(tmp_path) == []


def test_la_regle_est_jouee_par_analyser_suite(tmp_path: Path) -> None:
    """Une règle que le point d'entrée n'appelle pas n'existe pas (loi n° 1)."""
    _fichier(
        tmp_path, "tests/test_integration.py",
        "import pytest\n\n@pytest.mark.skipif(CONDITION, reason='x')\ndef test_a():\n    pass\n",
    )

    classes_vues = {f.classe for f in revue.analyser_suite(tmp_path)}

    assert "saut-conditionnel-en-integration-continue" in classes_vues


def test_les_bancs_de_la_forge_ne_rendent_AUCUN_constat() -> None:
    """Mesure d'entrée sur le corpus RÉEL, avant la livraison (leçon N-23 du pilot).

    Ce qu'une liste attrape à tort se lit avant ce qu'elle attrape à raison. Les deux bancs sont
    le corpus de référence : un constat ici serait un faux positif par construction.
    """
    racine = Path(__file__).resolve().parent.parent
    for banc in ("fixtures/banc-vert", "fixtures/banc-rouge"):
        findings = revue.saut_conditionnel(racine / banc)
        assert findings == [], f"{banc} : {[f.localisation for f in findings]}"


# --- L'exécuteur qui ne collecte rien -----------------------------------------------------------
def test_un_rapport_JUnit_SANS_AUCUN_CAS_est_refuse() -> None:
    """« No tests found » avec un code de sortie 0 : une suite entière absente, rapportée comme
    un succès. C'est le défaut le plus silencieux de la famille — il ne casse rien.

    Le refus est ici parce que c'est ici qu'on SAIT : rendre une liste vide se lirait « aucun
    défaut », exactement comme le code de sortie 0.
    """
    with pytest.raises(JunitIllisible) as capture:
        depuis_junit(
            '<testsuites><testsuite name="e2e" tests="0"></testsuite></testsuites>', "front"
        )

    assert "ne collecte rien" in str(capture.value)
    assert "succes" in str(capture.value), "le refus ne dit pas pourquoi zéro n'est pas un succès"


def test_un_rapport_JUnit_avec_des_cas_reste_lu_normalement() -> None:
    """Le second sens : le refus neuf ne mange pas le chemin nominal."""
    essais = depuis_junit(
        '<testsuite><testcase classname="a" name="b"/>'
        '<testcase classname="a" name="c"><skipped message="hors poste"/></testcase></testsuite>',
        "front",
    )

    assert [e.verdict for e in essais] == ["passant", "non_execute"]
    assert essais[1].pourquoi == "hors poste", (
        "le motif du saut n'est pas repris tel quel — un rapport qui ne dit pas POURQUOI un cas "
        "n'a pas tourné laisse croire qu'il a tourné"
    )
