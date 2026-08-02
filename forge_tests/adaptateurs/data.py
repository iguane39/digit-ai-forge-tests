"""Adaptateur Data (SQL) — tables et contraintes depuis les migrations, exercées PAR VIOLATION."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.execution import violations_levees
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "data-sql", "data", 1.0
_TABLE = re.compile(r"CREATE TABLE (\w+)\s*\(", re.IGNORECASE)
_CONTRAINTE = re.compile(r"CONSTRAINT (\w+)", re.IGNORECASE)
_NOT_NULL = re.compile(r"^\s*(\w+)\s+\w+\s+NOT NULL", re.IGNORECASE | re.MULTILINE)

_ORM_NOMMEE = re.compile(r"(?:UniqueConstraint|CheckConstraint|ForeignKey)\([^)]*name=\"(\w+)\"")
_ORM_NOT_NULL = re.compile(r"^\s*(\w+)\s*=\s*Column\([^)]*nullable=False", re.MULTILINE)

_NN = re.compile(r"NOT NULL constraint failed: (\w+)\.(\w+)")
_CK = re.compile(r"CHECK constraint failed: (\w+)")
_UQ = re.compile(r"UNIQUE constraint failed: (\w+)\.(\w+)")

NON_JUGE = [
    "data : les clés étrangères ne sont PAS attribuables par exécution — SQLite ne nomme pas la "
    "contrainte dans « FOREIGN KEY constraint failed ». Elles restent sur le recoupement "
    "textuel, moins sûr, jusqu à confrontation à un moteur qui nomme ses contraintes",
    "data : la présence d une table est déduite du texte des tests, pas de son usage réel",
    "data : triggers et index partiels ne sont pas inventoriés",
]


def _sql(cible: Path) -> list[Path]:
    return sorted((cible / "backend" / "migrations").glob("*.sql"))


def inventaire(cible: Path) -> list[Element]:
    elements: list[Element] = []
    vus: set[str] = set()
    for fichier in _sql(cible):
        haut = fichier.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
        for table in _TABLE.findall(haut):
            if f"table:{table}" not in vus and not table.endswith(("_nouveau", "_ancien")):
                vus.add(f"table:{table}")
                elements.append(Element(f"table:{table}", PAN, f"table {table}", str(fichier)))
        for nom in _CONTRAINTE.findall(haut):
            if f"contrainte:{nom}" not in vus:
                vus.add(f"contrainte:{nom}")
                elements.append(
                    Element(f"contrainte:{nom}", PAN, f"contrainte {nom}", str(fichier))
                )
        for colonne in _NOT_NULL.findall(haut):
            cle = f"contrainte:{colonne}.not_null"
            if cle not in vus:
                vus.add(cle)
                elements.append(Element(cle, PAN, f"{colonne} NOT NULL", str(fichier)))

    # Contraintes declarees dans l ORM : elles existent au modele meme si aucune migration ne
    # les porte. Leur absence des migrations est justement le genre de divergence a exposer.
    modeles = cible / "backend" / "app" / "models.py"
    if modeles.exists():
        source = modeles.read_text(encoding="utf-8")
        for nom in _ORM_NOMMEE.findall(source):
            cle = f"contrainte:{nom}"
            if cle not in vus:
                vus.add(cle)
                elements.append(
                    Element(cle, PAN, f"contrainte {nom} (ORM, hors migration)", str(modeles))
                )
        for colonne in _ORM_NOT_NULL.findall(source):
            cle = f"contrainte:{colonne}.not_null"
            if cle not in vus:
                vus.add(cle)
                elements.append(
                    Element(cle, PAN, f"{colonne} NOT NULL (ORM)", str(modeles))
                )
    return elements


def blocs_de_test(texte: str) -> list[str]:
    """Découpe en blocs de test, commentaires de tête RATTACHÉS à leur def.

    Sans ce rattachement, un test annoté du nom de la contrainte qu il exerce passerait pour
    ne pas la couvrir : le commentaire tomberait dans le bloc précédent.
    """
    blocs: list[str] = []
    report = ""
    for morceau in re.split(r"\n(?=def )", texte):
        lignes = morceau.splitlines()
        fin = len(lignes)
        while fin > 0 and (lignes[fin - 1].strip().startswith("#") or not lignes[fin - 1].strip()):
            fin -= 1
        blocs.append(report + "\n".join(lignes[:fin]))
        report = "\n".join(lignes[fin:]) + "\n"
    if report.strip():
        blocs.append(report)
    return blocs


def exerces(cible: Path) -> set[str] | None:
    """Contraintes RÉELLEMENT violées pendant la suite, lues dans les erreurs de la base.

    Repli textuel assumé et déclaré pour les tables et les clés étrangères : SQLite ne nomme
    pas la contrainte de clé étrangère violée, donc aucune attribution n est possible.
    """
    violations = violations_levees(cible)
    if violations is None:
        return None
    inv = inventaire(cible)
    noms = {e.id.split(":", 1)[1] for e in inv}
    couvert: set[str] = set()

    for message in violations:
        trouve = _NN.search(message)
        if trouve:
            couvert.add(f"contrainte:{trouve.group(2)}.not_null")
            continue
        trouve = _CK.search(message)
        if trouve:
            couvert.add(f"contrainte:{trouve.group(1)}")
            continue
        trouve = _UQ.search(message)
        if trouve:
            table, colonne = trouve.groups()
            for nom in noms:
                if table in nom and colonne in nom:
                    couvert.add(f"contrainte:{nom}")

    # Repli DÉCLARÉ : tables et clés étrangères, non attribuables par exécution.
    a_repli = {e.id for e in inv if e.id.startswith("table:") or e.id.endswith("_fk")}
    couvert |= _repli_textuel(cible, [e for e in inv if e.id in a_repli])
    return couvert


def _repli_textuel(cible: Path, elements: list[Element]) -> set[str]:
    couvert: set[str] = set()
    for fichier in sorted((cible / "backend" / "tests").glob("test_*.py")):
        for bloc in blocs_de_test(fichier.read_text(encoding="utf-8")):
            rejet_attendu = "raises" in bloc
            for element in elements:
                cle = element.id.split(":", 1)[1]
                if element.id.startswith("table:"):
                    if cle in bloc.lower():
                        couvert.add(element.id)
                    continue
                colonne = cle.replace(".not_null", "")
                if rejet_attendu and (cle in bloc or colonne in bloc):
                    couvert.add(element.id)
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    return evaluer_surface(NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE)
