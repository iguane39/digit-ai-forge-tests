"""Qualification — ce qui n a pas pu être exercé FAUTE DE CONFIGURATION (RT-6a).

Le rapport savait dire deux choses : « exercé » et « jamais exercé ». Il manquait la
troisième, et c est la seule que l humain peut RÉPARER en une minute : « personne ne pouvait
l exercer ici, il manque un identifiant ». Confondue avec la deuxième, elle produit un
reproche adressé au projet pour une carence de l environnement d audit ; confondue avec un
`non_juge`, elle disparaît dans une liste de limites permanentes alors qu elle est temporaire.

Ce module la nomme, avec les CHAMPS À FOURNIR. Trois sources, de la plus sûre à la plus
prudente :

  1. **constaté** — la sortie d exécution CITE une variable d environnement absente
     (`KeyError: 'X'`, `X is not set`, `Field required`, `Skipped: … X …`). C est un fait ;
  2. **constaté** — un adaptateur déclare lui-même ce qui lui manque (l authentification
     déclare `FORGE_TESTS_LOGIN` / `…_PASSWORD` quand aucun compte n est configuré) ;
  3. **présumé** — le projet audité déclare ses propres clés dans un `.env.example` et
     l environnement ne les porte pas. Aucune exécution ne l a dit : la provenance est
     marquée comme telle, jamais confondue avec un constat.

Un nom n est retenu que s il est ABSENT ou VIDE dans l environnement courant : une variable
citée mais correctement fournie n est pas un manque, c est du bruit de trace.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from forge_tests.noyau import NonTestable, SortieAdaptateur

NON_JUGE = [
    "qualification : un manque de configuration n est reconnu que s il se DIT — variable citee "
    "par une trace d execution, declaration d adaptateur, ou cle d un `.env.example` du projet. "
    "Un service tiers injoignable sans jamais nommer sa cle reste un pan non mesure ordinaire",
    "qualification : les champs tires d un `.env.example` sont PRESUMES requis (le fichier ne "
    "dit pas quel pan depend de quelle cle) — la provenance de chaque entree le declare",
]

# Domaines de configuration consultés par pan. « acces » porte ce qui ouvre une instance
# SERVIE (URL, compte) ; « backend » et « front » ce que chaque suite exige pour tourner.
_DOMAINES_PAR_PAN: dict[str, tuple[str, ...]] = {
    "front": ("front", "acces"),
    "accessibilite": ("front", "acces"),
    "visuel": ("front", "acces"),
    # Le pan interface est un contrôle STATIQUE de fichiers : aucune configuration ne le débloque.
    "interface": (),
}
_DOMAINES_DEFAUT = ("backend", "acces")

_EXEMPLES = (
    ".env.example", ".env.exemple", ".env.sample", ".env.template", ".env.dist",
    "backend/.env.example", "backend/.env.exemple", "backend/.env.sample",
)

_NOM = r"[A-Z][A-Z0-9_]{2,}"
_MOTIFS = (
    re.compile(rf"KeyError:\s*['\"]({_NOM})['\"]"),
    re.compile(rf"environ(?:\.get)?\(\s*['\"]({_NOM})['\"]"),
    re.compile(rf"getenv\(\s*['\"]({_NOM})['\"]"),
    re.compile(rf"(?:environment variable|variable d.environnement)\s+['\"]?({_NOM})"),
    re.compile(
        rf"\b({_NOM})\b\s*(?:is not set|is required|must be set|not configured"
        r"|n est pas d[eé]finie?|non d[eé]finie?|manquante?)"
    ),
    re.compile(
        rf"(?:Missing|missing|Manque|absente?)\s+(?:required\s+)?(?:environment\s+)?"
        rf"(?:variable|secret|cl[eé]|jeton|token|credential)s?\s*:?\s*['\"]?({_NOM})"
    ),
    # pydantic-settings : le nom du champ tient sa propre ligne, l explication la suivante.
    re.compile(rf"^\s*({_NOM})\s*$\n\s*(?:Field required|field required)", re.MULTILINE),
    re.compile(rf"(?:SKIPPED|Skipped).{{0,120}}?\b({_NOM})\b"),
)

# (cible, domaine) -> champs déclarés manquants, avec leur provenance.
_REQUIS: dict[tuple[str, str], dict[str, str]] = {}


def _cle(cible: Path | str) -> str:
    """Clé de registre normalisée : `Path` et `str` du même projet doivent se rejoindre.

    Sans cela, une déclaration faite depuis `execution` (qui manipule des `Path`) restait
    invisible à la qualification appelée avec la même cible sous une autre forme — le manque
    de configuration était détecté puis silencieusement perdu.
    """
    return str(Path(cible))


def _absent(nom: str) -> bool:
    return not (os.environ.get(nom) or "").strip()


def declarer(cible: Path | str, domaine: str, champs: object, provenance: str = "constate") -> None:
    """Enregistre des champs de configuration manquants pour (projet, domaine)."""
    retenus = {nom for nom in champs if _absent(nom)}
    if not retenus:
        return
    entree = _REQUIS.setdefault((_cle(cible), domaine), {})
    for nom in retenus:
        entree.setdefault(nom, provenance)


def detecter(cible: Path | str, domaine: str, texte: str) -> set[str]:
    """Noms de variables d environnement ABSENTES cités par une sortie d exécution.

    Appelé sur la trace d un run en échec : c est le seul moment où le projet dit lui-même ce
    qui lui manque. Le filtre « absente de l environnement » écarte les mentions de variables
    correctement fournies, qui ne sont pas des manques.
    """
    if not texte:
        return set()
    trouves = {nom for motif in _MOTIFS for nom in motif.findall(texte) if _absent(nom)}
    # Les faux amis les plus courants d une trace Python : ce ne sont pas des secrets.
    trouves -= {"PATH", "PYTHONPATH", "TERM", "HOME", "TMPDIR", "LANG", "TZ", "CI"}
    if trouves:
        declarer(cible, domaine, trouves)
    return trouves


def champs_presumes(cible: Path) -> list[str]:
    """Clés que le projet DÉCLARE attendre (`.env.example`…) et que l environnement n a pas."""
    noms: list[str] = []
    for relatif in _EXEMPLES:
        fichier = cible / relatif
        if not fichier.is_file():
            continue
        for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            nom = ligne.partition("=")[0].strip()
            if re.fullmatch(_NOM, nom) and _absent(nom) and nom not in noms:
                noms.append(nom)
    return noms


def requis(cible: Path | str, *domaines: str) -> dict[str, str]:
    """Champs manquants déclarés pour ces domaines, nom -> provenance."""
    fusion: dict[str, str] = {}
    for domaine in domaines:
        for nom, provenance in _REQUIS.get((_cle(cible), domaine), {}).items():
            fusion.setdefault(nom, provenance)
    return fusion


def oublier(cible: Path | str) -> None:
    """Vide le registre d un projet — utile entre deux analyses dans un même processus."""
    for cle in [c for c in _REQUIS if c[0] == _cle(cible)]:
        del _REQUIS[cle]


def qualifier(
    sorties: list[SortieAdaptateur], cible: Path, registre: dict[str, object]
) -> list[SortieAdaptateur]:
    """Remplit `non_testables` sur les sorties dont la mesure était IMPOSSIBLE ici.

    Point d application UNIQUE, au-dessus de tous les adaptateurs : aucun n a à connaître le
    mécanisme, et un adaptateur futur en hérite sans une ligne. Un adaptateur qui sait mieux
    reste libre de remplir `non_testables` lui-même — ce qui est déjà déclaré n est pas écrasé.
    """
    modules = {module.PAN: module for module in registre.values() if hasattr(module, "PAN")}
    presumes = champs_presumes(cible)
    for sortie in sorties:
        if sortie.non_testables or sortie.verdict != "SKIP":
            continue
        domaines = _DOMAINES_PAR_PAN.get(sortie.pan, _DOMAINES_DEFAUT)
        if not domaines:
            continue
        champs = requis(cible, *domaines)
        provenance = "constate"
        if not champs and presumes:
            champs = dict.fromkeys(presumes, "presume")
            provenance = "presume"
        if not champs:
            continue
        requis_tries = sorted(champs)
        motif = (
            f"{sortie.pan} : non exercable sans configuration ({provenance}) — "
            f"fournir {', '.join(requis_tries)}, puis `--reprendre` le rapport"
        )
        module = modules.get(sortie.pan)
        inventaire = getattr(module, "inventaire", None)
        elements = [e.id for e in inventaire(cible)] if inventaire is not None else []
        # Un pan dont rien n est meme enumerable reste NOMME : une entree pour le pan entier,
        # plutot qu un silence qui ressemblerait a « rien a tester ici ».
        for identifiant in elements or [f"pan:{sortie.pan}"]:
            sortie.non_testables.append(
                NonTestable(
                    element=identifiant,
                    champs_requis=requis_tries,
                    pan=sortie.pan,
                    motif=motif,
                )
            )
    return sorties
