"""Adaptateur Migrations — chaque migration doit être exercée à l ALLER, au RETOUR et en REJEU."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

from forge_tests.disposition import racine_execution
from forge_tests.execution import (
    instructions_sql,
    motif_indisponibilite,
    schema_obtenu,
    sources_sql,
)
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter
from forge_tests.sql import decouper, sans_commentaires

NOM, PAN, SEUIL = "migrations-sql", "migrations", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "déposer les migrations sous `backend/migrations/*.sql` avec les marqueurs `-- +migrate "
    "Up` / `-- +migrate Down`, et laisser le projet rejouable sur base neuve — le pan "
    "applique RÉELLEMENT le DDL, il ne le lit pas"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T3", "famille": "technique", "titre": "Migrations",
     "decoupe": "fichier", "axe_cas": "migration"},
)

SENS = ("aller", "retour", "rejeu")
_MOTS = {
    "aller": ("aller", "up", "upgrade"),
    "retour": ("retour", "down", "downgrade"),
    "rejeu": ("rejeu", "replay", "rejouer"),
}

NON_JUGE = [
    "migrations : l effet verifie est l EXISTENCE des objets nommes (tables, contraintes, "
    "index) apres application ; ni leur definition exacte, ni les donnees migrees",
    "migrations : le rejeu est déduit d une seconde exécution de TOUTES les instructions de "
    "la section ; deux migrations rigoureusement identiques resteraient indiscernables",
]


def _fichiers(cible: Path) -> list[Path]:
    """Migrations SQL du projet, sous la racine DÉCOUVERTE — jamais `<cible>/backend` supposé.

    TF-0256 : TF-0216 avait doté la forge d une découverte de racine (`disposition.py`), mais
    ce pan ne la consommait pas. Sur un produit à RACINE PLATE dont les migrations vivent en
    `<cible>/migrations`, `_fichiers` rendait une liste vide : le pan sortait « aucune migration
    à inventorier » et le pan `data`, ancré au même endroit, n a jamais crédité les 37 tests de
    violation de contraintes qui existaient bel et bien. Un faux négatif de l auditeur, pas un
    trou de l audité.
    """
    return sorted((racine_execution(cible) / "migrations").glob("*.sql"))


def _script_location(cible: Path) -> Path | None:
    """Dossier Alembic déclaré par le projet lui-même (`script_location` de `alembic.ini`).

    TF-0097 : trois chemins codés en dur ne lisaient jamais la configuration que le projet
    déclare en clair. Un `script_location = migrations` posé dans `backend/alembic.ini`
    pointait vers `backend/migrations/versions/` — jamais essayé, alors que 9 migrations y
    vivaient et avaient été appliquées avec succès (`alembic upgrade head`).
    """
    # TF-0256 : la racine DÉCOUVERTE d abord — elle couvre la racine plate comme la disposition
    # déclarée par `FORGE_TESTS_SOURCES` absolu. Les deux ancres historiques restent en repli :
    # sur la disposition `backend/` elles coïncident, aucun projet déjà mesuré ne bouge.
    ancres = (racine_execution(cible), cible / "backend", cible)
    vus: set[Path] = set()
    for ini in (ancre / "alembic.ini" for ancre in ancres):
        if ini in vus:
            continue
        vus.add(ini)
        if not ini.is_file():
            continue
        parseur = configparser.ConfigParser()
        try:
            parseur.read(ini, encoding="utf-8")
        except configparser.Error:
            continue
        brut = parseur.get("alembic", "script_location", fallback="").strip()
        if not brut:
            continue
        chemin = Path(brut)
        return chemin if chemin.is_absolute() else (ini.parent / chemin)
    return None


def _versions_alembic(cible: Path) -> list[Path]:
    declare = _script_location(cible)
    # TF-0256 : conventions ancrées sur la racine DÉCOUVERTE, puis les trois chemins historiques.
    # Sur la disposition `backend/` les deux séries coïncident dans le même ordre ; sur racine
    # plate, `app/alembic/versions` devient enfin atteignable.
    candidats = (
        ([declare / "versions"] if declare else [])
        + [racine_execution(cible) / base for base in ("app/alembic/versions", "alembic/versions")]
        + [
            cible / base
            for base in (
                "backend/app/alembic/versions",
                "backend/alembic/versions",
                "alembic/versions",
            )
        ]
    )
    for dossier in candidats:
        if dossier.is_dir():
            return sorted(p for p in dossier.glob("*.py") if p.name != "__init__.py")
    return []


def inventaire(cible: Path) -> list[Element]:
    fichiers = _fichiers(cible) or _versions_alembic(cible)
    return [
        Element(
            f"migration:{fichier.stem}:{sens}",
            PAN,
            f"migration {fichier.stem} au {sens}",
            str(fichier),
        )
        for fichier in fichiers
        for sens in SENS
    ]


def _motif_sans_migration(cible: Path) -> str:
    """Pourquoi il n y a AUCUNE migration à inventorier, plutôt qu un compteur à zéro.

    TF-0097 : « aucune surface » (le projet n a pas de migrations) et « surface non localisée »
    (le projet EN DÉCLARE mais le dossier annoncé est introuvable — chemin fautif, script_location
    mal renseigné) n appellent pas le même travail : la première ne réclame rien, la seconde une
    correction de configuration. Les confondre revient au faux négatif que ce correctif corrige.
    """
    declare = _script_location(cible)
    if declare is not None and not (declare / "versions").is_dir():
        return (
            f"migrations : script_location declare ({declare}) dans alembic.ini mais son "
            f"dossier versions est introuvable ({declare / 'versions'}) — surface NON "
            "LOCALISEE, pas absente : verifier le chemin declare"
        )
    envoyees = instructions_sql(cible) or []
    vues = sources_sql(cible) or []
    dossier = racine_execution(cible) / "migrations"
    if envoyees:
        return (
            f"migrations : aucune migration à inventorier — ni {dossier}"
            f"/*.sql ni versions Alembic, alors que {len(envoyees)} instructions SQL ont été "
            f"OBSERVÉES pendant la suite (relevé {', '.join(vues)}) : le schéma de ce projet "
            f"n est pas versionné par migrations"
        )
    return (
        "migrations : projet sans couche SQL observable — ni SQLAlchemy ni le repli sqlite3 "
        "n ont vu passer d instruction pendant la suite : pan migrations non mesurable"
    )


def _downgrades_vides(cible: Path) -> list[Path]:
    """Migrations Alembic dont le downgrade est un `pass` : non reversibles, comme H-05."""
    import ast as _ast

    vides: list[Path] = []
    for fichier in _versions_alembic(cible):
        try:
            arbre = _ast.parse(fichier.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for noeud in arbre.body:
            if isinstance(noeud, _ast.FunctionDef) and noeud.name == "downgrade":
                # Un appel `op.drop_table(...)` EST un ast.Expr : ne filtrer que les docstrings
                # (Expr portant une Constante) et les `pass` — faux positif corrige sur le
                # premier projet reel, ou 12 downgrades legitimes etaient signales vides.
                corps = [
                    n
                    for n in noeud.body
                    if not isinstance(n, _ast.Pass)
                    and not (
                        isinstance(n, _ast.Expr) and isinstance(n.value, _ast.Constant)
                    )
                ]
                if not corps:
                    vides.append(fichier)
    return vides


def _instructions(section: str) -> list[str]:
    """Instructions normalisées d une section de migration, comparables au relevé du moteur.

    RT-8 : le découpage se faisait sur `;` AVANT le filtrage des commentaires. Un `;` posé dans
    un commentaire `--` fabriquait une instruction qui n avait jamais existé, que le moteur
    n avait donc jamais vue, et la migration passait pour non exercée — un FAIL à tort constaté
    en production sur `0004_catalogues.sql`. Symétriquement, une VRAIE instruction précédée d un
    commentaire de tête était rejetée en bloc par le `startswith("--")` : la section entière
    perdait son instruction la plus tardive. `forge_tests.sql` filtre d abord, découpe ensuite.
    """
    return decouper(section)


def exerces(cible: Path) -> set[str] | None:
    """Sens exercés : les instructions de la section ont-elles ÉTÉ ENVOYÉES au moteur ?

    Écart avec le recoupement textuel : un test qui nomme « retour » sans jamais appliquer la
    section de retour ne couvre plus rien. C est le fait d exécution qui compte, pas le mot.
    """
    executees_ = instructions_sql(cible)
    if executees_ is None:
        return None
    vues = [" ".join(s.split()) for s in executees_]

    def comptees(instructions: list[str]) -> int:
        """Nombre de fois ou la section ENTIERE a ete envoyee.

        Se fier a la premiere instruction confondait deux migrations qui commencent pareil.
        On exige desormais que TOUTES les instructions de la section aient ete vues, et on
        compte les passages par la moins frequente d entre elles.
        """
        if not instructions:
            return 0
        passages = []
        for instruction in instructions:
            reference = instruction[:200]
            passages.append(sum(1 for vue in vues if reference and reference in vue))
        return min(passages)

    couvert: set[str] = set()
    for fichier in _fichiers(cible):
        haut, bas = _sections(fichier)
        occurrences_aller = comptees(_instructions(haut))
        if occurrences_aller >= 1:
            couvert.add(f"migration:{fichier.stem}:aller")
        if occurrences_aller >= 2:
            couvert.add(f"migration:{fichier.stem}:rejeu")
        if comptees(_instructions(bas)) >= 1:
            couvert.add(f"migration:{fichier.stem}:retour")
    return couvert


def _sections(fichier: Path) -> tuple[str, str]:
    texte = fichier.read_text(encoding="utf-8")
    haut, _, bas = texte.partition("-- +migrate Down")
    return haut.replace("-- +migrate Up", ""), bas


def analyser(cible: Path) -> SortieAdaptateur:
    couvert = exerces(cible)
    if couvert is None:
        inv = inventaire(cible)
        sortie = SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"migrations : {len(inv)} elements inventories "
                f"({len(inv) // 3} migrations x 3 sens) "
                "mais couverture non mesurable — "
                + motif_indisponibilite(cible, "backend", "suite non executable sous sonde"),
            ],
        )
        # Les divergences STATIQUES restent detectables meme sans execution.
        for fichier in _downgrades_vides(cible):
            sortie.findings.append(
                Finding(
                    id=f"divergence:migration:{fichier.stem}:retour",
                    classe="divergence",
                    localisation=str(fichier),
                    message="downgrade vide : la migration ne peut pas être inversée",
                    risque=coter(PAN, f"migration:{fichier.stem}", str(fichier)),
                )
            )
            sortie.verdict = "FAIL"
        return sortie
    inv = inventaire(cible)
    if not inv:
        # Sans ce motif, le SKIP publiait « schema reel non introspectable », ajoute plus bas :
        # un contresens quand la vraie raison est qu il n y a aucune migration a inventorier.
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP", non_juge=[*NON_JUGE, _motif_sans_migration(cible)]
        )
    sortie = evaluer_surface(NOM, PAN, str(cible), inv, couvert, SEUIL, list(NON_JUGE))
    # Une migration sans section de retour est une DIVERGENCE de la source, pas un trou de suite.
    for fichier in _fichiers(cible):
        if "-- +migrate Down" not in fichier.read_text(encoding="utf-8"):
            sortie.findings.append(
                Finding(
                    id=f"migration:{fichier.stem}:retour",
                    classe="divergence",
                    localisation=str(fichier),
                    message="migration sans section de retour : elle ne peut pas être inversée",
                    risque=coter(PAN, "migration:retour", str(fichier)),
                )
            )
            sortie.verdict = "FAIL"
    # Alembic : un downgrade vide est une migration NON REVERSIBLE — detectable statiquement.
    for fichier in _downgrades_vides(cible):
        sortie.findings.append(
            Finding(
                id=f"divergence:migration:{fichier.stem}:retour",
                classe="divergence",
                localisation=str(fichier),
                message="downgrade vide : la migration ne peut pas être inversée",
                risque=coter(PAN, f"migration:{fichier.stem}", str(fichier)),
            )
        )
        sortie.verdict = "FAIL"
    # Effet REEL : un objet qu une section pretend creer doit exister apres application.
    schema = schema_obtenu(str(cible))
    if schema is None:
        # TF-0309 — cf. `data` : la CAUSE déclarée par le rejeu suit le motif. Un démon de
        # conteneurs absent frappe ce chemin même quand la suite backend, elle, tourne sans
        # conteneur : sans cette reprise il restait muet sur son seul chemin.
        sortie.non_juge.append(
            "migrations : schema reel non introspectable, effet non verifie. Cause : "
            + motif_indisponibilite(cible, "schema", "non declaree par le rejeu")
        )
        return sortie
    presents = set(schema["tables"]) | set(schema["contraintes"]) | set(schema["index"])
    for fichier in _fichiers(cible):
        # RT-8 generalise : lire les ANNONCES sur le texte brut faisait entrer a l inventaire
        # un `CREATE TABLE` mis en commentaire — objet jamais cree, donc divergence fabriquee.
        haut = sans_commentaires(_sections(fichier)[0])
        # `DROP CONSTRAINT x` n ANNONCE pas x, il le retire : le compter serait accuser la
        # migration qui defait au lieu de celle qui promet.
        # TF-0208 (RT-14) etendu a CE pan : `IF NOT EXISTS` doit etre CONSOMME avant de lire le
        # nom, sinon l objet annonce s appelle « IF » — introuvable au schema, donc une
        # divergence BLOQUANTE fabriquee. Le comble : c est ce pan qui EXIGE l idiome
        # idempotent (aller/rejeu/retour), et c est lui qui le punissait. Meme fragment que
        # `data._SI_EXISTE`, ecrit ici pour ne pas coupler deux adaptateurs.
        si_existe = r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
        annonces = set(
            re.findall(rf"(?<!DROP )CONSTRAINT {si_existe}(\w+)", haut, re.IGNORECASE)
        )
        annonces |= set(
            re.findall(rf"CREATE (?:UNIQUE )?INDEX {si_existe}(\w+)", haut, re.IGNORECASE)
        )
        annonces |= set(re.findall(rf"CREATE TABLE {si_existe}(\w+)", haut, re.IGNORECASE))
        # « IF » n est jamais un nom d objet : si un motif le laisse encore passer, il ment.
        annonces -= {"IF", "if"}
        for nom in sorted(annonces - presents):
            sortie.findings.append(
                Finding(
                    id=f"divergence:migration:{fichier.stem}:{nom}",
                    classe="divergence",
                    localisation=str(fichier),
                    message=(
                        f"{nom} annoncé par la migration mais absent du schéma obtenu : "
                        "l'instruction s'exécute sans produire son objet"
                    ),
                    risque=coter(PAN, f"migration:{nom}", str(fichier)),
                )
            )
            sortie.verdict = "FAIL"
    return sortie
