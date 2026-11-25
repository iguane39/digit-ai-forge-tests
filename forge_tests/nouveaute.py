"""La nouveauté d'un constat se DATE : elle vient de la règle ou du code (TF-2862).

Fait (Produit-12, RS-56, 23/11/2026) : deux constats « bloquants » semgrep `incomplete-sanitization`
apparaissent sur `table-filters.js` alors que le rapport de la veille ne les portait pas (101
constats contre 103). Le fichier n'avait pas changé depuis `6660e50` : c'est la règle, ou l'outil
qui la porte, qui a changé, pas le code. Le rapport ne le disait pas, et un lecteur qui voit un
bloquant neuf cherche la modification qui l'a produit. Un faux bloquant dont l'origine reste muette
entraîne à ignorer la classe des bloquants.

Ce module compare chaque constat au rapport PRÉCÉDENT et, quand il est neuf, au dernier commit de
son fichier (`git log`) :

  - `deja_present` : le constat (même identifiant) figurait déjà au rapport précédent ;
  - `nouveau_par_la_regle` : le constat est neuf, et son fichier n'a pas changé depuis le rapport
    précédent (aucun commit plus récent, aucune modification non commitée) : la règle, l'outil ou sa
    configuration d'analyse a changé ;
  - `nouveau_par_le_code` : le constat est neuf, et son fichier a été commité (ou modifié) après le
    rapport précédent ;
  - `non_datable` : ni l'un ni l'autre ne se tranche (localisation qui n'est pas un fichier, fichier
    non versionné, `git` absent) ; le motif est dit sur le constat.

La section `nouveaute` du rapport est TOUJOURS présente : « aucun rapport précédent fourni » se lit,
il ne se confond pas avec « aucun constat neuf ».

Ce que ce module ne juge pas : la VERSION de la règle ou de l'outil (aucun oracle ne la publie : la
cause « règle » est une inférence, fichier inchangé et constat neuf), un fichier déplacé ou renommé
entre les deux rapports (son constat est vu neuf, et le dernier commit suit le chemin actuel), et la
date d'un rapport qui ne porte pas `genere_le` (celle de son fichier, que toute copie réécrit).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

NON_JUGE = [
    "nouveauté : « nouveau par la règle » est une INFÉRENCE (constat neuf, fichier inchangé depuis "
    "le rapport précédent) : aucun oracle ne publie la version de sa règle ni de son outil ; un "
    "fichier renommé entre les deux rapports se lit nouveau, et un changement du code voisin (un "
    "fichier importé) n'est pas vu",
    "nouveauté : la date d'un rapport qui ne porte pas `genere_le` est celle de son fichier, que "
    "toute copie réécrit ; un rapport précédent sans date ne date aucun constat",
]

DEJA_PRESENT = "deja_present"
PAR_LA_REGLE = "nouveau_par_la_regle"
PAR_LE_CODE = "nouveau_par_le_code"
NON_DATABLE = "non_datable"

_LIEU = re.compile(r"^(?P<fichier>.+?)(?::(?P<ligne>\d+))?(?: · .*)?$")

#: `dernier_commit(fichier)` → `(sha, date ISO)` du dernier commit qui touche le fichier, ou `None`
#: quand `git` ne le sait pas ; `modifie(fichier)` → modification non commitée. Injectables : la
#: recette ne dépend pas d'un dépôt git réel.
DernierCommit = Callable[[Path], tuple[str, str] | None]
Modifie = Callable[[Path], bool]


def dernier_commit_git(fichier: Path) -> tuple[str, str] | None:
    try:
        sortie = subprocess.run(
            ["git", "-C", str(fichier.parent), "log", "-1", "--format=%H%x09%cI", "--",
             fichier.name],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    ligne = sortie.stdout.strip()
    if sortie.returncode != 0 or "\t" not in ligne:
        return None
    sha, date = ligne.split("\t", 1)
    return sha, date


def modifie_depuis_le_commit(fichier: Path) -> bool:
    try:
        sortie = subprocess.run(
            ["git", "-C", str(fichier.parent), "status", "--porcelain", "--", fichier.name],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # `??` : un fichier non suivi n'a pas de commit à comparer, il se dit non versionné ailleurs.
    return sortie.returncode == 0 and any(
        ligne and not ligne.startswith("??") for ligne in sortie.stdout.splitlines()
    )


def _fichier_de(localisation: str, cible: Path) -> Path | None:
    """Le fichier qu'une localisation désigne (`chemin` ou `chemin:ligne`), s'il existe."""
    trouve = _LIEU.match(localisation.strip())
    if trouve is None:
        return None
    chemin = Path(trouve["fichier"])
    if not chemin.is_absolute():
        chemin = cible / chemin
    try:
        return chemin if chemin.is_file() else None
    except OSError:
        return None


def date_du_rapport(
    rapport: dict[str, Any], fichier: Path | None
) -> tuple[_dt.datetime | None, str]:
    """La date d'un rapport : `genere_le`, à défaut celle de son fichier, avec sa source."""
    declare = rapport.get("genere_le")
    if isinstance(declare, str):
        try:
            return _dt.datetime.fromisoformat(declare), "champ `genere_le` du rapport"
        except ValueError:
            pass
    if fichier is not None and fichier.is_file():
        modifie = _dt.datetime.fromtimestamp(fichier.stat().st_mtime).astimezone()
        return modifie, "date de modification du fichier (le rapport ne porte pas `genere_le`)"
    return None, "aucune date"


