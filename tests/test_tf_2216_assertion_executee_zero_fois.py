"""TF-2216 — un test de bout en bout vert sans avoir rien vérifié.

Fait remonté (Produit-86, lot du 05/11/2026, RP-36) : deux tests verts ne prouvaient pas
l'approbation qu'ils annonçaient. Une boucle d'approbation filtrait sur un bouton caché et tournait
sur ZÉRO carte ; une attente cherchait un libellé jamais servi et expirait en silence. Mesure du
porteur : 0 action approuvée par tour, deux tests verts.

Décision du 06/11/2026 : une règle refuse une boucle d'assertions exécutée zéro fois et une attente
bornée terminée sans sa condition.

Deux règles de la revue de suite (`forge_tests.revue`), chacune en sens rouge et en sens vert :
  - `boucle_sans_iteration_prouvee` — une boucle qui porte une assertion, sur une collection dont
    rien ne prouve qu'elle n'est pas vide : la boucle peut tourner zéro fois et le test passe ;
  - `attente_sans_echec` — une attente bornée (`waitFor…`, `expect.poll`, `expect(...).toBeVisible`)
    dont l'expiration est avalée (`.catch(() => {})`, `try { … } catch {}`) : le test continue
    comme si la condition était remplie.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import classes, revue

CLASSE = "assertion-de-test-executee-zero-fois"


def _spec(racine: Path, corps: str, nom: str = "e2e/approbation.spec.ts") -> None:
    chemin = racine / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test('approuver toutes les cartes', async ({ page }) => {\n" + corps + "});\n",
        encoding="utf-8",
    )


def test_la_classe_est_declaree_au_module_des_classes() -> None:
    assert classes.ASSERTION_EXECUTEE_ZERO_FOIS == CLASSE
    assert CLASSE in classes.CLASSES


# --- Boucle exécutée zéro fois -------------------------------------------------------------------
def test_rouge_une_boucle_sur_une_collection_peut_ne_jamais_tourner(tmp_path: Path) -> None:
    """Le cas du lot : la boucle d'approbation tourne sur les cartes dont le bouton est visible ;
    le bouton est caché, la collection est vide, les assertions ne s'exécutent jamais."""
    _spec(
        tmp_path,
        "  await page.goto('/');\n"
        "  const cartes = await page.locator('.carte:has(button:visible)').all();\n"
        "  for (const carte of cartes) {\n"
        "    await carte.getByRole('button', { name: 'Approuver' }).click();\n"
        "    await expect(carte).toBeHidden();\n"
        "  }\n",
    )
    constats = revue.boucle_sans_iteration_prouvee(tmp_path)
    assert len(constats) == 1, [c.id for c in constats]
    assert constats[0].classe == CLASSE and constats[0].severite == "bloquant"
    assert "ZÉRO fois" in constats[0].message
    assert "approbation.spec.ts" in constats[0].localisation


def test_rouge_les_formes_de_boucle_reconnues(tmp_path: Path) -> None:
    formes = {
        "for_of_inline": (
            "  for (const c of await page.locator('.carte').all()) {\n"
            "    await expect(c).toBeVisible();\n  }\n"
        ),
        "for_classique": (
            "  const n = await page.locator('.carte').count();\n"
            "  for (let i = 0; i < n; i++) {\n"
            "    await expect(page.locator('.carte').nth(i)).toBeVisible();\n  }\n"
        ),
        "for_each": (
            "  const cartes = await page.locator('.carte').all();\n"
            "  cartes.forEach(async (c) => {\n"
            "    await expect(c).toBeVisible();\n  });\n"
        ),
    }
    for nom, corps in formes.items():
        _spec(tmp_path / nom, corps)
        assert len(revue.boucle_sans_iteration_prouvee(tmp_path / nom)) == 1, nom


