"""TF-0104 — quatre trous d outillage vs l état de l art 2026 : v0 par sous-item.

Chaque v0 est une capacité RÉELLE et testée, pas une intégration complète dans le pipeline
d audit : la sélection par diff (1), la détection de flaky (2) et les squelettes de propriété
(3) sont des modules autonomes, appelables ; l échantillonnage de mutation orienté par le
risque (4) est une fonction pure de répartition. Le câblage de chacun dans le run principal
(`--reprendre --depuis`, l appel des squelettes proposés depuis le générateur, l emploi de
`repartir_mutants` dans `adaptateurs/mutation.py`) est un reste explicite, pas fait ici.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from forge_tests import flaky, impact
from forge_tests import generateur_proprietes as gp
from forge_tests import risque


# --- 1/4 — sélection par impact de diff ---------------------------------------------------
def test_impact_cartographie_les_prefixes_connus() -> None:
    impactes, orphelins = impact.pans_impactes(
        [
            "backend/app/db/models.py",
            "backend/migrations/0002_x.sql",
            "frontend/src/App.tsx",
        ]
    )
    assert impactes == {"data", "migrations", "front"}
    assert orphelins == set()


def test_impact_un_fichier_hors_cartographie_interdit_toute_reduction() -> None:
    """ROUGE implicite : sans ce garde, un fichier inconnu (ex. script racine) serait ignoré."""
    impactes, orphelins = impact.pans_impactes(["scripts/deploiement.sh"])
    assert orphelins == {"scripts/deploiement.sh"}
    assert impactes == set()


def test_impact_selection_reduit_quand_surs(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("x = 2\n", encoding="utf-8")

    resultat = impact.selection(tmp_path, ["api", "data", "front"], depuis="HEAD")

    assert resultat["mode"] == "cible"
    assert resultat["pans"] == ["api"]


def test_impact_selection_repli_complet_si_fichier_inconnu(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "deploy.sh").write_text("echo 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "deploy.sh").write_text("echo 2\n", encoding="utf-8")

    resultat = impact.selection(tmp_path, ["api", "data"], depuis="HEAD")

    # ROUGE implicite : une reduction naive aurait ici rendu `pans: []` (aucun prefixe connu) —
    # au lieu de quoi le repli complet est explicite, avec son motif.
    assert resultat["mode"] == "complet"
    assert resultat["pans"] == ["api", "data"]


def test_impact_git_indisponible_replie_sur_complet(tmp_path: Path) -> None:
    resultat = impact.selection(tmp_path, ["api", "data"], depuis="HEAD")
    assert resultat["mode"] == "complet"
    assert "indisponible" in resultat["motif"]


# --- 2/4 — détection de tests instables (flaky) --------------------------------------------
def test_resultats_par_test_lit_les_deux_ordres_de_verdict() -> None:
    sortie = "tests/test_x.py::test_a PASSED\nFAILED tests/test_x.py::test_b\n"
    releve = flaky.resultats_par_test(sortie)
    assert releve == {"tests/test_x.py::test_a": "PASSED", "tests/test_x.py::test_b": "FAILED"}


def test_rejouer_detecte_un_test_reellement_instable(tmp_path: Path) -> None:
    """Script dont le verdict alterne à chaque appel — flaky reproductible et déterministe."""
    compteur = tmp_path / "compteur.txt"
    compteur.write_text("0", encoding="utf-8")
    script = tmp_path / "suite.py"
    script.write_text(
        "from pathlib import Path\n"
        "c = Path(__file__).parent / 'compteur.txt'\n"
        "n = int(c.read_text()) + 1\n"
        "c.write_text(str(n))\n"
        "verdict = 'PASSED' if n % 2 else 'FAILED'\n"
        "print(f'tests/test_x.py::test_instable {verdict}')\n"
        "print('tests/test_x.py::test_stable PASSED')\n",
        encoding="utf-8",
    )

    resultat = flaky.rejouer([sys.executable, str(script)], cwd=tmp_path, repetitions=4)

    assert "tests/test_x.py::test_instable" in resultat["tests_instables"]
    assert "tests/test_x.py::test_stable" not in resultat["tests_instables"]
    assert resultat["repetitions"] == 4


def test_rejouer_exige_au_moins_deux_repetitions(tmp_path: Path) -> None:
    try:
        flaky.rejouer([sys.executable, "-c", "pass"], cwd=tmp_path, repetitions=1)
    except ValueError:
        return
    raise AssertionError("rejouer(repetitions=1) aurait du lever ValueError")


# --- 3/4 — squelettes de propriété (Hypothesis) --------------------------------------------
def test_candidats_retient_une_fonction_pure_a_deux_parametres(tmp_path: Path) -> None:
    module = tmp_path / "backend" / "app" / "calcul.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "def additionner(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n"
        "def _prive(a: int, b: int) -> int:\n"
        "    return a - b\n"
        "\n"
        "def ecrire_fichier(chemin: str, contenu: str) -> None:\n"
        "    with open(chemin, 'w') as f:\n"
        "        f.write(contenu)\n"
        "\n"
        "def solitaire(a: int) -> int:\n"
        "    return a\n",
        encoding="utf-8",
    )

    trouves = gp.candidats(tmp_path)
    noms = {c.fonction for c in trouves}

    # ROUGE implicite : sans le filtre de purete/parametres, `ecrire_fichier` (effet de bord) et
    # `_prive`/`solitaire` (prefixe prive / un seul parametre) seraient proposes a tort.
    assert noms == {"additionner"}


def test_squelette_ne_devine_jamais_la_propriete(tmp_path: Path) -> None:
    module = tmp_path / "backend" / "app" / "calcul.py"
    module.parent.mkdir(parents=True)
    module.write_text("def additionner(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    contenu = gp.proposer(tmp_path)

    assert "TODO" in contenu
    assert "assert True" in contenu
    assert "@given(a=st.integers(), b=st.integers())" in contenu


def test_proposer_chaine_vide_sans_candidat(tmp_path: Path) -> None:
    assert gp.proposer(tmp_path) == ""


# --- 4/4 — échantillonnage de mutation orienté par le risque -------------------------------
def test_repartir_mutants_favorise_le_fichier_le_plus_change(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    chaud = tmp_path / "chaud.py"
    froid = tmp_path / "froid.py"
    chaud.write_text("x = 1\n", encoding="utf-8")
    froid.write_text("y = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    for n in range(4):
        chaud.write_text(f"x = {n + 2}\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"maj {n}"], cwd=tmp_path, check=True)
    risque.probabilite.cache_clear()

    repartition = risque.repartir_mutants([str(chaud), str(froid)], budget_total=10)

    # ROUGE implicite : un echantillonnage REGULIER (le defaut actuel) donnerait 5 et 5.
    assert repartition[str(chaud)] > repartition[str(froid)]
    assert repartition[str(froid)] >= 1  # minimum garanti : jamais 0 mutant


def test_repartir_mutants_minimum_garanti_meme_sans_budget_suffisant() -> None:
    risque.probabilite.cache_clear()
    repartition = risque.repartir_mutants(
        ["/inexistant/a.py", "/inexistant/b.py", "/inexistant/c.py"], budget_total=1
    )
    assert all(v >= 1 for v in repartition.values())


def test_repartir_mutants_vide_sans_fichiers_ou_sans_budget() -> None:
    assert risque.repartir_mutants([], budget_total=10) == {}
    assert risque.repartir_mutants(["a.py"], budget_total=0) == {}
