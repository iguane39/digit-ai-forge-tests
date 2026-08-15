"""TF-0256 — les adaptateurs `migrations` et `data` etaient AVEUGLES a la racine plate.

Fait mesure (lot du 15/08/2026) : un produit a RACINE PLATE dont les migrations vivent en
`<cible>\\migrations` et le paquet en `<cible>\\app`. TF-0216 avait dote la forge d une
decouverte de racine d execution (`forge_tests.disposition`), consommee par `execution.py`,
`securite`, `api`, `batch`, `fichiers`, `mutation` — mais PAS par ces deux pans-la, restes
ancres sur `<cible>/backend/migrations` et `<cible>/backend/app`.

Consequence constatee : inventaire VIDE des deux cotes, donc SKIP « aucune migration a
inventorier » / « aucune migration SQL ni contrainte ORM a inventorier », et les 37 tests de
violation de contraintes REELLEMENT joues par le produit n etaient credites a rien. Un faux
negatif de l auditeur, jamais un trou de l audite.

ROUGE avant correctif : chaque test de `TestRacinePlate` echouait (listes vides, inventaires
vides, aucune contrainte creditee). VERT apres : la surface est vue et creditee.
La classe `TestNonRegressionBackend` prouve l autre sens — la disposition historique `backend\\`
rend exactement les memes chemins qu avant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import data, migrations

_MIGRATION = """-- +migrate Up
CREATE TABLE facture (
    id INTEGER PRIMARY KEY,
    numero TEXT NOT NULL,
    CONSTRAINT uq_facture_numero UNIQUE (numero)
);

-- +migrate Down
DROP TABLE facture;
"""

_MODELES = """from sqlalchemy import Column, Integer, String, UniqueConstraint


class Facture(Base):
    id = Column(Integer, primary_key=True)
    numero = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("numero", name="uq_facture_numero"),)
