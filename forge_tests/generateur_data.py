"""Générateur de cas — pan Data.

Le pan API générait déjà ; les autres pans non. Data est le plus dérivable des cinq : une
contrainte non exercée se teste toujours de la même façon — on la viole, on attend un rejet.

Contrairement au pan API, aucun invariant métier n est requis : la contrainte EST l invariant,
et le SQL de la migration dit exactement comment la violer. Le rappel y est donc naturellement
élevé là où il était nul côté API.

CE QUE TF-0840 A CORRIGÉ (lot Produit-61 du 05/09/2026), et pourquoi rien ne le disait. Les cas
générés passaient tous, et aucun ne mesurait quoi que ce soit : `_violer` attendait
`pytest.raises(Exception)`, donc une erreur de SYNTAXE SQL suffisait à faire passer le cas —
et il y en avait. Le nom de table était lu par `bloc.split("(")` juste après `CREATE TABLE`, ce
qui donnait « IF NOT EXISTS commande » sur un schéma écrit `CREATE TABLE IF NOT EXISTS`, donc
`INSERT INTO IF NOT EXISTS commande (…)`. L en-tête exigeait une fixture `moteur` qui n existait
pas chez le projet, et démolissait trois tables NOMMÉES EN DUR avec un `DROP … CASCADE` que tous
les moteurs n acceptent pas. Enfin l INSERT ne portait QUE la colonne visée : sur une table à
colonnes `NOT NULL`, il échouait pour une raison qui n était pas la contrainte mesurée. Coût :
56 cas relus et réécrits à la main.

Les quatre remèdes, dans l ordre de la chaîne : le nom de table est lu par une expression qui
connaît `IF NOT EXISTS` · la ligne insérée est une ligne VALIDE de la table, avec ses lignes
parentes semées d abord, dont on ne force QUE la valeur violante · le rejet attendu est
`IntegrityError`, jamais `Exception`, et le message doit citer la contrainte ou sa colonne ·
la fixture de moteur est FOURNIE par le fichier généré, sur une base jetable déclarée, et se
met en SKIP nommé plutôt qu en erreur quand elle manque.
"""

from __future__ import annotations

import re
from pathlib import Path

# Pan généré — voir `forge_tests.generateur.PAN`.
PAN = "data"

NON_JUGE = [
    "generateur data : la valeur violante est derivee du TYPE de contrainte (unicite, non-nullite, "
    "cle etrangere, verification) ; une contrainte de verification a expression complexe n est pas "
    "resolue et n est pas generee",
    "generateur data (TF-0840) : la ligne valide est derivee des colonnes NOT NULL declarees dans "
    "le CREATE TABLE ; une valeur exigee par un declencheur, une contrainte d exclusion ou une "
    "verification multi-colonnes n est pas devinee, et le cas genere echouera a la SEMENCE — "
    "visible, jamais silencieux, puisque le rejet attendu est nomme",
    "generateur data (TF-0840) : les lignes parentes ne sont semees que pour les cles etrangeres "
    "declarees en CONSTRAINT dans le corps de la table ; une cle etrangere posee par ALTER TABLE "
    "ou en REFERENCES de colonne n est pas vue, et sa ligne parente manquera",
]

_MOTEUR = "FORGE_TESTS_DATA_URL"

