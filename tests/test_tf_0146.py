"""TF-0146 — rapport exhaustif test-par-test : chaque cas exécuté porte son verdict motivé.

Le rapport agrégeait déjà la couverture de surface et la mutation PAR PAN — jamais le détail
CAS PAR CAS. Un pan à 92 % de couverture ne dit pas LEQUEL des 8 % restants a été essayé et a
échoué, lequel n a simplement jamais tourné, ni pourquoi. `noyau.resume_essais` ajoute cette
section (`essais`) au rapport, avec deux garde-fous :

  - **aucun verdict sans motif** : un essai NON PASSANT ou NON EXÉCUTÉ doit dire pourquoi —
    `resume_essais` REFUSE (`EssaiSansMotif`) plutôt que de publier un silence ;
  - **aucun ✓ sans oracle** : un essai PASSANT explicitement marqué `couvert=False` (mutation
    nulle ou ligne jamais exécutée sous mesure) est SIGNALÉ, jamais fondu dans les passants.

`forge_tests.junit` fournit le lecteur réel (JUnit XML, natif à pytest) qui alimentera un jour
un adaptateur — cette version l exerce sur des fragments XML construits à la main, la source de
vérité pour la traduction verdict + pourquoi.
"""

from __future__ import annotations

from forge_tests.junit import JunitIllisible, depuis_junit
from forge_tests.noyau import Essai, EssaiSansMotif, resume_essais


# --- Fixture du run fictif à 3 cas, telle que demandée par le mandat de campagne --------------
def _run_fictif() -> list[Essai]:
    return [
        Essai(id="test_creation_ok", pan="api", verdict="passant", couvert=True),
        Essai(
            id="test_montant_negatif_rejete", pan="api", verdict="non_passant",
            pourquoi="AssertionError: attendu 422, obtenu 500",
            details="Traceback (most recent call last): ...",
        ),
        Essai(
            id="test_export_pdf", pan="batch", verdict="non_execute",
            pourquoi="SKIPPED : dépendance LibreOffice absente du poste",
        ),
    ]


def test_run_fictif_produit_un_rapport_complet_verdict_par_cas() -> None:
    resultat = resume_essais(_run_fictif())
    par_id = {c["id"]: c for c in resultat["cas"]}
    assert par_id["test_creation_ok"]["verdict"] == "passant"
    assert par_id["test_montant_negatif_rejete"]["verdict"] == "non_passant"
    assert "422" in par_id["test_montant_negatif_rejete"]["pourquoi"]
    assert par_id["test_export_pdf"]["verdict"] == "non_execute"
    assert "LibreOffice" in par_id["test_export_pdf"]["pourquoi"]
    assert resultat["totaux"] == {"passant": 1, "non_passant": 1, "non_execute": 1}
    assert resultat["fourni"] is True


# --- « Aucun ✓ sans oracle » : un vert non couvert est SIGNALÉ, jamais silencieux -------------
def test_un_passant_couvert_n_est_pas_signale() -> None:
    resultat = resume_essais([Essai(id="t", pan="api", verdict="passant", couvert=True)])
    assert resultat["signales"] == []


def test_un_passant_non_couvert_est_signale_rouge() -> None:
    """RED : contrepartie du cas précédent — mutation nulle sur ce cas, jamais tu."""
    resultat = resume_essais([Essai(id="t", pan="back", verdict="passant", couvert=False)])
    assert len(resultat["signales"]) == 1
    assert resultat["signales"][0]["id"] == "t"
    assert "sans oracle" in resultat["signales"][0]["motif"]


def test_un_passant_de_couverture_inconnue_n_est_pas_signale() -> None:
    """`couvert=None` (inconnu) n est pas confondu avec `couvert=False` (mesuré et absent)."""
    resultat = resume_essais([Essai(id="t", pan="api", verdict="passant")])
    assert resultat["signales"] == []


