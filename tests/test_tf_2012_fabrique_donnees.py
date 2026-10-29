"""TF-2012 — la fabrique de données : un jeu SYNTHÉTIQUE, chargeable, jugé par un chargement réel.

Le CDC du 02/08/2026 (C4) constatait « Aucune fabrique de données n existe » ; la spec déclarait la
capacité 4 (« fixtures, seeding, teardown, cas limites ») sans qu une ligne de code la porte. Le
jeu des livrables (`livrables/jeux.py`) n écrit qu un JSON pour les cahiers, jamais chargé.

Paire de bancs à double sens, sous `fixtures/fabrique-donnees/` :

  - VERT : clés étrangères simples, composées et réflexives, type énuméré, identité, CHECK de
    bornes, de liste, de longueur et de relation entre deux colonnes — le jeu doit se charger
    sur une base PostgreSQL éphémère avec ZÉRO rejet ;
  - ROUGE « violation » : une vérification par expression régulière que la fabrique ne traduit
    pas — le chargement réel doit la faire rejeter, et NOMMER la contrainte ;
  - ROUGE « courriel » : un schéma qui impose une adresse d un domaine non réservé — le garde-fou
    de `jeux.py` doit refuser le jeu entier AVANT toute écriture.

Les tests de chargement réel exigent Docker et un interpréteur portant `testcontainers` et
`psycopg` (celui des bancs historiques : `uv sync --directory fixtures/banc-vert/backend`).
Sans eux, ils se mettent en SKIP NOMMÉ — et le verdict de la fabrique est NON_EXECUTABLE, jamais
un vert : c est ce que prouvent les tests de la section « non exécutable », qui n ont besoin
d aucun conteneur.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from forge_tests import execution, schema_sql
from forge_tests import fabrique_donnees as fabrique
from forge_tests.livrables import DepotInterdit, jeux

RACINE = Path(__file__).resolve().parent.parent
BANCS = RACINE / "fixtures" / "fabrique-donnees"
VERT = BANCS / "vert"
ROUGE_VIOLATION = BANCS / "rouge-violation"
ROUGE_COURRIEL = BANCS / "rouge-courriel"


@pytest.fixture(autouse=True)
def _disposition_neutre(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une racine de sources déclarée par l opérateur ne doit pas déplacer les migrations lues."""
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _projet(tmp_path: Path, sql: str, nom: str = "001_schema.sql") -> Path:
    dossier = tmp_path / "projet" / "backend" / "migrations"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(f"-- +migrate Up\n{sql}\n-- +migrate Down\n", encoding="utf-8")
    return tmp_path / "projet"


def _schema(sql: str) -> schema_sql.Schema:
    return schema_sql.lire_sections([("001.sql", sql)])


def _interprete_equipe() -> Path | None:
    """L interpréteur des bancs historiques : la recette exige déjà qu il porte testcontainers."""
    for banc in ("banc-vert", "banc-rouge"):
        venv = RACINE / "fixtures" / banc / "backend" / ".venv"
        for candidat in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
            if candidat.exists():
                return candidat
    return None


def _exiger_un_chargement(rapport: dict) -> None:
    """SKIP nommé si la base n a pas pu être montée ici — jamais un vert par défaut."""
    chargement = rapport.get("chargement") or rapport
    if chargement.get("verdict") == "NON_EXECUTABLE":
        pytest.skip(f"chargement réel non exécutable sur ce poste : {chargement.get('motif')}")


EQUIPE = _interprete_equipe()
avec_conteneur = pytest.mark.skipif(
    EQUIPE is None,
    reason="aucun interpréteur équipé de testcontainers — `uv sync --directory "
    "fixtures/banc-vert/backend` (préalable déjà exigé par la recette)",
)


# --- Lecture du schéma --------------------------------------------------------------------------