_ENTETE = '''"""Cas générés par Forge Tests — pan Data. À RELIRE AVANT USAGE.

Chaque cas viole UNE contrainte inventoriée et non exercée, et attend son rejet PAR LA BASE :
`IntegrityError`, et un message qui cite la contrainte ou sa colonne. Ni `Exception`, ni un
rejet anonyme — une erreur de syntaxe SQL ferait alors passer le cas sans rien mesurer
(TF-0840).

La ligne insérée est une ligne VALIDE de la table, dont SEULE la valeur violante est forcée ;
les lignes parentes exigées par les clés étrangères sont semées avant. Sans cela, l INSERT
échoue sur une colonne `NOT NULL` non renseignée et le cas mesure autre chose que sa contrainte.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

MIGRATIONS = sorted((Path(__file__).parent.parent / "migrations").glob("*.sql"))

#: Tables créées par les migrations, dans leur ordre de création — DÉRIVÉES du schéma, jamais
#: recopiées : une liste en dur démolissait les trois tables d un autre projet (TF-0840).
TABLES = [{tables}]


@pytest.fixture(scope="session")
def moteur_jetable():
    """Moteur sur une base JETABLE, déclarée par `{moteur}`.

    Fournie ici, et pas empruntée au projet : ces cas doivent pouvoir être joués tels quels.
    Si votre suite a déjà sa fixture de moteur, remplacez celle-ci par la vôtre — ces cas sont
    à ADOPTER, pas à exécuter en l état.

    JETABLE au sens strict : la fixture `base` DÉMOLIT puis reconstruit le schéma à chaque cas.
    Ne jamais pointer une base servie, de démonstration ou peuplée.
    """
    url = (os.environ.get("{moteur}") or "").strip()
    if not url:
        pytest.skip(
            "{moteur} absente : ces cas demolissent et reconstruisent le schema, "
            "ils exigent une base JETABLE — jamais une base servie ou peuplee"
        )
    return create_engine(url, future=True)


@pytest.fixture()
def base(moteur_jetable):
    """Schema reconstruit depuis les migrations, pour que chaque cas parte du meme etat."""
    with moteur_jetable.begin() as cx:
        for table in reversed(TABLES):
            cx.execute(text(f"DROP TABLE IF EXISTS {{table}}"))
    for migration in MIGRATIONS:
        haut = migration.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
        with moteur_jetable.begin() as cx:
            corps = haut.replace("-- +migrate Up", "")
            for instruction in [s.strip() for s in corps.split(";") if s.strip()]:
                cx.execute(text(instruction))
    return moteur_jetable


def _violer(base, instruction: str, indices: tuple[str, ...]) -> None:
    """Joue les instructions et exige un rejet D INTEGRITE qui nomme la contrainte visee.

    Les moteurs ne nomment pas la meme chose : PostgreSQL cite la CONTRAINTE, SQLite cite
    `table.colonne`. On accepte l un ou l autre — mais pas un rejet muet, et surtout pas une
    erreur de syntaxe, qui ne leve pas `IntegrityError`.
    """
    with pytest.raises(IntegrityError) as capture:
        with base.begin() as cx:
            for morceau in [s.strip() for s in instruction.split(";") if s.strip()]:
                cx.execute(text(morceau))
    message = str(capture.value).lower()
    assert any(indice.lower() in message for indice in indices), (
        f"rejet d integrite obtenu, mais il ne nomme aucun de {{indices}} : {{message}}"
    )
'''

_CAS = '''

# {id}  (risque {risque})
def test_genere_{nom}(base) -> None:
    _violer(base, "{sql}", {indices})
'''

_UNIQUE = re.compile(r"CONSTRAINT (\w+) UNIQUE \((\w+)\)", re.IGNORECASE)
_CHECK = re.compile(r"CONSTRAINT (\w+) CHECK \(([^)]+)\)", re.IGNORECASE)
_FK = re.compile(
    r"CONSTRAINT (\w+) FOREIGN KEY \((\w+)\) REFERENCES (\w+)", re.IGNORECASE
)

#: Ce qui suit `CREATE TABLE` : un `IF NOT EXISTS` facultatif, un schéma facultatif, puis le nom,
#: éventuellement cité. TF-0840 : `bloc.split("(")` rendait « IF NOT EXISTS commande », et le cas
#: généré produisait `INSERT INTO IF NOT EXISTS commande (…)` — une erreur de SYNTAXE.
_APRES_CREATE = re.compile(
    r"^(?:IF\s+NOT\s+EXISTS\s+)?(?:[`\"\[]?\w+[`\"\]]?\.)?[`\"\[]?(\w+)[`\"\]]?",
    re.IGNORECASE,
)

