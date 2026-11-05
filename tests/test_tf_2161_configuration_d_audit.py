"""TF-2161 — la configuration d'audit d'un produit ne vivait que dans la transcription.

Fait remonté (Produit-86, lot du 04/11/2026, RT-12). L'audit lancé le 04/11 sans
`FORGE_TESTS_APP`, `FORGE_TESTS_MUTATION` ni `FORGE_TESTS_QUALIF_URL` rend api 0/150 (« sonde API
muette »), back et qualif en SKIP, verdict PARTIEL, contre api 144/144 la veille avec ces
variables. Les variables avaient été posées à la main dans la session précédente : rien ne les
avait rangées chez le produit.

Deux demandes, deux sens chacune :

  1. un fichier de configuration d'audit VERSIONNÉ chez le produit,
     `forge/etapes/tests/audit.env`, lu d'office. Il ne porte aucun secret (il est versionné) :
     une clé de secret y est ÉCARTÉE et le dit. `.env.forge-tests` (non versionné) prime sur lui,
     et l'environnement de l'opérateur prime sur les deux ;
  2. un REFUS NOMMÉ quand l'application n'est désignée nulle part et que le produit est une
     fabrique : le pan `api` ne lance pas une mesure qui rendrait 0 %, il nomme la clé, la
     fabrique trouvée et l'endroit où ranger la valeur.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests import __main__ as cli
from forge_tests import application, authentification, execution
from forge_tests.adaptateurs import REGISTRE, api
from forge_tests.authentification import ENV_AUDIT, charger_env, cles_secretes_ignorees
from forge_tests.qualification import qualifier


@pytest.fixture(autouse=True)
def env_propre(monkeypatch, tmp_path):
    """`charger_env` écrit dans `os.environ` : sans restauration, un test verrait la config d'un
    autre. Le `.env` du dépôt forge-tests est remplacé par un fichier absent."""
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


def _produit_a_fabrique(racine: Path) -> Path:
    """Le cas du lot : une application FastAPI bâtie sur une fabrique, sans instance module."""
    _ecrire(racine, "backend/app/__init__.py", "")
    _ecrire(
        racine, "backend/app/main.py",
        "from fastapi import FastAPI\n\n\ndef creer_app():\n    return FastAPI()\n",
    )
    _ecrire(racine, "backend/tests/test_x.py", "def test_x():\n    assert True\n")
    return racine


def _produit_a_instance(racine: Path) -> Path:
    _ecrire(racine, "backend/app/__init__.py", "")
    _ecrire(racine, "backend/app/main.py", "from fastapi import FastAPI\n\napp = FastAPI()\n")
    _ecrire(racine, "backend/tests/test_x.py", "def test_x():\n    assert True\n")
    return racine


# --- 1. Le fichier de configuration d'audit du produit -----------------------------------------
class TestFichierDeConfigurationDAudit:
    def test_le_nom_du_fichier_est_celui_de_la_proposition(self) -> None:
        assert ENV_AUDIT == "forge/etapes/tests/audit.env"

    def test_rouge_les_cles_du_fichier_sont_lues_d_office(self, tmp_path: Path) -> None:
        """Avant : aucune des trois clés n'atteignait l'environnement du run."""
        projet = tmp_path / "produit"
        _ecrire(
            projet, ENV_AUDIT,
            "FORGE_TESTS_APP=app.main:creer_app\nFORGE_TESTS_MUTATION=1\n"
            "FORGE_TESTS_QUALIF_URL=https://qualif.exemple.test\n",
        )
        charger_env(projet)
        assert os.environ["FORGE_TESTS_APP"] == "app.main:creer_app"
        assert os.environ["FORGE_TESTS_MUTATION"] == "1"
        # Une clé qui DÉSIGNE une instance est admise ici : le fichier est celui du projet.
        assert os.environ["FORGE_TESTS_QUALIF_URL"] == "https://qualif.exemple.test"

    def test_l_environnement_de_l_operateur_prime_sur_le_fichier(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        projet = tmp_path / "produit"
        _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_APP=app.main:creer_app\n")
        monkeypatch.setenv("FORGE_TESTS_APP", "autre.module:app")
        charger_env(projet)
        assert os.environ["FORGE_TESTS_APP"] == "autre.module:app"

    def test_le_fichier_prive_prime_sur_le_fichier_versionne(self, tmp_path: Path) -> None:
        projet = tmp_path / "produit"
        _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_APP=app.main:creer_app\nFORGE_TESTS_MUTATION=1\n")
        _ecrire(projet, ".env.forge-tests", "FORGE_TESTS_APP=prive.module:app\n")
        charger_env(projet)
        assert os.environ["FORGE_TESTS_APP"] == "prive.module:app"
        # Ce que le fichier privé ne dit pas vient du fichier versionné.
        assert os.environ["FORGE_TESTS_MUTATION"] == "1"

    def test_un_secret_dans_le_fichier_versionne_est_ecarte_et_dit(self, tmp_path: Path) -> None:
        """Le fichier est versionné : y laisser un mot de passe le publierait (TF-0620)."""
        projet = tmp_path / "produit"
        _ecrire(
            projet, ENV_AUDIT,
            "FORGE_TESTS_APP=app.main:creer_app\nFORGE_TESTS_PASSWORD=pas-un-secret-reel\n"
            "FORGE_TESTS_QUALIF_BEARER=jeton-factice\nFORGE_TESTS_LOGIN=lecteur@exemple.test\n",
        )
        charger_env(projet)
        assert "FORGE_TESTS_PASSWORD" not in os.environ
        assert "FORGE_TESTS_QUALIF_BEARER" not in os.environ
        # Le reste du fichier est honoré : une clé écartée n'invalide pas le fichier.
        assert os.environ["FORGE_TESTS_APP"] == "app.main:creer_app"
        assert os.environ["FORGE_TESTS_LOGIN"] == "lecteur@exemple.test"
        assert cles_secretes_ignorees(projet) == [
            "FORGE_TESTS_PASSWORD", "FORGE_TESTS_QUALIF_BEARER"
        ]

    def test_sans_fichier_rien_n_est_ecarte_et_rien_ne_change(self, tmp_path: Path) -> None:
        projet = tmp_path / "produit"
        projet.mkdir()
        charger_env(projet)
        assert not [n for n in os.environ if n.startswith("FORGE_TESTS_")]
        assert cles_secretes_ignorees(projet) == []

    def test_l_audit_lit_le_fichier_d_office_et_le_dit_au_rapport(self, tmp_path: Path) -> None:
        """Le point d'application est l'entrée de l'audit, pas un pan qui y passerait par hasard :
        `FORGE_TESTS_MUTATION` n'était lue par aucun chargement de configuration."""
        projet = tmp_path / "produit"
        projet.mkdir()
        _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_MUTATION=1\nFORGE_TESTS_PASSWORD=x\n")
        rapport = cli.analyser(projet, ["workers"])
        assert os.environ["FORGE_TESTS_MUTATION"] == "1"
        lu = rapport["configuration_audit"]
        assert lu["fichiers_lus"] == [ENV_AUDIT]
        assert "FORGE_TESTS_MUTATION" in lu["cles_du_fichier"]
        assert lu["cles_secretes_ecartees"] == ["FORGE_TESTS_PASSWORD"]
        # Les VALEURS ne voyagent jamais au rapport.
        assert "x" not in str(lu["cles_du_fichier"])

    def test_sans_fichier_le_rapport_dit_qu_aucun_n_a_ete_lu(self, tmp_path: Path) -> None:
        projet = tmp_path / "produit"
        projet.mkdir()
        rapport = cli.analyser(projet, ["workers"])
        assert rapport["configuration_audit"]["fichiers_lus"] == []
        assert rapport["configuration_audit"]["fichier_attendu"] == ENV_AUDIT


