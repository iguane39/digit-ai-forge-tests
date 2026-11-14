"""TF-2467 — préparer un arbre de travail NEUF de forge-tests, hors ligne, en une commande.

Un `git worktree add` ou un clone neuf ne porte que les fichiers suivis. Or la recette mesure les
deux bancs d'essai (`fixtures/banc-rouge`, `fixtures/banc-vert`) avec des préalables que git ne
livre pas : l'environnement Python des essais du back (`backend/.venv`), les dépendances du front
(`frontend/node_modules`) et son build (`frontend/dist`). Sans eux, 12 pans sur 21 sont NON
MESURABLES et la section `dashboard` échouait à `check_html` sur le texte des préalables absents :
un faux rouge, mesuré le 12/11/2026 par l'agent du lot ft puis le 13/11/2026 sur un arbre neuf.

La commande, jouée depuis la racine du dépôt, est la seule à connaître (`COMMANDE`) :

    uv run --frozen --offline python recette/preparer_arbre.py

`uv run --frozen --offline` crée l'environnement du dépôt lui-même (`.venv` racine) depuis le
verrou et le cache de `uv`, sans réseau ; le script prépare ensuite les deux bancs. Il ne refait
que ce qui manque (relancé sur un arbre prêt, il ne joue rien), n'utilise que la bibliothèque
standard et ne parle à aucun serveur : `uv sync --frozen --offline` et `npm ci --offline` lisent
le cache du poste. Un cache incomplet est un échec DIT (code 1, sortie de l'outil à l'appui), pas
un contournement par le réseau.

Codes de sortie : 0 arbre prêt · 1 une étape a échoué · 3 un outil (`uv`, `npm`) est introuvable
ou, avec `--verifier`, des préalables manquent. `--verifier` ne modifie rien.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
BANCS = ("banc-rouge", "banc-vert")

#: La commande unique que le contrat d'agent de campagne nomme pour tout arbre de forge-tests.
COMMANDE = "uv run --frozen --offline python recette/preparer_arbre.py"

#: Délai d'une étape (secondes). Le build d'un front a pris 68 s à froid sur ce poste.
DELAI_ETAPE_S = 600


@dataclass(frozen=True)
class Etape:
    """Une étape de préparation : ce qu'elle lance, où, et ce qu'elle doit laisser sur le disque."""

    libelle: str
    dossier: Path
    argv: tuple[str, ...]
    produit: Path


def etapes(racine: Path = RACINE) -> list[Etape]:
    """Les étapes dans l'ordre : le build d'un front suit l'installation de ses dépendances."""
    sortie: list[Etape] = []
    for banc in BANCS:
        dossier = racine / "fixtures" / banc
        back, front = dossier / "backend", dossier / "frontend"
        sortie += [
            Etape(f"{banc} : environnement Python des essais", back,
                  ("uv", "sync", "--frozen", "--offline"), back / ".venv"),
            Etape(f"{banc} : dépendances du front", front,
                  ("npm", "ci", "--offline"), front / "node_modules"),
            Etape(f"{banc} : build du front", front, ("npm", "run", "build"), front / "dist"),
        ]
    return sortie


def prerequis_absents(racine: Path = RACINE) -> list[Etape]:
    """Les étapes dont le produit manque sur le disque (liste vide : l'arbre est prêt)."""
    return [etape for etape in etapes(racine) if not etape.produit.is_dir()]


def lignes_prerequis_absents(absents: Sequence[Etape], racine: Path = RACINE) -> list[str]:
    """Les lignes que la recette et `--verifier` impriment : quoi manque, et LA commande."""
    lignes = [f"  PRÉREQUIS ABSENT — arbre de travail neuf : {len(absents)} élément(s) manquent :"]
    for etape in absents:
        try:
            chemin = etape.produit.relative_to(racine).as_posix()
        except ValueError:
            chemin = str(etape.produit)
        lignes.append(f"             -> {chemin}")
    lignes.append(f"  Les préparer, hors ligne, depuis la racine du dépôt : {COMMANDE}")
    return lignes


#: Les deux formes RÉELLES du message d'un paquet absent du cache quand l'étape tourne hors ligne,
#: relevées le 14/11/2026 en jouant chaque étape sur un cache vide (TF-2524) :
#:   npm : « request to https://registry.npmjs.org/yallist/-/yallist-3.1.1.tgz failed: cache mode
#:         is 'only-if-cached' but no cached response is available » (code ENOTCACHED) ;
#:   uv  : « Network connectivity is disabled, but the requested data wasn't found in the cache
#:         for: `https://files.pythonhosted.org/…/pywin32-312-cp313-cp313-win_amd64.whl` ».
#: Motifs SPÉCIFIQUES : un échec d'une autre nature (build, version, droits) ne se dit pas « réseau
#: requis » — le symétrique du défaut ferait chercher le réseau là où il n'est pas la cause.
_PAQUET_ABSENT_DU_CACHE = (
    re.compile(r"request to (\S+) failed: cache mode is 'only-if-cached'"),
    re.compile(r"requested data wasn't found in the cache for:\s*`([^`]+)`"),
)