def test_le_banc_vert_est_lu_tables_cles_unicites_et_verifications() -> None:
    schema = schema_sql.lire(VERT)

    assert schema.migrations == ["001_catalogue.sql", "002_commandes.sql"]
    assert list(schema.tables) == ["client", "produit", "commande", "ligne_commande"]
    assert schema.enums == {"statut_commande": ["brouillon", "validee", "livree"]}
    client, ligne = schema.tables["client"], schema.tables["ligne_commande"]
    assert client.colonnes["id"].auto == "serie" and client.colonnes["id"].non_nul
    assert client.colonnes["nom_affiche"].longueur_max == 60
    assert schema.tables["produit"].colonnes["code"].longueur_max == 6
    assert schema.tables["commande"].colonnes["id"].auto == "identite_toujours"
    assert schema.tables["commande"].colonnes["statut"].enum == "statut_commande"
    assert {(c.colonnes, c.table_cible) for c in ligne.cles_etrangeres} == {
        (("commande_id",), "commande"), (("produit_code",), "produit")
    }
    assert [u.colonnes for u in ligne.unicites if u.primaire] == [("commande_id", "produit_code")]
    assert any(u.expression and u.colonnes == ("courriel",) for u in client.unicites)
    assert [(c.colonnes, c.table_cible) for c in client.cles_etrangeres] == [
        (("parrain_id",), "client")
    ]
    # Toutes les vérifications du banc vert sont dans les formes que la fabrique traduit.
    assert {v.nom: v.interpretee for t in schema.tables.values() for v in t.verifications} == {
        "client_nom_affiche_check": "oui", "client_niveau_borne": "oui",
        "produit_prix_check": "oui", "produit_categorie_check": "oui",
        "commande_livraison_apres": "oui", "ligne_commande_quantite_bornee": "oui",
        "ligne_commande_remise_admise": "oui",
    }
    assert schema.non_modelisees == {} and schema.notes == []


@pytest.mark.parametrize(
    ("expression", "attendu"),
    [
        ("statut IN ('a', 'b')", [("permis", "statut", None, ("a", "b"), None)]),
        ("statut NOT IN ('x')", [("exclus", "statut", None, ("x",), None)]),
        # La forme que `pg_dump` réécrit : casts partout, ANY sur un tableau.
        ("((statut)::text = ANY ((ARRAY['a'::character varying, 'b'::character varying])"
         "::text[]))", [("permis", "statut", None, ("a", "b"), None)]),
        ("n BETWEEN 1 AND 5", [("borne", "n", ">=", (1,), None),
                               ("borne", "n", "<=", (5,), None)]),
        ("n > 0 AND n < 100", [("borne", "n", ">", (0,), None),
                               ("borne", "n", "<", (100,), None)]),
        ("0 < n", [("borne", "n", ">", (0,), None)]),
        ("n <= 9.5", [("borne", "n", "<=", (Decimal("9.5"),), None)]),
        ("statut = 'a' OR statut = 'b'", [("permis", "statut", None, ("a", "b"), None)]),
        ("fin IS NULL OR fin >= debut", [("relation", "fin", ">=", (), "debut")]),
        ("char_length(trim(statut)) > 0", [("longueur", "statut", ">", (0,), None)]),
        ("btrim(statut) <> ''", [("non_vide", "statut", None, (), None)]),
        ("n IS NOT NULL", [("non_nul", "n", None, (), None)]),
    ],
)
def test_les_formes_de_check_reconnues_sont_traduites_en_valeurs(expression, attendu) -> None:
    schema = _schema("CREATE TABLE t (statut TEXT, n NUMERIC, debut DATE, fin DATE, "
                     f"CONSTRAINT t_ck CHECK ({expression}));")
    verification = schema.tables["t"].verifications[0]

    assert verification.interpretee == "oui", verification.expression
    assert [(e.genre, e.colonne, e.operateur, e.valeurs, e.autre)
            for e in verification.effets] == attendu


def test_une_verification_hors_des_formes_reconnues_est_nommee_pas_devinee() -> None:
    schema = _schema(
        "CREATE TABLE t (ref TEXT NOT NULL, n INT, "
        "CONSTRAINT t_ref_motif CHECK (ref ~ '^DOS-[0-9]{6}$'), "
        "CONSTRAINT t_mixte CHECK (n > 0 AND lower(ref) = ref));"
    )
    motif, mixte = schema.tables["t"].verifications

    assert (motif.interpretee, motif.effets, motif.colonnes) == ("non", [], ("ref",))
    # Un conjoint traduit, l autre non : « partielle », et la partie traduite est tenue.
    assert mixte.interpretee == "partielle"
    assert [(e.genre, e.colonne) for e in mixte.effets] == [("borne", "n")]


