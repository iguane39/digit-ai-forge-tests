"""Disposition des sources du projet audité — où vit son paquet Python.

Le framework a longtemps tenu `backend/app` pour acquis : `coverage run --source=app,tests`
dans `execution.py`, `DOSSIER_SOURCE = backend/app` dans l adaptateur de mutation, et les
chemins conventionnels des pans `batch` et `fichiers`. Un projet dont le paquet s appelle
autrement voyait donc SIX pans plafonnés à `SKIP` quelles que soient sa suite et sa couverture
— et le motif publié parlait d un environnement Python absent, ce qui envoyait chercher un
problème qui n existait pas.

Constaté le 12/08/2026 sur Produit-11, dont le paquet s appelle `src` : suite verte
de 116 tests, couverture de branches à 94 %, et pourtant `mutation : aucun dossier de sources
sous backend/app`. La preuve que seul le NOM était en cause a été faite par contre-oracle —
le moteur de mutation joué sur `backend/src` puis sur une copie renommée `backend/app` rend
exactement les mêmes chiffres : 189 mutants viables, 20 tués, score 0,1058.

Le parti pris suit celui de TF-0097 : on DÉCOUVRE la disposition du projet, on ne lui impose
pas la nôtre. `FORGE_TESTS_SOURCES` n est qu un dernier recours, pour le cas ambigu que la
découverte refuse de trancher — et quand elle le refuse, elle le DIT au lieu de deviner.

TF-0216 (14/08/2026, lot COMPTA) : TF-0097 n avait résolu que le NOM du paquet, pas son ANCRE.
`<cible>/backend` restait en dur ici, dans `execution.py` (`cwd=`) et dans l adaptateur
`securite`. Sur un produit FastAPI + Jinja2 à RACINE PLATE (`app/`, `tests/`, `.venv/` à la
racine, sans `backend/`) — disposition très répandue — SEPT pans sortaient non mesurables (api,
data, migrations, batch, fichiers, back, securite) alors que la suite pytest était verte à 74
tests et l app factory standard.

La racine d EXÉCUTION se découvre donc comme le paquet : candidats essayés dans un ORDRE FIXE
(`<cible>/backend`, puis `<cible>`), premier candidat portant un indice retenu — un `tests/`,
un `pyproject.toml`, un `.venv/`, un paquet Python. Deux exigences de méthode, sans quoi le
remède serait pire que l ancre en dur :

  - **déterminisme** — l ordre ne dépend d aucun parcours de disque ni d aucune heuristique de
    score ; à disposition égale, deux projets rendent la même décision ;
  - **déclaration** — `motif_racine_execution()` publie la racine RETENUE, la règle qui l a
    choisie et les candidats essayés avec leurs indices. Un choix implicite qui changerait d un
    projet à l autre sans le dire serait un silence, exactement ce que ce module existe pour ôter.

`FORGE_TESTS_SOURCES` en chemin ABSOLU vaut base complète : son parent devient la racine
d exécution (cwd compris), ce qui couvre les dispositions qu aucune convention ne décrit.
"""

from __future__ import annotations

import os
from pathlib import Path

# Ce qui vit sous la racine d exécution sans être le paquet du produit. `tests` en fait partie :
# la suite n est pas la source qu on mute, et `coverage` la reçoit déjà par ailleurs.
# TF-0216 : la découverte pouvant désormais s exercer à la RACINE DU DÉPÔT (projet plat), les
# dossiers de la convention pilot (`forge/`, `output/`, `old/`, `.oracles/`) et le front y sont
# ajoutés — ils ne sont jamais le paquet du produit, et les y laisser fabriquerait des
# ambiguïtés là où la disposition est en réalité limpide.
_HORS_SOURCES = {
    ".venv", "venv", "env", "node_modules", "__pycache__", "tests", "test",
    "migrations", "alembic", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "requirements", "scripts", "docs", ".idea", ".vscode", "htmlcov", "build", "dist",
    ".eggs", "site-packages",
    "forge", "output", "old", "Old", ".oracles", "frontend", ".claude", ".github",
}

# Essayés dans cet ordre avant toute découverte : deux conventions largement répandues.
_CONVENTIONS = ("app", "src")


def _candidats(racine: Path) -> list[Path]:
    """Dossiers de la racine d exécution qui ressemblent à un paquet Python du projet."""
    if not racine.is_dir():
        return []
    retenus = []
    for entree in sorted(racine.iterdir()):
        if not entree.is_dir() or entree.name in _HORS_SOURCES or entree.name.startswith("."):
            continue
        if next(entree.rglob("*.py"), None) is not None:
            retenus.append(entree)
    return retenus


