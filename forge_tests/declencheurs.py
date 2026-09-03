"""Déclencheurs de traitements par lot — ce qui ENCLENCHE un batch, pas ce qu'il fait dedans.

TF-0203, sur précision humaine du 14/08/2026 : le pan `batch` inventorie les branches de rejet
et de reprise À L'INTÉRIEUR du traitement, en supposant qu'il démarre. Or c'est le démarrage
qui manque le plus souvent : un lot dont le déclencheur n'est pas câblé ne tourne jamais, et
rien ne le dit.

**Un déclencheur est une affordance** au sens de la loi transverse n°1 de l'écosystème :
« toute affordance est câblée ou n'existe pas ». Déclaré dans une configuration mais pointant
vers une cible inexistante, il est exactement l'équivalent, côté serveur, du bouton sans
gestionnaire que le pan `interface` dénonce côté écran.

Trois constats, tous dérivés STATIQUEMENT et sans rien exécuter :

  - `trigger-non-cable`   — le déclencheur nomme une cible que le projet ne contient pas ;
  - `job-sans-declencheur`— un traitement par lot qu'aucun déclencheur n'atteint (code mort) ;
  - `cron-invalide`       — l'expression de planification ne se lit pas (mauvais nombre de
                            champs) : elle ne déclenchera rien, silencieusement.

Ce module LIT des fichiers de configuration ; il n'exécute aucun planificateur, ne déclenche
aucun lot et n'écrit rien (G-1).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from forge_tests import classes, exclusions

NON_JUGE = [
    "declencheurs : la decouverte est STATIQUE et bornee aux formes reconnues (cron d un "
    "workflow CI, crontab, timer systemd, decorateurs de planification Python, taches Celery, "
    "point d entree `__main__`) — un declencheur pose a l execution par un ordonnanceur "
    "externe (Airflow deporte, planificateur du cloud configure hors depot) n est pas "
    "inventoriable ici, et le declarer serait mentir",
    "declencheurs : le cablage est verifie sur le NOM de la cible (module, fonction, commande) "
    "presente dans le depot ; qu elle soit la BONNE cible, et qu elle fasse ce que le "
    "declencheur promet, releve du cas de test, pas de l inventaire",
    "declencheurs : une expression cron syntaxiquement valide n est pas pour autant la cadence "
    "VOULUE — l ecart entre la cadence declaree et la cadence attendue est un jugement humain",
    "declencheurs : la v0 juge le CABLAGE, la lisibilite de la planification et l absence "
    "totale de declencheur ; elle ne dit pas si la suite de tests DECLENCHE le lot au moins "
    "une fois (il faudrait relier le declencheur a la couverture d execution de sa cible) — "
    "ce volet est declare comme reste-a-faire, pas comme mesure",
]

# Dossiers hors périmètre : dépendances et artefacts (mêmes exclusions que les autres pans,
# RT-9/RT-10 du lot Produit-11).
_EXCLUS = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages", "dist", "build",
    "output", "old", "Old", ".oracles", ".forge",
    # TF-0536/0542/0543 (lot Produit-02 20260823) : le SOCLE commun vient desormais
    # d'une source unique. Le depot portait DIX listes divergentes (7 a 31 entrees) et
    # `input` ne figurait dans AUCUNE : sur un audit reel, 12 constats sur 15 portaient sur
    # `input\` — un site concurrent aspire et une ancienne version du site. Les entrees
    # ci-dessus restent ecrites ici : elles portent le motif de CE pan.
    *exclusions.socle(),
}

# --- Reconnaissance des formes ------------------------------------------------------------------
# `on: schedule: - cron: "…"` d'un workflow CI, et `OnCalendar=` d'un timer systemd.
_CRON_CI = re.compile(r"^\s*-?\s*cron:\s*[\"']?([^\"'\n#]+)[\"']?", re.MULTILINE)
_ONCALENDAR = re.compile(r"^\s*OnCalendar\s*=\s*(.+)$", re.MULTILINE)
# Ligne de crontab : 5 champs puis une commande.
_CRONTAB = re.compile(r"^\s*([\d*/,\-]+(?:\s+[\d*/,\-]+){4})\s+(\S.*)$", re.MULTILINE)
# Décorateurs de planification les plus répandus, quel que soit l'objet porteur.
_DECORATEUR_PLANIFIE = re.compile(
    r"@(?:\w+\.)*(scheduled_job|periodic_task|timer_trigger|schedule|cron)\b"
)
_DECORATEUR_TACHE = re.compile(r"@(?:\w+\.)*(shared_task|task)\b")

_CRON_CHAMPS = (5, 6)  # 5 champs (POSIX) ou 6 (avec les secondes)


def _fichiers(cible: Path, motifs: tuple[str, ...]) -> list[Path]:
    retenus: list[Path] = []
    for motif in motifs:
        for chemin in cible.rglob(motif):
            if chemin.is_file() and not any(p in _EXCLUS for p in chemin.parts):
                retenus.append(chemin)
    return sorted(set(retenus))


def cron_lisible(expression: str) -> bool:
    """Une expression de planification qui ne se lit pas ne déclenchera rien, en silence."""
    champs = expression.strip().split()
    if not champs:
        return False
    # Les raccourcis nommés sont valides et n'ont pas de champs (`@daily`, `@hourly`…).
    if champs[0].startswith("@"):
        return len(champs) == 1
    return len(champs) in _CRON_CHAMPS


def _cible_existe(cible: Path, designation: str) -> bool:
    """La cible nommée par un déclencheur est-elle présente dans le dépôt ?

    On cherche un fichier de ce nom, ou un module Python de ce nom — jamais une résolution
    d'import réelle, qui exigerait d'exécuter le projet.
    """
    designation = designation.strip().strip("\"'")
    if not designation:
        return False
    # `python -m paquet.module`, `python chemin/vers/script.py`, `bash script.sh`, `./job`
    mots = designation.replace("\\", "/").split()
    for mot in mots:
        mot = mot.strip()
        if mot.startswith("-") or mot in ("python", "python3", "bash", "sh", "node", "uv", "run"):
            continue
        candidat = mot.split("::")[0]
        if "/" in candidat or candidat.endswith((".py", ".sh", ".js", ".mjs")):
            if (cible / candidat).exists():
                return True
            if any(p.name == Path(candidat).name for p in _fichiers(cible, ("*",))[:0]):
                return True
            # Recherche par nom de fichier, le chemin déclaré pouvant être relatif à autre chose.
            nom = Path(candidat).name
            if nom and any(p.name == nom for p in cible.rglob(nom) if p.is_file()):
                return True
            continue
        if "." in candidat:  # module python pointé
            chemin = candidat.replace(".", "/")
            if (cible / f"{chemin}.py").exists() or (cible / chemin).is_dir():
                return True
            dernier = candidat.rsplit(".", 1)[-1]
            if any(p.name == f"{dernier}.py" for p in cible.rglob(f"{dernier}.py")):
                return True
    return False


def inventorier(cible: Path) -> list[dict]:
    """Déclencheurs trouvés. Chacun : {id, type, source, cadence, designation, cable, motif}."""
    cible = Path(cible)
    trouves: list[dict] = []

    def poser(identifiant: str, type_: str, source: Path, cadence: str, designation: str) -> None:
        cable = _cible_existe(cible, designation) if designation else None
        trouves.append(
            {
                "id": identifiant,
                "type": type_,
                "source": str(source),
                "cadence": cadence,
                "designation": designation,
                "cable": cable,
            }
        )

    # 1. Workflows de CI planifiés
    for fichier in _fichiers(cible, (".github/workflows/*.yml", ".github/workflows/*.yaml")):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for expression in _CRON_CI.findall(texte):
            poser(
                f"trigger:cron-ci:{fichier.name}:{expression.strip()}",
                "cron-ci", fichier, expression.strip(), fichier.name,
            )

    # 2. Timers systemd
    for fichier in _fichiers(cible, ("*.timer",)):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for expression in _ONCALENDAR.findall(texte):
            poser(
                f"trigger:timer:{fichier.stem}",
                "timer-systemd", fichier, expression.strip(), f"{fichier.stem}.service",
            )

    # 3. Crontab versionné
    for fichier in _fichiers(cible, ("crontab", "*.cron", "crontab.*")):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for expression, commande in _CRONTAB.findall(texte):
            poser(
                f"trigger:crontab:{fichier.name}:{expression.strip()}",
                "crontab", fichier, expression.strip(), commande.strip(),
            )

    # 4. Décorateurs de planification et tâches de file, dans les sources Python
    for fichier in _fichiers(cible, ("*.py",)):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        if not (_DECORATEUR_PLANIFIE.search(texte) or _DECORATEUR_TACHE.search(texte)):
            continue
        try:
            arbre = ast.parse(texte, filename=str(fichier))
        except SyntaxError:
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorateur in noeud.decorator_list:
                rendu = ast.unparse(decorateur) if hasattr(ast, "unparse") else ""
                if _DECORATEUR_PLANIFIE.search("@" + rendu):
                    poser(
                        f"trigger:planifie:{fichier.stem}:{noeud.name}",
                        "planifie", fichier, rendu, noeud.name,
                    )
                elif _DECORATEUR_TACHE.search("@" + rendu):
                    poser(
                        f"trigger:file:{fichier.stem}:{noeud.name}",
                        "file", fichier, "à la demande (message de file)", noeud.name,
                    )

    # 5. Point d'entrée manuel du module de lot
    for fichier in _fichiers(cible, ("batch.py", "*_batch.py", "traitement.py")):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        if "__main__" in texte:
            poser(
                f"trigger:manuel:{fichier.stem}",
                "manuel", fichier, "exécution manuelle (point d entrée `__main__`)", fichier.name,
            )
    return trouves


def constats(cible: Path, declencheurs: list[dict], jobs: list[str]) -> list[dict]:
    """Constats dérivés — chacun rattaché à un élément NOMMÉ, jamais un total anonyme.

    `jobs` : identifiants des traitements par lot inventoriés par le pan (branches, rejets).
    Un lot présent qu'aucun déclencheur n'atteint est du code que rien ne fait tourner.
    """
    releves: list[dict] = []
    for declencheur in declencheurs:
        if declencheur["cable"] is False:
            releves.append(
                {
                    "id": declencheur["id"],
                    "classe": classes.TRIGGER_NON_CABLE,
                    "localisation": declencheur["source"],
                    "message": (
                        f"déclencheur {declencheur['type']} déclaré vers « "
                        f"{declencheur['designation']} » — cible introuvable dans le dépôt : "
                        "le lot ne partira jamais, et rien ne le signale au déploiement"
                    ),
                }
            )
        if declencheur["type"] in ("cron-ci", "crontab") and not cron_lisible(
            declencheur["cadence"]
        ):
            releves.append(
                {
                    "id": declencheur["id"],
                    "classe": classes.CRON_INVALIDE,
                    "localisation": declencheur["source"],
                    "message": (
                        f"expression de planification « {declencheur['cadence']} » illisible "
                        "(ni 5 ou 6 champs, ni raccourci nommé) — la planification est "
                        "silencieusement inopérante"
                    ),
                }
            )
    if jobs and not declencheurs:
        releves.append(
            {
                "id": "job-sans-declencheur",
                "classe": classes.JOB_SANS_DECLENCHEUR,
                "localisation": str(cible),
                "message": (
                    f"{len(jobs)} élément(s) de traitement par lot inventorié(s) et AUCUN "
                    "déclencheur trouvé : soit le lot est enclenché hors du dépôt (à déclarer), "
                    "soit rien ne le fait tourner"
                ),
            }
        )
    return releves
