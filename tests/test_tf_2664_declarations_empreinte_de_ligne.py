"""TF-2664 — une déclaration de constat contesté ne suivait pas le constat quand sa ligne changeait.

Fait remonté par Produit-82 (lot 20261113j, RT-46, ledger seq 292) : après 3 commits qui décalent
des lignes, 5 constats SAST déjà contestés le matin réapparaissent comme nouveaux. La déclaration
porte le champ `texte`, mais les cinq constats partagent le même message : l'ancrage par `texte`
(TF-1672) rend CINQ candidats pour chaque déclaration, rien n'est deviné, aucune ne suit.

La règle : le champ facultatif `empreinte` ancre la déclaration sur l'EMPREINTE DE LA LIGNE VISÉE
(son texte, blancs normalisés) ; le rapport publie l'empreinte des constats que le message seul ne
distingue pas, et nomme les déclarations restées sans constat.

Deux sens :
  - VERT : cinq constats de même message, décalés de trois lignes, restent cinq fois contestés,
    chacun avec SA déclaration ;
  - ROUGE : sans `empreinte` (déclarations d'avant ce champ), le même décalage laisse les cinq
    ambigus, comme avant ; une empreinte qui ne retrouve aucune ligne ne devine rien.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from forge_tests import declarations

JOUR = dt.date(2026, 11, 16)
MESSAGE = "[sast] injection SQL : f-string dans execute()"
PREMIERE_LIGNE = 10  # les cinq constats occupent les lignes 10 à 14 avant le décalage
LIGNES_DE_CODE = [f'    c.execute(f"SELECT * FROM t{n} WHERE id={{x}}")' for n in range(5)]
LIGNES_AJOUTEES = ["# commit 1", "# commit 2", "# commit 3"]


def _source(racine: Path, ajoutees: list[str]) -> None:
    (racine / "app").mkdir(parents=True, exist_ok=True)
    haut = [f"# entete {n}" for n in range(PREMIERE_LIGNE - 1)]
    (racine / "app" / "requetes.py").write_text(
        "\n".join([*ajoutees, *haut, *LIGNES_DE_CODE, "# fin"]) + "\n", encoding="utf-8"
    )


def _ecrire(racine: Path, lignes: list[dict]) -> None:
    preuve = racine / "tests" / "test_requetes.py"
    preuve.parent.mkdir(parents=True, exist_ok=True)
    preuve.write_text("def test_a():\n    pass\n", encoding="utf-8")
    dossier = racine / "forge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "constats-contestes.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8"
    )


def _ref(ligne: int) -> str:
    return f"securite:sast:app/requetes.py:{ligne}"


def _declarations(avec_empreinte: bool) -> list[dict]:
    lignes = []
    for rang, code in enumerate(LIGNES_DE_CODE):
        ligne = PREMIERE_LIGNE + rang
        entree = {
            "constat": f"securite/{_ref(ligne)}",
            "motif": "conteste",
            "preuve": "tests/test_requetes.py",
            "par": "equipe-api",
            "date": "2026-11-16",
            "texte": MESSAGE,
            "explication": f"ligne d'origine {ligne}",
        }
        if avec_empreinte:
            entree["empreinte"] = declarations.empreinte_de_ligne(code)
        lignes.append(entree)
    return lignes


def _findings(decalage: int) -> list[dict]:
    return [
        {
            "id": _ref(PREMIERE_LIGNE + rang + decalage),
            "pan": "securite",
            "classe": "securite",
            "localisation": f"app/requetes.py:{PREMIERE_LIGNE + rang + decalage}",
            "message": MESSAGE,
            "severite": "bloquant",
            "risque": 40,
        }
        for rang in range(len(LIGNES_DE_CODE))
    ]


def _rapport(findings: list[dict]) -> dict:
    return {
        "findings": findings,
        "bandes_de_risque": {"critique": 0, "standard": len(findings), "differe": 0,
                             "non_cote": 0},
        "actions": [],
        "verdict": "FAIL",
    }


def _ecartes(rapport: dict) -> int:
    return sum(1 for f in rapport["findings"] if declarations.est_ecarte(f))


def test_apres_trois_commits_les_cinq_constats_contestes_restent_contestes(tmp_path: Path) -> None:
    """Le critère de TF-2664 : décalage de 3 lignes, 5 constats de même message, 5 contestés."""
    _source(tmp_path, LIGNES_AJOUTEES)
    _ecrire(tmp_path, _declarations(avec_empreinte=True))

    rapport = declarations.appliquer(_rapport(_findings(decalage=3)), tmp_path, JOUR)

    assert _ecartes(rapport) == 5
    assert rapport["declarations"]["inconnues"] == []
    assert rapport["declarations"]["ambigues"] == {}
    assert rapport["declarations"]["compte"]["rapprochees"] == 5
    # Chaque constat porte SA déclaration : celle de la ligne d'origine, pas celle d'un voisin.
    for rang, finding in enumerate(rapport["findings"]):
        origine = PREMIERE_LIGNE + rang
        assert finding["declaration"]["explication"] == f"ligne d'origine {origine}", finding["id"]
        assert finding["declaration"]["ancrage"] == "empreinte"


def test_une_ligne_decalee_sur_une_ancienne_cle_n_est_pas_prise_pour_l_autre(
    tmp_path: Path,
) -> None:
    """Après le décalage, les clés 13 et 14 existent encore : elles désignent d'AUTRES lignes.
    La jointure exacte ne les prend pas pour leurs anciens propriétaires."""
    _source(tmp_path, LIGNES_AJOUTEES)
    _ecrire(tmp_path, _declarations(avec_empreinte=True))

    rapport = declarations.appliquer(_rapport(_findings(decalage=3)), tmp_path, JOUR)

    sous_13 = next(f for f in rapport["findings"] if f["id"] == _ref(13))
    assert sous_13["declaration"]["explication"] == "ligne d'origine 10"
    assert sous_13["declaration"]["rapprochee_de"].endswith(":10")


def test_sans_decalage_la_jointure_exacte_reste_la_regle(tmp_path: Path) -> None:
    _source(tmp_path, [])
    _ecrire(tmp_path, _declarations(avec_empreinte=True))

    rapport = declarations.appliquer(_rapport(_findings(decalage=0)), tmp_path, JOUR)

    assert _ecartes(rapport) == 5
    assert rapport["declarations"]["rapprochees"] == []
    assert rapport["declarations"]["compte"]["inconnues"] == 0


def test_rouge_sans_empreinte_le_meme_decalage_ne_suit_pas_les_cinq(tmp_path: Path) -> None:
    """Le défaut du 13/11, sur des déclarations d'avant ce champ : `texte` seul ne distingue pas
    cinq constats de même message. Deux clés (13 et 14) retombent même sur d'AUTRES constats et
    les écartent à tort ; les trois autres déclarations restent sans constat, nommées, avec leurs
    candidats. C'est l'état de toute déclaration sans `empreinte`."""
    _source(tmp_path, LIGNES_AJOUTEES)
    _ecrire(tmp_path, _declarations(avec_empreinte=False))

    rapport = declarations.appliquer(_rapport(_findings(decalage=3)), tmp_path, JOUR)

    assert _ecartes(rapport) < 5
    assert rapport["declarations"]["compte"]["inconnues"] == 3
    assert len(rapport["declarations"]["ambigues"]) == 3


def test_rouge_une_empreinte_qui_ne_retrouve_aucune_ligne_ne_devine_rien(tmp_path: Path) -> None:
    """La ligne visée a été RÉÉCRITE : son empreinte ne se retrouve plus. La déclaration reste
    sans constat, et le rapport la NOMME ; aucun voisin de même message n'est contesté à sa
    place."""
    _source(tmp_path, LIGNES_AJOUTEES)
    lignes = _declarations(avec_empreinte=True)
    lignes[2]["empreinte"] = declarations.empreinte_de_ligne("    c.execute(ancienne_ligne)")
    _ecrire(tmp_path, lignes)

    rapport = declarations.appliquer(_rapport(_findings(decalage=3)), tmp_path, JOUR)

    assert _ecartes(rapport) == 4
    assert rapport["declarations"]["inconnues"] == [f"securite/{_ref(12)}"]
    assert not any(f["id"] == _ref(15) and "declaration" in f for f in rapport["findings"])


def test_l_empreinte_ignore_les_blancs_et_la_casse_des_fins_de_ligne() -> None:
    assert declarations.empreinte_de_ligne("  c.execute( x )\r\n") == (
        declarations.empreinte_de_ligne("c.execute( x )")
    )
    assert declarations.empreinte_de_ligne("a b") != declarations.empreinte_de_ligne("a  c")


def test_le_rapport_publie_l_empreinte_des_constats_que_le_message_ne_distingue_pas(
    tmp_path: Path,
) -> None:
    """De quoi écrire `empreinte` sans la calculer à la main : elle se lit au rapport."""
    _source(tmp_path, [])
    _ecrire(tmp_path, [])

    rapport = declarations.appliquer(_rapport(_findings(decalage=0)), tmp_path, JOUR)

    publiees = rapport["declarations"]["empreintes"]
    assert publiees == {
        f"securite/{_ref(PREMIERE_LIGNE + rang)}": declarations.empreinte_de_ligne(code)
        for rang, code in enumerate(LIGNES_DE_CODE)
    }


def test_un_constat_unique_de_son_message_ne_publie_pas_d_empreinte(tmp_path: Path) -> None:
    _source(tmp_path, [])
    _ecrire(tmp_path, [])

    rapport = declarations.appliquer(_rapport(_findings(decalage=0)[:1]), tmp_path, JOUR)

    assert rapport["declarations"]["empreintes"] == {}


def test_pour_declarer_nomme_le_champ_empreinte(tmp_path: Path) -> None:
    _source(tmp_path, [])
    _ecrire(tmp_path, [])

    rapport = declarations.appliquer(_rapport([]), tmp_path, JOUR)

    assert "empreinte" in rapport["declarations"]["pour_declarer"]
