"""TF-1672 — une déclaration de constat contesté indexée sur un numéro de ligne tombait dès que le
code se décalait.

Le fait, remis par Produit-80 le 12/10/2026 (RT-1 du lot 20261012b, ledger seq 334) : le constat
`interface:frontend/src/components/coquille.tsx:203:a`, contesté le 30/09, est revenu NON
DÉCLARÉ sous `:205:a` après l ajout de deux entrées de menu au-dessus. Même lien, même défaut,
identifiant différent. Coût : un audit complet de plus pour une déclaration à refaire.

Ce que ces tests fixent :
  1. une déclaration écrite AVANT ce correctif (sans `texte`) suit son constat quand seule la
     ligne a changé et qu un seul constat libre a la même forme — et le rapprochement est publié ;
  2. le champ facultatif `texte` ancre la déclaration sur le message du constat : elle le
     retrouve parmi plusieurs candidats, et ne vise plus une ancienne ligne qu occupe un autre
     constat ;
  3. dès que le choix n est pas unique, rien n est deviné : la déclaration reste inconnue et
     ses candidats sont nommés ;
  4. seul le numéro de ligne qui suit un nom de fichier est masqué.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from forge_tests import declarations

JOUR = dt.date(2026, 10, 14)
FICHIER_UI = "frontend/src/components/coquille.tsx"
MESSAGE = "a « Paramètres » — lien vers une route absente"


def _ecrire(racine: Path, lignes: list[dict]) -> None:
    dossier = racine / "forge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "constats-contestes.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8"
    )


def _declaration(racine: Path, ligne: int = 203, **surcharge: object) -> dict:
    preuve = racine / "frontend/tests/e2e/menu.spec.ts"
    preuve.parent.mkdir(parents=True, exist_ok=True)
    preuve.write_text("// le test qui etablit le contraire", encoding="utf-8")
    base = {
        "constat": f"interface/interface:{FICHIER_UI}:{ligne}:a",
        "motif": "conteste",
        "preuve": "frontend/tests/e2e/menu.spec.ts",
        "par": "equipe-front",
        "date": "2026-09-30",
    }
    base.update(surcharge)
    return base


def _finding(ligne: int, message: str = MESSAGE, classe: str = "lien-casse") -> dict:
    return {
        "id": f"interface:{FICHIER_UI}:{ligne}:a",
        "pan": "interface",
        "classe": classe,
        "localisation": FICHIER_UI,
        "message": message,
        "severite": "bloquant",
        "risque": 30,
    }


def _rapport(*findings: dict) -> dict:
    return {
        "findings": [dict(f) for f in findings],
        "bandes_de_risque": {"critique": 0, "standard": len(findings), "differe": 0,
                             "non_cote": 0},
        "actions": [
            {"finding_ref": f"interface/{f['id']}", "categorie": "manuelle_dev"}
            for f in findings
        ],
        "verdict": "FAIL",
    }


def _ecarte(rapport: dict, ligne: int) -> bool:
    return any(
        declarations.est_ecarte(f)
        for f in rapport["findings"]
        if f["id"] == f"interface:{FICHIER_UI}:{ligne}:a"
    )


# --- 1. Le cas réel, déclaration écrite avant le correctif ----------------------------------------
def test_la_declaration_suit_son_constat_quand_la_ligne_se_decale(tmp_path: Path) -> None:
    """ROUGE avant le correctif : le cas de Produit-80 à l identique. La déclaration visait
    `:203:a`, le constat est sous `:205:a` : il revenait au décompte, la déclaration sortait
    INCONNUE."""
    _ecrire(tmp_path, [_declaration(tmp_path, 203)])

    rapport = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)

    assert _ecarte(rapport, 205)
    assert rapport["declarations"]["inconnues"] == []
    assert rapport["declarations"]["compte"]["rapprochees"] == 1
    rapprochee = rapport["declarations"]["rapprochees"][0]
    assert rapprochee["declare"].endswith(":203:a")
    assert rapprochee["retrouve"] == f"interface/interface:{FICHIER_UI}:205:a"
    assert rapprochee["ancrage"] == "forme-sans-ligne"
    # Le rapprochement se DIT, avec ce qu il faut écrire pour ne plus en dépendre.
    assert ":205:a" in rapprochee["a_faire"] and "texte" in rapprochee["a_faire"]
    assert rapport["findings"][0]["declaration"]["rapprochee_de"].endswith(":203:a")
    # L action du constat écarté est mise à part, comme pour une jointure exacte.
    assert rapport["actions"] == []


def test_la_jointure_exacte_reste_la_regle(tmp_path: Path) -> None:
    """VERT de compatibilité : une déclaration qui vise encore la bonne ligne ne passe pas par
    le rapprochement."""
    _ecrire(tmp_path, [_declaration(tmp_path, 205)])

    rapport = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)

    assert _ecarte(rapport, 205)
    assert rapport["declarations"]["rapprochees"] == []
    assert "rapprochee_de" not in rapport["findings"][0]["declaration"]


# --- 2. L ancrage par `texte` --------------------------------------------------------------------
def test_texte_retrouve_le_constat_parmi_plusieurs_candidats(tmp_path: Path) -> None:
    """ROUGE avant le correctif : deux liens en défaut dans le même fichier. Sans `texte`, le
    choix serait ambigu ; avec, la déclaration vise celui dont le message est le sien."""
    _ecrire(tmp_path, [_declaration(tmp_path, 203, texte=MESSAGE)])
    autre = "a « Aide » — lien vers une route absente"

    rapport = declarations.appliquer(
        _rapport(_finding(205, autre), _finding(230)), tmp_path, JOUR
    )

    assert _ecarte(rapport, 230)
    assert not _ecarte(rapport, 205)
    assert rapport["declarations"]["rapprochees"][0]["ancrage"] == "texte"


def test_texte_refuse_l_ancienne_ligne_occupee_par_un_autre_constat(tmp_path: Path) -> None:
    """ROUGE avant le correctif : un AUTRE lien est arrivé sous `:203:a`. La jointure exacte
    l écartait à la place du constat contesté — une contestation appliquée au mauvais défaut."""
    autre = "a « Aide » — lien vers une route absente"
    _ecrire(tmp_path, [_declaration(tmp_path, 203, texte=MESSAGE)])

    rapport = declarations.appliquer(
        _rapport(_finding(203, autre), _finding(205)), tmp_path, JOUR
    )

    assert not _ecarte(rapport, 203)
    assert _ecarte(rapport, 205)


def test_texte_compare_le_message_sans_tenir_compte_des_blancs(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path, 205, texte="  a  « Paramètres »\n— lien vers une "
                                                         "route absente ")])

    rapport = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)

    assert _ecarte(rapport, 205)


# --- 3. Rien n est deviné ------------------------------------------------------------------------
def test_plusieurs_candidats_sans_texte_restent_ambigus(tmp_path: Path) -> None:
    """Sens rouge de la règle : deux constats libres de même forme, aucun `texte` — choisir
    l un serait deviner. La déclaration reste inconnue, les candidats sont nommés."""
    _ecrire(tmp_path, [_declaration(tmp_path, 203)])

    rapport = declarations.appliquer(
        _rapport(_finding(205), _finding(230, "a « Aide » — x")), tmp_path, JOUR
    )

    assert not any(declarations.est_ecarte(f) for f in rapport["findings"])
    cle = f"interface/interface:{FICHIER_UI}:203:a"
    assert rapport["declarations"]["inconnues"] == [cle]
    assert rapport["declarations"]["ambigues"][cle] == [
        f"interface/interface:{FICHIER_UI}:205:a",
        f"interface/interface:{FICHIER_UI}:230:a",
    ]


def test_deux_declarations_orphelines_pour_un_seul_constat_restent_ambigues(
    tmp_path: Path,
) -> None:
    """Deux contestations anciennes de même forme, un seul constat libre : lequel des deux défauts
    a disparu ne se sait pas. Aucune n est appliquée."""
    _ecrire(tmp_path, [_declaration(tmp_path, 203), _declaration(tmp_path, 240)])

    rapport = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)

    assert not _ecarte(rapport, 205)
    assert len(rapport["declarations"]["inconnues"]) == 2


def test_un_constat_deja_declare_n_est_pas_un_candidat(tmp_path: Path) -> None:
    """Le constat que vise déjà une déclaration exacte n est pas libre : l orpheline ne peut pas
    le reprendre."""
    _ecrire(
        tmp_path,
        [
            _declaration(tmp_path, 205),
            _declaration(tmp_path, 203, par="autre-equipe"),
        ],
    )

    rapport = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)

    assert rapport["findings"][0]["declaration"]["par"] == "equipe-front"
    assert rapport["declarations"]["rapprochees"] == []
    assert rapport["declarations"]["inconnues"] == [f"interface/interface:{FICHIER_UI}:203:a"]


def test_la_classe_declaree_borne_aussi_le_rapprochement(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path, 203, classe="affordance-inerte")])

    rapport = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)

    assert not _ecarte(rapport, 205)


# --- 4. Seul le numéro de ligne d un fichier est masqué -------------------------------------------
def test_forme_stable_ne_masque_que_la_ligne_qui_suit_un_fichier() -> None:
    assert (
        declarations.forme_stable(f"interface/interface:{FICHIER_UI}:203:a#1")
        == f"interface/interface:{FICHIER_UI}:*:a#1"
    )
    assert declarations.forme_stable("qualif/qualif:effet:/:0:form") == (
        "qualif/qualif:effet:/:0:form"
    )


def test_un_index_qui_ne_suit_pas_un_fichier_n_est_pas_rapproche(tmp_path: Path) -> None:
    """Sens rouge du masquage : `:0:` dans `qualif:effet:/:0:form` est un rang, pas une ligne.
    Le masquer rapprocherait deux formulaires différents de la même page."""
    preuve = tmp_path / "tests/e2e/f.spec.ts"
    preuve.parent.mkdir(parents=True)
    preuve.write_text("//", encoding="utf-8")
    _ecrire(
        tmp_path,
        [{"constat": "qualif/qualif:effet:/:0:form", "motif": "conteste",
          "preuve": "tests/e2e/f.spec.ts", "par": "equipe", "date": "2026-09-30"}],
    )
    finding = {"id": "qualif:effet:/:1:form", "pan": "qualif", "classe": "x", "message": "m",
               "risque": 10}

    rapport = declarations.appliquer(_rapport(finding), tmp_path, JOUR)

    assert not any(declarations.est_ecarte(f) for f in rapport["findings"])
    assert rapport["declarations"]["inconnues"] == ["qualif/qualif:effet:/:0:form"]


# --- Idempotence ---------------------------------------------------------------------------------
def test_appliquer_deux_fois_donne_le_meme_rapport(tmp_path: Path) -> None:
    _ecrire(tmp_path, [_declaration(tmp_path, 203)])
    une_fois = declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR)
    deux_fois = declarations.appliquer(
        declarations.appliquer(_rapport(_finding(205)), tmp_path, JOUR), tmp_path, JOUR
    )
    assert une_fois == deux_fois