#: Ce qui, dans une déclaration de colonne, dit que la base la remplit elle-même.
_AUTOMATIQUE = re.compile(
    r"\b(SERIAL|BIGSERIAL|SMALLSERIAL|AUTOINCREMENT|AUTO_INCREMENT|GENERATED|DEFAULT|"
    r"PRIMARY\s+KEY)\b",
    re.IGNORECASE,
)

#: Une ligne du corps qui déclare une contrainte, pas une colonne.
_LIGNE_CONTRAINTE = re.compile(
    r"^\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE|CHECK|FOREIGN\s+KEY|EXCLUDE)\b", re.IGNORECASE
)

#: Valeur valide par famille de type. La table est courte EXPRÈS : un type inconnu retombe sur
#: une chaîne, et le cas généré échouera visiblement à la semence plutôt que silencieusement.
_VALEURS = (
    (re.compile(r"\b(INT|INTEGER|BIGINT|SMALLINT|SERIAL|NUMERIC|DECIMAL|REAL|DOUBLE|FLOAT)",
                re.IGNORECASE), "1"),
    (re.compile(r"\bBOOL", re.IGNORECASE), "TRUE"),
    (re.compile(r"\b(TIMESTAMP|DATETIME|DATE)", re.IGNORECASE), "'2026-01-01'"),
)

_VALEUR_TEXTE = "'valeur'"
#: Valeur d une clé étrangère dont la ligne parente A ÉTÉ SEMÉE : première ligne, donc 1.
_VALEUR_PARENTE = "1"
#: Valeur d une clé étrangère qu on veut violer : aucune ligne parente ne la porte.
_VALEUR_ORPHELINE = "999999"


def _nom_de_table(apres_create: str) -> str | None:
    """Nom de la table dans ce qui suit `CREATE TABLE` — `IF NOT EXISTS` et schéma compris."""
    trouve = _APRES_CREATE.match(apres_create.strip())
    return trouve.group(1) if trouve else None


def _blocs(migrations: str) -> list[tuple[str, str]]:
    """`(table, corps)` pour chaque `CREATE TABLE` du schéma, corps borné au `;` qui le ferme."""
    trouves: list[tuple[str, str]] = []
    for bloc in re.split(r"CREATE TABLE ", migrations, flags=re.IGNORECASE)[1:]:
        nom = _nom_de_table(bloc)
        if nom is None:
            continue
        # Le corps commence APRÈS la parenthèse ouvrante : sans cela la première ligne
        # (« IF NOT EXISTS commande ( ») se lisait comme une déclaration de colonne.
        trouves.append((nom, bloc.split(";")[0].partition("(")[2]))
    return trouves


def _corps_de(table: str, migrations: str) -> str | None:
    for nom, corps in _blocs(migrations):
        if nom == table:
            return corps
    return None


def _table_de(fichier_sql: str, contrainte: str) -> str | None:
    """Table portant la contrainte, lue dans le CREATE TABLE qui la contient."""
    for nom, corps in _blocs(fichier_sql):
        if contrainte in corps:
            return nom
    return None


def _table_ayant_colonne(colonne: str, migrations: str) -> str | None:
    for nom, corps in _blocs(migrations):
        if re.search(rf"^\s*{colonne}\s", corps, re.MULTILINE):
            return nom
    return None


def _fk_de(table: str, migrations: str) -> list[re.Match]:
    corps = _corps_de(table, migrations) or ""
    return list(_FK.finditer(corps))