def test_alter_drop_et_rename_suivent_ce_que_le_moteur_fera() -> None:
    schema = _schema(
        "CREATE TYPE etat AS ENUM ('ouvert'); "
        "CREATE TABLE parent (id SERIAL PRIMARY KEY, code TEXT UNIQUE, jetable INT); "
        "CREATE TABLE enfant (id SERIAL PRIMARY KEY, parent_code TEXT REFERENCES parent (code), "
        "  e etat, quantite INT CHECK (quantite > 0)); "
        "CREATE TABLE orpheline (id INT REFERENCES enfant (id)); "
        "ALTER TABLE parent ADD COLUMN IF NOT EXISTS libelle VARCHAR(20) NOT NULL; "
        "ALTER TABLE parent DROP COLUMN jetable; "
        "ALTER TABLE parent RENAME COLUMN code TO reference; "
        "ALTER TYPE etat ADD VALUE 'clos' AFTER 'ouvert'; "
        "DROP TABLE enfant CASCADE;"
    )
    parent = schema.tables["parent"]

    assert list(parent.colonnes) == ["id", "reference", "libelle"]
    assert parent.colonnes["libelle"].non_nul and parent.colonnes["libelle"].longueur_max == 20
    assert [u.colonnes for u in parent.unicites] == [("id",), ("reference",)]
    assert "enfant" not in schema.tables
    # La clé de `orpheline` visait une table supprimée : le moteur l a emportée avec elle.
    assert schema.tables["orpheline"].cles_etrangeres == []
    assert schema.enums["etat"] == ["ouvert", "clos"]


def test_la_contrainte_implicite_retiree_par_son_nom_postgres_disparait() -> None:
    schema = _schema(
        "CREATE TABLE t (id INT PRIMARY KEY, n INT CHECK (n > 0), m INT UNIQUE); "
        "ALTER TABLE t RENAME COLUMN n TO nombre; "
        "ALTER TABLE t DROP CONSTRAINT t_n_check; "
        "ALTER TABLE t DROP CONSTRAINT t_m_key; "
        "ALTER TABLE t DROP CONSTRAINT t_inexistante;"
    )
    table = schema.tables["t"]

    assert table.verifications == []
    assert [u.colonnes for u in table.unicites] == [("id",)]
    # Un nom que le lecteur ne retrouve pas se DIT : rien n est retiré en silence.
    assert any("t_inexistante" in note and "introuvable" in note for note in schema.notes)


def test_les_instructions_non_modelisees_sont_comptees_par_nature() -> None:
    schema = _schema(
        "CREATE TABLE t (id INT); "
        "CREATE OR REPLACE FUNCTION f() RETURNS INT AS $$ SELECT 1 $$ LANGUAGE sql; "
        "CREATE TRIGGER tg BEFORE INSERT ON t FOR EACH ROW EXECUTE FUNCTION f(); "
        "INSERT INTO t (id) VALUES (1); "
        "COMMENT ON TABLE t IS 'une table';"
    )

    assert schema.non_modelisees == {
        "CREATE FUNCTION": 1, "CREATE TRIGGER": 1, "INSERT": 1, "COMMENT": 1
    }


# --- Fabrication --------------------------------------------------------------------------------


def test_meme_graine_meme_octet_autre_graine_autre_jeu() -> None:
    schema = schema_sql.lire(VERT)

    premier = fabrique.fabriquer(schema, graine=42).texte()
    second = fabrique.fabriquer(schema_sql.lire(VERT), graine=42).texte()
    autre = fabrique.fabriquer(schema, graine=43).texte()

    assert premier == second
    assert premier != autre
    assert "-- graine : 42 " in premier


def test_le_volume_d_une_table_ne_rebat_pas_les_tables_qui_ne_la_suivent_pas() -> None:
    schema = schema_sql.lire(VERT)
    base = fabrique.fabriquer(schema, graine=7)
    plus = fabrique.fabriquer(schema, graine=7, volumes={"commande": 30, "ligne_commande": 3})

    assert plus.tables["client"].lignes == base.tables["client"].lignes
    assert plus.tables["produit"].lignes == base.tables["produit"].lignes
    assert [len(plus.tables[t].lignes) for t in plus.ordre] == [10, 10, 30, 3]


