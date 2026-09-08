"""TF-0840 — les cas générés du pan `data` passaient sur une erreur de SYNTAXE SQL.

LE FAIT (lot Produit-61, retour du 05/09/2026). `output/<projet>-cas/test_genere_data.py` a été
relu à la main : **56 cas réécrits**. Ils passaient tous, et aucun ne mesurait sa contrainte.
Quatre défauts en série, dont le dernier masquait les trois autres :

1. le nom de table était lu par `bloc.split("(")` juste après `CREATE TABLE` — sur un schéma
   écrit `CREATE TABLE IF NOT EXISTS commande (…)`, cela donnait la table « IF NOT EXISTS
   commande », donc `INSERT INTO IF NOT EXISTS commande (…)` : une erreur de SYNTAXE ;
2. l en-tête généré exigeait une fixture `moteur` qui n existait nulle part chez le projet ;
3. il démolissait trois tables NOMMÉES EN DUR (`ligne_commande`, `commande`, `utilisateur`) par
   un `DROP TABLE … CASCADE` que tous les moteurs n acceptent pas ;
4. `_violer` attendait `pytest.raises(Exception)` — **n importe quelle** exception. Une erreur
   de syntaxe, une fixture absente, une table inconnue : le cas passait au vert.

Le quatrième est le seul qui compte vraiment : c est le contrat du cas. Tant qu il accepte
`Exception`, aucun des trois autres ne peut se voir, et le générateur peut produire n importe
quoi. Le remède : `IntegrityError`, et un message qui nomme la contrainte, sa colonne ou au
moins sa NATURE.

Ces cas jouent le SQL produit contre un vrai moteur — `sqlite3`, de la bibliothèque standard —
plutôt que de le comparer à une chaîne attendue. Un SQL qu on n exécute pas est exactement ce
qui a coûté les 56 relectures.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from forge_tests import generateur_data

#: Un schéma volontairement écrit comme celui qui a fait tomber le générateur : `IF NOT EXISTS`,
#: des colonnes `NOT NULL` sans défaut, une clé étrangère et un `CHECK` par liste.
_MIGRATION = """-- +migrate Up
CREATE TABLE IF NOT EXISTS utilisateur (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL,
  mot_de_passe_hash TEXT NOT NULL,
  actif INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT utilisateur_email_unique UNIQUE (email)
);
CREATE TABLE IF NOT EXISTS commande (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  utilisateur_id INTEGER NOT NULL,
  statut TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  CONSTRAINT commande_statut_check CHECK (statut IN ('brouillon','validee','annulee')),
  CONSTRAINT commande_utilisateur_fk FOREIGN KEY (utilisateur_id) REFERENCES utilisateur (id)
);

