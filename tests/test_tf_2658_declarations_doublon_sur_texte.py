"""TF-2658 — deux déclarations refusées comme doublons alors que leur message diffère.

Fait remonté par Produit-82 (lot 20261113e, RT-39, ledger seq 274) : deux constats SAST DISTINCTS
sur la même ligne partagent un identifiant (`securite:sast:<fichier>:<ligne>`) et ne se distinguent
que par leur message. Les déclarations portent le champ `texte`, que l'aide `pour_declarer`
présente comme l'ancre sur le message ; la forge refusait la seconde de chaque paire comme doublon,
parce que le doublon se jugeait sur le seul `constat`.

La règle : le doublon se juge sur le COUPLE `constat` + `texte` quand `texte` est fourni.

Deux sens :
  - VERT : deux déclarations de même `constat` et de `texte` différents sont retenues toutes deux,
    et chacune écarte SON constat ;
  - ROUGE : même `constat` et même `texte` (blancs près), ou un `texte` face à une déclaration
    sans `texte` (qui viserait déjà tout message), restent refusés comme doublons.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from forge_tests import declarations

JOUR = dt.date(2026, 11, 16)
CONSTAT = "securite/securite:sast:app/requetes.py:12"
SQL = "[sast] injection SQL : f-string dans execute()"
SHELL = "[sast] injection de commande : subprocess avec shell=True"


def _ecrire(racine: Path, lignes: list[dict]) -> None:
    (racine / "tests").mkdir(parents=True, exist_ok=True)
    preuve = racine / "tests" / "test_requetes.py"
    preuve.write_text("def test_a():\n    pass\n", encoding="utf-8")
    dossier = racine / "forge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "constats-contestes.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8"
    )


def _declaration(**surcharge: object) -> dict:
    base = {
        "constat": CONSTAT,
        "motif": "conteste",
        "preuve": "tests/test_requetes.py",
        "par": "equipe-api",
        "date": "2026-11-13",
        "texte": SQL,
    }
    base.update(surcharge)
    return base


def _finding(message: str) -> dict:
    return {
        "id": "securite:sast:app/requetes.py:12",
        "pan": "securite",
        "classe": "securite",
        "localisation": "app/requetes.py:12",
        "message": message,
        "severite": "bloquant",
        "risque": 40,
    }


def _rapport(*findings: dict) -> dict:
    return {
        "findings": [dict(f) for f in findings],
        "bandes_de_risque": {"critique": 0, "standard": len(findings), "differe": 0,
                             "non_cote": 0},
        "actions": [],
        "verdict": "FAIL",
    }


def test_deux_constats_distincts_sur_la_meme_ligne_portent_chacun_leur_declaration(
    tmp_path: Path,
) -> None:
    """Le critère de TF-2658, à l'identique du cas du 13/11 : aucune déclaration refusée."""
    _ecrire(tmp_path, [
        _declaration(texte=SQL, explication="requête paramétrée par l'ORM"),
        _declaration(texte=SHELL, explication="commande figée, aucun argument libre"),
    ])

    rapport = declarations.appliquer(_rapport(_finding(SQL), _finding(SHELL)), tmp_path, JOUR)

    compte = rapport["declarations"]["compte"]
    assert compte["refusee"] == 0, rapport["declarations"]["entrees"]
    assert compte["retenue"] == 2
    assert compte["constats_ecartes"] == 2
    ecartes = {f["message"]: f["declaration"]["explication"] for f in rapport["findings"]}
    assert ecartes == {
        SQL: "requête paramétrée par l'ORM",
        SHELL: "commande figée, aucun argument libre",
    }
    assert rapport["declarations"]["inconnues"] == []


def test_charger_retient_les_deux_declarations(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(texte=SQL), _declaration(texte=SHELL)])

    entrees = declarations.charger(tmp_path, JOUR)

    assert [e["statut"] for e in entrees.values()] == ["retenue", "retenue"]
    assert {e["texte"] for e in entrees.values()} == {SQL, SHELL}


def test_la_premiere_declaration_garde_la_cle_du_constat(tmp_path: Path) -> None:
    """Compatibilité : `charger(...)[constat]` rend toujours la première déclaration."""
    _ecrire(tmp_path, [_declaration(texte=SQL), _declaration(texte=SHELL)])

    assert declarations.charger(tmp_path, JOUR)[CONSTAT]["texte"] == SQL


def test_une_seule_des_deux_declarees_n_ecarte_que_son_constat(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(texte=SHELL)])

    rapport = declarations.appliquer(_rapport(_finding(SQL), _finding(SHELL)), tmp_path, JOUR)

    assert {f["message"] for f in rapport["findings"] if declarations.est_ecarte(f)} == {SHELL}


def test_rouge_meme_constat_meme_texte_reste_un_doublon(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(texte=SQL), _declaration(texte="  [sast]  injection SQL :\n"
                                                                  " f-string dans execute() ")])

    entrees = declarations.charger(tmp_path, JOUR)

    refusees = [e for e in entrees.values() if e["statut"] == "refusee"]
    assert len(refusees) == 1
    assert "doublon" in refusees[0]["motif_du_refus"]


def test_rouge_sans_texte_des_deux_cotes_le_doublon_reste_refuse(tmp_path: Path) -> None:
    """L'ancien comportement, tenu : sans `texte`, le couple se réduit au `constat`."""
    _ecrire(tmp_path, [_declaration(texte=""), _declaration(texte="")])

    entrees = declarations.charger(tmp_path, JOUR)

    assert sorted(e["statut"] for e in entrees.values()) == ["refusee", "retenue"]


def test_rouge_un_texte_face_a_une_declaration_sans_texte_est_un_doublon(tmp_path: Path) -> None:
    """Une déclaration sans `texte` vise déjà tout message de ce constat : la seconde la recoupe."""
    _ecrire(tmp_path, [_declaration(texte=""), _declaration(texte=SHELL)])

    entrees = declarations.charger(tmp_path, JOUR)

    assert sorted(e["statut"] for e in entrees.values()) == ["refusee", "retenue"]


def test_une_declaration_orpheline_est_nommee_avec_son_texte(tmp_path: Path) -> None:
    """Le rapport nomme la déclaration restée sans constat, et dit laquelle des deux c'est."""
    _ecrire(tmp_path, [_declaration(texte=SQL), _declaration(texte=SHELL)])

    rapport = declarations.appliquer(_rapport(_finding(SQL)), tmp_path, JOUR)

    inconnues = rapport["declarations"]["inconnues"]
    assert len(inconnues) == 1
    assert inconnues[0].startswith(CONSTAT) and "subprocess" in inconnues[0]
