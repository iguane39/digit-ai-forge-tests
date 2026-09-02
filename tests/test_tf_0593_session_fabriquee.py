"""TF-0593 — la session FABRIQUÉE, et la clé de relecture séparée de sa session.

Lot Produit-01 20260824c. Un produit à identité déléguée ne peut pas authentifier N identités
sans N comptes réels chez son fournisseur ; la solution tentante est d'écrire la session
directement dans le stockage du navigateur. Elle saute le seul mécanisme qui aurait vu l'erreur
— le contrôle d'audience de la bibliothèque cliente, qu'une session désérialisée ne rejoue
jamais. Mesuré : `client_id` faux survivant neuf jours, cinq workflows inter-profils échouant au
premier passage réel.

Les DEUX sens, et ici le second n'est vraiment pas décoratif : le harnais de cette forge
elle-même injecte un jeton dans le `localStorage`. Une règle qui ne distinguerait pas un jeton
OBTENU d'une session COMPOSÉE mettrait la forge en échec sur son propre outillage, et une règle
qui accuse à tort se fait désactiver — c'est-à-dire qu'elle meurt.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import revue


def _spec(racine: Path, nom: str, corps: str, sous: str = "frontend/tests/e2e") -> Path:
    dossier = racine.joinpath(*sous.split("/"))
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_text(corps, encoding="utf-8")
    return chemin


# --- Piège 7 : la session composée sur place ---------------------------------------------------
_SESSION_COMPOSEE = """import { test, expect } from '@playwright/test';

test('un approbateur voit la demande qui lui est passee', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('msal.account.keys', JSON.stringify({
      homeAccountId: 'profil-2',
      clientId: '00000000-0000-0000-0000-000000000000',
    }));
  });
  await page.goto('/inbox');
  await expect(page.getByTestId('demande-42')).toBeVisible();
});
"""

_SESSION_JOUEE = """import { test, expect } from '@playwright/test';

test('un approbateur voit la demande qui lui est passee', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Identifiant').fill(process.env.PROFIL_2_USER!);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page.getByTestId('demande-42')).toBeVisible();
});
"""

_JETON_OBTENU = """import { test, expect } from '@playwright/test';

test('un approbateur voit la demande qui lui est passee', async ({ page, request }) => {
  const jeton = await obtenirJetonReel(request, 'profil-2');
  await page.addInitScript((t) => { localStorage.setItem('access_token', t); }, jeton);
  await page.goto('/inbox');
  await expect(page.getByTestId('demande-42')).toBeVisible();
});
"""

_CLE_SANS_RAPPORT = """import { test, expect } from '@playwright/test';

