"""Palier 1 de la strategie de tests (etude du 01/09/2026) — le ciblage par ligne mutee.

CE QUE CES TESTS PROUVENT, et ce qu ils ne prouvent pas. Ils eprouvent les fonctions PURES de
selection et le point unique ou le palier touche l execution. Ils NE prouvent PAS la condition
de non-perte de l etude — meme liste de survivants que la campagne pleine —, qui exige un projet
reel dote de `coverage` : elle est declaree non jouee au rapport
(`mutation.ciblage.non_perte_jouee`)
plutot que supposee tenue.

Chaque test porte son SENS ROUGE : ce qui casse si la regle se defait.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import mutation


def test_le_suffixe_de_phase_est_retire_du_contexte() -> None:
    """ROUGE : sans le decoupage sur la barre, pytest recevrait `...::test_x|run`, un nodeid
    qui n existe pas — selection vide, mutant declare tue sans qu aucun test ne l ait vu."""
    carte = mutation._lire_contextes({
        "files": {"app/calcul.py": {"contexts": {"12": ["tests/test_calcul.py::test_somme|run"]}}}
    })
    assert carte == {"app/calcul.py": {12: ["tests/test_calcul.py::test_somme"]}}


def test_les_phases_setup_et_run_du_meme_test_ne_font_qu_une_cible() -> None:
    """Une fixture et son test donnent DEUX contextes pour la meme ligne. Les passer tels quels
    ferait jouer deux fois le meme nodeid."""
    carte = mutation._lire_contextes({
        "files": {"app/calcul.py": {"contexts": {"7": [
            "tests/test_calcul.py::test_somme|setup",
            "tests/test_calcul.py::test_somme|run",
        ]}}}
    })
    assert carte["app/calcul.py"][7] == ["tests/test_calcul.py::test_somme"]


def test_une_ligne_executee_hors_de_tout_test_ne_produit_aucune_cible() -> None:
    """Le contexte VIDE, c est l import a la collecte. Le retenir comme cible produirait une
    selection vide passee a pytest ; le declarer « aucun test » ferait sauter le mutant. Ni l un
    ni l autre : la ligne sort de la carte, et l appelant retombe sur la suite entiere."""
    carte = mutation._lire_contextes({
        "files": {"app/models.py": {"contexts": {"1": [""], "2": ["", "tests/t.py::test_a|run"]}}}
    })
    assert 1 not in carte.get("app/models.py", {})
    assert carte["app/models.py"][2] == ["tests/t.py::test_a"]


def test_sans_carte_ou_sans_couverture_on_rejoue_la_suite_entiere() -> None:
    """None n est pas « aucun test » : c est « je ne sais pas ». Confondre les deux est le mode
    d echec le plus cher du palier — un mutant jamais eprouve et compte comme tue."""
    assert mutation._tests_pour(None, "app/calcul.py", 12) is None
    carte = {"app/calcul.py": {12: ["tests/t.py::test_a"]}}
    assert mutation._tests_pour(carte, "app/calcul.py", 99) is None
    assert mutation._tests_pour(carte, "app/autre.py", 12) is None
    assert mutation._tests_pour(carte, "app/calcul.py", 12) == ["tests/t.py::test_a"]


def test_la_selection_est_bien_ce_que_pytest_recoit(monkeypatch) -> None:
    """Le seul point ou le palier touche l execution. ROUGE : si `cibles` etait ignore, la
    campagne resterait a 28,2 s par mutant en croyant avoir gagne un facteur onze."""
    vus: list[list[str]] = []

    class _Fini:
        returncode = 0

    def _faux_run(argv, **_kw):
        vus.append(list(argv))
        return _Fini()

    monkeypatch.setattr(mutation.subprocess, "run", _faux_run)
    monkeypatch.setattr(mutation, "_purger_bytecode", lambda _racine: None)
    racine, python = Path("."), Path("python")

    mutation._suite_verte(racine, python, ["tests/t.py::test_a", "tests/t.py::test_b"])
    assert "tests/t.py::test_a" in vus[-1] and "tests/t.py::test_b" in vus[-1]
    assert mutation.SUITE not in vus[-1]

    mutation._suite_verte(racine, python, None)
    assert mutation.SUITE in vus[-1]
    mutation._suite_verte(racine, python, [])
    assert mutation.SUITE in vus[-1]


def test_le_ciblage_est_absent_par_defaut(monkeypatch) -> None:
    """Loi transverse n° 2 : la voie neuve vit derriere un drapeau ABSENT par defaut tant que la
    condition de non-perte n a pas ete jouee sur un projet reel."""
    monkeypatch.delenv("FORGE_TESTS_MUTATION_CIBLAGE", raising=False)
    assert mutation._ciblage_demande() is False
    monkeypatch.setenv("FORGE_TESTS_MUTATION_CIBLAGE", "1")
    assert mutation._ciblage_demande() is True
    monkeypatch.setenv("FORGE_TESTS_MUTATION_CIBLAGE", "0")
    assert mutation._ciblage_demande() is False
