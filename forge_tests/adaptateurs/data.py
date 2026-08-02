"""Adaptateur Data (SQL) — tables et contraintes depuis les migrations, exercées PAR VIOLATION."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.execution import instructions_sql, violations_levees
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "data-sql", "data", 1.0
_TABLE = re.compile(r"CREATE TABLE (\w+)\s*\(", re.IGNORECASE)
_CONTRAINTE = re.compile(r"CONSTRAINT (\w+)", re.IGNORECASE)
_NOT_NULL = re.compile(r"^\s*(\w+)\s+\w+\s+NOT NULL", re.IGNORECASE | re.MULTILINE)
_INDEX = re.compile(r"CREATE (?:UNIQUE )?INDEX (\w+)", re.IGNORECASE)
_TRIGGER = re.compile(r"CREATE TRIGGER (\w+)", re.IGNORECASE)

_ORM_NOMMEE = re.compile(r"(?:UniqueConstraint|CheckConstraint|ForeignKey)\([^)]*name=\"(\w+)\"")
_ORM_NOT_NULL = re.compile(r"^\s*(\w+)\s*=\s*Column\([^)]*nullable=False", re.MULTILINE)

# PostgreSQL nomme TOUTES ses contraintes, cles etrangeres comprises.
_PG_NOMMEE = re.compile(r'violates (?:foreign key|unique|check) constraint "(\w+)"')
_PG_NOT_NULL = re.compile(r'null value in column "(\w+)" of relation "\w+"')
# SQLite : conserve pour les projets qui l utilisent, avec son angle mort sur les cles etrangeres.
_NN = re.compile(r"NOT NULL constraint failed: (\w+)\.(\w+)")
_CK = re.compile(r"CHECK constraint failed: (\w+)")
_UQ = re.compile(r"UNIQUE constraint failed: (\w+)\.(\w+)")

NON_JUGE = [
    "data : sur SQLite les clés étrangères restent non attribuables (le moteur ne nomme pas la "
    "contrainte violée) ; l attribution complète exige un moteur qui les nomme, comme PostgreSQL",
    "data : un index ou un trigger est réputé exercé si son instruction de création a été "
    "envoyée au moteur ; son EFFET (unicité réellement testée, trigger réellement déclenché) "
    "n est pas vérifié",
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
        for nom in _INDEX.findall(haut):
            cle = f"index:{nom}"
            if cle not in vus:
                vus.add(cle)
                elements.append(Element(cle, PAN, f"index {nom}", str(fichier)))
        for nom in _TRIGGER.findall(haut):
            cle = f"trigger:{nom}"
            if cle not in vus:
                vus.add(cle)
                elements.append(Element(cle, PAN, f"trigger {nom}", str(fichier)))
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
        trouve = _PG_NOMMEE.search(message)
        if trouve:
            couvert.add(f"contrainte:{trouve.group(1)}")
            continue
        trouve = _PG_NOT_NULL.search(message)
        if trouve:
            couvert.add(f"contrainte:{trouve.group(1)}.not_null")
            continue
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

    # Tables, index et triggers : exerces si une instruction envoyee au moteur les nomme.
    # Plus de repli textuel — c est l execution qui tranche, pour toutes les classes.
    envoyees = instructions_sql(cible) or []
    corpus = " ".join(envoyees).lower()
    for element in inv:
        classe, nom = element.id.split(":", 1)
        if classe in ("table", "index", "trigger") and nom.lower() in corpus:
            couvert.add(element.id)
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
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, "sonde indisponible : suite rouge ou environnement absent"],
        )
    inv = inventaire(cible)
    sortie = evaluer_surface(NOM, PAN, str(cible), inv, couvert, SEUIL, NON_JUGE)

    # Une contrainte declaree au MODELE mais absente des MIGRATIONS est une divergence : le code
    # croit la base protegee, la base ne l est pas. Aucun test ne peut la reveler — il n y a rien
    # a violer. Seule la comparaison des deux sources la nomme.
    migrations = " ".join(f.read_text(encoding="utf-8") for f in _sql(cible))
    modeles = cible / "backend" / "app" / "models.py"
    if modeles.exists():
        for nom in _ORM_NOMMEE.findall(modeles.read_text(encoding="utf-8")):
            if nom in migrations:
                continue
            sortie.findings.append(
                Finding(
                    id=f"divergence:contrainte:{nom}",
                    classe="divergence",
                    localisation=str(modeles),
                    message=(
                        f"contrainte {nom} declaree au modele mais absente des migrations : "
                        "la base ne l applique pas"
                    ),
                    risque=coter(PAN, f"contrainte:{nom}", str(modeles)),
                )
            )
            sortie.verdict = "FAIL"
    return sortie
