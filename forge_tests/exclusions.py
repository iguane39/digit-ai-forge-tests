r"""Source UNIQUE des exclusions de périmètre — quels chemins ne sont pas du produit.

Pourquoi ce module existe (TF-0536 / TF-0542 / TF-0543, lot Produit-02 du 23/08).

Le fait fondateur, mesuré : sur un audit réel, **12 des 15 constats portaient sur `input\\`** —
un dossier dont le nom seul dit qu'il contient de la matière d'entrée. Ont été audités comme
s'ils étaient du produit la page d'accueil d'un SITE CONCURRENT sauvegardée depuis un navigateur,
et une ANCIENNE version du site aspirée pour comparaison. Le pan `interface` sortait FAIL sur un
ratio de 0,9998 (18453/18456) : les trois affordances non exercées étaient les boutons de
carrousel du concurrent. Le produit réel ne portait AUCUN constat, et il a fallu un script de
dépouillement pour l'apprendre.

Le fait aggravant, mesuré à la correction : le dépôt portait **DIX** listes d'exclusion
divergentes (7 à 31 entrées), et `input` ne figurait dans **aucune**. `docs` n'était connu que
d'une seule, `output` de cinq sur dix. Chaque liste avait été étendue au fil d'un retour, jamais
les autres — RT-9/RT-10 du lot Produit-11 pour `output`, RT-4/TF-0218 du lot COMPTA pour
`forge\\`. C'est la troisième occurrence de la famille : le remède n'est pas d'ajouter une entrée
de plus à deux listes, c'est de n'en avoir qu'une.

CE QUE CE MODULE NE FAIT PAS, et c'est délibéré : il ne fusionne pas les dix listes en une seule
valeur. Certaines divergences sont LÉGITIMES — `mutation` exclut `tests` parce qu'un test n'est
pas une cible de mutation, `data` exclut `migrations` parce qu'un fichier de migration n'est pas
un modèle. Les écraser ferait taire des pans à raison. Le module fournit donc un SOCLE commun, et
chaque adaptateur y ajoute ce que son domaine justifie — en le motivant sur place.

Inversion de charge (TF-0536) : l'INCLUSION d'un de ces dossiers est le geste explicite du
projet, jamais l'exclusion. Un projet qui veut réellement auditer son `input\` le déclare par
``FORGE_TESTS_INCLURE`` ; sans déclaration, il est hors périmètre.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# --- socle : ce que produit l'outillage, jamais le produit -------------------------------------
# Environnements, caches, dépendances vendues, sorties de build. Aucun de ces dossiers n'est
# écrit à la main par quelqu'un du projet : un constat qui s'y trouve n'a personne à qui parler.
OUTILLAGE: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "site-packages", "vendor",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".eggs",
    ".next", ".nuxt", ".svelte-kit", "build", "dist", "out", "coverage", "htmlcov",
    ".idea", ".vscode", ".claude",
})

# --- ce qui n'est PAS le produit, même si c'est écrit à la main --------------------------------
# `input` est ici, et c'est tout l'objet de TF-0536 : de la matière d'ENTRÉE — briefs, sites
# concurrents aspirés, anciennes versions gardées pour comparaison. Auditer ces fichiers revient
# à reprocher au projet les défauts de quelqu'un d'autre.
HORS_PRODUIT: frozenset[str] = frozenset({
    "input",      # matière d'entrée : jamais du produit (TF-0536, 12 constats sur 15)
    "output",     # livrables générés (RT-9/RT-10, lot Produit-11 20260814a)
    "docs",       # documentation, jugée par ses propres règles et non par les pans de code
    "Old", "old",  # versions remplacées, gardées pour mémoire
    "forge",      # l'arbre de la forge chez le produit (RT-4/TF-0218, lot COMPTA 20260814a)
    ".forge", ".oracles", ".visuel",  # journaux et manifestes d'outillage
    "runs",       # journaux de run : des traces, pas du produit
})

# --- artefacts de sauvegarde navigateur ---------------------------------------------------------
# Une page « enregistrée sous » depuis un navigateur produit un `<nom>_files\` plein de CSS et de
# JS réécrits par le navigateur lui-même. Les juger, c'est auditer Chrome.
# TF-0537 (lot Produit-02 du 23/08) : L ACCENT MANQUAIT, et il coutait NEUF constats
# bloquants. Le navigateur francais nomme le fichier en cours de telechargement
# « weglot.min.js.telechargement » AVEC ses accents ; le motif ecrit sans accent ne
# correspondait a rien. Les deux graphies sont donc declarees, et la lecon vaut au-dela de ce
# motif : un nom de fichier produit par un logiciel LOCALISE ne s ecrit pas de memoire.
MOTIFS_ASPIRES: tuple[str, ...] = (
    "_files",
    ".telechargement", ".téléchargement",
    ".download", ".crdownload",
)

# Les MEMES artefacts, en motifs de nom de FICHIER cette fois. `dossier_exclu` ne juge que des
# noms de dossier ; un `weglot.min.js.telechargement` pose a plat, ou un `saved_resource` sans
# extension, traversait donc le filtre. Ces motifs se donnent tels quels a
# `shutil.ignore_patterns`, qui les applique aux fichiers comme aux dossiers.
MOTIFS_FICHIERS_ASPIRES: tuple[str, ...] = (
    "*.telechargement", "*.téléchargement", "*.download", "*.crdownload",
    "*_files", "saved_resource*",
)

# Marqueur que les navigateurs écrivent en tête d'une page sauvegardée. Sa présence dit, sans
# ambiguïté et sans configuration, que ce fichier vient d'ailleurs.
_MARQUEUR_ASPIREE = re.compile(rb"saved from url", re.IGNORECASE)


def _inclus_declares() -> frozenset[str]:
    r"""Ce que le projet réclame EXPLICITEMENT dans le périmètre, malgré le défaut.

    Inversion de charge : sans déclaration, `input\\` est dehors. Un projet qui a une vraie
    raison de l'auditer l'écrit, et cette écriture est la trace de sa décision.
    """
    brut = os.environ.get("FORGE_TESTS_INCLURE", "")
    return frozenset(p.strip() for p in brut.replace(";", ",").split(",") if p.strip())


def socle(*, avec_hors_produit: bool = True) -> frozenset[str]:
    r"""Le socle d'exclusions, moins ce que le projet a explicitement réclamé.

    `avec_hors_produit=False` sert aux pans qui doivent voir `docs\\` ou `output\\` — le pan i18n
    juge des pages livrées, par exemple. Le choix se motive sur place, il n'est pas deviné ici.
    """
    base = OUTILLAGE | (HORS_PRODUIT if avec_hors_produit else frozenset())
    return frozenset(base - _inclus_declares())


def dossier_exclu(nom: str, *, avec_hors_produit: bool = True) -> bool:
    r"""Un NOM de dossier est-il hors périmètre ?

    Comparaison EXACTE, comme les listes d'origine.
    """
    if nom in _inclus_declares():
        return False
    return nom in socle(avec_hors_produit=avec_hors_produit) or nom.endswith(MOTIFS_ASPIRES)


def chemin_exclu(chemin: os.PathLike[str] | str, *, avec_hors_produit: bool = True) -> bool:
    r"""Un CHEMIN traverse-t-il un segment hors périmètre ?"""
    return any(dossier_exclu(p, avec_hors_produit=avec_hors_produit) for p in Path(chemin).parts)


# --- ce que le dépôt lui-même déclare hors de lui : `.gitignore` ------------------------------
# TF-1767 (lot Produit-82 du 15/10/2026, RT-16) : lancé sur la racine du produit, l audit a
# inventorié et jugé `vendor-check/`, un clone du code amont ignoré par git. 493 constats sur un
# autre code, presque tous sur ses tests et son interface ; seule la mutation savait exclure un
# chemin. Un dossier que le dépôt ignore n est pas versionné, donc pas livré : ce n est pas du
# produit. Il sort du périmètre PAR DÉFAUT, nommé au rapport (`perimetre_exclu_git`).
#
# Ce filtre ne retire QUE ce que les listes de noms ne couvrent pas déjà : un `dist/` ou un
# `node_modules/` ignorés par git restent soumis à la politique de chaque pan (le catalogue i18n
# lit `dist/` à dessein). Inclusion explicite : le nom du dossier dans `FORGE_TESTS_INCLURE`.
_CACHE_GIT: dict[str, tuple[str, tuple[str, ...]]] = {}


def _normal(chemin: os.PathLike[str] | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(chemin)))


def _ignores_du_depot(racine: os.PathLike[str] | str) -> tuple[str, tuple[str, ...]]:
    """(racine git normalisée, dossiers ignorés en chemins absolus normalisés), en cache."""
    import subprocess

    cle = _normal(racine)
    if cle in _CACHE_GIT:
        return _CACHE_GIT[cle]
    resultat: tuple[str, tuple[str, ...]] = ("", ())
    try:
        haut = subprocess.run(
            ["git", "-C", cle, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if haut.returncode == 0 and haut.stdout.strip():
            depot = haut.stdout.strip()
            liste = subprocess.run(
                ["git", "-C", depot, "ls-files", "--others", "--ignored", "--exclude-standard",
                 "--directory", "-z"],
                capture_output=True, text=True, timeout=120, check=False,
                encoding="utf-8", errors="replace",
            )
            if liste.returncode == 0:
                noms_geres = OUTILLAGE | HORS_PRODUIT
                inclus = _inclus_declares()
                dossiers = []
                for brut in liste.stdout.split("\0"):
                    if not brut.endswith("/"):
                        continue  # un fichier ignoré isolé ne porte pas un autre code
                    relatif = brut.rstrip("/")
                    nom = relatif.rsplit("/", 1)[-1]
                    if nom in noms_geres or nom in inclus or nom.endswith(MOTIFS_ASPIRES):
                        continue
                    absolu = _normal(os.path.join(depot, relatif))
                    # Seuls les dossiers SOUS la racine auditée : une racine logée elle-même dans
                    # un dossier ignoré d un dépôt parent ne s exclut pas d elle-même.
                    if absolu.startswith(cle + os.sep):
                        dossiers.append(absolu)
                resultat = (_normal(depot), tuple(sorted(dossiers)))
    except (OSError, subprocess.SubprocessError):
        resultat = ("", ())
    _CACHE_GIT[cle] = resultat
    return resultat


def ignore_par_git(chemin: os.PathLike[str] | str, racine: os.PathLike[str] | str) -> bool:
    """`chemin` est-il sous un dossier que le dépôt de `racine` ignore (hors noms déjà gérés) ?"""
    _depot, dossiers = _ignores_du_depot(racine)
    if not dossiers:
        return False
    cible = _normal(chemin)
    return any(cible == d or cible.startswith(d + os.sep) for d in dossiers)


def ignores_git(racine: os.PathLike[str] | str) -> list[str]:
    """Les dossiers exclus par `.gitignore`, relatifs à `racine`, pour publication au rapport."""
    _depot, dossiers = _ignores_du_depot(racine)
    base = _normal(racine)
    sortie = []
    for d in dossiers:
        if d == base or d.startswith(base + os.sep):
            sortie.append(Path(os.path.relpath(d, base)).as_posix())
    return sortie


def est_page_aspiree(chemin: os.PathLike[str] | str) -> bool:
    r"""La page porte-t-elle le marqueur d'une sauvegarde navigateur ?

    Lu sur les premiers octets seulement : le marqueur vit en tête, et lire un fichier entier
    pour cette question coûterait plus qu'elle ne rapporte. Illisible ou binaire → False, parce
    qu'un doute ne doit pas retirer un fichier du périmètre en silence.
    """
    try:
        with open(chemin, "rb") as f:
            return bool(_MARQUEUR_ASPIREE.search(f.read(4096)))
    except OSError:
        return False
