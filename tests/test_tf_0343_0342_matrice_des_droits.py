"""TF-0343 / TF-0342 — la matrice des droits est exécutable, et un produit à rôles l'exige.

TF-0343 : le cahier d'Approval2 porte 10 actions × 4 profils. La suite les couvrait *dispersées
dans 13 fichiers, par service* — organisation qui ne peut PAS dire quelles cases manquent. Deux
manquaient (« en copie » jamais testé en lecture, aucun admin instancié sur une décision), et
deux autres cases ne sont pas tenues par le produit sans qu'aucun test ne le signale.

TF-0342 : le même produit a passé un audit 12 pans « 8/8, ratio 1,00, ZÉRO finding » sous UNE
identité qui se désignait elle-même approbateur. Le cas nominal du cahier n'avait jamais été
exécuté ; le trou a été trouvé par une question humaine, cinq jours plus tard.

Les deux sens sont tenus partout : la grille incomplète est refusée, la grille tenue passe.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import droits

_MATRICE = {
    "profils": ["demandeur", "approbateur", "en copie", "admin"],
    "actions": [
        {
            "nom": "decider",
            "methode": "POST",
            "route": "/api/demandes/{id}/decision",
            "mute": True,
            "attendu": {"approbateur": 200, "demandeur": 403, "en copie": 403, "admin": 403},
        },
        {
            "nom": "relancer",
            "methode": "POST",
            "route": "/api/demandes/{id}/relance",
            "attendu": {"demandeur": 200, "approbateur": 403, "en copie": 403, "admin": 200},
            "non_tenues": ["demandeur", "admin"],
        },
    ],
}


def _projet(racine: Path, matrice: dict | str = _MATRICE) -> Path:
    (racine / "forge").mkdir(parents=True, exist_ok=True)
    contenu = matrice if isinstance(matrice, str) else json.dumps(matrice, ensure_ascii=False)
    (racine / droits.FICHIER).write_text(contenu, encoding="utf-8")
    return racine


# --- La grille : une cellule par (action × profil), jamais une de moins ------------------------
def test_la_grille_est_le_produit_CARTESIEN_pas_ce_que_le_contrat_declare() -> None:
    """L'inversion est tout le sujet : énumérer d'abord la grille, regarder ensuite ce que le
    contrat en dit. Parcourir le contrat reproduirait le biais de disponibilité."""
    grille = droits.cellules(_MATRICE)

    assert len(grille) == 2 * 4, "2 actions × 4 profils = 8 cellules, toujours"
    assert {c["profil"] for c in grille} == set(_MATRICE["profils"])


def test_une_case_ABSENTE_du_contrat_est_nommee_pas_omise() -> None:
    matrice = {
        "profils": ["demandeur", "en copie"],
        "actions": [{"nom": "lire", "attendu": {"demandeur": 200}}],
    }

    grille = droits.cellules(matrice)
    copie = next(c for c in grille if c["profil"] == "en copie")

    assert copie["au_contrat"] is False
    assert len(grille) == 2


# --- Le fichier généré ---------------------------------------------------------------------------
def test_chaque_cellule_devient_UN_test_dans_UN_fichier_dedie() -> None:
    code = droits.generer_matrice(_MATRICE)

    assert code.count("\ndef test_") == 8, "une cellule = un test"
    assert "test_decider_approbateur" in code
    assert "test_decider_en_copie" in code, "le profil « en copie » a sa cellule, enfin"
    assert "test_decider_admin" in code, "l admin est INSTANCIE sur une décision"


def test_une_cellule_NON_TENUE_sort_en_xfail_STRICT_jamais_commentee() -> None:
    """`strict=True` est le cœur : le jour du correctif, XPASS fait échouer le test et force à
    retirer le marqueur. Un écart commenté, lui, survit à son correctif."""
    code = droits.generer_matrice(_MATRICE)
    bloc = code[code.index("def test_relancer_demandeur") - 400: code.index(
        "def test_relancer_demandeur"
    )]

    assert "xfail(" in bloc and "strict=True" in bloc
    assert "NON TENUE par le produit" in bloc
    assert "# def test_relancer_demandeur" not in code, "jamais commentée"


def test_une_cellule_TENUE_n_est_PAS_marquee_xfail() -> None:
    """Second sens : `xfail` partout rendrait la suite entière inoffensive."""
    code = droits.generer_matrice(_MATRICE)
    debut = code.index("def test_relancer_approbateur")

    assert "xfail" not in code[debut - 200: debut]


def test_une_cellule_MUTANTE_recoit_un_OBJET_NEUF_par_construction() -> None:
    """TF-0344, piège 3 : l'approbation du profil N ouvrait le tour du profil N+1, qui rendait
    201 au lieu de 409. Ici c'est structurel, pas une vigilance à retenir."""
    code = droits.generer_matrice(_MATRICE)
    debut = code.index("def test_decider_approbateur")
    corps = code[debut: debut + 500]

    assert "_objet_neuf(client, 'approbateur')" in corps


