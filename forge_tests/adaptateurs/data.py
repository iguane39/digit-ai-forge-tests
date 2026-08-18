"""Adaptateur Data (SQL) — tables et contraintes depuis les migrations, exercées PAR VIOLATION."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests import classes
from forge_tests.disposition import paquet_sources, racine_execution
from forge_tests.execution import (
    instructions_sql,
    motif_indisponibilite,
    schema_obtenu,
    sources_sql,
    violations_levees,
)
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter
from forge_tests.sql import sans_commentaires

NOM, PAN, SEUIL = "data-sql", "data", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "nommer les contraintes de la base `<type>_<table>_<colonne>` dans les migrations, et "
    "exercer chaque contrainte PAR VIOLATION dans la suite — la sonde data relève les "
    "violations réellement levées par le moteur (SQLAlchemy ou sqlite3)"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T2", "famille": "technique", "titre": "Données",
     "decoupe": "table", "axe_cas": "unitaire"},
)

# RT-14 (TF-0208) : le mot qui suit le mot-cle n est PAS toujours le nom de l objet. Les formes
# idempotentes `IF EXISTS` / `IF NOT EXISTS` s intercalent, et l inventaire retenait `IF` — une
# contrainte FANTOME, introuvable dans la base, donc « jamais exercee », cotee bloquante et
# impossible a satisfaire autrement qu en fabriquant une contrainte inexistante (G-2 : refuse).
#
# Le conflit etait INTERNE a la forge : le pan `migrations` EXIGE les trois sens (aller, rejeu,
# retour), donc l idiome `DROP CONSTRAINT IF EXISTS <nom>; ADD CONSTRAINT <nom> …` ; le pan
# `data` transformait ensuite cet idiome en defaut bloquant. Aucun projet ne pouvait satisfaire
# les deux pans a la fois — un defaut de l auditeur, jamais de l audite.
_SI_EXISTE = r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
_TABLE = re.compile(rf"CREATE\s+TABLE\s+{_SI_EXISTE}(\w+)\s*\(", re.IGNORECASE)
# `DROP CONSTRAINT x` n ANNONCE pas x, il le RETIRE : l inventorier fabriquerait un element que
# rien ne peut plus violer. Meme regle, meme motif que `migrations.py` (`(?<!DROP )CONSTRAINT`).
# Dans l idiome idempotent, c est l `ADD CONSTRAINT` qui suit qui porte l objet reellement cree.
_CONTRAINTE = re.compile(
    rf"(?:(DROP|ADD)\s+)?CONSTRAINT\s+{_SI_EXISTE}(\w+)", re.IGNORECASE
)
_NOT_NULL = re.compile(r"^\s*(\w+)\s+\w+\s+NOT NULL", re.IGNORECASE | re.MULTILINE)
_INDEX = re.compile(rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+{_SI_EXISTE}(\w+)", re.IGNORECASE)
_TRIGGER = re.compile(rf"CREATE\s+TRIGGER\s+{_SI_EXISTE}(\w+)", re.IGNORECASE)


def contraintes_declarees(texte: str) -> list[str]:
    """Noms des contraintes qu un fragment SQL CREE, dans l ordre, sans les formes idempotentes.

    Le texte est attendu DEJA nettoye de ses commentaires (`forge_tests.sql.sans_commentaires`) :
    la ligne de commentaire qui cite `DROP CONSTRAINT IF EXISTS` — un en-tete de migration qui
    documente son propre idiome — ne doit rien inventorier.
    """
    return [nom for verbe, nom in _CONTRAINTE.findall(texte) if verbe.upper() != "DROP"]


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
    "data : le repli `sqlite3` relève les INSTRUCTIONS envoyées au pilote, pas les violations "
    "de contrainte ; sur un projet sans SQLAlchemy les contraintes restent donc non "
    "attribuables — tables, index et triggers, eux, sont mesurés",
]


def _motif_surface_absente(cible: Path) -> str:
    """Pourquoi il n y a RIEN à inventorier ici — jamais « exercé = 0 » sans explication.

    Deux causes très différentes, qu un compteur à zéro confondait : le projet a bien une
    couche SQL mais son schéma naît du code applicatif (aucune migration, aucun modèle ORM),
    ou le projet n a aucune couche SQL observable.
    """
    envoyees = instructions_sql(cible) or []
    vues = sources_sql(cible) or []
    if envoyees:
        return (
            f"data : aucune migration SQL ni contrainte ORM à inventorier — surface data non "
            f"énumérable, alors que {len(envoyees)} instructions SQL ont été OBSERVÉES pendant "
            f"la suite (relevé {', '.join(vues)}) : le schéma de ce projet est créé par le code "
            f"applicatif, hors migrations"
        )
    return (
        "data : projet sans couche SQL observable — ni SQLAlchemy ni le repli sqlite3 n ont vu "
        "passer d instruction pendant la suite : pans data/migrations non mesurables"
    )


def _sql(cible: Path) -> list[Path]:
    """Migrations SQL, sous la racine DÉCOUVERTE — même ancre que le pan `migrations`.

    TF-0256 : ce pan énumère sa surface DEPUIS les migrations. Ancré en dur sur
    `<cible>/backend/migrations`, il rendait un inventaire VIDE sur toute racine plate, donc un
    SKIP « aucune migration SQL ni contrainte ORM à inventorier » — et les tests de violation
    de contrainte réellement joués par le projet n étaient crédités à rien.
    """
    return sorted((racine_execution(cible) / "migrations").glob("*.sql"))


_EXCLUS_MODELES = {".venv", "venv", "node_modules", "__pycache__", "tests", "migrations", "alembic"}


def _fichiers_modeles(cible: Path) -> list[Path]:
    """Modules ORM du projet — recherche récursive, pas un seul chemin conventionnel.

    TF-0097 : l adaptateur ne regardait que `backend/app/models.py`. Un projet dont les modèles
    vivent sous `backend/app/db/models.py` (ou toute autre sous-arborescence) sortait « aucune
    contrainte ORM à inventorier », alors que les modèles existent bel et bien.

    TF-0256 : le paquet est DÉCOUVERT (`disposition.paquet_sources`) au lieu d être supposé
    `<cible>/backend/app`. Sur racine plate, les modèles vivent sous `<cible>/app` — invisibles
    jusqu ici, donc aucune contrainte ORM inventoriée ni aucune divergence modèle/migration
    détectable.
    """
    racine = paquet_sources(cible)
    if racine is None:
        return []
    conventionnels = [racine / "models.py", racine / "db" / "models.py"]
    trouves = [p for p in conventionnels if p.is_file()]
    if trouves:
        return trouves
    if not racine.is_dir():
        return []
    return sorted(
        p for p in racine.rglob("models.py")
        if not (_EXCLUS_MODELES & set(p.relative_to(racine).parts[:-1]))
    )


def inventaire(cible: Path) -> list[Element]:
    elements: list[Element] = []
    vus: set[str] = set()
    for fichier in _sql(cible):
        # RT-8 generalise : les expressions regulieres d inventaire lisaient le TEXTE BRUT. Une
        # table, un index ou une contrainte mis en COMMENTAIRE entraient donc a l inventaire —
        # objets qui n existent pas, donc elements « jamais exerces » impossibles a couvrir.
        haut = sans_commentaires(
            fichier.read_text(encoding="utf-8").partition("-- +migrate Down")[0]
        )
        for table in _TABLE.findall(haut):
            if f"table:{table}" not in vus and not table.endswith(("_nouveau", "_ancien")):
                vus.add(f"table:{table}")
                elements.append(Element(f"table:{table}", PAN, f"table {table}", str(fichier)))
        for nom in contraintes_declarees(haut):
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
    for modeles in _fichiers_modeles(cible):
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


def exerces(cible: Path) -> set[str] | None:
    """Contraintes RÉELLEMENT violées pendant la suite, lues dans les erreurs de la base.

    TF-0270 : aucun repli TEXTUEL ici, pour aucune classe. Il en existait un — lecture des
    blocs de `backend/tests` à la recherche du nom de l élément — débranché le 02/08 quand la
    sonde SQL a rendu l exécution mesurable (« l exécution tranche pour toutes les classes »),
    puis resté en place sans appelant jusqu au 15/08. Ce qu un test NOMME ne prouve rien : ce
    qu il fait LEVER par le moteur, si. Une clé étrangère que SQLite ne nomme pas reste donc
    non attribuable — c est déclaré en `NON_JUGE`, pas rattrapé par une ressemblance de nom.
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


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "data : couverture non mesurable — "
                + motif_indisponibilite(
                    cible, "backend", "sonde indisponible : suite rouge ou environnement absent"
                ),
            ],
        )
    inv = inventaire(cible)
    if not inv:
        # `evaluer_surface` conclurait SKIP « inventaire VIDE », motif exact mais muet sur la
        # CAUSE ; et la suite d `analyser` ajouterait par-dessus « schema reel non
        # introspectable », qui devenait le motif publie — un contresens pour le lecteur.
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP", non_juge=[*NON_JUGE, _motif_surface_absente(cible)]
        )
    # TF-0309 — `list(NON_JUGE)` comme le pan `migrations` : `evaluer_surface` garde la liste
    # REÇUE, et l `append` ci-dessous mutait donc la constante du module. Le motif du banc rouge
    # se retrouvait publié sur le banc vert, et plus le motif est précis (la cause du rejeu, ici)
    # plus la fuite ment.
    sortie = evaluer_surface(NOM, PAN, str(cible), inv, couvert, SEUIL, list(NON_JUGE))

    # Une contrainte declaree au MODELE mais absente des MIGRATIONS est une divergence : le code
    # croit la base protegee, la base ne l est pas. Aucun test ne peut la reveler — il n y a rien
    # a violer. Seule la comparaison des deux sources la nomme.
    # Ce qui existe VRAIMENT apres application des migrations, pas ce que leur texte annonce :
    # une instruction peut s executer sans produire l objet qu on croit qu elle produit.
    schema = schema_obtenu(str(cible))
    if schema is None:
        reference = " ".join(
            sans_commentaires(f.read_text(encoding="utf-8")) for f in _sql(cible)
        )
        # TF-0309 — le motif DÉCLARÉ par le rejeu voyage jusqu au rapport : « non introspectable »
        # seul ne dit pas si une migration est invalide ou si le démon de conteneurs manque. Même
        # reprise que le pan `back` (TF-0299) : deux diagnostics du même fait valent moins qu un.
        sortie.non_juge.append(
            "data : schema reel non introspectable — divergence jugee sur le TEXTE des "
            "migrations. Cause : "
            + motif_indisponibilite(cible, "schema", "non declaree par le rejeu")
        )
    else:
        reference = " ".join(schema["contraintes"] + schema["index"] + schema["tables"])
    for modeles in _fichiers_modeles(cible):
        for nom in _ORM_NOMMEE.findall(modeles.read_text(encoding="utf-8")):
            if nom in reference:
                continue
            sortie.findings.append(
                Finding(
                    id=f"divergence:contrainte:{nom}",
                    classe=classes.DIVERGENCE,
                    localisation=str(modeles),
                    message=(
                        f"contrainte {nom} déclarée au modèle mais absente des migrations : "
                        "la base ne l'applique pas"
                    ),
                    risque=coter(PAN, f"contrainte:{nom}", str(modeles)),
                )
            )
            sortie.verdict = "FAIL"
    return sortie
