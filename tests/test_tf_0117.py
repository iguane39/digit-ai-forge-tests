"""TF-0117 — le dashboard du banc-rouge affichait « NULL » littéral × 24 dans ses cellules.

Constat réel (12/08) : `check_html.py` échoue sur le dashboard produit depuis le rapport du
banc-rouge — règle L11 du socle (« aucun littéral de langage — null/None/undefined — dans le
texte visible : une valeur non renseignée doit être traitée par le producteur »).

Sur pièces (recalculé, pas recopié) : les 24 occurrences ne sont PAS des valeurs absentes qui
ont fuité — `_e()` traite déjà toute valeur manquante en chaîne vide. Ce sont des constats qui
NOMMENT fidèlement une contrainte SQL du produit audité (`{colonne} NOT NULL : inventorié,
jamais exercé par la suite`, forgé par `forge_tests.noyau` à partir du libellé posé par
`forge_tests.adaptateurs.data`). Le mot « NULL » de « NOT NULL » matche la même regex que le
littéral technique que L11 traque, sans discriminer le contexte — un faux positif de l oracle
sur du vocabulaire du domaine, pas un défaut de contenu.

Le socle prévoit l échappatoire prévue pour ce cas exact : l attribut `data-litteral-ok`, qui
dit à L11 « ce mot est cité fidèlement, ce n est pas une valeur non traitée ». Le correctif
l applique aux TROIS colonnes de texte libre qui portaient les 24 occurrences (le « constat
mesuré » des chapitres, la « raison mesurée » des échecs, l « attendu » des actions) — jamais
aux colonnes structurées (état, classe, sévérité…), qui doivent continuer de dénoncer un
littéral non traité si l une d elles en laissait fuir un demain.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from forge_tests.livrables import dashboard as dash

RAPPORT = {
    "verdict": "FAIL",
    "seuils": {},
    "findings": [
        {
            "id": "contrainte:email.not_null",
            "pan": "data",
            "severite": "signale",
            "classe": "element-non-exerce",
            "message": "email NOT NULL : inventorie, jamais exerce par la suite",
            "localisation": "backend/app/models.py",
            "risque": 5,
        }
    ],
    "non_testables": [],
    "pans_non_couverts": [],
    "actions": [
        {
            "finding_ref": "contrainte:email.not_null",
            "categorie": "manuelle_dev",
            "etape_cible": "development",
            "attendu": (
                "générer un jeu qui viole la contrainte (email NOT NULL : inventorie, "
                "jamais exerce par la suite)"
            ),
        }
    ],
}
CONTEXTE = {
    "produit": "Preuve TF-0117", "date": "2026-08-12", "rapport_nom": "r.json",
    "rapport_sha": "0" * 64,
}
CHAPITRES = [
    {
        "famille": "technique", "code": "T1", "titre": "Contraintes", "pans": ["data"],
        "decoupe": "table", "elements": 1, "rattaches": 1, "grise": False,
        "pans_non_couverts": [],
        "sous_chapitres": [
            {
                "libelle": "table t",
                "elements": [
                    {
                        "id": "contrainte:email.not_null", "etat": "non_exerce",
                        "classe": "element-non-exerce",
                        "message": "email NOT NULL : inventorie, jamais exerce par la suite",
                        "risque": 5,
                    },
                ],
            },
        ],
    },
]


def test_texte_libre_enveloppe_le_constat_dans_le_garde_de_loracle_socle() -> None:
    rendu = dash._texte_libre("email NOT NULL : inventorie, jamais exerce par la suite")
    assert rendu == (
        "<span data-litteral-ok>email NOT NULL : inventorie, jamais exerce par la suite</span>"
    )


def test_texte_libre_continue_de_vider_une_valeur_absente() -> None:
    """Non-régression : `_texte_libre` ne doit jamais afficher un littéral pour une VRAIE
    valeur manquante — il délègue à `_e`, qui rend déjà None en chaîne vide."""
    assert dash._texte_libre(None) == "<span data-litteral-ok></span>"


def test_dashboard_ne_publie_plus_null_hors_du_garde_data_litteral_ok() -> None:
    """ROUGE implicite : avant le correctif, ces trois colonnes rendaient `_e(...)` seul — le
    mot « NULL » de « NOT NULL » apparaissait NU dans le texte visible, exactement ce que L11
    dénonce. Ici, toute occurrence du mot est à l intérieur du garde."""
    page = dash.construire(RAPPORT, CONTEXTE, CHAPITRES)
    occurrences = list(re.finditer(r"NULL", page))
    assert occurrences, "le cas de test n exerce plus le mot NOT NULL — fixture caduque"
    for match in occurrences:
        alentours = page[max(0, match.start() - 80) : match.start()]
        assert "data-litteral-ok" in alentours, (
            f"« NULL » hors garde : {page[match.start() - 40 : match.start() + 20]!r}"
        )


def test_check_html_pass_sur_un_constat_qui_cite_not_null(tmp_path: Path) -> None:
    """Preuve exécutée, pas de confiance : l oracle socle réel doit rendre PASS. Reproduit sur
    pièces le 12/08 : le même contenu, SANS le garde, faisait échouer check_html.py (verdict
    FAIL, « L11 littéral de langage… « NULL » × 24 »)."""
    page = dash.construire(RAPPORT, CONTEXTE, CHAPITRES)
    sortie = tmp_path / "dashboard.html"
    dash.ecrire(sortie, page, None)

    oracle = Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "scripts" / "check_html.py"
    if not oracle.exists():
        return  # DECLARE, jamais contourne — meme convention que verifier_dashboard (recette)

    resultat = subprocess.run(
        [sys.executable, str(oracle), str(sortie)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert resultat.returncode == 0, (resultat.stdout or "") + (resultat.stderr or "")
