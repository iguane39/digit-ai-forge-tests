"""Lot de retours bourse-aux-vacants 20260814a — RT-9 à RT-13, un test par défaut constaté.

Chaque test ci-dessous ÉCHOUAIT avant le correctif du 14/08 : c est ce qui les distingue d une
description après coup. Les cas sont ceux que le produit a mesurés, pas des cas de laboratoire
choisis pour passer.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import adoption
from forge_tests.adaptateurs import front, interface
from forge_tests.livrables import surface
from forge_tests.noyau import Element


# --- RT-11 : les routes non statiques ne sont jamais attribuables -----------------------------
def test_rt11_route_parametree_appariee_par_son_motif() -> None:
    """`/login/reset-password/:token/:email` EST visitée par la suite (preuve du produit :
    10-navigation.spec.ts l.49) et sortait « inventoriée, jamais exercée »."""
    declaree = "/login/reset-password/:token/:email"
    motif = front.motif_de_route(declaree)
    assert motif.match("/login/reset-password/abc123/qui@exemple.fr")
    # Un segment de moins n est pas la même route : le motif ne doit pas devenir permissif.
    assert not motif.match("/login/reset-password/abc123")


def test_rt11_splat_et_racine() -> None:
    assert front.motif_de_route("/*").match("/n/importe/quoi")
    assert front.motif_de_route("*").match("/inconnue")
    assert front.motif_de_route("/").match("/")
    assert not front.motif_de_route("/").match("/login")


def test_rt11_appariement_sur_inventaire() -> None:
    inventaire = [
        Element("route:/login/reset-password/:token/:email", "front", "route", "src"),
        Element("route:/facture/:id", "front", "route", "src"),
        Element("element:bouton", "front", "élément", "src"),
    ]
    couvert = front._routes_appariees(
        inventaire, ["/login/reset-password/jeton/moi@exemple.fr"]
    )
    assert couvert == {"route:/login/reset-password/:token/:email"}


# --- RT-9 / RT-10 : les artefacts ne sont pas des gabarits ------------------------------------
def test_rt9_les_artefacts_sortent_de_l_inventaire(tmp_path: Path) -> None:
    """Le pan `interface` inventoriait les dashboards produits par forge-tests elle-même :
    6 -> 27 éléments entre deux audits sans qu une ligne de gabarit change."""
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text("<a href='/'>x</a>", encoding="utf-8")
    # `old` et `Old` désignent le même dossier sur Windows, deux sur Linux : les deux graphies
    # sont exclues, le test les crée sans supposer laquelle survit.
    for artefact in ("output", "old", "Old", ".oracles"):
        dossier = tmp_path / artefact
        dossier.mkdir(exist_ok=True)
        (dossier / f"livrable-{artefact.strip('.')}.html").write_text(
            "<a href='/'>y</a>", encoding="utf-8"
        )
    retenus = interface._fichiers(tmp_path, interface.EXTENSIONS)
    assert [c.name for c in retenus] == ["index.html"]


# --- RT-12 : le constat de la route porteuse explique celui de l élément ------------------------
def test_rt12_le_constat_de_la_route_remonte_a_ses_elements() -> None:
    """Sur `qualif:effet:/:0:form`, la cellule affichait « formulaire sans action » sans le
    401 de `qualif:route:/` qui en est la cause — deux sous-chapitres plus loin."""
    rapport = {
        "couverture_par_pan": {
            "qualif": {
                "elements_exerces": [],
                "elements_non_exerces": ["qualif:effet:/:0:form", "qualif:route:/"],
            }
        },
        "findings": [
            {
                "pan": "qualif",
                "id": "qualif:route:/",
                "classe": "route-en-defaut",
                "message": "/ — erreur console : 401 (UNAUTHORIZED)",
                "severite": "bloquant",
                "risque": 27,
            },
            {
                "pan": "qualif",
                "id": "qualif:effet:/:0:form",
                "classe": "affordance-sans-effet",
                "message": "formulaire sans action ni écouteur de soumission",
                "severite": "bloquant",
                "risque": 27,
            },
        ],
    }
    par_pan = surface.inventaire(rapport)
    formulaire = next(e for e in par_pan["qualif"] if e["id"] == "qualif:effet:/:0:form")
    assert formulaire["porteur"]["id"] == "qualif:route:/"
    assert "401" in formulaire["porteur"]["message"]
    # La route ne se porte pas elle-même : ce serait une redite, pas un contexte.
    route = next(e for e in par_pan["qualif"] if e["id"] == "qualif:route:/")
    assert "porteur" not in route


def test_rt12_un_constat_rattache_vaut_etat_ko() -> None:
    """Un élément nommé par un finding affichait « Non joué » tout en portant un constat."""
    rapport = {
        "couverture_par_pan": {
            "qualif": {"elements_exerces": [], "elements_non_exerces": ["qualif:effet:/:0:form"]}
        },
        "findings": [
            {
                "pan": "qualif",
                "id": "qualif:effet:/:0:form",
                "classe": "affordance-sans-effet",
                "message": "formulaire sans action",
                "severite": "bloquant",
            }
        ],
    }
    element = surface.inventaire(rapport)["qualif"][0]
    assert element["etat"] == "defaut"


# --- RT-13 : une proposition doit pouvoir être adoptée ----------------------------------------
def _ecrire_adoptions(racine: Path, lignes: list[dict]) -> None:
    dossier = racine / "forge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "cas-adoptes.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8"
    )


def test_rt13_adoption_declaree_et_verifiee(tmp_path: Path) -> None:
    test = tmp_path / "frontend" / "tests" / "e2e" / "10-navigation.spec.ts"
    test.parent.mkdir(parents=True)
    test.write_text("// @cas F1-3025-3", encoding="utf-8")
    _ecrire_adoptions(
        tmp_path, [{"cas": "F1-3025-3", "test": "frontend/tests/e2e/10-navigation.spec.ts"}]
    )
    adoptions = adoption.charger(tmp_path)
    assert adoption.statut(adoptions, "F1-3025-3")["statut"] == "adopte"
    # Un cas non déclaré reste une proposition — jamais « non joué ».
    assert adoption.statut(adoptions, "F1-9999-1")["statut"] == "proposition"


def test_rt13_adoption_sans_test_existant_est_refusee(tmp_path: Path) -> None:
    """Sans ce contrôle, le solde descendrait sur du vide : un fichier d adoptions survivrait
    à la suppression des tests qu il cite."""
    _ecrire_adoptions(tmp_path, [{"cas": "F1-3025-3", "test": "tests/disparu.spec.ts"}])
    entree = adoption.statut(adoption.charger(tmp_path), "F1-3025-3")
    assert entree["statut"] == "refuse"
    assert "introuvable" in entree["motif"]


def test_rt13_aucune_declaration_n_est_pas_une_faute(tmp_path: Path) -> None:
    assert adoption.charger(tmp_path) == {}


def test_rt13_reference_inconnue_du_cahier_est_declaree(tmp_path: Path) -> None:
    test = tmp_path / "t.spec.ts"
    test.write_text("x", encoding="utf-8")
    _ecrire_adoptions(tmp_path, [{"cas": "F1-0000-9", "test": "t.spec.ts"}])
    adoptions = adoption.charger(tmp_path)
    assert adoption.references_inconnues(adoptions, {"F1-3025-3"}) == ["F1-0000-9"]
