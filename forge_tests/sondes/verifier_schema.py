"""Applique les migrations sur une base neuve et RESTITUE le schéma obtenu.

Jusqu ici l oracle savait qu une migration avait été envoyée au moteur. Il ne savait pas ce
qu elle avait produit — une instruction peut s exécuter sans créer ce qu on croit qu elle crée.

Ce script tourne dans l interpréteur du projet analysé, applique les sections « Up » dans
l ordre, puis interroge `information_schema` : tables, contraintes, index réellement présents.
La comparaison au DÉCLARÉ est faite par l adaptateur, pas ici — ce script ne juge pas, il
constate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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

    migrations = sorted((racine / "migrations").glob("*.sql"))
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as conteneur:
        moteur = create_engine(conteneur.get_connection_url())
        for migration in migrations:
            haut = migration.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
            haut = haut.replace("-- +migrate Up", "")
            with moteur.begin() as cx:
                for instruction in [s.strip() for s in haut.split(";") if s.strip()]:
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
