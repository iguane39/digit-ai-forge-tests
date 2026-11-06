"""Le schéma de la CIBLE, relevé, contre le schéma de la base d'essai (TF-2267).

Fait remonté (Produit-81, lot 20261106a, RP-3) : un script SQL de données validé deux fois sur une
base SQL Server jetable (979 lignes posées, puis 0) a échoué sur la cible réelle, Msg 544 :
`ID_TRADUCTION_LIB` est une colonne d'identité dans la base D1, pas dans la base jetable. Celle-ci
avait été reconstruite d'après le jeu fictif, jamais d'après le schéma de la cible. Un run de chaîne
en échec et un second lancement.

Règle (décision du 06/11/2026) : **une base d'essai se construit depuis le schéma de la cible**
(relevé `INFORMATION_SCHEMA` ou extraction), **jamais depuis le jeu fictif**. Ce module la joue là
où la forge prépare une base d'essai (`fabrique_donnees`) : le schéma des migrations du projet est
comparé au relevé de la cible, colonne par colonne, et tout écart REFUSE la fabrication avant
d'écrire quoi que ce soit, au lieu de valider sur un substitut qui diffère de la cible.

Format du relevé (JSON, une ligne par colonne — ce que rend
`SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.'
+ TABLE_NAME), COLUMN_NAME, 'IsIdentity') FROM INFORMATION_SCHEMA.COLUMNS`) :

    [{"table": "TRADUCTION_LIB", "colonne": "ID_TRADUCTION_LIB", "type": "int",
      "nullable": "NO", "identite": 1}, …]

`nullable` : `YES`/`NO`/booléen ; `identite` : `1`/`0`/booléen/`YES`/`NO`. Une valeur illisible est
refusée, jamais devinée.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests.schema_sql import Colonne, Schema

#: Variable qui désigne le relevé de la cible (à défaut de `--schema-cible`).
VARIABLE = "FORGE_TESTS_SCHEMA_CIBLE"

NON_JUGE = [
    "schema cible : le relevé compare les TABLES, les COLONNES, leur nullabilité, leur identité ; "
    "un type, un défaut serveur, un déclencheur ou une contrainte absents du relevé ne sont pas "
    "comparés, et un relevé extrait d'une autre version de la cible fait comparer autre chose",
]


class ReleveIllisible(ValueError):
    """Le relevé de la cible n'est pas exploitable : refus, jamais un relevé vide."""


def _booleen(valeur: object, champ: str, ligne: int) -> bool:
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, int) and valeur in (0, 1):
        return bool(valeur)
    if isinstance(valeur, str) and valeur.strip().upper() in ("YES", "OUI", "TRUE", "1"):
        return True
    if isinstance(valeur, str) and valeur.strip().upper() in ("NO", "NON", "FALSE", "0"):
        return False
    raise ReleveIllisible(f"ligne {ligne} : « {champ} » = {valeur!r} n'est ni oui ni non")


def lire_releve(chemin: Path) -> list[dict]:
    """Les lignes du relevé, normalisées (`nullable` et `identite` en booléens)."""
    try:
        brut = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        raise ReleveIllisible(f"relevé de la cible illisible ({chemin}) : {erreur}") from erreur
    if not isinstance(brut, list) or not brut:
        raise ReleveIllisible(
            f"relevé de la cible vide ou mal formé ({chemin}) : une liste de colonnes est attendue"
        )
    lignes = []
    for rang, entree in enumerate(brut, start=1):
        if not isinstance(entree, dict) or not entree.get("table") or not entree.get("colonne"):
            raise ReleveIllisible(f"ligne {rang} : « table » et « colonne » sont requis")
        lignes.append({
            "table": str(entree["table"]),
            "colonne": str(entree["colonne"]),
            "type": str(entree.get("type") or ""),
            "nullable": _booleen(entree.get("nullable", True), "nullable", rang),
            "identite": _booleen(entree.get("identite", False), "identite", rang),
        })
    return lignes


def _est_identite(colonne: Colonne) -> bool:
    return colonne.auto in ("identite_toujours", "identite_defaut")


def ecarts(schema: Schema, releve: list[dict]) -> list[str]:
    """Ce qui diffère entre la base d'essai (migrations du projet) et la cible relevée.

    Un message par écart, le geste de la cible nommé : l'écart d'identité est celui du lot (un
    INSERT explicite d'une colonne d'identité est refusé par la cible, Msg 544).
    """
    tables = {nom.lower(): table for nom, table in schema.tables.items()}
    constats: list[str] = []
    for ligne in releve:
        table = tables.get(ligne["table"].lower())
        if table is None:
            constats.append(
                f"table {ligne['table']} : présente dans la cible, absente du schéma d'essai"
            )
            continue
        colonnes = {nom.lower(): c for nom, c in table.colonnes.items()}
        colonne = colonnes.get(ligne["colonne"].lower())
        if colonne is None:
            constats.append(
                f"{ligne['table']}.{ligne['colonne']} : présente dans la cible, absente du "
                "schéma d'essai"
            )
            continue
        if ligne["identite"] and not _est_identite(colonne):
            constats.append(
                f"{ligne['table']}.{ligne['colonne']} : colonne d'IDENTITÉ dans la cible, simple "
                "colonne dans le schéma d'essai — un INSERT qui pose cette valeur passe sur la "
                "base d'essai et est refusé par la cible (Msg 544)"
            )
        elif not ligne["identite"] and _est_identite(colonne):
            constats.append(
                f"{ligne['table']}.{ligne['colonne']} : colonne d'identité dans le schéma d'essai, "
                "simple colonne dans la cible — la base d'essai refuserait une valeur que la "
                "cible accepte"
            )
        if not ligne["nullable"] and not colonne.non_nul and not _est_identite(colonne):
            constats.append(
                f"{ligne['table']}.{ligne['colonne']} : NOT NULL dans la cible, nullable dans le "
                "schéma d'essai — un NULL passe sur la base d'essai et est refusé par la cible"
            )
    return constats
