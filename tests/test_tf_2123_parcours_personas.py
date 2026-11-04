"""TF-2123 — aucun pan n exigeait un parcours de bout en bout par persona.

Fait remonté (Produit-86, lot du 03/11/2026) : les parcours de bout en bout par profil ont dû être
écrits par la session à la demande du porteur. Un produit qui déclare des personas pouvait passer
l audit avec une suite qui ne joue qu une identité, ou aucun parcours.

Le pan `parcours-personas` lit les personas que le produit DÉCLARE (EXIGENCES.json, matrice des
droits, comptes de test par rôle) et exige, pour chacun, au moins un parcours de bout en bout qui
le cite. Version minimale et prouvée : détection des personas déclarés, présence ou absence d un
parcours par persona. Le jeu contre l instance servie N EST PAS réalisé ni simulé : le pan le dit
à chaque rapport.

Trois sens :
  - ROUGE  — un persona déclaré qu aucun parcours ne cite : constat NOMMÉ, verdict FAIL ;
  - VERT   — un parcours par persona : PASS, et le non-jeu contre l instance reste publié ;
  - SANS OBJET — aucun persona déclaré : NA, avec la preuve de ce qui a été lu.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, personas
from forge_tests.livrables import exigences, surface

RACINE = Path(__file__).resolve().parent.parent

PARCOURS = (
    "import {{ test, expect }} from '@playwright/test';\n"
    "test('{nom}', async ({{ page }}) => {{\n"
    "  await page.goto('/');\n"
    "  await expect(page).toHaveTitle(/accueil/);\n"
    "}});\n"
)


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL"):
        monkeypatch.delenv(cle, raising=False)


def _ecrire(racine: Path, relatif: str, texte: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


def _produit(tmp_path: Path, declares: list[object], parcours: list[str]) -> Path:
    """Un produit dont EXIGENCES.json déclare `declares` et dont `e2e/<nom>.spec.ts` jouent
    chacun un parcours de bout en bout nommé par son fichier."""
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/EXIGENCES.json",
            json.dumps({"projet": "p", "personas": declares}, ensure_ascii=False))
    for nom in parcours:
        _ecrire(racine, f"e2e/{nom}.spec.ts", PARCOURS.format(nom=f"parcours {nom}"))
    return racine


def _non_exerces(racine: Path) -> list[str]:
    return sorted(f.id for f in personas.analyser(racine).findings if f.id.startswith("persona:"))


# --- ROUGE ----------------------------------------------------------------------------------------
def test_rouge_un_persona_sans_parcours_est_un_constat_nomme(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Gestionnaire", "Approbateur"], ["gestionnaire"])
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert _non_exerces(racine) == ["persona:approbateur"]
    constat = next(f for f in sortie.findings if f.id == "persona:approbateur")
    assert "Approbateur" in constat.message


def test_rouge_aucun_parcours_du_tout_nomme_chaque_persona(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Gestionnaire", "Approbateur"], [])
    assert personas.analyser(racine).verdict == "FAIL"
    assert _non_exerces(racine) == ["persona:approbateur", "persona:gestionnaire"]


def test_rouge_un_test_unitaire_qui_cite_le_persona_n_est_pas_un_parcours(
    tmp_path: Path,
) -> None:
    racine = _produit(tmp_path, ["Approbateur"], [])
    _ecrire(racine, "tests/approbateur.test.ts",
            "test('approbateur', () => { expect(1).toBe(1); })")
    _ecrire(racine, "tests/test_approbateur.py", "def test_approbateur():\n    assert True\n")
    assert _non_exerces(racine) == ["persona:approbateur"]


def test_rouge_un_pilote_de_navigateur_qui_ne_navigue_pas_n_est_pas_un_parcours(
    tmp_path: Path,
) -> None:
    racine = _produit(tmp_path, ["Approbateur"], [])
    _ecrire(racine, "e2e/approbateur.spec.ts",
            "import { test } from '@playwright/test';\ntest('approbateur', async () => {});\n")
    assert _non_exerces(racine) == ["persona:approbateur"]


def test_rouge_le_nom_d_un_persona_est_cite_en_mot_entier(tmp_path: Path) -> None:
    """`admin` n est pas cité par un parcours d « administrateur » : un fragment de mot ne vaut
    pas citation."""
    racine = _produit(tmp_path, ["admin"], ["administrateur"])
    assert _non_exerces(racine) == ["persona:admin"]


# --- VERT -----------------------------------------------------------------------------------------
def test_vert_un_parcours_par_persona_et_le_non_jeu_reste_publie(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Gestionnaire", "Approbateur"], ["gestionnaire", "approbateur"])
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS"
    assert sortie.findings == []
    assert sortie.surface is None or sortie.surface["ratio"] == 1.0
    # Le pan ne joue rien : il le dit, jamais un vert sans cette réserve.
    assert any("AUCUN parcours" in m or "aucune instance servie" in m for m in sortie.non_juge)
    assert any("n est PAS réalisé ici" in m for m in sortie.non_juge)


def test_vert_la_citation_dans_le_texte_vaut_citation_dans_le_nom(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Approbateur"], [])
    _ecrire(racine, "e2e/circuit-de-validation.spec.ts",
            PARCOURS.format(nom="le Approbateur décide, le suivant est sollicité"))
    assert _non_exerces(racine) == []
    assert personas.analyser(racine).verdict == "PASS"


def test_vert_les_accents_et_la_casse_ne_changent_pas_le_persona(tmp_path: Path) -> None:
    racine = _produit(tmp_path, [{"id": "P1", "nom": "Équipier d'été"}], [])
    _ecrire(racine, "e2e/equipier-d-ete.spec.ts", PARCOURS.format(nom="parcours"))
    assert _non_exerces(racine) == []


def test_vert_l_identifiant_d_un_persona_vaut_son_nom(tmp_path: Path) -> None:
    racine = _produit(tmp_path, [{"id": "P1", "nom": "Approbateur"}], [])
    assert _non_exerces(racine) == ["persona:approbateur"]
    _ecrire(racine, "e2e/p1.spec.ts", PARCOURS.format(nom="parcours"))
    assert _non_exerces(racine) == []


def test_vert_une_instance_declaree_est_dite_non_jouee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, ["Gestionnaire"], ["gestionnaire"])
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "https://exemple.invalide")
    non_juge = " ".join(personas.analyser(racine).non_juge)
    assert "une instance servie est déclarée" in non_juge and "AUCUN parcours" in non_juge


# --- les trois sources de personas ----------------------------------------------------------------
def test_les_profils_de_la_matrice_des_droits_sont_des_personas(tmp_path: Path) -> None:
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/matrice-droits.json",
            json.dumps({"profils": ["demandeur", "approbateur"], "actions": []}))
    _ecrire(racine, "e2e/demandeur.spec.ts", PARCOURS.format(nom="parcours"))
    assert _non_exerces(racine) == ["persona:approbateur"]


def test_les_comptes_de_test_par_role_sont_des_personas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = tmp_path / "produit"
    _ecrire(racine, ".env.forge-tests",
            "FORGE_TESTS_QUALIF_STORAGE_STATES=agent=a.json,superviseur=b.json\n")
    _ecrire(racine, "e2e/agent.spec.ts", PARCOURS.format(nom="parcours"))
    assert _non_exerces(racine) == ["persona:superviseur"]
    # Lu sans rien écrire dans l environnement du processus.
    import os
    assert "FORGE_TESTS_QUALIF_STORAGE_STATES" not in os.environ
    monkeypatch.setenv("FORGE_TESTS_QUALIF_STORAGE_STATES", "agent=a.json,tiers=c.json")
    assert _non_exerces(racine) == ["persona:tiers"]


def test_un_persona_declare_par_deux_sources_n_est_exige_qu_une_fois(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Approbateur"], [])
    _ecrire(racine, "forge/matrice-droits.json", json.dumps({"profils": ["approbateur"]}))
    inventaire = personas.inventaire(racine)
    assert [e.id for e in inventaire] == ["persona:approbateur"]
    assert "EXIGENCES.json" in inventaire[0].libelle and "matrice-droits" in inventaire[0].libelle


def test_le_referentiel_designe_par_la_variable_prime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, ["Gestionnaire"], ["gestionnaire"])
    ailleurs = tmp_path / "autre" / "EXIGENCES.json"
    _ecrire(ailleurs.parent, "EXIGENCES.json", json.dumps({"roles": ["Auditeur"]}))
    monkeypatch.setenv("FORGE_TESTS_EXIGENCES", str(ailleurs))
    assert _non_exerces(racine) == ["persona:auditeur"]


# --- SANS OBJET et illisible ----------------------------------------------------------------------
def test_sans_persona_declare_le_pan_est_sans_objet_et_dit_ce_qui_a_ete_lu(tmp_path: Path) -> None:
    racine = tmp_path / "produit"
    _ecrire(racine, "e2e/gestionnaire.spec.ts", PARCOURS.format(nom="parcours"))
    sortie = personas.analyser(racine)
    assert sortie.verdict == "NA"
    texte = " ".join(sortie.non_juge)
    assert "EXIGENCES.json" in texte and "matrice-droits" in texte
    assert "FORGE_TESTS_QUALIF_STORAGE_STATES" in texte


def test_un_referentiel_illisible_n_est_pas_un_sans_objet(tmp_path: Path) -> None:
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/EXIGENCES.json", "{ pas du json")
    sortie = personas.analyser(racine)
    assert sortie.verdict == "SKIP"
    assert any("illisible" in m for m in sortie.non_juge)


@pytest.mark.parametrize("banc", ["banc-vert", "banc-rouge"])
def test_les_bancs_de_la_recette_ne_declarent_aucun_persona(banc: str) -> None:
    """Le pan ne change ni le banc vert (aucun bloquant) ni le banc rouge (défauts plantés)."""
    assert personas.analyser(RACINE / "fixtures" / banc).verdict == "NA"


# --- câblage --------------------------------------------------------------------------------------
def test_le_pan_est_enregistre_documente_et_range_en_cahier() -> None:
    assert "parcours-personas" in PANS_ATTENDUS
    assert REGISTRE["parcours-personas"] is personas
    chapitre = next(c for c in surface.chapitres(REGISTRE) if c["code"] == "F7")
    assert chapitre["decoupe"] == "persona" and chapitre["axe_connu"]
    assert surface.sous_chapitre("persona", "persona:approbateur") == ("persona approbateur", True)


def test_la_variable_du_referentiel_est_celle_du_module_livrables() -> None:
    """Le littéral est recopié pour éviter l import circulaire (voir le module) : on teste
    l égalité."""
    assert personas._VARIABLE_EXIGENCES == exigences.VARIABLE
