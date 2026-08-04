"""Adaptateur Mutation (Python) — second contre-oracle : ce qu on atteint, le vérifie-t-on ?

Mutation réellement exécutée : on altère la source, on relance la suite, on compte les
survivants. Un mutant survivant est nommé avec sa ligne — jamais un total agrégé seul.

P6 : le périmètre couvre désormais TOUS les modules applicatifs, plus le seul module de
calcul, et les opérateurs de comparaison s ajoutent aux opérateurs arithmétiques. Le nombre
de mutants est plafonné pour borner la durée — et le plafond atteint est DÉCLARÉ, jamais
une troncature silencieuse.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN, SEUIL = "mutation-python", "back", 0.70
DOSSIER_SOURCE = Path("backend/app")
SUITE = "tests"
PLAFOND_MUTANTS = 90

NON_JUGE = [
    "mutation : les mutants équivalents ne sont pas détectés — un survivant peut être un mutant "
    "sémantiquement identique à l original",
    "mutation : opérateurs arithmétiques, de comparaison, booléens, d appartenance, bornes "
    "numériques et suppression d instruction ; ni permutation d arguments, ni littéraux non "
    "numériques",
]

_SUBSTITUTIONS = (("+", "-"), ("-", "+"), ("*", "/"), ("/", "*"))
_COMPARAISONS = (
    (" < ", " <= "),
    (" > ", " >= "),
    (" == ", " != "),
    (" != ", " == "),
    (" <= ", " < "),
    (" >= ", " > "),
    (" and ", " or "),
    (" or ", " and "),
    (" in ", " not in "),
    (" is not ", " is "),
)
# Litteraux numeriques : decaler une borne revele les tests qui ne verifient que le sens.
_BORNES = ((" 0", " 1"), (" 1", " 0"), (" 100", " 99"))


@dataclass(frozen=True)
class Mutant:
    fichier: str
    ligne: int
    colonne: int
    avant: str
    apres: str

    @property
    def id(self) -> str:
        return f"mutant:{self.fichier}:{self.ligne + 1}:{self.avant.strip()}->{self.apres.strip()}"


def _lignes_calculantes(lignes: list[str]) -> list[int]:
    """Lignes portant du code EXÉCUTABLE, hors docstrings.

    Muter l intérieur d une docstring produit un mutant équivalent par construction, qui
    survit toujours et fait chuter le score sans rien signaler de vrai.
    """
    retenues: list[int] = []
    dans_docstring = False
    for i, ligne in enumerate(lignes):
        nu = ligne.strip()
        marqueurs = nu.count('"""') + nu.count("'''")
        if dans_docstring:
            if marqueurs:
                dans_docstring = False
            continue
        if marqueurs == 1:
            dans_docstring = True
            continue
        if marqueurs >= 2 or not nu or nu.startswith(("#", "from ", "import ", "@")):
            continue
        retenues.append(i)
    return retenues