def test_vert_une_assertion_de_non_vacuite_acquitte_la_boucle(tmp_path: Path) -> None:
    """Le remède que le message propose, JOUÉ : prouver que la collection n'est pas vide."""
    _spec(
        tmp_path,
        "  const cartes = await page.locator('.carte').all();\n"
        "  expect(cartes.length).toBeGreaterThan(0);\n"
        "  for (const carte of cartes) {\n"
        "    await expect(carte).toBeVisible();\n"
        "  }\n",
    )
    assert revue.boucle_sans_iteration_prouvee(tmp_path) == []


def test_vert_les_autres_formes_de_non_vacuite(tmp_path: Path) -> None:
    preuves = (
        "await expect(page.locator('.carte')).toHaveCount(3);",
        "await expect(page.locator('.carte')).not.toHaveCount(0);",
        "expect(await page.locator('.carte').count()).toBeGreaterThanOrEqual(1);",
    )
    for rang, preuve in enumerate(preuves):
        _spec(
            tmp_path / str(rang),
            f"  {preuve}\n"
            "  for (const c of await page.locator('.carte').all()) {\n"
            "    await expect(c).toBeVisible();\n  }\n",
        )
        assert revue.boucle_sans_iteration_prouvee(tmp_path / str(rang)) == [], preuve


def test_vert_un_compteur_d_iterations_verifie_apres_la_boucle_acquitte(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  let approuvees = 0;\n"
        "  for (const c of await page.locator('.carte').all()) {\n"
        "    await expect(c).toBeVisible();\n    approuvees += 1;\n  }\n"
        "  expect(approuvees).toBeGreaterThan(0);\n",
    )
    assert revue.boucle_sans_iteration_prouvee(tmp_path) == []


def test_vert_une_boucle_sans_assertion_n_est_pas_visee(tmp_path: Path) -> None:
    """La règle vise une assertion jamais exécutée ; une boucle d'accumulation n'en porte pas."""
    _spec(
        tmp_path,
        "  const noms = [];\n"
        "  for (const c of await page.locator('.carte').all()) {\n"
        "    noms.push(await c.textContent());\n  }\n",
    )
    assert revue.boucle_sans_iteration_prouvee(tmp_path) == []


# --- Attente expirée sans échec ------------------------------------------------
def test_rouge_une_attente_qui_expire_sans_echouer(tmp_path: Path) -> None:
    """Le second cas du lot : l'attente cherche un libellé jamais servi et expire."""
    _spec(
        tmp_path,
        "  await page.goto('/');\n"
        "  await page.getByText('Demandes approuvées').waitFor({ timeout: 5000 })"
        ".catch(() => {});\n"
        "  await expect(page.locator('body')).toBeVisible();\n",
    )
    constats = revue.attente_sans_echec(tmp_path)
    assert len(constats) == 1, [c.id for c in constats]
    assert constats[0].classe == CLASSE and constats[0].severite == "bloquant"
    assert "SANS sa condition" in constats[0].message


def test_rouge_les_formes_d_attente_avalee_reconnues(tmp_path: Path) -> None:
    formes = {
        "catch_nul": "  await page.waitForSelector('.ok', { timeout: 3000 }).catch(() => null);\n",
        "catch_faux": "  await page.waitForURL('**/fin').catch(() => false);\n",
        "catch_vide_nomme": "  await page.waitForResponse('**/api').catch((e) => {});\n",
        "catch_commentaire": (
            "  await page.waitForSelector('.ok').catch(() => {\n    // tant pis\n  });\n"
        ),
        "expect_catch": (
            "  await expect(page.getByText('Fini')).toBeVisible({ timeout: 2000 })"
            ".catch(() => {});\n"
        ),
        "try_catch_vide": (
            "  try {\n    await page.waitForSelector('.ok', { timeout: 3000 });\n"
            "  } catch (e) {\n  }\n"
        ),
        "try_catch_sans_nom": (
            "  try {\n    await page.getByText('x').waitFor();\n  } catch {\n    // rien\n  }\n"
        ),
        "try_catch_journal": (
            "  try {\n    await page.getByText('x').waitFor();\n"
            "  } catch (e) {\n    console.log('attente expirée');\n  }\n"
        ),
    }
    for nom, corps in formes.items():
        _spec(tmp_path / nom, corps)
        assert len(revue.attente_sans_echec(tmp_path / nom)) == 1, nom


