"""Schéma d un projet lu dans ses migrations SQL — la matière de la fabrique de données (TF-2012).

La fabrique (`forge_tests.fabrique_donnees`) doit savoir ce qu une ligne VALIDE exige de chaque
table : ses colonnes et leurs types, ce qui ne peut pas être nul, ce qui doit être unique, ce
qu une clé étrangère oblige à semer d abord, ce qu une vérification (`CHECK`) borne ou énumère.
Ce module le lit dans les sections « Up » des migrations, jouées dans l ordre des fichiers : une
colonne ajoutée par `ALTER TABLE`, une contrainte posée puis retirée, une table supprimée
comptent comme le moteur les comptera.

Un seul lecteur, une seule vérité sur ce que contient une migration : les fichiers et leurs
sections sont ceux de l adaptateur `migrations` (`_fichiers`, `_sections`), le découpage celui
de `forge_tests.sql` (commentaires retirés AVANT de couper, littéraux préservés — RT-8).

Rien n est deviné en silence. Une instruction que ce lecteur ne modélise pas (fonction, vue,
déclencheur, données insérées) est COMPTÉE par nature ; une vérification qu il ne sait pas
interpréter est gardée avec son expression et marquée telle. C est le chargement réel, pas
cette lecture, qui dira si un jeu la tient.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from forge_tests.adaptateurs.migrations import _fichiers, _sections
from forge_tests.sql import decouper

NON_JUGE = [
    "schema sql : la lecture suit le decoupage de `forge_tests.sql` — un corps dollar-quote "
    "($$...$$) qui contient un `;` est coupe au mauvais endroit, et un litteral dont les espaces "
    "sont multiples est normalise par le decoupage",
    "schema sql : seuls CREATE / ALTER / DROP TABLE, CREATE / DROP INDEX, CREATE / ALTER / DROP "
    "TYPE ... AS ENUM et CREATE DOMAIN sont modelises ; les autres instructions (fonctions, "
    "vues, declencheurs, sequences, donnees inserees par la migration) sont COMPTEES par "
    "nature, pas lues",
    "schema sql : le nom implicite d une contrainte non nommee est reconstitue a la maniere de "
    "PostgreSQL (`<table>_<colonne>_key`, `_fkey`, `_check`, `_pkey`) sans sa troncature a 63 "
    "octets ni ses suffixes de dedoublonnage — un DROP CONSTRAINT qui vise un autre nom n est pas "
    "applique, et le dit",
    "schema sql : deux tables de meme nom dans deux schemas differents ne sont pas distinguees ; "
    "les colonnes heritees (INHERITS) et les partitions (PARTITION OF) ne sont pas lues",
    "schema sql : une contrainte posee par ALTER DOMAIN, ou une verification de domaine ajoutee "
    "apres la creation d une colonne qui l utilise, n est pas reportee sur la colonne",
]


# --- Lexique ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Jeton:
    """Unité lexicale d une instruction : mot nu, identifiant cité, chaîne, nombre ou opérateur.

    `valeur` est ce que le MOTEUR comprend : un mot nu est replié en minuscules (PostgreSQL le
    fait), un identifiant cité garde sa casse, une chaîne est déséchappée. `texte` est ce qui
    était ÉCRIT, et sert à restituer une expression telle que la migration la porte.
    """

    genre: str
    valeur: str
    texte: str

    def est(self, *mots: str) -> bool:
        return self.genre == "mot" and self.valeur in mots

    def est_op(self, *ops: str) -> bool:
        return self.genre == "op" and self.valeur in ops

    @property
    def nom(self) -> str | None:
        return self.valeur if self.genre in ("mot", "ident") else None


_LEXEMES = re.compile(
    r"""
      (?P<blanc>\s+)
    | (?P<chaine_e>[eE]'(?:[^'\\]|\\.|'')*')
    | (?P<chaine>'(?:[^']|'')*')
    | (?P<dollar>\$\$.*?\$\$|\$(?P<balise>[A-Za-z_]\w*)\$.*?\$(?P=balise)\$)
    | (?P<ident>"(?:[^"]|"")*")
    | (?P<nombre>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)
    | (?P<mot>[^\W\d]\w*(?:\$\w*)*)
    | (?P<op>::|<=|>=|<>|!=|\|\||!~\*|!~|~\*|[^\s\w])
    """,
    re.VERBOSE | re.DOTALL,
)

_ECHAPPEMENTS = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}


def _desechapper_e(corps: str) -> str:
    """Contenu d une chaîne `E'…'` : antislashs interprétés, `''` rendu en `'`."""
    sortie: list[str] = []
    indice = 0
    while indice < len(corps):
        caractere = corps[indice]
        if caractere == "\\" and indice + 1 < len(corps):
            suivant = corps[indice + 1]
            sortie.append(_ECHAPPEMENTS.get(suivant, suivant))
            indice += 2
            continue
        if caractere == "'" and corps.startswith("''", indice):
            sortie.append("'")
            indice += 2
            continue
        sortie.append(caractere)
        indice += 1
    return "".join(sortie)


def lexer(texte: str) -> list[Jeton]:
    """Jetons d une instruction déjà découpée et débarrassée de ses commentaires."""
    jetons: list[Jeton] = []
    for trouve in _LEXEMES.finditer(texte):
        genre = trouve.lastgroup
        brut = trouve.group(0)
        if genre == "blanc":
            continue
        if genre == "chaine_e":
            jetons.append(Jeton("chaine", _desechapper_e(brut[2:-1]), brut))
        elif genre == "chaine":
            jetons.append(Jeton("chaine", brut[1:-1].replace("''", "'"), brut))
        elif genre == "dollar":
            balise = brut[: brut.index("$", 1) + 1]
            jetons.append(Jeton("chaine", brut[len(balise) : -len(balise)], brut))
        elif genre == "ident":
            jetons.append(Jeton("ident", brut[1:-1].replace('""', '"'), brut))
        elif genre == "mot":
            jetons.append(Jeton("mot", brut.lower(), brut))
        elif genre in ("nombre", "op"):
            jetons.append(Jeton(genre, brut, brut))
    return jetons


#: Mots après lesquels une parenthèse ouvrante garde son blanc : `IN (…)`, `CHECK (…)`.
_MOTS_AVANT_PARENTHESE = frozenset(
    {"in", "and", "or", "not", "check", "any", "all", "some", "exists", "values", "key",
     "references", "as", "on", "unique", "between", "then", "else", "when", "is"}
)


def restituer(jetons: list[Jeton]) -> str:
    """Le texte d une suite de jetons, espacé comme on l écrirait."""
    morceaux: list[str] = []
    precedent: Jeton | None = None
    for jeton in jetons:
        appel = (
            jeton.est_op("(") and precedent is not None and precedent.nom is not None
            and precedent.valeur not in _MOTS_AVANT_PARENTHESE
        )
        colle = precedent is not None and (
            appel
            or jeton.est_op(")", ",", "]", "::", ".", "[")
            or precedent.est_op("(", "[", "::", ".")
        )
        if morceaux and not colle:
            morceaux.append(" ")
        morceaux.append(jeton.texte)
        precedent = jeton
    return "".join(morceaux)


def scinder(jetons: list[Jeton], separateur: str = ",") -> list[list[Jeton]]:
    """Morceaux séparés au niveau 0 — une virgule entre parenthèses ne sépare rien."""
    morceaux: list[list[Jeton]] = [[]]
    profondeur = 0
    for jeton in jetons:
        if jeton.est_op("(", "["):
            profondeur += 1
        elif jeton.est_op(")", "]"):
            profondeur -= 1
        elif profondeur == 0 and jeton.est_op(separateur):
            morceaux.append([])
            continue
        morceaux[-1].append(jeton)
    return [morceau for morceau in morceaux if morceau]


class _Curseur:
    """Lecture séquentielle d une suite de jetons, sans retour arrière implicite."""

    def __init__(self, jetons: list[Jeton]) -> None:
        self.jetons = jetons
        self.indice = 0

    def fini(self) -> bool:
        return self.indice >= len(self.jetons)

    def voir(self, decalage: int = 0) -> Jeton | None:
        position = self.indice + decalage
        return self.jetons[position] if 0 <= position < len(self.jetons) else None

    def suivant(self) -> Jeton | None:
        jeton = self.voir()
        if jeton is not None:
            self.indice += 1
        return jeton

    def mot(self, *mots: str) -> bool:
        """Consomme la SÉQUENCE de mots si elle est là en entier ; sinon ne consomme rien."""
        for decalage, attendu in enumerate(mots):
            jeton = self.voir(decalage)
            if jeton is None or not jeton.est(attendu):
                return False
        self.indice += len(mots)
        return True

    def op(self, *ops: str) -> bool:
        jeton = self.voir()
        if jeton is not None and jeton.est_op(*ops):
            self.indice += 1
            return True
        return False

    def nom(self) -> str | None:
        jeton = self.voir()
        if jeton is None or jeton.nom is None:
            return None
        self.indice += 1
        return jeton.nom

    def nom_qualifie(self) -> tuple[str | None, str | None]:
        """`schema.objet` ou `objet` — rend (schéma, objet)."""
        parties = [self.nom()]
        while self.voir() is not None and self.voir().est_op(".") and self.voir(1) is not None:
            self.indice += 1
            parties.append(self.nom())
        if parties[-1] is None:
            return None, None
        return (parties[-2] if len(parties) > 1 else None), parties[-1]

    def bloc(self) -> list[Jeton] | None:
        """Le contenu de la parenthèse ouvrante courante, parenthèses exclues — consommé."""
        if not (self.voir() is not None and self.voir().est_op("(")):
            return None
        profondeur, debut = 0, self.indice
        while not self.fini():
            jeton = self.suivant()
            if jeton.est_op("("):
                profondeur += 1
            elif jeton.est_op(")"):
                profondeur -= 1
                if profondeur == 0:
                    return self.jetons[debut + 1 : self.indice - 1]
        return self.jetons[debut + 1 :]

    def jusqu_a(self, arret) -> list[Jeton]:
        """Jetons consommés au niveau 0 jusqu au premier qui vérifie `arret` (non consommé)."""
        pris: list[Jeton] = []
        profondeur = 0
        while not self.fini():
            jeton = self.voir()
            if profondeur == 0 and arret(jeton):
                break
            if jeton.est_op("(", "["):
                profondeur += 1
            elif jeton.est_op(")", "]"):
                profondeur -= 1
            pris.append(jeton)
            self.indice += 1
        return pris

    def reste(self) -> list[Jeton]:
        pris = self.jetons[self.indice :]
        self.indice = len(self.jetons)
        return pris


# --- Modèle ---------------------------------------------------------------------------------------


@dataclass
class Colonne:
    nom: str
    type_sql: str
    famille: str
    longueur_max: int | None = None
    precision: int | None = None
    echelle: int | None = None
    bornes_type: tuple[int, int] | None = None
    tableau: bool = False
    non_nul: bool = False
    defaut: str | None = None
    # « serie » (SERIAL), « identite_toujours », « identite_defaut », « sequence » (nextval)
    auto: str | None = None
    generee: bool = False
    enum: str | None = None
    domaine: str | None = None


@dataclass
class Unicite:
    nom: str
    colonnes: tuple[str, ...]
    primaire: bool = False
    nulls_distincts: bool = True
    index: bool = False
    # Index unique sur EXPRESSION (`lower(email)`) : l unicité est approchée par les colonnes
    # citées, comparées sans casse — déclaré, pas deviné.
    expression: bool = False


@dataclass
class CleEtrangere:
    nom: str
    colonnes: tuple[str, ...]
    table_cible: str
    colonnes_cibles: tuple[str, ...] | None = None
    differable: bool = False


@dataclass
class Effet:
    """Ce qu une vérification interprétée impose à une colonne.

    `genre` : « permis » (valeurs énumérées), « exclus », « borne » (comparaison à une valeur),
    « longueur », « non_nul », « non_vide », « relation » (comparaison à une autre colonne).
    """

    genre: str
    colonne: str
    operateur: str | None = None
    valeurs: tuple = ()
    autre: str | None = None


@dataclass
class Verification:
    nom: str
    expression: str
    jetons: list[Jeton]
    effets: list[Effet] = field(default_factory=list)
    # « oui », « partielle » (une partie des conjoints seulement), « non »
    interpretee: str = "non"
    colonnes: tuple[str, ...] = ()


@dataclass
class Table:
    nom: str
    schema: str | None
    migration: str
    colonnes: dict[str, Colonne] = field(default_factory=dict)
    unicites: list[Unicite] = field(default_factory=list)
    cles_etrangeres: list[CleEtrangere] = field(default_factory=list)
    verifications: list[Verification] = field(default_factory=list)

    @property
    def nom_sql(self) -> str:
        """Nom CITÉ, qualifié si la migration le qualifiait : la casse lue est celle du moteur."""
        nom = citer(self.nom)
        return f"{citer(self.schema)}.{nom}" if self.schema else nom


@dataclass
class TypeDomaine:
    nom: str
    base: Colonne
    non_nul: bool = False
    verifications: list[tuple[str | None, list[Jeton]]] = field(default_factory=list)


@dataclass
class Schema:
    tables: dict[str, Table] = field(default_factory=dict)
    enums: dict[str, list[str]] = field(default_factory=dict)
    domaines: dict[str, TypeDomaine] = field(default_factory=dict)
    migrations: list[str] = field(default_factory=list)
    non_modelisees: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def citer(nom: str) -> str:
    """Identifiant toujours cité : un nom réservé (`user`, `order`) ne casse rien."""
    return '"' + nom.replace('"', '""') + '"'


# --- Types --------------------------------------------------------------------------------------

_BORNES_16 = (-32768, 32767)
_BORNES_32 = (-2147483648, 2147483647)
_BORNES_64 = (-9223372036854775808, 9223372036854775807)

_ENTIERS = {
    "smallint": _BORNES_16, "int2": _BORNES_16, "smallserial": _BORNES_16, "serial2": _BORNES_16,
    "integer": _BORNES_32, "int": _BORNES_32, "int4": _BORNES_32, "serial": _BORNES_32,
    "serial4": _BORNES_32, "bigint": _BORNES_64, "int8": _BORNES_64, "bigserial": _BORNES_64,
    "serial8": _BORNES_64,
}
_SERIES = frozenset({"smallserial", "serial2", "serial", "serial4", "bigserial", "serial8"})
_FAMILLES = {
    "numeric": "decimal", "decimal": "decimal",
    "real": "flottant", "float4": "flottant", "float8": "flottant", "float": "flottant",
    "double": "flottant", "money": "monnaie", "boolean": "booleen", "bool": "booleen",
    "text": "texte", "varchar": "texte", "character": "texte", "char": "texte",
    "bpchar": "texte", "citext": "texte", "name": "texte",
    "date": "date", "timestamp": "horodatage", "timestamptz": "horodatage_tz",
    "time": "heure", "timetz": "heure_tz", "interval": "duree", "uuid": "uuid",
    "json": "json", "jsonb": "json", "bytea": "binaire", "inet": "reseau", "cidr": "cidr",
    "macaddr": "mac", "macaddr8": "mac",
}


def _typer(nom: str, jetons: list[Jeton], schema: Schema) -> Colonne:
    """Une colonne de type lu dans `jetons` (`varchar(40)`, `numeric(10,2)`, `statut_t`…)."""
    texte = restituer(jetons)
    tableau = any(j.est_op("[") for j in jetons) or any(j.est("array") for j in jetons)
    utiles: list[Jeton] = []
    for jeton in jetons:
        if jeton.est_op("[") or jeton.est("array"):
            break
        utiles.append(jeton)
    parametres: list[int] = []
    curseur = _Curseur(utiles)
    mots: list[str] = []
    qualifie = False
    while not curseur.fini():
        jeton = curseur.voir()
        if jeton.est_op("("):
            interieur = curseur.bloc() or []
            if not parametres:
                parametres = [int(j.valeur) for j in interieur if j.genre == "nombre"
                              and j.valeur.isdigit()]
            continue
        if jeton.est_op("."):
            qualifie = True
            mots = []
        elif jeton.nom is not None:
            mots.append(jeton.nom)
        curseur.indice += 1
    premier = mots[0] if mots else ""
    colonne = Colonne(nom=nom, type_sql=texte.lower() if not qualifie else texte,
                      famille="inconnu", tableau=tableau)
    if tableau:
        colonne.famille = "tableau"
        # Le type des éléments sert au rendu du littéral de tableau.
        colonne.type_sql = premier
        colonne.bornes_type = _ENTIERS.get(premier)
        return colonne
    if premier in schema.enums:
        colonne.famille, colonne.enum = "enum", premier
        return colonne
    if premier in schema.domaines:
        domaine = schema.domaines[premier]
        base = domaine.base
        colonne.famille = base.famille
        colonne.type_sql = base.type_sql
        colonne.longueur_max, colonne.precision = base.longueur_max, base.precision
        colonne.echelle, colonne.bornes_type = base.echelle, base.bornes_type
        colonne.enum, colonne.domaine = base.enum, premier
        colonne.non_nul = domaine.non_nul
        return colonne
    avec_fuseau = "with" in mots and "zone" in mots and "without" not in mots
    if premier in _ENTIERS:
        colonne.famille, colonne.bornes_type = "entier", _ENTIERS[premier]
        if premier in _SERIES:
            colonne.auto, colonne.non_nul = "serie", True
        return colonne
    famille = _FAMILLES.get(premier)
    if famille is None:
        return colonne
    colonne.famille = famille
    if famille == "decimal" and parametres:
        colonne.precision = parametres[0]
        colonne.echelle = parametres[1] if len(parametres) > 1 else 0
    elif famille == "texte":
        variable = "varying" in mots or premier == "varchar"
        if parametres:
            colonne.longueur_max = parametres[0]
        elif premier in ("character", "char") and not variable:
            colonne.longueur_max = 1  # CHAR sans longueur vaut CHAR(1) pour PostgreSQL
    elif famille == "horodatage" and avec_fuseau:
        colonne.famille = "horodatage_tz"
    elif famille == "heure" and avec_fuseau:
        colonne.famille = "heure_tz"
    return colonne


# --- Instructions -------------------------------------------------------------------------------

_DEBUTS_CONTRAINTE = ("constraint", "check", "unique", "primary", "foreign", "exclude")
_ARRETS_TYPE = frozenset(
    {"constraint", "not", "null", "check", "default", "generated", "unique", "primary",
     "references", "collate", "deferrable", "initially"}
)


def _compter(schema: Schema, nature: str) -> None:
    schema.non_modelisees[nature] = schema.non_modelisees.get(nature, 0) + 1


def _nature(jetons: list[Jeton]) -> str:
    """Nature d une instruction non modélisée : `CREATE FUNCTION`, `INSERT`, `COMMENT`…"""
    mots = [j.valeur.upper() for j in jetons[:6] if j.genre == "mot"]
    if not mots:
        return "fragment non reconnu"
    if mots[0] in ("CREATE", "ALTER", "DROP"):
        suite = [m for m in mots[1:] if m not in ("OR", "REPLACE", "UNIQUE", "TEMP", "TEMPORARY",
                                                  "UNLOGGED", "GLOBAL", "LOCAL", "IF", "NOT")]
        return f"{mots[0]} {suite[0]}" if suite else mots[0]
    return mots[0]


def _colonnes_citees(jetons: list[Jeton], noms: set[str]) -> tuple[str, ...]:
    vues: list[str] = []
    for jeton in jetons:
        if jeton.nom is not None and jeton.nom in noms and jeton.nom not in vues:
            vues.append(jeton.nom)
    return tuple(vues)


def _nom_verification(table: Table, colonnes: tuple[str, ...]) -> str:
    # Comme PostgreSQL : `<table>_<colonne>_check` si l expression cite UNE colonne.
    return f"{table.nom}_{colonnes[0]}_check" if len(colonnes) == 1 else f"{table.nom}_check"


def _ajouter_verification(
    table: Table, nom: str | None, jetons: list[Jeton], en_cours: str | None = None
) -> None:
    noms = set(table.colonnes) | ({en_cours} if en_cours else set())
    citees = _colonnes_citees(jetons, noms)
    table.verifications.append(
        Verification(nom or _nom_verification(table, citees), restituer(jetons), jetons,
                     colonnes=citees)
    )


def _suite_cle(curseur: _Curseur) -> bool:
    """Consomme MATCH, ON DELETE/UPDATE, DEFERRABLE… après REFERENCES ; rend « différable »."""
    differable = False
    while not curseur.fini():
        if curseur.mot("match"):
            curseur.nom()
        elif curseur.mot("on", "delete") or curseur.mot("on", "update"):
            if curseur.mot("set", "null") or curseur.mot("set", "default"):
                curseur.bloc()
            elif not (curseur.mot("cascade") or curseur.mot("restrict")
                      or curseur.mot("no", "action")):
                curseur.suivant()
        elif curseur.mot("deferrable"):
            differable = True
        elif curseur.mot("not", "deferrable"):
            differable = False
        elif (curseur.mot("not", "valid") or curseur.mot("initially", "deferred")
              or curseur.mot("initially", "immediate")):
            continue
        else:
            break
    return differable


def _noms_de(jetons: list[Jeton] | None) -> tuple[str, ...]:
    return tuple(j.nom for j in (jetons or []) if j.nom is not None)


def _nulls_distincts(curseur: _Curseur) -> bool:
    if curseur.mot("nulls", "not", "distinct"):
        return False
    curseur.mot("nulls", "distinct")
    return True


def _colonne(curseur: _Curseur, table: Table, schema: Schema, si_absente: bool = False) -> None:
    nom = curseur.nom()
    if nom is None:
        schema.notes.append(f"{table.nom} : déclaration de colonne illisible, ignorée")
        return
    type_jetons = curseur.jusqu_a(lambda j: j.genre == "mot" and j.valeur in _ARRETS_TYPE)
    colonne = _typer(nom, type_jetons, schema)
    if nom in table.colonnes:
        if not si_absente:
            schema.notes.append(f"{table.nom}.{nom} : colonne déclarée deux fois, la première "
                                "est gardée")
        return
    table.colonnes[nom] = colonne
    if colonne.domaine:
        # Les vérifications du domaine valent pour la colonne : VALUE y désigne la colonne.
        for nom_verif, jetons in schema.domaines[colonne.domaine].verifications:
            substitues = [Jeton("ident", nom, citer(nom)) if j.est("value") else j
                          for j in jetons]
            _ajouter_verification(table, nom_verif or f"{colonne.domaine}_check", substitues)
    nom_contrainte: str | None = None
    while not curseur.fini():
        if curseur.mot("constraint"):
            nom_contrainte = curseur.nom()
            continue
        if curseur.mot("not", "null"):
            colonne.non_nul = True
        elif curseur.mot("null"):
            pass
        elif curseur.mot("check"):
            _ajouter_verification(table, nom_contrainte, curseur.bloc() or [], en_cours=nom)
            curseur.mot("no", "inherit")
        elif curseur.mot("default"):
            expression = curseur.jusqu_a(lambda j: j.genre == "mot" and j.valeur in _ARRETS_TYPE)
            colonne.defaut = restituer(expression) or None
            if colonne.defaut and "nextval" in colonne.defaut.lower() and not colonne.auto:
                colonne.auto = "sequence"
        elif curseur.mot("generated"):
            mode = "toujours" if curseur.mot("always") else "defaut"
            curseur.mot("by", "default")
            curseur.mot("as")
            if curseur.mot("identity"):
                colonne.auto, colonne.non_nul = f"identite_{mode}", True
                curseur.bloc()
            else:
                curseur.bloc()
                if not curseur.mot("stored"):
                    curseur.mot("virtual")
                colonne.generee = True
        elif curseur.mot("unique"):
            distincts = _nulls_distincts(curseur)
            table.unicites.append(Unicite(nom_contrainte or f"{table.nom}_{nom}_key", (nom,),
                                          nulls_distincts=distincts))
            if curseur.mot("using", "index", "tablespace"):
                curseur.nom()
        elif curseur.mot("primary", "key"):
            colonne.non_nul = True
            table.unicites.append(Unicite(nom_contrainte or f"{table.nom}_pkey", (nom,),
                                          primaire=True))
            if curseur.mot("using", "index", "tablespace"):
                curseur.nom()
        elif curseur.mot("references"):
            _schema_cible, cible = curseur.nom_qualifie()
            cibles = _noms_de(curseur.bloc()) or None
            differable = _suite_cle(curseur)
            if cible:
                table.cles_etrangeres.append(CleEtrangere(
                    nom_contrainte or f"{table.nom}_{nom}_fkey", (nom,), cible, cibles,
                    differable))
        elif curseur.mot("collate"):
            curseur.nom_qualifie()
        elif not (curseur.mot("deferrable") or curseur.mot("not", "deferrable")
                  or curseur.mot("initially", "deferred")
                  or curseur.mot("initially", "immediate")):
            reste = restituer(curseur.reste())
            schema.notes.append(f"{table.nom}.{nom} : suite de déclaration non lue ({reste})")
            break
        nom_contrainte = None


def _contrainte_de_table(curseur: _Curseur, table: Table, schema: Schema) -> None:
    nom: str | None = None
    if curseur.mot("constraint"):
        nom = curseur.nom()
    if curseur.mot("check"):
        _ajouter_verification(table, nom, curseur.bloc() or [])
        return
    if curseur.mot("unique") or curseur.mot("primary", "key"):
        primaire = curseur.jetons[curseur.indice - 1].est("key")
        distincts = _nulls_distincts(curseur)
        colonnes = _noms_de(curseur.bloc())
        if not colonnes and curseur.mot("using", "index"):
            index = curseur.nom()
            source = next((u for u in table.unicites if u.index and u.nom == index), None)
            colonnes = source.colonnes if source else ()
        if not colonnes:
            schema.notes.append(f"{table.nom} : contrainte d unicité sans colonne lisible")
            return
        suffixe = "pkey" if primaire else f"{'_'.join(colonnes)}_key"
        table.unicites.append(Unicite(nom or f"{table.nom}_{suffixe}", colonnes,
                                      primaire=primaire, nulls_distincts=distincts))
        return
    if curseur.mot("foreign", "key"):
        colonnes = _noms_de(curseur.bloc())
        if not curseur.mot("references"):
            schema.notes.append(f"{table.nom} : FOREIGN KEY sans REFERENCES lisible")
            return
        _schema_cible, cible = curseur.nom_qualifie()
        cibles = _noms_de(curseur.bloc()) or None
        differable = _suite_cle(curseur)
        if cible and colonnes:
            table.cles_etrangeres.append(CleEtrangere(
                nom or f"{table.nom}_{'_'.join(colonnes)}_fkey", colonnes, cible, cibles,
                differable))
        return
    if curseur.mot("exclude"):
        _compter(schema, "contrainte EXCLUDE")
        schema.notes.append(f"{table.nom} : contrainte d exclusion (EXCLUDE) non modélisée — "
                            "seul le chargement réel la juge")
        return
    schema.notes.append(f"{table.nom} : contrainte de table non lue ({restituer(curseur.reste())})")


def _element_de_table(jetons: list[Jeton], table: Table, schema: Schema) -> None:
    if jetons[0].est("like"):
        _compter(schema, "CREATE TABLE ... (LIKE ...)")
        return
    if jetons[0].est(*_DEBUTS_CONTRAINTE):
        _contrainte_de_table(_Curseur(jetons), table, schema)
    else:
        _colonne(_Curseur(jetons), table, schema)


def _creer_table(curseur: _Curseur, schema: Schema, migration: str) -> bool:
    if not curseur.mot("global"):
        curseur.mot("local")
    temporaire = curseur.mot("temporary") or curseur.mot("temp")
    curseur.mot("unlogged")
    if not curseur.mot("table"):
        return False
    si_absente = curseur.mot("if", "not", "exists")
    nom_schema, nom = curseur.nom_qualifie()
    if nom is None:
        schema.notes.append(f"{migration} : CREATE TABLE sans nom lisible")
        return True
    if temporaire:
        _compter(schema, "CREATE TEMPORARY TABLE")
        return True
    corps = curseur.bloc()
    if corps is None:
        _compter(schema, "CREATE TABLE ... AS / OF / PARTITION OF")
        schema.notes.append(f"{nom} : table créée sans liste de colonnes (AS, OF, PARTITION OF) "
                            "— non lue")
        return True
    if nom in schema.tables:
        if not si_absente:
            schema.notes.append(f"{nom} : table créée deux fois, la première est gardée")
        return True
    table = Table(nom=nom, schema=nom_schema, migration=migration)
    for element in scinder(corps):
        _element_de_table(element, table, schema)
    reste = curseur.reste()
    if any(j.est("inherits") for j in reste):
        schema.notes.append(f"{nom} : INHERITS — les colonnes héritées ne sont pas lues")
    if any(j.est("partition") for j in reste):
        schema.notes.append(f"{nom} : table partitionnée — ses partitions ne sont pas lues")
    schema.tables[nom] = table
    return True


def _retirer_contrainte(table: Table, nom: str | None, schema: Schema) -> None:
    avant = (len(table.unicites), len(table.cles_etrangeres), len(table.verifications))
    table.unicites = [u for u in table.unicites if u.index or u.nom != nom]
    table.cles_etrangeres = [c for c in table.cles_etrangeres if c.nom != nom]
    table.verifications = [v for v in table.verifications if v.nom != nom]
    apres = (len(table.unicites), len(table.cles_etrangeres), len(table.verifications))
    if avant == apres:
        schema.notes.append(f"{table.nom} : DROP CONSTRAINT {nom} — contrainte introuvable au "
                            "schéma lu (nom implicite non reconstitué ?), rien n est retiré")


def _retirer_colonne(schema: Schema, table: Table, nom: str | None) -> None:
    if nom not in table.colonnes:
        schema.notes.append(f"{table.nom} : DROP COLUMN {nom} — colonne inconnue du schéma lu")
        return
    del table.colonnes[nom]
    table.unicites = [u for u in table.unicites if nom not in u.colonnes]
    table.cles_etrangeres = [c for c in table.cles_etrangeres if nom not in c.colonnes]
    table.verifications = [v for v in table.verifications if nom not in v.colonnes]
    for autre in schema.tables.values():
        autre.cles_etrangeres = [
            c for c in autre.cles_etrangeres
            if not (c.table_cible == table.nom and nom in (c.colonnes_cibles or ()))
        ]


def _renommer_colonne(
    schema: Schema, table: Table, ancien: str | None, nouveau: str | None
) -> None:
    if ancien not in table.colonnes or not nouveau:
        schema.notes.append(f"{table.nom} : RENAME COLUMN {ancien} — colonne inconnue")
        return
    table.colonnes = {(nouveau if cle == ancien else cle): col
                      for cle, col in table.colonnes.items()}
    table.colonnes[nouveau].nom = nouveau

    def renommer(noms: tuple[str, ...] | None) -> tuple[str, ...] | None:
        return None if noms is None else tuple(nouveau if n == ancien else n for n in noms)

    for unicite in table.unicites:
        unicite.colonnes = renommer(unicite.colonnes)
    for cle in table.cles_etrangeres:
        cle.colonnes = renommer(cle.colonnes)
    for autre in schema.tables.values():
        for cle in autre.cles_etrangeres:
            if cle.table_cible == table.nom:
                cle.colonnes_cibles = renommer(cle.colonnes_cibles)
    for verification in table.verifications:
        verification.jetons = [Jeton("ident", nouveau, citer(nouveau)) if j.nom == ancien
                               else j for j in verification.jetons]
        verification.expression = restituer(verification.jetons)
        verification.colonnes = renommer(verification.colonnes)


def _renommer_table(schema: Schema, ancien: str, nouveau: str | None) -> None:
    if not nouveau:
        return
    schema.tables = {(nouveau if cle == ancien else cle): t for cle, t in schema.tables.items()}
    schema.tables[nouveau].nom = nouveau
    for autre in schema.tables.values():
        for cle in autre.cles_etrangeres:
            if cle.table_cible == ancien:
                cle.table_cible = nouveau


def _action(curseur: _Curseur, table: Table, schema: Schema) -> None:
    """Une action d `ALTER TABLE` — celles qui changent ce qu une ligne valide exige."""
    if curseur.mot("add"):
        suivant = curseur.voir()
        if suivant is not None and suivant.est(*_DEBUTS_CONTRAINTE):
            _contrainte_de_table(curseur, table, schema)
            return
        curseur.mot("column")
        si_absente = curseur.mot("if", "not", "exists")
        _colonne(curseur, table, schema, si_absente)
        return
    if curseur.mot("drop", "constraint"):
        curseur.mot("if", "exists")
        _retirer_contrainte(table, curseur.nom(), schema)
        return
    if curseur.mot("drop"):
        curseur.mot("column")
        curseur.mot("if", "exists")
        _retirer_colonne(schema, table, curseur.nom())
        return
    if curseur.mot("alter", "constraint"):
        return
    if curseur.mot("alter"):
        curseur.mot("column")
        nom = curseur.nom()
        colonne = table.colonnes.get(nom or "")
        if colonne is None:
            schema.notes.append(f"{table.nom} : ALTER COLUMN {nom} — colonne inconnue")
            return
        if curseur.mot("set", "data", "type") or curseur.mot("type"):
            jetons = curseur.jusqu_a(lambda j: j.est("collate", "using"))
            neuf = _typer(colonne.nom, jetons, schema)
            for attribut in ("type_sql", "famille", "longueur_max", "precision", "echelle",
                             "bornes_type", "tableau", "enum", "domaine"):
                setattr(colonne, attribut, getattr(neuf, attribut))
        elif curseur.mot("set", "not", "null"):
            colonne.non_nul = True
        elif curseur.mot("drop", "not", "null"):
            colonne.non_nul = False
        elif curseur.mot("set", "default"):
            colonne.defaut = restituer(curseur.reste()) or None
            if colonne.defaut and "nextval" in colonne.defaut.lower() and not colonne.auto:
                colonne.auto = "sequence"
        elif curseur.mot("drop", "default"):
            colonne.defaut = None
            if colonne.auto == "sequence":
                colonne.auto = None
        elif curseur.mot("add", "generated"):
            mode = "toujours" if curseur.mot("always") else "defaut"
            colonne.auto, colonne.non_nul = f"identite_{mode}", True
        elif curseur.mot("set", "generated"):
            colonne.auto = "identite_toujours" if curseur.mot("always") else "identite_defaut"
        elif curseur.mot("drop", "identity"):
            colonne.auto = None
        elif curseur.mot("drop", "expression"):
            colonne.generee = False
        return
    # OWNER, ENABLE/DISABLE TRIGGER, SET (...), VALIDATE CONSTRAINT… : sans effet sur une ligne
    # valide. Une action inconnue se COMPTE, elle ne se tait pas.
    jeton = curseur.voir()
    if jeton is not None and not jeton.est("owner", "enable", "disable", "set", "reset",
                                           "validate", "cluster", "replica", "inherit", "no",
                                           "force", "attach", "detach", "of", "not"):
        _compter(schema, f"ALTER TABLE ... {jeton.valeur.upper()}")


def _modifier_table(curseur: _Curseur, schema: Schema) -> None:
    curseur.mot("if", "exists")
    curseur.mot("only")
    _schema, nom = curseur.nom_qualifie()
    curseur.op("*")
    table = schema.tables.get(nom or "")
    if table is None:
        schema.notes.append(f"ALTER TABLE {nom} : table inconnue du schéma lu, instruction "
                            "ignorée")
        return
    if curseur.mot("rename"):
        if curseur.mot("to"):
            _renommer_table(schema, table.nom, curseur.nom())
        elif curseur.mot("constraint"):
            ancien = curseur.nom()
            curseur.mot("to")
            nouveau = curseur.nom() or ancien
            for liste in (table.unicites, table.cles_etrangeres, table.verifications):
                for element in liste:
                    if element.nom == ancien:
                        element.nom = nouveau
        else:
            curseur.mot("column")
            ancien = curseur.nom()
            curseur.mot("to")
            _renommer_colonne(schema, table, ancien, curseur.nom())
        return
    if curseur.mot("set", "schema"):
        table.schema = curseur.nom()
        return
    for action in scinder(curseur.reste()):
        _action(_Curseur(action), table, schema)


def _creer_index(curseur: _Curseur, schema: Schema, unique: bool) -> None:
    curseur.mot("concurrently")
    curseur.mot("if", "not", "exists")
    nom = None if (curseur.voir() is not None and curseur.voir().est("on")) else curseur.nom()
    if not curseur.mot("on"):
        schema.notes.append(f"CREATE INDEX {nom} : table visée illisible")
        return
    curseur.mot("only")
    _schema, nom_table = curseur.nom_qualifie()
    if curseur.mot("using"):
        curseur.nom()
    elements = curseur.bloc() or []
    reste = curseur.reste()
    if not unique:
        return
    table = schema.tables.get(nom_table or "")
    if table is None:
        schema.notes.append(f"CREATE UNIQUE INDEX {nom} : table {nom_table} inconnue du schéma lu")
        return
    colonnes: list[str] = []
    expression = False
    for element in scinder(elements):
        premier = element[0]
        simple = premier.nom is not None and (
            len(element) == 1 or not element[1].est_op("(", ".", "::", "||", "+", "-", "*", "/")
        )
        if simple:
            colonnes.append(premier.nom)
            continue
        expression = True
        colonnes.extend(n for n in _colonnes_citees(element, set(table.colonnes))
                        if n not in colonnes)
    distincts = not any(
        reste[i].est("nulls") and reste[i + 1].est("not")
        for i in range(len(reste) - 1)
    )
    if any(j.est("where") for j in reste):
        schema.notes.append(f"{table.nom} : index unique PARTIEL {nom} — traité comme une "
                            "unicité totale, plus stricte que celle du moteur")
    if colonnes:
        table.unicites.append(Unicite(nom or f"{table.nom}_{'_'.join(colonnes)}_idx",
                                      tuple(colonnes), nulls_distincts=distincts, index=True,
                                      expression=expression))


def _retirer_index(curseur: _Curseur, schema: Schema) -> None:
    curseur.mot("concurrently")
    curseur.mot("if", "exists")
    for morceau in scinder(curseur.reste()):
        noms = [j.nom for j in morceau if j.nom is not None and not j.est("cascade", "restrict")]
        if not noms:
            continue
        for table in schema.tables.values():
            table.unicites = [u for u in table.unicites if not (u.index and u.nom == noms[-1])]


def _creer_type(curseur: _Curseur, schema: Schema) -> None:
    _schema, nom = curseur.nom_qualifie()
    if nom and curseur.mot("as", "enum"):
        schema.enums[nom] = [j.valeur for j in (curseur.bloc() or []) if j.genre == "chaine"]
        return
    _compter(schema, "CREATE TYPE (composite, intervalle…)")


def _modifier_type(curseur: _Curseur, schema: Schema) -> None:
    _schema, nom = curseur.nom_qualifie()
    valeurs = schema.enums.get(nom or "")
    if valeurs is None:
        _compter(schema, "ALTER TYPE")
        return
    if curseur.mot("add", "value"):
        curseur.mot("if", "not", "exists")
        nouvelle = curseur.suivant()
        if nouvelle is None or nouvelle.genre != "chaine" or nouvelle.valeur in valeurs:
            return
        position = len(valeurs)
        if curseur.mot("before") or curseur.mot("after"):
            apres = curseur.jetons[curseur.indice - 1].est("after")
            repere = curseur.suivant()
            if repere is not None and repere.valeur in valeurs:
                position = valeurs.index(repere.valeur) + (1 if apres else 0)
        valeurs.insert(position, nouvelle.valeur)
    elif curseur.mot("rename", "value"):
        ancienne = curseur.suivant()
        curseur.mot("to")
        nouvelle = curseur.suivant()
        if ancienne is not None and nouvelle is not None and ancienne.valeur in valeurs:
            valeurs[valeurs.index(ancienne.valeur)] = nouvelle.valeur
    elif curseur.mot("rename", "to"):
        neuf = curseur.nom()
        if neuf:
            schema.enums[neuf] = schema.enums.pop(nom)
            for table in schema.tables.values():
                for colonne in table.colonnes.values():
                    if colonne.enum == nom:
                        colonne.enum = neuf


def _creer_domaine(curseur: _Curseur, schema: Schema) -> None:
    _schema, nom = curseur.nom_qualifie()
    if not nom:
        return
    curseur.mot("as")
    jetons = curseur.jusqu_a(lambda j: j.est("collate", "default", "constraint", "not", "null",
                                             "check"))
    domaine = TypeDomaine(nom=nom, base=_typer("value", jetons, schema))
    nom_contrainte: str | None = None
    while not curseur.fini():
        if curseur.mot("constraint"):
            nom_contrainte = curseur.nom()
            continue
        if curseur.mot("not", "null"):
            domaine.non_nul = True
        elif curseur.mot("check"):
            domaine.verifications.append((nom_contrainte, curseur.bloc() or []))
        elif curseur.mot("default"):
            curseur.jusqu_a(lambda j: j.est("constraint", "not", "null", "check"))
        elif curseur.mot("collate"):
            curseur.nom_qualifie()
        elif not curseur.mot("null"):
            curseur.suivant()
        nom_contrainte = None
    schema.domaines[nom] = domaine


def _retirer_tables(curseur: _Curseur, schema: Schema) -> None:
    curseur.mot("if", "exists")
    for morceau in scinder(curseur.reste()):
        noms = [j.nom for j in morceau if j.nom is not None and not j.est("cascade", "restrict")]
        if not noms:
            continue
        nom = noms[-1]
        schema.tables.pop(nom, None)
        for autre in schema.tables.values():
            autre.cles_etrangeres = [c for c in autre.cles_etrangeres if c.table_cible != nom]


def _appliquer(instruction: str, schema: Schema, migration: str) -> None:
    jetons = lexer(instruction)
    if not jetons:
        return
    curseur = _Curseur(jetons)
    if curseur.mot("create"):
        curseur.mot("or", "replace")
        position = curseur.indice
        if _creer_table(curseur, schema, migration):
            return
        curseur.indice = position
        unique = curseur.mot("unique")
        if curseur.mot("index"):
            _creer_index(curseur, schema, unique)
            return
        if curseur.mot("type"):
            _creer_type(curseur, schema)
            return
        if curseur.mot("domain"):
            _creer_domaine(curseur, schema)
            return
    elif curseur.mot("alter", "table"):
        _modifier_table(curseur, schema)
        return
    elif curseur.mot("alter", "type"):
        _modifier_type(curseur, schema)
        return
    elif curseur.mot("drop", "table"):
        _retirer_tables(curseur, schema)
        return
    elif curseur.mot("drop", "index"):
        _retirer_index(curseur, schema)
        return
    elif curseur.mot("drop", "type"):
        curseur.mot("if", "exists")
        for morceau in scinder(curseur.reste()):
            noms = [j.nom for j in morceau
                    if j.nom is not None and not j.est("cascade", "restrict")]
            if noms:
                schema.enums.pop(noms[-1], None)
        return
    _compter(schema, _nature(jetons))


# --- Interprétation des vérifications -----------------------------------------------------------


class _NonInterpretable(Exception):
    """Forme d expression que la fabrique ne sait pas traduire en valeurs."""


_COMPARATEURS = ("=", "<>", "!=", "<", "<=", ">", ">=")
_MOTS_DE_TYPE = frozenset({"varying", "precision", "with", "without", "time", "zone"})
_FONCTIONS_LONGUEUR = frozenset({"length", "char_length", "character_length"})
_FONCTIONS_BLANCS = frozenset({"trim", "btrim", "ltrim", "rtrim"})


class _Expression:
    """Analyse descendante d une expression de vérification — sans évaluer quoi que ce soit."""

    def __init__(self, jetons: list[Jeton]) -> None:
        self.c = _Curseur(jetons)

    def analyser(self) -> tuple:
        arbre = self.ou()
        if not self.c.fini():
            raise _NonInterpretable(restituer(self.c.reste()))
        return arbre

    def ou(self) -> tuple:
        gauche = self.et()
        while self.c.mot("or"):
            gauche = ("ou", gauche, self.et())
        return gauche

    def et(self) -> tuple:
        gauche = self.non()
        while self.c.mot("and"):
            gauche = ("et", gauche, self.non())
        return gauche

    def non(self) -> tuple:
        if self.c.mot("not"):
            return ("non", self.non())
        return self.comparaison()

    def comparaison(self) -> tuple:
        gauche = self.additif()
        if self.c.mot("is"):
            nie = self.c.mot("not")
            if self.c.mot("null"):
                return ("estnul", gauche, nie)
            raise _NonInterpretable("IS ...")
        if self.c.mot("isnull"):
            return ("estnul", gauche, False)
        if self.c.mot("notnull"):
            return ("estnul", gauche, True)
        nie = False
        suivant = self.c.voir(1)
        if self.c.voir() is not None and self.c.voir().est("not") and suivant is not None and (
            suivant.est("in", "between", "like", "ilike", "similar")
        ):
            self.c.indice += 1
            nie = True
        if self.c.mot("in"):
            interieur = self.c.bloc()
            if interieur is None:
                raise _NonInterpretable("IN sans liste")
            return ("dans", gauche, [_Expression(m).analyser() for m in scinder(interieur)], nie)
        if self.c.mot("between"):
            self.c.mot("symmetric")
            bas = self.additif()
            if not self.c.mot("and"):
                raise _NonInterpretable("BETWEEN sans AND")
            return ("entre", gauche, bas, self.additif(), nie)
        if self.c.mot("like") or self.c.mot("ilike") or self.c.mot("similar", "to"):
            raise _NonInterpretable("motif LIKE / SIMILAR")
        jeton = self.c.voir()
        if jeton is not None and jeton.est_op(*_COMPARATEURS, "~", "~*", "!~", "!~*"):
            self.c.indice += 1
            if self.c.mot("any") or self.c.mot("some") or self.c.mot("all"):
                quantite = self.c.jetons[self.c.indice - 1].valeur
                interieur = self.c.bloc()
                if interieur is None:
                    raise _NonInterpretable("ANY / ALL sans parenthèse")
                return ("quantifie", jeton.valeur, gauche, quantite,
                        _Expression(interieur).analyser())
            return ("cmp", jeton.valeur, gauche, self.additif())
        return gauche

    def additif(self) -> tuple:
        gauche = self.multiplicatif()
        while self.c.voir() is not None and self.c.voir().est_op("+", "-", "||"):
            operateur = self.c.suivant().valeur
            gauche = ("arith", operateur, gauche, self.multiplicatif())
        return gauche

    def multiplicatif(self) -> tuple:
        gauche = self.unaire()
        while self.c.voir() is not None and self.c.voir().est_op("*", "/", "%"):
            operateur = self.c.suivant().valeur
            gauche = ("arith", operateur, gauche, self.unaire())
        return gauche

    def unaire(self) -> tuple:
        if self.c.op("-"):
            return ("neg", self.unaire())
        if self.c.op("+"):
            return self.unaire()
        return self.postfixe()

    def postfixe(self) -> tuple:
        arbre = self.primaire()
        while True:
            if self.c.op("::"):
                arbre = ("cast", arbre, self.type_de_cast())
                continue
            if self.c.voir() is not None and self.c.voir().est_op("["):
                raise _NonInterpretable("indice de tableau")
            return arbre

    def type_de_cast(self) -> str:
        _schema, nom = self.c.nom_qualifie()
        if nom is None:
            raise _NonInterpretable("cast illisible")
        mots = [nom]
        while self.c.voir() is not None and self.c.voir().est(*_MOTS_DE_TYPE):
            mots.append(self.c.suivant().valeur)
        self.c.bloc()
        while self.c.op("["):
            self.c.jusqu_a(lambda j: j.est_op("]"))
            self.c.op("]")
        return " ".join(mots)

    def primaire(self) -> tuple:
        jeton = self.c.suivant()
        if jeton is None:
            raise _NonInterpretable("expression tronquée")
        if jeton.genre == "nombre":
            return ("lit", _nombre(jeton.valeur), "nombre")
        if jeton.genre == "chaine":
            return ("lit", jeton.valeur, "chaine")
        if jeton.est_op("("):
            self.c.indice -= 1
            interieur = self.c.bloc() or []
            morceaux = scinder(interieur)
            if len(morceaux) != 1:
                raise _NonInterpretable("liste entre parenthèses")
            return _Expression(morceaux[0]).analyser()
        if jeton.est("true", "false"):
            return ("lit", jeton.valeur == "true", "booleen")
        if jeton.est("null"):
            return ("lit", None, "nul")
        if jeton.est("array") and self.c.op("["):
            elements = self.c.jusqu_a(lambda j: j.est_op("]"))
            self.c.op("]")
            return ("tableau", [_Expression(m).analyser() for m in scinder(elements)])
        if jeton.est("cast") and self.c.voir() is not None and self.c.voir().est_op("("):
            interieur = self.c.bloc() or []
            position = next((i for i, j in enumerate(interieur) if j.est("as")), None)
            if position is None:
                raise _NonInterpretable("CAST sans AS")
            return ("cast", _Expression(interieur[:position]).analyser(),
                    restituer(interieur[position + 1 :]))
        if jeton.est("date", "timestamp", "time", "interval") and self.c.voir() is not None and (
            self.c.voir().genre == "chaine"
        ):
            return ("lit", self.c.suivant().valeur, "chaine")
        if jeton.est("case", "exists", "select"):
            raise _NonInterpretable(jeton.valeur.upper())
        if jeton.nom is not None:
            if self.c.voir() is not None and self.c.voir().est_op("("):
                interieur = self.c.bloc() or []
                if any(j.est("from", "for", "both", "leading", "trailing", "distinct")
                       for j in interieur):
                    raise _NonInterpretable(f"{jeton.valeur}(…) à mots-clés")
                return ("appel", jeton.nom,
                        [_Expression(m).analyser() for m in scinder(interieur)])
            nom = jeton.nom
            while self.c.op("."):
                nom = self.c.nom() or nom
            return ("col", nom)
        raise _NonInterpretable(jeton.texte)


def _nombre(texte: str) -> int | Decimal:
    if re.fullmatch(r"\d+", texte):
        return int(texte)
    try:
        return Decimal(texte)
    except InvalidOperation as erreur:
        raise _NonInterpretable(texte) from erreur


def _sans_cast(noeud: tuple) -> tuple:
    while noeud[0] == "cast":
        noeud = noeud[1]
    return noeud


_ABSENT = object()


def _litteral(noeud: tuple) -> object:
    """Valeur d un littéral (négation et cast compris), ou `_ABSENT`."""
    noeud = _sans_cast(noeud)
    if noeud[0] == "lit" and noeud[2] != "nul":
        return noeud[1]
    if noeud[0] == "neg":
        valeur = _litteral(noeud[1])
        if isinstance(valeur, (int, Decimal)) and not isinstance(valeur, bool):
            return -valeur
    return _ABSENT


def _colonne_de(noeud: tuple, noms: set[str]) -> str | None:
    noeud = _sans_cast(noeud)
    return noeud[1] if noeud[0] == "col" and noeud[1] in noms else None


def _longueur_de(noeud: tuple, noms: set[str]) -> str | None:
    """`length(col)`, `char_length(trim(col))`… → la colonne mesurée (un jeu n a pas de blancs
    de bord : la longueur rognée vaut la longueur)."""
    noeud = _sans_cast(noeud)
    if noeud[0] != "appel" or noeud[1] not in _FONCTIONS_LONGUEUR or len(noeud[2]) != 1:
        return None
    argument = _sans_cast(noeud[2][0])
    if argument[0] == "appel" and argument[1] in _FONCTIONS_BLANCS and len(argument[2]) == 1:
        argument = argument[2][0]
    return _colonne_de(argument, noms)


def _rogne_de(noeud: tuple, noms: set[str]) -> str | None:
    noeud = _sans_cast(noeud)
    if noeud[0] == "appel" and noeud[1] in _FONCTIONS_BLANCS and len(noeud[2]) == 1:
        return _colonne_de(noeud[2][0], noms)
    return None


_INVERSE = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "=": "=", "<>": "<>", "!=": "!="}


def _effet_de_comparaison(colonne: str, operateur: str, valeur: object) -> Effet:
    if operateur == "=":
        return Effet("permis", colonne, valeurs=(valeur,))
    if operateur in ("<>", "!="):
        return Effet("exclus", colonne, valeurs=(valeur,))
    if operateur in ("<", "<=", ">", ">="):
        return Effet("borne", colonne, operateur, (valeur,))
    raise _NonInterpretable(operateur)


def _litteraux(noeuds: list[tuple]) -> tuple:
    valeurs = tuple(_litteral(n) for n in noeuds)
    if any(v is _ABSENT for v in valeurs):
        raise _NonInterpretable("liste non littérale")
    return valeurs


def _effets(noeud: tuple, noms: set[str]) -> list[Effet]:
    noeud = _sans_cast(noeud)
    genre = noeud[0]
    if genre == "et":
        return _effets(noeud[1], noms) + _effets(noeud[2], noms)
    if genre == "ou":
        return _effets_ou(noeud, noms)
    if genre == "lit" and noeud[1] is True:
        return []
    if genre == "cmp":
        _, operateur, gauche, droite = noeud
        colonne_g, colonne_d = _colonne_de(gauche, noms), _colonne_de(droite, noms)
        valeur_g, valeur_d = _litteral(gauche), _litteral(droite)
        if colonne_g and valeur_d is not _ABSENT:
            return [_effet_de_comparaison(colonne_g, operateur, valeur_d)]
        if colonne_d and valeur_g is not _ABSENT:
            return [_effet_de_comparaison(colonne_d, _INVERSE.get(operateur, "?"), valeur_g)]
        if colonne_g and colonne_d and operateur in ("<", "<=", ">", ">="):
            return [Effet("relation", colonne_g, operateur, autre=colonne_d)]
        mesuree = _longueur_de(gauche, noms)
        if mesuree and isinstance(valeur_d, int) and operateur in _COMPARATEURS:
            return [Effet("longueur", mesuree, operateur, (valeur_d,))]
        mesuree = _longueur_de(droite, noms)
        if mesuree and isinstance(valeur_g, int) and operateur in _COMPARATEURS:
            return [Effet("longueur", mesuree, _INVERSE[operateur], (valeur_g,))]
        rognee = _rogne_de(gauche, noms) or _rogne_de(droite, noms)
        if rognee and operateur in ("<>", "!=") and "" in (valeur_g, valeur_d):
            return [Effet("non_vide", rognee)]
        raise _NonInterpretable("comparaison")
    if genre == "dans":
        _, gauche, elements, nie = noeud
        colonne = _colonne_de(gauche, noms)
        if colonne is None:
            raise _NonInterpretable("IN sur une expression")
        return [Effet("exclus" if nie else "permis", colonne, valeurs=_litteraux(elements))]
    if genre == "quantifie":
        _, operateur, gauche, quantite, interieur = noeud
        colonne, interieur = _colonne_de(gauche, noms), _sans_cast(interieur)
        if colonne is None or interieur[0] != "tableau":
            raise _NonInterpretable("ANY / ALL")
        valeurs = _litteraux(interieur[1])
        if operateur == "=" and quantite in ("any", "some"):
            return [Effet("permis", colonne, valeurs=valeurs)]
        if operateur in ("<>", "!=") and quantite == "all":
            return [Effet("exclus", colonne, valeurs=valeurs)]
        raise _NonInterpretable("ANY / ALL")
    if genre == "entre":
        _, gauche, bas, haut, nie = noeud
        valeur_bas, valeur_haut = _litteral(bas), _litteral(haut)
        if nie or _ABSENT in (valeur_bas, valeur_haut):
            raise _NonInterpretable("BETWEEN")
        colonne = _colonne_de(gauche, noms)
        if colonne:
            return [Effet("borne", colonne, ">=", (valeur_bas,)),
                    Effet("borne", colonne, "<=", (valeur_haut,))]
        mesuree = _longueur_de(gauche, noms)
        if mesuree and isinstance(valeur_bas, int) and isinstance(valeur_haut, int):
            return [Effet("longueur", mesuree, ">=", (valeur_bas,)),
                    Effet("longueur", mesuree, "<=", (valeur_haut,))]
        raise _NonInterpretable("BETWEEN")
    if genre == "estnul":
        _, gauche, nie = noeud
        colonne = _colonne_de(gauche, noms)
        if colonne and nie:
            return [Effet("non_nul", colonne)]
        raise _NonInterpretable("IS NULL")
    if genre == "non":
        interieur = _sans_cast(noeud[1])
        if interieur[0] == "dans" and not interieur[3]:
            return _effets(("dans", interieur[1], interieur[2], True), noms)
        if interieur[0] == "estnul" and not interieur[2]:
            return _effets(("estnul", interieur[1], True), noms)
        raise _NonInterpretable("NOT")
    raise _NonInterpretable(genre)


def _disjoints(noeud: tuple) -> list[tuple]:
    noeud = _sans_cast(noeud)
    if noeud[0] == "ou":
        return _disjoints(noeud[1]) + _disjoints(noeud[2])
    return [noeud]


def _effets_ou(noeud: tuple, noms: set[str]) -> list[Effet]:
    """Deux formes de OU seulement : une énumération (`a = 'x' OR a = 'y'`) et une condition
    qui admet le nul (`a IS NULL OR a > 0`). Le reste n est pas traduisible en valeurs."""
    nuls: set[str] = set()
    autres: list[list[Effet]] = []
    for disjoint in _disjoints(noeud):
        if disjoint[0] == "estnul" and not disjoint[2] and _colonne_de(disjoint[1], noms):
            nuls.add(_colonne_de(disjoint[1], noms))
            continue
        autres.append(_effets(disjoint, noms))
    if nuls and len(autres) == 1 and all(e.colonne in nuls for e in autres[0]):
        return autres[0]
    if not nuls and autres and all(len(e) == 1 and e[0].genre == "permis" for e in autres):
        colonnes = {e[0].colonne for e in autres}
        if len(colonnes) == 1:
            valeurs: list = []
            for effets in autres:
                valeurs.extend(v for v in effets[0].valeurs if v not in valeurs)
            return [Effet("permis", colonnes.pop(), valeurs=tuple(valeurs))]
    raise _NonInterpretable("OR")


def _conjoints(noeud: tuple) -> list[tuple]:
    noeud = _sans_cast(noeud)
    if noeud[0] == "et":
        return _conjoints(noeud[1]) + _conjoints(noeud[2])
    return [noeud]


def interpreter(verification: Verification, noms: set[str]) -> None:
    """Pose `effets` et `interpretee` : chaque conjoint traduit en valeurs, ou compté non lu."""
    try:
        arbre = _Expression(verification.jetons).analyser()
    except _NonInterpretable:
        verification.effets, verification.interpretee = [], "non"
        return
    effets: list[Effet] = []
    reussis = 0
    conjoints = _conjoints(arbre)
    for conjoint in conjoints:
        try:
            effets.extend(_effets(conjoint, noms))
            reussis += 1
        except _NonInterpretable:
            continue
    verification.effets = effets
    verification.interpretee = (
        "oui" if reussis == len(conjoints) else ("partielle" if reussis else "non")
    )


def _finaliser(schema: Schema) -> None:
    for table in schema.tables.values():
        for unicite in table.unicites:
            if unicite.primaire:
                for nom in unicite.colonnes:
                    if nom in table.colonnes:
                        table.colonnes[nom].non_nul = True
        for verification in table.verifications:
            interpreter(verification, set(table.colonnes))


# --- Points d entrée ----------------------------------------------------------------------------


def lire_sections(sections: list[tuple[str, str]]) -> Schema:
    """Schéma obtenu en jouant, dans l ordre, les sections « Up » données (nom, texte)."""
    schema = Schema()
    for nom, texte in sections:
        schema.migrations.append(nom)
        for instruction in decouper(texte):
            _appliquer(instruction, schema, nom)
    _finaliser(schema)
    return schema


def lire(cible: Path) -> Schema:
    """Schéma du projet `cible`, lu dans ses migrations SQL (`<racine>/migrations/*.sql`)."""
    return lire_sections([(f.name, _sections(f)[0]) for f in _fichiers(Path(cible))])