def paquet_absent_du_cache(sortie: str) -> str | None:
    """Le fichier du paquet que le cache du poste n'a pas, lu dans la sortie de l'outil, ou None."""
    for motif in _PAQUET_ABSENT_DU_CACHE:
        trouve = motif.search(re.sub(r"\s+", " ", sortie or ""))
        if trouve:
            return trouve.group(1).rstrip("/").rsplit("/", 1)[-1]
    return None


def commande_en_ligne(etape: Etape) -> str:
    """La commande de l'étape SANS `--offline` : celle qui remplit le cache, depuis son dossier."""
    return " ".join(arg for arg in etape.argv if arg != "--offline")


def preparer(
    racine: Path = RACINE,
    executer: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    chercher: Callable[[str], str | None] = shutil.which,
) -> int:
    """Joue les étapes manquantes, une à une. 0 prêt · 1 étape en échec · 3 outil introuvable."""
    a_faire = prerequis_absents(racine)
    if not a_faire:
        print("arbre déjà prêt : rien à préparer")
        return 0
    for rang, etape in enumerate(a_faire, start=1):
        exe = chercher(etape.argv[0])
        if exe is None:
            print(f"PRÉREQUIS ABSENT — outil « {etape.argv[0]} » introuvable dans le PATH : "
                  f"« {etape.libelle} » ne peut pas être préparé")
            return 3
        print(f"[{rang}/{len(a_faire)}] {etape.libelle} : {' '.join(etape.argv)}", flush=True)
        debut = time.monotonic()
        try:
            issue = executer(
                [exe, *etape.argv[1:]], cwd=etape.dossier, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=DELAI_ETAPE_S,
            )
        except subprocess.TimeoutExpired:
            print(f"ÉCHEC — « {etape.libelle} » dépasse {DELAI_ETAPE_S} s")
            return 1
        duree = time.monotonic() - debut
        if issue.returncode != 0:
            sortie = (issue.stdout or "") + (issue.stderr or "")
            print(f"ÉCHEC — « {etape.libelle} » : code {issue.returncode} après {duree:.0f} s")
            print(sortie.strip()[-1200:])
            absent = paquet_absent_du_cache(sortie)
            if absent is not None:
                # TF-2524 : la cause est lue, pas supposée — et dite en clair, avec le geste.
                try:
                    dossier = etape.dossier.relative_to(racine).as_posix()
                except ValueError:
                    dossier = str(etape.dossier)
                print(f"  RÉSEAU REQUIS — le paquet « {absent} » manque au cache du poste, et "
                      f"cette étape tourne HORS LIGNE : elle ne peut pas le télécharger. Remplir "
                      f"le cache en ligne, depuis {dossier} : `{commande_en_ligne(etape)}`, "
                      f"puis rejouer : {COMMANDE}")
            else:
                print("  Hors ligne, l'étape lit le cache du poste : s'il est incomplet, le "
                      "remplir en ligne (uv sync, npm ci sans --offline), puis rejouer la "
                      "commande.")
            return 1
        if not etape.produit.is_dir():
            print(f"ÉCHEC — « {etape.libelle} » : code 0 mais {etape.produit} reste absent")
            return 1
        print(f"      fait en {duree:.0f} s -> {etape.produit}", flush=True)
    print(f"arbre prêt : {len(a_faire)} étape(s) jouée(s)")
    return 0


def main(argv: Sequence[str] | None = None, racine: Path = RACINE) -> int:
    parser = argparse.ArgumentParser(
        prog="preparer_arbre",
        description="Prépare, hors ligne, les bancs d'un arbre de travail neuf de forge-tests.",
    )
    parser.add_argument(
        "--verifier", action="store_true",
        help="ne modifie rien : liste les préalables absents (code 3), sinon rend 0",
    )
    args = parser.parse_args(argv)
    if args.verifier:
        absents = prerequis_absents(racine)
        if not absents:
            print("arbre prêt : aucun préalable absent")
            return 0
        for ligne in lignes_prerequis_absents(absents, racine):
            print(ligne)
        return 3
    return preparer(racine)


if __name__ == "__main__":
    sys.exit(main())
