"""TF-0866 — la suite entière doit rester COLLECTABLE, et un défaut de collecte se voit.

LE FAIT (constaté le 07/09/2026, dix-huit jours après sa pose). Le 20/08 (commit d6a7a84),
une passe d'anonymisation a remplacé un nom de produit par « Produit-09 » **à l'intérieur d'un
identifiant Python** — `def test_le_cas_Produit-09_FR_…` dans
`tests/test_tf_0401_manifeste_racines.py`. Le tiret est illégal dans un identifiant : Python
rend `SyntaxError: invalid decimal literal` à la COMPILATION du module, donc avant l'exécution
du moindre test. Sous `pytest -x`, la collecte s'arrête là et la suite ne joue pas.

Ce que la suite unitaire ne pouvait pas dire. Un test ne peut pas signaler l'absence du fichier
qui le contient : le module cassé n'est jamais importé, aucune assertion ne s'exécute, et le
rouge se présente comme une ERREUR DE COLLECTE — un statut qu'un opérateur pressé lit comme un
incident d'environnement, pas comme un défaut du dépôt. Dix-huit jours de suite non jouée, et
une réparation d'une ligne.

Le garde-fou : un test qui, lui, s'exécute, et qui COMPILE tous les modules du code de la forge
(`forge_tests/`, `tests/`, `recette/`) sans les importer. Un module qui ne parse pas devient un
échec nommé, avec son fichier et sa ligne, dans un rapport qui reste lisible.

Portée. Les bancs d'essai de `fixtures/` sont des DONNÉES d'acceptation — des produits factices
dont certains défauts sont plantés exprès — et restent hors du contrôle, comme ils sont déjà
hors du linter (`extend-exclude` de `pyproject.toml`).
"""

from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Le code de la forge, c'est-à-dire ce que la suite doit pouvoir collecter et jouer.
PAQUETS_DU_CODE = ("forge_tests", "tests", "recette")


def modules_non_compilables(racine: Path) -> list[tuple[str, int, str]]:
    """Rend `(chemin relatif, ligne, message)` pour chaque `.py` qui ne PARSE pas.

    Aucun import n'est fait : on compile le texte, donc un module aux dépendances absentes
    n'est pas accusé à tort. Les caches (`__pycache__`) sont ignorés.
    """
    fautifs: list[tuple[str, int, str]] = []
    for chemin in sorted(racine.rglob("*.py")):
        if "__pycache__" in chemin.parts:
            continue
        try:
            ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        except SyntaxError as erreur:
            fautifs.append((chemin.relative_to(racine).as_posix(), erreur.lineno or 0, erreur.msg))
    return fautifs


def test_aucun_module_du_code_de_la_forge_n_est_en_erreur_de_syntaxe() -> None:
    """Le contrôle réel : la suite du dépôt est collectable de bout en bout."""
    fautifs: list[tuple[str, int, str]] = []
    for paquet in PAQUETS_DU_CODE:
        fautifs.extend(modules_non_compilables(RACINE / paquet))

    assert fautifs == [], (
        "modules non compilables (la collecte de pytest s'arrêtera dessus) : "
        + " ; ".join(f"{f}:{ligne} — {message}" for f, ligne, message in fautifs)
    )


def test_le_defaut_de_TF_0866_est_bien_ATTRAPE(tmp_path: Path) -> None:
    """Fixture ROUGE : le pseudonyme à tiret posé DANS un identifiant est vu, et bien situé."""
    (tmp_path / "test_anonymise_a_tort.py").write_text(
        "def test_le_cas_Produit-09_FR_une_arborescence(tmp_path) -> None:\n    pass\n",
        encoding="utf-8",
    )

    fautifs = modules_non_compilables(tmp_path)

    assert len(fautifs) == 1, f"le défaut fondateur doit être vu une fois : {fautifs}"
    fichier, ligne, message = fautifs[0]
    assert fichier == "test_anonymise_a_tort.py"
    assert ligne == 1, "la LIGNE est publiée, sans quoi le message n'oriente pas la réparation"
    assert "invalid decimal literal" in message


def test_le_meme_nom_sans_tiret_passe(tmp_path: Path) -> None:
    """Fixture VERTE : la réparation prescrite (souligné au lieu du tiret) satisfait le contrôle."""
    (tmp_path / "test_anonymise_correctement.py").write_text(
        "def test_le_cas_Produit_09_FR_une_arborescence(tmp_path) -> None:\n    pass\n",
        encoding="utf-8",
    )

    assert modules_non_compilables(tmp_path) == []
