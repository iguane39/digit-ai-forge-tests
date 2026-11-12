"""TF-2403 — le pan `securite` ne voyait pas les avis des dépendances d'un front rangé hors de la
racine d'exécution.

Fait remonté par la campagne du 10/11/2026 : `oracle-sca` joué à la main sur le banc vert voyait
quatre avis publiés (`vite` 5.4.21 x3, `react-router-dom` 6.30.4 x1), le pan `securite` en mode
vif n'en rendait aucun, « cause non élucidée ».

Cause mesurée le 12/11/2026 : le pan copie et fait lire à ses trois oracles la seule RACINE
D'EXÉCUTION du projet (`backend/` sur le banc vert, `disposition.racine_execution`). Un produit
dont le front vit à côté (`frontend/package.json` et son verrou) voyait donc ses dépendances npm
hors du périmètre de l'audit : ni lues, ni avis, ni mention au `non_juge`. Un audit de sécurité
vert sur des avis connus est un faux négatif. Le défaut ne tenait pas au calendrier ni aux avis
retenus : l'oracle lancé sur `frontend/` rendait FAIL, le pan ne le lui demandait jamais.

Correction : `oracle-sca` reçoit les MANIFESTES de dépendances de la racine du PROJET (`cible`),
copiés sans les dossiers de dépendances ; `sast` et `secrets` gardent la racine d'exécution (c'est
du code source, et le périmètre élargi lui ferait lire les bancs et les livrables du dépôt).

Sens prouvés :
  - ROUGE  — un `frontend/package.json` à côté de `backend/` n'était jamais remis à l'oracle ;
  - VERT   — il l'est, le finding est localisé sur le chemin RÉEL du manifeste, et le `non_juge`
             nomme les manifestes remis ;
  - CONTRE-ÉPREUVES — un projet sans manifeste hors racine reste PASS ; un manifeste rangé sous
             `node_modules` n'est jamais remis ; un projet plat garde son manifeste ; deux
             manifestes de même nom, dans deux dossiers, restent deux findings distincts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite

# Un `oracle-sca` factice qui reproduit le seul comportement dont ce test dépend : l'oracle réel
# parcourt le dossier reçu en profondeur, écarte les dossiers de dépendances, et rend un finding
# bloquant par `package.json` lu, localisé relativement au dossier reçu (`where`).
_ORACLE_SCA = """\
import fs from 'node:fs';
import path from 'node:path';
const ECARTES = ['node_modules', '.git', '.venv', 'venv', 'dist', 'build', 'fixtures'];
const lus = [];
const chercher = (dir) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ECARTES.includes(e.name)) continue;
    const fp = path.join(dir, e.name);
    if (e.isDirectory()) chercher(fp); else if (e.name === 'package.json') lus.push(fp);
  }
};
chercher(process.argv[2]);
const findings = lus.map((f) => ({
  sev: 'bloquant',
  msg: 'npm vite@5.4.21 : GHSA-4w7w-66w2-5vf9',
  where: path.relative(process.argv[2], f).split(path.sep).join('/'),
}));
process.stdout.write(JSON.stringify({
  oracle: 'oracle-sca', verdict: findings.length ? 'FAIL' : 'PASS', findings, non_juge: [],
}));
"""


@pytest.fixture
def registre(tmp_path: Path, monkeypatch) -> Path:
    racine = tmp_path / "oracles"
    racine.mkdir()
    (racine / "oracle-sca.mjs").write_text(_ORACLE_SCA, encoding="utf-8")
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    monkeypatch.setattr(securite, "_racine_oracles", lambda: racine)
    return racine


def _backend(produit: Path) -> None:
    """Un produit dont la racine d'exécution est `backend/` (indices : tests/, pyproject.toml)."""
    (produit / "backend" / "app").mkdir(parents=True)
    (produit / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (produit / "backend" / "tests").mkdir()
    (produit / "backend" / "pyproject.toml").write_text("[project]\nname='p'\n", encoding="utf-8")


def _sca(sortie) -> list:
    return [f for f in sortie.findings if f.id.startswith("securite:sca:")]


def test_rouge_les_dependances_d_un_front_hors_de_la_racine_d_execution_sont_auditees(
    tmp_path: Path, registre: Path
) -> None:
    """Le défaut mesuré : `frontend/` à côté de `backend/`, jamais remis à oracle-sca."""
    produit = tmp_path / "produit"
    _backend(produit)
    (produit / "frontend").mkdir()
    (produit / "frontend" / "package.json").write_text('{"name":"f"}', encoding="utf-8")

    sortie = securite.analyser(produit)

    sca = _sca(sortie)
    assert len(sca) == 1, "le package.json du front doit parvenir à oracle-sca"
    assert sca[0].severite == "bloquant"
    assert sortie.verdict == "FAIL"
    # Le chemin publié est celui du projet audité, jamais un dossier temporaire détruit.
    assert Path(sca[0].localisation) == produit / "frontend" / "package.json"
    assert "forge-tests-securite-" not in sca[0].localisation


def test_le_non_juge_nomme_les_manifestes_remis_a_oracle_sca(
    tmp_path: Path, registre: Path
) -> None:
    """Une lecture se DIT : sans elle, « aucun avis » ne se distingue pas de « jamais lu »."""
    produit = tmp_path / "produit"
    _backend(produit)
    (produit / "frontend").mkdir()
    (produit / "frontend" / "package.json").write_text('{"name":"f"}', encoding="utf-8")

    sortie = securite.analyser(produit)

    ligne = [n for n in sortie.non_juge if "manifestes de dependances remis a oracle-sca" in n]
    assert len(ligne) == 1
    assert "frontend/package.json" in ligne[0]


def test_vert_sans_manifeste_hors_racine_le_pan_reste_pass(tmp_path: Path, registre: Path) -> None:
    """Contre-épreuve : rien à lire hors de `backend/`, le pan ne s'accuse de rien."""
    produit = tmp_path / "produit"
    _backend(produit)

    sortie = securite.analyser(produit)

    assert _sca(sortie) == []
    assert sortie.verdict == "PASS"
    assert not any("manifestes de dependances remis" in n for n in sortie.non_juge)


def test_vert_un_manifeste_de_dependance_installee_n_est_jamais_remis(
    tmp_path: Path, registre: Path
) -> None:
    """Contre-épreuve : le périmètre s'élargit aux manifestes DU PRODUIT, pas à ceux de ses
    dépendances (`node_modules`, `.venv`, `vendor`) — ils ne sont ni son code ni son risque."""
    produit = tmp_path / "produit"
    _backend(produit)
    for dossier in ("frontend/node_modules/vite", "vendor/lib", ".venv/Lib/site-packages/x"):
        (produit / dossier).mkdir(parents=True)
        (produit / dossier / "package.json").write_text('{"name":"tiers"}', encoding="utf-8")

    sortie = securite.analyser(produit)

    assert _sca(sortie) == []
    assert sortie.verdict == "PASS"


def test_un_projet_plat_garde_son_manifeste(tmp_path: Path, registre: Path) -> None:
    """Non-régression : la racine d'exécution EST la racine du projet (projet plat)."""
    produit = tmp_path / "produit"
    (produit / "tests").mkdir(parents=True)
    (produit / "pyproject.toml").write_text("[project]\nname='p'\n", encoding="utf-8")
    (produit / "app.py").write_text("x = 1\n", encoding="utf-8")
    (produit / "package.json").write_text('{"name":"plat"}', encoding="utf-8")

    sortie = securite.analyser(produit)

    sca = _sca(sortie)
    assert len(sca) == 1
    assert Path(sca[0].localisation) == produit / "package.json"


def test_deux_manifestes_de_meme_nom_donnent_deux_findings_distincts(
    tmp_path: Path, registre: Path
) -> None:
    """L'identifiant d'un finding se construit sur sa localisation : sans chemin complet, deux
    `package.json` de deux dossiers porteraient le même identifiant et l'un masquerait l'autre."""
    produit = tmp_path / "produit"
    _backend(produit)
    for dossier in ("frontend", "admin"):
        (produit / dossier).mkdir()
        (produit / dossier / "package.json").write_text('{"name":"x"}', encoding="utf-8")

    sca = _sca(securite.analyser(produit))

    assert len(sca) == 2
    assert len({f.id for f in sca}) == 2