# Indices qu un dossier est la RACINE D EXÉCUTION du projet — celui depuis lequel sa suite se
# lance et sous lequel vit son paquet. Aucun n est requis seul : c est leur PRÉSENCE qui compte
# et l ordre des candidats qui tranche. Éprouvés dans cet ordre pour que le libellé publié soit
# lui aussi stable d un projet à l autre.
_INDICES_RACINE: tuple[tuple[str, str], ...] = (
    ("tests/", "dossier"),
    ("test/", "dossier"),
    ("pyproject.toml", "fichier"),
    (".venv/", "dossier"),
    ("venv/", "dossier"),
    ("paquet Python", "paquet"),
)

# L ordre des candidats. `backend` D ABORD : la disposition historique reste prioritaire, si
# bien qu aucun projet déjà mesuré ne change de racine du fait de TF-0216. `.` ensuite : la
# racine plate, qui n était jusque-là jamais essayée.
_ORDRE_CANDIDATS = ("backend", ".")


def _indices(dossier: Path) -> list[str]:
    """Indices de racine d exécution portés par ce dossier, dans l ordre canonique."""
    if not dossier.is_dir():
        return []
    trouves: list[str] = []
    for nom, genre in _INDICES_RACINE:
        if genre == "paquet":
            present = bool(_candidats(dossier))
        elif genre == "fichier":
            present = (dossier / nom).is_file()
        else:
            present = (dossier / nom.rstrip("/")).is_dir()
        if present:
            trouves.append(nom)
    return trouves


#: TF-0401 (RF-3, lot Produit-09 20260820a) — le manifeste OPPOSABLE du projet. Le pilot présente
#: P-18 comme primant sur toute détection ; jusqu'ici AUCUN code de cette forge ne le lisait
#: (0 occurrence, relevé du 20/08) : les racines étaient en dur (`backend`, `.`, `frontend`),
#: et une arborescence `back/` + `front/` — celle du produit SCC.FR — n'était pas vue, quel que
#: soit le manifeste livré. Un audit pouvait mesurer un dossier vide et rendre un verdict
#: d'apparence normale.
#:
#: Schéma minimal, défini ici faute d'exister ailleurs (le manifeste du conducteur porte le
#: PROFIL, pas les racines) :
#:
#:     [racines]
#:     execution = "back"    # racine d'exécution de la suite (l'« ancre backend »)
#:     front = "front"       # racine du front
#:
#: Cascade : déclaration OPÉRATEUR (FORGE_TESTS_SOURCES, geste explicite au run) > manifeste
#: PROJET > indices du disque > repli déclaré. Un manifeste illisible ou une racine déclarée
#: absente du disque se DISENT — jamais un repli silencieux vers la détection : le silence est
#: exactement ce que le retour a payé.
MANIFESTE_RELATIF = Path(".forge") / "profile.toml"


def racines_declarees(cible: Path) -> tuple[dict[str, str], str | None]:
    """({execution, front} déclarées par le manifeste, motif d'illisibilité éventuel)."""
    manifeste = cible / MANIFESTE_RELATIF
    if not manifeste.is_file():
        return {}, None
    import tomllib

    try:
        donnees = tomllib.loads(manifeste.read_text(encoding="utf-8", errors="replace"))
    except tomllib.TOMLDecodeError as erreur:
        return {}, (
            f"manifeste `{MANIFESTE_RELATIF.as_posix()}` present mais ILLISIBLE ({erreur}) — "
            "il est ignore EN LE DISANT, jamais en silence"
        )
    racines = donnees.get("racines") or {}
    return (
        {cle: str(racines[cle]) for cle in ("execution", "front") if racines.get(cle)},
        None,
    )


def _declaration() -> str:
    return (os.environ.get("FORGE_TESTS_SOURCES") or "").strip()


def _base_declaree() -> Path | None:
    """`FORGE_TESTS_SOURCES` en chemin ABSOLU existant — base complète, cwd compris.

    Un chemin absolu ne se lit pas comme un nom de paquet sous une ancre supposée : il DÉSIGNE
    le paquet, donc son parent désigne la racine d exécution. C est la porte de sortie pour
    toute disposition qu aucune convention ne décrit.
    """
    declare = _declaration()
    if not declare:
        return None
    chemin = Path(declare)
    return chemin if chemin.is_absolute() and chemin.is_dir() else None