def test_ordre_des_cles_etrangeres_parents_d_abord_dans_le_fichier() -> None:
    jeu = fabrique.fabriquer(schema_sql.lire(VERT), graine=3)
    texte = jeu.texte()

    assert jeu.ordre == ["client", "produit", "commande", "ligne_commande"]
    dernier_client = texte.rindex('INSERT INTO "client"')
    assert dernier_client < texte.index('INSERT INTO "commande"')
    assert texte.rindex('INSERT INTO "produit"') < texte.index('INSERT INTO "ligne_commande"')
    # Identité GENERATED ALWAYS : valeur explicite autorisée, et séquences recalées après.
    assert 'INSERT INTO "commande" ("id", "client_id"' in texte
    assert "OVERRIDING SYSTEM VALUE VALUES" in texte
    assert "SELECT setval(pg_get_serial_sequence('\"commande\"', 'id')" in texte
    # Une instruction par ligne : le juge et `psql -f` lisent le même découpage.
    instructions = [ligne for ligne in texte.splitlines()
                    if ligne and not ligne.startswith("--")]
    assert instructions[0] == "BEGIN;" and instructions[-1] == "COMMIT;"
    assert all(ligne.endswith(";") for ligne in instructions)


def test_les_valeurs_fabriquees_tiennent_les_contraintes_lues() -> None:
    jeu = fabrique.fabriquer(schema_sql.lire(VERT), graine=11, volume=40,
                             volumes={"ligne_commande": 120})
    lignes = {nom: produite.lignes for nom, produite in jeu.tables.items()}
    clients, produits = lignes["client"], lignes["produit"]

    courriels = [c["courriel"] for c in clients]
    assert len({c.lower() for c in courriels}) == len(courriels) == 40
    assert all(c.endswith("@" + jeux.DOMAINE) for c in courriels)
    assert all(1 <= c["niveau"] <= 5 for c in clients)
    assert all(0 < len(c["nom_affiche"].strip()) <= 60 for c in clients)
    ids_clients = {c["id"] for c in clients}
    assert all(c["parrain_id"] is None or c["parrain_id"] in ids_clients for c in clients)
    assert all(len(p["code"]) <= 6 for p in produits)
    assert len({p["code"] for p in produits}) == 40
    assert all(Decimal("0") < p["prix"] <= Decimal("999.99") for p in produits)
    assert {p["categorie"] for p in produits} <= {"entree", "plat", "dessert"}
    assert all(c["client_id"] in ids_clients for c in lignes["commande"])
    assert {c["statut"] for c in lignes["commande"]} <= {"brouillon", "validee", "livree"}
    assert all(c["livree_le"] is None or c["livree_le"] >= c["passee_le"]
               for c in lignes["commande"])
    ids_commandes = {c["id"] for c in lignes["commande"]}
    codes = {p["code"] for p in produits}
    paires = [(lc["commande_id"], lc["produit_code"]) for lc in lignes["ligne_commande"]]
    assert len(paires) == len(set(paires)) == 120
    assert all(c in ids_commandes and p in codes for c, p in paires)
    assert all(1 <= lc["quantite"] <= 99 for lc in lignes["ligne_commande"])
    assert {lc["remise_pct"] for lc in lignes["ligne_commande"]} <= {0, 5, 10, 15}


def test_les_cas_limites_sont_valides_et_declares() -> None:
    jeu = fabrique.fabriquer(schema_sql.lire(VERT), graine=5)
    produit, client = jeu.tables["produit"], jeu.tables["client"]

    assert produit.lignes[0]["prix"] == Decimal("0.01")
    assert produit.lignes[2]["prix"] == Decimal("999.99")
    assert len(produit.lignes[0]["libelle"]) == 40
    assert client.lignes[0]["niveau"] == 1 and client.lignes[2]["niveau"] == 5
    assert client.lignes[1]["parrain_id"] is None
    assert "prix : borne basse" in produit.cas_limites
    assert any(limite.startswith("NULL dans") for limite in client.cas_limites)


