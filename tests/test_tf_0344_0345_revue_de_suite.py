"""TF-0344 / TF-0345 — les faux verts de la suite, détectés sans rien exécuter.

Trois faux verts le même jour, sur la même campagne, aucun vu par un oracle. Deux sont
détectables statiquement ; le troisième est déclaré non jugé, et porté ailleurs (TF-0343).
S'y ajoute la donnée de test recopiée (TF-0345), même famille : un défaut invisible à la
lecture du diff, coûteux au diagnostic parce que le symptôme ne pointe pas vers la cause.

Chaque règle est tenue dans les DEUX sens. Le second sens n'est pas décoratif ici : une revue
statique qui crie sur du code sain se désactive à la première campagne pressée, et le contrôle
meurt en silence — exactement ce que ce module existe pour empêcher.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import revue


def _spec(racine: Path, nom: str, corps: str) -> Path:
    dossier = racine / "frontend" / "tests" / "e2e"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_text(corps, encoding="utf-8")
    return chemin


# --- Piège 1 : absence sans présence -----------------------------------------------------------
_ABSENCE_NUE = """import { test, expect } from '@playwright/test';

test('le passage de main sequentiel retire la demande de la file', async ({ page }) => {
  await page.goto('/inbox');
  await expect(page.getByTestId('demande-42')).toHaveCount(0);
});
"""

_ABSENCE_ACQUITTEE = """import { test, expect } from '@playwright/test';

