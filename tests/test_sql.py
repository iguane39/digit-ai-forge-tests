"""Lecture du SQL — le module dont dépendent les QUATRE lecteurs du dépôt (RT-8).

Le plus petit défaut ici se propage à l inventaire des tables, aux objets annoncés par une
migration et à la sonde qui rejoue le schéma : un `;` mal placé y devient une migration
« jamais exercée », c est-à-dire un FAIL produit par l auditeur et non par le projet audité.
La recette en couvre sept cas nominaux ; ces tests portent sur les BORDS, que le corpus
n exerce pas — littéral non fermé, commentaire non clos, texte vide, collage de jetons.
"""

from __future__ import annotations

import pytest

from forge_tests.sql import decouper, sans_commentaires


@pytest.mark.parametrize(
    ("libelle", "source", "attendu"),
    [
        ("texte vide", "", []),
        ("commentaire seul : aucune instruction ne doit etre fabriquee", "-- rien ici\n", []),
        ("point-virgules consecutifs : pas d instruction vide", "SELECT 1;;\n;", ["SELECT 1"]),
        ("dernier fragment sans point-virgule final", "SELECT 1", ["SELECT 1"]),
        (
            "commentaire de bloc JAMAIS ferme : le reste est du commentaire, pas une instruction",
            "SELECT 1; /* ouvert mais jamais clos ; SELECT 2;",
            ["SELECT 1"],
        ),
        (
            "litteral non ferme : le lecteur degrade, il ne leve pas",
            "INSERT INTO t VALUES ('jamais ferme ; ni ici",
            ["INSERT INTO t VALUES ('jamais ferme ; ni ici"],
        ),
        (
            "apostrophe echappee par doublement : le litteral ne se ferme pas au milieu",
            "INSERT INTO t (c) VALUES ('l''unicite ; metier'); SELECT 2;",
            ["INSERT INTO t (c) VALUES ('l''unicite ; metier')", "SELECT 2"],
        ),
        (
            "identifiant entre guillemets porteur d un point-virgule",
            'CREATE TABLE "table; etrange" (id INT);',
            ['CREATE TABLE "table; etrange" (id INT)'],
        ),
        (
            "espaces et sauts de ligne normalises en un seul blanc",
            "CREATE   TABLE\n\n  t (id INT);",
            ["CREATE TABLE t (id INT)"],
        ),
    ],
)
def test_decouper_bords(libelle: str, source: str, attendu: list[str]) -> None:
    assert decouper(source) == attendu, libelle


def test_sans_commentaires_ne_colle_pas_les_jetons() -> None:
    """Le commentaire est remplace par un BLANC, jamais supprime sans trace.

    Supprime sans trace, `CREATE INDEX i -- note\\n ON t (c)` devenait `CREATE INDEX iON t (c)` :
    une instruction inventee par le lecteur, introuvable dans le releve de la sonde.
    """
    propre = sans_commentaires("CREATE INDEX i -- note\n  ON t (c);")
    assert "iON" not in propre
    assert decouper("CREATE INDEX i -- note\n  ON t (c);") == ["CREATE INDEX i ON t (c)"]


def test_sans_commentaires_epargne_les_litteraux() -> None:
    """Un `--` dans une chaine n est pas un commentaire : le masquer perdrait la donnee."""
    source = "INSERT INTO t (c) VALUES ('a--b');"
    assert "a--b" in sans_commentaires(source)


def test_decouper_est_idempotent_sur_son_propre_resultat() -> None:
    """Redecouper une instruction deja normalisee doit la rendre a l identique.

    La sonde `verifier_schema` rejoue ce que l adaptateur a decoupe : si le second passage
    coupait autrement, les deux ne parleraient pas du meme objet.
    """
    instructions = decouper("-- entete ;\nCREATE TABLE t (id INT);\nDROP INDEX i;")
    for instruction in instructions:
        assert decouper(instruction) == [instruction]
