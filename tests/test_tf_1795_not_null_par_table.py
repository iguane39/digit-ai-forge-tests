"""TF-1795 — le pan data attribuait un NOT NULL par son seul nom de colonne, sans sa table.

Fait remonté par Produit-83 (lot 20261015b, RE-6, ledger seq 126). L inventaire nommait
l élément `contrainte:<colonne>.not_null` : deux tables portant chacune une colonne `nom NOT
NULL` ne faisaient qu UN élément, et la violation levée sur l une couvrait l autre. Une
contrainte jamais violée passait donc pour exercée, dès qu une homonyme l était ailleurs.

La règle corrigée : l élément porte sa table (`contrainte:<table>.<colonne>.not_null`), lue dans
le `CREATE TABLE` qui la déclare (ou le `__tablename__` du modèle), et la violation s attribue
par le couple que le moteur nomme (PostgreSQL « of relation », SQLite « table.colonne »).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import data

MIGRATION = """CREATE TABLE etablissement (
  id INTEGER PRIMARY KEY,
  nom TEXT NOT NULL,
  siret TEXT NOT NULL
);
CREATE TABLE contact (
  id INTEGER PRIMARY KEY,
  nom TEXT NOT NULL
);
"""


def _projet(tmp_path: Path) -> Path:
    (tmp_path / "backend" / "migrations").mkdir(parents=True)
    (tmp_path / "backend" / "migrations" / "0001_init.sql").write_text(
        MIGRATION, encoding="utf-8"
    )
    return tmp_path


def test_deux_colonnes_homonymes_font_deux_elements(tmp_path: Path) -> None:
    ids = {e.id for e in data.inventaire(_projet(tmp_path))}
    assert "contrainte:etablissement.nom.not_null" in ids
    assert "contrainte:contact.nom.not_null" in ids
    assert "contrainte:etablissement.siret.not_null" in ids
    assert "contrainte:nom.not_null" not in ids


@pytest.mark.parametrize(
    "message",
    [
        'null value in column "nom" of relation "contact" violates not-null constraint',
        "NOT NULL constraint failed: contact.nom",
    ],
)
def test_la_violation_ne_couvre_que_la_table_que_le_moteur_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    projet = _projet(tmp_path)
    monkeypatch.setattr(data, "violations_levees", lambda _cible: [message])
    monkeypatch.setattr(data, "instructions_sql", lambda _cible: [])
    couvert = data.exerces(projet)
    assert "contrainte:contact.nom.not_null" in couvert
    assert "contrainte:etablissement.nom.not_null" not in couvert


def test_orm_porte_sa_table(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "models.py").write_text(
        "class Etablissement(Base):\n"
        '    __tablename__ = "etablissement"\n'
        "    nom = Column(String, nullable=False)\n"
        "\n"
        "class Contact(Base):\n"
        '    __tablename__ = "contact"\n'
        "    nom = Column(String, nullable=False)\n",
        encoding="utf-8",
    )
    ids = {e.id for e in data.inventaire(tmp_path)}
    assert {"contrainte:etablissement.nom.not_null", "contrainte:contact.nom.not_null"} <= ids