test('le tableau garde la colonne repliee entre deux visites', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('preferences.colonnes-repliees', JSON.stringify(['montant']));
  });
  await page.goto('/inbox');
  await expect(page.getByTestId('colonne-montant')).toBeHidden();
});
"""


def test_une_session_COMPOSEE_sur_place_est_bloquante(tmp_path: Path) -> None:
    """Le cas fondateur : la clé est calculée à la main, la redirection sautée, et le contrôle
    d'audience de la bibliothèque cliente avec elle."""
    _spec(tmp_path, "20-inter-profils.spec.ts", _SESSION_COMPOSEE)

    findings = revue.session_fabriquee(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert findings[0].severite == "bloquant"
    assert findings[0].classe == "session-fabriquee-hors-parcours-d-entree"
    assert "PARCOURS D ENTREE REEL" in findings[0].message
    assert "run 13894" in findings[0].message


def test_une_session_JOUEE_par_le_parcours_reel_est_innocente(tmp_path: Path) -> None:
    """La forme que la règle demande : aucun stockage touché, la session naît du produit."""
    _spec(tmp_path, "20-inter-profils.spec.ts", _SESSION_JOUEE)

    assert revue.session_fabriquee(tmp_path) == []


def test_un_jeton_OBTENU_puis_injecte_est_signale_jamais_bloquant(tmp_path: Path) -> None:
    """Ce que fait le harnais de cette forge : le jeton vient d'un appel réel, donc son audience
    a été vérifiée par le serveur émetteur. L'écart se LIT, il ne s'accuse pas — sans quoi la
    forge mettrait en échec son propre outillage, et la règle serait désactivée."""
    _spec(tmp_path, "20-inter-profils.spec.ts", _JETON_OBTENU)

    findings = revue.session_fabriquee(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert findings[0].severite == "signale"
    assert "issue d un APPEL" in findings[0].message


def test_une_cle_de_stockage_SANS_RAPPORT_avec_une_session_passe(tmp_path: Path) -> None:
    """La liste des fragments est FERMÉE : une préférence d'affichage n'est pas une session, et
    un contrôle qui les confondrait attraperait la moitié des specs."""
    _spec(tmp_path, "30-preferences.spec.ts", _CLE_SANS_RAPPORT)

    assert revue.session_fabriquee(tmp_path) == []


# --- Piège 8 : la clé de relecture hors du stockage de la session ------------------------------
_CONFIG_AVEC_STORAGE_STATE = """import { defineConfig } from '@playwright/test';

export default defineConfig({
  use: { storageState: 'tests/.auth/profil-2.json' },
});
"""

_SPEC_ECRIT_SESSION_STORAGE = """import { test, expect } from '@playwright/test';

test('le profil choisi survit au rechargement', async ({ page }) => {
  await page.goto('/inbox');
  await page.evaluate(() => { sessionStorage.setItem('profil-actif', 'profil-2'); });
  await page.reload();
  await expect(page.getByTestId('profil-actif')).toHaveText('profil-2');
});
"""

_SPEC_ECRIT_LOCAL_STORAGE = """import { test, expect } from '@playwright/test';

test('le profil choisi survit au rechargement', async ({ page }) => {
  await page.goto('/inbox');
  await page.evaluate(() => { localStorage.setItem('profil-actif', 'profil-2'); });
  await page.reload();
  await expect(page.getByTestId('profil-actif')).toHaveText('profil-2');
});
"""


def test_storageState_et_sessionStorage_ensemble_sont_constates(tmp_path: Path) -> None:
    """Le second défaut de Produit-01, celui qui passait tsc, eslint, 137 tests unitaires et le
    harnais de connexion : `storageState` ne sauvegarde pas le sessionStorage, donc la clé est
    perdue au rejeu et l'application retombe silencieusement sur son identité nominale."""
    (tmp_path / "playwright.config.ts").write_text(_CONFIG_AVEC_STORAGE_STATE, encoding="utf-8")
    _spec(tmp_path, "40-profil.spec.ts", _SPEC_ECRIT_SESSION_STORAGE)

    findings = revue.cle_de_relecture_separee_de_la_session(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert findings[0].classe == "cle-de-relecture-hors-du-stockage-de-la-session"
    assert "ne sauvegarde PAS" in findings[0].message
    assert "137 tests unitaires" in findings[0].message


def test_la_cle_dans_le_MEME_stockage_que_la_session_est_innocente(tmp_path: Path) -> None:
    """La forme corrigée : la clé vit là où `storageState` la sauvegardera."""
    (tmp_path / "playwright.config.ts").write_text(_CONFIG_AVEC_STORAGE_STATE, encoding="utf-8")
    _spec(tmp_path, "40-profil.spec.ts", _SPEC_ECRIT_LOCAL_STORAGE)

    assert revue.cle_de_relecture_separee_de_la_session(tmp_path) == []


def test_sans_storageState_le_sessionStorage_n_est_pas_reproche(tmp_path: Path) -> None:
    """Sans état persisté, rien n'est perdu au rejeu : la règle n'a pas d'objet, et elle se tait
    plutôt que de signaler un usage légitime du sessionStorage."""
    _spec(tmp_path, "40-profil.spec.ts", _SPEC_ECRIT_SESSION_STORAGE)

    assert revue.cle_de_relecture_separee_de_la_session(tmp_path) == []


def test_les_deux_regles_sont_jouees_par_analyser_suite(tmp_path: Path) -> None:
    """Une règle non appelée par le point d'entrée n'existe pas (loi 1) : les cinq précédentes
    étaient câblées, ces deux-là doivent l'être aussi."""
    (tmp_path / "playwright.config.ts").write_text(_CONFIG_AVEC_STORAGE_STATE, encoding="utf-8")
    _spec(tmp_path, "20-inter-profils.spec.ts", _SESSION_COMPOSEE)
    _spec(tmp_path, "40-profil.spec.ts", _SPEC_ECRIT_SESSION_STORAGE)

    classes_vues = {f.classe for f in revue.analyser_suite(tmp_path)}

    assert "session-fabriquee-hors-parcours-d-entree" in classes_vues
    assert "cle-de-relecture-hors-du-stockage-de-la-session" in classes_vues
