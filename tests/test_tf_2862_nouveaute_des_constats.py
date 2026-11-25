"""TF-2862 (2/2) — le rapport DATE la nouveauté d'un constat : la règle, ou le code.

Fait (Produit-12, RS-56, 23/11/2026) : deux constats « bloquants » semgrep apparaissent sur
`table-filters.js`, fichier inchangé depuis `6660e50`, absents du rapport de la veille (101 constats
contre 103). Le rapport ne disait pas que la nouveauté venait de la règle et non du code ; le
lecteur cherchait une modification qui n'existait pas.

Le rapport précédent (`--precedent`, ou `--reprendre`) et `git log` du fichier tranchent : un
constat neuf dont le fichier n'a pas changé depuis le rapport précédent est « nouveau par la
règle » ; un constat neuf dont le fichier a été commité ou modifié depuis est « nouveau par le
code ». Les cas
rouges (le code a changé) tiennent l'autre bout : la règle ne se dit pas pour tout constat neuf.
Les dépôts git des cas sont RÉELS (date de commit posée par l'environnement de `git commit`).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import pytest

from forge_tests import __main__ as cli
from forge_tests import nouveaute
from forge_tests.nouveaute import (
    DEJA_PRESENT,
    NON_DATABLE,
    PAR_LA_REGLE,
    PAR_LE_CODE,
    classer,
    date_du_rapport,
    dater,
    lignes_du_resume,
    lire_precedent,
)

RAPPORT_PRECEDENT_LE = "2026-11-22T10:00:00+01:00"


# --- Un dépôt git réel, aux dates posées ------------------------------------------------------


def _git(depot: Path, *args: str, date: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@exemple.test",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@exemple.test"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(depot), *args], check=True, capture_output=True, env=env)


def _produit(tmp_path: Path, commite_le: str = "2026-11-10T09:00:00+01:00") -> Path:
    """Un produit versionné dont `app/table-filters.js` est commité à la date donnée."""
    depot = tmp_path / "produit"
    (depot / "app").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(depot)], check=True, capture_output=True)
    (depot / "app" / "table-filters.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
    _git(depot, "add", "-A")
    _git(depot, "commit", "-q", "-m", "ajout", date=commite_le)
    return depot


def _constat(depot: Path, ligne: int = 2, regle: str = "incomplete-sanitization") -> dict:
    lieu = f"{depot / 'app' / 'table-filters.js'}:{ligne}"
    return {
        "id": f"securite:sast:{lieu}", "classe": "securite", "localisation": lieu,
        "message": f"[sast] semgrep {regle}", "severite": "bloquant", "risque": None,
        "pan": "securite",
    }


def _rapport(findings: list[dict], **plus: object) -> dict:
    return {"findings": findings, "verdict": "FAIL", **plus}


def _precedent(findings: list[dict], genere_le: str | None = RAPPORT_PRECEDENT_LE) -> dict:
    return _rapport(findings, **({"genere_le": genere_le} if genere_le else {}))


def _origines(rap: dict) -> list[str]:
    return [c["nouveaute"]["origine"] for c in rap["findings"]]


# --- Le cas mesuré : constat neuf, fichier inchangé -> la règle ------------------------------


def test_un_constat_neuf_sur_un_fichier_inchange_est_nouveau_par_la_regle(tmp_path: Path) -> None:
    depot = _produit(tmp_path)  # commité le 10/11, rapport précédent le 22/11
    rap = _rapport([_constat(depot, 1), _constat(depot, 2)])

    dater(rap, depot, _precedent([]), None)

    assert _origines(rap) == [PAR_LA_REGLE, PAR_LA_REGLE]
    section = rap["nouveaute"]
    assert section["statut"] == "mesuree"
    assert section["comptes"][PAR_LA_REGLE] == 2 and section["comptes"][PAR_LE_CODE] == 0
    motif = rap["findings"][0]["nouveaute"]["motif"]
    assert "n'a pas changé depuis le rapport précédent" in motif and "règle" in motif
    assert rap["findings"][0]["nouveaute"]["dernier_commit"], "le dernier commit est cité"
    assert section["precedent"]["source_de_la_date"].startswith("champ `genere_le`")


def test_le_rapport_lisible_dit_la_regle_et_nomme_les_constats(tmp_path: Path) -> None:
    depot = _produit(tmp_path)
    rap = _rapport([_constat(depot, 1)])
    dater(rap, depot, _precedent([]), None)

    lignes = lignes_du_resume(rap)

    assert "1 nouveau(x) par la règle (fichier inchangé)" in lignes[0]
    assert "0 nouveau(x) par le code" in lignes[0]
    assert "par la règle" in lignes[1] and "table-filters.js:1" in lignes[1]


# --- Sens rouge : le code a changé -> ce n'est pas la règle ----------------------------------


def test_un_constat_neuf_sur_un_fichier_commite_apres_le_rapport_vient_du_code(
    tmp_path: Path,
) -> None:
    depot = _produit(tmp_path, commite_le="2026-11-23T08:00:00+01:00")
    rap = _rapport([_constat(depot)])

    dater(rap, depot, _precedent([]), None)

    assert _origines(rap) == [PAR_LE_CODE]
    assert "commité après le rapport précédent" in rap["findings"][0]["nouveaute"]["motif"]


def test_un_fichier_modifie_et_non_commite_vient_du_code(tmp_path: Path) -> None:
    depot = _produit(tmp_path)
    (depot / "app" / "table-filters.js").write_text("var a = 1;\nvar b = 3;\n", encoding="utf-8")
    rap = _rapport([_constat(depot)])

    dater(rap, depot, _precedent([]), None)

    assert _origines(rap) == [PAR_LE_CODE]
    assert "modifié depuis son dernier commit" in rap["findings"][0]["nouveaute"]["motif"]


def test_le_remede_du_rouge_rejoue_le_meme_constat_redevient_par_la_regle(tmp_path: Path) -> None:
    """Mêmes constats, même rapport précédent : seule la date du dernier commit change l'origine."""
    ancien = _produit(tmp_path / "a", commite_le="2026-11-10T09:00:00+01:00")
    recent = _produit(tmp_path / "b", commite_le="2026-11-23T09:00:00+01:00")
    rap_ancien, rap_recent = _rapport([_constat(ancien)]), _rapport([_constat(recent)])

    dater(rap_ancien, ancien, _precedent([]), None)
    dater(rap_recent, recent, _precedent([]), None)

    assert _origines(rap_ancien) == [PAR_LA_REGLE]
    assert _origines(rap_recent) == [PAR_LE_CODE]


