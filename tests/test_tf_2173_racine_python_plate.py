"""TF-2173 — un outil Python autonome hors de `backend/` ne pouvait recevoir aucun verdict.

Fait remonté (Produit-86, RP-13, 03/11/2026). `outils/compteur-foundry` : des modules `.py` et un
`tests/` côte à côte, sans paquet `app` ni `src`, sans `.venv`. Le pan back (mutation) sortait en
SKIP « sources du projet non localisables » malgré 11 tests verts, `couverture_par_pan` restait
vide et le verdict PARTIEL (rapport du 03/11 : code 3, 0 pan couvert sur 2 demandés).

Deux demandes, deux sens chacune :

  1. une RACINE PYTHON PLATE est acceptée : les modules posés à la racine sont la source, la suite
     est celle de `tests/`, la couverture se mesure sur la racine sans lire l'environnement ni les
     artefacts. `paquet_sources` ne change pas (les pans qui le parcourent récursivement liraient
     `.venv/` si on lui rendait la racine) ;
  2. l'INTERPRÈTE se désigne par `--python` (ou `FORGE_TESTS_PYTHON`), et une désignation
     introuvable n'est jamais remplacée en silence par un autre interpréteur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from forge_tests import __main__ as cli
from forge_tests import authentification, disposition, execution
from forge_tests.adaptateurs import mutation
from forge_tests.authentification import ENV_AUDIT, charger_env

RACINE = Path(__file__).resolve().parent.parent
VENV_DU_BANC = RACINE / "fixtures" / "banc-vert" / "backend" / ".venv" / "Scripts" / "python.exe"


@pytest.fixture(autouse=True)
def env_propre(monkeypatch, tmp_path):
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    monkeypatch.setattr(authentification, "ENV_DEPOT", tmp_path / "depot-absent" / ".env")
    execution.mesurer.cache_clear()
    yield
    os.environ.clear()
    os.environ.update(memoire)
    execution.mesurer.cache_clear()


def _ecrire(racine: Path, relatif: str, texte: str) -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


COMPTEUR = (
    "def compter(valeurs):\n"
    "    total = 0\n"
    "    for v in valeurs:\n"
    "        total += v\n"
    "    return total\n"
)
TEST_COMPTEUR = (
    "from compteur import compter\n\n\n"
    "def test_compter():\n"
    "    assert compter([1, 2]) == 3\n"
)


def _outil_plat(racine: Path) -> Path:
    """Le cas du lot : modules à la racine, `tests/` voisin, ni paquet ni `.venv`."""
    _ecrire(racine, "compteur.py", COMPTEUR)
    _ecrire(racine, "rapport.py", "def titre():\n    return 'rapport'\n")
    _ecrire(racine, "tests/test_compteur.py", TEST_COMPTEUR)
    return racine


class _Faux:
    def __init__(self, code: int = 0, sortie: str = "") -> None:
        self.returncode, self.stdout, self.stderr = code, sortie, ""


# --- 1. La racine plate ---------------------------------------------------------------------------
class TestRacinePlate:
    def test_rouge_l_outil_plat_est_reconnu(self, tmp_path: Path) -> None:
        """Avant : `paquet_sources` rendait None et rien d'autre ne reconnaissait la racine."""
        cible = _outil_plat(tmp_path / "outil")
        assert disposition.racine_plate(cible) == cible

    def test_les_modules_plats_sont_ceux_du_produit_ni_tests_ni_amorcage(
        self, tmp_path: Path
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        _ecrire(cible, "conftest.py", "")
        _ecrire(cible, "setup.py", "")
        _ecrire(cible, "test_a_la_racine.py", "def test_x():\n    assert True\n")
        _ecrire(cible, "calcul_test.py", "def test_y():\n    assert True\n")
        assert [m.name for m in disposition.modules_plats(cible)] == ["compteur.py", "rapport.py"]

    def test_paquet_sources_ne_change_pas(self, tmp_path: Path) -> None:
        """Garde de portée : les pans qui parcourent « le paquet » en rglob liraient `.venv/`."""
        cible = _outil_plat(tmp_path / "outil")
        assert disposition.paquet_sources(cible) is None

    @pytest.mark.parametrize(
        "cas",
        ["paquet_app", "aucun_module", "aucun_test", "deux_dossiers", "sources_declarees"],
    )
    def test_ce_qui_n_est_pas_un_outil_plat_n_est_pas_reconnu(
        self, tmp_path: Path, monkeypatch, cas: str
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        if cas == "paquet_app":
            _ecrire(cible, "app/__init__.py", "")
        elif cas == "aucun_module":
            (cible / "compteur.py").unlink()
            (cible / "rapport.py").unlink()
        elif cas == "aucun_test":
            (cible / "tests" / "test_compteur.py").unlink()
        elif cas == "deux_dossiers":
            _ecrire(cible, "alpha/a.py", "X = 1\n")
            _ecrire(cible, "beta/b.py", "Y = 2\n")
        else:
            monkeypatch.setenv("FORGE_TESTS_SOURCES", str(tmp_path / "ailleurs"))
        assert disposition.racine_plate(cible) is None

    def test_les_dossiers_d_outillage_n_empechent_pas_la_racine_plate(self, tmp_path: Path) -> None:
        """`.venv`, `forge/`, `scripts/`, `docs/` ne sont jamais le paquet du produit."""
        cible = _outil_plat(tmp_path / "outil")
        _ecrire(cible, ".venv/Lib/site-packages/tiers/__init__.py", "")
        _ecrire(cible, "forge/etapes/x.py", "")
        _ecrire(cible, "scripts/aide.py", "")
        _ecrire(cible, "docs/conf.py", "")
        assert disposition.racine_plate(cible) == cible

    def test_la_couverture_se_mesure_sur_la_racine_sans_l_environnement(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        faux_python = _ecrire(tmp_path, "interp/python.exe", "")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(faux_python))
        commandes: list[tuple[list[str], Path | None]] = []

        def _run(commande, *, banc, domaine, quoi, **kwargs):
            commandes.append((list(commande), kwargs.get("cwd")))
            return _Faux(0, '{"files": {}}' if quoi == "rapport coverage" else "")

        monkeypatch.setattr(execution, "_run", _run)
        # ROUGE avant : « sources du projet non localisables » et aucune commande de suite.
        assert execution.mesurer(str(cible)) is not None
        suite = next(c for c, _ in commandes if "run" in c)
        assert "--source=." in suite
        omission = next(a for a in suite if a.startswith("--omit="))
        assert ".venv/*" in omission and "node_modules/*" in omission
        assert "tests/*" not in omission, "la suite reste mesurée, comme avec un paquet"
        assert all(cwd == cible for c, cwd in commandes if "run" in c)

    def test_avec_un_paquet_la_commande_de_couverture_ne_change_pas(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        _ecrire(cible, "app/__init__.py", "")
        _ecrire(cible, "app/main.py", "X = 1\n")
        faux_python = _ecrire(tmp_path, "interp/python.exe", "")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(faux_python))
        commandes: list[list[str]] = []

        def _run(commande, *, banc, domaine, quoi, **kwargs):
            commandes.append(list(commande))
            return _Faux(0, '{"files": {}}' if quoi == "rapport coverage" else "")

        monkeypatch.setattr(execution, "_run", _run)
        assert execution.mesurer(str(cible)) is not None
        suite = next(c for c in commandes if "run" in c)
        assert "--source=app,tests" in suite
        assert not [a for a in suite if a.startswith("--omit=")]


# --- 2. Le pan back sur la racine plate ----------------------------------------------------------
class TestPanBack:
    def test_la_decouverte_ne_lit_que_les_modules_de_la_racine_et_nomme_ce_qu_elle_ecarte(
        self, tmp_path: Path
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        _ecrire(cible, "conftest.py", "import pytest\n")
        _ecrire(cible, "test_a_la_racine.py", "def test_x():\n    assert True\n")
        _ecrire(cible, "scripts/aide.py", "def aide():\n    return 1 + 1\n")
        retenus, exclus = mutation.decouvrir(cible, cible)
        assert [m.name for m in retenus] == ["compteur.py", "rapport.py"]
        ecartes = {e["module"]: e["motif"] for e in exclus}
        assert set(ecartes) == {"conftest.py", "test_a_la_racine.py"}
        assert all("hors sources" in motif for motif in ecartes.values())

    def test_rouge_le_pan_ne_sort_plus_en_sources_non_localisables(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setattr(mutation, "resume_fichiers", lambda c: None)
        sortie = mutation.analyser(cible)
        texte = " ".join(sortie.non_juge)
        assert "non localisables" not in texte
        assert "RACINE PLATE" in texte and "compteur.py" in texte
        # Non demandé : la campagne est à la demande (D-34), et les modules sont inventoriés.
        assert "NON JOUE" in texte
        assert [m["module"] for m in sortie.modules] == ["compteur.py", "rapport.py"]

    def test_un_interpreteur_designe_introuvable_est_dit_pas_remplace(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setattr(mutation, "resume_fichiers", lambda c: None)
        monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(tmp_path / "absent" / "python.exe"))
        sortie = mutation.analyser(cible)
        assert sortie.verdict == "SKIP"
        texte = " ".join(sortie.non_juge)
        assert "FORGE_TESTS_PYTHON" in texte and "ne désigne aucun fichier" in texte

    def test_sans_interpreteur_le_motif_nomme_l_option(self, tmp_path: Path, monkeypatch) -> None:
        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setattr(mutation, "resume_fichiers", lambda c: None)
        monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
        texte = " ".join(mutation.analyser(cible).non_juge)
        assert "--python" in texte


# --- 3. L'interpréteur désigné -------------------------------------------------------------------
class TestInterpreteurDesigne:
    def test_rien_de_designe_laisse_la_decouverte_des_venv(self, tmp_path: Path) -> None:
        assert execution.python_designe(tmp_path) == (None, None)

    def test_un_interpreteur_designe_est_utilise(self, tmp_path: Path, monkeypatch) -> None:
        faux = _ecrire(tmp_path, "interp/python.exe", "")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(faux))
        assert execution.python_designe(tmp_path) == (faux, None)
        assert execution._python(tmp_path) == faux

    def test_la_designation_prime_sur_le_venv_du_projet(self, tmp_path: Path, monkeypatch) -> None:
        cible = tmp_path / "produit"
        venv = _ecrire(cible, ".venv/Scripts/python.exe", "")
        faux = _ecrire(tmp_path, "interp/python.exe", "")
        assert execution._python(cible) == venv
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(faux))
        assert execution._python(cible) == faux

    def test_un_chemin_relatif_se_lit_depuis_la_racine_auditee(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = tmp_path / "produit"
        voulu = _ecrire(cible, "outillage/python.exe", "")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", "outillage/python.exe")
        assert execution.python_designe(cible) == (voulu, None)

    def test_une_designation_introuvable_n_est_jamais_remplacee(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = tmp_path / "produit"
        _ecrire(cible, ".venv/Scripts/python.exe", "")  # un venv existe : il ne doit pas servir
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(tmp_path / "absent.exe"))
        chemin, motif = execution.python_designe(cible)
        assert chemin is None and "ne désigne aucun fichier" in (motif or "")
        assert execution._python(cible) is None

    def test_la_mesure_nomme_la_designation_cassee_et_non_l_absence_de_venv(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(tmp_path / "absent.exe"))
        assert execution.mesurer(str(cible)) is None
        motif = execution.motif_indisponibilite(cible, "backend", "")
        assert "FORGE_TESTS_PYTHON" in motif and "ne désigne aucun fichier" in motif

    def test_sans_designation_ni_venv_le_motif_propose_l_option(self, tmp_path: Path) -> None:
        cible = _outil_plat(tmp_path / "outil")
        assert execution.mesurer(str(cible)) is None
        assert "--python" in execution.motif_indisponibilite(cible, "backend", "")

    def test_la_cle_se_range_dans_le_fichier_d_audit_du_produit(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        faux = _ecrire(tmp_path, "interp/python.exe", "")
        _ecrire(cible, ENV_AUDIT, f"FORGE_TESTS_PYTHON={faux}\n")
        charger_env(cible)
        assert execution.python_designe(cible) == (faux, None)


def test_le_gabarit_depose_chez_le_projet_nomme_la_cle_et_le_fichier_d_audit() -> None:
    """Une affordance est câblée ou n'existe pas : la clé est dérivée du code, le fichier dit."""
    from forge_tests import gabarit_env

    contenu = gabarit_env.rendre(gabarit_env.cles_connues())
    assert "FORGE_TESTS_PYTHON=" in contenu
    assert "interpréteur qui lance la suite" in contenu
    assert ENV_AUDIT in contenu


# --- 4. L'option de ligne de commande ------------------------------------------------------------
class TestOptionPython:
    @pytest.fixture
    def projet(self, tmp_path: Path, monkeypatch) -> Path:
        cible = _outil_plat(tmp_path / "outil")
        rapport = {
            "adaptateurs": [], "couverture_par_pan": {}, "mutation": {}, "seuils": {},
            "modules": [], "pans_non_couverts": [], "pans_sans_objet": [],
            "motifs_non_couverture": {},
            "bandes_de_risque": {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0},
            "findings": [], "non_testables": [], "actions": [], "non_juge": [],
            "essais": {"cas": [], "totaux": {}, "signales": [], "fourni": False},
            "verdict": "PASS",
        }
        monkeypatch.setattr(cli, "analyser", lambda c, pans=None: dict(rapport))
        monkeypatch.setattr("forge_tests.declarations.appliquer", lambda r, c: None)
        return cible

    def test_rouge_l_option_existe_et_designe_l_interpreteur(
        self, projet: Path, tmp_path: Path
    ) -> None:
        faux = _ecrire(tmp_path, "interp/python.exe", "")
        assert cli.main([str(projet), "--json", "--python", str(faux)]) == 0
        assert os.environ["FORGE_TESTS_PYTHON"] == str(faux.resolve())

    def test_l_option_prime_sur_les_fichiers_du_projet(self, projet: Path, tmp_path: Path) -> None:
        faux = _ecrire(tmp_path, "interp/python.exe", "")
        _ecrire(projet, ".env.forge-tests", "FORGE_TESTS_PYTHON=ailleurs/python.exe\n")
        _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_PYTHON=encore-ailleurs/python.exe\n")
        assert cli.main([str(projet), "--json", "--python", str(faux)]) == 0
        charger_env(projet)
        assert execution.python_designe(projet) == (faux.resolve(), None)

    def test_un_interpreteur_introuvable_est_refuse_a_l_entree(
        self, projet: Path, tmp_path: Path, capsys
    ) -> None:
        with pytest.raises(SystemExit) as sortie:
            cli.main([str(projet), "--json", "--python", str(tmp_path / "absent.exe")])
        assert sortie.value.code == 2
        assert "--python" in capsys.readouterr().err
        assert "FORGE_TESTS_PYTHON" not in os.environ

    def test_l_aide_documente_l_option(self, capsys) -> None:
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        assert "--python" in capsys.readouterr().out


# --- 5. Une mesure RÉELLE, sans doublure ---------------------------------------------------------
@pytest.mark.skipif(
    not VENV_DU_BANC.is_file(),
    reason=f"interpréteur portant coverage et pytest absent ({VENV_DU_BANC}) : le banc vert n'a "
    "pas son environnement sur ce poste ; les cas ci-dessus couvrent la commande, pas la mesure",
)
class TestMesureReelle:
    def test_la_suite_d_un_outil_plat_est_mesuree_et_les_modules_sont_inventories(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(VENV_DU_BANC))
        monkeypatch.setattr(sys, "argv", ["forge-tests"])
        mesure = execution.mesurer(str(cible))
        assert mesure is not None, execution.motif_indisponibilite(cible, "backend", "")
        resume = mesure["resume_fichiers"]
        assert resume["compteur.py"]["lignes_couvertes"] > 0
        # Un module que la suite n'importe jamais figure à 0 % : il est dans la mesure, pas absent.
        assert resume["rapport.py"]["lignes_couvertes"] == 0
        assert "tests/test_compteur.py" in resume
        assert not [chemin for chemin in resume if ".venv" in chemin]

    def test_la_campagne_de_mutation_tourne_sur_l_outil_plat(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(VENV_DU_BANC))
        monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
        sortie = mutation.analyser(cible)
        assert sortie.verdict != "SKIP", " ".join(sortie.non_juge)
        assert sortie.mutation and sortie.mutation["mutants_viables"] > 0
        modules = {m["module"]: m for m in sortie.modules}
        assert modules["compteur.py"]["exerce"] is True
        assert modules["compteur.py"]["mute"] is True


# --- 6. La surface de l'outil plat : sans elle, sa campagne était refusée au rapport -------------
class TestSurfaceDeLOutilPlat:
    """Constaté en rejouant le cas du lot par la ligne de commande : une campagne de mutation jouée
    sur un outil plat sortait en `REFUSE` (« score de mutation présent sans aucune couverture de
    surface »). Un outil sans route ni formulaire n'a aucun autre pan qui publie une surface ; les
    modules sources exercés par la suite sont la seule qu'il ait."""

    def test_la_surface_compte_les_modules_exerces_et_ecarte_les_exclus(self) -> None:
        inventaire = [
            {"module": "a.py", "categorie": "metier", "exclu": None, "exerce": True},
            {"module": "b.py", "categorie": "metier", "exclu": None, "exerce": False},
            {"module": "conftest.py", "categorie": "exclu", "exclu": "hors sources",
             "exerce": None},
        ]
        surface = mutation._surface_modules(inventaire)
        assert surface["inventorie"] == 2 and surface["exerce"] == 1 and surface["ratio"] == 0.5
        assert surface["elements_exerces"] == ["module:a.py"]
        assert surface["elements_non_exerces"] == ["module:b.py"]
        assert surface["seuil"] == 1.0

    def test_sans_module_a_juger_il_n_y_a_pas_de_surface(self) -> None:
        assert mutation._surface_modules([]) is None

    def test_la_surface_est_declaree_au_registre_des_seuils(self) -> None:
        from forge_tests import seuils

        assert seuils.valeur("couverture_surface_modules") == 1.0
        assert seuils.severite("couverture_surface_modules") == "bloquant"
        assert "couverture_surface_modules" in seuils.au_rapport()

    @pytest.mark.skipif(
        not VENV_DU_BANC.is_file(),
        reason=f"interpréteur portant coverage et pytest absent ({VENV_DU_BANC})",
    )
    def test_rouge_la_campagne_jouee_sur_un_outil_plat_passe_la_regle_conjointe(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from forge_tests.adaptateurs import PANS_ATTENDUS
        from forge_tests.noyau import rapport

        cible = _outil_plat(tmp_path / "outil")
        monkeypatch.setenv("FORGE_TESTS_PYTHON", str(VENV_DU_BANC))
        monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
        sortie = mutation.analyser(cible)
        assert sortie.mutation, " ".join(sortie.non_juge)
        assert sortie.surface is not None
        assert sortie.surface["elements_exerces"] == ["module:compteur.py"]
        assert sortie.surface["elements_non_exerces"] == ["module:rapport.py"]
        # Avant : RapportRefuse — le score de mutation n'avait aucune surface à côté de lui.
        publie = rapport([sortie], PANS_ATTENDUS)
        assert publie["couverture_par_pan"]["back"]["ratio"] == 0.5
        assert publie["mutation"]["back"]["mutants_viables"] > 0

    def test_une_suite_avec_paquet_ne_publie_pas_de_surface_de_modules(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Garde de portée : ce complément ne change rien pour un projet à paquet."""
        cible = _outil_plat(tmp_path / "outil")
        _ecrire(cible, "app/__init__.py", "")
        _ecrire(cible, "app/service.py", "def f(a, b):\n    return a + b\n")
        monkeypatch.setattr(mutation, "resume_fichiers", lambda c: None)
        assert mutation.analyser(cible).surface is None