def _contrainte_de_colonne(table: str, colonne: str, migrations: str) -> str | None:
    """Valeur imposée à cette colonne par un CHECK, quand le CHECK est résoluble.

    Deux formes seulement, et c est déclaré au `non_juge` : `col IN (…)` — on prend la première
    valeur listée — et `col > n` — on prend `n + 1`. Le reste n est pas deviné.
    """
    for corps in (_corps_de(table, migrations) or "", migrations):
        for trouve in _CHECK.finditer(corps):
            expression = trouve.group(2)
            liste = re.match(rf"\s*{colonne}\s+IN\s*\((.+)$", expression, re.IGNORECASE)
            if liste:
                premiere = liste.group(1).split(",")[0].strip().rstrip(")")
                if premiere:
                    return premiere
            borne = re.match(rf"\s*{colonne}\s*>\s*(-?\d+)", expression, re.IGNORECASE)
            if borne:
                return str(int(borne.group(1)) + 1)
    return None


def _colonnes_a_remplir(table: str, migrations: str) -> dict[str, str]:
    """`{colonne: littéral valide}` pour ce qu il FAUT renseigner sur cette table.

    Retenu : les colonnes `NOT NULL` que la base ne remplit pas elle-même. C est le minimum qui
    fait passer l INSERT, et le maximum qu on puisse dériver du seul `CREATE TABLE`.
    """
    corps = _corps_de(table, migrations)
    if corps is None:
        return {}
    etrangeres = {m.group(2) for m in _FK.finditer(corps)}
    valeurs: dict[str, str] = {}
    for ligne in corps.splitlines():
        ligne = ligne.strip().rstrip(",")
        if not ligne or _LIGNE_CONTRAINTE.match(ligne) or ligne.startswith(("(", ")", "--")):
            continue
        declaration = ligne.lstrip("(").strip()
        mots = declaration.split()
        if len(mots) < 2:
            continue
        colonne = mots[0].strip('`"[]')
        if not re.match(r"^\w+$", colonne):
            continue
        if _AUTOMATIQUE.search(declaration) or not re.search(
            r"\bNOT\s+NULL\b", declaration, re.IGNORECASE
        ):
            continue
        valeurs[colonne] = _valeur_pour(table, colonne, declaration, migrations, etrangeres)
    return valeurs


def _valeur_pour(
    table: str, colonne: str, declaration: str, migrations: str, etrangeres: set[str]
) -> str:
    if colonne in etrangeres:
        return _VALEUR_PARENTE
    impose = _contrainte_de_colonne(table, colonne, migrations)
    if impose is not None:
        return impose
    for motif, valeur in _VALEURS:
        if motif.search(declaration):
            return valeur
    return _VALEUR_TEXTE


def _insert(table: str, valeurs: dict[str, str]) -> str:
    colonnes = ", ".join(valeurs)
    litteraux = ", ".join(valeurs.values())
    return f"INSERT INTO {table} ({colonnes}) VALUES ({litteraux})"


def _semences(table: str, migrations: str, vues: set[str] | None = None) -> list[str]:
    """Les lignes PARENTES qu exigent les clés étrangères de `table`, ancêtres d abord.

    Sans elles, une ligne pourtant valide est rejetée pour une clé étrangère orpheline — et le
    cas mesure alors une contrainte qui n est pas la sienne.
    """
    vues = vues if vues is not None else {table}
    instructions: list[str] = []
    for trouve in _fk_de(table, migrations):
        parent = trouve.group(3)
        if parent in vues:
            continue
        vues.add(parent)
        instructions.extend(_semences(parent, migrations, vues))
        instructions.append(_insert(parent, _colonnes_a_remplir(parent, migrations)))
    return instructions


def _ligne_violante(
    table: str, migrations: str, forcages: dict[str, str], repetitions: int = 1
) -> str:
    """Les semences, puis la ligne valide de `table` dont SEULES `forcages` sont forcées."""
    valeurs = _colonnes_a_remplir(table, migrations)
    valeurs.update(forcages)
    instructions = _semences(table, migrations)
    instructions.extend([_insert(table, valeurs)] * repetitions)
    return "; ".join(instructions)


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
        violation = _violation(nom, migrations)
        if violation is None:
            continue
        instruction, indices = violation
        cas.append(
            _CAS.format(
                id=finding["id"],
                risque=finding["risque"],
                nom=re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_"),
                sql=instruction.replace('"', "'"),
                indices=repr(indices),
            )
        )
        if len(cas) >= limite:
            break
    return entete(migrations) + "".join(cas) if cas else ""