# --- Les autres issues ------------------------------------------------------------------------


def test_un_constat_deja_au_rapport_precedent_est_deja_present(tmp_path: Path) -> None:
    depot = _produit(tmp_path, commite_le="2026-11-23T08:00:00+01:00")
    constat = _constat(depot)
    rap = _rapport([dict(constat)])

    dater(rap, depot, _precedent([constat]), None)

    assert _origines(rap) == [DEJA_PRESENT]
    assert rap["nouveaute"]["comptes"][DEJA_PRESENT] == 1


def test_un_fichier_non_versionne_n_est_pas_datable_et_le_dit(tmp_path: Path) -> None:
    depot = _produit(tmp_path)
    (depot / "app" / "neuf.js").write_text("var c = 3;\n", encoding="utf-8")
    constat = _constat(depot)
    constat["localisation"] = f"{depot / 'app' / 'neuf.js'}:1"
    constat["id"] = "securite:sast:neuf"
    rap = _rapport([constat])

    dater(rap, depot, _precedent([]), None)

    assert _origines(rap) == [NON_DATABLE]
    assert "non versionné" in rap["findings"][0]["nouveaute"]["motif"]


def test_une_localisation_qui_n_est_pas_un_fichier_n_est_pas_datable(tmp_path: Path) -> None:
    depot = _produit(tmp_path)
    constat = {**_constat(depot), "id": "api:GET /x", "localisation": "GET /x"}
    rap = _rapport([constat])

    dater(rap, depot, _precedent([]), None)

    assert _origines(rap) == [NON_DATABLE]
    assert "ne désigne pas un fichier" in rap["findings"][0]["nouveaute"]["motif"]


