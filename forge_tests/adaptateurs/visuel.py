"""Adaptateur Régression visuelle (Q4) — câblage de `oracle-visual-diff.py`.

Dernier oracle du registre à n avoir jamais été appelé, pour la même raison que
l accessibilité : il compare le rendu d une PAGE, et le banc n était pas une application vivante.

Gouvernance des goldens, reprise telle quelle de l oracle : **jamais de création automatique
pendant un run**. Un golden absent produit un SKIP motivé, pas un vert de complaisance. La
création passe par `--accepter`, hors boucle — c est ce qui empêche d entériner un rendu qui
vient d échouer.

Sur la paire de fixtures, le golden a une source naturelle : le rendu du banc SAIN. C est le
seul contexte où la référence n a pas à être décidée par un humain — sur un projet réel, elle
reste une décision, et l adaptateur la réclame au lieu de l inventer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "visuel-golden", "visuel"
DOSSIER = ".visuel"
_ORACLE = Path.home() / ".claude" / "skills" / "quality-oracles" / "scripts" / "oracle-visual-diff.py"

NON_JUGE = [
    "visuel : un diff dit qu il y a changement, pas si le changement est VOULU — la decision "
    "reste humaine (limite propre de l oracle, reprise telle quelle)",
    "visuel : le rendu compare est le DOM capture a l etat initial de chaque route, sans style "
    "externe charge depuis le serveur",
]


def _routes(cible: Path) -> list[str]:
    from forge_tests.adaptateurs.front import inventaire

    return [e.id.split(":", 1)[1] for e in inventaire(cible) if e.id.startswith("route:")]


def capturer(cible: Path) -> dict[str, Path]:
    """Ecrit le DOM rendu de chaque route dans `<cible>/.visuel/`. Reutilise la mecanique a11y."""
    from forge_tests.adaptateurs.accessibilite import _capturer

    dossier = cible / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    return _capturer(cible, _routes(cible), dossier)


def _juger(page: Path, accepter: bool = False) -> dict | None:
    python = shutil.which("python") or shutil.which("python3")
    if python is None or not _ORACLE.exists():
        return None
    commande = [python, str(_ORACLE), str(page)]
    if accepter:
        commande.append("--accepter")
    try:
        resultat = subprocess.run(
            commande,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            # Sans cela l oracle plante en ECRIVANT son verdict : console cp1252, JSON accentue.
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        # Delai depasse : le pan se declare non mesure, il n emporte pas l audit entier.
        return None
    sortie = (resultat.stdout or "").strip()
    try:
        return json.loads(sortie) if sortie else None
    except json.JSONDecodeError:
        return None


def semer_goldens(reference: Path, cibles: list[Path]) -> int:
    """Fait du rendu de `reference` le golden de chaque cible. Hors boucle, jamais pendant un run."""
    captures = capturer(reference)
    poses = 0
    for cible in cibles:
        dossier = cible / DOSSIER
        dossier.mkdir(parents=True, exist_ok=True)
        for route, page in captures.items():
            copie = dossier / page.name
            if copie.resolve() != page.resolve():
                shutil.copy(page, copie)
            if _juger(copie, accepter=True) is not None:
                poses += 1
    return poses


def inventaire(cible: Path) -> list[Element]:
    source = str(cible / "frontend" / "src" / "routes.jsx")
    return [
        Element(f"visuel:{route}", PAN, f"rendu de la route {route}", source)
        for route in _routes(cible)
    ]


def analyser(cible: Path) -> SortieAdaptateur:
    captures = capturer(cible)
    if not captures:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, "front non servi : build absent, npm ou navigateur manquant"],
        )
    findings: list[Finding] = []
    non_juge = list(NON_JUGE)
    juges: list[str] = []
    sautes: list[str] = []
    for route, page in captures.items():
        rapport = _juger(page)
        if rapport is None:
            non_juge.append(f"visuel : route {route} non jugee (oracle injoignable)")
            continue
        non_juge.extend(f"visual-diff : {ligne}" for ligne in rapport.get("non_juge", []))
        if rapport.get("verdict") == "SKIP":
            sautes.append(route)
            continue
        juges.append(route)
        for brut in rapport.get("findings", []):
            if brut.get("sev") == "info":
                continue
            identifiant = f"visuel:{route}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe="regression-visuelle",
                    localisation=route,
                    message=f"[{route}] {brut.get('msg', '')}",
                    severite="bloquant" if brut.get("sev") == "bloquant" else "signale",
                    risque=coter(PAN, identifiant, str(cible / "frontend")),
                )
            )
    if sautes:
        non_juge.append(
            "visuel : golden absent pour " + ", ".join(sautes)
            + " — aucune creation automatique pendant un run (gouvernance R5)"
        )
    if not juges:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=sorted(set(non_juge)))
    non_juge.append(f"visuel : routes jugees — {', '.join(juges)}")
    bloquants = [f for f in findings if f.severite == "bloquant"]
    return SortieAdaptateur(
        adaptateur=NOM, pan=PAN, cible=str(cible),
        verdict="FAIL" if bloquants else "PASS",
        findings=findings, non_juge=sorted(set(non_juge)),
    )
