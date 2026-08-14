"""TF-0216 (RT-2, lot COMPTA 20260814a) — l ancre `backend\\` etait en dur.

Fait mesure : produit FastAPI + Jinja2 a RACINE PLATE (`app\\`, `tests\\`, `.venv\\` a la
racine, SANS dossier `backend\\`) — disposition tres repandue. `disposition.py` ancrait la
decouverte du paquet sur `<cible>\\backend`, `execution.py` lancait la suite avec
`cwd=<cible>\\backend`, `securite.py:131` testait `(cible/'backend').is_dir()`. Resultat :
SEPT pans non mesurables (api, data, migrations, batch, fichiers, back, securite) alors que la
suite pytest etait VERTE a 74 tests et l app factory standard. TF-0097 (12/08) n avait resolu
que le NOM du paquet, pas son ANCRE.

Ce que ces tests protegent — dans l ordre du garde-fou de methode du mandat :

  1. le cas REEL du produit est mesurable (racine plate reconnue, paquet trouve, suite lancee
     depuis la bonne racine, pan securite ancre au bon endroit) ;
  2. la disposition historique `backend\\` reste PRIORITAIRE — aucun projet deja mesure ne
     change de racine du fait de ce correctif ;
  3. la decouverte est DETERMINISTE (ordre fixe, aucun score, aucun parcours de disque
     departageant) et se DECLARE (« racine d execution retenue : … »), sans quoi un choix
     implicite qui change d un projet a l autre serait pire que l ancre en dur.

ROUGE implicite : avant le correctif, chacun des tests de la classe `TestCasReelDuProduit`
echouait — `paquet_sources` rendait None, `racine_execution` n existait pas, et le `cwd` de la
suite pointait un dossier inexistant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import execution
from forge_tests.adaptateurs import securite
from forge_tests.disposition import (
    motif_indetermine,
    motif_racine_execution,
    nom_paquet_sources,
    paquet_sources,
    racine_execution,
)


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    """Aucun test ne doit dependre de la variable posee par la machine qui le joue."""
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    execution.mesurer.cache_clear()
    yield
    execution.mesurer.cache_clear()


def _racine_plate(racine: Path) -> Path:
    """La disposition EXACTE du produit du lot COMPTA : `app\\` + `tests\\` + `.venv\\`, sans
    `backend\\`. FastAPI + Jinja2, suite pytest verte, app factory standard."""
    (racine / "app").mkdir(parents=True)
    (racine / "app" / "__init__.py").write_text("", encoding="utf-8")
    (racine / "app" / "main.py").write_text(
        "def creer_app():\n    return object()\n", encoding="utf-8"
    )
    (racine / "app" / "templates").mkdir()
    (racine / "app" / "templates" / "facture.html").write_text(
        "<form action='/ventiler'><button type='submit'>Ventiler</button></form>\n",
        encoding="utf-8",
    )
    (racine / "tests").mkdir()
    (racine / "tests" / "test_ventilation.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (racine / "pyproject.toml").write_text("[project]\nname = 'compta'\n", encoding="utf-8")
    for relatif in (".venv/Scripts/python.exe", ".venv/bin/python"):
        chemin = racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("", encoding="utf-8")
    return racine


def _disposition_backend(racine: Path) -> Path:
    """La disposition historique, celle de `fixtures/banc-vert` : tout sous `backend\\`."""
    socle = racine / "backend"
    (socle / "app").mkdir(parents=True)
    (socle / "app" / "main.py").write_text("VALEUR = 1\n", encoding="utf-8")
    (socle / "tests").mkdir()
    (socle / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (socle / ".venv" / "Scripts").mkdir(parents=True)
    (socle / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    return racine


class TestCasReelDuProduit:
    """Le cas COMPTA : racine plate, sept pans qui doivent redevenir mesurables."""

    def test_la_racine_plate_est_reconnue_comme_racine_d_execution(self, tmp_path):
        cible = _racine_plate(tmp_path)
        # ROUGE implicite : `<cible>/backend` etait la seule ancre — un dossier ici INEXISTANT.
        assert racine_execution(cible) == cible

    def test_le_paquet_est_trouve_a_la_racine_plate(self, tmp_path):
        cible = _racine_plate(tmp_path)
        assert paquet_sources(cible) == cible / "app"
        # C est le nom que `coverage run --source=` recoit : sans lui, couverture vide et
        # « la suite n exerce rien » sur une suite verte a 74 tests.
        assert nom_paquet_sources(cible) == "app"

    def test_l_environnement_python_de_la_racine_plate_est_trouve(self, tmp_path):
        cible = _racine_plate(tmp_path)
        python = execution._python(cible)
        assert python is not None
        assert python.parent.parent == cible / ".venv"

    def test_la_suite_est_lancee_depuis_la_racine_plate(self, tmp_path, monkeypatch):
        """Le `cwd` de la suite — le coeur de RT-2, et ce qui emportait les sept pans."""
        cible = _racine_plate(tmp_path)
        cwd_vus: list[Path] = []

        class _Faux:
            def __init__(self, code=0, sortie=""):
                self.returncode, self.stdout, self.stderr = code, sortie, ""

        def _run_espion(commande, *, banc, domaine, quoi, **kwargs):
            if "cwd" in kwargs:
                cwd_vus.append(Path(kwargs["cwd"]))
            if quoi == "rapport coverage":
                return _Faux(0, '{"files": {}}')
            return _Faux(0)

        monkeypatch.setattr(execution, "_run", _run_espion)
        mesure = execution.mesurer(str(cible))

        # ROUGE implicite : `cwd=<cible>/backend` — un dossier inexistant ici, donc un
        # `NotADirectoryError` puis un pan non mesure, sept fois de suite.
        assert mesure is not None, "la mesure doit aboutir sur une racine plate"
        assert cwd_vus, "la suite doit avoir ete lancee"
        assert all(cwd == cible for cwd in cwd_vus), f"cwd retenus : {cwd_vus}"

    def test_le_pan_securite_lit_les_sources_de_la_racine_plate(self, tmp_path, monkeypatch):
        """`securite.py:131` testait `(cible/'backend').is_dir()` — SKIP sur racine plate."""
        cible = _racine_plate(tmp_path)
        oracles = tmp_path / "oracles"
        oracles.mkdir()
        (oracles / "oracle-secrets.mjs").write_text("", encoding="utf-8")
        recus: list[list[str]] = []

        def _lancer_espion(script: Path, scan: Path) -> dict:
            # La copie filtree est detruite au retour d `analyser` : son contenu se releve ICI.
            recus.append(sorted(c.relative_to(scan).as_posix() for c in scan.rglob("*.py")))
            return {"verdict": "PASS", "non_juge": [], "findings": []}

        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)
        monkeypatch.setattr(securite, "_lancer", _lancer_espion)

        sortie = securite.analyser(cible)

        # ROUGE implicite : verdict SKIP, motif « registre d oracles introuvable » (TF-0219).
        assert sortie.verdict == "PASS"
        assert recus, "l oracle delegue doit recevoir les sources du produit"
        assert "app/main.py" in recus[0], f"sources transmises : {recus[0]}"

    def test_le_pan_securite_ne_scanne_pas_les_artefacts_du_pilot(self, tmp_path, monkeypatch):
        """Corollaire de TF-0218 : elargir la racine ne doit pas elargir la POLLUTION.

        Depuis que ce pan peut lire la racine du depot, `forge\\` et `output\\` s y trouvent —
        les tendre a gitleaks imputerait des « fuites » a des livrables de forge-tests, ce qui
        est exactement RT-9 (219 faux positifs, 100 % hors du produit) transpose d un cran.
        """
        cible = _racine_plate(tmp_path)
        for dossier in ("forge/etapes/tests/livrables", "output", "old"):
            chemin = cible / dossier
            chemin.mkdir(parents=True)
            (chemin / "archive.py").write_text("CLE = 'AKIAABCDEFGHIJKLMNOP'\n", encoding="utf-8")
        oracles = tmp_path / "oracles"
        oracles.mkdir()
        (oracles / "oracle-secrets.mjs").write_text("", encoding="utf-8")
        recus: list[list[str]] = []

        def _lancer_espion(script: Path, scan: Path) -> dict:
            recus.append(sorted(c.relative_to(scan).as_posix() for c in scan.rglob("*.py")))
            return {"verdict": "PASS", "non_juge": [], "findings": []}

        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)
        monkeypatch.setattr(securite, "_lancer", _lancer_espion)
        securite.analyser(cible)

        assert recus
        assert "app/main.py" in recus[0]
        assert not any("archive.py" in fichier for fichier in recus[0]), recus[0]

    def test_le_pan_securite_declare_la_racine_sur_laquelle_il_a_lu(self, tmp_path, monkeypatch):
        cible = _racine_plate(tmp_path)
        oracles = tmp_path / "oracles"
        oracles.mkdir()
        (oracles / "oracle-secrets.mjs").write_text("", encoding="utf-8")
        monkeypatch.setattr(securite, "_racine_oracles", lambda: oracles)
        monkeypatch.setattr(
            securite, "_lancer", lambda s, c: {"verdict": "PASS", "non_juge": [], "findings": []}
        )

        sortie = securite.analyser(cible)

        assert any("racine d execution retenue" in m for m in sortie.non_juge)


class TestNonRegressionDispositionHistorique:
    """`backend\\` reste la PREMIERE ancre : aucun projet deja mesure ne bouge."""

    def test_backend_l_emporte_quand_il_existe(self, tmp_path):
        cible = _disposition_backend(tmp_path)
        assert racine_execution(cible) == cible / "backend"
        assert paquet_sources(cible) == cible / "backend" / "app"

    def test_backend_l_emporte_meme_si_la_racine_porte_aussi_des_indices(self, tmp_path):
        """Monorepo : `backend\\` complet ET un `tests\\` de bout en bout a la racine."""
        cible = _disposition_backend(tmp_path)
        (cible / "tests").mkdir()
        (cible / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        assert racine_execution(cible) == cible / "backend"

    def test_le_venv_de_backend_reste_prioritaire(self, tmp_path):
        cible = _disposition_backend(tmp_path)
        (cible / ".venv" / "Scripts").mkdir(parents=True)
        (cible / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
        python = execution._python(cible)
        assert python is not None
        assert python.parent.parent == cible / "backend" / ".venv"


class TestDeclarationAbsolue:
    """`FORGE_TESTS_SOURCES` absolu = base COMPLETE, cwd compris."""

    def test_un_chemin_absolu_fixe_aussi_la_racine_d_execution(self, tmp_path, monkeypatch):
        cible = tmp_path / "produit"
        (cible / "ailleurs" / "coeur").mkdir(parents=True)
        (cible / "ailleurs" / "coeur" / "m.py").write_text("X = 1\n", encoding="utf-8")
        monkeypatch.setenv("FORGE_TESTS_SOURCES", str(cible / "ailleurs" / "coeur"))
        assert paquet_sources(cible) == cible / "ailleurs" / "coeur"
        # Le cwd suit le paquet declare : c est ce qui rend la porte de sortie UTILISABLE pour
        # une disposition qu aucune convention ne decrit.
        assert racine_execution(cible) == cible / "ailleurs"

    def test_un_nom_relatif_reste_relatif_a_la_racine_decouverte(self, tmp_path, monkeypatch):
        cible = _racine_plate(tmp_path)
        (cible / "maison").mkdir()
        (cible / "maison" / "m.py").write_text("X = 1\n", encoding="utf-8")
        monkeypatch.setenv("FORGE_TESTS_SOURCES", "maison")
        assert paquet_sources(cible) == cible / "maison"
        assert racine_execution(cible) == cible


class TestDeterminismeEtDeclaration:
    """Le garde-fou de methode : jamais deviner en silence."""

    def test_la_decision_est_stable_d_un_appel_a_l_autre(self, tmp_path):
        cible = _racine_plate(tmp_path)
        decisions = {racine_execution(cible) for _ in range(5)}
        assert len(decisions) == 1

    def test_deux_projets_de_meme_disposition_decident_pareil(self, tmp_path):
        """Aucune heuristique de score, aucun ordre de parcours de disque : la meme
        disposition rend la meme racine, quels que soient les noms et l ordre de creation."""
        a = _racine_plate(tmp_path / "a")
        b = _racine_plate(tmp_path / "b")
        assert racine_execution(a).relative_to(a) == racine_execution(b).relative_to(b)

    def test_la_racine_retenue_est_publiable_en_clair(self, tmp_path):
        cible = _racine_plate(tmp_path)
        motif = motif_racine_execution(cible)
        assert motif.startswith("racine d execution retenue : ")
        assert str(cible) in motif

    def test_le_motif_nomme_la_regle_et_les_indices(self, tmp_path):
        cible = _racine_plate(tmp_path)
        motif = motif_racine_execution(cible)
        assert "indices trouves" in motif
        for indice in ("tests/", "pyproject.toml", ".venv/", "paquet Python"):
            assert indice in motif, f"indice non declare : {indice}"

    def test_le_motif_nomme_les_candidats_essayes_dans_l_ordre(self, tmp_path):
        cible = _racine_plate(tmp_path)
        motif = motif_racine_execution(cible)
        assert "candidats essayes dans l ordre" in motif
        # Le candidat ECARTE est nomme lui aussi, avec la raison de son ecart : sans cela, le
        # lecteur ne peut pas reconstituer la decision.
        assert f"{cible / 'backend'} (absent)" in motif
        assert motif.index(str(cible / "backend")) < motif.rindex(str(cible))

    def test_le_repli_sur_backend_se_declare_comme_un_repli(self, tmp_path):
        """Ni `backend\\`, ni aucun indice a la racine : la forge le DIT, elle ne devine pas."""
        motif = motif_racine_execution(tmp_path)
        assert "repli DECLARE" in motif
        assert "aucun candidat ne porte d indice" in motif

    def test_le_motif_d_indetermination_nomme_les_deux_candidats(self, tmp_path):
        """RT-2 cotait « aucun dossier `backend` » sans jamais dire que la racine plate avait
        ete regardee — le lecteur ne pouvait pas savoir que la question avait ete posee."""
        motif = motif_indetermine(tmp_path)
        assert "aucun dossier `backend`" in motif  # contrat historique preserve
        assert "racine d execution retenue" in motif

    def test_le_motif_d_indetermination_nomme_la_racine_ou_l_on_a_cherche(self, tmp_path):
        """Racine plate SANS paquet lisible : le motif doit dire SOUS QUOI on a cherche."""
        cible = tmp_path
        (cible / "tests").mkdir()
        (cible / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        assert paquet_sources(cible) is None
        motif = motif_indetermine(cible)
        assert "aucun paquet Python" in motif
        assert str(cible) in motif


class TestPansDebloquesEtResidus:
    """Ce que la nouvelle ancre debloque REELLEMENT, et ce qu elle laisse ouvert.

    Un correctif d ancre qui se contenterait de dire « c est corrige » sans mesurer pan par pan
    reproduirait le defaut de TF-0097, qui se croyait complet et ne l etait qu a moitie.
    """

    def test_aucun_adaptateur_ne_leve_sur_une_racine_plate(self, tmp_path):
        """G-2 : un pan qui LEVE emporte l audit entier (exit 2, zero rapport) — c est
        strictement pire que le SKIP qu il remplace."""
        from forge_tests.adaptateurs import REGISTRE

        cible = _racine_plate(tmp_path)
        leves: dict[str, str] = {}
        for nom, module in REGISTRE.items():
            if nom == "mutation-python":
                continue  # cf. le test suivant : residu CONNU, hors perimetre d ecriture
            try:
                module.analyser(cible)
            except Exception as erreur:  # noqa: BLE001 — c est precisement ce qu on mesure
                leves[nom] = f"{type(erreur).__name__}: {erreur}"
        assert not leves, leves

    def test_le_pan_back_ne_leve_pas_sur_une_racine_plate(self, tmp_path):
        from forge_tests.adaptateurs import mutation

        cible = _racine_plate(tmp_path)
        mutation.analyser(cible)  # ne doit RIEN lever

    def test_le_pan_interface_mesure_le_gabarit_jinja_du_produit(self, tmp_path):
        """Le pan qui ne dependait pas de l ancre reste, lui, parfaitement mesure."""
        from forge_tests.adaptateurs import interface

        cible = _racine_plate(tmp_path)
        sortie = interface.analyser(cible)
        assert sortie.verdict == "PASS"
        assert sortie.surface["inventorie"] == 2  # le `<form>` et son bouton de soumission


class TestMotifsDExecution:
    """Ce que le rapport lit quand la mesure echoue quand meme."""

    def test_la_racine_retenue_est_declaree_avant_toute_mesure(self, tmp_path):
        """Publiee des l entree de `mesurer`, quoi qu il advienne ensuite."""
        cible = _racine_plate(tmp_path)
        (cible / ".venv").rename(cible / ".venv-absent")  # aucun python : la mesure echoue
        assert execution.mesurer(str(cible)) is None
        declare = execution.motif_indisponibilite(cible, "racine-execution", "rien")
        assert declare.startswith("racine d execution retenue : ")
        assert str(cible) in declare

    def test_le_motif_d_absence_de_python_nomme_les_venv_essayes(self, tmp_path):
        cible = _racine_plate(tmp_path)
        (cible / ".venv").rename(cible / ".venv-absent")
        execution.mesurer(str(cible))
        motif = execution.motif_indisponibilite(cible, "backend", "rien")
        assert str(cible / ".venv") in motif
        assert "racine d execution retenue" in motif
