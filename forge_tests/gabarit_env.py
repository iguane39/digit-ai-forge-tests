r"""Dépose `.env.forge-tests.exemple` chez le projet audité — dérivé du code, jamais recopié.

Pourquoi (TF-0539, lot Produit-02 20260823a). Le rapport énumère, pan par pan, les clés
attendues ET le chemin exact du fichier, jusqu'à préciser pour certains pans que « renseigner
cette configuration ne le rendrait pas mesurable pour autant ». La forge sait donc aussi quelles
clés seraient INUTILES sur la stack détectée. Le projet devait pourtant reconstituer le fichier
à la main depuis un rapport de 1,1 Mo.

Le choix qui compte ici : les clés sont **dérivées du code** par balayage des littéraux
`FORGE_TESTS_*`, jamais recopiées dans une liste. Une liste recopiée se périme au premier ajout
de clé, en silence, et personne ne s'en aperçoit avant qu'un projet cherche une option qui
n'existe plus — c'est la même classe de défaut que les dix listes d'exclusion de TF-0543.

Ce qu'il livre AUSSI, depuis TF-0620 (mesure du pilot du 25/08). Ce module PRESCRIT le nom
`.env.forge-tests` chez le projet audité, et ce fichier porte, par construction, les éléments
d'authentification de l'application. Jusqu'ici la protection était SUPPOSÉE : le docstring
d'`authentification.py` écrivait « gitignore que l'opérateur remplit », et le mot `gitignore`
n'apparaissait nulle part ailleurs dans le paquet. Une convention qui repose sur un geste
d'opérateur non outillé ne produit pas « souvent conforme » — elle produit un TIRAGE. Le tirage a
été mesuré sur les trois projets du parc qui portent le fichier réel : **un seul l'ignorait**. Le
deuxième n'avait aucune ligne, et le troisième portait `!.env.forge-tests`, une NÉGATION écrite
exprès pour que git suive ce fichier — ce qui interdit de conclure à l'étourderie. Les deux étaient
versionnés, et l'un PUBLIÉ sur `origin/main`. Loi transverse n° 1, mot pour mot : *toute affordance
est câblée ou n'existe pas.*

Où s'arrête ce module, et pourquoi la frontière est là. Il AJOUTE la ligne manquante — un geste
additif, réversible, dans un fichier dont il connaît déjà l'usage. Il ne RETIRE jamais une négation
existante : quelqu'un l'a écrite, éventuellement pour une raison, et l'effacer serait décider à sa
place. Il la DÉNONCE, avec son numéro de ligne. Et il ne retire jamais du suivi un fichier déjà
versionné : cela relève de l'humain (R-29), et pour un fichier déjà publié, seule une rotation
d'identifiant réduit le risque — le retirer du disque n'y change rien.

Ce que ce module NE fait PAS : écraser un fichier existant. Le projet renomme et remplit
`.env.forge-tests.exemple` en `.env.forge-tests` ; ce dernier lui appartient et n'est jamais
touché. Un exemple qui écraserait une configuration réelle coûterait plus qu'il ne rend.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Le nom du fichier déposé. `.exemple` et non `.env.forge-tests` : le second appartient au
#: projet, et déposer directement une configuration vide la ferait passer pour renseignée.
FICHIER = ".env.forge-tests.exemple"

_CLE = re.compile(r"FORGE_TESTS_[A-Z0-9_]+")

#: Ce qu'une clé sert, quand son nom ne le dit pas seul. Une clé absente d'ici sort sans glose
#: plutôt qu'avec une paraphrase de son nom : une glose creuse fatigue le lecteur et ne l'aide pas.
GLOSES: dict[str, str] = {
    "FORGE_TESTS_APP": "application ASGI du projet, forme `module:objet` — sans elle, le pan "
                       "api ne peut rien appeler",
    "FORGE_TESTS_BASE_URL": "URL de l'instance à interroger pour les pans qui parlent au "
                            "produit lancé",
    "FORGE_TESTS_SOURCES": "paquet Python du produit ; son parent devient la racine d'exécution",
    "FORGE_TESTS_INCLURE": "dossiers à RÉINTÉGRER au périmètre malgré le socle d'exclusions "
                           "(TF-0536) — `input` par exemple, si le projet a une vraie raison "
                           "de l'auditer",
    "FORGE_TESTS_MUTATION_EXCLUT": "modules hors du pan mutation",
    "FORGE_TESTS_MUTATION_PLAFOND": "plafond de mutants, pour borner la durée",
    "FORGE_TESTS_I18N_ROUTES": "routes attendues par locale (TF-0470)",
    "FORGE_TESTS_I18N_CHAINES": "lexique de chaînes littérales à surveiller (TF-0465)",
    "FORGE_TESTS_LOGIN": "identifiants de démonstration, JAMAIS un compte réel",
    "FORGE_TESTS_GLOSSAIRE": "glossaire du projet (TF-0644) — defaut "
                             "`docs/projet/GLOSSAIRE.md` ; il donne, par locale, le TERME "
                             "retenu, sans quoi « 8 gites » et « 8 cottages » ne se "
                             "rapprochent pas",
    "FORGE_TESTS_FAITS": "JSON `{\"<pivot>\": <nombre>}` — la DONNEE du produit, seul point "
                         "fixe hors du catalogue. Le defaut fondateur disait « 8 » dans les "
                         "SEPT langues : coherentes entre elles, et toutes fausses",
    "FORGE_TESTS_AVANCEMENT_S": "période d'émission de l'avancement, en secondes",
}


def cles_connues(racine_forge: Path | str | None = None) -> list[str]:
    """Les clés `FORGE_TESTS_*` réellement lues par le code, dérivées et triées.

    Dérivées, donc à jour par construction : ajouter une clé au code l'ajoute au gabarit sans
    que personne ait à y penser.
    """
    base = Path(racine_forge) if racine_forge else Path(__file__).parent
    cles: set[str] = set()
    for source in base.rglob("*.py"):
        if "__pycache__" in source.parts:
            continue
        try:
            cles |= set(_CLE.findall(source.read_text(encoding="utf-8")))
        except OSError:
            continue
    return sorted(cles)


def rendre(cles: list[str]) -> str:
    """Le contenu du gabarit : en-tête, puis une clé vide par ligne, commentée quand c'est utile."""
    lignes = [
        "# Configuration d'audit forge-tests — GABARIT DÉPOSÉ PAR LA FORGE (TF-0539).",
        "#",
        "# Renommer ce fichier en `.env.forge-tests` et renseigner ce qui s'applique à ce projet.",
        "# Une clé laissée vide est une clé non fournie : le pan concerné le DIT dans le rapport,",
        "# il ne devine pas et ne se tait pas.",
        "#",
        "# JAMAIS de secret réel ici ni dans `.env.forge-tests` : des comptes de démonstration,",
        "# ou une référence `# à fournir :` pour ce qui vient d'ailleurs.",
        "#",
        f"# {len(cles)} clés, DÉRIVÉES du code de la forge — pas une liste recopiée, donc pas une",
        "# liste qui se périme au prochain ajout.",
        "",
    ]
    for cle in cles:
        glose = GLOSES.get(cle)
        if glose:
            lignes.append(f"# {glose}")
        lignes.append(f"{cle}=")
        lignes.append("")
    return "\n".join(lignes)