def _zones_litterales(texte: str) -> dict[int, list[tuple[int, int]]]:
    """Plages de colonnes occupées par des chaînes et des commentaires, par ligne (0-indexée).

    Muter à l intérieur d une chaîne ne mute pas du CODE. Pire : quand la même constante sert
    au code et au test (« REJ-VIDE », « utf-8 »), le mutant est équivalent par construction et
    survit toujours — il fait chuter le score sans jamais désigner une faiblesse de la suite.
    """
    import io
    import tokenize

    zones: dict[int, list[tuple[int, int]]] = {}
    try:
        jetons = list(tokenize.generate_tokens(io.StringIO(texte).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return zones
    for jeton in jetons:
        if jeton.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (ligne_debut, col_debut), (ligne_fin, col_fin) = jeton.start, jeton.end
        for ligne in range(ligne_debut, ligne_fin + 1):
            debut = col_debut if ligne == ligne_debut else 0
            fin = col_fin if ligne == ligne_fin else 10**6
            zones.setdefault(ligne - 1, []).append((debut, fin))
    return zones


def generer_mutants(source: Path, nom_court: str) -> list[Mutant]:
    texte = source.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    zones = _zones_litterales(texte)

    def dans_litteral(ligne: int, colonne: int) -> bool:
        return any(debut <= colonne < fin for debut, fin in zones.get(ligne, ()))

    mutants: list[Mutant] = []
    for i in _lignes_calculantes(lignes):
        ligne = lignes[i]
        for avant, apres in (*_COMPARAISONS, *_BORNES):
            position = ligne.find(avant)
            if position >= 0 and not dans_litteral(i, position + 1):
                mutants.append(Mutant(nom_court, i, position, avant, apres))
        for j, caractere in enumerate(ligne):
            if dans_litteral(i, j):
                continue
            for avant, apres in _SUBSTITUTIONS:
                if caractere == avant:
                    mutants.append(Mutant(nom_court, i, j, avant, apres))
        # Suppression d instruction : neutraliser un appel dont le retour n est pas utilise.
        # Un test qui ne verifie que l absence d exception ne le remarque jamais.
        nu = ligne.strip()
        if nu.endswith(")") and "=" not in nu and not nu.startswith(("return", "raise", "assert")):
            indentation = len(ligne) - len(ligne.lstrip())
            mutants.append(Mutant(nom_court, i, indentation, nu[:1], "pass  # "))
    return mutants


def _purger_bytecode(racine: Path) -> None:
    """Un mutant a la MÊME TAILLE que l original ; si la restauration tombe dans la même
    seconde, Python réutilise un .pyc périmé et la suite juge un code qui n existe plus."""
    for cache in racine.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _suite_verte(racine: Path, python: Path) -> bool:
    _purger_bytecode(racine)
    resultat = subprocess.run(
        [
            str(python), "-m", "pytest", SUITE, "-q", "--no-header",
            "-p", "no:cacheprovider", "-p", "no:warnings", "-x",
        ],
        cwd=racine,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return resultat.returncode == 0


def analyser(cible: Path) -> SortieAdaptateur:
    racine = cible / "backend"
    dossier = cible / DOSSIER_SOURCE
    python = racine / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = racine / ".venv" / "bin" / "python"
    if not dossier.is_dir() or not python.exists():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP", non_juge=[*NON_JUGE, "environnement du projet absent"]
        )

    modules = [f for f in sorted(dossier.glob("*.py")) if f.name != "__init__.py"]
    originaux = {f: f.read_text(encoding="utf-8") for f in modules}
    tous = [(f, m) for f in modules for m in generer_mutants(f, f.name)]

    non_juge = list(NON_JUGE)
    if len(tous) > PLAFOND_MUTANTS:
        non_juge.append(
            f"mutation : plafond de {PLAFOND_MUTANTS} mutants atteint — "
            f"{len(tous) - PLAFOND_MUTANTS} mutants non joués, score calculé sur le "
            "sous-ensemble DÉCLARÉ"
        )
    retenus = tous[:PLAFOND_MUTANTS]

    survivants: list[Mutant] = []
    viables = 0
    try:
        if not _suite_verte(racine, python):
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                non_juge=[*non_juge, "suite rouge avant mutation : score non calculable"],
            )
        for fichier, mutant in retenus:
            original = originaux[fichier]
            lignes = original.splitlines()
            ligne = lignes[mutant.ligne]
            lignes[mutant.ligne] = (
                ligne[: mutant.colonne] + mutant.apres + ligne[mutant.colonne + len(mutant.avant) :]
            )
            mute = "\n".join(lignes) + "\n"
            try:
                compile(mute, str(fichier), "exec")
            except SyntaxError:
                continue  # mutant non viable : hors du dénominateur
            viables += 1
            fichier.write_text(mute, encoding="utf-8")
            if _suite_verte(racine, python):
                survivants.append(mutant)
            fichier.write_text(original, encoding="utf-8")
    except subprocess.TimeoutExpired:
        # Un délai dépassé ne doit jamais emporter l audit entier : le pan se DÉCLARE non
        # mesuré (le `finally` restaure les sources avant toute chose).
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *non_juge,
                "mutation : délai dépassé pendant le jeu des mutants — score non calculable, "
                "les autres pans restent mesurés",
            ],
        )
    finally:
        for fichier, contenu in originaux.items():
            fichier.write_text(contenu, encoding="utf-8")
        _purger_bytecode(racine)

    tues = viables - len(survivants)
    score = tues / viables if viables else 0.0
    findings = [
        Finding(
            id=m.id,
            classe="mutant-survivant",
            localisation=f"{dossier / m.fichier}:{m.ligne + 1}",
            message=f"mutant {m.avant.strip()} -> {m.apres.strip()} non tué : la suite reste verte",
            severite="signale",
            risque=coter(PAN, m.id, str(dossier / m.fichier)),
        )
        for m in survivants
    ]
    if viables and score < SEUIL:
        findings.append(
            Finding(
                id=f"seuil:{PAN}",
                classe="seuil-non-tenu",
                localisation=str(cible),
                message=f"score de mutation {score:.0%} sous le seuil {SEUIL:.0%}",
                risque=coter(PAN, f"seuil:{PAN}", str(dossier)),
            )
        )
    bloquants = [f for f in findings if f.severite == "bloquant"]
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if bloquants else "PASS",
        findings=findings,
        non_juge=non_juge,
        mutation={
            "mutants_viables": viables,
            "tues": tues,
            "score": round(score, 4),
            "modules": [f.name for f in modules],
            "survivants": [m.id for m in survivants],
        },
    )