test('le passage de main sequentiel retire la demande de la file', async ({ page }) => {
  await page.goto('/inbox');
  await expect(page.getByTestId('file-des-demandes')).toBeVisible();
  await expect(page.getByTestId('demande-42')).toHaveCount(0);
});
"""


def test_une_assertion_d_ABSENCE_sans_presence_est_constatee(tmp_path: Path) -> None:
    """Le cas réel : vert en isolation, rouge en exécution complète. Sur une page encore en
    chargement, `toHaveCount(0)` passe parce que rien n'est encore là."""
    _spec(tmp_path, "10-sequentiel.spec.ts", _ABSENCE_NUE)

    findings = revue.absence_sans_presence(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert "sans qu aucune assertion de PRESENCE" in findings[0].message
    assert findings[0].classe == "faux-vert-absence-sans-presence"


def test_une_assertion_d_ABSENCE_precedee_d_une_PRESENCE_est_innocente(tmp_path: Path) -> None:
    _spec(tmp_path, "10-sequentiel.spec.ts", _ABSENCE_ACQUITTEE)

    assert revue.absence_sans_presence(tmp_path) == []


def test_l_ordre_compte_une_presence_APRES_l_absence_n_acquitte_rien(tmp_path: Path) -> None:
    """Le détail qui fait tout : une présence assertée APRÈS ne prouve rien sur l'instant où
    l'absence a été mesurée."""
    corps = _ABSENCE_NUE.replace(
        "  await expect(page.getByTestId('demande-42')).toHaveCount(0);\n",
        "  await expect(page.getByTestId('demande-42')).toHaveCount(0);\n"
        "  await expect(page.getByTestId('file-des-demandes')).toBeVisible();\n",
    )
    _spec(tmp_path, "11-ordre.spec.ts", corps)

    assert len(revue.absence_sans_presence(tmp_path)) == 1


# --- Piège 2 : motif satisfait par le déclencheur ------------------------------------------------
_MOTIF_COLLISION = """import { test, expect } from '@playwright/test';

test('le refus est enregistre', async ({ page }) => {
  await page.goto('/review/7');
  await page.getByRole('button', { name: 'Refuse' }).click();
  await expect(page.getByText(/Refused|Refus/i)).toBeVisible();
});
"""

_MOTIF_DISJOINT = """import { test, expect } from '@playwright/test';

test('le refus est enregistre', async ({ page }) => {
  await page.goto('/review/7');
  await page.getByRole('button', { name: 'Refuse' }).click();
  await expect(page.getByText('Decision enregistree')).toBeVisible();
});
"""


def test_un_motif_d_assertion_prefixe_du_libelle_CLIQUE_est_constate(tmp_path: Path) -> None:
    """Le cas exact : `/Refused|Refus/i` matche le bouton « Refuse ». L'assertion passait donc
    avant toute décision, supprimant la barrière de synchronisation entre profils."""
    _spec(tmp_path, "20-refus.spec.ts", _MOTIF_COLLISION)

    findings = revue.motif_satisfait_par_le_declencheur(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert "prefixe du libelle CLIQUE" in findings[0].message
    assert "Refuse" in findings[0].message


def test_un_motif_d_assertion_DISJOINT_du_declencheur_est_innocent(tmp_path: Path) -> None:
    _spec(tmp_path, "20-refus.spec.ts", _MOTIF_DISJOINT)

    assert revue.motif_satisfait_par_le_declencheur(tmp_path) == []


def test_chaque_ALTERNATIVE_du_motif_est_confrontee_pas_seulement_la_premiere(
    tmp_path: Path,
) -> None:
    """`Refused|Refus` : c'est la SECONDE alternative qui collisionne. Ne lire que la première
    aurait laissé passer le cas fondateur lui-même."""
    _spec(tmp_path, "21-alternatives.spec.ts", _MOTIF_COLLISION)

    assert revue._alternatives("Refused|Refus") == ["Refused", "Refus"]
    assert len(revue.motif_satisfait_par_le_declencheur(tmp_path)) == 1


# --- TF-0345 : la donnée de test recopiée ---------------------------------------------------------
# La taille du cas fondateur : 3316 caracteres de base64. Elle compte — a cette echelle, une
# perte de 80 caracteres est invisible a la lecture ET laisse la donnee « plausible ».
_PNG = "iVBORw0KGgoAAAANSUhEUg" + "AB" * 1647


def _spec_avec_donnee(racine: Path, nom: str, donnee: str) -> None:
    _spec(
        racine,
        nom,
        "import { test, expect } from '@playwright/test';\n"
        f"const PNG = '{donnee}';\n"
        "test('envoi', async ({ page }) => { await page.goto('/'); });\n",
    )


def test_une_donnee_de_test_RECOPIEE_a_l_identique_est_constatee(tmp_path: Path) -> None:
    _spec_avec_donnee(tmp_path, "30-envoi.spec.ts", _PNG)
    _spec_avec_donnee(tmp_path, "31-inter-profils.spec.ts", _PNG)

    findings = revue.donnees_recopiees(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert "est RECOPIEE" in findings[0].message
    assert "se REFERENCE" in findings[0].message


def test_une_recopie_qui_a_DERIVE_est_constatee_et_nommee_comme_telle(tmp_path: Path) -> None:
    """Le cas fondateur : 80 caractères perdus. Le fichier gardait sa signature PNG et une
    taille plausible — quatre tests en timeout, diagnostic égaré vers la conversion."""
    _spec_avec_donnee(tmp_path, "30-envoi.spec.ts", _PNG)
    _spec_avec_donnee(tmp_path, "31-inter-profils.spec.ts", _PNG[:-80])

    findings = revue.donnees_recopiees(tmp_path)

    assert len(findings) == 1, [f.id for f in findings]
    assert "quasi identiques" in findings[0].message
    assert "une recopie a DERIVE" in findings[0].message


def test_deux_donnees_REELLEMENT_differentes_ne_declenchent_rien(tmp_path: Path) -> None:
    _spec_avec_donnee(tmp_path, "30-envoi.spec.ts", "A" * 400)
    _spec_avec_donnee(tmp_path, "31-inter-profils.spec.ts", "Zk9" * 200)

    assert revue.donnees_recopiees(tmp_path) == []


def test_une_donnee_utilisee_DEUX_FOIS_dans_le_MEME_fichier_n_est_pas_une_recopie(
    tmp_path: Path,
) -> None:
    """La règle vise la recopie ENTRE fichiers — c'est elle qui dérive. Deux usages dans un
    même fichier partagent déjà une source unique de fait."""
    _spec(
        tmp_path,
        "30-envoi.spec.ts",
        f"const A = '{_PNG}';\nconst B = '{_PNG}';\n"
        "import { test } from '@playwright/test';\n",
    )

    assert revue.donnees_recopiees(tmp_path) == []


# --- Le troisième piège : déclaré non jugé, jamais fait semblant de voir --------------------------
def test_la_cellule_mutante_est_DECLAREE_non_jugee_et_renvoie_a_son_porteur() -> None:
    """Loi 3 : on s'écarte explicitement. Un module qui tairait ce troisième piège laisserait
    croire que « revue passée » veut dire « les trois pièges sont fermés »."""
    declare = " ".join(revue.NON_JUGE)

    assert "CELLULE MUTANTE" in declare
    assert "TF-0343" in declare, "le non-jugé nomme qui porte la règle à sa place"
    assert "suites Python ne le sont pas" in declare


# --- Le câblage : la revue tourne DANS le pan, et même quand la suite ne tourne pas ---------------
def test_le_pan_front_PORTE_les_constats_de_revue_meme_sans_suite_executable(
    tmp_path: Path,
) -> None:
    """C'est le cœur du câblage : un projet dont la suite ne peut pas tourner est justement
    celui où un faux vert dort le plus longtemps. La revue est statique, elle doit sortir."""
    from forge_tests.adaptateurs import front

    (tmp_path / "frontend" / "src").mkdir(parents=True)
    _spec(tmp_path, "20-refus.spec.ts", _MOTIF_COLLISION)

    sortie = front.analyser(tmp_path)

    assert sortie.verdict == "FAIL", sortie.verdict
    assert any(f.classe == "faux-vert-motif-du-declencheur" for f in sortie.findings)
    assert any("CELLULE MUTANTE" in n for n in sortie.non_juge)
