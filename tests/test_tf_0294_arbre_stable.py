"""TF-0294 — la recette prononçait S-01 sur un arbre qui bougeait sous elle.

Fait mesure, DEUX fois le 15/08/2026 : `recette/verifier_corpus.py` lancee pendant qu une
campagne concurrente modifiait le depot a rendu « S-01 NON TENU » sur les sections `lint` puis
`corpus` et `dette`. Des echecs FANTOMES, indiscernables d une regression reelle — l un a coute
une instruction complete avant d etre ecarte. Rejouee sur arbre stable : 13/13 sections, S-01
TENU. Avec deux campagnes concurrentes sur un meme depot (situation devenue courante), le piege
est structurel : la section `dette` compare le registre COMMITTE au code, et les deux bougeaient.

La regle posee : l empreinte de l arbre de travail est relevee a l OUVERTURE, re-relevee a la
FERMETURE, et si elle a bouge le verdict est REFUSE — un troisieme etat, ni TENU ni NON TENU.
Un verdict rendu sur un arbre instable n est pas un verdict.

Double sens systematique : chaque cas ou l instabilite doit etre DENONCEE porte son temoin ou
elle ne doit PAS l etre — sans quoi le garde-fou pourrait tout refuser et passerait pour vert.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recette import verifier_corpus as vc  # noqa: E402


def _depot(racine: Path) -> None:
    """Un vrai depot git : le perimetre du releve est celui de git, il faut donc un git."""
    subprocess.run(["git", "init", "-q", str(racine)], check=True, capture_output=True)
    (racine / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    (racine / "module.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (racine / "registre.json").write_text('{"dette": []}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(racine), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(racine), "-c", "user.email=r@r", "-c", "user.name=r",
         "commit", "-qm", "socle"],
        check=True, capture_output=True,
    )


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    _depot(tmp_path)
    return tmp_path


# --- Le releve lui-meme -----------------------------------------------------------------------
def test_l_empreinte_couvre_les_fichiers_suivis(depot: Path) -> None:
    empreintes = vc.empreinte_arbre(depot)
    assert empreintes is not None
    assert "module.py" in empreintes
    assert "registre.json" in empreintes


def test_l_empreinte_couvre_aussi_le_non_suivi_non_ignore(depot: Path) -> None:
    """Une campagne qui AJOUTE un fichier fait bouger l arbre autant qu une qui en modifie un."""
    (depot / "neuf.py").write_text("x = 1\n", encoding="utf-8")
    empreintes = vc.empreinte_arbre(depot)
    assert empreintes is not None and "neuf.py" in empreintes


def test_l_empreinte_ignore_ce_que_git_ignore(depot: Path) -> None:
    """TEMOIN : la recette ecrit elle-meme des caches. S ils entraient au releve, elle se
    declarerait instable a chaque passage — un garde-fou qui refuse toujours ne garde rien."""
    (depot / "__pycache__").mkdir()
    (depot / "__pycache__" / "module.cpython-311.pyc").write_bytes(b"\x00\x01")
    empreintes = vc.empreinte_arbre(depot)
    assert empreintes is not None
    assert not [chemin for chemin in empreintes if "__pycache__" in chemin]


def test_hors_git_l_empreinte_est_None_jamais_un_dictionnaire_vide(tmp_path: Path) -> None:
    """`None` (non mesurable) et `{}` (arbre vide) ne disent pas la meme chose."""
    assert vc.empreinte_arbre(tmp_path / "pas-un-depot") is None


# --- Le verdict d instabilite -----------------------------------------------------------------
def test_un_arbre_immobile_est_declare_STABLE(depot: Path) -> None:
    avant = vc.empreinte_arbre(depot)
    assert vc.instabilites(avant, vc.empreinte_arbre(depot)) == []


def test_un_fichier_MODIFIE_pendant_la_recette_est_denonce_et_nomme(depot: Path) -> None:
    avant = vc.empreinte_arbre(depot)
    (depot / "module.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    bouges = vc.instabilites(avant, vc.empreinte_arbre(depot))
    assert bouges == ["module.py (modifie)"]


def test_un_fichier_APPARU_pendant_la_recette_est_denonce(depot: Path) -> None:
    avant = vc.empreinte_arbre(depot)
    (depot / "neuf.py").write_text("x = 1\n", encoding="utf-8")
    assert vc.instabilites(avant, vc.empreinte_arbre(depot)) == ["neuf.py (apparu)"]


def test_un_fichier_DISPARU_pendant_la_recette_est_denonce(depot: Path) -> None:
    avant = vc.empreinte_arbre(depot)
    (depot / "registre.json").unlink()
    assert vc.instabilites(avant, vc.empreinte_arbre(depot)) == ["registre.json (disparu)"]


def test_un_cache_ecrit_par_la_recette_ne_rend_pas_l_arbre_instable(depot: Path) -> None:
    """Le second sens du temoin ci-dessus, au niveau du VERDICT : la recette a le droit
    d ecrire ce que git ignore, sans quoi elle refuserait de conclure a chaque fois."""
    avant = vc.empreinte_arbre(depot)
    (depot / "__pycache__").mkdir()
    (depot / "__pycache__" / "module.cpython-311.pyc").write_bytes(b"\x00")
    assert vc.instabilites(avant, vc.empreinte_arbre(depot)) == []


def test_une_alteration_G1_deja_nommee_n_est_PAS_comptee_comme_instabilite(depot: Path) -> None:
    """Un source de banc que la restauration apres mutation n a pas rendu a l octet pres est un
    ECHEC MESURE, deja nomme par la section `corpus`. Le recompter ici transformerait la
    regression que la recette vient de trouver en « arbre instable, verdict refuse » — c est-a-
    dire l effacerait. C est le cas ou le garde-fou doit se TAIRE."""
    avant = vc.empreinte_arbre(depot)
    (depot / "module.py").write_text("def f():\r\n    return 1\r\n", encoding="utf-8")
    nomme = f"banc-rouge/{(depot / 'module.py').as_posix()}"
    assert vc.instabilites(avant, vc.empreinte_arbre(depot), [nomme]) == []
    # TEMOIN : sans cette altération déclarée, le même fichier EST une instabilité.
    assert vc.instabilites(avant, vc.empreinte_arbre(depot)) == ["module.py (modifie)"]


def test_une_alteration_G1_sur_un_AUTRE_fichier_n_absout_rien(depot: Path) -> None:
    """L ecart ne se fait pas en bloc : G-1 nomme des fichiers, pas une permission generale."""
    avant = vc.empreinte_arbre(depot)
    (depot / "module.py").write_text("def f():\n    return 3\n", encoding="utf-8")
    nomme = f"banc-rouge/{(depot / 'registre.json').as_posix()}"
    assert vc.instabilites(avant, vc.empreinte_arbre(depot), [nomme]) == ["module.py (modifie)"]


def test_une_empreinte_non_relevee_ne_fabrique_pas_de_fausse_instabilite() -> None:
    """Git muet : la stabilite est NON VERIFIEE et le verdict le DIT (main() l imprime), mais
    l absence de mesure ne se convertit pas en accusation."""
    assert vc.instabilites(None, {"a": "1"}) == []
    assert vc.instabilites({"a": "1"}, None) == []


# --- Le verdict rendu par la recette entiere ---------------------------------------------------
def test_la_recette_REFUSE_de_prononcer_et_sort_2_quand_l_arbre_bouge(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas vecu du 15/08, joue de bout en bout sur la section la moins couteuse : l arbre
    bouge PENDANT la recette. Attendu : ni « S-01 TENU », ni « S-01 NON TENU » — un refus."""
    _depot(tmp_path)
    releves = [vc.empreinte_arbre(tmp_path)]
    (tmp_path / "module.py").write_text("def f():\n    return 99\n", encoding="utf-8")
    releves.append(vc.empreinte_arbre(tmp_path))

    monkeypatch.setattr(vc, "empreinte_arbre", lambda *_a, **_k: releves.pop(0))
    monkeypatch.setattr(vc, "verifier_lecture_sql", lambda: 0)

    code = vc.main(["--section", "sql"])
    sortie = capsys.readouterr().out
    assert code == 2
    assert "ARBRE INSTABLE" in sortie and "VERDICT REFUSÉ" in sortie
    assert "module.py (modifie)" in sortie
    assert "S-01 NON TENU" not in sortie and "S-01 TENU" not in sortie


def test_sur_arbre_STABLE_la_recette_prononce_normalement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second sens : le garde-fou ne doit rien empecher quand l arbre ne bouge pas."""
    _depot(tmp_path)
    monkeypatch.setattr(vc, "empreinte_arbre", lambda *_a, **_k: {"module.py": "identique"})
    monkeypatch.setattr(vc, "verifier_lecture_sql", lambda: 0)

    code = vc.main(["--section", "sql"])
    sortie = capsys.readouterr().out
    assert code == 0
    assert "ARBRE INSTABLE" not in sortie
    # Recette PARTIELLE : S-01 reste non prononce pour la raison qui existait deja.
    assert "RECETTE PARTIELLE" in sortie