def test_une_cellule_NON_mutante_ne_fabrique_pas_d_objet() -> None:
    code = droits.generer_matrice(_MATRICE)
    debut = code.index("def test_relancer_approbateur")

    assert "_objet_neuf" not in code[debut: debut + 400]


def test_le_fichier_genere_est_du_PYTHON_valide() -> None:
    """Un patron qui ne compile pas est un gabarit, pas un livrable."""
    compile(droits.generer_matrice(_MATRICE), "test_matrice_droits.py", "exec")


def test_sans_matrice_declaree_rien_n_est_genere(tmp_path: Path) -> None:
    assert droits.ecrire(tmp_path, tmp_path / "cas") is None


def test_la_matrice_est_ECRITE_dans_le_dossier_de_cas_derives_jamais_chez_l_audite(
    tmp_path: Path,
) -> None:
    projet = _projet(tmp_path / "projet")
    destination = tmp_path / "cas-derives"

    chemin = droits.ecrire(projet, destination)

    assert chemin is not None and chemin.parent == destination
    assert not (projet / droits.NOM_FICHIER_GENERE).exists(), "G-1 : jamais chez l audité"


# --- TF-0342 : les deux exigences de socle -------------------------------------------------------
_SPEC_MONO = """import { test, expect } from '@playwright/test';
test('parcours approbateur', async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: 'approbateur.json' });
  const page = await ctx.newPage();
  await page.goto('/review/7');
});
"""

_SPEC_COEXISTENCE = """import { test, expect } from '@playwright/test';
test('le suivant est sollicite pendant que le premier decide', async ({ browser }) => {
  const a = await browser.newContext({ storageState: 'approbateur1.json' });
  const b = await browser.newContext({ storageState: 'approbateur2.json' });
  const pageA = await a.newPage();
  const pageB = await b.newPage();
  await pageA.goto('/review/7');
  await pageB.goto('/review/7');
});
"""


def _specs(racine: Path, corps: str) -> list[Path]:
    dossier = racine / "frontend" / "tests" / "e2e"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "40-profils.spec.ts"
    chemin.write_text(corps, encoding="utf-8")
    return [chemin]


def _sessions(*roles: str) -> list[dict]:
    return [{"role": role, "storage_state": f"{role}.json", "etat": None} for role in roles]


def test_moins_d_identites_que_de_roles_est_un_CONSTAT_pas_un_avertissement(
    tmp_path: Path,
) -> None:
    """Le cas du 12/08 : un compte unique, « ratio 1,00, ZÉRO finding », et trois surfaces
    réservées jamais visitées sous leur rôle propre."""
    projet = _projet(tmp_path)
    specs = _specs(projet, _SPEC_COEXISTENCE)

    findings = droits.controles(projet, _sessions("approbateur"), specs)

    manquantes = [f for f in findings if f.id.endswith("identites-manquantes")]
    assert len(manquantes) == 1
    assert "« admin »" in manquantes[0].message
    assert "« en copie »" in manquantes[0].message


def test_autant_d_identites_que_de_roles_ET_une_coexistence_ne_declenche_rien(
    tmp_path: Path,
) -> None:
    projet = _projet(tmp_path)
    specs = _specs(projet, _SPEC_COEXISTENCE)

    assert droits.controles(
        projet, _sessions("demandeur", "approbateur", "en copie", "admin"), specs
    ) == []


def test_rejouer_le_parcours_sous_N_profils_ne_remplace_PAS_une_coexistence(
    tmp_path: Path,
) -> None:
    """L'un après l'autre ne montre jamais ce qu'un profil VOIT pendant qu'un autre AGIT — et
    c'est ainsi qu'a été trouvé le défaut produit du 17/08."""
    projet = _projet(tmp_path)
    specs = _specs(projet, _SPEC_MONO)

    findings = droits.controles(
        projet, _sessions("demandeur", "approbateur", "en copie", "admin"), specs
    )

    assert [f.id for f in findings] == ["qualif:multi-profils:aucune-coexistence"]
    assert "pendant qu un autre AGIT" in findings[0].message


def test_un_produit_SANS_role_declare_n_est_pas_inquiete(tmp_path: Path) -> None:
    """L'exigence naît de la déclaration de rôles. Sans matrice, rien à exiger."""
    (tmp_path / "forge").mkdir()

    assert droits.controles(tmp_path, _sessions(), []) == []


def test_une_matrice_ILLISIBLE_est_denoncee_jamais_ignoree(tmp_path: Path) -> None:
    """Un contrôle qu'on désarme en cassant son entrée n'est pas un contrôle."""
    projet = _projet(tmp_path, matrice="{ ceci n est pas du JSON")

    findings = droits.controles(projet, _sessions("admin"), [])

    assert [f.id for f in findings] == ["qualif:matrice-droits:illisible"]
    assert "aucune cellule n est opposable" in findings[0].message
