"""TF-2252 — la table de la revue statique du README nomme les pièges 5 à 9.

Fait remonté par la campagne du 06/11/2026 : la table du README ne nommait que les pièges 1 à 4
(plus 10 et 11, ajoutés par TF-2216), alors que `forge_tests/revue.py` en porte onze. Un lecteur du
README ignorait cinq règles que la revue applique et qui peuvent le refuser.

Sens prouvés : ROUGE (avant la correction, cinq lignes manquaient) et VERT ; contre-épreuve : le
garde lit la source de vérité (le module) pour savoir quels pièges existent, il ne recopie pas la
liste attendue.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
README = RACINE / "README.md"
REVUE = RACINE / "forge_tests" / "revue.py"

#: Un piège → un jeton qui le désigne dans la table (le TF qui l'a fondé, ou son nom).
JETONS = {
    1: "absence sans présence",
    2: "motif satisfait par le déclencheur",
    3: "cellule mutante",
    4: "TF-0345",
    5: "TF-0396",
    6: "TF-0395",
    7: "session fabriquée",
    8: "clé de relecture",
    9: "TF-0605",
    10: "boucle d'assertions",
    11: "attente terminée",
    12: "traitement attendu",
}


def _table_du_readme() -> str:
    texte = README.read_text(encoding="utf-8")
    debut = texte.index("## Revue statique de la suite")
    fin = texte.index("\n## ", debut + 1)
    return texte[debut:fin]


def _pieges_du_module() -> set[int]:
    """Les numéros de pièges que revue.py déclare : `**(N)` en docstring, et `piège (9)`."""
    texte = REVUE.read_text(encoding="utf-8")
    numeros = {int(n) for n in re.findall(r"\*\*\((\d+)\)", texte)}
    numeros |= {int(n) for n in re.findall(r"pi[eè]ge \((\d+)\)", texte, re.IGNORECASE)}
    return numeros


def test_chaque_piege_de_la_revue_a_sa_ligne_dans_la_table_du_readme() -> None:
    table = _table_du_readme()
    lignes = [ligne for ligne in table.splitlines() if ligne.startswith("| ")]
    manquants = {
        n: JETONS[n] for n in sorted(_pieges_du_module())
        if not any(JETONS[n] in ligne for ligne in lignes)
    }
    assert not manquants, f"pièges de revue.py absents de la table du README : {manquants}"


def test_le_garde_connait_tous_les_pieges_du_module() -> None:
    """Contre-épreuve : un piège neuf dans revue.py sans jeton ici ferait échouer ce garde."""
    inconnus = _pieges_du_module() - set(JETONS)
    assert not inconnus, f"piège(s) {sorted(inconnus)} de revue.py sans jeton dans ce garde"
    assert {5, 6, 7, 8, 9} <= _pieges_du_module(), "la source de vérité ne lit plus 5 à 9"