# --- 2. Le refus nommé de l'application non désignée -------------------------------------------
class TestRefusApplicationNonDesignee:
    @pytest.fixture(autouse=True)
    def suite_jamais_lancee(self, monkeypatch):
        """Le refus est AVANT la mesure : lancer la suite pour rendre 0 % est ce que le retour a
        payé (48 minutes). Toute exécution lève."""
        def _interdit(*_args, **_kwargs):
            raise AssertionError("la suite du projet ne doit pas être lancée sur ce refus")

        monkeypatch.setattr(api, "exerces", _interdit)

    def test_rouge_une_fabrique_sans_designation_est_refusee_et_nommee(self, tmp_path: Path):
        projet = _produit_a_fabrique(tmp_path / "produit")
        sortie = api.analyser(projet)
        assert sortie.verdict == "SKIP"
        texte = " ".join(sortie.non_juge)
        assert "REFUS" in texte
        assert "FORGE_TESTS_APP" in texte
        assert "creer_app" in texte
        # Le remède porte la valeur à recopier ET l'endroit où la ranger.
        assert "FORGE_TESTS_APP=app.main:creer_app" in texte
        assert ENV_AUDIT in texte
        # Ce n'est pas un 0 % : aucune surface n'est publiée sur ce refus.
        assert sortie.surface is None
        assert sortie.findings == []

    def test_le_refus_est_un_manque_de_configuration_qui_nomme_le_champ(
        self, tmp_path: Path
    ) -> None:
        """Après qualification (point d'application unique de l'audit) : un manque de
        configuration à fournir, pas un échec du produit."""
        projet = _produit_a_fabrique(tmp_path / "produit")
        sortie = api.analyser(projet)
        qualifier([sortie], projet, REGISTRE)
        assert sortie.non_testables
        assert {tuple(n.champs_requis) for n in sortie.non_testables} == {("FORGE_TESTS_APP",)}
        assert {n.pan for n in sortie.non_testables} == {"api"}

    def test_la_designation_par_defaut_est_celle_de_la_sonde(self) -> None:
        """Le littéral est jugé sans importer la sonde (un greffon pytest) : on teste l'égalité."""
        from forge_tests.sondes import sonde_api

        defaut = ".".join(application.MODULE_PAR_DEFAUT) + ":" + application.INSTANCE_PAR_DEFAUT
        assert defaut == sonde_api.DESIGNATION_PAR_DEFAUT

    def test_vert_la_designation_dans_le_fichier_d_audit_leve_le_refus(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        projet = _produit_a_fabrique(tmp_path / "produit")
        _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_APP=app.main:creer_app\n")
        # Le refus levé, l'analyse poursuit et atteint la mesure : c'est elle qui lève ici.
        with pytest.raises(AssertionError, match="ne doit pas être lancée"):
            api.analyser(projet)

    def test_vert_la_designation_dans_l_environnement_leve_le_refus(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        projet = _produit_a_fabrique(tmp_path / "produit")
        monkeypatch.setenv("FORGE_TESTS_APP", "app.main:creer_app")
        with pytest.raises(AssertionError, match="ne doit pas être lancée"):
            api.analyser(projet)

    def test_vert_une_instance_module_n_est_pas_refusee(self, tmp_path: Path) -> None:
        """`app.main:app` est la désignation par défaut de la sonde : elle fonctionne, rien à
        refuser. Un refus ici accuserait un produit conforme."""
        projet = _produit_a_instance(tmp_path / "produit")
        with pytest.raises(AssertionError, match="ne doit pas être lancée"):
            api.analyser(projet)

    def test_le_remede_propose_est_joue_et_passe(self, tmp_path: Path) -> None:
        """Jouer le remède recommandé (TF-1013) : la valeur que le refus donne, rangée où il le
        dit, lève le refus."""
        projet = _produit_a_fabrique(tmp_path / "produit")
        refus = " ".join(api.analyser(projet).non_juge)
        valeur = refus.split("FORGE_TESTS_APP=", 1)[1].split()[0].strip("`.,;")
        _ecrire(projet, ENV_AUDIT, f"FORGE_TESTS_APP={valeur}\n")
        with pytest.raises(AssertionError, match="ne doit pas être lancée"):
            api.analyser(projet)

    def test_une_fabrique_a_racine_plate_est_refusee_aussi(self, tmp_path: Path) -> None:
        projet = tmp_path / "produit"
        _ecrire(projet, "app/__init__.py", "")
        _ecrire(
            projet, "app/main.py",
            "from fastapi import FastAPI\n\n\ndef create_app():\n    return FastAPI()\n",
        )
        _ecrire(projet, "tests/test_x.py", "def test_x():\n    assert True\n")
        texte = " ".join(api.analyser(projet).non_juge)
        assert "REFUS" in texte and "FORGE_TESTS_APP=app.main:create_app" in texte

    def test_une_fabrique_flask_n_est_pas_refusee(self, tmp_path: Path) -> None:
        """`create_app` existe aussi chez Flask : la sonde ASGI ne le greffe pas, nommer
        `FORGE_TESTS_APP` y serait une consigne sans issue."""
        projet = tmp_path / "produit"
        _ecrire(projet, "app/__init__.py", "")
        _ecrire(
            projet, "app/main.py",
            "from flask import Flask\n\n\ndef create_app():\n    return Flask(__name__)\n",
        )
        _ecrire(projet, "tests/test_x.py", "def test_x():\n    assert True\n")
        assert application.refus_designation(projet) is None

    def test_une_fabrique_asgi_a_nom_libre_est_refusee_et_nommee(self, tmp_path: Path) -> None:
        projet = tmp_path / "produit"
        _ecrire(projet, "app/__init__.py", "")
        _ecrire(
            projet, "app/main.py",
            "from fastapi import FastAPI\n\n\ndef monter_le_service():\n    return FastAPI()\n",
        )
        _ecrire(projet, "tests/test_x.py", "def test_x():\n    assert True\n")
        refus = application.refus_designation(projet)
        assert refus is not None and refus["fabrique"] == "app.main:monter_le_service"
        assert refus["fichier"] == "app/main.py:4"


# --- 3. La déclaration en ligne de commande ----------------------------------------------------
def test_la_cli_declare_sur_stderr_la_cle_de_secret_ecartee(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Même règle que TF-0243 : l'écart se dit avant la mesure, sur stderr (stdout reste JSON)."""
    projet = tmp_path / "produit"
    _ecrire(projet, ENV_AUDIT, "FORGE_TESTS_PASSWORD=pas-un-secret-reel\n")
    rapport = {
        "adaptateurs": [], "couverture_par_pan": {}, "mutation": {}, "seuils": {}, "modules": [],
        "pans_non_couverts": [], "pans_sans_objet": [], "motifs_non_couverture": {},
        "bandes_de_risque": {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0},
        "findings": [], "non_testables": [], "actions": [], "non_juge": [],
        "essais": {"cas": [], "totaux": {}, "signales": [], "fourni": False}, "verdict": "PASS",
    }
    monkeypatch.setattr(cli, "analyser", lambda c, pans=None: dict(rapport))
    monkeypatch.setattr("forge_tests.declarations.appliquer", lambda r, c: None)
    assert cli.main([str(projet), "--json"]) == 0
    sortie = capsys.readouterr()
    assert "[TF-2161] FORGE_TESTS_PASSWORD" in sortie.err
    assert "pas-un-secret-reel" not in sortie.err + sortie.out