"""


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    """Aucun test ne doit dependre de la variable posee par la machine qui le joue."""
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _arborescence(socle: Path) -> None:
    """Le squelette commun aux deux dispositions, pose sous `socle` (racine d execution)."""
    socle.mkdir(parents=True, exist_ok=True)
    (socle / "app").mkdir()
    (socle / "app" / "__init__.py").write_text("", encoding="utf-8")
    (socle / "app" / "models.py").write_text(_MODELES, encoding="utf-8")
    (socle / "tests").mkdir()
    (socle / "tests" / "test_facture.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (socle / "pyproject.toml").write_text("[project]\nname = 'compta'\n", encoding="utf-8")
    (socle / "migrations").mkdir()
    (socle / "migrations" / "0001_facture.sql").write_text(_MIGRATION, encoding="utf-8")


def _racine_plate(racine: Path) -> Path:
    """Le produit du constat : `app\\`, `tests\\`, `migrations\\` a la RACINE, sans `backend\\`."""
    _arborescence(racine)
    return racine


def _disposition_backend(racine: Path) -> Path:
    """La disposition historique : tout sous `backend\\` (celle de `fixtures/banc-vert`)."""
    _arborescence(racine / "backend")
    return racine


class TestRacinePlate:
    """Ce que le pan voyait : rien. Ce qu il doit voir : la surface reelle du produit."""

    def test_les_migrations_sql_de_la_racine_plate_sont_trouvees(self, tmp_path):
        cible = _racine_plate(tmp_path)
        # ROUGE : `<cible>/backend/migrations` n existe pas ici — la liste etait vide.
        assert [f.name for f in migrations._fichiers(cible)] == ["0001_facture.sql"]

    def test_le_pan_migrations_inventorie_les_trois_sens(self, tmp_path):
        cible = _racine_plate(tmp_path)
        inv = migrations.inventaire(cible)
        assert sorted(e.id for e in inv) == [
            "migration:0001_facture:aller",
            "migration:0001_facture:rejeu",
            "migration:0001_facture:retour",
        ]

    def test_le_motif_d_absence_nomme_la_racine_reellement_regardee(self, tmp_path, monkeypatch):
        """Un motif qui accuse `<cible>/backend/migrations` sur un projet plat envoie chercher
        un dossier que le produit n a aucune raison d avoir."""
        cible = tmp_path
        (cible / "app").mkdir()
        (cible / "app" / "m.py").write_text("X = 1\n", encoding="utf-8")
        (cible / "tests").mkdir()
        monkeypatch.setattr(migrations, "instructions_sql", lambda c: ["SELECT 1"])
        monkeypatch.setattr(migrations, "sources_sql", lambda c: ["sqlite3"])

        motif = migrations._motif_sans_migration(cible)

        assert str(cible / "migrations") in motif
        assert str(cible / "backend" / "migrations") not in motif

    def test_les_versions_alembic_de_la_racine_plate_sont_trouvees(self, tmp_path):
        cible = _racine_plate(tmp_path)
        versions = cible / "app" / "alembic" / "versions"
        versions.mkdir(parents=True)
        (versions / "0001_init.py").write_text(
            "def upgrade(): pass\ndef downgrade(): pass\n", encoding="utf-8"
        )
        # ROUGE : seuls `backend/app/alembic/versions`, `backend/alembic/versions` et
        # `alembic/versions` etaient essayes — `app/alembic/versions` n etait jamais atteint.
        assert [p.name for p in migrations._versions_alembic(cible)] == ["0001_init.py"]

    def test_le_pan_data_inventorie_la_surface_de_la_racine_plate(self, tmp_path):
        cible = _racine_plate(tmp_path)
        ids = {e.id for e in data.inventaire(cible)}
        # ROUGE : inventaire VIDE, donc SKIP « aucune migration SQL ni contrainte ORM ».
        assert "table:facture" in ids
        assert "contrainte:uq_facture_numero" in ids
        assert "contrainte:numero.not_null" in ids

    def test_les_modeles_orm_de_la_racine_plate_sont_lus(self, tmp_path):
        cible = _racine_plate(tmp_path)
        assert data._fichiers_modeles(cible) == [cible / "app" / "models.py"]

    def test_une_violation_reelle_est_creditee_sur_racine_plate(self, tmp_path, monkeypatch):
        """Le coeur du constat : 37 tests de violation existaient, aucun n etait credite."""
        cible = _racine_plate(tmp_path)
        monkeypatch.setattr(
            data,
            "violations_levees",
            lambda c: ['violates unique constraint "uq_facture_numero"'],
        )
        monkeypatch.setattr(
            data, "instructions_sql", lambda c: ["CREATE TABLE facture (id INTEGER)"]
        )

        couvert = data.exerces(cible)

        # ROUGE : `inventaire` etant vide, la contrainte n existait pas pour la forge et la
        # violation reellement levee par le moteur n etait imputee a rien.
        assert "contrainte:uq_facture_numero" in couvert
        assert "table:facture" in couvert


class TestNonRegressionBackend:
    """La disposition historique rend EXACTEMENT les memes chemins qu avant le correctif."""

    def test_les_migrations_de_backend_restent_trouvees(self, tmp_path):
        cible = _disposition_backend(tmp_path)
        trouves = migrations._fichiers(cible)
        assert trouves == [cible / "backend" / "migrations" / "0001_facture.sql"]

    def test_le_pan_data_inventorie_toujours_depuis_backend(self, tmp_path):
        cible = _disposition_backend(tmp_path)
        ids = {e.id for e in data.inventaire(cible)}
        assert "table:facture" in ids
        assert "contrainte:uq_facture_numero" in ids

    def test_les_modeles_de_backend_restent_lus(self, tmp_path):
        cible = _disposition_backend(tmp_path)
        assert data._fichiers_modeles(cible) == [cible / "backend" / "app" / "models.py"]

    def test_backend_l_emporte_quand_les_deux_dispositions_coexistent(self, tmp_path):
        """Monorepo : des migrations sous `backend\\` ET a la racine — `backend\\` prime, comme
        l ordre de `disposition._ORDRE_CANDIDATS` l impose."""
        cible = _disposition_backend(tmp_path)
        (cible / "migrations").mkdir()
        (cible / "migrations" / "9999_leurre.sql").write_text(_MIGRATION, encoding="utf-8")
        assert [f.name for f in migrations._fichiers(cible)] == ["0001_facture.sql"]
