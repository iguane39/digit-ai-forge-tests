"""Charge un jeu de données SQL sur une base PostgreSQL ÉPHÉMÈRE et CONSTATE ce qui s est passé.

Le pendant de `verifier_schema.py` pour la fabrique de données (TF-2012) : même interpréteur
(celui qui porte `testcontainers` et un pilote PostgreSQL), même découpage des migrations
(`forge_tests/sql.py` chargé par chemin, par la fonction de `verifier_schema`), même image.

Il applique les sections « Up » dans l ordre, une transaction par migration, puis le jeu,
instruction par instruction : chaque INSERT sous un point de sauvegarde, pour qu un rejet
n emporte pas les suivants et que CHAQUE violation soit nommée par le moteur. Il compte les
lignes de chaque table avant et après le jeu. La base est détruite à la sortie.

Ce script ne juge pas : il constate, dans le fichier de résultat que nomme le plan. Le verdict
est rendu par `forge_tests.fabrique_donnees`. Codes : 0 = constat écrit ; 3 = rien n a pu être
monté ici (module absent, démon de conteneurs injoignable) — le résultat dit lequel.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

IMAGE = "postgres:16-alpine"
POINT = "fabrique_donnees"


def _ecrire(destination: Path, donnees: dict) -> None:
    destination.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")


def _pilote():
    """psycopg (3) d abord, psycopg2 ensuite : le projet audité a l un ou l autre."""
    try:
        import psycopg

        return psycopg
    except ImportError:
        import psycopg2

        return psycopg2


def _erreur(exception: Exception) -> dict:
    diagnostic = getattr(exception, "diag", None)
    message = getattr(diagnostic, "message_primary", None) or str(exception)
    return {
        "sqlstate": getattr(exception, "sqlstate", None) or getattr(exception, "pgcode", None),
        "contrainte": getattr(diagnostic, "constraint_name", None),
        "table": getattr(diagnostic, "table_name", None),
        "colonne": getattr(diagnostic, "column_name", None),
        "message": " ".join(str(message).split())[:300],
        "detail": " ".join(str(getattr(diagnostic, "message_detail", None) or "").split())[:300],
    }


def _instructions_du_jeu(texte: str) -> list[tuple[int, str]]:
    """(numéro de ligne, instruction) : le jeu porte UNE instruction par ligne, par construction."""
    retenues: list[tuple[int, str]] = []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        propre = ligne.strip()
        if not propre or propre.startswith("--") or propre.upper() in ("BEGIN;", "COMMIT;"):
            continue
        retenues.append((numero, propre[:-1] if propre.endswith(";") else propre))
    return retenues


def _compter(curseur, tables: list[str]) -> dict[str, int | None]:
    comptes: dict[str, int | None] = {}
    for table in tables:
        try:
            curseur.execute(f"SELECT count(*) FROM {table}")
            comptes[table] = int(curseur.fetchone()[0])
        except Exception:  # noqa: BLE001 — une table absente se constate, elle ne tue pas
            curseur.connection.rollback()
            comptes[table] = None
    return comptes


def _charger(url: str, plan: dict, lecteur, pilote) -> dict:
    connexion = pilote.connect(url)
    try:
        curseur = connexion.cursor()
        curseur.execute("SELECT version()")
        version = str(curseur.fetchone()[0]).split(" on ")[0]
        connexion.commit()
        for migration in plan["migrations"]:
            chemin = Path(migration)
            haut = chemin.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
            for rang, instruction in enumerate(lecteur.decouper(haut), start=1):
                try:
                    curseur.execute(instruction)
                except Exception as exception:  # noqa: BLE001 — constaté, rendu, jamais tu
                    connexion.rollback()
                    return {"statut": "migrations", "postgres": version,
                            "migration": chemin.name, "rang": rang,
                            "instruction": instruction[:200], "erreur": _erreur(exception)}
            connexion.commit()
        tables = list(plan["tables"])
        avant = _compter(curseur, tables)
        connexion.commit()
        erreurs: list[dict] = []
        instructions = _instructions_du_jeu(Path(plan["jeu"]).read_text(encoding="utf-8"))
        for numero, instruction in instructions:
            curseur.execute(f"SAVEPOINT {POINT}")
            try:
                curseur.execute(instruction)
            except Exception as exception:  # noqa: BLE001 — chaque rejet est NOMMÉ
                curseur.execute(f"ROLLBACK TO SAVEPOINT {POINT}")
                erreurs.append({"ligne": numero, "instruction": instruction[:200],
                                **_erreur(exception)})
                continue
            curseur.execute(f"RELEASE SAVEPOINT {POINT}")
        connexion.commit()
        apres = _compter(curseur, tables)
        connexion.commit()
        return {"statut": "charge", "postgres": version, "instructions": len(instructions),
                "erreurs": erreurs,
                "lignes": {t: {"avant": avant[t], "apres": apres[t]} for t in tables}}
    finally:
        connexion.close()


def main() -> int:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    destination = Path(plan["sortie"])
    try:
        from testcontainers.community.postgres import PostgresContainer

        pilote = _pilote()
    except Exception as exception:  # noqa: BLE001 — l absence d un module se DIT
        _ecrire(destination, {"statut": "indisponible",
                              "motif": f"{type(exception).__name__}: {exception}",
                              "interprete": sys.executable})
        return 3
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verifier_schema import _lecteur_sql

    lecteur = _lecteur_sql()
    try:
        conteneur = PostgresContainer(IMAGE, driver=None)
        conteneur.start()
    except Exception:  # noqa: BLE001 — la base n a pas pu être montée : préalable, pas verdict
        _ecrire(destination, {"statut": "conteneur", "trace": traceback.format_exc()[-3000:]})
        return 3
    try:
        resultat = _charger(conteneur.get_connection_url(), plan, lecteur, pilote)
    except Exception:  # noqa: BLE001 — une panne de la sonde se rend, elle ne se tait pas
        resultat = {"statut": "panne", "trace": traceback.format_exc()[-3000:]}
    try:
        conteneur.stop()
    except Exception as exception:  # noqa: BLE001 — un arrêt raté se DIT au résultat
        resultat["arret"] = f"{type(exception).__name__}: {exception}"
    resultat["image"] = IMAGE
    _ecrire(destination, resultat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
