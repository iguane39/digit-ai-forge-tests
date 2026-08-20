"""TF-0395 / TF-0396 (lot nhood-cockpit-ia 20260820a) — pièges 5 et 6 de la revue statique.

Les deux viennent du même produit et du même épisode : la bascule EasyAuth du 17/08.

**Piège 5** : le parcours écrit POUR couvrir un défaut de déconnexion affirmait
`toContain("/.auth/logout")` — vert sur le comportement défectueux, `/.auth/logout` (déconnexion
du compte Microsoft entier, messagerie comprise) et `/.auth/logout/complete` (déconnexion de
l'application seule) partageant ce préfixe. Le défaut a été trouvé par un humain qui a cliqué.

**Piège 6** : la bascule a produit 13 parcours neufs sans reprendre l'assertion de déconnexion
que la suite sœur portait — le bouton a disparu de l'environnement déployé pendant TROIS JOURS
sous 68 parcours verts.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import classes, revue


def _spec(racine: Path, relatif: str, contenu: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


# --- Piège 5 — toContain sur un préfixe piégeux ------------------------------------------------
def test_le_cas_fondateur_auth_logout_est_constate(tmp_path: Path) -> None:
    _spec(tmp_path, "e2e/logout.spec.ts", """
test('la deconnexion referme la session', async () => {
  await expect(page.url()).toContain("/.auth/logout");
});
""")
    _spec(tmp_path, "e2e/routes.spec.ts", """
test('la deconnexion applicative', async () => {
  await page.goto("/.auth/logout/complete");
  await expect(page).toHaveURL("/.auth/logout/complete");
});
""")

    constats = revue.prefixe_d_un_chemin_valide(tmp_path)

    assert len(constats) == 1
    assert constats[0].classe == classes.FAUX_VERT_PREFIXE
    assert "/.auth/logout/complete" in constats[0].message
    assert "EXACTE" in constats[0].message


def test_deux_chemins_distincts_ne_sont_PAS_un_prefixe_piegeux(tmp_path: Path) -> None:
    """« /foo » face à « /foobar » : deux chemins, pas une extension — le signaler serait du
    bruit, et le bruit se fait ignorer."""
    _spec(tmp_path, "e2e/a.spec.ts", """
test('foo', async () => { await expect(page.url()).toContain("/foo"); });
""")
    _spec(tmp_path, "e2e/b.spec.ts", """
test('foobar', async () => { await page.goto("/foobar"); });
""")

    assert revue.prefixe_d_un_chemin_valide(tmp_path) == []


def test_un_toContain_sans_extension_dans_le_corpus_reste_muet(tmp_path: Path) -> None:
    _spec(tmp_path, "e2e/a.spec.ts", """
test('seul', async () => { await expect(page.url()).toContain("/compte/profil"); });
""")

    assert revue.prefixe_d_un_chemin_valide(tmp_path) == []


# --- Piège 6 — le trou de couverture inter-suites ----------------------------------------------
def test_le_cas_fondateur_easyauth_est_signale(tmp_path: Path) -> None:
    """La sœur affirme la déconnexion ; la suite neuve n'en parle jamais — même pas en texte."""
    _spec(tmp_path, "e2e/profils/connexion.spec.ts", """
test('la deconnexion referme reellement la session', async () => {
  await page.goto("/.auth/logout/complete");
  await expect(page.getByRole('button', { name: 'Connexion' })).toBeVisible();
});
""")
    _spec(tmp_path, "e2e/easyauth/entree.spec.ts", """
test('l entree redirige vers Entra', async () => {
  await page.goto("/tableau-de-bord");
  await expect(page).toHaveURL(/microsoftonline/);
});
""")

    constats = revue.trous_de_couverture_inter_suites(tmp_path)

    troues = [c for c in constats if "easyauth" in c.localisation]
    assert len(troues) == 1
    assert troues[0].classe == classes.TROU_DE_COUVERTURE_SOEUR
    assert troues[0].severite == "signale", "signal nomme, jamais un echec"
    assert "/.auth/logout/complete" in troues[0].message
    assert "profils" in troues[0].message, "la soeur qui porte l assertion est NOMMEE"


def test_une_MENTION_meme_hors_assertion_vaut_choix_conscient(tmp_path: Path) -> None:
    """La règle signale l'absence TOTALE : une suite qui mentionne le chemin (même en
    commentaire ou en préparation) a vu le sujet — l'écart est alors un choix, pas un angle
    mort."""
    _spec(tmp_path, "e2e/profils/connexion.spec.ts", """
test('deconnexion', async () => { await page.goto("/.auth/logout/complete"); });
""")
    _spec(tmp_path, "e2e/easyauth/entree.spec.ts", """
// La deconnexion passe par "/.auth/logout/complete" — couverte par la suite profils.
test('entree', async () => { await page.goto("/tableau-de-bord"); });
""")

    constats = revue.trous_de_couverture_inter_suites(tmp_path)

    assert [c for c in constats if "easyauth" in c.localisation] == []


def test_un_dossier_sans_frere_n_est_pas_une_famille(tmp_path: Path) -> None:
    _spec(tmp_path, "e2e/seul/a.spec.ts", """
test('a', async () => { await page.goto("/x"); });
""")

    assert revue.trous_de_couverture_inter_suites(tmp_path) == []


def test_les_cinq_regles_sont_agregees_par_analyser_suite(tmp_path: Path) -> None:
    """Une règle écrite et non agrégée est un contrôle que personne ne joue — le défaut trouvé
    six fois cette semaine."""
    _spec(tmp_path, "e2e/logout.spec.ts", """
test('prefixe', async () => { await expect(page.url()).toContain("/.auth/logout"); });
""")
    _spec(tmp_path, "e2e/routes.spec.ts", """
test('complet', async () => { await page.goto("/.auth/logout/complete"); });
""")

    classes_vues = {c.classe for c in revue.analyser_suite(tmp_path)}

    assert classes.FAUX_VERT_PREFIXE in classes_vues
