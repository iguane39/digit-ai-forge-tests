"""TF-0219 (RT-5, lot COMPTA 20260814a) — motif trompeur du pan `securite`.

Fait mesure : `analyser()` testait `racine is None OR not backend\\` et publiait dans les DEUX
cas « registre d oracles introuvable : definir FORGE_TESTS_ORACLES ». Sur le produit du lot, le
registre ETAIT resolu (chemin par defaut existant ET variable declaree) ; la cause reelle etait
l absence de `backend\\`. Cout mesure : un aller-retour de configuration inutile entre les
cycles 1 et 2 (ledger seq 17) — l operateur est parti regler une variable qui allait bien.

Deux causes, deux motifs. Le `POUR_COUVRIR` du pan disait deja la bonne cause (« fournir des
sources Python lisibles ») ; le motif s aligne dessus.

Rappel de contrat (`forge_tests.noyau.rapport`) : le motif publie au rapport pour un pan SKIP
est le DERNIER `non_juge` de la sortie. C est lui que ces tests inspectent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _registre(racine: Path) -> Path:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "oracle-secrets.mjs").write_text("", encoding="utf-8")
    return racine


def _sources(racine: Path) -> Path:
    (racine / "backend" / "app").mkdir(parents=True)
    (racine / "backend" / "app" / "main.py").write_text("X = 1\n", encoding="utf-8")
    return racine


def _motif(sortie) -> str:
    """Le motif que le rapport publiera pour ce pan — le DERNIER non_juge."""
    return sortie.non_juge[-1]


class TestRegistreAbsent:
    """Cause 1 : le registre d oracles est reellement introuvable."""

    def test_le_motif_nomme_la_variable_a_definir(self, tmp_path, monkeypatch):
        cible = _sources(tmp_path)
        monkeypatch.setattr(securite, "_racine_oracles", lambda: None)

        sortie = securite.analyser(cible)

        assert sortie.verdict == "SKIP"
        assert "FORGE_TESTS_ORACLES" in _motif(sortie)


class TestSourcesAbsentes:
    """Cause 2 : le registre va bien, il n y a rien a lire. C est le cas du lot COMPTA."""

    def test_le_motif_ne_parle_plus_du_registre(self, tmp_path, monkeypatch):
        """LE defaut de RT-5 : ce motif envoyait regler une variable qui allait bien."""
        oracles = _registre(tmp_path / "oracles")
        cible = tmp_path / "produit"
        cible.mkdir()
        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)

        sortie = securite.analyser(cible)

        assert sortie.verdict == "SKIP"
        motif = _motif(sortie)
        # ROUGE implicite : le motif valait « registre d oracles introuvable : definir
        # FORGE_TESTS_ORACLES » alors que le registre etait resolu — un aller-retour perdu.
        assert "introuvable : definir FORGE_TESTS_ORACLES" not in motif

    def test_le_motif_dit_la_vraie_cause(self, tmp_path, monkeypatch):
        oracles = _registre(tmp_path / "oracles")
        cible = tmp_path / "produit"
        cible.mkdir()
        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)

        motif = _motif(securite.analyser(cible))

        assert "aucune source a lire" in motif
        # Et il dit explicitement que l AUTRE cause est ecartee : sans cela, le lecteur qui
        # connait l ancien message reste tente d aller verifier sa variable.
        assert str(oracles) in motif

    def test_le_motif_nomme_la_racine_cherchee(self, tmp_path, monkeypatch):
        """Complement TF-0216 : dire « rien a lire » sans dire OU l on a cherche relance
        exactement la meme perte de temps, d un cran plus loin."""
        oracles = _registre(tmp_path / "oracles")
        cible = tmp_path / "produit"
        cible.mkdir()
        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)

        motif = _motif(securite.analyser(cible))

        assert "racine d execution retenue" in motif
        assert "candidats essayes dans l ordre" in motif

    def test_le_motif_s_aligne_sur_le_pour_couvrir_du_pan(self):
        """RT-5 : « le POUR_COUVRIR, lui, dit deja la bonne cause »."""
        assert "sources" in securite.POUR_COUVRIR
        assert "code à lire" in securite.POUR_COUVRIR


class TestLesDeuxCausesNeSeConfondentPas:
    def test_les_deux_motifs_sont_distincts(self, tmp_path, monkeypatch):
        oracles = _registre(tmp_path / "oracles")

        avec_sources = _sources(tmp_path / "a")
        monkeypatch.setattr(securite, "_racine_oracles", lambda: None)
        motif_registre = _motif(securite.analyser(avec_sources))

        sans_sources = tmp_path / "b"
        sans_sources.mkdir()
        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)
        motif_sources = _motif(securite.analyser(sans_sources))

        # ROUGE implicite : les deux chaines etaient IDENTIQUES — un motif unique pour deux
        # causes qui n appellent pas le meme travail.
        assert motif_registre != motif_sources
