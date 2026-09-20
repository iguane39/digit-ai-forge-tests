r"""Une suite presente dans le depot est jouee par la chaine, ou declaree hors portee (TF-1043).

============================================================================================
POURQUOI (etude d'opportunite « socle de la chaine », 20260914a, decidee le 14/09/2026, O2)
============================================================================================

MESURE FONDATRICE (Produit-11, RT-62, 11/09/2026) : deux tests sont restes ROUGES SIX JOURS
DURANT UNE REOUVERTURE DE FAILLE P0, sans qu'aucun controle du socle ne le remonte. La chaine
avait cesse de jouer une suite presente sur le depot, et rien ne le disait : une suite qui
n'echoue plus parce qu'elle ne tourne plus se lit exactement comme une suite qui passe.

DEUX REGLES ecrites ici, dont UNE mecanisee dans ce module :

  1. (mecanisee ici) Toute suite de tests presente dans le depot est jouee par la chaine, ou
     declaree HORS PORTEE avec son motif et sa date — jamais silencieusement absente du
     rapport d'execution.
  2. (ecrite, non mecanisee dans ce lot — hors perimetre de ce module) Un correctif de
     securite qui retire une donnee d'une interface publique CITE les tests qui la lisaient :
     la classe `correctif-de-securite-laisse-un-test-muet` proposee par le candidat trouve sa
     recette naturelle ici, mais son mecanisme suppose de confronter un DIFF a une liste de
     tests couvrant l'interface touchee — nature differente de la regle 1 (etat du depot,
     jamais un differentiel de commit), remis au registre comme candidature distincte.

CE QUE CE MODULE FAIT, ET RIEN D'AUTRE : il compare deux ensembles — les fichiers de suite
PRESENTS sur disque (``test_*.py`` / ``*_test.py``, hors arborescences exclues) et les fichiers
REELLEMENT COLLECTES par ``pytest --collect-only`` (jamais devines : la chaine peut exclure un
fichier par ``testpaths``, ``--ignore``, un motif de collecte, ou une panne d'import qui saute
le fichier en silence — seule une collecte REELLE le voit). Un fichier present et non collecte,
sans declaration ``# hors-chaine (id), AAAA-MM-JJ : motif`` dans ses dix premieres lignes, est
un finding NOMME.

CE QUE CE MODULE NE FAIT PAS : il ne juge pas la CI HEBERGEE (GitHub Actions, Azure Pipelines)
directement — il rejoue la MEME collecte que la chaine locale invoquerait, sur l'hypothese que
la CI hebergee invoque la meme commande (meme angle mort que la classe
``recette-locale-ne-rejoue-pas-l-environnement-de-la-ci``, TF-1017, non recouvert ici). Il ne
juge pas non plus un test COLLECTE mais toujours SKIPPE (``pytest.mark.skip`` sans motif) :
c'est une classe voisine, pas celle mesuree par RT-62 (le test avait disparu de la collecte,
pas ete marque skip).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Protocol

_MOTIFS_SUITE = ("test_*.py", "*_test.py")
_EXCLUS = {".venv", "venv", "__pycache__", "node_modules", ".git", "vendor", "build", "dist"}

# `# hors-chaine (TF-xxxx), AAAA-MM-JJ : motif` — meme grammaire que le reste du socle (id,
# date, motif) : une declaration GRATUITE mais datee et motivee vaut mieux qu'un silence.
_DECLARATION = re.compile(
    r"^\s*#\s*hors-chaine\s*\(([^)]+)\)\s*,\s*(\d{4}-\d{2}-\d{2})\s*:\s*(\S.*)$"
)

NON_JUGE = [
    "chaine : la CI HEBERGEE (GitHub Actions, Azure Pipelines) n'est pas interrogee — la "
    "collecte rejouee est celle de la commande pytest locale, sur l'hypothese qu'elle est "
    "identique a celle de l'hebergeur (angle mort partage avec TF-1017)",
    "chaine : un test COLLECTE mais marque `pytest.mark.skip` sans motif date n'est pas vu "
    "ici — classe voisine, pas celle mesuree par RT-62 (le test avait disparu de la collecte)",
    "chaine : la regle 2 (un correctif de securite cite les tests qu'il affecte) n'est pas "
    "mecanisee dans ce module — elle suppose un diff de commit, nature differente de l'etat "
    "du depot que ce module lit",
    "chaine : sans `testpaths` declare au pyproject.toml audite, le perimetre suppose est "
    "le dossier `tests` — un projet qui range ses suites ailleurs SANS le declarer echappe "
    "au perimetre (meme angle mort que pytest lui-meme dans ce cas)",
]


class Executeur(Protocol):
    def __call__(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]: ...


def _exclu(chemin: Path) -> bool:
    return any(part in _EXCLUS for part in chemin.parts)


def _testpaths(racine: Path) -> list[str]:
    """Lit `[tool.pytest.ini_options].testpaths` du `pyproject.toml` audité — le perimetre de
    la SUITE DECLAREE, jamais devine. Defaut `["tests"]` (convention la plus repandue) si le
    fichier est absent, illisible, ou ne declare pas cette cle."""
    pyproject = racine / "pyproject.toml"
    if not pyproject.exists():
        return ["tests"]
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return ["tests"]
    testpaths = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths")
    if isinstance(testpaths, list) and testpaths:
        return [str(p) for p in testpaths]
    return ["tests"]


def suites_du_depot(racine: Path) -> list[Path]:
    """Chaque fichier de suite Python present sous les `testpaths` declares, hors arborescences
    exclues — un fixture/banc de DONNEES rangé HORS testpaths (ex. `fixtures/`) n'est pas une
    suite de ce depot, quelle que soit sa ressemblance de nom."""
    trouves: set[Path] = set()
    for sous_chemin in _testpaths(racine):
        base = racine / sous_chemin
        if not base.exists():
            continue
        for motif in _MOTIFS_SUITE:
            trouves.update(
                p.resolve() for p in base.rglob(motif) if p.is_file() and not _exclu(p)
            )
    return sorted(trouves)


def declaration_hors_chaine(chemin: Path) -> dict[str, str] | None:
    """Lit une declaration `# hors-chaine (id), AAAA-MM-JJ : motif` dans les 10 premieres lignes.

    Absente ou incomplete (grammaire non respectee) -> None : une declaration qui ne se lit pas
    ne protege personne, exactement le meme principe que O9 (forge-ops)."""
    try:
        lignes = chemin.read_text(encoding="utf-8", errors="ignore").splitlines()[:10]
    except OSError:
        return None
    for ligne in lignes:
        m = _DECLARATION.match(ligne)
        if m:
            return {"id": m.group(1).strip(), "date": m.group(2), "motif": m.group(3).strip()}
    return None


def _executeur_defaut(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)


# Sortie reelle de `pytest --collect-only -q` (pytest 8.x) : UNE LIGNE PAR FICHIER COLLECTE,
# `<chemin relatif>.py: <n> test(s)`, jamais une arborescence — verifie sur ce depot le 14/09/2026.
_LIGNE_COLLECTE = re.compile(r"^(?P<chemin>.+\.py):\s*\d+")


def suites_collectees(racine: Path, *, executeur: Executeur | None = None) -> set[Path]:
    """Fichiers REELLEMENT collectes par `pytest --collect-only -q` — jamais devines : c'est la
    difference entre lire une intention (testpaths) et constater un fait (collecte reelle). Un
    fichier qui echoue a l'IMPORT (erreur de collecte) n'apparait pas ici sous cette forme : il
    est donc vu comme non collecte, ce qui est le comportement voulu — un fichier qui casse la
    collecte ne joue pas plus qu'un fichier absent de la chaine."""
    r = (executeur or _executeur_defaut)(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"], racine
    )
    sortie = (r.stdout or "") + "\n" + (r.stderr or "")
    fichiers: set[Path] = set()
    for ligne in sortie.splitlines():
        m = _LIGNE_COLLECTE.match(ligne.strip())
        if not m:
            continue
        p = (racine / m.group("chemin")).resolve()
        if p.exists():
            fichiers.add(p)
    return fichiers