def test_un_precedent_sans_date_ne_date_aucun_constat(tmp_path: Path) -> None:
    depot = _produit(tmp_path)
    rap = _rapport([_constat(depot)])

    dater(rap, depot, _precedent([], genere_le=None), None)  # sans `genere_le` ni fichier

    assert _origines(rap) == [NON_DATABLE]
    assert any("aucune date" in n for n in rap["nouveaute"]["non_juge"])


# --- Sans rapport précédent : la section le dit ----------------------------------------------


def test_sans_rapport_precedent_la_section_est_presente_et_dit_pourquoi(tmp_path: Path) -> None:
    depot = _produit(tmp_path)
    rap = _rapport([_constat(depot)])

    dater(rap, depot, None, None)

    assert rap["nouveaute"]["statut"] == "non_mesuree"
    assert "--precedent" in rap["nouveaute"]["motif"]
    assert "nouveaute" not in rap["findings"][0], "sans point de comparaison, aucun constat daté"
    assert rap["genere_le"], "la date de CE rapport est posée pour que le suivant la lise"
    assert lignes_du_resume(rap)[0].startswith("nouveauté des constats : non datée")


def test_un_rapport_precedent_illisible_se_dit(tmp_path: Path) -> None:
    mauvais = tmp_path / "rapport.json"
    mauvais.write_text("{ pas du json", encoding="utf-8")

    precedent, fichier, refus = lire_precedent([mauvais], None)
    rap = _rapport([])
    dater(rap, tmp_path, precedent, fichier, refus=refus)

    assert precedent is None and refus and "illisible" in refus
    assert rap["nouveaute"]["statut"] == "non_mesuree"
    assert "illisible" in rap["nouveaute"]["motif"]


# --- La date du rapport précédent -------------------------------------------------------------


def test_la_date_vient_de_genere_le_puis_du_fichier(tmp_path: Path) -> None:
    fichier = tmp_path / "rapport-20261122c.json"
    fichier.write_text("{}", encoding="utf-8")
    veille = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC).timestamp()
    os.utime(fichier, (veille, veille))

    declaree, source_declaree = date_du_rapport({"genere_le": RAPPORT_PRECEDENT_LE}, fichier)
    du_fichier, source_fichier = date_du_rapport({}, fichier)
    aucune, source_aucune = date_du_rapport({}, None)

    assert declaree == dt.datetime.fromisoformat(RAPPORT_PRECEDENT_LE)
    assert "genere_le" in source_declaree
    assert du_fichier is not None and du_fichier.date() == dt.date(2026, 11, 22)
    assert "date de modification du fichier" in source_fichier
    assert aucune is None and source_aucune == "aucune date"


def test_les_donnees_git_sont_injectables_sans_depot(tmp_path: Path) -> None:
    fichier = tmp_path / "x.js"
    fichier.write_text("1\n", encoding="utf-8")
    constat = {"id": "n", "localisation": f"{fichier}:1"}

    rouge = classer(constat, set(), dt.datetime.fromisoformat(RAPPORT_PRECEDENT_LE), tmp_path,
                    lambda f: ("a" * 40, "2026-11-23T09:00:00+01:00"), lambda f: False)
    vert = classer(constat, set(), dt.datetime.fromisoformat(RAPPORT_PRECEDENT_LE), tmp_path,
                   lambda f: ("b" * 40, "2026-11-01T09:00:00+01:00"), lambda f: False)

    assert rouge["origine"] == PAR_LE_CODE and vert["origine"] == PAR_LA_REGLE
    assert vert["dernier_commit"] == "b" * 12


# --- La ligne de commande ---------------------------------------------------------------------

