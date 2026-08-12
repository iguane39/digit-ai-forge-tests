"""Suite de la découverte des sources du projet audité.

Ce que ces tests protègent : un projet qui ne nomme pas son paquet `app` doit être MESURÉ,
et un projet ambigu doit être DÉCLARÉ tel — jamais deviné.
"""

import pytest

from forge_tests.disposition import (
    motif_indetermine,
    nom_paquet_sources,
    paquet_sources,
)


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    """Aucun test ne doit dépendre de la variable posée par la machine qui le joue."""
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _projet(racine, paquets=(), autres=()):
    for nom in paquets:
        dossier = racine / "backend" / nom
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "module.py").write_text("VALEUR = 1\n", encoding="utf-8")
    for nom in autres:
        dossier = racine / "backend" / nom
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "note.txt").write_text("pas du python\n", encoding="utf-8")
    return racine


class TestConventions:
    def test_app_reste_la_convention_premiere(self, tmp_path):
        _projet(tmp_path, paquets=("app",))
        assert paquet_sources(tmp_path) == tmp_path / "backend" / "app"
        assert nom_paquet_sources(tmp_path) == "app"

    def test_src_est_reconnu(self, tmp_path):
        _projet(tmp_path, paquets=("src",))
        assert nom_paquet_sources(tmp_path) == "src"

    def test_app_l_emporte_sur_src_quand_les_deux_existent(self, tmp_path):
        _projet(tmp_path, paquets=("app", "src"))
        assert nom_paquet_sources(tmp_path) == "app"


class TestDecouverte:
    def test_un_paquet_hors_convention_est_trouve_s_il_est_seul(self, tmp_path):
        _projet(tmp_path, paquets=("coeur_metier",))
        assert nom_paquet_sources(tmp_path) == "coeur_metier"

    def test_les_dossiers_hors_sources_ne_comptent_pas(self, tmp_path):
        _projet(tmp_path, paquets=("coeur_metier", "tests", ".venv", "migrations"))
        assert nom_paquet_sources(tmp_path) == "coeur_metier"

    def test_un_dossier_sans_python_ne_compte_pas(self, tmp_path):
        _projet(tmp_path, paquets=("coeur_metier",), autres=("assets",))
        assert nom_paquet_sources(tmp_path) == "coeur_metier"

    def test_un_paquet_en_sous_arborescence_est_vu(self, tmp_path):
        racine = tmp_path / "backend" / "produit" / "domaine"
        racine.mkdir(parents=True)
        (racine / "regle.py").write_text("X = 1\n", encoding="utf-8")
        assert nom_paquet_sources(tmp_path) == "produit"


class TestAmbiguiteEtAbsence:
    def test_deux_paquets_possibles_ne_se_devinent_pas(self, tmp_path):
        _projet(tmp_path, paquets=("coeur", "outillage"))
        assert paquet_sources(tmp_path) is None

    def test_le_motif_nomme_les_candidats(self, tmp_path):
        _projet(tmp_path, paquets=("coeur", "outillage"))
        motif = motif_indetermine(tmp_path)
        assert "coeur" in motif and "outillage" in motif
        assert "FORGE_TESTS_SOURCES" in motif

    def test_aucun_paquet(self, tmp_path):
        (tmp_path / "backend").mkdir()
        assert paquet_sources(tmp_path) is None
        assert "aucun paquet Python" in motif_indetermine(tmp_path)

    def test_aucun_backend(self, tmp_path):
        assert paquet_sources(tmp_path) is None
        assert "aucun dossier `backend`" in motif_indetermine(tmp_path)


class TestDeclarationExplicite:
    def test_la_declaration_tranche_l_ambiguite(self, tmp_path, monkeypatch):
        _projet(tmp_path, paquets=("coeur", "outillage"))
        monkeypatch.setenv("FORGE_TESTS_SOURCES", "outillage")
        assert nom_paquet_sources(tmp_path) == "outillage"

    def test_la_declaration_l_emporte_sur_la_convention(self, tmp_path, monkeypatch):
        _projet(tmp_path, paquets=("app", "maison"))
        monkeypatch.setenv("FORGE_TESTS_SOURCES", "maison")
        assert nom_paquet_sources(tmp_path) == "maison"

    def test_un_chemin_absolu_est_accepte(self, tmp_path, monkeypatch):
        _projet(tmp_path, paquets=("maison",))
        monkeypatch.setenv("FORGE_TESTS_SOURCES", str(tmp_path / "backend" / "maison"))
        assert nom_paquet_sources(tmp_path) == "maison"

    def test_une_declaration_fausse_est_un_refus_pas_un_repli(self, tmp_path, monkeypatch):
        # Silencieusement retomber sur `app` ferait mesurer AUTRE CHOSE que ce qui est
        # demande — la mesure porterait un nom faux.
        _projet(tmp_path, paquets=("app",))
        monkeypatch.setenv("FORGE_TESTS_SOURCES", "inexistant")
        assert paquet_sources(tmp_path) is None
        assert "inexistant" in motif_indetermine(tmp_path)
