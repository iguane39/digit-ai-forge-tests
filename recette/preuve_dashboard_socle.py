"""Preuve TF-0063 — le dashboard tient les règles du socle HTML (L1-L12, charte, rendu).

Construit une page depuis un rapport SYNTHÉTIQUE qui arme les règles en cause :
≥ 8 findings (L4 : tables filtrables), colonne « sévérité » (L3), sommaire (L6/L7).
La page est ensuite jugée par les oracles du socle — check_html et render_page —
exactement comme M2 de la recette S-01 le fait sur les bancs.

TF-0235 (15/08/2026) — l ÉTAGE AU-DESSUS du socle est jugé ici aussi : `oracle-restitution`
de forge-design vérifie que la page fait son travail auprès de ses lecteurs (famille déclarée,
verdict, KPI complets, figures à question, chemins de lecteur, manifeste d écarts). Le socle
dit « la page est-elle bien construite ? » ; celui-là dit « sert-elle son lecteur ? ». Les deux
sont dus, donc les deux sont prouvés au même endroit.

Usage : uv run python recette/preuve_dashboard_socle.py   (exit 0 = preuve tenue)
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _s.reconfigure(encoding="utf-8")


def _python_du_poste() -> list[str] | None:
    """Interpréteur HORS venv portant playwright — `uv run` préfixe le PATH du venv,
    donc la résolution est fonctionnelle (import réel), jamais un which nominal."""
    for candidat in (["py", "-3"], ["python"], [sys.executable]):
        with contextlib.suppress(Exception):
            essai = subprocess.run(
                [*candidat, "-c", "import playwright"],
                capture_output=True,
                timeout=30,
            )
            if essai.returncode == 0:
                return list(candidat)
    return None

def _oracle_restitution() -> Path | None:
    """`oracle-restitution.mjs` de forge-design, résolu comme le pilot résout les forges :
    `FORGE_ROOT` s il est posé, sinon le dossier PARENT de ce dépôt. Absent du poste : SKIP
    motivé — la preuve se dégrade, elle ne ment pas."""
    racine = os.environ.get("FORGE_ROOT")
    base = Path(racine) if racine else Path(__file__).resolve().parent.parent.parent
    chemin = base / "digit-ai-forge-design" / "oracles" / "oracle-restitution.mjs"
    return chemin if chemin.exists() else None


from forge_tests.livrables import dashboard as dash  # noqa: E402

RAPPORT = {
    "verdict": "FAIL",
    "seuils": {
        "couverture_api": {"valeur": 0.9, "severite": "bloquant", "porte_sur": "pan api"},
        "mutation": {"valeur": 0.6, "severite": "majeur", "porte_sur": "pan data"},
    },
    "findings": [
        {
            "id": f"code:GET /api/x{i}=200",
            "pan": "api",
            "severite": "bloquant" if i % 3 == 0 else "majeur",
            "classe": "assertion-fausse",
            "message": f"constat mesuré numéro {i} sur l endpoint x{i}",
            "localisation": f"tests/test_x{i}.py:12",
            "risque": 20 - i,
        }
        for i in range(10)
    ],
    "non_testables": [
        {
            "pan": "qualif",
            "element": f"route:/admin/{i}",
            "champs_requis": ["FORGE_TESTS_BASE_URL"],
            "motif": "configuration absente",
        }
        for i in range(9)
    ],
    "pans_non_couverts": [],
    "actions": [
        {
            "finding_ref": f"code:GET /api/x{i}=200",
            "categorie": "ia",
            "etape_cible": "development",
            "attendu": f"corriger l assertion du cas x{i}",
        }
        for i in range(10)
    ],
}
CONTEXTE = {
    "produit": "Preuve Socle",
    "date": "2026-08-11",
    "rapport_nom": "rapport-preuve.json",
    "rapport_sha": "0" * 64,
}
CHAPITRES = [
    {
        "famille": "fonctionnel",
        "code": "F1",
        "titre": "Parcours",
        "pans": ["api"],
        "decoupe": "route",
        "elements": 10,
        "rattaches": 10,
        "grise": False,
        "pans_non_couverts": [],
        "sous_chapitres": [
            {
                "libelle": "Endpoints",
                "elements": [
                    {
                        "id": f"code:GET /api/x{i}=200",
                        # État du VOCABULAIRE de `surface.ETATS` — « echec » n en fait pas
                        # partie : le glossaire le rendait alors en badge sans descriptif, et
                        # la preuve sortait rouge sur dix `title=""` (règle L3 du socle). Une
                        # fixture qui parle une langue que la forge ne connaît pas ne prouve
                        # rien sur la forge.
                        "etat": "defaut",
                        "classe": "assertion-fausse",
                        "message": f"constat {i}",
                        "risque": 20 - i,
                    }
                    for i in range(10)
                ],
            }
        ],
    },
]


def main() -> int:
    page = dash.construire(RAPPORT, CONTEXTE, CHAPITRES)
    sortie = Path(tempfile.mkdtemp(prefix="preuve-dash-")) / "dashboard.html"
    dash.ecrire(sortie, page, None)
    ecarts = dash.controler(page, RAPPORT)
    if ecarts:
        print("totaux infidèles :", ecarts)
        return 1
    skill = Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "scripts"
    verdicts = []
    for script, arguments in (("check_html.py", []), ("render_page.py", ["--widths", "1280,390"])):
        oracle = skill / script
        if not oracle.exists():
            print(f"[SKIP] {script} absent du poste — preuve partielle")
            continue
        # check_html tourne partout ; render_page exige playwright → python du poste.
        if script == "render_page.py":
            interpreteur = _python_du_poste()
            if interpreteur is None:
                print(f"[SKIP] {script} — aucun interpréteur avec playwright (preuve partielle)")
                continue
        else:
            interpreteur = [sys.executable]
        resultat = subprocess.run(
            [*interpreteur, str(oracle), str(sortie), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        verdicts.append((script, resultat.returncode))
        print(f"[{'PASS' if resultat.returncode == 0 else 'FAIL'}] {script}")
        if resultat.returncode != 0:
            print(((resultat.stdout or "") + (resultat.stderr or ""))[-1400:])

    # TF-0235 — l étage « restitution » : la page sert-elle ses lecteurs ? Exit 2 = SKIP motivé
    # de l oracle (page hors périmètre déclaré) : c est un ÉCHEC ici, puisque ce dashboard, lui,
    # doit déclarer sa famille « suivi ».
    restitution = _oracle_restitution()
    node = shutil.which("node")
    if restitution is None:
        print("[SKIP] oracle-restitution — forge-design absente du poste (preuve partielle)")
    elif node is None:
        print("[SKIP] oracle-restitution — node absent du poste (preuve partielle)")
    else:
        resultat = subprocess.run(
            [node, str(restitution), str(sortie), "--json-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        verdicts.append(("oracle-restitution", resultat.returncode))
        print(f"[{'PASS' if resultat.returncode == 0 else 'FAIL'}] oracle-restitution")
        if resultat.returncode != 0:
            print(((resultat.stdout or "") + (resultat.stderr or ""))[-1400:])

    return 1 if any(code != 0 for _, code in verdicts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