def test_vert_une_attente_dont_l_expiration_fait_echouer(tmp_path: Path) -> None:
    """Le remède joué : l'attente nue échoue d'elle-même ; le `catch` qui relance est licite."""
    _spec(
        tmp_path,
        "  await page.getByText('Demandes approuvées').waitFor({ timeout: 5000 });\n"
        "  try {\n    await page.waitForSelector('.ok');\n"
        "  } catch (e) {\n    throw new Error(`condition jamais remplie : ${e}`);\n  }\n",
    )
    assert revue.attente_sans_echec(tmp_path) == []


def test_vert_un_catch_qui_avale_autre_chose_qu_une_attente_n_est_pas_vise(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  await page.screenshot({ path: 'a.png' }).catch(() => {});\n"
        "  try {\n    await page.evaluate(() => window.scrollTo(0, 0));\n"
        "  } catch (e) {\n  }\n",
    )
    assert revue.attente_sans_echec(tmp_path) == []


# --- Les exemptions déclarées par la règle elle-même ----------------------------
def test_vert_une_boucle_declaree_possiblement_vide_est_exemptee(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  // forge-tests: boucle-possiblement-vide — les cartes n'existent qu'après un import\n"
        "  for (const c of await page.locator('.carte').all()) {\n"
        "    await expect(c).toBeVisible();\n  }\n",
    )
    assert revue.boucle_sans_iteration_prouvee(tmp_path) == []


def test_vert_une_attente_declaree_optionnelle_est_exemptee(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  // forge-tests: attente-optionnelle — le bandeau de cookies n'apparait qu'une fois\n"
        "  await page.getByText('Accepter').waitFor({ timeout: 1000 }).catch(() => {});\n",
    )
    assert revue.attente_sans_echec(tmp_path) == []


def test_rouge_l_exemption_d_une_boucle_ne_couvre_pas_la_boucle_suivante(tmp_path: Path) -> None:
    _spec(
        tmp_path,
        "  // forge-tests: boucle-possiblement-vide — motif\n"
        "  for (const c of await page.locator('.a').all()) {\n"
        "    await expect(c).toBeVisible();\n  }\n\n\n"
        "  for (const c of await page.locator('.b').all()) {\n"
        "    await expect(c).toBeVisible();\n  }\n",
    )
    assert len(revue.boucle_sans_iteration_prouvee(tmp_path)) == 1


# --- Branchement et bancs -------------------------------------------------------
def test_les_deux_regles_sont_jouees_par_analyser_suite(tmp_path: Path) -> None:
    """Une règle que le point d'entrée n'appelle pas n'existe pas (loi n° 1)."""
    _spec(
        tmp_path,
        "  for (const c of await page.locator('.carte').all()) {\n"
        "    await expect(c).toBeVisible();\n  }\n"
        "  await page.waitForSelector('.ok').catch(() => {});\n",
    )
    ids = [f.id for f in revue.analyser_suite(tmp_path)]
    assert any(i.startswith("revue:boucle-sans-iteration:") for i in ids), ids
    assert any(i.startswith("revue:attente-sans-echec:") for i in ids), ids


def test_les_bancs_de_la_forge_ne_rendent_AUCUN_constat() -> None:
    """Mesure d'entrée sur le corpus réel : un constat sur les bancs serait un faux positif."""
    racine = Path(__file__).resolve().parent.parent
    for banc in ("fixtures/banc-vert", "fixtures/banc-rouge"):
        for regle in (revue.boucle_sans_iteration_prouvee, revue.attente_sans_echec):
            constats = regle(racine / banc)
            assert constats == [], f"{banc} : {[c.localisation for c in constats]}"