def test_un_cycle_de_cles_se_rompt_sur_la_cle_nullable_et_le_dit() -> None:
    schema = _schema(
        "CREATE TABLE equipe (id SERIAL PRIMARY KEY, chef_id INT); "
        "CREATE TABLE membre (id SERIAL PRIMARY KEY, equipe_id INT NOT NULL "
        "  REFERENCES equipe (id)); "
        "ALTER TABLE equipe ADD CONSTRAINT equipe_chef_fk FOREIGN KEY (chef_id) "
        "  REFERENCES membre (id);"
    )
    jeu = fabrique.fabriquer(schema, volume=4)

    assert jeu.ordre == ["equipe", "membre"]
    assert all(e["chef_id"] is None for e in jeu.tables["equipe"].lignes)
    assert any("equipe_chef_fk" in note and "NULL" in note for note in jeu.notes)
    assert len(jeu.tables["membre"].lignes) == 4


def test_un_volume_que_le_schema_rend_impossible_est_un_ecart_dit() -> None:
    schema = _schema("CREATE TABLE drapeau (id SERIAL PRIMARY KEY, actif BOOLEAN UNIQUE);")
    produite = fabrique.fabriquer(schema, volume=5).tables["drapeau"]

    assert len(produite.lignes) == 2
    assert sum(produite.ecarts.values()) == 3
    assert any("actif" in motif for motif in produite.ecarts)


def test_le_rendu_echappe_ce_qui_couperait_une_instruction() -> None:
    texte = schema_sql.Colonne("c", "text", "texte")
    monnaie = schema_sql.Colonne("m", "money", "monnaie")

    assert fabrique.rendre("l'apostrophe", texte) == "'l''apostrophe'"
    assert fabrique.rendre("deux\nlignes", texte) == "E'deux\\nlignes'"
    assert fabrique.rendre(None, texte) == "NULL"
    assert fabrique.rendre(Decimal("12.30"), monnaie) == "'12.30'"
    assert fabrique.rendre(date(2026, 1, 15), texte) == "'2026-01-15'"


# --- Garde-fou de jeux.py -----------------------------------------------------------------------


def test_chaque_valeur_passe_par_le_garde_fou_de_jeux_py(monkeypatch: pytest.MonkeyPatch) -> None:
    """La réutilisation est vérifiée, pas supposée : c est `jeux.verifier` qui est appelé, et il
    reçoit toutes les valeurs non nulles du jeu."""
    vues: list[object] = []
    monkeypatch.setattr(jeux, "verifier", lambda donnees, cible=None: vues.append(donnees))
    jeu = fabrique.fabriquer(schema_sql.lire(VERT), graine=9)

    compte = fabrique.verifier_synthetique(jeu, VERT)

    (donnees,) = vues
    attendues = [str(v) for p in jeu.tables.values() for ligne in p.lignes
                 for v in ligne.values() if v is not None]
    recues = [v for lignes in donnees.values() for ligne in lignes for v in ligne.values()]
    assert compte == len(attendues) == len(recues) > 0
    assert sorted(recues) == sorted(attendues)


def test_rouge_courriel_reel_le_jeu_entier_est_refuse_avant_ecriture(tmp_path: Path) -> None:
    sortie = tmp_path / "depot" / "jeu.sql"

    with pytest.raises(jeux.DonneeNonSynthetique) as refus:
        fabrique.produire(ROUGE_COURRIEL, sortie, chargement=False)

    message = str(refus.value)
    assert "example.com" in message and "pas un domaine réservé" in message
    assert "notification_expediteur_check" in message  # la valeur est IMPOSÉE par le schéma
    assert not sortie.exists() and not sortie.parent.exists()


def test_rouge_courriel_au_cli_code_2_et_rien_d_ecrit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sortie = tmp_path / "jeu.sql"

    code = fabrique.main([str(ROUGE_COURRIEL), "--sortie", str(sortie), "--json"])

    rapport = json.loads(capsys.readouterr().out)
    assert code == fabrique.SORTIE_ERREUR == 2
    assert rapport["verdict"] == "REFUSE" and "RIEN n est ecrit" in rapport["motif"]
    assert not sortie.exists()


def test_le_banc_vert_passe_le_garde_fou_sans_refus(tmp_path: Path) -> None:
    rapport = fabrique.produire(VERT, tmp_path / "jeu.sql", chargement=False)

    assert re.fullmatch(r"jeux\.verifier : \d+ valeur\(s\) relue\(s\) avant ecriture, aucun refus",
                        rapport["garde_fou"])
    assert rapport["verdict"] == "NON_JUGE"


