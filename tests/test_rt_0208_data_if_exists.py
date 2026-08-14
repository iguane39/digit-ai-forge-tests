"""RT-14 / TF-0208 — le pan `data` fabriquait une contrainte FANTÔME nommée `IF`.

Constaté en production, avec preuve : le rapport portait `contrainte:IF`, classée
`element-non-exerce`, sévérité BLOQUANT, risque 75, localisée dans
`backend/migrations/0001_schema_initial.sql`. Aucune contrainte de ce nom n existe : le fichier
contient six `ALTER TABLE … DROP CONSTRAINT IF EXISTS <nom réel>;` et l inventaire retenait le
mot qui suit `CONSTRAINT`, soit `IF`.

Ce qui rend le défaut grave, c est que le conflit était INTERNE à la forge : le pan `migrations`
EXIGE les trois sens (aller / rejeu / retour), donc l idiome idempotent
`DROP CONSTRAINT IF EXISTS x; … ADD CONSTRAINT x …` ; le pan `data` transformait ensuite cet
idiome en défaut bloquant. Aucun projet ne pouvait satisfaire les deux pans à la fois. Et
l action produite était `auto_ia` : la satisfaire aurait demandé de FABRIQUER une contrainte
inexistante pour qu un test la fasse tomber — du truquage, refusé au titre de G-2.

Deux sens prouvés ici :
  - ROUGE — aucune des formes idempotentes (`DROP CONSTRAINT IF EXISTS`,
    `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE TRIGGER IF NOT EXISTS`,
    `CREATE EXTENSION IF NOT EXISTS`), ni leur citation en COMMENTAIRE, n inventorie plus
    d objet nommé `IF`, `NOT` ou `EXISTS` ;
  - VERT — une contrainte réellement nommée reste inventoriée : le correctif ne rend pas le pan
    aveugle, ce qui serait échanger un faux positif contre un faux négatif.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import data

_FANTOMES = {"if", "not", "exists"}


def _migration(racine: Path, sql: str, nom: str = "0001_schema_initial.sql") -> Path:
    fichier = racine / "backend" / "migrations" / nom
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(sql, encoding="utf-8")
    return fichier


def _ids(racine: Path) -> set[str]:
    return {element.id for element in data.inventaire(racine)}


def _fantomes(identifiants: set[str]) -> set[str]:
    """Identifiants dont le NOM est un mot-clé de forme idempotente — jamais un objet réel."""
    return {i for i in identifiants if i.split(":", 1)[1].split(".", 1)[0].lower() in _FANTOMES}


# --- ROUGE : une forme par test, telle que le fichier réel les porte --------------------------
@pytest.mark.parametrize(
    ("libelle", "sql"),
    [
        (
            "DROP CONSTRAINT IF EXISTS — l idiome exigé par le pan migrations",
            "ALTER TABLE facture DROP CONSTRAINT IF EXISTS ck_facture_montant;\n",
        ),
        (
            "CREATE TABLE IF NOT EXISTS",
            "CREATE TABLE IF NOT EXISTS facture (id INTEGER PRIMARY KEY);\n",
        ),
        (
            "CREATE EXTENSION IF NOT EXISTS",
            "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n",
        ),
        (
            "CREATE INDEX IF NOT EXISTS",
            "CREATE INDEX IF NOT EXISTS ix_facture_client ON facture (client_id);\n",
        ),
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_facture_ref ON facture (reference);\n",
        ),
        (
            "CREATE TRIGGER IF NOT EXISTS",
            "CREATE TRIGGER IF NOT EXISTS trg_facture_maj BEFORE UPDATE ON facture\n"
            "FOR EACH ROW EXECUTE FUNCTION touch();\n",
        ),
        (
            "les mêmes formes EN COMMENTAIRE — ligne 5 du fichier réel",
            "-- Schéma initial.\n"
            "-- Idempotence : chaque contrainte est précédée d un\n"
            "-- ALTER TABLE facture DROP CONSTRAINT IF EXISTS ck_facture_montant;\n"
            "/* et chaque table d un CREATE TABLE IF NOT EXISTS facture ( */\n"
            "-- CREATE INDEX IF NOT EXISTS ix_mort ON facture (id);\n",
        ),
    ],
)
def test_aucune_forme_idempotente_ne_fabrique_d_objet_fantome(
    tmp_path: Path, libelle: str, sql: str
) -> None:
    _migration(tmp_path, sql)
    assert _fantomes(_ids(tmp_path)) == set(), libelle


def test_le_commentaire_n_inventorie_rien_du_tout(tmp_path: Path) -> None:
    """Un objet CITÉ dans un commentaire n existe pas : ni fantôme, ni objet réel."""
    _migration(
        tmp_path,
        "-- ALTER TABLE facture DROP CONSTRAINT IF EXISTS ck_facture_montant;\n"
        "-- CREATE TABLE IF NOT EXISTS table_morte (id INTEGER);\n"
        "-- CREATE INDEX IF NOT EXISTS ix_mort ON facture (id);\n",
    )
    assert _ids(tmp_path) == set()


def test_drop_seul_n_annonce_aucune_contrainte(tmp_path: Path) -> None:
    """`DROP CONSTRAINT x` RETIRE x, il ne le crée pas — l inventorier serait un élément que
    plus rien ne peut violer, donc un « jamais exercé » impossible à couvrir. Même règle et même
    motif que `migrations.py`, qui exclut déjà `DROP CONSTRAINT` de ses objets annoncés."""
    _migration(tmp_path, "ALTER TABLE facture DROP CONSTRAINT IF EXISTS ck_facture_montant;\n")
    assert _ids(tmp_path) == set()


def test_idiome_idempotent_complet_inventorie_le_nom_reel_une_seule_fois(tmp_path: Path) -> None:
    """Le cas RÉEL : six `DROP … IF EXISTS` suivis de leur `ADD CONSTRAINT`.

    C est le sens qui compte : la contrainte réellement créée est inventoriée, sous son nom, et
    aucune contrainte `IF` n apparaît — le projet peut enfin satisfaire `data` ET `migrations`.
    """
    lignes = []
    for i in range(1, 7):
        lignes.append(f"ALTER TABLE facture DROP CONSTRAINT IF EXISTS ck_facture_{i};")
        lignes.append(
            f"ALTER TABLE facture ADD CONSTRAINT ck_facture_{i} CHECK (montant_{i} >= 0);"
        )
    _migration(tmp_path, "\n".join(lignes) + "\n")

    identifiants = _ids(tmp_path)
    assert _fantomes(identifiants) == set()
    assert {f"contrainte:ck_facture_{i}" for i in range(1, 7)} <= identifiants
    # Une seule entrée par contrainte : le DROP ne double pas l ADD.
    contraintes = [e for e in data.inventaire(tmp_path) if e.id.startswith("contrainte:")]
    assert len(contraintes) == len({e.id for e in contraintes}) == 6


# --- VERT : le correctif ne rend pas le pan aveugle -------------------------------------------
def test_une_contrainte_reellement_nommee_reste_inventoriee(tmp_path: Path) -> None:
    """Le sens VERT exigé : contrainte inline, contrainte ajoutée, table, index, trigger."""
    _migration(
        tmp_path,
        "CREATE TABLE facture (\n"
        "  id INTEGER PRIMARY KEY,\n"
        "  reference TEXT NOT NULL,\n"
        "  CONSTRAINT ck_facture_reference CHECK (length(reference) > 0)\n"
        ");\n"
        "ALTER TABLE facture ADD CONSTRAINT uq_facture_reference UNIQUE (reference);\n"
        "CREATE INDEX ix_facture_reference ON facture (reference);\n"
        "CREATE TRIGGER trg_facture_maj BEFORE UPDATE ON facture\n"
        "FOR EACH ROW EXECUTE FUNCTION touch();\n",
    )
    identifiants = _ids(tmp_path)
    assert {
        "table:facture",
        "contrainte:ck_facture_reference",
        "contrainte:uq_facture_reference",
        "contrainte:reference.not_null",
        "index:ix_facture_reference",
        "trigger:trg_facture_maj",
    } <= identifiants


def test_les_formes_idempotentes_inventorient_le_vrai_nom(tmp_path: Path) -> None:
    """Le pan devient VOYANT là où il était muet : `CREATE TABLE IF NOT EXISTS` n entrait
    AUCUNE table à l inventaire (la regex exigeait la parenthèse juste après le nom), et
    `CREATE INDEX IF NOT EXISTS` y entrait un index nommé `IF`."""
    _migration(
        tmp_path,
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n"
        "CREATE TABLE IF NOT EXISTS facture (id INTEGER PRIMARY KEY);\n"
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_facture_ref ON facture (reference);\n"
        "CREATE TRIGGER IF NOT EXISTS trg_facture_maj BEFORE UPDATE ON facture\n"
        "FOR EACH ROW EXECUTE FUNCTION touch();\n",
    )
    identifiants = _ids(tmp_path)
    assert _fantomes(identifiants) == set()
    assert {
        "table:facture",
        "index:ux_facture_ref",
        "trigger:trg_facture_maj",
    } <= identifiants


def test_contraintes_declarees_est_le_lecteur_unique(tmp_path: Path) -> None:
    """Le lecteur exposé, exercé directement — la casse du mot-clé n y change rien."""
    assert data.contraintes_declarees(
        "alter table t drop constraint if exists ck_t; "
        "alter table t add constraint ck_t check (v > 0);"
    ) == ["ck_t"]
    assert data.contraintes_declarees("CONSTRAINT ck_inline CHECK (v > 0)") == ["ck_inline"]
    assert data.contraintes_declarees("ALTER TABLE t DROP CONSTRAINT ck_t;") == []