-- +migrate Down
DROP TABLE commande;
DROP TABLE utilisateur;
"""

_CONTRAINTES = (
    "utilisateur_email_unique",
    "commande_statut_check",
    "commande_utilisateur_fk",
    "email.not_null",
)

#: `_violer(base, "<sql>", (<indices>))` — tel que le gabarit `_CAS` l écrit.
_APPEL = re.compile(r'_violer\(base, "(?P<sql>.*)", \((?P<indices>.*)\)\)')


@pytest.fixture()
def projet(tmp_path: Path) -> Path:
    migrations = tmp_path / "backend" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_socle.sql").write_text(_MIGRATION, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def genere(projet: Path) -> str:
    rapport = {
        "findings": [
            {"classe": "element-non-exerce", "id": f"contrainte:{nom}", "risque": "eleve"}
            for nom in _CONTRAINTES
        ]
    }
    contenu = generateur_data.construire(rapport, projet)
    assert contenu, "le generateur doit produire des cas sur ce schema"
    return contenu


def _schema_sqlite() -> sqlite3.Connection:
    """Le schéma des migrations, monté sur une base en mémoire, clés étrangères ARMÉES."""
    cx = sqlite3.connect(":memory:")
    cx.execute("PRAGMA foreign_keys = ON")
    haut = _MIGRATION.partition("-- +migrate Down")[0].replace("-- +migrate Up", "")
    for instruction in [s.strip() for s in haut.split(";") if s.strip()]:
        cx.execute(instruction)
    cx.commit()
    return cx


def _cas_generes(contenu: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """`(nom du cas, sql, indices)` pour chaque cas du fichier produit."""
    cas: list[tuple[str, str, tuple[str, ...]]] = []
    nom = ""
    for ligne in contenu.splitlines():
        if ligne.startswith("def test_genere_"):
            nom = ligne[len("def "):].split("(")[0]
        trouve = _APPEL.search(ligne)
        if trouve:
            indices = tuple(
                m.strip().strip("'\"") for m in trouve.group("indices").split(",") if m.strip()
            )
            cas.append((nom, trouve.group("sql"), indices))
    return cas


# --- Le défaut fondateur, et pourquoi il ne se voyait pas -------------------------------------


def test_le_nom_de_table_ignore_IF_NOT_EXISTS() -> None:
    """Défaut n° 1, à sa source."""
    assert generateur_data._nom_de_table("IF NOT EXISTS commande (") == "commande"
    assert generateur_data._nom_de_table("commande (") == "commande"
    assert generateur_data._nom_de_table('IF NOT EXISTS public."commande" (') == "commande"


def test_la_forme_d_avant_est_bien_une_erreur_de_SYNTAXE_et_le_contrat_d_avant_l_acceptait():
    """FIXTURE ROUGE — le SQL que produisait le générateur, joué contre un vrai moteur.

    Deux faits, et c est leur conjonction qui a coûté les 56 relectures : ce SQL ne s exécute
    pas, et l ancien contrat (`pytest.raises(Exception)`) le comptait comme un succès.
    """
    cx = _schema_sqlite()

    with pytest.raises(sqlite3.OperationalError):
        cx.execute("INSERT INTO IF NOT EXISTS commande (statut) VALUES ('brouillon')")

    # `Exception` couvrait cette erreur de syntaxe ; `IntegrityError` ne la couvre pas.
    assert issubclass(sqlite3.OperationalError, Exception)
    assert not issubclass(sqlite3.OperationalError, sqlite3.IntegrityError)


def test_aucun_cas_genere_ne_porte_le_nom_de_table_fautif(genere: str) -> None:
    assert "IF NOT EXISTS" not in genere.partition('"""')[2].partition('"""')[2], (
        "le corps des cas ne doit plus porter « IF NOT EXISTS » dans un INSERT")


# --- Le contrat du cas, qui est ce qui décide ---------------------------------------------------


def test_l_entete_exige_un_rejet_D_INTEGRITE_et_pas_n_importe_quelle_exception(genere: str):
    assert "pytest.raises(IntegrityError)" in genere
    assert "pytest.raises(Exception)" not in genere
    assert "from sqlalchemy.exc import IntegrityError" in genere


def test_l_entete_fournit_son_moteur_et_ne_demolit_que_les_tables_du_schema(genere: str) -> None:
    """Défauts n° 2 et n° 3 : la fixture absente, et les trois tables en dur."""
    assert "def moteur_jetable(" in genere, "le fichier genere doit fournir sa fixture de moteur"
    assert "pytest.skip(" in genere, "sans base jetable declaree, un SKIP nomme, pas une erreur"
    assert "CASCADE" not in genere, "un DROP CASCADE n est pas portable d un moteur a l autre"
    assert 'TABLES = ["utilisateur", "commande"]' in genere, (
        "les tables demolies sont DERIVEES du schema, pas nommees en dur")


# --- Ce que chaque cas mesure vraiment, prouvé contre un moteur ---------------------------------


def test_chaque_cas_genere_est_rejete_pour_SA_contrainte(genere: str) -> None:
    """Le contrôle qui compte : le SQL s exécute, et il est refusé POUR LA BONNE RAISON."""
    cas = _cas_generes(genere)
    assert len(cas) == len(_CONTRAINTES), f"{len(cas)} cas generes pour {len(_CONTRAINTES)}"

    for nom, sql, indices in cas:
        cx = _schema_sqlite()
        with pytest.raises(sqlite3.IntegrityError) as capture:
            for morceau in [s.strip() for s in sql.split(";") if s.strip()]:
                cx.execute(morceau)
        message = str(capture.value).lower()
        assert any(indice.lower() in message for indice in indices), (
            f"{nom} : rejet « {message} » — aucun de {indices} n y figure")
        cx.close()


def test_la_ligne_inseree_est_valide_et_ses_parentes_sont_semees(genere: str) -> None:
    """Défaut n° 4 bis : l INSERT ne portait que la colonne visée.

    Le cas de la clé étrangère est le plus parlant : la ligne parente est semée d abord, et la
    ligne fille est complète — seule la valeur de la clé est orpheline.
    """
    par_nom = {nom: sql for nom, sql, _ in _cas_generes(genere)}
    fk = par_nom["test_genere_commande_utilisateur_fk"]

    assert fk.startswith("INSERT INTO utilisateur ("), f"la ligne parente doit etre semee : {fk}"
    assert "INSERT INTO commande (utilisateur_id, statut, cree_le)" in fk, (
        f"la ligne fille doit porter TOUTES ses colonnes NOT NULL : {fk}")
    assert "999999" in fk

    # Et la ligne semée est elle-même complète, sinon la semence échouerait avant le cas.
    unique = par_nom["test_genere_utilisateur_email_unique"]
    assert unique.count("INSERT INTO utilisateur (email, mot_de_passe_hash)") == 2