def suites_non_jouees(
    racine: Path,
    *,
    collecte: set[Path] | None = None,
    executeur: Executeur | None = None,
) -> list[dict[str, str]]:
    """Regle 1 (TF-1043) : une suite presente et NON collectee par la chaine, sans declaration
    hors-chaine valide, est un finding NOMME (fichier + constat)."""
    presentes = suites_du_depot(racine)
    jouees = collecte if collecte is not None else suites_collectees(racine, executeur=executeur)
    findings: list[dict[str, str]] = []
    for f in presentes:
        if f in jouees:
            continue
        decl = declaration_hors_chaine(f)
        if decl is not None:
            continue
        findings.append(
            {
                "fichier": str(f),
                "constat": "suite presente dans le depot, non jouee par la chaine, non "
                "declaree hors portee (# hors-chaine (id), AAAA-MM-JJ : motif)",
            }
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Entree CLI : ``python -m forge_tests.chaine <racine>``."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage : python -m forge_tests.chaine <racine>", file=sys.stderr)
        return 2
    racine = Path(args[0])
    if not racine.exists():
        print(f"chaine : racine introuvable ({racine})", file=sys.stderr)
        return 2
    findings = suites_non_jouees(racine)
    if not findings:
        print("chaine : PASS — chaque suite presente est jouee ou declaree hors portee")
        return 0
    print(f"chaine : FAIL ({len(findings)} suite(s) non jouee(s), non declaree(s))",
          file=sys.stderr)
    for f in findings:
        print(f"  - {f['fichier']} : {f['constat']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