# --- Aucun verdict sans motif : REFUS, pas un champ vide au rapport ----------------------------
def test_non_passant_sans_pourquoi_est_refuse() -> None:
    try:
        resume_essais([Essai(id="t", pan="api", verdict="non_passant")])
    except EssaiSansMotif as erreur:
        assert "t" in str(erreur)
    else:
        raise AssertionError("un non_passant sans pourquoi doit lever EssaiSansMotif")


def test_non_execute_sans_pourquoi_est_refuse() -> None:
    try:
        resume_essais([Essai(id="t", pan="batch", verdict="non_execute")])
    except EssaiSansMotif:
        pass
    else:
        raise AssertionError("un non_execute sans pourquoi doit lever EssaiSansMotif")


def test_passant_sans_pourquoi_est_accepte() -> None:
    """VERT — contrepartie : un passant n a rien à motiver, la règle ne sur-filtre pas."""
    resultat = resume_essais([Essai(id="t", pan="api", verdict="passant")])
    assert resultat["totaux"]["passant"] == 1


# --- Intégration au rapport du noyau : présent même sans essais fournis ------------------------
def test_rapport_sans_essais_declare_non_fourni_jamais_silencieux() -> None:
    from forge_tests.noyau import rapport

    rap = rapport([], ["api"], pour_couvrir={"api": "chemin"})
    assert rap["essais"] == {"cas": [], "totaux": {}, "signales": [], "fourni": False}


def test_rapport_avec_essais_porte_la_section_complete() -> None:
    from forge_tests.noyau import rapport

    rap = rapport([], ["api"], pour_couvrir={"api": "chemin"}, essais=_run_fictif())
    assert rap["essais"]["fourni"] is True
    assert rap["essais"]["totaux"]["non_passant"] == 1


# --- Lecteur JUnit réel : verdict + pourquoi extraits d un vrai fragment XML pytest ------------
_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="1" errors="0" skipped="1">
    <testcase classname="tests.test_api" name="test_creation_ok" time="0.01" />
    <testcase classname="tests.test_api" name="test_montant_negatif_rejete" time="0.02">
      <failure message="AssertionError: attendu 422, obtenu 500">Traceback...</failure>
    </testcase>
    <testcase classname="tests.test_batch" name="test_export_pdf" time="0.00">
      <skipped message="dépendance LibreOffice absente du poste" type="pytest.skip" />
    </testcase>
  </testsuite>
</testsuites>
"""


def test_depuis_junit_traduit_les_trois_verdicts() -> None:
    essais = depuis_junit(_JUNIT, pan="api")
    par_id = {e.id: e for e in essais}
    assert par_id["tests.test_api::test_creation_ok"].verdict == "passant"
    echec = par_id["tests.test_api::test_montant_negatif_rejete"]
    assert echec.verdict == "non_passant"
    assert "422" in echec.pourquoi
    saut = par_id["tests.test_batch::test_export_pdf"]
    assert saut.verdict == "non_execute"
    assert "LibreOffice" in saut.pourquoi
    # Le triplet lu se motive : `resume_essais` ne doit PAS refuser cette sortie du lecteur réel.
    resultat = resume_essais(essais)
    assert resultat["totaux"] == {"passant": 1, "non_passant": 1, "non_execute": 1}


def test_depuis_junit_refuse_un_xml_illisible() -> None:
    """RED : un texte qui n est pas du XML JUnit est un refus, jamais une liste vide muette."""
    try:
        depuis_junit("ceci n est pas du XML", pan="api")
    except JunitIllisible:
        pass
    else:
        raise AssertionError("un XML invalide doit lever JunitIllisible")


def test_depuis_junit_sur_une_suite_entierement_verte_ne_produit_aucun_signale() -> None:
    xml = """<testsuites><testsuite name="pytest" tests="1">
      <testcase classname="tests.test_x" name="test_ok" time="0.01" />
    </testsuite></testsuites>"""
    essais = depuis_junit(xml, pan="api")
    resultat = resume_essais(essais)
    assert resultat["totaux"] == {"passant": 1, "non_passant": 0, "non_execute": 0}
    assert resultat["signales"] == []
