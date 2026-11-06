"""TF-2207 — un e2e par parcours ET par rôle, exigé dès que le parcours est déclaré.

Fait remonté (Produit-86, lot du 05/11/2026, RP-27) : au troisième jour, 27 exigences sur 127
étaient citées par un test de bout en bout, et 9 cases « parcours x rôle » sur 30 portaient un
e2e. Rien n'exigeait l'e2e du rôle à la création du parcours.

Décision du 06/11/2026 (part forge-tests) : un parcours exige un e2e par rôle, et la règle bloque.
Le produit déclare ses parcours par la clé `parcours` d'EXIGENCES.json (une entrée : un nom, ou
`{"nom": …, "roles": […]}`). Chaque case parcours x rôle est un élément de surface du pan
`parcours-personas`, exercé quand un e2e actif cite le parcours ET le rôle. Un constat est
bloquant (seuil 100 %), comme tout élément non exercé du pan.

Sens prouvés :
  - ROUGE  — une case sans e2e : FAIL nommé, avec le parcours et le rôle ; un e2e qui cite le
             parcours seul, ou le rôle seul, ne couvre pas la case ;
  - VERT   — un e2e par case ; des rôles restreints par le parcours ;
  - SANS OBJET — aucune clé `parcours` : rien n'est exigé de plus qu'avant ;
  - REMÈDE — écrire l'e2e que le message demande fait passer la case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import personas

E2E = (
    "import {{ test }} from '@playwright/test';\n"
    "test('{nom}', async ({{ page }}) => {{\n  await page.goto('/');\n}});\n"
)


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_TESTS_QUALIF_STORAGE_STATES",
                "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL"):
        monkeypatch.delenv(cle, raising=False)


def _ecrire(racine: Path, relatif: str, texte: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


def _produit(tmp_path: Path, parcours: list[object], e2e: dict[str, str]) -> Path:
    """Deux personas, `operateur` et `approbateur`, un parcours croisé qui les cite, et les e2e
    de `e2e` (fichier -> intitulé du test)."""
    racine = tmp_path / "produit"
    _ecrire(racine, "forge/EXIGENCES.json", json.dumps(
        {"projet": "p", "personas": ["Operateur", "Approbateur"], "parcours": parcours},
        ensure_ascii=False,
    ))
    _ecrire(racine, "e2e/croise.spec.ts", E2E.format(nom="operateur agit, approbateur voit"))
    for fichier, nom in e2e.items():
        _ecrire(racine, f"e2e/{fichier}.spec.ts", E2E.format(nom=nom))
    return racine


def _cases(racine: Path) -> list[str]:
    return sorted(
        f.id for f in personas.analyser(racine).findings if f.id.startswith("parcours:")
    )


# --- ROUGE ----------------------------------------------------------------------------------------
def test_rouge_une_case_parcours_x_role_sans_e2e_est_un_constat_nomme(tmp_path: Path) -> None:
    racine = _produit(
        tmp_path, ["Demande de conge"],
        {"operateur": "operateur : demande de conge", "approbateur": "approbateur valide"},
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert _cases(racine) == ["parcours:demande-de-conge@approbateur"]
    constat = next(f for f in sortie.findings if f.id.startswith("parcours:"))
    assert constat.severite == "bloquant"
    assert "Demande de conge" in constat.message and "Approbateur" in constat.message
    assert "nommer le parcours et le rôle" in constat.message


def test_rouge_un_parcours_declare_sans_aucun_e2e_est_du_pour_chaque_role(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Demande de conge"], {})
    assert _cases(racine) == [
        "parcours:demande-de-conge@approbateur", "parcours:demande-de-conge@operateur",
    ]


def test_rouge_le_role_cite_sans_le_parcours_ne_couvre_pas_la_case(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Demande de conge"], {"approbateur": "approbateur : accueil"})
    assert "parcours:demande-de-conge@approbateur" in _cases(racine)


# --- VERT -----------------------------------------------------------------------------------------
def test_vert_un_e2e_par_case(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Demande de conge"], {
        "operateur": "operateur : demande de conge",
        "approbateur": "approbateur : demande de conge",
    })
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert {"parcours:demande-de-conge@operateur",
            "parcours:demande-de-conge@approbateur"} <= set(sortie.surface["elements_exerces"])


def test_vert_un_parcours_restreint_a_certains_roles_n_exige_que_ceux_la(tmp_path: Path) -> None:
    racine = _produit(
        tmp_path, [{"nom": "Validation de conge", "roles": ["Approbateur"]}],
        {"approbateur": "approbateur : validation de conge"},
    )
    sortie = personas.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    inventaire = {e.id for e in personas.inventaire(racine)}
    assert "parcours:validation-de-conge@approbateur" in inventaire
    assert "parcours:validation-de-conge@operateur" not in inventaire


def test_sans_objet_aucune_cle_parcours_n_ajoute_aucune_exigence(tmp_path: Path) -> None:
    racine = _produit(tmp_path, [], {"operateur": "operateur", "approbateur": "approbateur"})
    assert [e for e in personas.inventaire(racine) if e.id.startswith("parcours:")] == []
    assert personas.analyser(racine).verdict == "PASS"


def test_remede_joue_ecrire_l_e2e_demande_fait_passer_la_case(tmp_path: Path) -> None:
    racine = _produit(tmp_path, ["Demande de conge"], {
        "operateur": "operateur : demande de conge", "approbateur": "approbateur valide",
    })
    assert _cases(racine) == ["parcours:demande-de-conge@approbateur"]
    _ecrire(racine, "e2e/approbateur-conge.spec.ts",
            E2E.format(nom="approbateur : demande de conge"))
    assert _cases(racine) == []
    assert personas.analyser(racine).verdict == "PASS"