def entete(migrations: str) -> str:
    """L en-tête du fichier généré, avec la liste des tables DÉRIVÉE du schéma."""
    tables = [nom for nom, _ in _blocs(migrations)]
    return _ENTETE.format(
        tables=", ".join(f'"{nom}"' for nom in tables),
        moteur=_MOTEUR,
    )


def _violation(contrainte: str, migrations: str) -> tuple[str, tuple[str, ...]] | None:
    """`(instructions SQL, indices attendus dans le message)` — ou None si non dérivable."""
    if contrainte.endswith(".not_null"):
        colonne = contrainte[: -len(".not_null")]
        table = _table_ayant_colonne(colonne, migrations)
        if table is None:
            return None
        return _ligne_violante(table, migrations, {colonne: "NULL"}), (colonne, "null")
    for motif, fabrique in (
        (_UNIQUE, _violer_unique),
        (_CHECK, _violer_check),
        (_FK, _violer_fk),
    ):
        for correspondance in motif.finditer(migrations):
            if correspondance.group(1) == contrainte:
                return fabrique(correspondance, migrations)
    return None


def _violer_unique(m: re.Match, migrations: str) -> tuple[str, tuple[str, ...]] | None:
    table = _table_de(migrations, m.group(1))
    colonne = m.group(2)
    if table is None:
        return None
    # La MÊME ligne valide, deux fois, la colonne visée FORCÉE à une valeur fixe — sans quoi une
    # colonne à `DEFAULT` (donc absente de la ligne dérivée) ne serait pas dupliquée du tout.
    corps = _corps_de(table, migrations) or ""
    declaration = ""
    for ligne in corps.splitlines():
        if re.match(rf"^\s*{colonne}\s", ligne):
            declaration = ligne
            break
    valeur = _valeur_pour(table, colonne, declaration, migrations, set())
    return (
        _ligne_violante(table, migrations, {colonne: valeur}, repetitions=2),
        (m.group(1), colonne, "unique"),
    )


def _violer_check(m: re.Match, migrations: str) -> tuple[str, tuple[str, ...]] | None:
    table = _table_de(migrations, m.group(1))
    expression = m.group(2)
    if table is None:
        return None
    borne = re.match(r"\s*(\w+)\s*>\s*(-?\d+)", expression)
    if borne is not None:
        colonne, valeur = borne.group(1), borne.group(2)
        return (
            _ligne_violante(table, migrations, {colonne: valeur}),
            (m.group(1), colonne, "check"),
        )
    liste = re.match(r"\s*(\w+)\s+IN\s*\(", expression, re.IGNORECASE)
    if liste is not None:
        colonne = liste.group(1)
        return (
            _ligne_violante(table, migrations, {colonne: "'hors_domaine'"}),
            (m.group(1), colonne, "check"),
        )
    return None  # expression complexe : non resolue, declaree au non_juge


def _violer_fk(m: re.Match, migrations: str) -> tuple[str, tuple[str, ...]] | None:
    table = _table_de(migrations, m.group(1))
    colonne = m.group(2)
    if table is None:
        return None
    return (
        _ligne_violante(table, migrations, {colonne: _VALEUR_ORPHELINE}),
        (m.group(1), colonne, "foreign key"),
    )


def ecrire(rapport: dict, cible: Path, destination: Path) -> Path | None:
    contenu = construire(rapport, cible)
    if not contenu:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    fichier = destination / "test_genere_data.py"
    fichier.write_text(contenu, encoding="utf-8")
    return fichier
