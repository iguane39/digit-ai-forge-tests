"""TF-2769 — un pan à 0 % qui porte une fonction centrale ne se cache plus derrière PARTIEL.

Fait remonté par Produit-12 (retour du 22/11/2026, RS-40) : l'audit du 08/11 inventorie 15
modèles d'IA au pan `prompts` et n'en exerce aucun (ratio 0, seuil 1). Le verdict PARTIEL
(sortie 3), porté par d'autres pans non couverts, a été accepté, et la version est partie en
production alors que la rédaction par IA n'avait jamais tourné. Onze retours de la même classe
depuis TF-1101 : un constat qu'aucun verdict ne force à lire.

Décision : le projet DÉCLARE ses pans centraux (`FORGE_TESTS_PANS_CENTRAUX`, liste de pans). Un
pan central mesuré à 0 % rend le verdict FAIL (sortie 1), avant PARTIEL, et le rapport nomme le
pan bloquant (`pans_bloquants`). La forge ne devine pas la centralité : sans déclaration, le
verdict est celui d'avant.

Sens prouvés :
  - ROUGE  — l'audit d'un projet dont le pan `prompts` est à 0 % rend PARTIEL (sortie 3), pan
             déclaré central ou non, sur l'ancien code ;
  - VERT   — pan déclaré central : FAIL (sortie 1), `pans_bloquants` le nomme avec son compte ;
  - CONTRE-ÉPREUVES — pan non déclaré : verdict inchangé ; pan central partiellement exercé,
             non mesuré ou inconnu : jamais bloquant, et la déclaration inutile est NOMMÉE ; la
             reprise fusionnée tient la même règle.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests import __main__ as cli
from forge_tests import authentification, execution, reprise
from forge_tests.authentification import ENV_AUDIT
from forge_tests.noyau import (
    VARIABLE_PANS_CENTRAUX,
    Element,
    SortieAdaptateur,
    evaluer_surface,
    lire_pans_centraux,
    pans_bloquants,
    rapport,
)

MODELE = "claude-sonnet-4-5-20250929"


@pytest.fixture(autouse=True)
def env_propre(monkeypatch, tmp_path):
    """`charger_env` écrit dans `os.environ` : sans restauration, un test voit celle d'un autre."""
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


def _surface(pan: str, inventories: int, exerces: int) -> SortieAdaptateur:
    """Un pan mesuré par la vraie fonction du noyau : `inventories` éléments, `exerces` d'entre eux
    exercés, seuil 1,0."""
    elements = [
        Element(f"{pan}:e{n}", pan, f"élément {n}", f"/x/{pan}") for n in range(inventories)
    ]
    return evaluer_surface("a", pan, "/x", elements, {e.id for e in elements[:exerces]}, 1.0, [])


def _skip(pan: str) -> SortieAdaptateur:
    return SortieAdaptateur("a", pan, "/x", "SKIP", non_juge=[f"{pan} : suite non exécutée"])


PANS = ["prompts", "api", "data"]


# --- La déclaration -------------------------------------------------
def test_la_declaration_se_lit_en_liste_sans_doublon_dans_l_ordre() -> None:
    assert lire_pans_centraux("prompts, api;data  api") == ["prompts", "api", "data"]
    assert lire_pans_centraux("PROMPTS") == ["prompts"]
    assert lire_pans_centraux("") == [] and lire_pans_centraux(None) == []


# --- Le rapport -----------------------------------------------------
def test_rouge_sans_declaration_un_pan_a_zero_reste_dans_un_verdict_partiel() -> None:
    """Le défaut du 08/11, conservé quand le projet ne déclare rien : PARTIEL, rien d'autre."""
    r = rapport([_surface("prompts", 15, 0), _skip("api")], PANS)
    assert r["verdict"] == "PARTIEL"
    assert r["pans_centraux"] == [] and r["pans_bloquants"] == []


def test_vert_un_pan_central_a_zero_rend_fail_et_est_nomme() -> None:
    r = rapport([_surface("prompts", 15, 0), _skip("api")], PANS, pans_centraux=["prompts"])
    assert r["verdict"] == "FAIL"  # et non PARTIEL, bien que `api` et `data` restent non couverts
    assert r["pans_centraux"] == ["prompts"]
    (bloquant,) = r["pans_bloquants"]
    assert bloquant["pan"] == "prompts" and bloquant["inventorie"] == 15 and bloquant["exerce"] == 0
    assert bloquant["ratio"] == 0.0 and bloquant["seuil"] == 1.0
    assert "pan central « prompts » à 0 %" in bloquant["motif"]
    # Le pan non couvert reste nommé : FAIL ne dispense pas de dire ce qui n'a pas été joué.
    assert {e["pan"] for e in r["pans_non_couverts"]} == {"api", "data"}


def test_contre_epreuve_un_pan_central_partiellement_exerce_n_est_pas_bloquant() -> None:
    r = rapport([_surface("prompts", 15, 1), _skip("api")], PANS, pans_centraux=["prompts"])
    assert r["pans_bloquants"] == []
    # le seuil non tenu se nomme déjà par ses constats, pas par ce motif
    assert r["verdict"] == "PARTIEL"