def test_G1_un_jeu_depose_dans_le_projet_est_refuse_sans_rien_ecrire(tmp_path: Path) -> None:
    projet = _projet(tmp_path, "CREATE TABLE t (id SERIAL PRIMARY KEY);")
    sortie = projet / "seeds" / "jeu.sql"

    with pytest.raises(DepotInterdit):
        fabrique.produire(projet, sortie, chargement=False)
    assert not sortie.parent.exists()
    assert fabrique.main([str(projet), "--sortie", str(sortie), "--sans-chargement"]) == 4


def test_sans_migration_sql_la_fabrique_n_invente_pas_de_schema(tmp_path: Path) -> None:
    (tmp_path / "projet" / "backend" / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "projet" / "backend" / "alembic" / "versions" / "0001_init.py").write_text(
        "def upgrade():\n    pass\n", encoding="utf-8"
    )

    with pytest.raises(fabrique.SchemaIntrouvable) as erreur:
        fabrique.produire(tmp_path / "projet", tmp_path / "jeu.sql", chargement=False)
    assert "Alembic" in str(erreur.value) and "n en invente pas" in str(erreur.value)


# --- Non exécutable : jamais un vert ------------------------------------------------------------


def test_sans_chargement_le_verdict_est_NON_JUGE_code_3(tmp_path: Path) -> None:
    sortie = tmp_path / "jeu.sql"
    assert fabrique.main([str(VERT), "--sortie", str(sortie), "--sans-chargement"]) == 3
    assert sortie.exists()


def test_un_interpreteur_introuvable_rend_NON_EXECUTABLE(tmp_path: Path) -> None:
    rapport = fabrique.produire(VERT, tmp_path / "jeu.sql", python=tmp_path / "absent.exe")

    assert rapport["verdict"] == "NON_EXECUTABLE"
    assert "aucun interpreteur equipe" in rapport["motif"] and "absent.exe" in rapport["motif"]


@pytest.mark.skipif(
    importlib.util.find_spec("testcontainers") is not None,
    reason="l interpréteur de la suite porte testcontainers : ce cas n y existe pas",
)
def test_un_interpreteur_sans_testcontainers_rend_NON_EXECUTABLE_par_la_sonde_reelle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """La sonde est RÉELLEMENT lancée avec l interpréteur de la suite, qui n a pas le module."""
    code = fabrique.main([str(VERT), "--sortie", str(tmp_path / "jeu.sql"), "--json",
                          "--python", sys.executable])

    rapport = json.loads(capsys.readouterr().out)
    assert code == 3 and rapport["verdict"] == "NON_EXECUTABLE"
    assert "ModuleNotFoundError" in rapport["motif"] and "testcontainers" in rapport["motif"]


TRACE_DEMON_ABSENT = (
    "Traceback (most recent call last):\n"
    '  File "charger_jeu.py", line 120, in main\n'
    "docker.errors.DockerException: Error while fetching server API version: "
    "(2, 'CreateFile', 'Le fichier specifie est introuvable.')\n"
)


@pytest.mark.parametrize(
    ("constat", "verdict", "marque"),
    [
        ({"statut": "conteneur", "trace": TRACE_DEMON_ABSENT}, "NON_EXECUTABLE", True),
        ({"statut": "conteneur", "trace": "docker.errors.ImageNotFound: 404 pull refusé"},
         "NON_EXECUTABLE", False),
        ({"statut": "delai", "trace": "chargement : délai de 600 s dépassé"}, "NON_EXECUTABLE",
         False),
        ({"statut": "panne", "trace": "KeyError: 'sortie'", "code": 1}, "ERREUR", False),
        ({"statut": "migrations", "migration": "001.sql", "rang": 2,
          "erreur": {"sqlstate": "42P01", "message": "relation absente"}}, "ERREUR", False),
    ],
)
def test_ce_qui_n_a_pas_ete_charge_n_est_jamais_un_vert(constat, verdict, marque) -> None:
    rendu = fabrique._verdict(constat, {'"t"': 3}, Path("python"))

    assert rendu["verdict"] == verdict
    assert (execution.PREALABLE_ABSENT in rendu["motif"]) is marque
    assert "PAS jug" in rendu["motif"] or verdict == "ERREUR"


