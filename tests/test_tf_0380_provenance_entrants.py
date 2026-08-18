"""TF-0380 — un pan couvert à 100 % sur des fichiers REÇUS.

Le fait, mesuré sur un audit réel : verdict global PARTIEL, juste. Mais le **seul** pan couvert,
`interface`, affichait **15 inventoriés / 15 exercés, ratio 1,0, PASS** — et ses 15 éléments
étaient les 15 ancres de deux fichiers `input/*.html`, des documents **reçus du client** que ce
projet ne produit pas et ne modifie jamais. Au même commit, les trois livrables HTML de `output/`
portaient 27 ancres, dont aucune n'était inventoriée (`output/` est exclu depuis RT-9/RT-10, à
juste titre : auditer ses propres artefacts est un auto-audit).

Le seul PASS de l'audit portait donc sur ce que le projet ne produit pas.

**Un ratio de 1,0 sur des entrants est plus trompeur qu'un pan franchement non couvert** : le
second se voit, le premier se lit comme une réussite.

Ce qui est corrigé : un élément porte sa **provenance**, déduite du chemin — aucun adaptateur n'a
à connaître le mécanisme, et un adaptateur futur en hérite sans une ligne. Les entrants restent
inventoriés et NOMMÉS (les taire ferait disparaître ce qui a été lu), mais ils ne comptent ni au
numérateur ni au dénominateur. Et quand tout l'inventaire est entrant, le pan sort **NA** avec un
motif qui le dit.
"""

from __future__ import annotations

from forge_tests.noyau import Element, evaluer_surface, provenance_de

SEUIL = 0.8


def _element(identifiant: str, source: str, provenance: str = "") -> Element:
    return Element(id=identifiant, pan="interface", libelle=identifiant, source=source,
                   provenance=provenance)


# --- La déduction, et son SENS D'ERREUR --------------------------------------------------------
def test_un_chemin_sous_input_est_un_ENTRANT() -> None:
    assert provenance_de("input/Client - Cahier.html") == "entrant"
    assert provenance_de(r"C:\projet\input\donnees.csv") == "entrant"


def test_tout_le_reste_est_PRODUIT_et_le_sens_de_l_erreur_est_voulu() -> None:
    """Ce qui n'est pas reconnu comme entrant reste `produit`, donc COMPTE dans la couverture.
    Mieux vaut exiger à tort la couverture d'un fichier reçu que de dispenser à tort celle d'un
    livrable : la première erreur se voit et se déclare, la seconde produit un ratio flatteur."""
    assert provenance_de("frontend/src/pages/Accueil.tsx") == "produit"
    assert provenance_de("output/rapport.html") == "produit"
    assert provenance_de("inputs/donnees.csv") == "produit", "« inputs » n est pas « input »"


# --- Le cas réel : tout l'inventaire est entrant -----------------------------------------------
def test_quinze_ancres_d_ENTRANTS_ne_font_plus_un_ratio_de_1() -> None:
    """Le cas exact du 18/08 : 15 ancres de deux fichiers `input/*.html`, toutes exercées."""
    inventaire = [_element(f"ancre:{i}", "input/Client - Cahier V1.4.html") for i in range(15)]

    sortie = evaluer_surface("interface-statique", "interface", ".", inventaire,
                             {e.id for e in inventaire}, SEUIL, [])

    assert sortie.verdict == "NA", "« 15/15 ratio 1,0 PASS » etait le pire rapport possible"
    motif = " ".join(sortie.non_juge)
    assert "SANS OBJET" in motif
    assert "TOUS des entrants" in motif
    assert "plus trompeur qu un pan franchement non couvert" in motif


def test_les_entrants_ecartes_restent_NOMMES_au_rapport() -> None:
    """Les taire aurait remplacé un ratio faux par un silence. Ce qui a été lu se publie."""
    inventaire = [_element("ancre:1", "input/recu.html"), _element("ancre:2", "input/recu.html")]

    sortie = evaluer_surface("interface-statique", "interface", ".", inventaire, set(), SEUIL, [])

    assert sortie.surface["entrants_hors_ratio"] == ["ancre:1", "ancre:2"]


# --- Le cas mixte, qui est le cas courant -----------------------------------------------------
def test_le_ratio_ne_porte_que_sur_le_PRODUIT() -> None:
    """Deux entrants exercés ne rachètent pas deux éléments produits non exercés. Avant, le ratio
    était 2/4 = 50 % ; il est maintenant 0/2 = 0 %, et c'est le chiffre vrai."""
    inventaire = [
        _element("ancre:recu-1", "input/recu.html"),
        _element("ancre:recu-2", "input/recu.html"),
        _element("route:/accueil", "frontend/src/App.tsx"),
        _element("route:/detail", "frontend/src/App.tsx"),
    ]

    sortie = evaluer_surface("interface-statique", "interface", ".", inventaire,
                             {"ancre:recu-1", "ancre:recu-2"}, SEUIL, [])

    assert sortie.surface["inventorie"] == 2, "les entrants sortent du denominateur"
    assert sortie.surface["exerce"] == 0, "un entrant exerce ne compte pas au numerateur"
    assert sortie.surface["ratio"] == 0.0
    assert sortie.verdict == "FAIL"


def test_le_pan_DIT_combien_d_entrants_il_a_ecartes() -> None:
    """Un écart silencieux se lirait comme un périmètre complet."""
    inventaire = [
        _element("ancre:recu", "input/recu.html"),
        _element("route:/accueil", "frontend/src/App.tsx"),
    ]

    sortie = evaluer_surface("interface-statique", "interface", ".", inventaire,
                             {"route:/accueil"}, SEUIL, [])

    motif = " ".join(sortie.non_juge)
    assert "1 element(s) INVENTORIE(S) mais ENTRANT(S)" in motif
    assert "ancre:recu" in motif, "l element ecarte est NOMME, pas seulement compte"
    assert sortie.verdict == "PASS", "le seul element produit est exerce"


# --- Ce qui ne doit PAS avoir changé ----------------------------------------------------------
def test_un_projet_SANS_entrant_est_juge_exactement_comme_avant() -> None:
    """Garde anti-régression : la correction ne doit rien changer là où il n'y a pas d'entrant."""
    inventaire = [
        _element("route:/accueil", "frontend/src/App.tsx"),
        _element("route:/detail", "frontend/src/App.tsx"),
    ]

    sortie = evaluer_surface("interface-statique", "interface", ".", inventaire,
                             {"route:/accueil"}, SEUIL, [])

    assert sortie.surface["inventorie"] == 2
    assert sortie.surface["ratio"] == 0.5
    assert sortie.surface["entrants_hors_ratio"] == []
    assert sortie.verdict == "FAIL"


def test_un_adaptateur_qui_SAIT_pose_la_provenance_lui_meme() -> None:
    """La déduction par chemin est un défaut utile, pas une loi : un adaptateur qui connaît la
    nature de ce qu'il inventorie n'a pas à passer par le chemin."""
    inventaire = [_element("table:bronze.ventes", "backend/models.py", provenance="entrant")]

    sortie = evaluer_surface("data", "data", ".", inventaire, set(), SEUIL, [])

    assert sortie.verdict == "NA", "declare entrant malgre un chemin de produit"
