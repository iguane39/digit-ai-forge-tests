"""TF-0279 — l identifiant d un constat SAST embarquait le dossier temporaire de la passe.

Fait mesure (etude 20260815e, verdict O2) : le pan `securite` copie les sources du produit dans
`forge-tests-securite-<alea>/sources/` avant de les tendre aux oracles delegues. `oracle-secrets`
publie un `where` ABSOLU — `_relocaliser` remplace le prefixe et l identifiant vaut le chemin
PROJET (112/112 contestations prises). `oracle-sast`, lui, publie
`path.relative(process.cwd(), fichier)` : un chemin RELATIF ou le prefixe absolu n apparait pas.
Le remplacement echouait donc en SILENCE et l identifiant gardait l alea de la passe. Verifie sur
trois runs (lgvdcxei, qyoth9pg, ccnh5t5j) : aucune ligne de `constats-contestes.jsonl` ne pouvait
matcher d une passe a l autre — la contestation d un constat SAST etait mecaniquement impossible,
alors meme que le mecanisme existait et fonctionnait pour l oracle d a cote.

ROUGE : `test_l_id_survit_a_deux_passes` echoue avant le correctif — les deux identifiants
different par le nom tire au sort du brouillon.

Ici on ne joue pas node : c est le CONTRAT de sortie des oracles qui est rejoue (`_lancer`
simule), a l identique de ce que leur code source produit. Le defaut vit dans la traduction, pas
dans l oracle.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite
from forge_tests.disposition import racine_execution


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _registre(racine: Path) -> Path:
    """Un registre d oracles ou SEUL `oracle-sast` existe : les autres se declarent absents."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "oracle-sast.mjs").write_text("", encoding="utf-8")
    return racine


def _produit(racine: Path) -> Path:
    (racine / "backend" / "app").mkdir(parents=True)
    (racine / "backend" / "app" / "requetes.py").write_text(
        'def lire(cursor, nom):\n    cursor.execute(f"SELECT * FROM client WHERE nom={nom}")\n',
        encoding="utf-8",
    )
    return racine


def _sast_relatif(script: Path, scan: Path) -> dict:
    """Rejoue le contrat de sortie d `oracle-sast` : `where` RELATIF au dossier courant.

    Une ligne du script reel : `where: path.relative(process.cwd(), f) + ':' + (i + 1)`.
    """
    fichier = sorted(Path(scan).rglob("*.py"))[0]
    return {
        "verdict": "FAIL",
        "findings": [
            {
                "sev": "bloquant",
                "msg": "injection SQL : f-string dans execute()",
                "where": os.path.relpath(fichier, Path.cwd()) + ":2",
            }
        ],
        "non_juge": [],
    }


def _sast_absolu(script: Path, scan: Path) -> dict:
    """Contrat d `oracle-secrets` : `where` ABSOLU — la forme deja ré-étiquetée avant TF-0279."""
    fichier = sorted(Path(scan).rglob("*.py"))[0]
    return {
        "verdict": "FAIL",
        "findings": [{"sev": "bloquant", "msg": "secret en clair", "where": str(fichier)}],
        "non_juge": [],
    }


def _ids(cible: Path) -> list[str]:
    return sorted(f.id for f in securite.analyser(cible).findings)


def test_l_id_survit_a_deux_passes(tmp_path, monkeypatch):
    """LE defaut : deux passes du MEME defaut sur le MEME fichier, deux identifiants."""
    cible = _produit(tmp_path / "produit")
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _sast_relatif)

    premiere = _ids(cible)
    seconde = _ids(cible)

    assert premiere, "montage inutile : la passe doit produire un constat"
    # ROUGE avant correctif : les deux listes different par le nom tire au sort du brouillon.
    assert premiere == seconde, (premiere, seconde)


def test_l_id_est_ancre_au_chemin_projet(tmp_path, monkeypatch):
    cible = _produit(tmp_path / "produit")
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _sast_relatif)

    identifiant = _ids(cible)[0]

    assert str(racine_execution(cible)) in identifiant, identifiant
    assert "requetes.py" in identifiant, identifiant


def test_l_id_ne_porte_plus_le_brouillon_de_la_passe(tmp_path, monkeypatch):
    """Le brouillon est detruit a la fin de l analyse : le citer, c est publier un chemin mort."""
    cible = _produit(tmp_path / "produit")
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _sast_relatif)

    sortie = securite.analyser(cible)

    for finding in sortie.findings:
        assert "forge-tests-securite-" not in finding.id, finding.id
        assert "forge-tests-securite-" not in finding.localisation, finding.localisation


def test_la_forme_absolue_reste_relocalisee(tmp_path, monkeypatch):
    """Non-regression : le chemin ABSOLU d `oracle-secrets` se ré-étiquetait deja, il continue."""
    cible = _produit(tmp_path / "produit")
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _sast_absolu)

    premiere = _ids(cible)
    seconde = _ids(cible)

    assert premiere == seconde, (premiere, seconde)
    assert str(racine_execution(cible)) in premiere[0], premiere
