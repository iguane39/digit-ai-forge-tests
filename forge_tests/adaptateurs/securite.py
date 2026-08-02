"""Adaptateur Sécurité (Q4) — câblage des oracles existants, sans en réécrire un seul.

Trois oracles du registre `quality-oracles` existent, sont exécutables, et n avaient jamais été
appelés par Forge Tests : SAST (injection, exécution dangereuse), SCA (vulnérabilités de
dépendances), secrets. Les réécrire aurait violé la règle R3 — on s appuie sur l outil qui fait
foi. Cet adaptateur les invoque et traduit leur contrat de sortie dans celui du framework.

Propriété importante : leurs `non_juge` sont REPRIS tels quels. Ce que ces oracles ne jugent
pas devient de la dette déclarée du framework, pas une limite invisible héritée en silence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "securite-oracles", "securite"
ORACLES = ("sast", "secrets", "sca")

_DEFAUT = Path.home() / ".claude" / "skills" / "quality-oracles" / "scripts"

# Nom attendu par le registre de dette. Les non_juge des oracles delegues s y ajoutent a
# l execution : ils dependent des outils reellement presents (semgrep, gitleaks, pip-audit).
NON_JUGE = [
    "securite : le perimetre scanne est le dossier applicatif ; ni l historique git, ni "
    "l infrastructure, ni la configuration de deploiement",
    "securite : aucun test d intrusion ni d authentification/autorisation au niveau metier",
]


def _racine_oracles() -> Path | None:
    declare = os.environ.get("FORGE_TESTS_ORACLES")
    if declare and Path(declare).is_dir():
        return Path(declare)
    return _DEFAUT if _DEFAUT.is_dir() else None


def _lancer(script: Path, cible: Path) -> dict | None:
    node = shutil.which("node")
    if node is None:
        return None
    resultat = subprocess.run(
        [node, str(script), str(cible)],
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
        errors="replace",
    )
    sortie = (resultat.stdout or "").strip()
    if not sortie:
        return None
    try:
        return json.loads(sortie)
    except json.JSONDecodeError:
        return None


def analyser(cible: Path) -> SortieAdaptateur:
    racine = _racine_oracles()
    application = cible / "backend" / "app"
    if racine is None or not application.is_dir():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "registre d oracles introuvable : definir FORGE_TESTS_ORACLES vers le dossier "
                "scripts de quality-oracles",
            ],
        )

    findings: list[Finding] = []
    non_juge: list[str] = list(NON_JUGE)
    echec = False
    joues: list[str] = []

    for nom in ORACLES:
        script = racine / f"oracle-{nom}.mjs"
        if not script.exists():
            non_juge.append(f"securite : oracle-{nom} absent du registre, non joue")
            continue
        rapport = _lancer(script, application)
        if rapport is None:
            non_juge.append(f"securite : oracle-{nom} n a produit aucun verdict exploitable")
            continue
        joues.append(nom)
        # Les limites de l oracle delegue deviennent de la dette DECLAREE du framework.
        non_juge.extend(f"securite/{nom} : {ligne}" for ligne in rapport.get("non_juge", []))
        if rapport.get("verdict") != "FAIL":
            continue
        echec = True
        for brut in rapport.get("findings", []):
            if brut.get("sev") == "info":
                continue
            identifiant = f"securite:{nom}:{brut.get('where', application.name)}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe="securite",
                    localisation=str(brut.get("where") or application),
                    message=f"[{nom}] {brut.get('msg', '')}",
                    severite="bloquant" if brut.get("sev") == "bloquant" else "signale",
                    risque=coter(PAN, identifiant, str(application)),
                )
            )

    if not joues:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*non_juge, "aucun oracle de securite n a pu etre joue"],
        )
    non_juge.append(f"securite : oracles reellement joues — {', '.join(joues)}")
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if echec and any(f.severite == "bloquant" for f in findings) else "PASS",
        findings=findings,
        non_juge=non_juge,
    )
