"""TF-2091 — la campagne de mutation pose un verrou pendant qu elle altere les sources EN PLACE.

La mutation ecrit un mutant dans un fichier source, rejoue la suite, puis restaure a l octet
pres. Entre la pose et la restauration, le fichier porte un code FAUX : une ecriture ou un commit
concurrent FIGE le mutant dans le depot (G-1 rompu le temps d un mutant — observe en reel : deux
recettes concurrentes qui mutent le meme banc laissaient un `importer.py` altere). Un verrou DIT
la fenetre ouverte — pid, heure, fichiers en cours, avertissement « ne pas commiter » — pour qu un
hook pre-commit de la factory refuse de commiter tant qu il existe. Il est retire
inconditionnellement, meme sur interruption.

Escalade (voir rapport) : le cote LECTURE du verrou (le hook pre-commit qui refuse) vit chez le
pilot / forge-ops, hors de ce depot ; muter une copie de travail complete reste l option lourde.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from forge_tests.adaptateurs import mutation

_NOM_VERROU = ".forge-tests-mutation-en-cours"


def test_verrou_pose_nomme_les_fichiers_et_avertit(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    fichier = tmp_path / "app" / "calcul.py"
    fichier.write_text("x = 1\n", encoding="utf-8")
    verrou = mutation._poser_verrou_mutation(tmp_path, [fichier])
    assert verrou is not None and verrou.exists()
    charge = json.loads(verrou.read_text(encoding="utf-8"))
    assert charge["pid"] == os.getpid()
    assert "app/calcul.py" in charge["fichiers"]
    assert "commiter" in charge["message"].lower()


def test_verrou_retire_inconditionnellement(tmp_path: Path) -> None:
    verrou = mutation._poser_verrou_mutation(tmp_path, [])
    mutation._retirer_verrou_mutation(verrou)
    assert not verrou.exists()
    # Idempotent et sur quand le verrou est deja parti ou absent (fenetre fermee, interruption).
    mutation._retirer_verrou_mutation(verrou)
    mutation._retirer_verrou_mutation(None)


def test_le_verrou_est_tenu_pendant_la_fenetre_de_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preuve du contrat : au moment ou la suite est rejouee sur CHAQUE mutant, le verrou EXISTE a
    la racine ; une fois la campagne finie, il est parti (le `finally` le defait)."""
    projet = tmp_path / "produit"
    app = projet / "app"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "calcul.py").write_text(
        "def signe(x):\n    if x > 0:\n        return 1\n    return 0\n", encoding="utf-8"
    )
    venv = projet / ".venv" / "Scripts"
    venv.mkdir(parents=True)
    # Presence seule de l interpreteur : `_suite_verte` est doublee, python.exe n est jamais lance.
    (venv / "python.exe").write_text("", encoding="utf-8")

    monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
    monkeypatch.setattr(mutation, "racine_execution", lambda _c: projet)
    monkeypatch.setattr(mutation, "paquet_sources", lambda _c: app)
    monkeypatch.setattr(mutation, "resume_fichiers", lambda _c: {})
    monkeypatch.setattr(mutation, "_suite_verte_ou_injouable", lambda _r, _p: True)
    monkeypatch.setattr(mutation, "_ciblage_demande", lambda: False)

    vu_pendant: list[bool] = []

    def _suite(racine: Path, _python: Path, _selection: object) -> bool:
        vu_pendant.append((racine / _NOM_VERROU).exists())
        return False  # mutant tue : la suite echoue sur le mutant

    monkeypatch.setattr(mutation, "_suite_verte", _suite)

    mutation.analyser(projet)

    # AVANT le correctif : aucun verrou pose, vu_pendant = [False, ...] -> l assertion echoue.
    assert vu_pendant, "la fenetre de mutation n a jamais ete atteinte (plan vide ?)"
    assert all(vu_pendant), "le verrou n est pas tenu pendant le rejeu d un mutant"
    # Fenetre fermee : le verrou est retire.
    assert not (projet / _NOM_VERROU).exists()