_RAPPORT_CLI = {
    "adaptateurs": [], "couverture_par_pan": {}, "mutation": {}, "seuils": {}, "modules": [],
    "pans_non_couverts": [], "pans_sans_objet": [], "motifs_non_couverture": {},
    "bandes_de_risque": {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0},
    "non_testables": [], "actions": [], "non_juge": [],
    "essais": {"cas": [], "totaux": {}, "signales": [], "fourni": False}, "verdict": "FAIL",
}


@pytest.fixture
def cli_fige(monkeypatch: pytest.MonkeyPatch):
    """La mesure est figée : ce test porte sur la datation de la CLI, pas sur l'audit."""
    def installer(findings: list[dict]) -> None:
        monkeypatch.setattr(
            cli, "analyser",
            lambda c, pans=None: {**_RAPPORT_CLI, "findings": json.loads(json.dumps(findings))},
        )
        monkeypatch.setattr("forge_tests.declarations.appliquer", lambda rapport, cible: None)
    return installer


def test_la_cli_date_le_rapport_json_avec_le_precedent(
    tmp_path: Path, cli_fige, capsys: pytest.CaptureFixture[str]
) -> None:
    depot = _produit(tmp_path)
    cli_fige([_constat(depot, 1)])
    precedent = tmp_path / "rapport-20261122c.json"
    precedent.write_text(json.dumps(_precedent([])), encoding="utf-8")

    cli.main([str(depot), "--json", "--precedent", str(precedent)])

    rapport = json.loads(capsys.readouterr().out)
    assert rapport["nouveaute"]["comptes"][PAR_LA_REGLE] == 1
    assert rapport["findings"][0]["nouveaute"]["origine"] == PAR_LA_REGLE
    assert rapport["nouveaute"]["precedent"]["fichier"].endswith("rapport-20261122c.json")


def test_la_cli_sans_precedent_publie_la_section_non_mesuree(
    tmp_path: Path, cli_fige, capsys: pytest.CaptureFixture[str]
) -> None:
    depot = _produit(tmp_path)
    cli_fige([_constat(depot, 1)])

    cli.main([str(depot), "--json"])

    rapport = json.loads(capsys.readouterr().out)
    assert rapport["nouveaute"]["statut"] == "non_mesuree"
    assert rapport["genere_le"]


def test_le_rapport_lisible_porte_la_ligne_de_nouveaute(
    tmp_path: Path, cli_fige, capsys: pytest.CaptureFixture[str]
) -> None:
    depot = _produit(tmp_path)
    cli_fige([_constat(depot, 1)])
    precedent = tmp_path / "precedent.json"
    precedent.write_text(json.dumps(_precedent([])), encoding="utf-8")

    cli.main([str(depot), "--precedent", str(precedent)])

    sortie = capsys.readouterr().out
    assert "nouveauté des constats" in sortie
    assert "1 nouveau(x) par la règle (fichier inchangé)" in sortie


def test_la_cli_prend_le_rapport_de_reprise_pour_precedent(
    tmp_path: Path, cli_fige, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    depot = _produit(tmp_path)
    constat = _constat(depot, 1)
    cli_fige([constat])
    ancien = tmp_path / "rapport-1.json"
    ancien.write_text(json.dumps(_precedent([constat])), encoding="utf-8")
    monkeypatch.setattr("forge_tests.reprise.pans_a_rejouer", lambda a: [])
    monkeypatch.setattr(
        "forge_tests.reprise.fusionner",
        lambda a, n, o, r, p: {**_RAPPORT_CLI, "findings": [dict(constat)]},
    )

    cli.main([str(depot), "--json", "--reprendre", str(ancien)])

    rapport = json.loads(capsys.readouterr().out)
    assert rapport["findings"][0]["nouveaute"]["origine"] == DEJA_PRESENT


def test_le_module_n_importe_pas_de_pan() -> None:
    """La datation lit le rapport, pas l'audit : aucune dépendance aux adaptateurs."""
    source = Path(nouveaute.__file__).read_text(encoding="utf-8")
    assert "adaptateurs" not in source