def _en_utc(date: _dt.datetime) -> _dt.datetime:
    """Une date comparable : une date sans fuseau se lit à l'heure locale du poste."""
    return date.astimezone(_dt.UTC)


def classer(
    constat: dict[str, Any],
    precedent_ids: set[str],
    date_precedent: _dt.datetime | None,
    cible: Path,
    dernier_commit: DernierCommit,
    modifie: Modifie,
) -> dict[str, Any]:
    """L'origine d'un constat, avec ce qui la fonde."""
    if constat.get("id") in precedent_ids:
        return {"origine": DEJA_PRESENT, "motif": "le constat figurait au rapport précédent"}
    fichier = _fichier_de(str(constat.get("localisation") or ""), cible)
    if fichier is None:
        return {
            "origine": NON_DATABLE,
            "motif": "la localisation ne désigne pas un fichier lisible : aucun `git log` à lire",
        }
    if date_precedent is None:
        return {"origine": NON_DATABLE, "motif": "le rapport précédent n'a pas de date"}
    if modifie(fichier):
        return {
            "origine": PAR_LE_CODE,
            "motif": "le fichier est modifié depuis son dernier commit : le code a changé",
        }
    commit = dernier_commit(fichier)
    if commit is None:
        return {
            "origine": NON_DATABLE,
            "motif": "le fichier n'a pas de commit lisible (non versionné, ou `git` absent)",
        }
    sha, date_commit = commit
    try:
        commite_le = _dt.datetime.fromisoformat(date_commit)
    except ValueError:
        return {"origine": NON_DATABLE, "motif": f"date de commit illisible : {date_commit}"}
    base = {"dernier_commit": sha[:12], "dernier_commit_le": date_commit}
    if _en_utc(commite_le) > _en_utc(date_precedent):
        return {
            "origine": PAR_LE_CODE,
            "motif": "le fichier a été commité après le rapport précédent : le code a changé",
            **base,
        }
    return {
        "origine": PAR_LA_REGLE,
        "motif": (
            "le fichier n'a pas changé depuis le rapport précédent (dernier commit "
            f"{sha[:12]}, le {date_commit}) : la règle, l'outil ou sa configuration d'analyse a "
            "changé, pas le code"
        ),
        **base,
    }


