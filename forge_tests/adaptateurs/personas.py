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

CE QUE LE VOLET STATIQUE NE FAISAIT PAS, et que le jeu fait désormais (TF-2123, suite) : un
persona « exercé » par citation signifiait « un parcours le cite », pas « ce parcours passe ». Quand
une instance servie est déclarée (`FORGE_TESTS_QUALIF_URL`, à défaut `FORGE_TESTS_BASE_URL`) et que
le rôle du persona a un compte (`FORGE_TESTS_QUALIF_STORAGE_STATES`, `role=chemin`), le pan JOUE les
routes que son parcours navigue, sous les cookies et le jeton de ce compte, en GET seulement. Un
élément `joue:<persona>` s ajoute à l inventaire ; il est exercé quand chaque route répond sans
refus, sans erreur et sans renvoi vers la mire. Sans instance, sans compte pour un rôle, ou instance
injoignable, le persona n est PAS joué, et le rapport le dit : ni succès ni échec du produit.

Ce que le jeu ne fait toujours pas, et il le dit à chaque rapport : il ne clique pas, ne remplit
aucun formulaire et n exécute aucun JavaScript. C est un parcours HTTP des routes navigées ; le pan
qualif multi-sessions (TF-0316) parcourt l application rendue.

LA SUITE DU 06/11/2026 (retours Produit-86 du 05/11, décisions R-58) :

  - **TF-2204** — un code HTTP que le test porteur AFFIRME pour une route (`expect(r.status())
    .toBe(404)` pour une adresse inconnue) n est pas compté en défaut par le jeu ;
  - **TF-2197** — `parcours-croise` : dès que deux personas sont déclarés, au moins un parcours doit
    les citer ENSEMBLE (l un agit, l autre voit) ; un parcours dont tous les tests peuvent être
    SAUTÉS sous condition (`test.skip(!URL)`, `skipif`) n exerce personne ;
  - **TF-2207** — la clé `parcours` d `EXIGENCES.json` déclare les parcours du produit ; chaque case
    parcours x rôle (`parcours:<parcours>@<rôle>`) exige un e2e qui cite le parcours ET le rôle ;
  - **TF-2208** — sur opt-in (`FORGE_TESTS_PARCOURS_MUTANTS=1`, l instance est modifiable), les
    actions mutantes à adresse littérale du parcours sont rejouées sous l identité du persona, puis
    sans identité (contre-épreuve : refusée, sinon la garde n existe pas). Élément `mute:<persona>`.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from forge_tests import classes, droits, exclusions
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "parcours-personas", "parcours-personas", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publié tel quel au rapport.
POUR_COUVRIR = (
    "écrire, pour chaque persona ou rôle déclaré (clés `personas` ou `roles` d EXIGENCES.json, "
    "`profils` de forge/matrice-droits.json, comptes de FORGE_TESTS_QUALIF_STORAGE_STATES), au "
    "moins un test de bout en bout qui pilote un navigateur, navigue, et nomme ce persona dans son "
    "nom de fichier ou son texte ; quand deux personas sont déclarés, écrire un parcours qui les "
    "cite ensemble ; pour chaque parcours déclaré (clé `parcours` d EXIGENCES.json), un e2e par "
    "rôle qui cite le parcours et le rôle ; ôter les sauts conditionnels qui rendent une suite "
    "SKIPPED ; fournir l instance servie (FORGE_TESTS_QUALIF_URL ou "
    "FORGE_TESTS_BASE_URL) et un compte par rôle (FORGE_TESTS_QUALIF_STORAGE_STATES) pour que le "
    "pan JOUE ce parcours sous l identité du rôle"
)

# Chapitre de cahier que ce pan alimente, DÉRIVÉ du registre par le cahier et le dashboard.
CHAPITRES = (
    {"code": "F7", "famille": "fonctionnel", "titre": "Parcours par persona",
     "decoupe": "persona", "axe_cas": "unitaire"},
)

