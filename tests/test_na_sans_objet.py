"""État NA — « sans objet » : un pan sans périmètre n'est pas un pan non couvert.

Décision humaine du 14/08 : « les pans qui n'ont pas de périmètre dans un projet doivent
ressortir en Non Applicable (NA) lors des tests, puisqu'il n'y a rien à tester ».

Le point délicat, et ce que ces tests protègent : **NA exige une preuve POSITIVE d'absence**.
Le framework tient depuis l'origine qu'un inventaire vide ne prouve rien — il prouve que
l'adaptateur n'a rien su énumérer. Si NA se déduisait d'un inventaire vide, la garde contre
l'absence silencieuse tomberait le jour même où on l'ajoute.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import batch, fichiers, front
from forge_tests.noyau import Element, evaluer_surface, rapport


# --- Le mécanisme -----------------------------------------------------------------------------
def test_inventaire_vide_SANS_preuve_reste_un_skip() -> None:
    """La garde historique tient : sans preuve d'absence, un inventaire vide est un SKIP."""
    sortie = evaluer_surface("a", "p", "/x", [], set(), 0.9, [])
    assert sortie.verdict == "SKIP"
    assert "inventaire VIDE" in sortie.non_juge[-1]


def test_inventaire_vide_AVEC_preuve_sort_en_na() -> None:
    sortie = evaluer_surface("a", "p", "/x", [], set(), 0.9, [], sans_objet="aucun dossier X")
    assert sortie.verdict == "NA"
    assert "SANS OBJET" in sortie.non_juge[-1]
    assert "aucun dossier X" in sortie.non_juge[-1]


def test_une_preuve_d_absence_ne_masque_jamais_un_inventaire_NON_vide() -> None:
    """Sens rouge du mécanisme : s'il y a de la surface, `sans_objet` est ignoré. Sinon un
    adaptateur mal réglé pourrait faire disparaître un pan qui a pourtant quelque chose."""
    inventaire = [Element("x:1", "p", "un élément", "src")]
    sortie = evaluer_surface("a", "p", "/x", inventaire, set(), 0.9, [], sans_objet="prétendu vide")
    assert sortie.verdict != "NA"


# --- L'effet sur le rapport --------------------------------------------------------------------
def _sortie(pan: str, verdict: str, motif: str):
    from forge_tests.noyau import SortieAdaptateur

    return SortieAdaptateur("a", pan, "/x", verdict, non_juge=[motif])


def test_un_pan_na_ne_rend_plus_le_rapport_partiel() -> None:
    """Le cœur de la demande : ne pas avoir de lot n'est pas un manque."""
    r = rapport([_sortie("batch", "NA", "batch : SANS OBJET — aucun module de lot")], ["batch"])
    assert r["pans_non_couverts"] == []
    assert r["verdict"] == "PASS"


def test_un_pan_na_reste_NOMME_au_rapport_avec_son_motif() -> None:
    """Un pan qui disparaîtrait laisserait croire que le sujet n'existe pas — interdit."""
    r = rapport([_sortie("batch", "NA", "batch : SANS OBJET — aucun module de lot")], ["batch"])
    assert r["pans_sans_objet"] == [
        {"pan": "batch", "motif": "batch : SANS OBJET — aucun module de lot"}
    ]


def test_un_pan_skip_rend_toujours_le_rapport_partiel() -> None:
    """Non-régression : NA ne doit pas contaminer le cas « je n'ai pas pu mesurer »."""
    r = rapport([_sortie("batch", "SKIP", "batch : suite non exécutée")], ["batch"])
    assert [e["pan"] for e in r["pans_non_couverts"]] == ["batch"]
    assert r["verdict"] == "PARTIEL"


def test_na_et_skip_cohabitent_sans_se_confondre() -> None:
    r = rapport(
        [_sortie("batch", "NA", "sans objet"), _sortie("api", "SKIP", "non mesurable")],
        ["batch", "api"],
    )
    assert [e["pan"] for e in r["pans_sans_objet"]] == ["batch"]
    assert [e["pan"] for e in r["pans_non_couverts"]] == ["api"]
    assert r["verdict"] == "PARTIEL"  # à cause d'api seulement


# --- Les preuves d'absence, adaptateur par adaptateur -------------------------------------------
def test_front_sans_objet_quand_le_projet_n_a_pas_de_frontend(tmp_path: Path) -> None:
    assert "aucun dossier" in (front.sans_objet(tmp_path) or "")


def test_front_a_un_objet_des_qu_un_frontend_existe(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    assert front.sans_objet(tmp_path) is None


def test_batch_sans_objet_quand_ni_module_ni_declencheur(tmp_path: Path) -> None:
    assert "aucun module de traitement par lot" in (batch.sans_objet(tmp_path) or "")


def test_batch_a_un_objet_des_qu_un_declencheur_existe(tmp_path: Path) -> None:
    """Un projet SANS module de lot mais AVEC un cron a bien quelque chose à dire : le cron
    pointe vers une cible, et si elle manque c'est un défaut — surtout pas un NA."""
    (tmp_path / "crontab").write_text("0 3 * * * python jobs/nuit.py\n", encoding="utf-8")
    assert batch.sans_objet(tmp_path) is None


def test_fichiers_sans_objet_quand_aucun_module_d_import(tmp_path: Path) -> None:
    assert "aucun module d import" in (fichiers.sans_objet(tmp_path) or "")