#: Le nom prescrit au projet. Une seule source pour ce nom : le répéter en littéral dans deux
#: fonctions ferait diverger la ligne écrite au `.gitignore` de celle qui est cherchée.
CONFIG = ".env.forge-tests"


def proteger(cible: Path | str) -> dict:
    """Garantit que le `.gitignore` du projet couvre `.env.forge-tests`, ou DIT pourquoi
    il ne l'est pas.

    Quatre issues, toutes nommées — un silence ne se distinguerait pas d'un oubli :
      · `deja` — une ligne le couvre déjà, rien à faire ;
      · `negation` — le `.gitignore` porte `!.env.forge-tests`, qui DÉS-IGNORE le fichier exprès.
        Elle n'est PAS retirée : quelqu'un l'a écrite. Elle est dénoncée avec sa ligne ;
      · `ajoutee` — la ligne manquait, elle est ajoutée (geste additif et réversible) ;
      · `impossible` — l'écriture a échoué, et l'erreur est rendue plutôt qu'avalée.
    """
    racine = Path(cible)
    chemin = racine / ".gitignore"
    lignes: list[str] = []
    if chemin.exists():
        try:
            lignes = chemin.read_text(encoding="utf-8").splitlines()
        except OSError as erreur:
            return {"etat": "impossible", "ligne": None,
                    "motif": f"`.gitignore` illisible : {erreur}"}

    for numero, brute in enumerate(lignes, start=1):
        nue = brute.strip()
        if nue == f"!{CONFIG}":
            return {
                "etat": "negation",
                "motif": (
                    f"`.gitignore:{numero}` porte `!{CONFIG}` — une NÉGATION, qui dés-ignore "
                    f"exprès un fichier porteur d'identifiants. Elle n'est pas retirée par la "
                    f"forge : quelqu'un l'a écrite et l'effacer serait décider à sa place. À "
                    f"retirer, puis `git rm --cached {CONFIG}` ; si le fichier est déjà publié, "
                    f"seule une rotation d'identifiant réduit le risque"
                ),
                "ligne": numero,
            }
        if nue == CONFIG or nue == f"/{CONFIG}":
            return {"etat": "deja", "ligne": numero,
                    "motif": f"`.gitignore:{numero}` couvre déjà `{CONFIG}`"}

    entete = "" if not lignes or lignes[-1].strip() == "" else "\n"
    ajout = (
        f"{entete}# Configuration d'audit forge-tests : porte des identifiants, jamais "
        "versionnée (TF-0620).\n"
        f"{CONFIG}\n"
    )
    try:
        with chemin.open("a", encoding="utf-8") as f:
            f.write(ajout)
    except OSError as erreur:
        return {"etat": "impossible", "ligne": None,
                "motif": f"écriture impossible dans `.gitignore` : {erreur}"}
    return {"etat": "ajoutee", "ligne": len(lignes) + 2,
            "motif": f"`{CONFIG}` ajouté au `.gitignore` du projet"}


