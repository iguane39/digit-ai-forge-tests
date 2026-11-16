"""TF-2654 — le pan sécurité comptait des constats dans les dossiers que le rapport déclare exclus.

Fait remonté par Produit-82 (lot 20261113c, RT-37, ledger seq 264 et 265) : le rapport du
13/11/2026 déclarait exclus les dossiers ignorés par git (`perimetre_exclu_git`, TF-1767) et
comptait pourtant 643 de ses 701 constats dans ces dossiers, dont 631 bloquants (`vendor-check` 614,
sauvegardes 21, clients 6, runtime 2). Le filtre de TF-1767 était appliqué aux pans qui parcourent
le projet eux-mêmes ; le pan sécurité copie le projet pour les oracles délégués et ne le lui
appliquait pas.

Trois preuves, dans les deux sens :
  - VERTE : un secret planté dans un dossier ignoré par git n'atteint pas les oracles, le pan ne
    compte aucun constat et reste PASS ;
  - DÉCLARÉE : l'exclusion nomme le dossier dans `non_juge` (une exclusion muette est un angle
    mort) ;
  - ROUGE : un VRAI secret dans le code versionné reste détecté, et le dossier réclamé par son nom
    dans `FORGE_TESTS_INCLURE` est jugé de nouveau.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import exclusions
from forge_tests.adaptateurs import securite

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent du poste")

_SECRET = "AKIAIOSFODNN7EXAMPLE"
#: Les quatre familles du constat du 13/11/2026 : une copie amont, des sauvegardes, des clients,
#: un dossier d'exécution.
_IGNORES = ("vendor-check", "sauvegardes", "clients", "runtime")


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch):
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    monkeypatch.delenv("FORGE_TESTS_INCLURE", raising=False)
    exclusions._CACHE_GIT.clear()


def _registre(racine: Path) -> Path:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "oracle-secrets.mjs").write_text("", encoding="utf-8")
    return racine


def _produit(racine: Path, *, secret_dans_le_produit: bool, depot_git: bool = True) -> Path:
    """Un produit à racine plate : son code, et quatre dossiers que son `.gitignore` écarte."""
    (racine / "app").mkdir(parents=True)
    ligne = f'CLE = "{_SECRET}"\n' if secret_dans_le_produit else "CLE = os.environ['CLE']\n"
    (racine / "app" / "config.py").write_text(ligne, encoding="utf-8")
    for nom in _IGNORES:
        (racine / nom / "amont").mkdir(parents=True)
        (racine / nom / "amont" / "cle.py").write_text(f'CLE = "{_SECRET}"\n', encoding="utf-8")
    (racine / ".gitignore").write_text("".join(f"{n}/\n" for n in _IGNORES), encoding="utf-8")
    if depot_git:
        subprocess.run(["git", "init", "-q", str(racine)], check=True)
    exclusions._CACHE_GIT.clear()
    return racine


def _oracle_secrets(script: Path, scan: Path) -> dict:
    """Rejoue le contrat d'`oracle-secrets` sur CE QU'IL REÇOIT, sans node ni réseau."""
    findings = [
        {"sev": "bloquant", "msg": "secret probable : clé d'accès AWS", "where": str(fichier)}
        for fichier in sorted(Path(scan).rglob("*"))
        if fichier.is_file() and _SECRET in fichier.read_text(encoding="utf-8", errors="ignore")
    ]
    return {"verdict": "FAIL" if findings else "PASS", "findings": findings, "non_juge": []}


def _analyser(cible: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _oracle_secrets)
    return securite.analyser(cible)


def _localisations(sortie) -> list[str]:
    return sorted(f.localisation.replace("\\", "/") for f in sortie.findings)


def test_aucun_constat_des_dossiers_ignores_par_git_n_est_compte(tmp_path, monkeypatch):
    """Le cas du 13/11 : des constats comptés dans le périmètre déclaré exclu, désormais 0."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert sortie.findings == [], _localisations(sortie)
    assert sortie.verdict == "PASS"
    assert not [f for f in sortie.findings if f.severite == "bloquant"]


def test_l_exclusion_nomme_chaque_dossier_ignore(tmp_path, monkeypatch):
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    mesures = [ligne for ligne in sortie.non_juge if "ignorés par git" in ligne]
    assert mesures, sortie.non_juge
    for nom in _IGNORES:
        assert nom in mesures[0], mesures[0]
    assert "FORGE_TESTS_INCLURE" in mesures[0]


def test_un_vrai_secret_du_code_versionne_reste_detecte(tmp_path, monkeypatch):
    """La contrepartie qui rend l'exclusion défendable : on n'a pas acheté du silence."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=True)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert sortie.verdict == "FAIL"
    localisations = _localisations(sortie)
    assert len(localisations) == 1, localisations
    assert localisations[0].endswith("app/config.py"), localisations


def test_le_dossier_reclame_par_son_nom_est_juge_de_nouveau(tmp_path, monkeypatch):
    """Le geste explicite du projet (`FORGE_TESTS_INCLURE`) réintègre le dossier au scan."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)
    monkeypatch.setenv("FORGE_TESTS_INCLURE", "vendor-check")
    exclusions._CACHE_GIT.clear()

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert len(sortie.findings) == 1
    assert "vendor-check" in sortie.findings[0].localisation.replace("\\", "/")
    assert sortie.verdict == "FAIL"


def test_les_manifestes_d_un_dossier_ignore_ne_sont_pas_remis_a_oracle_sca(tmp_path):
    """Même périmètre pour SCA : le `package.json` de `vendor-check` n'est pas celui du produit."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)
    (cible / "package.json").write_text("{}", encoding="utf-8")
    (cible / "vendor-check" / "package.json").write_text("{}", encoding="utf-8")
    origine: dict[str, Path] = {}

    brouillon = tmp_path / "brouillon"
    brouillon.mkdir()
    securite._manifestes_du_produit([cible], brouillon, origine)

    assert sorted(origine) == ["package.json"]


def test_hors_depot_git_rien_ne_change(tmp_path, monkeypatch):
    """Sans dépôt git, aucune information : le dossier reste soumis à la politique du pan."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False, depot_git=False)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert len(sortie.findings) == len(_IGNORES)