NON_JUGE = [
    "parcours-personas : statique — un persona est tenu pour exercé (`persona:<clé>`) quand un "
    "fichier de test de bout en bout (navigateur piloté, navigation) le CITE par son nom de "
    "fichier ou dans son texte ; la citation seule ne prouve pas qu un parcours cité passe, le "
    "jeu contre l instance est un élément à part (`joue:<clé>`), présent quand il a lieu",
    "parcours-personas : quand le jeu a lieu (instance et compte par rôle fournis), il rejoue en "
    "GET les routes que le parcours NAVIGUE (littéraux de `goto`, `visit`…), sous les cookies et "
    "le jeton du storage state du rôle ; il ne joue ni clic ni formulaire ni JavaScript. Une "
    "application à page unique qui répond 200 sur son enveloppe et renvoie vers la mire côté "
    "client n est pas vue ici : c est le pan qualif multi-sessions qui parcourt l application "
    "rendue",
    "parcours-personas : une citation n est pas un parcours DÉDIÉ — un persona au nom courant "
    "(« admin ») cité dans un parcours écrit pour un autre est tenu pour exercé ; la lecture "
    "du fichier désigné reste humaine",
    "parcours-personas : un parcours croisé est un parcours qui CITE deux personas ; la "
    "citation ne prouve pas qu un profil agit pendant que l autre observe (la coexistence de "
    "deux identités dans "
    "un test est contrôlée par le pan qualif, TF-0342), et une suite dont chaque test peut être "
    "sauté est écartée sur lecture du texte, pas sur le compte des tests réellement sautés à "
    "l exécution (la forge ne lance pas la suite du produit)",
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
_ENV_INSTANCE_QUALIF = "FORGE_TESTS_QUALIF_URL"
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
    brut = _valeur_declaree(cible, _ENV_COMPTES)
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


def _parcours_bruts(cible: Path) -> list[tuple[str, str]]:
    """(chemin relatif, texte BRUT) de chaque parcours de bout en bout — la casse des routes que le
    jeu rejoue doit survivre, la normalisation du repérage la détruit."""
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
                trouves.append((relatif, texte))
    return trouves


def _parcours(cible: Path) -> list[tuple[str, str]]:
    """(chemin relatif, texte normalisé nom+contenu) de chaque parcours de bout en bout."""
    return [
        (relatif, _sans_accent(f"{relatif}\n{texte}").lower())
        for relatif, texte in _parcours_bruts(cible)
    ]


# TF-2197 (volet c) : un parcours de bout en bout dont CHAQUE test peut être sauté
# (`test.skip(!URL)`, `skipif`) ne prouve rien le jour où la condition est vraie : la suite est
# SKIPPED, verte, et l'audit la comptait comme un parcours. Un tel fichier ne vaut pas
# parcours : il est écarté de ce qui exerce un persona, et le rapport le nomme.
_PYTEST_MARQUE_DE_MODULE = re.compile(r"^\s*pytestmark\s*=.*\bskipif\b", re.MULTILINE)
_TEST_PYTHON = re.compile(r"^\s*(?:async\s+)?def\s+test_\w+", re.MULTILINE)


# TF-2274 (Produit-86, RP-47) : la condition d'un saut se juge dans le CONTEXTE où le pan joue.
# Un e2e qui se saute sans instance désignée (`PENTEST_E2E_URL`) ne se saute pas quand l'instance
# est fournie au pan : l'écarter alors faisait perdre 2 adresses sur 5 par profil, sans un mot au
# rapport. Seul un saut dont la condition NOMME l'instance (une URL, un hôte, un serveur) est levé
# par l'instance fournie ; toute autre condition (`CI`, un drapeau, un navigateur) reste tenue pour
# sautable, et le rapport le dit.
_IDENTIFIANT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NOM_D_INSTANCE = re.compile(r"url|uri|host|instance|endpoint|server|serveur", re.IGNORECASE)


def _condition_du_saut(lignes: list[str], rang: int) -> str:
    """Le texte du saut posé à la ligne `rang`, parenthèses équilibrées (6 lignes au plus),
    sans les chaînes en prose (le motif « pas d URL » n'est pas la condition)."""
    texte = ""
    profondeur = 0
    for ligne in lignes[rang:rang + 6]:
        texte += ligne + "\n"
        profondeur += ligne.count("(") - ligne.count(")")
        if profondeur <= 0:
            break
    return _sans_prose(texte)


def _sans_prose(texte: str) -> str:
    """`texte` sans le contenu des chaînes qui portent un espace (motif en prose) : les chaînes
    sans espace (`'PENTEST_E2E_URL'`, nom d'une variable d'environnement) sont gardées."""
    sortie: list[str] = []
    i = 0
    while i < len(texte):
        guillemet = texte[i]
        if guillemet in "'\"`":
            fin = texte.find(guillemet, i + 1)
            if fin == -1:
                sortie.append(texte[i:])
                break
            contenu = texte[i + 1:fin]
            sortie.append(" " if any(c.isspace() for c in contenu) else texte[i:fin + 1])
            i = fin + 1
        else:
            sortie.append(guillemet)
            i += 1
    return "".join(sortie)


def _saut_d_instance(lignes: list[str], rang: int) -> bool:
    """Vrai si la condition de ce saut nomme l'instance : sans instance fournie il se déclenche,
    avec elle il ne se déclenche pas."""
    condition = _condition_du_saut(lignes, rang)
    return any(_NOM_D_INSTANCE.search(mot) for mot in _IDENTIFIANT.findall(condition))


def toujours_sautable(brut: str, instance_fournie: bool = False) -> bool:
    """Vrai si tous les tests du fichier peuvent être sautés sous condition.

    Un saut conditionnel posé AVANT le premier test (niveau fichier ou `describe`), une marque
    `pytestmark = …skipif…` de module, ou autant de sauts conditionnels que de tests : aucun test
    ne tourne de façon certaine. Un saut inconditionnel et motivé est une décision lisible, il n'est
    pas visé (même distinction que la règle 9 de la revue de suite).

    `instance_fournie` (TF-2274) : le pan a reçu l'instance servie ; un saut dont la condition ne
    tient qu'à l'instance ne se déclenche pas dans ce contexte, il n'est donc plus compté.
    """
    from forge_tests import revue

    lignes = brut.splitlines()
    sauts = [
        rang for rang, ligne in enumerate(lignes)
        if revue._SAUT_CONDITIONNEL.search(ligne) and not revue._SAUT_ASSUME.search(ligne)
    ]
    if instance_fournie:
        sauts = [rang for rang in sauts if not _saut_d_instance(lignes, rang)]
    marque = _PYTEST_MARQUE_DE_MODULE.search(brut)
    if marque and not (
        instance_fournie
        and _saut_d_instance(lignes, brut.count("\n", 0, brut.index("pytestmark", marque.start())))
    ):
        return True
    if not sauts:
        return False
    tests = [brut.count("\n", 0, m.start()) for m in revue._TEST.finditer(brut)]
    tests += [brut.count("\n", 0, m.start()) for m in _TEST_PYTHON.finditer(brut)]
    if not tests:
        return True
    return min(sauts) < min(tests) or len(sauts) >= len(tests)


def sautables(cible: Path, instance_fournie: bool | None = None) -> set[str]:
    """Chemins relatifs des parcours de bout en bout dont tous les tests peuvent être sautés.

    TF-2274 : jugés dans le contexte du pan. `instance_fournie` à `None` lit ce contexte (une
    instance déclarée au pan, `instance_declaree`) ; le passer à `True` ou `False` rejoue l'autre
    contexte, ce que le rapport fait pour dire ce que l'instance changerait.
    """
    if instance_fournie is None:
        instance_fournie = bool(instance_declaree(cible))
    return {
        relatif for relatif, brut in _parcours_bruts(cible)
        if toujours_sautable(brut, instance_fournie)
    }


def _parcours_actifs(cible: Path) -> list[tuple[str, str]]:
    """(chemin, texte normalisé) des parcours qui exercent : les sautables en sont écartés."""
    ecartes = sautables(cible)
    return [(relatif, texte) for relatif, texte in _parcours(cible) if relatif not in ecartes]


def _motifs_du_persona(cle: str, entree: dict) -> list[re.Pattern[str]]:
    return [_motif(c) for c in (cle, *entree.get("alias", ()))]


def parcours_par_persona(cible: Path, personas: dict[str, dict]) -> dict[str, list[str]]:
    """{clé du persona: [chemins des parcours qui le citent]} — liste vide : aucun parcours."""
    parcours = _parcours_actifs(cible)
    resultat: dict[str, list[str]] = {}
    for cle, entree in personas.items():
        motifs = _motifs_du_persona(cle, entree)
        resultat[cle] = [
            relatif for relatif, texte in parcours if any(m.search(texte) for m in motifs)
        ]
    return resultat


# --- Le parcours croisé entre profils (TF-2197, volet b) ------------------------------------------
ELEMENT_CROISE = "parcours-croise"


def parcours_croises(cible: Path, personas: dict[str, dict]) -> list[str]:
    """Chemins des parcours qui citent AU MOINS DEUX personas déclarés distincts.

    Fait remonté (Produit-86, 05/11/2026, RP-17) : aucun parcours « l'opérateur crée, l'approbateur
    voit ». Un parcours par persona prouve que chacun accède à son écran, jamais que ce qu'un profil
    fait est vu par l'autre : c'est le cas nominal d'un produit à rôles (TF-0342).
    """
    croises = []
    for relatif, texte in _parcours_actifs(cible):
        cites = {
            cle for cle, entree in personas.items()
            if any(m.search(texte) for m in _motifs_du_persona(cle, entree))
        }
        if len(cites) >= 2:
            croises.append(relatif)
    return croises


# --- Un e2e par parcours ET par rôle (TF-2207) ----------------------------------------------------
def parcours_declares(cible: Path) -> tuple[dict[str, dict], list[str]]:
    """({clé: {"libelle", "roles": [clés] ou None, "source"}}, notes) — la clé `parcours` de
    EXIGENCES.json, convention de cette forge comme `personas` et `roles`.

    Une entrée est un nom (`"Création d'une demande"`) ou un objet (`{"nom": …, "roles": [...]}`).
    Sans `roles`, le parcours est dû à TOUS les personas déclarés ; avec `roles`, aux seuls rôles
    nommés. Fait remonté (Produit-86, RP-27) : 9 cases parcours x rôle sur 30 portaient un e2e.
    """
    chemin = _chemin_exigences(cible)
    if chemin is None:
        return {}, []
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []  # l'illisibilité est déjà notée par `declares`
    trouves: dict[str, dict] = {}
    liste = donnees.get("parcours") if isinstance(donnees, dict) else None
    for entree in liste if isinstance(liste, list) else []:
        noms = _noms_de(entree)
        cles = [c for c in (_cle(n) for n in noms) if c]
        if not cles:
            continue
        roles = None
        if isinstance(entree, dict) and isinstance(entree.get("roles"), list):
            roles = [c for c in (_cle(str(r)) for r in entree["roles"]) if c]
        trouves.setdefault(
            cles[0],
            {"libelle": noms[0], "alias": cles[1:], "roles": roles,
             "source": f"{chemin.name}:parcours"},
        )
    return trouves, []


def cases_parcours_x_role(
    cible: Path, personas_: dict[str, dict]
) -> list[tuple[str, str, str]]:
    """[(clé du parcours, clé du rôle, libellé du rôle)] — la grille due, parcours x rôle."""
    parcours, _ = parcours_declares(cible)
    cases = []
    for cle, entree in sorted(parcours.items()):
        roles = entree["roles"] if entree["roles"] is not None else sorted(personas_)
        for role in roles:
            libelle = personas_[role]["libelle"] if role in personas_ else role
            cases.append((cle, role, libelle))
    return cases


def cases_exercees(cible: Path, personas_: dict[str, dict]) -> set[str]:
    """Les cases `parcours:<p>@<rôle>` qu'un e2e cite ENSEMBLE (le parcours et le rôle)."""
    parcours, _ = parcours_declares(cible)
    actifs = _parcours_actifs(cible)
    exercees = set()
    for cle, role, _libelle in cases_parcours_x_role(cible, personas_):
        entree = parcours[cle]
        motifs_parcours = [_motif(c) for c in (cle, *entree["alias"])]
        motifs_role = _motifs_du_persona(role, personas_.get(role, {}))
        for _relatif, texte in actifs:
            if any(m.search(texte) for m in motifs_parcours) and any(
                m.search(texte) for m in motifs_role
            ):
                exercees.add(f"parcours:{cle}@{role}")
                break
    return exercees


# --- Le jeu des parcours contre l instance servie (TF-2123, suite) ------------------------------
#: Nombre maximal de routes jouées par persona. Au-delà, le rapport le dit : un parcours qui navigue
#: plus de routes que cela est une exploration, pas un parcours, et le jeu s'arrête à la borne.
PLAFOND_ROUTES = 12
_DELAI_REQUETE_S = 15
_SAUTS_MAX = 5
# Une adresse dont le NOM porte une action. Un GET n'est sûr que par convention : jouer `/logout`
# fermerait la session du compte d'audit, `/supprimer` ou `/reset` modifierait l'instance. Ces
# routes ne sont pas jouées, et le rapport les nomme.
_ROUTE_A_EFFET = re.compile(
    r"(?:^|[/_-])(?:logout|log-out|signout|sign-out|deconnexion|deconnecter|se-deconnecter"
    r"|delete|supprimer|suppression|remove|reset|destroy|purge)(?:$|[/_.-])",
    re.IGNORECASE,
)
_GOTO_LITTERAL = re.compile(
    r"""(?:\.goto|\bcy\.visit|\bdriver\.get|\.navigate)\s*\(\s*(?P<q>['"`])(?P<route>[^'"`]*)(?P=q)"""
)
# Premier segment d une adresse qui est la mire de connexion : y atterrir, c est ne pas avoir de
# session acceptée. Un jeu dont la route demandée EST la mire n y voit pas un échec.
_MIRES = {
    "login", "connexion", "signin", "sign-in", "auth", "authentification", "se-connecter",
    "log-in", "identification",
}


def routes_du_parcours(brut: str) -> list[str]:
    """Les routes que ce parcours NAVIGUE, dans l ordre, sans doublon — littéraux seulement.

    Une adresse construite (`${id}`, concaténation), une adresse absolue vers un autre hôte ou une
    chaîne vide ne sont pas des routes que le jeu peut rejouer sans deviner : elles sont écartées,
    et un parcours qui n en garde aucune joue la racine (le rapport le dit).
    """
    routes: list[str] = []
    for trouve in _GOTO_LITTERAL.finditer(brut):
        route = trouve.group("route").strip()
        if not route.startswith("/") or "${" in route or route.startswith("//"):
            continue
        route = route.split("#")[0]
        chemin = route.split("?")[0] or "/"
        if chemin not in routes:
            routes.append(chemin)
    return routes


# TF-2204 (retour Produit-86 du 05/11/2026) : une route que le test porteur ATTEND en 404
# (`/adresse-inconnue-e2e`, E-069) était comptée en défaut par le jeu : parcours-personas 2/4,
# verdict PARTIEL et seuil bloquant sur un produit conforme. Un code que le test lui-même affirme
# pour cette route n'est pas un défaut du produit : c'est le comportement vérifié.
_CODE_ATTENDU = (
    # expect(reponse.status()).toBe(404) · expect(r?.status()).toEqual(404)
    re.compile(
        r"status\w*\s*(?:\(\s*\))?\s*\)?\s*\.\s*(?:toBe|toEqual|toStrictEqual)\s*\(\s*(\d{3})\s*\)"
    ),
    # assert r.status_code == 404 · expect(r.status() === 404).toBe(true)
    re.compile(r"status\w*\s*(?:\(\s*\))?\s*(?:===?)\s*(\d{3})"),
    # cy.request(...).its('status').should('eq', 404)
    re.compile(r"""should\(\s*['"]eq['"]\s*,\s*(\d{3})\s*\)"""),
)
_DECLARATION_DE_TEST = re.compile(r"""\b(?:test|it)(?:\.\w+)*\s*\(\s*['"`]""")


def codes_attendus_par_route(brut: str) -> dict[str, set[int]]:
    """{route: {codes que le test affirme pour elle}} — lus après chaque navigation littérale.

    Un code compte pour la route dont il suit la navigation, jusqu'à la navigation suivante ou la
    déclaration du test suivant : l'affirmer pour `/inconnue` n'excuse pas un 404 sur `/tableau`.
    Les codes de redirection (3xx) sont écartés : le jeu suit les redirections et juge la page
    d'arrivée, comme le navigateur du test.
    """
    attendus: dict[str, set[int]] = {}
    navigations = [m for m in _GOTO_LITTERAL.finditer(brut)]
    for rang, trouve in enumerate(navigations):
        route = trouve.group("route").strip()
        if not route.startswith("/") or "${" in route or route.startswith("//"):
            continue
        chemin = route.split("#")[0].split("?")[0] or "/"
        fin = navigations[rang + 1].start() if rang + 1 < len(navigations) else len(brut)
        suite = brut[trouve.end():fin]
        autre_test = _DECLARATION_DE_TEST.search(suite)
        if autre_test:
            suite = suite[:autre_test.start()]
        codes = _codes_dans(suite)
        if codes:
            attendus.setdefault(chemin, set()).update(codes)
    return attendus


def _codes_dans(suite: str) -> set[int]:
    """Les codes HTTP (hors 3xx) que le texte affirme par l'une des formes reconnues."""
    return {
        int(code)
        for motif in _CODE_ATTENDU
        for code in motif.findall(suite)
        if not 300 <= int(code) < 400
    }


def _valeur_declaree(cible: Path, cle: str) -> str:
    """Une clé de configuration, SANS rien écrire dans l environnement du processus.

    Dans l ordre : l environnement de l opérateur, `.env.forge-tests`, puis le fichier d audit
    versionné du produit."""
    from forge_tests.authentification import ENV_AUDIT, ENV_PROJET, _valeurs

    brut = os.environ.get(cle)
    if brut and brut.strip():
        return brut.strip()
    for fichier in (ENV_PROJET, ENV_AUDIT):
        valeur = _valeurs(Path(cible) / fichier).get(cle, "").strip()
        if valeur:
            return valeur
    return ""


def instance_declaree(cible: Path) -> str:
    """L instance servie que le jeu joint : `FORGE_TESTS_QUALIF_URL`, à défaut `..._BASE_URL`
    (même ordre que le pan qualif, qui parcourt l instance peuplée)."""
    for cle in (_ENV_INSTANCE_QUALIF, _ENV_INSTANCE):
        valeur = _valeur_declaree(cible, cle)
        if valeur:
            return valeur if valeur.startswith(("http://", "https://")) else f"https://{valeur}"
    return ""


def identites(cible: Path) -> dict[str, str]:
    """{étiquette de rôle: chemin du storage state} — `role=chemin`, séparés par des virgules."""
    brut = _valeur_declaree(cible, _ENV_COMPTES)
    trouvees: dict[str, str] = {}
    for paire in brut.split(","):
        role, separateur, chemin = paire.partition("=")
        if separateur and role.strip() and chemin.strip():
            trouvees.setdefault(role.strip(), chemin.strip())
    return trouvees


def _identite_du_persona(
    cle: str, entree: dict, trouvees: dict[str, str]
) -> tuple[str, str] | None:
    """(étiquette, chemin) du compte de ce persona : l étiquette du rôle, normalisée comme la
    clé du persona, égale à sa clé ou à l un de ses alias."""
    voulues = {cle, *entree.get("alias", ())}
    for role, chemin in trouvees.items():
        if _cle(role) in voulues:
            return role, chemin
    return None


def _lire_etat(cible: Path, chemin: str) -> tuple[dict | None, str | None]:
    fichier = Path(chemin)
    if not fichier.is_absolute():
        fichier = Path(cible) / fichier
    try:
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return None, f"« {fichier.name} » illisible ({type(erreur).__name__})"
    if not isinstance(donnees, dict):
        return None, f"« {fichier.name} » n est pas un storage state (objet JSON attendu)"
    return donnees, None


def _cookie_vaut_pour(cookie: dict, hote: str, chemin: str, https: bool) -> bool:
    domaine = str(cookie.get("domain") or "")
    if not domaine and cookie.get("url"):
        domaine = urlsplit(str(cookie["url"])).hostname or ""
    domaine = domaine.lstrip(".").lower()
    if not domaine or not (hote == domaine or hote.endswith("." + domaine)):
        return False
    portee = str(cookie.get("path") or "/")
    if not chemin.startswith(portee):
        return False
    boucle_locale = hote in ("localhost", "127.0.0.1", "::1")
    return not (cookie.get("secure") and not https and not boucle_locale)


def _en_tetes(etat: dict, base: str, chemin: str) -> dict[str, str]:
    """Les en-têtes d identité d un storage state pour cette requête : les cookies dont le domaine
    et le chemin portent, et le jeton du stockage local de la même origine en `Authorization`."""
    from forge_tests.authentification import CLE_STOCKAGE

    morceaux = urlsplit(base)
    hote = (morceaux.hostname or "").lower()
    https = morceaux.scheme == "https"
    cookies = [
        f"{c['name']}={c['value']}"
        for c in etat.get("cookies") or []
        if isinstance(c, dict) and "name" in c and "value" in c
        and _cookie_vaut_pour(c, hote, chemin, https)
    ]
    en_tetes: dict[str, str] = {}
    if cookies:
        en_tetes["Cookie"] = "; ".join(cookies)
    origine = f"{morceaux.scheme}://{morceaux.netloc}".lower()
    for entree in etat.get("origins") or []:
        if not isinstance(entree, dict):
            continue
        if str(entree.get("origin", "")).lower().rstrip("/") != origine:
            continue
        for element in entree.get("localStorage") or []:
            if isinstance(element, dict) and element.get("name") == CLE_STOCKAGE:
                en_tetes["Authorization"] = f"Bearer {element.get('value', '')}"
    return en_tetes


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Les redirections sont suivies À LA MAIN : chaque saut est lu, et le dernier dit où la route
    a atterri (la mire de connexion, ou un autre hôte)."""

    def redirect_request(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN201
        return None


def _est_la_mire(chemin: str) -> bool:
    premier = chemin.strip("/").split("/")[0].lower()
    return premier in _MIRES


def _jouer_route(
    base: str, route: str, etat: dict, attendus: frozenset[int] | set[int] = frozenset()
) -> tuple[str, str]:
    """(issue, détail) d un GET de `route` sous l identité de `etat`.

    Issues : `ok` · `refuse` (401, 403) · `mire` (renvoyée vers la mire, ou hors de l instance) ·
    `erreur` (404, 5xx, autre code) · `injoignable`. GET seulement.

    `attendus` (TF-2204) : les codes que le test porteur du parcours affirme pour cette route. Le
    code reçu, s il en fait partie, est `ok` : c est le comportement vérifié par le test, pas un
    défaut. Un autre code (un 500 là où le test attend un 404) reste un défaut.
    """
    ouvreur = urllib.request.build_opener(_SansRedirection)
    courant = base.rstrip("/") + route
    for _saut in range(_SAUTS_MAX + 1):
        morceaux = urlsplit(courant)
        origine_base = urlsplit(base)
        if morceaux.netloc.lower() != origine_base.netloc.lower():
            return "mire", f"renvoyée hors de l instance ({morceaux.netloc})"
        requete = urllib.request.Request(  # noqa: S310 — l URL est celle que l opérateur déclare
            courant, headers=_en_tetes(etat, base, morceaux.path or "/"), method="GET"
        )
        try:
            with ouvreur.open(requete, timeout=_DELAI_REQUETE_S) as reponse:  # noqa: S310
                code, lieu = reponse.status, ""
        except urllib.error.HTTPError as erreur:
            code, lieu = erreur.code, erreur.headers.get("Location", "")
        except (urllib.error.URLError, OSError, ValueError) as erreur:
            cause = getattr(erreur, "reason", erreur)
            return "injoignable", f"{type(cause).__name__}"
        if 300 <= code < 400 and lieu:
            courant = urljoin(courant, lieu)
            continue
        if code in attendus and not 300 <= code < 400:
            return "ok", f"{code} (code attendu par le test du parcours)"
        if code in (401, 403):
            return "refuse", f"{code}"
        if 200 <= code < 300:
            arrivee = urlsplit(courant).path or "/"
            if _est_la_mire(arrivee) and not _est_la_mire(route):
                return "mire", f"renvoyée vers la mire {arrivee}"
            return "ok", f"{code}"
        return "erreur", f"{code}"
    return "erreur", f"plus de {_SAUTS_MAX} redirections"


def jouer(cible: Path, personas_: dict[str, dict]) -> dict:
    """Joue, pour chaque persona qu un parcours cite ET dont le rôle a un compte, les routes de
    ce parcours contre l instance déclarée. Aucun effet de bord sur l instance : GET seulement.

    Rend `{"instance", "joues", "sans_identite", "illisibles", "injoignables", "sans_parcours"}`.
    `joues[cle]` porte le rôle, le fichier du compte (son NOM, jamais son contenu), les routes
    avec leur issue, `ok` et la liste des parcours dont elles viennent.
    """
    base = instance_declaree(cible)
    jeu: dict = {"instance": base, "joues": {}, "sans_identite": [], "illisibles": {},
                 "injoignables": [], "sans_parcours": [], "ecartees": {}, "sans_route_jouable": []}
    if not base:
        return jeu
    comptes = identites(cible)
    bruts = dict(_parcours_bruts(cible))
    cites = parcours_par_persona(cible, personas_)
    for cle, entree in sorted(personas_.items()):
        fichiers = cites.get(cle) or []
        if not fichiers:
            jeu["sans_parcours"].append(cle)
            continue
        compte = _identite_du_persona(cle, entree, comptes)
        if compte is None:
            jeu["sans_identite"].append(cle)
            continue
        role, chemin = compte
        etat, motif = _lire_etat(cible, chemin)
        if etat is None:
            jeu["illisibles"][cle] = motif
            continue
        routes: list[str] = []
        attendus: dict[str, set[int]] = {}
        for relatif in fichiers:
            for route in routes_du_parcours(bruts.get(relatif, "")):
                if route not in routes:
                    routes.append(route)
            for route, codes in codes_attendus_par_route(bruts.get(relatif, "")).items():
                attendus.setdefault(route, set()).update(codes)
        a_effet = [r for r in routes if _ROUTE_A_EFFET.search(_sans_accent(r))]
        if a_effet:
            jeu["ecartees"][cle] = a_effet
            routes = [r for r in routes if r not in a_effet]
            if not routes:
                jeu["sans_route_jouable"].append(cle)
                continue
        sans_route = not routes
        total = len(routes)
        routes = (routes or ["/"])[:PLAFOND_ROUTES]
        issues = []
        for route in routes:
            issue, detail = _jouer_route(base, route, etat, attendus.get(route, set()))
            issues.append({"route": route, "issue": issue, "detail": detail})
        if all(i["issue"] == "injoignable" for i in issues):
            jeu["injoignables"].append(cle)
            continue
        jeu["joues"][cle] = {
            "role": role,
            "compte": Path(chemin).name,
            "routes": issues,
            "ok": all(i["issue"] == "ok" for i in issues),
            "parcours": fichiers,
            "routes_navigees": total,
            "racine_par_defaut": sans_route,
        }
    return jeu


# --- Les actions mutantes du parcours, rejouées profil par profil (TF-2208) ----------------------
# Fait remonté (Produit-86, RP-28) : le jeu ne rejouait qu'en GET. Il ne jugeait donc jamais ce
# qu'un profil FAIT (créer, valider, agir) : seuls ses écrans étaient lus.
#
# Ce jeu MODIFIE l'instance. Il n'a donc lieu que sur déclaration explicite de l'opérateur
# (`FORGE_TESTS_PARCOURS_MUTANTS=1`, environnement ou `.env.forge-tests`) : poser la variable dit
# « cette instance peut être modifiée par l'audit ». Sans elle, les actions trouvées sont NOMMÉES au
# rapport, jamais rejouées.
#
# Ce qui est rejoué : les appels mutants à adresse LITTÉRALE du parcours (`request.post('/api/x',
# { data: {…} })`, `cy.request('POST', '/api/x', {…})`), sous l'identité du persona dont le parcours
# les porte, avec le corps littéral quand il se lit. La contre-épreuve : le MÊME appel sans aucune
# identité doit être refusé (401, 403, renvoi vers la mire) ; accepté, la garde n'existe pas.
# Ce qui ne l'est pas : un enchaînement dont une étape dépend de la réponse d'une autre (identifiant
# créé puis validé par un autre profil) — le rapport le dit.
_ENV_MUTANTS = "FORGE_TESTS_PARCOURS_MUTANTS"
_MUTANT_METHODE = re.compile(
    r"""\.\s*(?P<m>post|put|patch|delete)\s*\(\s*(?P<q>['"`])(?P<route>/[^'"`$]*)(?P=q)""",
    re.IGNORECASE,
)
_MUTANT_CYPRESS = re.compile(
    r"""\bcy\.request\s*\(\s*['"`](?P<m>POST|PUT|PATCH|DELETE)['"`]\s*,\s*"""
    r"""['"`](?P<route>/[^'"`$]*)['"`]""",
    re.IGNORECASE,
)
_CORPS_CLE = re.compile(r"""\b(?:data|json|body)\s*[:=]\s*(?=\{)""")
_FENETRE_CORPS = 600


def _objet_litteral(texte: str) -> dict | None:
    """Le premier objet littéral qui suit `data:`/`json=`/`body:`, lu comme JSON — ou None.

    Une valeur construite (`${id}`, variable, appel) n'est pas devinée : le corps n'est alors pas
    rejoué, et l'appel est rejoué sans corps (le rapport le dit)."""
    cle = _CORPS_CLE.search(texte)
    if not cle:
        return None
    debut = cle.end()
    profondeur = 0
    for rang in range(debut, len(texte)):
        if texte[rang] == "{":
            profondeur += 1
        elif texte[rang] == "}":
            profondeur -= 1
            if profondeur == 0:
                brut = texte[debut:rang + 1]
                break
    else:
        return None
    brut = re.sub(
        r"""(['"`])((?:\\.|(?!\1).)*)\1""", lambda m: json.dumps(m.group(2)), brut, flags=re.DOTALL
    )
    brut = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', brut)
    brut = re.sub(r",\s*([}\]])", r"\1", brut)
    try:
        objet = json.loads(brut)
    except ValueError:
        return None
    return objet if isinstance(objet, dict) else None


def actions_mutantes(brut: str) -> list[dict]:
    """Les appels mutants à adresse littérale du parcours, dans l'ordre, sans doublon.

    `{"methode", "route", "corps" (dict ou None), "attendus" (codes affirmés par le test)}`."""
    trouves = sorted(
        [*_MUTANT_METHODE.finditer(brut), *_MUTANT_CYPRESS.finditer(brut)],
        key=lambda m: m.start(),
    )
    actions: list[dict] = []
    for rang, trouve in enumerate(trouves):
        route = trouve.group("route").split("#")[0].split("?")[0] or "/"
        if _ROUTE_A_EFFET.search(_sans_accent(route)):
            continue
        fin = trouves[rang + 1].start() if rang + 1 < len(trouves) else len(brut)
        suite = brut[trouve.end():fin]
        autre_test = _DECLARATION_DE_TEST.search(suite)
        if autre_test:
            suite = suite[:autre_test.start()]
        action = {
            "methode": trouve.group("m").upper(), "route": route,
            "corps": _objet_litteral(suite[:_FENETRE_CORPS]), "attendus": _codes_dans(suite),
        }
        if not any(a["methode"] == action["methode"] and a["route"] == route for a in actions):
            actions.append(action)
    return actions


def _mutation_declaree(cible: Path) -> bool:
    return _valeur_declaree(cible, _ENV_MUTANTS).lower() in ("1", "true", "oui", "yes")


def _jouer_mutation(base: str, action: dict, etat: dict | None) -> tuple[str, str]:
    """(issue, code) d'un appel mutant, sous l'identité de `etat` (None : sans identité).

    Issues : `ok` (2xx, ou code attendu par le test) · `refuse` (401, 403) · `mire` (renvoi vers la
    mire de connexion) · `erreur` · `injoignable`. Les redirections ne sont PAS suivies : une
    mutation rejouée deux fois par un suivi de 307 serait une double écriture."""
    url = base.rstrip("/") + action["route"]
    entetes = _en_tetes(etat, base, action["route"]) if etat else {}
    donnees = None
    if action["corps"] is not None:
        donnees = json.dumps(action["corps"]).encode("utf-8")
        entetes["Content-Type"] = "application/json"
    requete = urllib.request.Request(  # noqa: S310 — l'URL est celle que l'opérateur déclare
        url, data=donnees, headers=entetes, method=action["methode"]
    )
    try:
        with urllib.request.build_opener(_SansRedirection).open(  # noqa: S310
            requete, timeout=_DELAI_REQUETE_S
        ) as reponse:
            code, lieu = reponse.status, ""
    except urllib.error.HTTPError as erreur:
        code, lieu = erreur.code, erreur.headers.get("Location", "")
    except (urllib.error.URLError, OSError, ValueError) as erreur:
        return "injoignable", type(getattr(erreur, "reason", erreur)).__name__
    if code in action["attendus"] and not 300 <= code < 400:
        return "ok", f"{code}"
    if 300 <= code < 400 and _est_la_mire(urlsplit(urljoin(url, lieu)).path or "/"):
        return "mire", f"{code} vers la mire"
    if code in (401, 403):
        return "refuse", f"{code}"
    if 200 <= code < 300:
        return "ok", f"{code}"
    return "erreur", f"{code}"


def jouer_mutations(cible: Path, personas_: dict[str, dict], jeu: dict) -> dict:
    """Rejoue les actions mutantes du parcours de chaque persona dont le parcours a été joué.

    Rend `{"autorise", "nommees", "jouees"}` : `nommees[cle]` = les actions trouvées (rejouées ou
    non), `jouees[cle]` = `{"role", "actions": [{methode, route, sous_identite, contre_epreuve}],
    "ok"}`. Sans instance, ou sans l'opt-in, rien n'est rejoué : les actions sont seulement
    nommées."""
    resultat: dict = {"autorise": _mutation_declaree(cible), "nommees": {}, "jouees": {}}
    if not jeu["instance"]:
        return resultat
    bruts = dict(_parcours_bruts(cible))
    cites = parcours_par_persona(cible, personas_)
    comptes = identites(cible)
    for cle, entree in sorted(personas_.items()):
        actions: list[dict] = []
        for relatif in cites.get(cle) or []:
            for action in actions_mutantes(bruts.get(relatif, "")):
                if not any(a["methode"] == action["methode"] and a["route"] == action["route"]
                           for a in actions):
                    actions.append(action)
        if not actions:
            continue
        resultat["nommees"][cle] = actions
        compte = _identite_du_persona(cle, entree, comptes)
        if not resultat["autorise"] or compte is None:
            continue
        role, chemin = compte
        etat, _motif_illisible = _lire_etat(cible, chemin)
        if etat is None:
            continue
        rejouees = []
        for action in actions:
            issue, code = _jouer_mutation(jeu["instance"], action, etat)
            contre = None
            if issue == "ok":
                # La contre-épreuve n'a de sens que si l'appel passe sous l'identité du rôle.
                contre = _jouer_mutation(jeu["instance"], action, None)
            rejouees.append({
                "methode": action["methode"], "route": action["route"],
                "sans_corps_lisible": action["corps"] is None,
                "sous_identite": (issue, code), "contre_epreuve": contre,
            })
        if all(r["sous_identite"][0] == "injoignable" for r in rejouees):
            continue
        resultat["jouees"][cle] = {
            "role": role, "actions": rejouees,
            "ok": all(
                r["sous_identite"][0] == "ok"
                and r["contre_epreuve"] is not None and r["contre_epreuve"][0] in ("refuse", "mire")
                for r in rejouees
            ),
        }
    return resultat


def _elements_des_mutations(
    cible: Path, mutations: dict, personas_: dict[str, dict]
) -> list[Element]:
    return [
        Element(
            f"mute:{cle}",
            PAN,
            f"actions mutantes du parcours de « {personas_[cle]['libelle']} » rejouées sous "
            f"l'identité du rôle « {joue['role']} », avec contre-épreuve sans identité",
            str(Path(cible) / "forge" / "EXIGENCES.json"),
        )
        for cle, joue in sorted(mutations["jouees"].items())
    ]


def _message_des_mutations(libelle: str, joue: dict) -> str:
    fautes = []
    for action in joue["actions"]:
        appel = f"{action['methode']} {action['route']}"
        issue, code = action["sous_identite"]
        if issue != "ok":
            fautes.append(f"{appel} : refusé ou en erreur sous l'identité du rôle (HTTP {code})")
        elif action["contre_epreuve"] is not None and action["contre_epreuve"][0] not in (
            "refuse", "mire"
        ):
            fautes.append(
                f"{appel} : CONTRE-ÉPREUVE ratée — le même appel SANS identité a répondu "
                f"HTTP {action['contre_epreuve'][1]} ({action['contre_epreuve'][0]}) au lieu "
                "d'un refus : la garde n'existe pas"
            )
    return (
        f"persona « {libelle} » : action(s) mutante(s) de son parcours rejouée(s) sous "
        f"l'identité du rôle « {joue['role']} » — {len(fautes)} sur {len(joue['actions'])} "
        "en défaut : "
        + "; ".join(fautes[:5])
    )


def _mentions_des_mutations(mutations: dict, personas_: dict[str, dict]) -> list[str]:
    nommees = mutations["nommees"]
    if not nommees:
        return [
            "parcours-personas : aucune action MUTANTE à adresse littérale trouvée dans les "
            "parcours (`request.post('/api/…')`, `cy.request('POST', '/api/…')`) : ce que chaque "
            "profil FAIT n'est pas jugé ici, seuls ses écrans le sont (GET)"
        ]
    lignes = []
    for cle, actions in sorted(nommees.items()):
        noms = ", ".join(f"{a['methode']} {a['route']}" for a in actions[:5])
        if cle in mutations["jouees"]:
            sans_corps = [a for a in actions if a["corps"] is None and a["methode"] != "DELETE"]
            lignes.append(
                "parcours-personas : ACTIONS MUTANTES REJOUÉES pour "
                f"« {personas_[cle]['libelle']} » ({noms}) sous son identité, puis sans "
                "identité (contre-épreuve) ; l'instance a été MODIFIÉE (opt-in "
                + _ENV_MUTANTS + ")"
                + (f" ; {len(sans_corps)} appel(s) rejoué(s) sans corps (corps non littéral)"
                   if sans_corps else "")
            )
        elif not mutations["autorise"]:
            lignes.append(
                f"parcours-personas : {len(actions)} action(s) mutante(s) du parcours de "
                f"« {personas_[cle]['libelle']} » NON rejouée(s) ({noms}) : les rejouer modifie "
                f"l'instance, ce qui exige {_ENV_MUTANTS}=1 (instance déclarée modifiable)"
            )
        else:
            lignes.append(
                f"parcours-personas : action(s) mutante(s) de « {personas_[cle]['libelle']} » "
                f"({noms}) NON rejouée(s) : aucun compte pour son rôle ({_ENV_COMPTES}) ou compte "
                "illisible, ou instance injoignable"
            )
    lignes.append(
        "parcours-personas : un ENCHAÎNEMENT entre profils dont une étape dépend de la réponse "
        "d'une autre (l'opérateur prépare → l'approbateur valide l'identifiant créé → l'agent "
        "agit → l'opérateur voit) n'est PAS rejoué : chaque action l'est isolément, sous le "
        "seul profil dont le parcours la porte ; l'enchaînement reste à écrire en test de bout "
        "en bout"
    )
    return lignes


# --- Contrat d adaptateur -----------------------------------------------------------------------
def _fichier_source(cible: Path, source: str) -> str:
    """Le fichier qui porte la déclaration (jamais un nom de variable), pour localiser."""
    brut = source.split(":")[0]
    if brut == _ENV_COMPTES:
        return str(cible / ".env.forge-tests")
    return str(cible / brut)


def inventaire(cible: Path) -> list[Element]:
    personas, _ = declares(cible)
    elements = [
        Element(
            f"persona:{cle}",
            PAN,
            f"persona « {entree['libelle']} » (déclaré par {', '.join(entree['sources'])}) — "
            "exige au moins un parcours de bout en bout",
            _fichier_source(cible, entree["sources"][0]),
        )
        for cle, entree in sorted(personas.items())
    ]
    source = _chemin_exigences(cible)
    if len(personas) >= 2:
        # TF-2197 (b) : plusieurs profils déclarés exigent un parcours qui les fait AGIR ensemble.
        premier = personas[sorted(personas)[0]]
        elements.append(
            Element(
                ELEMENT_CROISE,
                PAN,
                "parcours croisé entre profils — exige au moins un parcours de bout en bout qui "
                f"cite deux des {len(personas)} personas déclarés (l'un agit, l'autre voit)",
                _fichier_source(cible, premier["sources"][0]),
            )
        )
    parcours, _ = parcours_declares(cible)
    for cle, role, libelle_role in cases_parcours_x_role(cible, personas):
        elements.append(
            Element(
                f"parcours:{cle}@{role}",
                PAN,
                f"parcours « {parcours[cle]['libelle']} » x rôle « {libelle_role} » — exige un "
                "parcours de bout en bout qui cite le parcours ET le rôle",
                str(source) if source else str(cible),
            )
        )
    return elements


def exerces(cible: Path) -> set[str]:
    personas, _ = declares(cible)
    cites = parcours_par_persona(cible, personas)
    exerces_ = {f"persona:{cle}" for cle, parcours in cites.items() if parcours}
    if len(personas) >= 2 and parcours_croises(cible, personas):
        exerces_.add(ELEMENT_CROISE)
    return exerces_ | cases_exercees(cible, personas)


def _elements_du_jeu(cible: Path, jeu: dict, personas_: dict[str, dict]) -> list[Element]:
    """Un élément `joue:<persona>` par persona dont le parcours a pu être joué sous son identité.

    Un persona sans compte, au compte illisible ou dont l instance est injoignable n a PAS
    d élément : il n a pas été joué, et le dire (non_juge) est plus honnête que l accuser d un
    échec du produit ou le compter pour un succès.
    """
    elements = []
    for cle, joue in sorted(jeu["joues"].items()):
        libelle = personas_[cle]["libelle"]
        elements.append(
            Element(
                f"joue:{cle}",
                PAN,
                f"parcours de « {libelle} » joué contre l instance sous l identité du rôle "
                f"« {joue['role']} »",
                str(Path(cible) / joue["parcours"][0]),
            )
        )
    return elements


_PHRASES_ISSUE = {
    "refuse": lambda d: f"refusée à ce rôle (HTTP {d})",
    "mire": lambda d: d,
    "erreur": lambda d: f"en erreur (HTTP {d})" if d.isdigit() else d,
    "injoignable": lambda d: f"injoignable ({d})",
}


def _message_du_jeu(libelle: str, joue: dict, instance: str) -> str:
    """La phrase d un constat de jeu : le persona, le rôle, les routes en défaut et pourquoi."""
    fautives = [r for r in joue["routes"] if r["issue"] != "ok"]
    montrees = "; ".join(
        f"{r['route']} : {_PHRASES_ISSUE[r['issue']](r['detail'])}" for r in fautives[:5]
    )
    reste = f"; … et {len(fautives) - 5} autre(s)" if len(fautives) > 5 else ""
    return (
        f"persona « {libelle} » : parcours joué sous l identité du rôle « {joue['role']} » "
        f"contre {instance} — {len(fautives)} route(s) sur {len(joue['routes'])} en défaut : "
        f"{montrees}{reste}"
    )


def _jeu_non_realise() -> str:
    return (
        "parcours-personas : le jeu de chaque parcours contre l instance servie, sous l identité "
        "du rôle, n est PAS réalisé ici — il exige l instance servie (FORGE_TESTS_QUALIF_URL ou "
        f"FORGE_TESTS_BASE_URL) et un compte par rôle ({_ENV_COMPTES}, `role=chemin`)"
    )


def _mentions_du_jeu(jeu: dict, personas_: dict[str, dict]) -> list[str]:
    """Ce que le jeu a fait, et surtout ce qu il n a pas fait : une ligne par réserve."""
    nom = {cle: entree["libelle"] for cle, entree in personas_.items()}
    base = jeu["instance"]
    if not base:
        return [
            "parcours-personas : aucune instance servie déclarée (FORGE_TESTS_QUALIF_URL ou "
            "FORGE_TESTS_BASE_URL) — le jeu des parcours par persona contre une instance est "
            "impossible tant qu elle n est pas fournie",
            _jeu_non_realise(),
        ]
    lignes: list[str] = []
    joues = jeu["joues"]
    if joues:
        detail = " · ".join(
            f"{cle} sous « {j['role']} » : "
            + ", ".join(f"{r['route']} {r['detail']}" for r in j["routes"])
            for cle, j in sorted(joues.items())
        )
        lignes.append(
            f"parcours-personas : JEU RÉEL — {len(joues)} parcours joué(s) contre {base} sous "
            f"l identité du rôle de chaque persona, en GET seulement (l instance n est jamais "
            f"modifiée) : {detail}"
        )
    else:
        lignes.append(
            "parcours-personas : une instance servie est déclarée (FORGE_TESTS_QUALIF_URL ou "
            "FORGE_TESTS_BASE_URL) mais ce pan n y joue AUCUN parcours — aucun persona cité par "
            f"un parcours n a pu être joué sous son identité ({_ENV_COMPTES}, `role=chemin`)"
        )
    if jeu["sans_identite"]:
        lignes.append(
            f"parcours-personas : {len(jeu['sans_identite'])} persona(s) cité(s) par un parcours "
            f"mais SANS identité — non joué(s) : "
            + ", ".join(nom[c] for c in jeu["sans_identite"])
            + f" ; fournir un compte par rôle dans {_ENV_COMPTES} (`role=chemin`, un storage state "
            "par rôle). Ce n est pas un échec du produit"
        )
    for cle, motif in sorted(jeu["illisibles"].items()):
        lignes.append(
            f"parcours-personas : le compte du persona « {nom[cle]} » est {motif} — non joué ; "
            "ce n est ni un succès ni un échec du produit"
        )
    if jeu["injoignables"]:
        lignes.append(
            f"parcours-personas : instance {base} INJOIGNABLE pour "
            + ", ".join(nom[c] for c in jeu["injoignables"])
            + " — non joué(s) ; ce n est ni un succès ni un échec du produit. Démarrer l instance "
            "(commande de démarrage déclarée par le projet) puis `--reprendre` le rapport"
        )
    for cle, ecartees in sorted(jeu["ecartees"].items()):
        lignes.append(
            f"parcours-personas : {len(ecartees)} route(s) du parcours de « {nom[cle]} » NON "
            f"JOUÉE(S) ({', '.join(ecartees[:5])}) : leur nom porte une action (fermer la session, "
            "supprimer, réinitialiser), et un GET sur une telle adresse peut modifier l instance "
            "ou fermer la session du compte d audit"
            + (" ; plus aucune route à jouer, le persona n est pas joué"
               if cle in jeu["sans_route_jouable"] else "")
        )
    for cle, joue in sorted(joues.items()):
        if joue["racine_par_defaut"]:
            lignes.append(
                f"parcours-personas : le parcours de « {nom[cle]} » ne navigue aucune route "
                "littérale : le jeu a joué la racine (`/`) sous son identité, et rien d autre"
            )
        if joue["routes_navigees"] > PLAFOND_ROUTES:
            lignes.append(
                f"parcours-personas : le parcours de « {nom[cle]} » navigue "
                f"{joue['routes_navigees']} routes ; le jeu en rejoue {PLAFOND_ROUTES} (plafond), "
                "les suivantes ne sont pas jouées"
            )
    return lignes


def analyser(cible: Path) -> SortieAdaptateur:
    personas_, notes = declares(cible)
    if not personas_:
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
    # Le jeu contre l instance servie (TF-2123, suite) : il ajoute un élément `joue:<persona>` par
    # parcours effectivement joué, exercé quand chacune de ses routes a répondu sous l identité.
    jeu = jouer(cible, personas_)
    # TF-2208 : les actions mutantes du parcours, rejouées profil par profil sur opt-in.
    mutations = jouer_mutations(cible, personas_, jeu)
    exerce = (
        exerces(cible)
        | {f"joue:{cle}" for cle, j in jeu["joues"].items() if j["ok"]}
        | {f"mute:{cle}" for cle, j in mutations["jouees"].items() if j["ok"]}
    )
    sortie = evaluer_surface(
        NOM, PAN, str(cible),
        [*inventaire(cible), *_elements_du_jeu(cible, jeu, personas_),
         *_elements_des_mutations(cible, mutations, personas_)],
        exerce, SEUIL, NON_JUGE,
    )
    for constat in sortie.findings:
        if constat.id.startswith("joue:"):
            cle = constat.id[len("joue:"):]
            constat.classe = classes.PARCOURS_PERSONA_REFUSE
            constat.message = _message_du_jeu(
                personas_[cle]["libelle"], jeu["joues"][cle], jeu["instance"]
            )
        elif constat.id.startswith("mute:"):
            cle = constat.id[len("mute:"):]
            constat.classe = classes.PARCOURS_PERSONA_REFUSE
            constat.message = _message_des_mutations(
                personas_[cle]["libelle"], mutations["jouees"][cle]
            )
    ecartes = _parcours_sautables_nommes(cible)
    for constat in sortie.findings:
        if constat.id == ELEMENT_CROISE or constat.id.startswith(("parcours:", "persona:")):
            constat.message += _suite_du_defaut(constat.id, ecartes)
    sortie.non_juge = [
        *sortie.non_juge, *notes, *_mentions_du_jeu(jeu, personas_),
        *(_mentions_des_mutations(mutations, personas_) if jeu["instance"] else []),
        *_mentions_des_parcours_sautables(cible, ecartes),
    ]
    return sortie


def _parcours_sautables_nommes(cible: Path) -> list[str]:
    return sorted(sautables(cible))


def _suite_du_defaut(identifiant: str, ecartes: list[str]) -> str:
    """Ce que le lecteur fait du constat : où chercher, et ce qui est écarté du décompte."""
    if ecartes:
        ecart = (
            f" ; {len(ecartes)} parcours dont tous les tests peuvent être SAUTÉS sous condition "
            f"({', '.join(ecartes[:3])}{' …' if len(ecartes) > 3 else ''}) ne comptent pas"
        )
    else:
        ecart = ""
    if identifiant == ELEMENT_CROISE:
        return (
            " — écrire un parcours où un profil agit et un autre voit le résultat (nommer les "
            f"deux dans le test){ecart}"
        )
    if identifiant.startswith("parcours:"):
        return (
            " — écrire le parcours de bout en bout pour ce rôle (nommer le parcours et le rôle "
            f"dans son fichier ou son texte){ecart}"
        )
    return ecart


def _mentions_des_parcours_sautables(cible: Path, ecartes: list[str]) -> list[str]:
    """Les fichiers écartés, TOUS nommés (aucune borne d'affichage), avec le contexte du jugement
    (TF-2274) : instance fournie ou non, et ce que l'instance changerait."""
    if not ecartes:
        return []
    if instance_declaree(cible):
        contexte = (
            "instance fournie : les sauts qui ne tiennent qu'à l'instance ne comptent plus, "
            "ceux-ci "
            "tiennent à une autre condition (variable d'environnement, intégration continue, "
            "drapeau) que fournir l'instance ne lève pas"
        )
    else:
        levables = sorted(set(ecartes) - sautables(cible, True))
        if levables:
            contexte = (
                f"aucune instance fournie : {len(levables)} d'entre eux ({', '.join(levables)}) ne "
                "se sautent que faute d'instance et compteraient dès que FORGE_TESTS_QUALIF_URL "
                "ou FORGE_TESTS_BASE_URL est fourni"
            )
        else:
            contexte = (
                "aucune instance fournie, mais aucun d'eux ne tient à la seule instance : la "
                "fournir ne les rétablirait pas"
            )
    return [
        f"parcours-personas : {len(ecartes)} parcours de bout en bout dont TOUS les tests peuvent "
        f"être sautés sous condition sont écartés de ce qui exerce un persona : "
        f"{', '.join(ecartes)}. Une suite SKIPPED (URL absente, variable non posée) est verte et "
        f"ne prouve rien ; ôter la condition ou faire échouer explicitement son absence les "
        f"rétablit. Contexte du jugement : {contexte}. Une condition qui ne nomme ni URL, ni hôte, "
        "ni instance, ni serveur est tenue pour sautable dans les deux contextes"
    ]
