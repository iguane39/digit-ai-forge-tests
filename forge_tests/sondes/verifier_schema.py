"""Applique les migrations sur une base neuve et RESTITUE le schéma obtenu.

Jusqu ici l oracle savait qu une migration avait été envoyée au moteur. Il ne savait pas ce
qu elle avait produit — une instruction peut s exécuter sans créer ce qu on croit qu elle crée.

Ce script tourne dans l interpréteur du projet analysé, applique les sections « Up » dans
l ordre, puis interroge `information_schema` : tables, contraintes, index réellement présents.
La comparaison au DÉCLARÉ est faite par l adaptateur, pas ici — ce script ne juge pas, il
constate.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _lecteur_sql():
    """Charge `forge_tests/sql.py` PAR CHEMIN, sans importer le paquet.

    Ce script tourne dans l interpréteur du PROJET analysé, qui n a aucune raison de connaître
    Forge Tests. Le charger par chemin évite d exiger le paquet là-bas, tout en gardant une
    SEULE implémentation du découpage SQL — RT-8 corrigé ici comme dans les adaptateurs. Sans
    ce partage, un `;` dans un commentaire faisait envoyer un fragment VIDE au moteur et
    l introspection du schéma entier échouait : `schema_obtenu` rendait None et deux pans
    perdaient leur contrôle d effet réel.
    """
    source = Path(__file__).resolve().parent.parent / "sql.py"
    specification = importlib.util.spec_from_file_location("forge_tests_sql", source)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


REQUETE_CONTRAINTES = """
SELECT c.conname
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
"""
REQUETE_TABLES = """
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'
"""
REQUETE_INDEX = """
SELECT indexname FROM pg_indexes WHERE schemaname = 'public'
"""


def main() -> int:
    racine, destination = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        from sqlalchemy import create_engine, text
        from testcontainers.community.postgres import PostgresContainer
    except Exception as exc:  # noqa: BLE001
        destination.write_text(json.dumps({"erreur": str(exc)}), encoding="utf-8")
        return 2

    lecteur = _lecteur_sql()
    migrations = sorted((racine / "migrations").glob("*.sql"))
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as conteneur:
        moteur = create_engine(conteneur.get_connection_url())
        for migration in migrations:
            haut = migration.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
            with moteur.begin() as cx:
                for instruction in lecteur.decouper(haut):
                    cx.execute(text(instruction))
        with moteur.connect() as cx:
            obtenu = {
                "tables": sorted(r[0] for r in cx.execute(text(REQUETE_TABLES))),
                "contraintes": sorted(r[0] for r in cx.execute(text(REQUETE_CONTRAINTES))),
                "index": sorted(r[0] for r in cx.execute(text(REQUETE_INDEX))),
            }
    destination.write_text(json.dumps(obtenu, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
