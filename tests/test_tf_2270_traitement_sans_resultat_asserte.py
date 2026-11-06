"""TF-2270 — un parcours de bout en bout qui attend la fin d'un traitement sans rien affirmer de son
résultat.

Fait remonté (Produit-86, lot 20261106a, RP-43) : 34 parcours, 0 assertion sur le contenu d'un
constat. Seul l'état SUCCEEDED du traitement était jugé : un traitement qui se termine en rendant un
résultat faux, vide ou périmé passait. La vérité du lab avait été relevée à la main par une sonde.

Décision du 06/11/2026 : un parcours qui attend la fin d'un traitement sans assertion sur son
résultat est relevé, et la règle exige une vérité de référence avec sa contre-épreuve.

Règle (piège 12 de la revue de suite) en sens rouge et en sens vert :
  - ROUGE  — attente d'un état terminal (`SUCCEEDED`, `Terminé`…) et aucune assertion de VALEUR
             (contenu, compte, égalité) ailleurs dans le test ;
  - VERT   — la même attente suivie d'une assertion sur le contenu produit ; un test qui n'attend
             aucun traitement ; l'exemption déclarée `forge-tests: etat-seul — <motif>` ;
  - le message exige la vérité de référence ET sa contre-épreuve.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import actions, classes, revue

CLASSE = "traitement-attendu-sans-resultat-assert"


def _spec(racine: Path, corps: str, nom: str = "e2e/analyse.spec.ts") -> None:
    chemin = racine / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test('lancer une analyse', async ({ page }) => {\n" + corps + "});\n",
        encoding="utf-8",
    )


def test_la_classe_est_declaree_et_classee() -> None:
    assert classes.TRAITEMENT_SANS_RESULTAT_ASSERTE == CLASSE
    assert CLASSE in classes.CLASSES
    assert CLASSE in actions._REGLES


def test_rouge_l_etat_succeeded_attendu_sans_rien_affirmer_du_resultat(tmp_path: Path) -> None:
    """Le cas du lot : le parcours lance l'analyse, attend SUCCEEDED, et s'arrête là."""
    _spec(
        tmp_path,
        "  await page.goto('/analyses');\n"
        "  await page.getByRole('button', { name: 'Lancer' }).click();\n"
        "  await expect(page.getByTestId('statut')).toHaveText('SUCCEEDED', { timeout: 60000 });\n",
    )
    constats = revue.traitement_sans_resultat_asserte(tmp_path)
    assert len(constats) == 1, [c.id for c in constats]
    unique = constats[0]
    assert unique.classe == CLASSE and unique.severite == "bloquant"
    assert "analyse.spec.ts" in unique.localisation
    assert "vérité de référence" in unique.message
    assert "contre-épreuve" in unique.message


def test_rouge_une_attente_par_sondage_de_l_etat_termine(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  await page.goto('/analyses');\n"
        "  await expect.poll(async () => (await api.get('/job/1')).status, "
        "{ timeout: 30000 }).toBe('COMPLETED');\n",
    )
    assert len(revue.traitement_sans_resultat_asserte(tmp_path)) == 1


def test_rouge_l_etat_en_francais_et_une_simple_visibilite_ne_prouvent_pas_le_resultat(
    tmp_path: Path,
) -> None:
    _spec(
        tmp_path,
        "  await page.getByRole('button', { name: 'Lancer' }).click();\n"
        "  await expect(page.getByText('Terminé')).toBeVisible({ timeout: 60000 });\n"
        "  await expect(page.getByRole('heading', { name: 'Résultats' })).toBeVisible();\n",
    )
    assert len(revue.traitement_sans_resultat_asserte(tmp_path)) == 1


def test_vert_une_assertion_sur_le_contenu_du_resultat_acquitte_le_test(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  await page.getByRole('button', { name: 'Lancer' }).click();\n"
        "  await expect(page.getByTestId('statut')).toHaveText('SUCCEEDED');\n"
        "  const constats = await page.getByTestId('constat').allTextContents();\n"
        "  expect(constats).toEqual(['XSS reflété sur /recherche', 'En-tête CSP absent']);\n",
    )
    assert revue.traitement_sans_resultat_asserte(tmp_path) == []


def test_vert_un_compte_attendu_acquitte_aussi(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  await expect(page.getByText('Terminé')).toBeVisible();\n"
        "  await expect(page.getByTestId('constat')).toHaveCount(2);\n",
    )
    assert revue.traitement_sans_resultat_asserte(tmp_path) == []


def test_vert_un_test_qui_n_attend_aucun_traitement_n_est_pas_vise(tmp_path: Path) -> None:
    """Contre-épreuve de la règle : ni état terminal, ni traitement, ni constat."""
    _spec(
        tmp_path,
        "  await page.goto('/aide');\n"
        "  await expect(page.getByRole('heading', { name: 'Aide' })).toBeVisible();\n",
    )
    assert revue.traitement_sans_resultat_asserte(tmp_path) == []


def test_vert_l_exemption_declaree_avec_son_motif_est_respectee(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  // forge-tests: etat-seul — test de fumée du lanceur, contenu jugé par analyse-2\n"
        "  await expect(page.getByTestId('statut')).toHaveText('SUCCEEDED');\n",
    )
    assert revue.traitement_sans_resultat_asserte(tmp_path) == []


def test_la_regle_est_dans_l_analyse_de_la_suite(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  await expect(page.getByTestId('statut')).toHaveText('SUCCEEDED');\n",
    )
    ids = [f.id for f in revue.analyser_suite(tmp_path)]
    assert any(i.startswith("revue:traitement-sans-resultat:") for i in ids), ids


def test_la_limite_est_declaree_au_non_juge() -> None:
    texte = " ".join(revue.NON_JUGE)
    assert "piege 12" in texte and "TF-2270" in texte
