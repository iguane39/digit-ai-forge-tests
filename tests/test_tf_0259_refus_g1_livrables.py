"""TF-0259 — le refus G-1 de `--livrables` sortait MUET, et confondu avec une panne.

Fait mesure (retours BdL du 15/08/2026, R7) : un `--livrables` pointe DANS le projet audite
est refuse — comportement VOULU, garde-fou G-1 : la forge n ecrit jamais chez l audite, sans
quoi elle s auditerait elle-meme au run suivant. Mais deux choses manquaient a ce refus :

  1. son motif etait ECRIT et pourtant ILLISIBLE. stdout est bufferise, stderr ne l est pas :
     le rapport se vidait APRES le message, qui atterrissait ligne 24 d une sortie de 69.
     L operateur qui lit la fin de sa sortie ne voyait qu un exit 2 muet — deux executions
     perdues avant diagnostic ;
  2. il sortait en 2, le code des ERREURS DE GENERATION. « J ai mal designe le dossier » et
     « la generation a echoue » n appellent pas le meme remede, et rien ne les distinguait.

Le code 4 est neuf. L audit des consommateurs du 15/08 le rend sans risque : le contrat publie
du pilot ne documente que 0/1/3, le seul consommateur EXECUTABLE de la CLI
(`conductor/gates/affordances_gate.py` de forge-development) ne lit jamais `returncode` mais le
JSON de stdout, et aucun script, oracle ou CI de l ecosysteme ne teste un code de sortie de
forge-tests. La classe `TestNonRegressionDesAutresCodes` tient l autre bout : les codes
existants ne bougent pas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import __main__ as cli

_RAPPORT_VERT = {
    "adaptateurs": [],
    "couverture_par_pan": {},
    "mutation": {},
    "seuils": {},
    "modules": [],
    "pans_non_couverts": [],
    "pans_sans_objet": [],
    "motifs_non_couverture": {},
    "bandes_de_risque": {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0},
    "findings": [],
    "non_testables": [],
    "actions": [],
    "non_juge": [],
    "essais": {"cas": [], "totaux": {}, "signales": [], "fourni": False},
    "verdict": "PASS",
}


@pytest.fixture
def projet(tmp_path, monkeypatch):
    """Un projet audite dont la mesure est figee : ce test porte sur la CLI, pas sur l audit."""
    cible = tmp_path / "produit"
    (cible / "app").mkdir(parents=True)
    (cible / "app" / "main.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(cli, "analyser", lambda c, pans=None: dict(_RAPPORT_VERT))
    monkeypatch.setattr(
        "forge_tests.declarations.appliquer", lambda rapport, cible: None
    )
    return cible


def _lancer(projet: Path, dossier: Path, capsys) -> tuple[int, str]:
    code = cli.main([str(projet), "--json", "--livrables", str(dossier)])
    return code, capsys.readouterr().err


class TestRefusG1:
    """Le refus reste un refus — il devient LISIBLE et DISTINCT."""

    def test_le_dossier_dans_le_projet_sort_le_code_de_refus(self, projet, capsys):
        code, _err = _lancer(projet, projet / "forge" / "livrables", capsys)
        # ROUGE : `SORTIE_ERREUR` (2), le meme code qu un referentiel introuvable ou qu un
        # dashboard en ecart — trois causes, un seul code, aucun tri possible.
        assert code == cli.SORTIE_REFUS_G1
        assert cli.SORTIE_REFUS_G1 != cli.SORTIE_ERREUR

    def test_le_motif_est_explicite_et_nomme_le_chemin_recu(self, projet, capsys):
        dossier = projet / "etapes" / "tests" / "livrables"
        _code, err = _lancer(projet, dossier, capsys)
        assert "G-1 : livrables HORS projet requis" in err
        assert f"chemin reçu : {dossier}" in err

    def test_le_motif_se_lit_en_QUEUE_de_sortie(self, projet, capsys):
        """Le coeur du constat : le message existait deja, mais pas la ou on le lit."""
        _code, err = _lancer(projet, projet / "livrables", capsys)
        lignes = [ligne for ligne in err.splitlines() if ligne.strip()]
        # Le bloc de refus occupe la FIN de stderr — rien ne s imprime apres lui.
        assert any("G-1 : livrables HORS projet requis" in ligne for ligne in lignes[-3:]), err

    def test_le_projet_lui_meme_comme_dossier_est_refuse(self, projet, capsys):
        code, err = _lancer(projet, projet, capsys)
        assert code == cli.SORTIE_REFUS_G1
        assert "G-1 : livrables HORS projet requis" in err

    def test_la_mesure_n_est_pas_perdue(self, projet, capsys):
        """Le rapport est publie AVANT les livrables : un dossier mal designe ne coute pas
        l audit. La sortie le DIT, sans quoi l operateur relance pour rien."""
        code = cli.main([str(projet), "--json", "--livrables", str(projet / "x")])
        capture = capsys.readouterr()
        assert code == cli.SORTIE_REFUS_G1
        assert '"verdict": "PASS"' in capture.out
        assert "la mesure n est pas perdue" in capture.err

    def test_un_dossier_hors_projet_n_est_pas_refuse(self, projet, tmp_path, capsys):
        """Temoin : le garde-fou n a pas ete elargi — un dossier exterieur passe."""
        code = cli.main(
            [str(projet), "--json", "--livrables", str(tmp_path / "propositions")]
        )
        capsys.readouterr()
        assert code != cli.SORTIE_REFUS_G1


class TestNonRegressionDesAutresCodes:
    """Le code 4 s AJOUTE : aucun code existant ne change de sens."""

    def test_les_codes_historiques_sont_intacts(self):
        assert (cli.SORTIE_OK, cli.SORTIE_FAIL, cli.SORTIE_ERREUR, cli.SORTIE_PARTIEL) == (
            0, 1, 2, 3
        )

    def test_le_code_de_refus_ne_collisionne_avec_aucun_autre(self):
        codes = (cli.SORTIE_OK, cli.SORTIE_FAIL, cli.SORTIE_ERREUR, cli.SORTIE_PARTIEL)
        assert cli.SORTIE_REFUS_G1 not in codes

    def test_une_panne_de_generation_garde_le_code_erreur(self, projet, monkeypatch, capsys):
        """La distinction n a de valeur que si l AUTRE cas garde son code : une generation qui
        echoue pour toute autre raison reste un 2."""
        import forge_tests.livrables as livrables

        def _casse(*_args, **_kwargs):
            raise RuntimeError("dashboard : les totaux affiches divergent du rapport")

        monkeypatch.setattr(livrables, "produire", _casse)
        code = cli.main(
            [str(projet), "--json", "--livrables", str(projet.parent / "dehors")]
        )
        err = capsys.readouterr().err
        assert code == cli.SORTIE_ERREUR
        assert "livrables NON PRODUITS" in err

    def test_un_audit_sans_livrables_ne_voit_pas_le_nouveau_code(self, projet, capsys):
        code = cli.main([str(projet), "--json"])
        capsys.readouterr()
        assert code == cli.SORTIE_OK


class TestDocumentation:
    """Un code de sortie non documente est un code de sortie qui n existe pas pour l appelant."""

    def test_le_readme_publie_le_code_4_et_son_message(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        assert "| `4` |" in readme
        assert "G-1 : livrables HORS projet requis" in readme