def lire_precedent(
    precedents: list[Path] | None, reprendre: Path | None
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    """Le rapport de comparaison : le dernier `--precedent`, à défaut `--reprendre`.

    Rend `(rapport, fichier, refus)`. Un rapport illisible n'arrête pas l'audit : le refus se DIT
    dans la section `nouveaute`, jamais en silence.
    """
    fichier = precedents[-1] if precedents else reprendre
    if fichier is None:
        return None, None, None
    try:
        donnees = json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return None, fichier, f"rapport précédent illisible : {fichier} ({erreur})"
    if not isinstance(donnees, dict) or "findings" not in donnees:
        return None, fichier, f"rapport précédent illisible : {fichier} (ce n'est pas un rapport)"
    return donnees, fichier, None


def dater(
    rap: dict[str, Any],
    cible: Path,
    precedent: dict[str, Any] | None,
    precedent_fichier: Path | None = None,
    *,
    refus: str | None = None,
    dernier_commit: DernierCommit = dernier_commit_git,
    modifie: Modifie = modifie_depuis_le_commit,
    maintenant: _dt.datetime | None = None,
) -> None:
    """Date la nouveauté de chaque constat du rapport, en place.

    Ajoute `genere_le` (la date de CE rapport, pour que le suivant la lise), `nouveaute` sur chaque
    constat et la section `nouveaute` du rapport. Sans rapport précédent, la section le DIT.
    """
    rap["genere_le"] = (maintenant or _dt.datetime.now().astimezone()).isoformat(timespec="seconds")
    non_juge = list(NON_JUGE)
    if precedent is None:
        rap["nouveaute"] = {
            "statut": "non_mesuree",
            "motif": refus or (
                "aucun rapport précédent fourni (`--precedent <rapport.json>` ou `--reprendre`) : "
                "un constat neuf ne peut pas être attribué à la règle ou au code"
            ),
            "non_juge": non_juge,
        }
        return
    date_precedent, source = date_du_rapport(precedent, precedent_fichier)
    precedents = {str(c.get("id")) for c in precedent.get("findings") or []}
    comptes = {DEJA_PRESENT: 0, PAR_LA_REGLE: 0, PAR_LE_CODE: 0, NON_DATABLE: 0}
    for constat in rap.get("findings") or []:
        origine = classer(constat, precedents, date_precedent, cible, dernier_commit, modifie)
        constat["nouveaute"] = origine
        comptes[origine["origine"]] += 1
    if date_precedent is None:
        non_juge.append("nouveauté : le rapport précédent n'a aucune date, aucun constat daté")
    rap["nouveaute"] = {
        "statut": "mesuree",
        "precedent": {
            "fichier": str(precedent_fichier) if precedent_fichier else None,
            "date": date_precedent.isoformat(timespec="seconds") if date_precedent else None,
            "source_de_la_date": source,
            "constats": len(precedents),
        },
        "comptes": comptes,
        "non_juge": non_juge,
    }


def lignes_du_resume(rap: dict[str, Any]) -> list[str]:
    """Ce que le rapport lisible dit de la nouveauté, en tête de ses constats."""
    section = rap.get("nouveaute")
    if not isinstance(section, dict):
        return []
    if section.get("statut") != "mesuree":
        return [f"nouveauté des constats : non datée — {section.get('motif', 'non mesurée')}"]
    comptes = section["comptes"]
    precedent = section["precedent"]
    lignes = [
        f"nouveauté des constats (rapport précédent du {precedent['date'] or 'date inconnue'}, "
        f"{precedent['constats']} constat(s)) : {comptes[DEJA_PRESENT]} déjà présent(s), "
        f"{comptes[PAR_LA_REGLE]} nouveau(x) par la règle (fichier inchangé), "
        f"{comptes[PAR_LE_CODE]} nouveau(x) par le code, {comptes[NON_DATABLE]} non datable(s)"
    ]
    par_la_regle = [
        c for c in rap.get("findings") or []
        if (c.get("nouveaute") or {}).get("origine") == PAR_LA_REGLE
    ]
    for constat in par_la_regle[:10]:
        lignes.append(
            f"  par la règle : {constat.get('localisation')} — {constat.get('message')}"
        )
    if len(par_la_regle) > 10:
        lignes.append(f"  … et {len(par_la_regle) - 10} autre(s) (champ `nouveaute` du constat)")
    return lignes
