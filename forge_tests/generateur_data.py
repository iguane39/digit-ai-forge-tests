"""Générateur de cas — pan Data.

Le pan API générait déjà ; les autres pans non. Data est le plus dérivable des cinq : une
contrainte non exercée se teste toujours de la même façon — on la viole, on attend un rejet.

Contrairement au pan API, aucun invariant métier n est requis : la contrainte EST l invariant,
et le SQL de la migration dit exactement comment la violer. Le rappel y est donc naturellement
élevé là où il était nul côté API.
"""

from __future__ import annotations

import re
from pathlib import Path

NON_JUGE = [
    "generateur data : la valeur violante est derivee du TYPE de contrainte (unicite, non-nullite, "
    "cle etrangere, verification) ; une contrainte de verification a expression complexe n est pas "
    "resolue et n est pas generee",
]

ENTETE = '''"""Cas générés par Forge Tests — pan Data. À RELIRE AVANT USAGE.

Chaque cas viole UNE contrainte inventoriée et non exercée, et attend son rejet par la base.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

MIGRATIONS = sorted((Path(__file__).parent.parent / "migrations").glob("*.sql"))


@pytest.fixture()
def base(moteur):
    """Schema reconstruit depuis les migrations, pour que chaque cas parte du meme etat."""
    with moteur.begin() as cx:
        for table in ("ligne_commande", "commande", "utilisateur"):
            cx.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    for migration in MIGRATIONS:
        haut = migration.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
        with moteur.begin() as cx:
            for instruction in [s.strip() for s in haut.replace("-- +migrate Up", "").split(";") if s.strip()]:
                cx.execute(text(instruction))
    return moteur


def _violer(base, instruction: str) -> None:
    with pytest.raises(Exception):
        with base.begin() as cx:
            for morceau in [s.strip() for s in instruction.split(";") if s.strip()]:
                cx.execute(text(morceau))
'''

_CAS = '''

# {id}  (risque {risque})
def test_genere_{nom}(base) -> None:
    _violer(base, "{sql}")
'''

_UNIQUE = re.compile(r"CONSTRAINT (\w+) UNIQUE \((\w+)\)", re.IGNORECASE)
_CHECK = re.compile(r"CONSTRAINT (\w+) CHECK \(([^)]+)\)", re.IGNORECASE)
_FK = re.compile(
    r"CONSTRAINT (\w+) FOREIGN KEY \((\w+)\) REFERENCES (\w+)", re.IGNORECASE
)


def _table_de(fichier_sql: str, contrainte: str) -> str | None:
    """Table portant la contrainte, lue dans le CREATE TABLE qui la contient."""
    for bloc in re.split(r"CREATE TABLE ", fichier_sql, flags=re.IGNORECASE)[1:]:
        nom = bloc.split("(", 1)[0].strip()
        if contrainte in bloc:
            return nom
    return None


def construire(rapport: dict, cible: Path, limite: int = 20) -> str:
    """Produit un fichier de tests violant chaque contrainte non exercée, par risque."""
    migrations = "\n".join(
        f.read_text(encoding="utf-8")
        for f in sorted((cible / "backend" / "migrations").glob("*.sql"))
    )
    cas: list[str] = []
    for finding in rapport["findings"]:
        if finding["classe"] != "element-non-exerce" or not finding["id"].startswith("contrainte:"):
            continue
        nom = finding["id"].split(":", 1)[1]
        instruction = _violation(nom, migrations)
        if instruction is None:
            continue
        cas.append(
            _CAS.format(
                id=finding["id"],
                risque=finding["risque"],
                nom=re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_"),
                sql=instruction.replace('"', "'"),
            )
        )
        if len(cas) >= limite:
            break
    return ENTETE + "".join(cas) if cas else ""


def _violation(contrainte: str, migrations: str) -> str | None:
    """Instruction SQL qui viole la contrainte nommée, dérivée de sa déclaration."""
    if contrainte.endswith(".not_null"):
        colonne = contrainte[: -len(".not_null")]
        table = _table_ayant_colonne(colonne, migrations)
        return None if table is None else f"INSERT INTO {table} ({colonne}) VALUES (NULL)"
    trouve = _UNIQUE.search(migrations) if contrainte in migrations else None
    for motif, fabrique in (
        (_UNIQUE, lambda m: _violer_unique(m, migrations)),
        (_CHECK, lambda m: _violer_check(m, migrations)),
        (_FK, lambda m: _violer_fk(m, migrations)),
    ):
        for correspondance in motif.finditer(migrations):
            if correspondance.group(1) == contrainte:
                return fabrique(correspondance)
    return trouve and None


def _table_ayant_colonne(colonne: str, migrations: str) -> str | None:
    for bloc in re.split(r"CREATE TABLE ", migrations, flags=re.IGNORECASE)[1:]:
        nom = bloc.split("(", 1)[0].strip()
        if re.search(rf"^\s*{colonne}\s", bloc.split(";")[0], re.MULTILINE):
            return nom
    return None


def _violer_unique(m: re.Match, migrations: str) -> str | None:
    table = _table_de(migrations, m.group(1))
    colonne = m.group(2)
    if table is None:
        return None
    return (
        f"INSERT INTO {table} ({colonne}) VALUES ('doublon'); "
        f"INSERT INTO {table} ({colonne}) VALUES ('doublon')"
    )


def _violer_check(m: re.Match, migrations: str) -> str | None:
    table = _table_de(migrations, m.group(1))
    expression = m.group(2)
    borne = re.match(r"\s*(\w+)\s*>\s*(-?\d+)", expression)
    if table is None or borne is None:
        return None  # expression complexe : non resolue, declaree au non_juge
    return f"INSERT INTO {table} ({borne.group(1)}) VALUES ({borne.group(2)})"


def _violer_fk(m: re.Match, migrations: str) -> str | None:
    table = _table_de(migrations, m.group(1))
    colonne = m.group(2)
    if table is None:
        return None
    return f"INSERT INTO {table} ({colonne}) VALUES (999999)"


def ecrire(rapport: dict, cible: Path, destination: Path) -> Path | None:
    contenu = construire(rapport, cible)
    if not contenu:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    fichier = destination / "test_genere_data.py"
    fichier.write_text(contenu, encoding="utf-8")
    return fichier