def test_un_chargement_incomplet_sans_erreur_est_un_FAIL() -> None:
    """Un déclencheur qui avale une ligne ne lève rien : seul le compte le trahit."""
    constat = {"statut": "charge", "instructions": 3, "erreurs": [],
               "lignes": {'"t"': {"avant": 0, "apres": 2}}}

    rendu = fabrique._verdict(constat, {'"t"': 3}, Path("python"))

    assert rendu["verdict"] == "FAIL"
    assert rendu["lignes_absentes"] == ['"t" : 2 ligne(s) présente(s) sur 3 insérée(s)']


@avec_conteneur
def test_demon_injoignable_la_sonde_reelle_rend_NON_EXECUTABLE_et_sa_preuve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le démon n est jamais arrêté pour de vrai : la sonde le cherche à une adresse morte."""
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:1")

    rapport = fabrique.produire(VERT, tmp_path / "jeu.sql", python=EQUIPE)

    assert rapport["verdict"] == "NON_EXECUTABLE", rapport["motif"]
    assert execution.PREALABLE_ABSENT in rapport["motif"]
    assert "DockerException" in rapport["motif"]


# --- Chargement réel ----------------------------------------------------------------------------


@avec_conteneur
def test_banc_vert_le_jeu_se_charge_sans_un_rejet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sortie = tmp_path / "jeu.sql"

    code = fabrique.main([str(VERT), "--sortie", str(sortie), "--graine", "2012",
                          "--volume", "12", "--volume-table", "ligne_commande=30",
                          "--python", str(EQUIPE), "--json"])

    rapport = json.loads(capsys.readouterr().out)
    _exiger_un_chargement(rapport)
    chargement = rapport["chargement"]
    assert code == 0 and rapport["verdict"] == "PASS", rapport["motif"]
    assert chargement["erreurs"] == [] and chargement["lignes_absentes"] == []
    assert chargement["postgres"].startswith("PostgreSQL 16")
    assert {t: c["apres"] - c["avant"] for t, c in chargement["lignes"].items()} == {
        '"client"': 12, '"produit"': 12, '"commande"': 12, '"ligne_commande"': 30
    }
    assert rapport["verifications_non_interpretees"] == []


@avec_conteneur
def test_banc_rouge_la_violation_est_attrapee_par_le_chargement_et_nommee(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = fabrique.main([str(ROUGE_VIOLATION), "--sortie", str(tmp_path / "jeu.sql"),
                          "--volume", "3", "--python", str(EQUIPE), "--json"])

    rapport = json.loads(capsys.readouterr().out)
    _exiger_un_chargement(rapport)
    rejets = {e["contrainte"] for e in rapport["chargement"]["erreurs"]}
    assert code == 1 and rapport["verdict"] == "FAIL"
    assert "dossier_reference_format" in rejets
    assert "dossier_reference_format" in rapport["motif"]
    # La fabrique l avait annoncé : la vérification était nommée « non interprétée ».
    assert [v["contrainte"] for v in rapport["verifications_non_interpretees"]] == [
        "dossier_reference_format"
    ]


@avec_conteneur
def test_un_jeu_altere_a_la_main_est_attrape_par_le_juge(tmp_path: Path) -> None:
    """Le juge discrimine : la même pièce, une clé étrangère faussée, et le moteur la nomme."""
    sortie = tmp_path / "jeu.sql"
    jeu = fabrique.fabriquer(schema_sql.lire(VERT), graine=4, volume=3)
    texte = jeu.texte()
    ligne = next(x for x in texte.splitlines() if x.startswith('INSERT INTO "ligne_commande"'))
    faussee = re.sub(r"VALUES \(\d+,", "VALUES (999999,", ligne)
    sortie.write_text(texte.replace(ligne, faussee), encoding="utf-8", newline="\n")

    verdict = fabrique.charger(VERT, sortie, sorted((VERT / "backend" / "migrations").glob(
        "*.sql")), jeu.attendues(), python=EQUIPE)

    _exiger_un_chargement(verdict)
    assert verdict["verdict"] == "FAIL"
    assert [e["contrainte"] for e in verdict["erreurs"]] == ["ligne_commande_commande_fk"]
    assert verdict["lignes_absentes"] == ['"ligne_commande" : 2 ligne(s) présente(s) sur 3 '
                                          "insérée(s)"]