def deposer(cible: Path | str, *, racine_forge: Path | str | None = None) -> dict:
    """Dépose le gabarit chez le projet audité, s'il y a lieu.

    Trois cas, tous rendus explicitement — un dépôt silencieux ne se distinguerait pas d'un oubli :
      · le projet a déjà `.env.forge-tests` → rien à faire, il est configuré ;
      · le gabarit est déjà là → rien à faire, il n'est pas réécrit (le projet a pu l'annoter) ;
      · sinon → dépôt, et le rapport le signale.
    """
    racine = Path(cible)
    if (racine / ".env.forge-tests").exists():
        return {"depose": False, "fichier": None,
                "motif": "le projet a déjà son `.env.forge-tests`"}
    destination = racine / FICHIER
    if destination.exists():
        return {"depose": False, "fichier": str(destination),
                "motif": f"`{FICHIER}` déjà présent — jamais réécrit, le projet a pu l'annoter"}
    try:
        destination.write_text(rendre(cles_connues(racine_forge)), encoding="utf-8")
    except OSError as erreur:
        return {"depose": False, "motif": f"dépôt impossible : {erreur}", "fichier": None}
    return {
        "depose": True,
        "motif": f"`{FICHIER}` déposé — le renommer en `.env.forge-tests` et le renseigner",
        "fichier": str(destination),
    }