def test_contre_epreuve_un_pan_non_central_a_zero_ne_change_pas_le_verdict() -> None:
    r = rapport([_surface("data", 4, 0), _skip("api")], PANS, pans_centraux=["prompts"])
    assert r["pans_bloquants"] == [] and r["verdict"] == "PARTIEL"


def test_contre_epreuve_un_pan_central_non_mesure_n_est_pas_a_zero_mais_est_nomme() -> None:
    r = rapport([_skip("prompts")], PANS, pans_centraux=["prompts"])
    assert r["pans_bloquants"] == [] and r["verdict"] == "PARTIEL"
    assert any(
        "« prompts » est déclaré central mais n a aucune couverture mesurée" in ligne
        for ligne in r["non_juge"]
    )


def test_contre_epreuve_un_pan_inconnu_est_nomme_et_sans_effet() -> None:
    r = rapport([_surface("prompts", 3, 3)], ["prompts"], pans_centraux=["promtps"])
    assert r["pans_bloquants"] == [] and r["verdict"] == "PASS"
    ligne = next(ligne for ligne in r["non_juge"] if "« promtps » n est pas un pan connu" in ligne)
    assert VARIABLE_PANS_CENTRAUX in ligne and "prompts" in ligne


def test_contre_epreuve_un_pan_central_a_zero_sur_entrants_seuls_n_est_pas_bloquant() -> None:
    """Un pan sans élément produit (tous entrants, NA) a `inventorie` 0 : ce n'est pas 0 sur N."""
    surface = {"prompts": {"inventorie": 0, "exerce": 0, "ratio": 1.0}}
    assert pans_bloquants(surface, ["prompts"]) == []


def test_un_pan_central_tenu_ne_change_pas_un_verdict_pass() -> None:
    r = rapport([_surface("prompts", 3, 3)], ["prompts"], pans_centraux=["prompts"])
    assert r["verdict"] == "PASS" and r["pans_bloquants"] == []


# --- La reprise -----------------------------------------------------
def test_la_reprise_fusionnee_tient_la_meme_regle() -> None:
    ancien = rapport([_surface("prompts", 15, 0), _skip("api")], PANS, pans_centraux=["prompts"])
    fusion = reprise.fusionner(ancien, {}, "rapport.json", [], PANS)
    assert fusion["verdict"] == "FAIL"
    assert fusion["pans_centraux"] == ["prompts"]
    assert [b["pan"] for b in fusion["pans_bloquants"]] == ["prompts"]


def test_la_reprise_leve_le_blocage_quand_le_pan_central_est_enfin_exerce() -> None:
    ancien = rapport([_surface("prompts", 15, 0), _skip("api")], PANS, pans_centraux=["prompts"])
    neuf = rapport([_surface("prompts", 15, 15)], PANS, pans_centraux=["prompts"])
    fusion = reprise.fusionner(ancien, neuf, "rapport.json", ["prompts"], PANS)
    assert fusion["pans_bloquants"] == []
    assert fusion["verdict"] == "PARTIEL"  # `api` reste à rejouer : PARTIEL, plus FAIL


# --- L'audit complet et la CLI --------------------------------------
def _projet_a_zero(racine: Path, centraux: str | None) -> Path:
    """Un prompt adressable et son modèle, aucun corpus de cas : le pan `prompts` est à 0 sur 2."""
    _ecrire(
        racine, "prompts/assistant.prompt",
        f"modele: {MODELE}\n\nTu réponds à une question sur l'état d'une commande.\n",
    )
    if centraux is not None:
        _ecrire(racine, ENV_AUDIT, f"{VARIABLE_PANS_CENTRAUX}={centraux}\n")
    return racine


def test_rouge_l_audit_d_un_pan_a_zero_rend_partiel_sortie_3_sans_declaration(
    tmp_path: Path, capsys
) -> None:
    projet = _projet_a_zero(tmp_path / "produit", None)
    assert cli.main([str(projet), "--json", "--pans", "prompts"]) == cli.SORTIE_PARTIEL
    assert '"pans_bloquants": []' in capsys.readouterr().out


def test_vert_l_audit_lit_la_declaration_du_projet_et_sort_en_fail(
    tmp_path: Path, capsys
) -> None:
    projet = _projet_a_zero(tmp_path / "produit", "prompts")
    assert cli.main([str(projet), "--json", "--pans", "prompts"]) == cli.SORTIE_FAIL
    sortie = capsys.readouterr().out
    assert '"pans_centraux": [\n    "prompts"\n  ]' in sortie
    assert "pan central « prompts » à 0 %" in sortie


def test_la_lecture_humaine_nomme_le_pan_bloquant_sous_le_verdict(tmp_path: Path, capsys) -> None:
    projet = _projet_a_zero(tmp_path / "produit", "prompts")
    assert cli.main([str(projet), "--pans", "prompts"]) == cli.SORTIE_FAIL
    lignes = capsys.readouterr().out.splitlines()
    rang = next(i for i, ligne in enumerate(lignes) if ligne.startswith("verdict global : FAIL"))
    assert lignes[rang + 1].startswith("PAN BLOQUANT : pan central « prompts » à 0 %")
