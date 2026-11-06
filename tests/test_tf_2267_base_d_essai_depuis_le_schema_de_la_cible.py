"""TF-2267 — une base d'essai se construit depuis le schéma de la CIBLE, pas du jeu fictif.

Fait remonté (Produit-81, lot 20261106a, RP-3) : un script SQL de données validé deux fois sur une
base SQL Server jetable reconstruite d'après le jeu fictif (979 lignes posées, puis 0) a échoué sur
la cible réelle, Msg 544 : `ID_TRADUCTION_LIB` est une colonne d'identité dans la base D1, pas dans
la base jetable. Un run de chaîne en échec et un second lancement.

Décision du 06/11/2026 : la base d'essai se construit depuis le schéma de la cible (relevé
INFORMATION_SCHEMA ou extraction), jamais depuis le jeu fictif ; la règle est écrite au guide de la
forge (README) et jouée là où la forge prépare une base d'essai (`fabrique_donnees`).

Sens prouvés :
  - ROUGE  — le cas du lot : la colonne d'identité de la cible est une simple colonne dans les
             migrations ; la fabrique REFUSE avant d'écrire, et nomme la colonne et le Msg 544 ;
  - VERT   — un relevé conforme au schéma d'essai laisse fabriquer ; le rapport dit l'origine du
             schéma (migrations du projet, relevé de la cible comparé ou non) ;
  - un relevé illisible est refusé, jamais lu comme vide ; la règle est écrite au README.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests import fabrique_donnees as fabrique
from forge_tests import schema_cible, schema_sql

MIGRATION = (
    "-- +migrate Up\n"
    "CREATE TABLE traduction_lib (\n"
    "  id_traduction_lib INTEGER PRIMARY KEY,\n"
    "  libelle VARCHAR(80) NOT NULL,\n"
    "  note VARCHAR(80)\n"
    ");\n"
    "-- +migrate Down\n"
    "DROP TABLE traduction_lib;\n"
)


def _projet(racine: Path) -> Path:
    projet = racine / "projet"
    (projet / "backend" / "migrations").mkdir(parents=True)
    (projet / "backend" / "migrations" / "001_init.sql").write_text(MIGRATION, encoding="utf-8")
    return projet


def _releve(racine: Path, lignes: list[dict]) -> Path:
    chemin = racine / "releve.json"
    chemin.write_text(json.dumps(lignes), encoding="utf-8")
    return chemin


CONFORME = [
    {"table": "TRADUCTION_LIB", "colonne": "ID_TRADUCTION_LIB", "type": "int",
     "nullable": "NO", "identite": 0},
    {"table": "TRADUCTION_LIB", "colonne": "LIBELLE", "type": "varchar", "nullable": "NO",
     "identite": 0},
    {"table": "TRADUCTION_LIB", "colonne": "NOTE", "type": "varchar", "nullable": "YES",
     "identite": 0},
]
IDENTITE_DE_LA_CIBLE = [
    {**CONFORME[0], "identite": 1}, *CONFORME[1:],
]


def test_rouge_la_colonne_d_identite_de_la_cible_est_nommee_avant_toute_ecriture(
    tmp_path: Path,
) -> None:
    """Le cas du lot : l'identité n'existe que dans la cible. La fabrique refuse et n'écrit rien."""
    projet = _projet(tmp_path)
    releve = _releve(tmp_path, IDENTITE_DE_LA_CIBLE)
    sortie = tmp_path / "hors" / "jeu.sql"
    with pytest.raises(fabrique.SchemaEcarteDeLaCible) as refus:
        fabrique.produire(projet, sortie, chargement=False, schema_cible=releve)
    message = str(refus.value)
    assert "ID_TRADUCTION_LIB" in message and "IDENTITÉ" in message and "Msg 544" in message
    assert not sortie.exists(), "le jeu a été écrit malgré l'écart de schéma"


def test_rouge_un_not_null_de_la_cible_absent_du_schema_d_essai(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    lignes = [*CONFORME[:2], {**CONFORME[2], "nullable": "NO"}]
    with pytest.raises(fabrique.SchemaEcarteDeLaCible, match="NOT NULL dans la cible"):
        fabrique.produire(projet, tmp_path / "hors" / "j.sql", chargement=False,
                          schema_cible=_releve(tmp_path, lignes))


def test_rouge_une_colonne_de_la_cible_absente_du_schema_d_essai(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    lignes = [*CONFORME, {"table": "TRADUCTION_LIB", "colonne": "LANGUE", "type": "char",
                          "nullable": "NO", "identite": 0}]
    with pytest.raises(fabrique.SchemaEcarteDeLaCible, match="LANGUE"):
        fabrique.produire(projet, tmp_path / "hors" / "j.sql", chargement=False,
                          schema_cible=_releve(tmp_path, lignes))


def test_vert_un_releve_conforme_laisse_fabriquer_et_l_origine_est_dite(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    rapport = fabrique.produire(projet, tmp_path / "hors" / "jeu.sql", chargement=False,
                                schema_cible=_releve(tmp_path, CONFORME))
    assert (tmp_path / "hors" / "jeu.sql").is_file()
    assert "relevé de la cible" in rapport["schema_origine"]
    assert "comparé" in rapport["schema_origine"]
    assert any("schema cible" in ligne for ligne in rapport["non_juge"])


def test_sans_releve_l_origine_est_dite_et_le_manque_est_nomme(tmp_path: Path) -> None:
    """Sans relevé, la fabrique n'invente rien mais ne prétend pas avoir comparé : elle le dit."""
    projet = _projet(tmp_path)
    rapport = fabrique.produire(projet, tmp_path / "hors" / "jeu.sql", chargement=False)
    assert "migrations du projet" in rapport["schema_origine"]
    assert "NON relevé sur la cible" in rapport["schema_origine"]
    assert schema_cible.VARIABLE in rapport["schema_origine"]


def test_le_releve_peut_etre_designe_par_la_variable_d_environnement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projet = _projet(tmp_path)
    monkeypatch.setenv(schema_cible.VARIABLE, str(_releve(tmp_path, IDENTITE_DE_LA_CIBLE)))
    with pytest.raises(fabrique.SchemaEcarteDeLaCible):
        fabrique.produire(projet, tmp_path / "hors" / "j.sql", chargement=False)


@pytest.mark.parametrize("contenu", ["pas du json", "[]", '[{"table": "T"}]',
                                     '[{"table": "T", "colonne": "C", "nullable": "peut-être"}]'])
def test_un_releve_illisible_est_refuse_jamais_lu_comme_vide(
    tmp_path: Path, contenu: str
) -> None:
    chemin = tmp_path / "releve.json"
    chemin.write_text(contenu, encoding="utf-8")
    with pytest.raises(schema_cible.ReleveIllisible):
        schema_cible.lire_releve(chemin)


def test_l_ecart_d_identite_inverse_est_releve(tmp_path: Path) -> None:
    """La cible n'a pas l'identité que la base d'essai a : l'essai refuserait ce qu'elle accepte."""
    projet = _projet(tmp_path)
    schema = schema_sql.lire(projet)
    colonne = schema.tables["traduction_lib"].colonnes["id_traduction_lib"]
    colonne.auto = "identite_toujours"
    constats = schema_cible.ecarts(schema, schema_cible.lire_releve(_releve(tmp_path, CONFORME)))
    assert len(constats) == 1 and "identité dans le schéma d'essai" in constats[0]


def test_la_regle_est_ecrite_au_guide_de_la_forge() -> None:
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "jamais depuis le jeu fictif" in readme
    assert schema_cible.VARIABLE in readme
