"""TF-1808 — ETAPE-MEP § 4 exige une copie datée du dashboard de tests sous `output\\`.

Fait remonté par Produit-83 (lot 20261015b, RE-9, ledger seq 160) : le dossier de MEP demande
« le dashboard de tests (copie datée dans `output\\`) », et forge-tests ne la produisait pas.
`--livrables` écrit un dashboard daté, mais HORS du projet (G-1) : le produit devait le
recopier à la main.

Le geste outillé : `--copie-output`, avec `--livrables`, dépose une copie du dashboard daté dans
`<projet>/output/`, sous son nom daté. Seul ce fichier entre dans le projet, et seulement dans
`output/`, que l audit exclut de son périmètre : la forge ne s y audite jamais elle-même. Les
cahiers et le jeu de données restent hors du projet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import __main__ as cli

_RAPPORT_VERT = {
    "adaptateurs": [],
    "couverture_par_pan": {},
    "mutation": {},
    "seuils": {},
    "modules": [],
    "pans_non_couverts": [],
    "pans_sans_objet": [],
    "motifs_non_couverture": {},
    "bandes_de_risque": {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0},
    "findings": [],
    "non_testables": [],
    "actions": [],
    "non_juge": [],
    "essais": {"cas": [], "totaux": {}, "signales": [], "fourni": False},
    "verdict": "PASS",
}


@pytest.fixture
def projet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cible = tmp_path / "produit"
    (cible / "app").mkdir(parents=True)
    (cible / "app" / "main.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(cli, "analyser", lambda c, pans=None: dict(_RAPPORT_VERT))
    monkeypatch.setattr("forge_tests.declarations.appliquer", lambda rapport, cible: None)
    monkeypatch.setenv("FORGE_TESTS_PRODUIT", "Produit-99")
    return cible


def test_copie_output_depose_le_dashboard_date_dans_output(
    projet: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    depot = tmp_path / "depot"
    code = cli.main([str(projet), "--json", "--livrables", str(depot), "--copie-output"])
    err = capsys.readouterr().err
    assert code == cli.SORTIE_OK, err
    copies = sorted((projet / "output").glob("Produit-99 - Dashboard tests - *.html"))
    assert len(copies) == 1
    originaux = sorted(depot.glob("Produit-99 - Dashboard tests - *.html"))
    assert copies[0].name == originaux[0].name
    assert copies[0].read_bytes() == originaux[0].read_bytes()
    assert "copie datee" in err
    # Rien d autre n entre dans le projet : ni cahier, ni jeu de données.
    assert sorted(p.name for p in (projet / "output").iterdir()) == [copies[0].name]


def test_sans_l_option_rien_n_est_ecrit_dans_le_projet(
    projet: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main([str(projet), "--json", "--livrables", str(tmp_path / "depot")])
    capsys.readouterr()
    assert code == cli.SORTIE_OK
    assert not (projet / "output").exists()


def test_copie_output_sans_livrables_est_refusee(
    projet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(projet), "--json", "--copie-output"])
    assert "--livrables" in capsys.readouterr().err
