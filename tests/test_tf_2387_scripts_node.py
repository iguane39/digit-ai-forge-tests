"""TF-2387 — un produit en scripts Node sans package.json : inventaire et suite node:test jouée.

Fait remonté par le produit marketing (lot 20261109c, ledger seq 267) : l'audit d'un produit dont le
code est fait de scripts Node sans `package.json` rendait PARTIEL sans inventorier `scripts/*.mjs`
ni jouer `node --test` : `modules` vide, `essais.fourni` faux, aucune mention de `scripts/` au
rapport, et le non-jugé ne le disait pas.

Décision du 10/11/2026 : l'audit inventorie scripts/*.mjs et joue node --test sur un produit sans
package.json, ou publie dans le non_juge que ce code n'est pas couvert. Les deux voies sont tenues.

Sens prouvés (Node réel, produits factices en répertoire temporaire) :
  - ROUGE  — sur l'ancien code, le rapport n'a ni section `scripts_node`, ni essais, ni mention de
             `scripts/` au non-jugé, et un test rouge du produit n'influe pas sur le verdict ;
  - VERT   — la suite est jouée (essais test par test au rapport, scripts exercés et jamais chargés
             nommés), un test rouge rend FAIL, un test sauté rend PARTIEL, une absence de suite
             est publiée au non-jugé AVEC les scripts non couverts nommés ;
  - CONTRE-ÉPREUVES — un produit avec `package.json` ou sans `scripts/` n'est pas concerné et le
             rapport le dit ; deux tests homonymes de deux fichiers gardent deux identifiants ; un
             délai dépassé rend DELAI_DEPASSE avec son réglage.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import __main__ as cli
from forge_tests import execution, scripts_node
from forge_tests.noyau import rapport

sans_node = pytest.mark.skipif(shutil.which("node") is None, reason="node absent de ce poste")

SCRIPT_A = "export const double = (x) => x * 2;\nexport const jamais = () => 1;\n"
SCRIPT_B = "export const triple = (x) => x * 3;\n"
TEST_VERT = (
    'import test from "node:test";\nimport assert from "node:assert";\n'
    'import { double } from "./a.mjs";\n'
    'test("double", () => assert.equal(double(2), 4));\n'
)
TEST_ROUGE = TEST_VERT + 'test("rouge", () => assert.equal(double(2), 5));\n'
TEST_SAUTE = TEST_VERT + 'test("saute", { skip: "pas maintenant" }, () => {});\n'


def _produit(tmp_path: Path, test: str | None, *, scripts: dict[str, str] | None = None) -> Path:
    dossier = tmp_path / "scripts"
    dossier.mkdir()
    for nom, contenu in (scripts or {"a.mjs": SCRIPT_A, "b.mjs": SCRIPT_B}).items():
        (dossier / nom).write_text(contenu, encoding="utf-8")
    if test is not None:
        (dossier / "a.test.mjs").write_text(test, encoding="utf-8")
    scripts_node._jouer.cache_clear()
    return tmp_path


@sans_node
def test_l_inventaire_exclut_les_fichiers_de_test_et_nomme_les_scripts(tmp_path: Path) -> None:
    produit = _produit(tmp_path, TEST_VERT)
    assert scripts_node.inventaire(produit) == ["scripts/a.mjs", "scripts/b.mjs"]


@sans_node
def test_rouge_la_suite_est_jouee_et_le_rapport_porte_essais_et_scripts_non_couverts(
    tmp_path: Path,
) -> None:
    """ROUGE avant : section absente, `essais.fourni` faux. VERT : tout est au rapport."""
    produit = _produit(tmp_path, TEST_VERT)
    section = scripts_node.section(produit)
    assert section["applicable"] is True and section["statut"] == "joue"
    assert section["exerces"] == ["scripts/a.mjs"]
    assert section["non_exerces"] == ["scripts/b.mjs"]  # jamais chargé par un test : nommé
    texte = " ".join(section["non_juge"])
    assert "2 script(s) Node sous `scripts/`" in texte and "JAMAIS CHARGÉ(S)" in texte
    assert "scripts/b.mjs" in texte
    essais = scripts_node.essais_de_la_cible(produit)
    assert essais is not None and [e.verdict for e in essais] == ["passant"]
    rap = rapport([], [], essais=essais, scripts_node=section)
    assert rap["essais"]["fourni"] is True
    assert rap["scripts_node"]["statut"] == "joue"
    assert any("scripts/b.mjs" in ligne for ligne in rap["non_juge"])
    assert rap["verdict"] == "PASS"


@sans_node
def test_un_test_rouge_du_produit_rend_fail_et_est_nomme(tmp_path: Path) -> None:
    produit = _produit(tmp_path, TEST_ROUGE)
    section = scripts_node.section(produit)
    assert [e["id"] for e in section["echecs"]] == ["scripts/a.test.mjs::rouge"]
    assert "4 == 5" in section["echecs"][0]["message"]
    rap = rapport([], [], essais=scripts_node.essais_de_la_cible(produit), scripts_node=section)
    assert rap["verdict"] == "FAIL"


@sans_node
def test_un_test_saute_rend_partiel_comme_toute_suite(tmp_path: Path) -> None:
    produit = _produit(tmp_path, TEST_SAUTE)
    essais = scripts_node.essais_de_la_cible(produit)
    assert essais is not None and sorted(e.verdict for e in essais) == ["non_execute", "passant"]
    rap = rapport([], [], essais=essais, scripts_node=scripts_node.section(produit))
    assert rap["verdict"] == "PARTIEL"


@sans_node
def test_l_absence_de_suite_est_publiee_avec_les_scripts_non_couverts(tmp_path: Path) -> None:
    """Seconde voie de la décision : pas de suite, le non-jugé le dit et nomme le code."""
    produit = _produit(tmp_path, None)
    section = scripts_node.section(produit)
    assert section["statut"] == "aucune_suite"
    assert section["non_exerces"] == ["scripts/a.mjs", "scripts/b.mjs"]
    texte = " ".join(section["non_juge"])
    assert "AUCUNE suite" in texte and "n'est PAS couvert" in texte
    assert "scripts/a.mjs" in texte and "scripts/b.mjs" in texte
    assert scripts_node.essais_de_la_cible(produit) is None


@sans_node
def test_deux_tests_homonymes_de_deux_fichiers_gardent_deux_identifiants(tmp_path: Path) -> None:
    produit = _produit(tmp_path, TEST_VERT)
    (produit / "scripts" / "b.test.mjs").write_text(
        'import test from "node:test";\ntest("double", () => {});\n', encoding="utf-8"
    )
    scripts_node._jouer.cache_clear()
    essais = scripts_node.essais_de_la_cible(produit)
    assert essais is not None
    assert sorted(e.id for e in essais) == [
        "scripts/a.test.mjs::double", "scripts/b.test.mjs::double",
    ]


def test_contre_epreuve_un_package_json_ecarte_ce_chemin_et_le_rapport_le_dit(
    tmp_path: Path,
) -> None:
    produit = _produit(tmp_path, TEST_VERT)
    (produit / "package.json").write_text("{}", encoding="utf-8")
    section = scripts_node.section(produit)
    assert section["applicable"] is False and "package.json" in section["motif"]
    assert scripts_node.essais_de_la_cible(produit) is None


def test_contre_epreuve_sans_scripts_le_chemin_est_sans_objet_motive(tmp_path: Path) -> None:
    scripts_node._jouer.cache_clear()
    section = scripts_node.section(tmp_path)
    assert section["applicable"] is False and "aucun `scripts/*.mjs`" in section["motif"]


def test_un_node_absent_est_publie_pas_tu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    produit = _produit(tmp_path, TEST_VERT)
    monkeypatch.setattr(scripts_node.shutil, "which", lambda _nom: None)
    section = scripts_node.section(produit)
    assert section["statut"] == "node_absent"
    assert "`node` introuvable" in " ".join(section["non_juge"])


def test_un_delai_depasse_rend_delai_depasse_avec_son_reglage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    produit = _produit(tmp_path, TEST_VERT)
    monkeypatch.setattr(scripts_node.shutil, "which", lambda _nom: "node-factice")
    monkeypatch.setenv("FORGE_TESTS_DELAI_SCRIPTS_S", "300")

    def lent(commande, **kwargs):
        raise subprocess.TimeoutExpired(commande, kwargs["timeout"])

    monkeypatch.setattr(execution.subprocess, "run", lent)
    section = scripts_node.section(produit)
    assert section["statut"] == "delai_depasse"
    texte = " ".join(section["non_juge"])
    assert "DELAI_DEPASSE" in texte and "(délai 300 s)" in texte
    assert "FORGE_TESTS_DELAI_SCRIPTS_S=600" in texte


@sans_node
def test_l_audit_complet_publie_la_section_dans_le_rapport(tmp_path: Path) -> None:
    """Bout en bout par le point d'entrée de l'audit (aucun pan retenu : seule la section parle)."""
    produit = _produit(tmp_path, TEST_ROUGE)
    rap = cli.analyser(produit, pans=[])
    assert rap["scripts_node"]["applicable"] is True
    assert rap["essais"]["fourni"] is True
    assert [e["id"] for e in rap["scripts_node"]["echecs"]] == ["scripts/a.test.mjs::rouge"]
    # aucun pan retenu = tous les pans attendus non couverts : PARTIEL domine, comme pour tout pan
    # en FAIL (le FAIL net du test rouge est prouvé plus haut, rapport() sans pan non couvert)
    assert rap["verdict"] == "PARTIEL"
    assert any("scripts/b.mjs" in ligne for ligne in rap["non_juge"])


@sans_node
def test_la_reprise_garde_la_section_et_ses_tests_rouges(tmp_path: Path) -> None:
    """`--reprendre` fusionne deux rapports : la section des scripts et son FAIL y survivent."""
    from forge_tests import reprise

    produit = _produit(tmp_path, TEST_ROUGE)
    ancien = rapport([], [], essais=scripts_node.essais_de_la_cible(produit),
                     scripts_node=scripts_node.section(produit))
    fusion = reprise.fusionner(ancien, {}, "rapport.json", [], [])
    assert fusion["scripts_node"]["statut"] == "joue"
    assert [e["id"] for e in fusion["scripts_node"]["echecs"]] == ["scripts/a.test.mjs::rouge"]
    assert fusion["verdict"] == "FAIL"
    assert any("scripts/b.mjs" in ligne for ligne in fusion["non_juge"])
