"""Adaptateur parcours-personas — un parcours de bout en bout PAR persona déclaré (TF-2123).

Fait remonté (lot Produit-86 du 03/11/2026) : les parcours de bout en bout par profil ont dû être
écrits par la session à la demande du porteur. Aucun pan ne les exigeait : un produit qui déclare
des personas pouvait passer l audit avec une suite qui ne joue qu une identité, ou aucun parcours.

Ce pan lit deux choses, SANS EXÉCUTION et sans réseau :

  - **les personas ou rôles que le produit DÉCLARE** — jamais devinés. Trois sources, réunies :
    les clés `personas` et `roles` de `EXIGENCES.json` (chemin de `FORGE_TESTS_EXIGENCES`, sinon
    `EXIGENCES.json`, `forge/EXIGENCES.json` ou `forge/etapes/conception/EXIGENCES.json`), les
    `profils` de `forge/matrice-droits.json`, et les comptes de test par rôle de
    `FORGE_TESTS_QUALIF_STORAGE_STATES` (`role=chemin`, virgules). Un élément `persona:<clé>` par
    persona, qui porte ses sources ;
  - **les parcours de bout en bout** : un fichier de test qui PILOTE UN NAVIGATEUR (Playwright,
    Cypress, Selenium, Puppeteer), navigue (`goto`, `cy.visit`…) et CITE le persona, par son nom
    de fichier ou dans son texte. Un persona qu aucun parcours ne cite est `non exercé` : un
    FAIL nommé, avec le persona.

CE QUE CE PAN NE FAIT PAS, et il le dit à chaque rapport (`non_juge`) : il ne JOUE aucun
parcours. Jouer un parcours par persona contre l instance servie exige une identité par rôle, une
instance peuplée et un navigateur : c est le volet `qualif` multi-sessions (TF-0316) et la suite
du projet, pas une lecture de sources. Un persona « exercé » ici signifie « un parcours de bout en
bout le cite », pas « ce parcours passe ». Le reste de TF-2123 (le jeu contre l instance servie)
reste ouvert et n est pas simulé.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from forge_tests import droits, exclusions
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "parcours-personas", "parcours-personas", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publié tel quel au rapport.
POUR_COUVRIR = (
    "écrire, pour chaque persona ou rôle déclaré (clés `personas` ou `roles` d EXIGENCES.json, "
    "`profils` de forge/matrice-droits.json, comptes de FORGE_TESTS_QUALIF_STORAGE_STATES), au "
    "moins un test de bout en bout qui pilote un navigateur, navigue, et nomme ce persona dans son "
    "nom de fichier ou son texte ; puis le jouer contre l instance servie sous l identité du rôle"
)

# Chapitre de cahier que ce pan alimente, DÉRIVÉ du registre par le cahier et le dashboard.
CHAPITRES = (
    {"code": "F7", "famille": "fonctionnel", "titre": "Parcours par persona",
     "decoupe": "persona", "axe_cas": "unitaire"},
)

NON_JUGE = [
    "parcours-personas : statique — un persona est tenu pour exercé quand un fichier de test de "
    "bout en bout (navigateur piloté, navigation) le CITE par son nom de fichier ou dans son "
    "texte ; ce pan ne joue aucun parcours et ne prouve pas qu un parcours cité passe",
    "parcours-personas : le jeu de chaque parcours contre l instance servie, sous l identité du "
    "rôle, n est PAS réalisé ici — il relève du pan qualif multi-sessions (storage states par "
    "rôle) et de la suite du projet ; il reste ouvert",
    "parcours-personas : une citation n est pas un parcours DÉDIÉ — un persona au nom courant "
    "(« admin ») cité dans un parcours écrit pour un autre est tenu pour exercé ; la lecture "
    "du fichier désigné reste humaine",
    "parcours-personas : seuls les pilotes Playwright, Cypress, Selenium et Puppeteer sont "
    "reconnus ; un parcours écrit avec un autre outil n est pas vu",
    "parcours-personas : les personas ne sont lus que dans EXIGENCES.json (clés `personas` et "
    "`roles`, convention de cette forge : le schéma du référentiel ne les définit pas), la matrice "
    "des droits et les comptes par rôle ; un persona seulement décrit en prose n est pas vu",
]

_CLES_EXIGENCES = ("personas", "roles")
_CHAMPS_NOM = ("nom", "libelle", "role", "persona", "name", "id")
_EXIGENCES = ("EXIGENCES.json", "forge/EXIGENCES.json", "forge/etapes/conception/EXIGENCES.json")
# Littéral de `forge_tests.livrables.exigences.VARIABLE`, recopié pour ne pas importer le paquet
# `livrables` depuis un adaptateur (`livrables/__init__` importe le REGISTRE des adaptateurs :
# l import serait circulaire). L égalité des deux est TESTÉE.
_VARIABLE_EXIGENCES = "FORGE_TESTS_EXIGENCES"
_ENV_COMPTES = "FORGE_TESTS_QUALIF_STORAGE_STATES"
_ENV_INSTANCE = "FORGE_TESTS_BASE_URL"
_PLAFOND_OCTETS = 512 * 1024

# --- Parcours de bout en bout -------------------------------------------------------------------
_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")
_NOM_DE_TEST = re.compile(
    r"(?:\.(?:spec|test|e2e|cy)\.[cm]?[jt]sx?|(?:^|/)test_[^/]*\.py|_test\.py)$", re.IGNORECASE
)
_DOSSIERS_E2E = {"e2e", "cypress", "playwright", "parcours", "end-to-end"}
_PILOTE_NAVIGATEUR = re.compile(
    r"@playwright/test|\bplaywright\b|\bcypress\b|\bcy\.visit\s*\(|\bselenium\b|\bpuppeteer\b",
    re.IGNORECASE,
)
_NAVIGATION = re.compile(r"\.goto\s*\(|\bcy\.visit\s*\(|\bdriver\.get\s*\(|\.navigate\s*\(")


def _sans_accent(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def _cle(texte: str) -> str:
    """Clé stable d un persona : minuscules, sans accent, séparateurs réduits à un tiret."""
    return re.sub(r"[^a-z0-9]+", "-", _sans_accent(texte).lower()).strip("-")


def _motif(cle: str) -> re.Pattern[str]:
    """Le persona cité en MOT ENTIER dans un texte normalisé (`gestionnaire-rh` ~ `gestionnaire
    rh`, `gestionnaire_rh`), jamais comme fragment d un autre mot (`administrateur` ≠ `admin`)."""
    morceaux = [re.escape(m) for m in cle.split("-") if m]
    return re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]{1,3}".join(morceaux) + r"(?![a-z0-9])")


# --- Personas déclarés --------------------------------------------------------------------------
def _noms_de(entree: object) -> list[str]:
    """Le nom d un persona, puis ses alias : `{"id": "P1", "nom": "Approbateur"}` se cite par
    l un ou l autre. Une chaîne seule est son propre nom."""
    if isinstance(entree, str):
        return [entree.strip()] if entree.strip() else []
    noms: list[str] = []
    if isinstance(entree, dict):
        for champ in _CHAMPS_NOM:
            valeur = entree.get(champ)
            if isinstance(valeur, str) and valeur.strip() and valeur.strip() not in noms:
                noms.append(valeur.strip())
    return noms


def _chemin_exigences(cible: Path) -> Path | None:
    brut = (os.environ.get(_VARIABLE_EXIGENCES) or "").strip()
    if brut:
        return Path(brut)
    for relatif in _EXIGENCES:
        if (cible / relatif).is_file():
            return cible / relatif
    return None


def _comptes_par_role(cible: Path) -> list[str]:
    """Rôles des comptes de test : `role=chemin`, séparés par des virgules (environnement, puis
    `.env.forge-tests` du projet). Lus sans rien écrire dans l environnement du processus."""
    from forge_tests.authentification import ENV_PROJET, _valeurs

    brut = os.environ.get(_ENV_COMPTES) or _valeurs(Path(cible) / ENV_PROJET).get(_ENV_COMPTES, "")
    roles = []
    for paire in brut.split(","):
        role, separateur, _chemin = paire.partition("=")
        if separateur and role.strip():
            roles.append(role.strip())
    return roles


def declares(cible: Path) -> tuple[dict[str, dict], list[str]]:
    """({clé: {"libelle", "sources": [...]}}, notes sur ce qui n a pas pu être lu).

    Une source illisible est une NOTE, jamais un silence : le pan ne prétend pas « aucun persona »
    sur un fichier qu il n a pas pu lire.
    """
    trouves: dict[str, dict] = {}
    notes: list[str] = []

    def ajouter(noms: list[str], source: str) -> None:
        cles = [c for c in (_cle(n) for n in noms) if c]
        if not cles:
            return
        entree = trouves.setdefault(cles[0], {"libelle": noms[0], "sources": [], "alias": []})
        for alias in cles[1:]:
            if alias not in entree["alias"]:
                entree["alias"].append(alias)
        if source not in entree["sources"]:
            entree["sources"].append(source)

    chemin = _chemin_exigences(cible)
    if chemin is not None:
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erreur:
            notes.append(
                f"parcours-personas : {chemin.name} illisible ({type(erreur).__name__}) — les "
                "personas qu il déclare ne sont pas connus, donc pas exigés"
            )
        else:
            if isinstance(donnees, dict):
                for cle in _CLES_EXIGENCES:
                    liste = donnees.get(cle)
                    for entree in liste if isinstance(liste, list) else []:
                        ajouter(_noms_de(entree), f"{chemin.name}:{cle}")

    matrice = droits.lire(cible)
    if matrice.get("_illisible"):
        notes.append(
            f"parcours-personas : {matrice['_illisible']} — les profils qu elle déclare ne "
            "sont pas connus, donc pas exigés"
        )
    for profil in matrice.get("profils") or []:
        ajouter([str(profil)], droits.FICHIER)

    for role in _comptes_par_role(cible):
        ajouter([role], _ENV_COMPTES)
    return trouves, notes


# --- Parcours de bout en bout trouvés -----------------------------------------------------------
def _est_un_parcours_e2e(relatif: str, texte: str) -> bool:
    nom_de_test = bool(_NOM_DE_TEST.search(relatif)) or bool(
        {p.lower() for p in Path(relatif).parts[:-1]} & _DOSSIERS_E2E
    )
    pilote = bool(_PILOTE_NAVIGATEUR.search(texte))
    return nom_de_test and pilote and bool(_NAVIGATION.search(texte))


def _parcours(cible: Path) -> list[tuple[str, str]]:
    """(chemin relatif, texte normalisé nom+contenu) de chaque parcours de bout en bout."""
    trouves: list[tuple[str, str]] = []
    for racine, dossiers, fichiers in os.walk(cible):
        # Élagage : on ne descend ni dans les dépendances ni dans ce que git ignore.
        dossiers[:] = sorted(
            d for d in dossiers
            if not exclusions.dossier_exclu(d)
            and not exclusions.ignore_par_git(Path(racine, d), cible)
        )
        for nom in sorted(fichiers):
            chemin = Path(racine, nom)
            if chemin.suffix.lower() not in _EXTENSIONS:
                continue
            try:
                if chemin.stat().st_size > _PLAFOND_OCTETS:
                    continue
                texte = chemin.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relatif = chemin.relative_to(cible).as_posix()
            if _est_un_parcours_e2e(relatif, texte):
                trouves.append((relatif, _sans_accent(f"{relatif}\n{texte}").lower()))
    return trouves


def parcours_par_persona(cible: Path, personas: dict[str, dict]) -> dict[str, list[str]]:
    """{clé du persona: [chemins des parcours qui le citent]} — liste vide : aucun parcours."""
    parcours = _parcours(cible)
    resultat: dict[str, list[str]] = {}
    for cle, entree in personas.items():
        motifs = [_motif(c) for c in (cle, *entree.get("alias", ()))]
        resultat[cle] = [
            relatif for relatif, texte in parcours if any(m.search(texte) for m in motifs)
        ]
    return resultat


# --- Contrat d adaptateur -----------------------------------------------------------------------
def _fichier_source(cible: Path, source: str) -> str:
    """Le fichier qui porte la déclaration (jamais un nom de variable), pour localiser."""
    brut = source.split(":")[0]
    if brut == _ENV_COMPTES:
        return str(cible / ".env.forge-tests")
    return str(cible / brut)


def inventaire(cible: Path) -> list[Element]:
    personas, _ = declares(cible)
    return [
        Element(
            f"persona:{cle}",
            PAN,
            f"persona « {entree['libelle']} » (déclaré par {', '.join(entree['sources'])}) — "
            "exige au moins un parcours de bout en bout",
            _fichier_source(cible, entree["sources"][0]),
        )
        for cle, entree in sorted(personas.items())
    ]


def exerces(cible: Path) -> set[str]:
    personas, _ = declares(cible)
    cites = parcours_par_persona(cible, personas)
    return {f"persona:{cle}" for cle, parcours in cites.items() if parcours}


def _mention_instance(cible: Path) -> str:
    from forge_tests.authentification import ENV_PROJET, _valeurs

    declaree = os.environ.get(_ENV_INSTANCE) or _valeurs(Path(cible) / ENV_PROJET).get(
        _ENV_INSTANCE, ""
    )
    if declaree.strip():
        return (
            "parcours-personas : une instance servie est déclarée (FORGE_TESTS_BASE_URL) mais ce "
            "pan n y joue AUCUN parcours — le jeu par persona contre cette instance reste ouvert"
        )
    return (
        "parcours-personas : aucune instance servie déclarée (FORGE_TESTS_BASE_URL) — le jeu des "
        "parcours par persona contre une instance est impossible tant qu elle n est pas fournie"
    )


def analyser(cible: Path) -> SortieAdaptateur:
    personas, notes = declares(cible)
    if not personas:
        if notes:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[*NON_JUGE, *notes],
            )
        return evaluer_surface(
            NOM, PAN, str(cible), [], set(), SEUIL, NON_JUGE,
            sans_objet=(
                "aucun persona ni rôle déclaré — ni clé `personas` ou `roles` dans EXIGENCES.json, "
                "ni profils dans forge/matrice-droits.json, ni compte par rôle dans "
                f"{_ENV_COMPTES} : ce projet ne déclare pas de persona à parcourir"
            ),
        )
    sortie = evaluer_surface(
        NOM, PAN, str(cible), inventaire(cible), exerces(cible), SEUIL, NON_JUGE
    )
    sortie.non_juge = [*sortie.non_juge, *notes, _mention_instance(cible)]
    return sortie
