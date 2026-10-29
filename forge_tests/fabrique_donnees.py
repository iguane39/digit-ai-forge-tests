"""Fabrique de données — la capacité 4 de la spec (« fixtures, seeding, teardown, cas limites »).

TF-2012. Le CDC le constatait le 02/08/2026 (C4) : « Aucune fabrique de données n existe ». Le
jeu des livrables (`livrables/jeux.py`) est un JSON pour les cahiers : il dit la FORME d un cas,
il ne se charge dans aucune base. Ce module fabrique un jeu CHARGEABLE : un fichier d INSERT
dérivé du schéma que construisent les migrations SQL du projet (`schema_sql`), dans l ordre des
clés étrangères, et JUGÉ par le seul juge qui vaille — un chargement réel sur une base
PostgreSQL éphémère, créée puis détruite pour l occasion.

Trois lois, dans l ordre où elles s appliquent :

  1. **Synthétique, et prouvé tel avant écriture.** Les valeurs viennent du vocabulaire fermé de
     `jeux.py` et de règles écrites ici ; les seules qui viennent du projet sont celles que son
     schéma IMPOSE (une liste `CHECK … IN`, un type énuméré). Toutes passent par le garde-fou de
     `jeux.py` avant que le fichier existe : un courriel hors domaine réservé, une valeur qui
     ressemble à un secret, une valeur de configuration du projet lèvent `DonneeNonSynthetique`
     et rien n est écrit. Décision (c) du cadrage : synthétiques uniquement.
  2. **Déterministe.** Même schéma, même graine, mêmes volumes : même octet. Les tirages ne
     passent que par `random.Random.random()`, la seule méthode dont la documentation du module
     garantit la suite d une version de Python à l autre.
  3. **Jugé par exécution, jamais par confiance.** Les migrations « Up » sont rejouées sur une
     base neuve, puis le jeu, instruction par instruction : zéro rejet et toutes les lignes
     présentes, ou le verdict nomme la contrainte. Sans démon de conteneurs, ou sans
     `testcontainers` dans l interpréteur, le verdict est NON EXÉCUTABLE ICI — jamais un vert.

Usage : `uv run python -m forge_tests.fabrique_donnees <projet> --sortie <jeu.sql>`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path

from forge_tests import execution as _execution
from forge_tests import schema_sql
from forge_tests.adaptateurs.migrations import _fichiers, _versions_alembic
from forge_tests.livrables import DepotInterdit, _verifier_hors_projet
from forge_tests.livrables import jeux as _jeux
from forge_tests.schema_sql import Colonne, Schema, Table, citer

NON_JUGE = [
    "fabrique de donnees : seul PostgreSQL juge le jeu (base ephemere postgres:16-alpine montee "
    "par testcontainers) ; un projet servi par un autre moteur (SQLite, MySQL, SQL Server) recoit "
    "un jeu dont le chargement n est pas juge pour son moteur",
    "fabrique de donnees : seules les migrations SQL `-- +migrate Up` sont lues ; un schema "
    "versionne par Alembic, ou par un ORM sans migrations SQL, n est pas lu et aucun jeu n est "
    "produit — la fabrique le dit au lieu d inventer un schema",
    "fabrique de donnees : une verification CHECK hors des formes reconnues (IN, = ANY, "
    "comparaison a une borne, BETWEEN, longueur, IS NOT NULL, relation d ordre entre deux "
    "colonnes, OU d egalites) n est pas traduite en valeurs : elle est NOMMEE au rapport et seul "
    "le chargement reel la juge",
    "fabrique de donnees : un declencheur, une regle, une politique RLS ou une contrainte "
    "d exclusion (EXCLUDE) n est pas modelise ; seul le chargement reel en juge l effet",
    "fabrique de donnees : les lignes que les migrations inserent elles-memes ne sont pas lues ; "
    "une unicite qu elles occupent deja peut faire echouer le chargement, qui le nomme",
    "fabrique de donnees : le jeu dit la FORME d une donnee valide (type, bornes, unicite, "
    "cles), pas la semantique metier d une colonne — un `telephone` recoit un libelle",
    "fabrique de donnees : aucun script de retrait (teardown) n est produit pour une base "
    "durable ; seule la base ephemere du jugement est creee puis detruite",
    "fabrique de donnees : un cycle de cles etrangeres sans colonne nullable n est pas resolu "
    "(ni UPDATE differe, ni contrainte DEFERRABLE exploitee) : les lignes qu il empeche manquent "
    "au volume, et le rapport le dit",
    "fabrique de donnees : un index unique sur EXPRESSION (`lower(email)`) est approche par les "
    "colonnes qu il cite, comparees sans casse ; un index unique PARTIEL est tenu comme total",
]

VOLUME_DEFAUT = 10
GRAINE_DEFAUT = 1
DELAI_CHARGEMENT_S = 600
ESSAIS_PAR_LIGNE = 25
SONDE = Path(__file__).resolve().parent / "sondes" / "charger_jeu.py"

# Codes de sortie, alignés sur ceux du CLI d audit : 0 conforme · 1 défaut · 2 refus ou erreur ·
# 3 jugement non rendu (partiel, non exécutable, non demandé) · 4 refus G-1.
SORTIE_PASS, SORTIE_FAIL, SORTIE_ERREUR, SORTIE_NON_JUGE, SORTIE_REFUS_G1 = 0, 1, 2, 3, 4
_CODES = {"PASS": SORTIE_PASS, "FAIL": SORTIE_FAIL, "ERREUR": SORTIE_ERREUR,
          "REFUSE": SORTIE_ERREUR, "PARTIEL": SORTIE_NON_JUGE,
          "NON_EXECUTABLE": SORTIE_NON_JUGE, "NON_JUGE": SORTIE_NON_JUGE,
          "REFUS_G1": SORTIE_REFUS_G1}

JOUR_PIVOT = date.fromisoformat(_jeux.JOUR_PIVOT)
_ORIGINE_DATE = date(2000, 1, 1)
_ORIGINE_HORODATAGE = datetime(2000, 1, 1)
_NUMERIQUES = frozenset({"entier", "decimal", "flottant", "monnaie", "date", "horodatage",
                         "horodatage_tz", "heure", "heure_tz"})


class SchemaIntrouvable(RuntimeError):
    """Le projet ne porte aucun schéma lisible par la fabrique. Rien n est inventé à sa place."""


class _Impossible:
    """Aucune valeur admise ne reste pour cette colonne."""


IMPOSSIBLE = _Impossible()


# --- Tirages ------------------------------------------------------------------------------------


def _rang_table(nom: str) -> int:
    return sum((position + 1) * ord(caractere) for position, caractere in enumerate(nom))


class _Tirage:
    """Tirages déterministes d une table : seule `random()` est garantie stable entre versions."""

    def __init__(self, graine: int, table: str) -> None:
        self._alea = random.Random(graine * 1_000_003 + _rang_table(table))

    def entier(self, borne: int) -> int:
        """Entier dans [0, borne[."""
        if borne <= 1:
            return 0
        return min(int(self._alea.random() * borne), borne - 1)

    def choix(self, valeurs: list | tuple):
        return valeurs[self.entier(len(valeurs))]


# --- Domaines -----------------------------------------------------------------------------------


@dataclass
class _Domaine:
    """Ce que le schéma admet pour une colonne, d après son type et ses vérifications lues."""

    permis: list | None = None
    exclus: set = field(default_factory=set)
    basses: list[tuple[object, bool]] = field(default_factory=list)
    hautes: list[tuple[object, bool]] = field(default_factory=list)
    long_min: int = 0
    long_max: int | None = None
    non_nul: bool = False
    # Citée par une vérification non (entièrement) interprétée : aucune valeur de bord n y est
    # injectée, aucun NULL non plus — rien qui puisse fabriquer un rejet que le jeu n a pas voulu.
    contrainte: bool = False


def _appliquer_effet(domaine: _Domaine, effet: schema_sql.Effet) -> None:
    if effet.genre == "permis":
        if domaine.permis is None:
            domaine.permis = list(effet.valeurs)
        else:
            domaine.permis = [v for v in domaine.permis if v in effet.valeurs]
    elif effet.genre == "exclus":
        domaine.exclus.update(effet.valeurs)
    elif effet.genre == "borne":
        valeur = effet.valeurs[0]
        if effet.operateur in (">", ">="):
            domaine.basses.append((valeur, effet.operateur == ">="))
        else:
            domaine.hautes.append((valeur, effet.operateur == "<="))
    elif effet.genre == "longueur":
        n = int(effet.valeurs[0])
        mini, maxi = {"=": (n, n), ">": (n + 1, None), ">=": (n, None), "<": (0, n - 1),
                      "<=": (0, n)}.get(effet.operateur or "", (0, None))
        domaine.long_min = max(domaine.long_min, mini)
        if maxi is not None:
            domaine.long_max = maxi if domaine.long_max is None else min(domaine.long_max, maxi)
    elif effet.genre == "non_nul":
        domaine.non_nul = True
    elif effet.genre == "non_vide":
        domaine.long_min = max(domaine.long_min, 1)


def _domaines(table: Table, schema: Schema) -> tuple[dict[str, _Domaine], list[schema_sql.Effet]]:
    domaines = {
        nom: _Domaine(long_max=colonne.longueur_max, non_nul=colonne.non_nul)
        for nom, colonne in table.colonnes.items()
    }
    for nom, colonne in table.colonnes.items():
        if colonne.enum:
            domaines[nom].permis = list(schema.enums.get(colonne.enum, []))
    relations: list[schema_sql.Effet] = []
    for verification in table.verifications:
        if verification.interpretee != "oui":
            for nom in verification.colonnes:
                if nom in domaines:
                    domaines[nom].contrainte = True
        for effet in verification.effets:
            if effet.genre == "relation":
                relations.append(effet)
            elif effet.colonne in domaines:
                _appliquer_effet(domaines[effet.colonne], effet)
    return domaines, relations


# --- Valeurs ------------------------------------------------------------------------------------


def _ascii(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")


def _base36(n: int) -> str:
    chiffres = "0123456789abcdefghijklmnopqrstuvwxyz"
    sortie = ""
    while True:
        n, reste = divmod(n, 36)
        sortie = chiffres[reste] + sortie
        if n == 0:
            return sortie


def _parmi(candidats: list, rang: int, seule: bool, tirage: _Tirage, etat: dict):
    """Une valeur admise : la suivante si la colonne est unique, sinon un tirage."""
    if not candidats:
        return IMPOSSIBLE
    if seule:
        indice = etat.get("indice_permis", 0)
        if indice >= len(candidats):
            return IMPOSSIBLE
        etat["indice_permis"] = indice + 1
        return candidats[indice]
    if rang == 0:
        return candidats[0]
    return tirage.choix(candidats)


def _echelle(colonne: Colonne) -> int:
    if colonne.famille == "decimal" and colonne.echelle is not None:
        return colonne.echelle
    return 2 if colonne.famille in ("decimal", "flottant", "monnaie") else 0


def _horodatage(texte: str) -> datetime:
    texte = texte.strip().replace("T", " ")
    return datetime.fromisoformat(texte[:19]) if len(texte) > 10 else datetime.fromisoformat(
        texte[:10]
    )


def _vers_unites(valeur: object, colonne: Colonne) -> Decimal | None:
    """La valeur exprimée en unités entières de la colonne (centimes, jours, minutes…)."""
    famille = colonne.famille
    try:
        if famille in ("entier", "decimal", "flottant", "monnaie"):
            if isinstance(valeur, bool):
                return None
            return Decimal(str(valeur)).scaleb(_echelle(colonne))
        if famille == "date":
            jour = valeur if isinstance(valeur, date) and not isinstance(valeur, datetime) else (
                date.fromisoformat(str(valeur)[:10])
            )
            return Decimal((jour - _ORIGINE_DATE).days)
        if famille in ("horodatage", "horodatage_tz"):
            moment = valeur if isinstance(valeur, datetime) else _horodatage(str(valeur))
            return Decimal(int((moment - _ORIGINE_HORODATAGE).total_seconds())) / 60
        if famille in ("heure", "heure_tz"):
            heure = valeur if isinstance(valeur, time) else time.fromisoformat(str(valeur)[:8])
            return Decimal(heure.hour * 60 + heure.minute) + Decimal(heure.second) / 60
    except (ValueError, InvalidOperation, TypeError):
        return None
    return None


def _depuis_unites(unites: int, colonne: Colonne) -> object:
    famille = colonne.famille
    if famille == "entier":
        return int(unites)
    if famille in ("decimal", "flottant", "monnaie"):
        return Decimal(unites).scaleb(-_echelle(colonne))
    if famille == "date":
        return _ORIGINE_DATE + timedelta(days=unites)
    if famille in ("horodatage", "horodatage_tz"):
        return _ORIGINE_HORODATAGE + timedelta(minutes=unites)
    return time(unites // 60, unites % 60)


def _bornes_unites(colonne: Colonne) -> tuple[int, int]:
    famille = colonne.famille
    if famille == "entier":
        return colonne.bornes_type or (-(2**63), 2**63 - 1)
    if famille == "decimal" and colonne.precision:
        limite = 10**colonne.precision - 1
        return -limite, limite
    if famille in ("decimal", "flottant", "monnaie"):
        return -(10**15), 10**15
    if famille == "date":
        return -(10**6), 10**6
    if famille in ("horodatage", "horodatage_tz"):
        return -(10**9), 10**9
    return 0, 24 * 60 - 1


def _depart(colonne: Colonne) -> int:
    famille = colonne.famille
    if famille == "date":
        return (JOUR_PIVOT - _ORIGINE_DATE).days
    if famille in ("horodatage", "horodatage_tz"):
        moment = datetime.combine(JOUR_PIVOT, time(9, 0))
        return int((moment - _ORIGINE_HORODATAGE).total_seconds() // 60)
    if famille in ("heure", "heure_tz"):
        return 9 * 60
    return 10 ** _echelle(colonne)


def _borne_basse(unites: Decimal, incluse: bool) -> int:
    plafond = int(unites.to_integral_value(rounding=ROUND_CEILING))
    return plafond if (incluse or plafond != unites) else plafond + 1


def _borne_haute(unites: Decimal, incluse: bool) -> int:
    plancher = int(unites.to_integral_value(rounding=ROUND_FLOOR))
    return plancher if (incluse or plancher != unites) else plancher - 1


def _dans_intervalle(
    bas: int, haut: int, depart: int, avec_bas: bool, avec_haut: bool, domaine: _Domaine,
    exclus: set[int], rang: int, seule: bool, tirage: _Tirage, etat: dict, limites: list[str],
    nom: str,
) -> int | None:
    if bas > haut:
        return None
    fenetre = 1000
    debut = min(max(depart, bas), max(bas, haut - fenetre + 1))
    fin = min(haut, debut + fenetre - 1)
    if seule:
        valeur = etat.get("suivant", debut)
        while valeur in exclus and valeur <= haut:
            valeur += 1
        if valeur > haut:
            return None
        etat["suivant"] = valeur + 1
        return valeur
    libre = not domaine.contrainte
    if rang == 0 and libre and avec_bas and bas not in exclus:
        limites.append(f"{nom} : borne basse")
        return bas
    if rang == 2 and libre and avec_haut and haut not in exclus:
        limites.append(f"{nom} : borne haute")
        return haut
    for _ in range(20):
        valeur = debut + tirage.entier(fin - debut + 1)
        if valeur not in exclus:
            return valeur
    return None


def _numerique(colonne: Colonne, domaine: _Domaine, rang: int, seule: bool, tirage: _Tirage,
               etat: dict, limites: list[str]) -> object:
    bas, haut = _bornes_unites(colonne)
    avec_bas = avec_haut = False
    for valeur, incluse in domaine.basses:
        unites = _vers_unites(valeur, colonne)
        if unites is not None:
            bas, avec_bas = max(bas, _borne_basse(unites, incluse)), True
    for valeur, incluse in domaine.hautes:
        unites = _vers_unites(valeur, colonne)
        if unites is not None:
            haut, avec_haut = min(haut, _borne_haute(unites, incluse)), True
    exclus: set[int] = set()
    for valeur in domaine.exclus:
        unites = _vers_unites(valeur, colonne)
        if unites is not None and unites == unites.to_integral_value():
            exclus.add(int(unites))
    if domaine.permis is not None:
        candidats: list[int] = []
        for valeur in domaine.permis:
            unites = _vers_unites(valeur, colonne)
            if unites is None or unites != unites.to_integral_value():
                continue
            if bas <= int(unites) <= haut and int(unites) not in exclus | set(candidats):
                candidats.append(int(unites))
        choisi = _parmi(candidats, rang, seule, tirage, etat)
        return choisi if choisi is IMPOSSIBLE else _depuis_unites(choisi, colonne)
    choisi = _dans_intervalle(bas, haut, _depart(colonne), avec_bas, avec_haut, domaine, exclus,
                              rang, seule, tirage, etat, limites, colonne.nom)
    return IMPOSSIBLE if choisi is None else _depuis_unites(choisi, colonne)


def _est_courriel(nom: str) -> bool:
    return "mail" in nom or "courriel" in nom


def _est_adresse_web(nom: str) -> bool:
    return nom in ("url", "uri", "site", "site_web", "lien", "website") or nom.endswith(
        ("_url", "_uri", "_lien")
    )


def _texte_compose(colonne: Colonne, domaine: _Domaine, n: int, marque: bool,
                   tirage: _Tirage) -> str:
    nom = colonne.nom.lower()
    if _est_courriel(nom):
        prenom, famille = tirage.choix(_jeux._PRENOMS), tirage.choix(_jeux._NOMS)
        courriel = _ascii(f"{prenom}.{famille}.{n}@{_jeux.DOMAINE}").lower()
        if domaine.long_max is not None and len(courriel) > domaine.long_max:
            courriel = f"u{n}@{_jeux.DOMAINE}"
        return courriel
    if _est_adresse_web(nom):
        libelle = _ascii(tirage.choix(_jeux._LIBELLES)).lower()
        return f"https://www.{_jeux.DOMAINE}/{libelle}-{n}"
    if "prenom" in nom or nom in ("first_name", "firstname", "given_name"):
        base = tirage.choix(_jeux._PRENOMS)
    elif nom in ("nom_complet", "nom_affiche", "full_name", "fullname", "display_name"):
        base = f"{tirage.choix(_jeux._PRENOMS)} {tirage.choix(_jeux._NOMS)}"
    else:
        base = tirage.choix(_jeux._LIBELLES)
    return f"{base} {n:04d}" if marque else base


def _texte(colonne: Colonne, domaine: _Domaine, rang: int, seule: bool, marque: bool,
           tirage: _Tirage, etat: dict, limites: list[str]) -> object:
    if domaine.permis is not None:
        candidats = [str(v) for v in domaine.permis if not isinstance(v, bool)
                     and str(v) not in domaine.exclus
                     and domaine.long_min <= len(str(v)) <= (domaine.long_max or len(str(v)))]
        return _parmi(candidats, rang, seule, tirage, etat)
    n = etat["n"] = etat.get("n", 0) + 1
    texte = _texte_compose(colonne, domaine, n, seule or marque, tirage)
    adresse = "@" in texte or texte.startswith("https://")
    if domaine.long_max is not None and len(texte) > domaine.long_max:
        suffixe = _base36(n)
        if len(suffixe) > domaine.long_max:
            if seule:
                return IMPOSSIBLE
            texte = texte[: domaine.long_max]
        else:
            # Plus de forme de courriel ni d adresse : tronquer `…@exemple.test` en fabriquerait
            # une sous un domaine NON réservé, que le garde-fou refuserait à raison.
            texte = (texte.split("@")[0].replace("https://", "") if adresse else texte)
            texte = texte[: domaine.long_max - len(suffixe)] + suffixe
            adresse = False
    elif (rang == 0 and not seule and not adresse and not domaine.contrainte
          and domaine.long_max is not None and domaine.long_max <= 255):
        texte = texte.ljust(domaine.long_max, "x")
        limites.append(f"{colonne.nom} : longueur maximale ({domaine.long_max})")
    if len(texte) < domaine.long_min:
        texte = texte + "x" * (domaine.long_min - len(texte))
    if texte in domaine.exclus:
        # Un libellé nu qu une liste exclut (`NOT IN ('Alpha')`) reprend son numéro de rang.
        texte = f"{texte} {n:04d}"
    if domaine.long_max is not None and len(texte) > domaine.long_max:
        return IMPOSSIBLE
    return IMPOSSIBLE if texte in domaine.exclus else texte


def _autre(colonne: Colonne, domaine: _Domaine, rang: int, seule: bool, tirage: _Tirage,
           etat: dict, position: int) -> object:
    """Familles sans ordre utile : booléen, énuméré, uuid, json, binaire, réseau, durée…"""
    famille = colonne.famille
    if famille == "booleen":
        permis = domaine.permis if domaine.permis is not None else [False, True]
        candidats = [v for v in (False, True) if v in permis and v not in domaine.exclus]
        return _parmi(candidats, rang, seule, tirage, etat)
    if famille == "enum":
        candidats = [v for v in (domaine.permis or []) if v not in domaine.exclus]
        return _parmi(candidats, rang, seule, tirage, etat)
    if domaine.permis is not None:
        return _parmi([str(v) for v in domaine.permis if str(v) not in domaine.exclus], rang,
                      seule, tirage, etat)
    n = etat["n"] = etat.get("n", 0) + 1
    if famille == "uuid":
        return f"00000000-0000-4000-8000-{position & 0xFFFF:04x}{n & 0xFFFFFFFF:08x}"
    if famille == "json":
        return json.dumps({"rang": n, "libelle": tirage.choix(_jeux._LIBELLES)},
                          ensure_ascii=False)
    if famille == "binaire":
        return f"\\x{n & 0xFFFFFFFF:08x}"
    if famille == "reseau":
        return f"2001:db8::{n:x}" if seule else f"192.0.2.{1 + tirage.entier(254)}"
    if famille == "cidr":
        return f"2001:db8:{n:x}::/48" if seule else "192.0.2.0/24"
    if famille == "mac":
        return f"02:00:00:00:{(n >> 8) & 0xFF:02x}:{n & 0xFF:02x}"
    if famille == "duree":
        return f"{n} days" if seule else f"{1 + tirage.entier(30)} days"
    if famille == "tableau":
        if colonne.bornes_type:
            return "{" + str(n) + "}"
        if colonne.type_sql in ("text", "varchar", "character", "char", "citext"):
            return '{"' + tirage.choix(_jeux._LIBELLES) + f' {n:04d}"' + "}"
        return "{}"
    # Type non reconnu : un libellé, et c est le chargement réel qui dira s il est admis.
    return f"{tirage.choix(_jeux._LIBELLES)} {n:04d}"


def _valeur(colonne: Colonne, domaine: _Domaine, rang: int, seule: bool, marque: bool,
            tirage: _Tirage, etat: dict, position: int, limites: list[str]) -> object:
    if colonne.famille in _NUMERIQUES:
        return _numerique(colonne, domaine, rang, seule, tirage, etat, limites)
    if colonne.famille == "texte":
        return _texte(colonne, domaine, rang, seule, marque, tirage, etat, limites)
    return _autre(colonne, domaine, rang, seule, tirage, etat, position)


# --- Rendu SQL ----------------------------------------------------------------------------------


def _chaine(texte: str) -> str:
    if any(ord(c) < 32 for c in texte):
        echappe = "".join(
            {"\n": "\\n", "\t": "\\t", "\r": "\\r", "\\": "\\\\", "'": "''"}.get(c)
            or (f"\\x{ord(c):02x}" if ord(c) < 32 else c)
            for c in texte
        )
        return f"E'{echappe}'"
    return "'" + texte.replace("'", "''") + "'"


def rendre(valeur: object, colonne: Colonne) -> str:
    """Littéral SQL d une valeur du jeu, selon la famille de sa colonne."""
    if valeur is None:
        return "NULL"
    if isinstance(valeur, bool):
        return "TRUE" if valeur else "FALSE"
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, Decimal):
        texte = format(valeur, "f")
        return _chaine(texte) if colonne.famille == "monnaie" else texte
    if isinstance(valeur, datetime):
        fuseau = "+00" if colonne.famille == "horodatage_tz" else ""
        return _chaine(valeur.isoformat(sep=" ") + fuseau)
    if isinstance(valeur, date):
        return _chaine(valeur.isoformat())
    if isinstance(valeur, time):
        return _chaine(valeur.isoformat() + ("+00" if colonne.famille == "heure_tz" else ""))
    return _chaine(str(valeur))


# --- Ordre et liens -----------------------------------------------------------------------------


def _cles_primaires(table: Table) -> tuple[str, ...]:
    return next((u.colonnes for u in table.unicites if u.primaire), ())


def ordonner(schema: Schema) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """(ordre des tables, clés rompues (table, contrainte) mises à NULL, notes).

    Parents d abord. Un cycle se rompt sur une clé dont toutes les colonnes admettent NULL ; un
    cycle sans telle clé est DIT, et ses tables suivent l ordre des migrations.
    """
    rompues: set[tuple[str, str]] = set()
    notes: list[str] = []
    ordre: list[str] = []
    restantes = list(schema.tables)
    while restantes:
        def parents(nom: str) -> set[str]:
            return {c.table_cible for c in schema.tables[nom].cles_etrangeres
                    if c.table_cible in schema.tables and c.table_cible != nom
                    and (nom, c.nom) not in rompues}

        pretes = [nom for nom in restantes if parents(nom) <= set(ordre)]
        if pretes:
            for nom in pretes:
                ordre.append(nom)
                restantes.remove(nom)
            continue
        candidate = next(
            ((nom, cle) for nom in restantes for cle in schema.tables[nom].cles_etrangeres
             if cle.table_cible in restantes and cle.table_cible != nom
             and (nom, cle.nom) not in rompues
             and all(not schema.tables[nom].colonnes[c].non_nul for c in cle.colonnes
                     if c in schema.tables[nom].colonnes)),
            None,
        )
        if candidate is None:
            notes.append("cycle de clés étrangères sans colonne nullable entre "
                         + ", ".join(restantes) + " : non résolu, ces tables suivent l ordre "
                         "des migrations et leurs lignes sans parent manqueront au volume")
            ordre.extend(restantes)
            break
        nom, cle = candidate
        rompues.add((nom, cle.nom))
        notes.append(f"cycle de clés étrangères rompu sur {nom}.{cle.nom} : ses colonnes "
                     f"({', '.join(cle.colonnes)}) restent NULL dans le jeu")
    return ordre, sorted(rompues), notes


@dataclass
class _Lien:
    cle: schema_sql.CleEtrangere
    parent: str
    cibles: tuple[str, ...]
    biunivoque: bool
    nullable: bool
    rompue: bool
    connue: bool


def _liens(table: Table, schema: Schema, rompues: set[tuple[str, str]],
           notes: list[str]) -> list[_Lien]:
    liens: list[_Lien] = []
    for cle in table.cles_etrangeres:
        parent = schema.tables.get(cle.table_cible)
        cibles = cle.colonnes_cibles or (_cles_primaires(parent) if parent else ())
        connue = parent is not None and len(cibles) == len(cle.colonnes)
        if not connue:
            notes.append(f"{cle.nom} : table ou colonnes visées inconnues du schéma lu "
                         f"({cle.table_cible}) — la clé ne peut pas être semée")
        nullable = all(c in table.colonnes and not table.colonnes[c].non_nul
                       for c in cle.colonnes)
        biunivoque = any(set(u.colonnes) <= set(cle.colonnes) for u in table.unicites
                         if not u.expression)
        liens.append(_Lien(cle, cle.table_cible, tuple(cibles), biunivoque, nullable,
                           (table.nom, cle.nom) in rompues, connue))
    return liens


def _relier(ligne: dict, lien: _Lien, etat: dict, tirage: _Tirage, parents: list[dict]) -> bool:
    """Copie dans `ligne` les valeurs visées d une ligne parente ; faux si aucune ne convient."""
    if lien.rompue or not lien.connue:
        if not lien.nullable:
            return False
        for colonne in lien.cle.colonnes:
            ligne[colonne] = None
        return True
    utilisables = [p for p in parents if all(p.get(c) is not None for c in lien.cibles)]
    if not utilisables:
        if not lien.nullable:
            return False
        for colonne in lien.cle.colonnes:
            ligne[colonne] = None
        return True
    if lien.biunivoque:
        indice = etat.get("suivant", 0)
        if indice >= len(utilisables):
            if not lien.nullable:
                return False
            for colonne in lien.cle.colonnes:
                ligne[colonne] = None
            return True
        etat["suivant"] = indice + 1
        parent = utilisables[indice]
    else:
        parent = utilisables[tirage.entier(len(utilisables))]
    for colonne, cible in zip(lien.cle.colonnes, lien.cibles, strict=True):
        ligne[colonne] = parent[cible]
    return True


def _cle_unicite(ligne: dict, unicite: schema_sql.Unicite) -> tuple | None:
    valeurs = []
    for colonne in unicite.colonnes:
        valeur = ligne.get(colonne)
        if valeur is None and unicite.nulls_distincts:
            return None
        if unicite.expression and isinstance(valeur, str):
            valeur = valeur.lower()
        valeurs.append(valeur)
    return tuple(valeurs)


_GROUPES = {"entier": "nombre", "decimal": "nombre", "flottant": "nombre", "monnaie": "nombre",
            "date": "date", "horodatage": "moment", "horodatage_tz": "moment",
            "heure": "heure", "heure_tz": "heure"}


def _comparable(valeur: object, groupe: str) -> object:
    return Decimal(str(valeur)) if groupe == "nombre" else valeur


def _decaler(reference: object, colonne: Colonne, vers_le_haut: bool, strict: bool) -> object:
    """La valeur la plus proche de `reference` qui la dépasse (ou l égale) dans le bon sens."""
    groupe = _GROUPES[colonne.famille]
    signe = 1 if vers_le_haut else -1
    if groupe == "nombre":
        pas = Decimal(1).scaleb(-_echelle(colonne))
        brut = Decimal(str(reference)) + (signe * pas if strict else 0)
        arrondi = brut.quantize(pas, rounding=ROUND_CEILING if vers_le_haut else ROUND_FLOOR)
        return int(arrondi) if colonne.famille == "entier" else arrondi
    if groupe == "date":
        return reference + timedelta(days=signe if strict else 0)
    if groupe == "moment":
        return reference + timedelta(hours=signe if strict else 0)
    minutes = reference.hour * 60 + reference.minute + (signe if strict else 0)
    return time(minutes // 60, minutes % 60) if 0 <= minutes < 24 * 60 else reference


def _tenir_relation(ligne: dict, relation: schema_sql.Effet, table: Table,
                    figees: set[str]) -> None:
    """`a >= b` : si l ordre est faux, la colonne libre est recalée sur l autre."""
    a, b, operateur = relation.colonne, relation.autre or "", relation.operateur or ""
    va, vb = ligne.get(a), ligne.get(b)
    if va is None or vb is None or a not in table.colonnes or b not in table.colonnes:
        return
    colonne_a, colonne_b = table.colonnes[a], table.colonnes[b]
    groupe = _GROUPES.get(colonne_a.famille)
    if groupe is None or groupe != _GROUPES.get(colonne_b.famille):
        return
    xa, xb = _comparable(va, groupe), _comparable(vb, groupe)
    tenue = {"<": xa < xb, "<=": xa <= xb, ">": xa > xb, ">=": xa >= xb}.get(operateur, True)
    if tenue:
        return
    strict, au_dessus = operateur in ("<", ">"), operateur.startswith(">")
    if a not in figees:
        ligne[a] = _decaler(vb, colonne_a, au_dessus, strict)
    elif b not in figees:
        ligne[b] = _decaler(va, colonne_b, not au_dessus, strict)


# --- Fabrication --------------------------------------------------------------------------------


@dataclass
class TableProduite:
    table: Table
    volume_demande: int
    colonnes: list[str]
    lignes: list[dict]
    ecarts: dict[str, int] = field(default_factory=dict)
    cas_limites: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Jeu:
    schema: Schema
    graine: int
    volume: int
    volumes: dict[str, int]
    ordre: list[str]
    tables: dict[str, TableProduite]
    notes: list[str]
    provenances: dict[tuple[str, str], str]

    def valeurs_a_verifier(self) -> dict[str, list[dict[str, str]]]:
        """Toutes les valeurs du jeu, sous leur forme textuelle, pour le garde-fou."""
        return {
            nom: [{c: str(v) for c, v in ligne.items() if v is not None}
                  for ligne in produite.lignes]
            for nom, produite in self.tables.items()
        }

    def attendues(self) -> dict[str, int]:
        return {p.table.nom_sql: len(p.lignes) for p in self.tables.values() if p.lignes}

    def texte(self) -> str:
        """Le fichier SQL : une instruction par ligne, rejouable par `psql -f`."""
        declares = ", ".join(f"{t}={n}" for t, n in sorted(self.volumes.items())) or "aucun"
        lignes = [
            "-- Jeu de données SYNTHÉTIQUE — Forge Tests, fabrique de données (TF-2012)",
            "-- Aucune valeur ne vient d une base réelle : vocabulaire fermé de "
            "forge_tests/livrables/jeux.py,",
            f"-- courriels sous {_jeux.DOMAINE} (RFC 6761), seules valeurs reprises du projet : "
            "celles que son schéma impose",
            "-- (CHECK … IN, type énuméré). Chaque valeur a passé le garde-fou de jeux.py avant "
            "l écriture de ce fichier.",
            f"-- graine : {self.graine} · volume par défaut : {self.volume} · volumes déclarés : "
            f"{declares}",
            f"-- migrations lues : {', '.join(self.schema.migrations)}",
            f"-- ordre des tables (clés étrangères d abord) : {', '.join(self.ordre)}",
            "-- rejouer : psql -v ON_ERROR_STOP=1 -f <ce fichier>, sur une base où les "
            "migrations Up sont appliquées",
            "BEGIN;",
        ]
        for nom in self.ordre:
            produite = self.tables[nom]
            table = produite.table
            lignes.append(f"-- {nom} : {len(produite.lignes)} ligne(s) sur "
                          f"{produite.volume_demande} demandée(s)")
            if not produite.lignes:
                continue
            noms = ", ".join(citer(c) for c in produite.colonnes)
            surcharge = (" OVERRIDING SYSTEM VALUE" if any(
                table.colonnes[c].auto == "identite_toujours" for c in produite.colonnes)
                else "")
            for ligne in produite.lignes:
                valeurs = ", ".join(rendre(ligne.get(c), table.colonnes[c])
                                    for c in produite.colonnes)
                lignes.append(f"INSERT INTO {table.nom_sql} ({noms}){surcharge} "
                              f"VALUES ({valeurs});")
            for colonne in produite.colonnes:
                definition = table.colonnes[colonne]
                if definition.auto and definition.famille == "entier":
                    lignes.append(
                        f"SELECT setval(pg_get_serial_sequence({_chaine(table.nom_sql)}, "
                        f"{_chaine(colonne)}), (SELECT max({citer(colonne)}) FROM "
                        f"{table.nom_sql}));"
                    )
        lignes.append("COMMIT;")
        return "\n".join(lignes) + "\n"


def _fabriquer_table(schema: Schema, table: Table, position: int, graine: int, volume: int,
                     produites: dict[str, TableProduite], rompues: set[tuple[str, str]],
                     visees: set[str]) -> TableProduite:
    tirage = _Tirage(graine, table.nom)
    domaines, relations = _domaines(table, schema)
    notes: list[str] = []
    liens = _liens(table, schema, rompues, notes)
    colonnes = [c.nom for c in table.colonnes.values() if not c.generee]
    reliees = {c for lien in liens for c in lien.cle.colonnes}
    seules = {u.colonnes[0] for u in table.unicites if len(u.colonnes) == 1}
    composees = {c for u in table.unicites if len(u.colonnes) > 1 for c in u.colonnes}
    primaires = set(_cles_primaires(table))
    non_distinctes = {c for u in table.unicites if not u.nulls_distincts for c in u.colonnes}
    nullables = {
        nom for nom in colonnes
        if not table.colonnes[nom].non_nul and not domaines[nom].non_nul
        and not domaines[nom].contrainte and nom not in primaires and nom not in visees
        and nom not in non_distinctes
    }
    # Les NULL de la deuxième ligne : colonnes libres qui l admettent, et clés étrangères dont
    # TOUTES les colonnes l admettent (une clé à moitié nulle n est pas un cas limite, c est un
    # rejet sous MATCH FULL).
    nulles = sorted(nullables - reliees) + [
        c for lien in liens if all(x in nullables for x in lien.cle.colonnes)
        for c in lien.cle.colonnes
    ]
    figees = reliees | seules | {n for n, d in domaines.items() if d.permis is not None}
    etats: dict[str, dict] = {nom: {} for nom in colonnes}
    etats_liens: list[dict] = [{} for _ in liens]
    vus: list[set] = [set() for _ in table.unicites]
    lignes: list[dict] = []
    ecarts: dict[str, int] = {}
    limites: list[str] = []
    for rang in range(volume):
        retenue: dict | None = None
        motif = ""
        for _essai in range(ESSAIS_PAR_LIGNE):
            ligne: dict = {}
            motif = ""
            for nom in colonnes:
                if nom in reliees:
                    continue
                valeur = _valeur(table.colonnes[nom], domaines[nom], rang, nom in seules,
                                 nom in composees, tirage, etats[nom], position, limites)
                if valeur is IMPOSSIBLE:
                    motif = (f"{nom} : aucune valeur admise ne reste (domaine épuisé ou "
                             "contradictoire)")
                    break
                ligne[nom] = valeur
            if motif:
                break
            for lien, etat in zip(liens, etats_liens, strict=True):
                parents = (lignes + [ligne]) if lien.parent == table.nom else (
                    produites[lien.parent].lignes if lien.parent in produites else []
                )
                if not _relier(ligne, lien, etat, tirage, parents):
                    motif = f"{lien.cle.nom} : aucune ligne parente disponible dans {lien.parent}"
                    break
            if motif:
                break
            if rang == 1:
                for nom in nulles:
                    ligne[nom] = None
            for relation in relations:
                _tenir_relation(ligne, relation, table, figees)
            cles = [_cle_unicite(ligne, u) for u in table.unicites]
            conflit = next((u.nom for u, cle, vu in zip(table.unicites, cles, vus, strict=True)
                            if cle is not None and cle in vu), None)
            if conflit is None:
                retenue = ligne
                for cle, vu in zip(cles, vus, strict=True):
                    if cle is not None:
                        vu.add(cle)
                break
            motif = f"unicité {conflit} non tenue après {ESSAIS_PAR_LIGNE} essais"
        if retenue is None:
            ecarts[motif] = ecarts.get(motif, 0) + 1
            continue
        lignes.append(retenue)
    if volume >= 2 and nulles:
        limites.append("NULL dans les colonnes qui l admettent : " + ", ".join(nulles))
    for nom in colonnes:
        if table.colonnes[nom].famille == "inconnu":
            notes.append(f"{nom} : type non reconnu ({table.colonnes[nom].type_sql}) — valeur "
                         "texte, le chargement réel dira si elle est admise")
    vus_limites: list[str] = []
    for limite in limites:
        if limite not in vus_limites:
            vus_limites.append(limite)
    return TableProduite(table, volume, colonnes, lignes, ecarts, vus_limites, notes)


def fabriquer(schema: Schema, graine: int = GRAINE_DEFAUT, volume: int = VOLUME_DEFAUT,
              volumes: dict[str, int] | None = None) -> Jeu:
    """Le jeu complet, déterministe pour (schéma, graine, volumes). N écrit rien."""
    volumes = dict(volumes or {})
    if graine < 0 or volume < 0 or any(n < 0 for n in volumes.values()):
        raise ValueError("la graine et les volumes sont des entiers positifs ou nuls")
    inconnues = sorted(set(volumes) - set(schema.tables))
    if inconnues:
        raise ValueError(
            f"table(s) inconnue(s) du schéma lu : {', '.join(inconnues)} — tables lues : "
            f"{', '.join(schema.tables) or 'aucune'}"
        )
    ordre, rompues, notes = ordonner(schema)
    visees: dict[str, set[str]] = {nom: set() for nom in schema.tables}
    for table in schema.tables.values():
        for cle in table.cles_etrangeres:
            parent = schema.tables.get(cle.table_cible)
            if parent is not None:
                visees[parent.nom].update(cle.colonnes_cibles or _cles_primaires(parent))
    produites: dict[str, TableProduite] = {}
    for position, nom in enumerate(ordre):
        produites[nom] = _fabriquer_table(schema, schema.tables[nom], position, graine,
                                          volumes.get(nom, volume), produites, set(rompues),
                                          visees[nom])
    provenances: dict[tuple[str, str], str] = {}
    for table in schema.tables.values():
        for nom, colonne in table.colonnes.items():
            if colonne.enum:
                provenances[(table.nom, nom)] = f"type énuméré {colonne.enum}"
        for verification in table.verifications:
            for effet in verification.effets:
                if effet.genre == "permis":
                    provenances[(table.nom, effet.colonne)] = (
                        f"vérification {verification.nom} ({verification.expression})"
                    )
    return Jeu(schema, graine, volume, volumes, ordre, produites, notes, provenances)


def verifier_synthetique(jeu: Jeu, cible: Path | None) -> int:
    """Garde-fou de `jeux.py` sur CHAQUE valeur ; lève `DonneeNonSynthetique`, rend le compte."""
    valeurs = jeu.valeurs_a_verifier()
    try:
        _jeux.verifier(valeurs, cible)
    except _jeux.DonneeNonSynthetique as refus:
        trouve = re.match(r"\.([^\[]+)\[\d+\]\.(.+?) : ", str(refus))
        provenance = jeu.provenances.get((trouve.group(1), trouve.group(2))) if trouve else None
        if provenance is None:
            raise
        raise _jeux.DonneeNonSynthetique(
            f"{refus} — valeur IMPOSÉE par le schéma du projet ({provenance}) : la fabrique "
            "ne peut que la reprendre, elle refuse donc le jeu entier"
        ) from refus
    return sum(len(ligne) for lignes in valeurs.values() for ligne in lignes)


# --- Chargement réel ----------------------------------------------------------------------------


def _interpretes(cible: Path, python: Path | None) -> list[Path]:
    if python is not None:
        return [Path(python)]
    candidats: list[Path] = []
    for candidat in (_execution._python(cible), Path(sys.executable)):
        if candidat is not None and candidat not in candidats:
            candidats.append(candidat)
    return candidats


def _jouer_sonde(cible: Path, interprete: Path, jeu: Path, migrations: list[Path],
                 tables: list[str], delai: int) -> dict:
    if not interprete.exists():
        return {"statut": "indisponible", "motif": "interpréteur introuvable",
                "interprete": str(interprete)}
    with tempfile.TemporaryDirectory(prefix="forge-fabrique-") as temporaire:
        dossier = Path(temporaire)
        constat, plan = dossier / "constat.json", dossier / "plan.json"
        plan.write_text(json.dumps({
            "migrations": [str(m) for m in migrations], "jeu": str(jeu), "tables": tables,
            "sortie": str(constat),
        }, ensure_ascii=False), encoding="utf-8")
        resultat = _execution._run(
            [str(interprete), str(SONDE), str(plan)],
            banc=cible, domaine="fabrique", quoi="chargement du jeu sur base PostgreSQL ephemere",
            remede="relancer avec moins de lignes (--volume)", cwd=dossier, timeout=delai,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
        )
        if resultat is None:
            return {"statut": "delai", "trace": _execution.motif_indisponibilite(
                cible, "fabrique", "chargement interrompu")}
        if constat.exists():
            return json.loads(constat.read_text(encoding="utf-8"))
        trace = f"{resultat.stdout or ''}\n{resultat.stderr or ''}"
        return {"statut": "panne", "trace": trace[-3000:], "code": resultat.returncode}


def _derniere_ligne(trace: str) -> str:
    return next((ligne.strip() for ligne in reversed((trace or "").splitlines())
                 if ligne.strip()), "aucune sortie")[:200]


def _verdict(constat: dict, attendues: dict[str, int], interprete: Path) -> dict:
    statut = constat.get("statut")
    base = {"interprete": str(interprete), "image": constat.get("image"),
            "postgres": constat.get("postgres")}
    if statut == "charge":
        erreurs = constat.get("erreurs") or []
        manquantes: list[str] = []
        for table, inserees in attendues.items():
            compte = (constat.get("lignes") or {}).get(table) or {}
            avant, apres = compte.get("avant"), compte.get("apres")
            if avant is None or apres is None:
                manquantes.append(f"{table} : comptage impossible après chargement")
            elif apres - avant < inserees:
                manquantes.append(f"{table} : {apres - avant} ligne(s) présente(s) sur "
                                  f"{inserees} insérée(s)")
        if erreurs or manquantes:
            nommees = sorted({e.get("contrainte") or e.get("sqlstate") or "?" for e in erreurs})
            motif = (f"{len(erreurs)} instruction(s) rejetée(s) par le moteur"
                     + (f" (contrainte(s) : {', '.join(nommees)})" if nommees else "")
                     + (f" ; lignes absentes : {' ; '.join(manquantes)}" if manquantes else ""))
            verdict = "FAIL"
        else:
            motif = (f"jeu chargé sur base PostgreSQL éphémère ({constat.get('postgres')}) : "
                     f"{constat.get('instructions')} instruction(s), 0 rejet, toutes les lignes "
                     "présentes")
            verdict = "PASS"
        return {**base, "verdict": verdict, "motif": motif,
                "instructions": constat.get("instructions"), "erreurs": erreurs,
                "lignes_absentes": manquantes, "lignes": constat.get("lignes")}
    if statut == "migrations":
        erreur = constat.get("erreur") or {}
        return {**base, "verdict": "ERREUR", "motif": (
            f"les migrations Up ne se rejouent pas sur base neuve — {constat.get('migration')}, "
            f"instruction {constat.get('rang')} ({erreur.get('sqlstate')}) : "
            f"{erreur.get('message')} — le jeu n est PAS jugé"), "constat": constat}
    trace = str(constat.get("trace") or constat.get("motif") or "")
    preuve = _execution.prealable_conteneur(trace)
    if preuve is not None:
        return {**base, "verdict": "NON_EXECUTABLE", "motif": (
            f"{_execution.PREALABLE_ABSENT} — demon de conteneurs INJOIGNABLE : la base "
            "ephemere n a pas pu etre montee, le jeu n est PAS juge. Demarrer le demon (Docker "
            f"Desktop), verifier `docker ps`, puis rejouer. Preuve lue dans la trace : {preuve}")}
    if statut in ("conteneur", "delai"):
        return {**base, "verdict": "NON_EXECUTABLE", "motif": (
            "la base ephemere n a pas pu etre montee ici, le jeu n est PAS juge : "
            f"{_derniere_ligne(trace)}")}
    return {**base, "verdict": "ERREUR", "motif": (
        f"la sonde de chargement a echoue (code {constat.get('code')}) : "
        f"{_derniere_ligne(trace)}")}


def charger(cible: Path, jeu: Path, migrations: list[Path], attendues: dict[str, int],
            python: Path | None = None, delai: int = DELAI_CHARGEMENT_S) -> dict:
    """Verdict du chargement RÉEL : PASS, FAIL, NON_EXECUTABLE ou ERREUR — avec ses preuves.

    L interpréteur qui monte la base est celui que l on désigne, sinon celui du projet (comme le
    rejeu des migrations du pan `migrations`), sinon celui de la forge. Le premier qui porte
    `testcontainers` et un pilote PostgreSQL joue ; s il n y en a aucun, rien n est jugé.
    """
    essais: list[str] = []
    for interprete in _interpretes(Path(cible), python):
        constat = _jouer_sonde(Path(cible), interprete, Path(jeu), migrations, list(attendues),
                               delai)
        if constat.get("statut") == "indisponible":
            essais.append(f"{interprete} : {constat.get('motif')}")
            continue
        return _verdict(constat, attendues, interprete)
    return {"verdict": "NON_EXECUTABLE", "interpretes_essayes": essais, "motif": (
        "aucun interpreteur equipe pour monter la base ephemere — "
        + " ; ".join(essais)
        + ". Installer `testcontainers[postgres]` et `psycopg[binary]` dans le venv du projet, "
        "ou designer un interpreteur equipe par --python ; le jeu n est PAS juge")}


# --- Production ---------------------------------------------------------------------------------


def _motif_sans_schema(cible: Path) -> str:
    alembic = _versions_alembic(cible)
    suite = (f" ; {len(alembic)} version(s) Alembic présente(s), que la fabrique ne lit pas "
             "(écart déclaré)" if alembic else "")
    return ("aucune migration SQL à lire (`<racine>/migrations/*.sql`, format `-- +migrate "
            f"Up` / `-- +migrate Down`) sous {cible}{suite} : la fabrique ne fabrique pas sans "
            "schéma, elle n en invente pas")


def produire(cible: Path, sortie: Path, graine: int = GRAINE_DEFAUT,
             volume: int = VOLUME_DEFAUT, volumes: dict[str, int] | None = None,
             chargement: bool = True, python: Path | None = None) -> dict:
    """Lit le schéma, fabrique, vérifie, écrit `sortie`, juge par chargement réel. Rend le rapport.

    Lève `DepotInterdit` (sortie dans le projet, G-1), `SchemaIntrouvable`, `ValueError`
    (volumes) et `DonneeNonSynthetique` (garde-fou) AVANT d écrire quoi que ce soit.
    """
    cible, sortie = Path(cible).resolve(), Path(sortie).resolve()
    _verifier_hors_projet(sortie.parent, cible)
    schema = schema_sql.lire(cible)
    if not schema.migrations:
        raise SchemaIntrouvable(_motif_sans_schema(cible))
    if not schema.tables:
        raise SchemaIntrouvable(f"{len(schema.migrations)} migration(s) lue(s), aucune table "
                                "créée : rien à fabriquer")
    jeu = fabriquer(schema, graine, volume, volumes)
    verifiees = verifier_synthetique(jeu, cible)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(jeu.texte(), encoding="utf-8", newline="\n")
    rapport = rapporter(jeu, cible, sortie, verifiees)
    if not chargement:
        rapport.update(verdict="NON_JUGE", motif=(
            "chargement non demande (--sans-chargement) : le jeu est ecrit, il n est PAS juge"))
        return rapport
    print("fabrique : chargement du jeu sur base PostgreSQL ephemere (testcontainers)…",
          file=sys.stderr)
    rapport["chargement"] = charger(cible, sortie, _fichiers(cible), jeu.attendues(), python)
    verdict = rapport["chargement"]["verdict"]
    motif = rapport["chargement"]["motif"]
    incomplets = [t for t in rapport["tables"] if t["lignes"] < t["volume_demande"]]
    if verdict == "PASS" and incomplets:
        verdict = "PARTIEL"
        motif += " ; volume non tenu pour " + ", ".join(
            f"{t['table']} ({t['lignes']}/{t['volume_demande']})" for t in incomplets)
    rapport.update(verdict=verdict, motif=motif)
    return rapport


def rapporter(jeu: Jeu, cible: Path, sortie: Path, verifiees: int) -> dict:
    schema = jeu.schema
    return {
        "outil": "forge-tests · fabrique de donnees (TF-2012)",
        "verdict": None,
        "motif": None,
        "cible": str(cible),
        "jeu": str(sortie),
        "graine": jeu.graine,
        "volume_defaut": jeu.volume,
        "volumes": dict(sorted(jeu.volumes.items())),
        "migrations": list(schema.migrations),
        "ordre": list(jeu.ordre),
        "garde_fou": f"jeux.verifier : {verifiees} valeur(s) relue(s) avant ecriture, aucun refus",
        "tables": [
            {"table": nom, "volume_demande": p.volume_demande, "lignes": len(p.lignes),
             "ecarts": dict(sorted(p.ecarts.items())), "cas_limites": p.cas_limites,
             "notes": p.notes}
            for nom, p in ((n, jeu.tables[n]) for n in jeu.ordre)
        ],
        "verifications_non_interpretees": [
            {"table": t.nom, "contrainte": v.nom, "expression": v.expression,
             "interpretee": v.interpretee}
            for t in schema.tables.values() for v in t.verifications if v.interpretee != "oui"
        ],
        "instructions_non_modelisees": dict(sorted(schema.non_modelisees.items())),
        "notes": list(schema.notes) + list(jeu.notes),
        "chargement": None,
        "non_juge": [*NON_JUGE, *schema_sql.NON_JUGE],
    }


# --- CLI ----------------------------------------------------------------------------------------


def _resume(rapport: dict, debut: _dt.datetime) -> str:
    fin = _dt.datetime.now().astimezone()
    duree = (fin - debut).total_seconds()
    lignes = [
        f"forge-tests · fabrique de donnees · {rapport.get('cible') or ''}".rstrip(" ·"),
        f"termine le {fin.strftime('%Y-%m-%d a %Hh%M')} ({fin.tzname()}) · duree "
        f"{int(duree // 60)} min {int(duree % 60)} s",
        "",
        f"verdict : {rapport['verdict']} — {rapport['motif']}",
    ]
    if rapport.get("jeu"):
        lignes.append(f"jeu : {rapport['jeu']} (graine {rapport.get('graine')})")
    if rapport.get("tables"):
        lignes += ["", "tables, dans l ordre des cles etrangeres"]
        for table in rapport["tables"]:
            ecart = "" if table["lignes"] >= table["volume_demande"] else (
                " — " + " ; ".join(f"{m} ({n})" for m, n in table["ecarts"].items()))
            lignes.append(f"  {table['table']:<28} {table['lignes']:>5}/"
                          f"{table['volume_demande']:<5} ligne(s) fabriquee(s){ecart}")
            if table["cas_limites"]:
                lignes.append("      cas limites : " + " ; ".join(table["cas_limites"]))
        non_lues = rapport.get("verifications_non_interpretees") or []
        lignes.append("")
        lignes.append("verifications non interpretees (jugees par le seul chargement reel) : "
                      + ("aucune" if not non_lues else str(len(non_lues))))
        for verification in non_lues:
            lignes.append(f"  {verification['table']}.{verification['contrainte']} "
                          f"[{verification['interpretee']}] {verification['expression']}")
        modeles = rapport.get("instructions_non_modelisees") or {}
        lignes.append("instructions non modelisees : " + (", ".join(
            f"{nature} ({n})" for nature, n in modeles.items()) or "aucune"))
        for note in rapport.get("notes") or []:
            lignes.append(f"  note : {note}")
    chargement = rapport.get("chargement") or {}
    for erreur in (chargement.get("erreurs") or [])[:20]:
        lignes.append(f"  rejet ligne {erreur.get('ligne')} : {erreur.get('contrainte') or '-'} "
                      f"({erreur.get('sqlstate')}) {erreur.get('message')}")
    if len(chargement.get("erreurs") or []) > 20:
        lignes.append(f"  … {len(chargement['erreurs'])} rejets au total, les 20 premiers listés "
                      "(--json les porte tous)")
    return "\n".join(lignes)


def _volumes(valeurs: list[str] | None) -> dict[str, int]:
    volumes: dict[str, int] = {}
    for valeur in valeurs or []:
        table, egal, nombre = valeur.partition("=")
        if not egal or not nombre.strip().isdigit() or not table.strip():
            raise argparse.ArgumentTypeError(f"--volume-table attend TABLE=N, recu « {valeur} »")
        volumes[table.strip()] = int(nombre)
    return volumes


def _forcer_utf8() -> None:
    for flux in (sys.stdout, sys.stderr):
        reconfigurer = getattr(flux, "reconfigure", None)
        if reconfigurer is not None:
            reconfigurer(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _forcer_utf8()
    debut = _dt.datetime.now().astimezone()
    parser = argparse.ArgumentParser(
        prog="forge-tests fabrique",
        description=(
            "Fabrique un jeu de donnees SYNTHETIQUE et chargeable depuis les migrations SQL du "
            "projet, puis le juge par un chargement reel sur une base PostgreSQL ephemere."
        ),
    )
    parser.add_argument("cible", type=Path, help="racine du projet dont lire les migrations")
    parser.add_argument("--sortie", type=Path, required=True, metavar="FICHIER.sql",
                        help="fichier SQL a ecrire, HORS du projet (G-1)")
    parser.add_argument("--graine", type=int, default=GRAINE_DEFAUT,
                        help=f"graine des tirages (defaut {GRAINE_DEFAUT}) : meme graine, meme jeu")
    parser.add_argument("--volume", type=int, default=VOLUME_DEFAUT,
                        help=f"lignes par table (defaut {VOLUME_DEFAUT})")
    parser.add_argument("--volume-table", action="append", default=None, metavar="TABLE=N",
                        help="volume propre a une table (repetable)")
    parser.add_argument("--python", type=Path, default=None, metavar="INTERPRETE",
                        help="interpreteur portant testcontainers et psycopg (defaut : celui du "
                             "projet, puis celui de la forge)")
    parser.add_argument("--sans-chargement", action="store_true",
                        help="ecrire le jeu sans le juger (verdict NON_JUGE, code 3)")
    parser.add_argument("--json", action="store_true", help="rapport machine complet")
    args = parser.parse_args(argv)
    try:
        volumes = _volumes(args.volume_table)
    except argparse.ArgumentTypeError as erreur:
        parser.error(str(erreur))

    def publier(rapport: dict) -> int:
        sys.stderr.flush()
        print(json.dumps(rapport, ensure_ascii=False, indent=2) if args.json
              else _resume(rapport, debut))
        return _CODES.get(rapport["verdict"], SORTIE_ERREUR)

    try:
        rapport = produire(args.cible, args.sortie, args.graine, args.volume, volumes,
                           chargement=not args.sans_chargement, python=args.python)
    except DepotInterdit as refus:
        sys.stdout.flush()
        print(f"G-1 : jeu HORS projet requis — chemin recu : {args.sortie}\n{refus}",
              file=sys.stderr)
        return publier({"verdict": "REFUS_G1", "motif": str(refus), "cible": str(args.cible)})
    except _jeux.DonneeNonSynthetique as refus:
        return publier({"verdict": "REFUSE", "cible": str(args.cible), "motif": (
            f"garde-fou de jeux.py : {refus} — RIEN n est ecrit")})
    except (SchemaIntrouvable, ValueError) as erreur:
        return publier({"verdict": "ERREUR", "motif": str(erreur), "cible": str(args.cible)})
    return publier(rapport)


if __name__ == "__main__":
    raise SystemExit(main())