def _decider_racine(cible: Path) -> tuple[Path, str, list[tuple[Path, bool, list[str]]]]:
    """(racine retenue, règle qui l a choisie, candidats essayés) — décision DÉTERMINISTE.

    Rien n est deviné en silence : le troisième membre porte la trace complète, que
    `motif_racine_execution` publie telle quelle.
    """
    essais = [
        (candidat, candidat.is_dir(), _indices(candidat))
        for candidat in (
            cible / nom if nom != "." else cible for nom in _ORDRE_CANDIDATS
        )
    ]
    base = _base_declaree()
    if base is not None:
        return (
            base.parent,
            f"declaree par FORGE_TESTS_SOURCES={str(base)!r} (chemin absolu : base complete)",
            essais,
        )
    # TF-0401 — le manifeste du PROJET, après l'opérateur et avant toute détection. Une racine
    # déclarée qui n'existe pas sur le disque est RENDUE quand même, avec un motif qui le dit :
    # retomber en silence sur la détection referait exactement le défaut mesuré (un manifeste
    # livré et ignoré).
    declarees, motif_manifeste = racines_declarees(cible)
    if declarees.get("execution"):
        racine = cible / declarees["execution"]
        return (
            racine,
            f"declaree par le manifeste `{MANIFESTE_RELATIF.as_posix()}` "
            f"([racines] execution = {declarees['execution']!r})"
            + ("" if racine.is_dir() else " — ATTENTION : ce dossier N EXISTE PAS sur le disque, "
               "le manifeste et l arborescence se contredisent"),
            essais,
        )
    if motif_manifeste:
        essais = [*essais]  # le motif d illisibilité voyage avec la trace publiée
    for candidat, _existe, indices in essais:
        if indices:
            return candidat, f"indices trouves — {', '.join(indices)}", essais
    prefixe = (motif_manifeste + " ; ") if motif_manifeste else ""
    return (
        cible / "backend",
        prefixe
        + "aucun candidat ne porte d indice de racine d execution — repli DECLARE sur l ancre "
        "historique `backend`",
        essais,
    )


def racine_execution(cible: Path) -> Path:
    """Dossier depuis lequel la suite du projet se lance — jamais `backend` supposé.

    Toujours un chemin (jamais None) : c est une ANCRE, pas une mesure. Quand aucun candidat
    ne porte d indice, le repli sur `backend` est rendu tel quel et `motif_racine_execution`
    dit que c est un repli — l appelant publie alors un motif exact au lieu d un chemin muet.
    """
    return _decider_racine(cible)[0]


def motif_racine_execution(cible: Path) -> str:
    """Phrase publiable au rapport : quelle racine a été retenue, par quelle règle, sur quoi.

    Le garde-fou de méthode de TF-0216 : une découverte qui change d un projet à l autre DOIT
    dire ce qu elle a choisi. Cette phrase est le canal de cette déclaration.
    """
    racine, regle, essais = _decider_racine(cible)
    detail = " ; ".join(
        f"{chemin} ({'absent' if not existe else (', '.join(indices) or 'aucun indice')})"
        for chemin, existe, indices in essais
    )
    return (
        f"racine d execution retenue : {racine} — {regle} ; candidats essayes dans l ordre : "
        f"{detail}"
    )


def paquet_sources(cible: Path) -> Path | None:
    """Racine des sources Python du projet, ou None si elle n est pas déterminable.

    Ordre : déclaration explicite, puis conventions (`app`, `src`), puis découverte quand
    elle ne laisse qu un seul candidat. Plusieurs candidats — un vrai paquet et un dossier
    d outillage, par exemple — ne se départagent pas sans risque : on rend None, et l appelant
    publie le motif.

    TF-0216 : l ancre n est plus `<cible>/backend` en dur mais la racine DÉCOUVERTE.
    """
    racine = racine_execution(cible)

    declare = _declaration()
    if declare:
        chemin = Path(declare)
        chemin = chemin if chemin.is_absolute() else racine / chemin
        return chemin if chemin.is_dir() else None

    for nom in _CONVENTIONS:
        if (racine / nom).is_dir():
            return racine / nom

    candidats = _candidats(racine)
    return candidats[0] if len(candidats) == 1 else None


def nom_paquet_sources(cible: Path) -> str | None:
    """Nom du paquet, tel que `coverage --source=` l attend."""
    dossier = paquet_sources(cible)
    return None if dossier is None else dossier.name


def motif_indetermine(cible: Path) -> str:
    """Pourquoi la disposition n a pas pu être tranchée — jamais un silence.

    Le motif NOMME désormais la racine d exécution retenue : sans elle, « aucun paquet Python
    sous … » laissait le lecteur ignorer SOUS QUOI la forge avait cherché.
    """
    racine = racine_execution(cible)
    declare = _declaration()
    if declare:
        return (
            f"FORGE_TESTS_SOURCES={declare!r} ne designe aucun dossier existant "
            f"(attendu sous {racine} ou en chemin absolu) — "
            f"{motif_racine_execution(cible)}"
        )
    if not racine.is_dir():
        # Le repli sur `backend` n a pas de dossier derrière lui, et la racine plate ne portait
        # aucun indice : les DEUX candidats sont nommés, pas seulement l ancre historique.
        return (
            f"aucun dossier `backend` sous {cible}, et {cible} ne porte aucun indice de racine "
            f"d execution ({', '.join(nom for nom, _ in _INDICES_RACINE)}) — "
            f"{motif_racine_execution(cible)}"
        )
    candidats = _candidats(racine)
    if not candidats:
        return (
            f"aucun paquet Python sous {racine} : ni `app`, ni `src`, ni aucun dossier "
            "portant des modules"
        )
    return (
        "plusieurs paquets Python possibles sous "
        f"{racine} — {', '.join(c.name for c in candidats)} ; "
        "declarer celui du produit par FORGE_TESTS_SOURCES=<nom>"
    )
