"""TF-0280 — le code VENDORISE n etait pas exclu du pan securite, et lui seul.

Fait mesure (etude 20260815e, verdict O2) : `tests/vendor/axe.min.js` — axe-core EPINGLE, copie
dans le depot pour figer sa version, jamais servi ni modifie — produisait a lui seul 114 constats
du pan securite (112 secrets, 2 SAST). Un rapport dont le lecteur doit ecarter la quasi-totalite
a la main avant d apercevoir le produit ne se lit plus : c est le meme defaut que RT-9 (les
dependances de `.venv` imputees au produit), a un dossier pres.

Le contrat existait deja partout ailleurs — forge-development exclut `vendor/` de ses gates
(`extend-exclude = ["vendor"]`, « code tiers epingle »), les pans `interface` et `prompts` de
cette forge l excluent aussi. Le pan securite etait le SEUL a le tendre encore aux oracles.

Trois preuves, dans les deux sens :
  - VERTE : le vendored n atteint pas les oracles — il n est pas dans la copie filtree ;
  - DECLAREE : l exclusion est publiee en `non_juge` et NOMME le dossier ecarte. Une exclusion
    silencieuse rendrait « rien a signaler dans le vendored » indiscernable de « le vendored n a
    jamais ete lu » ;
  - ROUGE : un VRAI secret dans du code PRODUIT reste detecte. C est la contrepartie qui rend
    l exclusion defendable — sans elle, on aurait achete du silence, pas de la lisibilite.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite

# Un secret de la forme que `oracle-secrets` reconnait (cle d acces AWS), pose deux fois : dans
# une dependance vendorisee, et dans le code du produit.
_SECRET = "AKIAIOSFODNN7EXAMPLE"


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _registre(racine: Path) -> Path:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "oracle-secrets.mjs").write_text("", encoding="utf-8")
    return racine


def _produit(racine: Path, *, secret_dans_le_produit: bool) -> Path:
    """Un produit avec sa dependance vendorisee — et, au choix, un vrai secret a lui."""
    (racine / "backend" / "app").mkdir(parents=True)
    ligne = f'CLE = "{_SECRET}"\n' if secret_dans_le_produit else "CLE = os.environ['CLE']\n"
    (racine / "backend" / "app" / "config.py").write_text(ligne, encoding="utf-8")
    (racine / "backend" / "tests" / "vendor").mkdir(parents=True)
    (racine / "backend" / "tests" / "vendor" / "axe.min.js").write_text(
        f'var t="{_SECRET}";\n', encoding="utf-8"
    )
    return racine


def _oracle_secrets(script: Path, scan: Path) -> dict:
    """Rejoue le contrat d `oracle-secrets` sur CE QU IL RECOIT — sans node, sans reseau.

    Le defaut ne vit pas dans l oracle mais dans ce qu on lui tend : ce faux oracle lit donc
    reellement l arborescence copiee, il ne recite pas une reponse ecrite d avance.
    """
    findings = [
        {"sev": "bloquant", "msg": "secret probable : cle d'acces AWS", "where": str(fichier)}
        for fichier in sorted(Path(scan).rglob("*"))
        if fichier.is_file() and _SECRET in fichier.read_text(encoding="utf-8", errors="ignore")
    ]
    return {
        "verdict": "FAIL" if findings else "PASS",
        "findings": findings,
        "non_juge": [],
    }


def _analyser(cible: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _oracle_secrets)
    return securite.analyser(cible)


def test_le_vendored_n_atteint_jamais_les_oracles(tmp_path):
    """La copie filtree est le seul levier qui ne reecrit pas l outil delegue (R3)."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)
    application = cible / "backend"

    with tempfile.TemporaryDirectory() as brouillon:
        scan = securite._sources_du_produit(application, Path(brouillon))

        copies = {p.name for p in scan.rglob("*") if p.is_file()}

    assert "axe.min.js" not in copies, copies
    assert "config.py" in copies, copies


def test_l_exclusion_est_declaree_et_nomme_le_dossier(tmp_path, monkeypatch):
    """ROUGE de la declaration : une exclusion muette est un angle mort, pas un perimetre."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    declarations = [ligne for ligne in sortie.non_juge if "VENDORISE" in ligne]
    assert declarations, sortie.non_juge
    assert "vendor" in declarations[0], declarations[0]


def test_le_vendored_ne_produit_plus_aucun_constat(tmp_path, monkeypatch):
    """ROUGE avant correctif : 1 constat ici, 114 sur le depot reel."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=False)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert not sortie.findings, [f.localisation for f in sortie.findings]
    assert sortie.verdict == "PASS", sortie.verdict


def test_un_vrai_secret_du_produit_reste_detecte(tmp_path, monkeypatch):
    """La contrepartie non negociable : on a achete de la lisibilite, jamais du silence."""
    cible = _produit(tmp_path / "produit", secret_dans_le_produit=True)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert sortie.verdict == "FAIL", sortie.verdict
    assert len(sortie.findings) == 1, [f.localisation for f in sortie.findings]
    assert "config.py" in sortie.findings[0].localisation, sortie.findings[0].localisation


def test_aucune_declaration_quand_il_n_y_a_rien_a_exclure(tmp_path, monkeypatch):
    """Declarer une exclusion qui n a rien exclu serait du bruit — et un rapport se lit."""
    cible = tmp_path / "produit"
    (cible / "backend" / "app").mkdir(parents=True)
    (cible / "backend" / "app" / "config.py").write_text("CLE = 1\n", encoding="utf-8")

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert not [ligne for ligne in sortie.non_juge if "VENDORISE" in ligne], sortie.non_juge
