"""TF-0349 — un cas dérivé se solde, ou le cahier porte un reste-à-faire (R-40).

Fait mesuré le 17/08/2026, sur pièces et sur des produits réels : les « Cahiers de tests »
livrés se déclaraient eux-mêmes PROPOSITIONS et sortaient avec **971 cas dérivés pour 0 adopté**
(bourse-aux-vacants, 20260817b), **680 pour 0** (COMPTA, 20260814b), **176** (Approval2). Des
contrôles jamais joués, livrés comme s'ils attestaient une couverture. La règle R-40 du pilot
ferme cette voie : « proposition » n'est plus un état terminal.

Ce que ces tests tiennent, DANS LES DEUX SENS — sans quoi la règle serait une décoration :

  - VERT : un cahier dont chacun des cas est soldé (adopté et exécuté · `non_testable` motivé
    avec ses `champs_requis` · écarté par une décision humaine nommée) publie un solde NUL et
    se déclare soldé ;
  - ROUGE : un seul cas laissé sans état suffit à ce que le cahier se DÉNONCE — solde non nul,
    reste-à-faire dit en tête, et le cas nommé « à adopter et exécuter, non soldé ». Les deux
    portes de sortie muettes (un `non_testable` sans champ, un écart sans nom) sont refusées et
    le cas reste AU solde : sinon la règle offrirait elle-même le moyen de la contourner.

Le solde est `dérivés − adoptés − non_testables − écartés`. Il ne dit rien de la QUALITÉ des
tests adoptés — c'est le rôle de la mutation, et cette limite est déclarée au registre de dette.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from forge_tests import adoption

# Un cas est titré `**T2-0481-1 — …**` dans le cahier. La référence est stable par construction
# (empreinte de l identifiant d élément), donc citable ici sans la coder en dur.
_REFERENCE = re.compile(r"^\*\*([A-Za-z0-9]+-\d{4}-\w+) — ", re.MULTILINE)


def _projet(tmp_path: Path) -> Path:
    projet = tmp_path / "produit"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "modeles.py").write_text("X = 1\n", encoding="utf-8")
    return projet


def _rapport(projet: Path) -> dict:
    """Un rapport RÉEL mais minimal : ces tests portent sur le solde, pas sur la mesure."""
    from forge_tests.noyau import Element, evaluer_surface, rapport

    inventaire = [
        Element("table:facture", "data", "table facture", str(projet / "app" / "modeles.py")),
        Element("contrainte:montant_positif", "data", "contrainte", str(projet / "app")),
    ]
    sortie = evaluer_surface(
        "data-sql", "data", str(projet), inventaire, {"table:facture"}, 0.9, []
    )
    return rapport([sortie], ["data"])


def _declarer(projet: Path, lignes: list[dict]) -> None:
    """Le PROJET déclare, jamais la forge (G-1) — elle lit ce fichier en lecture seule."""
    dossier = projet / "forge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "cas-adoptes.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes), encoding="utf-8"
    )


def _cahiers(projet: Path, depot: Path) -> tuple[str, list[str]]:
    """(texte des deux cahiers, références des cas dérivés) — production réelle, hors projet."""
    from forge_tests.livrables import produire

    chemins = produire(_rapport(projet), projet, depot)
    texte = "\n".join(
        chemins[famille].read_text(encoding="utf-8") for famille in ("fonctionnel", "technique")
    )
    return texte, _REFERENCE.findall(texte)


# --- L état de naissance : « a_adopter », plus jamais « proposition » --------------------------
def test_un_cas_non_declare_nait_a_adopter_et_le_mot_proposition_n_est_plus_produit() -> None:
    etat = adoption.statut({}, "T2-0481-1")

    assert etat["statut"] == adoption.A_ADOPTER == "a_adopter"
    assert "proposition" not in json.dumps(etat)


def test_l_anteriorite_proposition_est_LUE_comme_a_adopter_jamais_reecrite() -> None:
    """Les cahiers et fichiers d adoption d avant le 17/08 portent « proposition ». Les afficher
    en état inconnu ferait mentir un artefact que personne n a modifié."""
    assert adoption.est_a_adopter("proposition")
    assert adoption.est_a_adopter(adoption.A_ADOPTER)
    assert adoption.est_a_adopter(None)
    # Et l ancien vocabulaire pèse au solde exactement comme le neuf : il n est pas soldé.
    ancien = adoption.solde([{"statut": "proposition"}, {"statut": adoption.A_ADOPTER}])
    assert ancien["a_adopter"] == 2
    assert ancien["solde"] == 2
    # Sens rouge du même point : un état INCONNU ne se fait pas passer pour soldé.
    assert not adoption.est_a_adopter("adopte")
    assert adoption.solde([{"statut": "inconnu"}])["solde"] == 1


# --- Le solde, dans les deux sens -------------------------------------------------------------
def test_solde_nul_quand_les_trois_etats_couvrent_tous_les_cas() -> None:
    etats = [
        {"statut": adoption.ADOPTE},
        {"statut": adoption.NON_TESTABLE},
        {"statut": adoption.ECARTE},
    ]

    compte = adoption.solde(etats)

    assert compte == {
        "derives": 3,
        "adoptes": 1,
        "non_testables": 1,
        "ecartes": 1,
        "refuses": 0,
        "a_adopter": 0,
        "solde": 0,
    }
    assert "cahier SOLDÉ" in adoption.libelle_solde(compte)


def test_un_perimetre_sans_cas_derive_ne_se_declare_pas_solde() -> None:
    """Sinon le chapitre le plus VIDE du cahier récolterait le libellé le plus flatteur."""
    libelle = adoption.libelle_solde(adoption.solde([]))

    assert "rien à solder" in libelle
    assert "SOLDÉ" not in libelle


def test_un_seul_cas_sans_etat_rend_le_solde_non_nul_et_le_dit() -> None:
    """ROUGE : c est ce test qui empêche le précédent d être vert pour une raison quelconque."""
    compte = adoption.solde([{"statut": adoption.ADOPTE}, {"statut": adoption.A_ADOPTER}])

    assert compte["solde"] == 1
    libelle = adoption.libelle_solde(compte)
    assert "NON SOLDÉ(S)" in libelle
    assert "reste-à-faire" in libelle


def test_une_declaration_refusee_reste_AU_solde() -> None:
    """RT-13 : sinon le solde descendrait sur du vide — une déclaration invérifiable ne solde
    rien, et le motif du refus est rappelé au libellé."""
    compte = adoption.solde([{"statut": adoption.REFUSE}])

    assert compte["solde"] == 1
    assert "adoption(s) refusée(s)" in adoption.libelle_solde(compte)


def test_cumuler_recalcule_le_solde_au_lieu_d_additionner_les_restes() -> None:
    total = adoption.cumuler(
        [
            adoption.solde([{"statut": adoption.ADOPTE}, {"statut": adoption.A_ADOPTER}]),
            adoption.solde([{"statut": adoption.NON_TESTABLE}]),
        ]
    )

    assert total["derives"] == 3
    assert (total["adoptes"], total["non_testables"], total["ecartes"]) == (1, 1, 0)
    assert total["solde"] == 1


# --- Les deux portes de sortie muettes sont fermées -------------------------------------------
def test_non_testable_sans_champs_requis_est_refuse(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    _declarer(projet, [{"cas": "T2-0481-1", "non_testable": True}])

    etat = adoption.statut(adoption.charger(projet), "T2-0481-1")

    assert etat["statut"] == adoption.REFUSE
    assert "champs_requis" in etat["motif"]
    assert adoption.solde([etat])["solde"] == 1


def test_non_testable_motive_solde_le_cas_et_nomme_ce_qu_il_faut_fournir(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    _declarer(
        projet,
        [{"cas": "T2-0481-1", "non_testable": True, "champs_requis": ["FORGE_TESTS_QUALIF_URL"]}],
    )

    etat = adoption.statut(adoption.charger(projet), "T2-0481-1")

    assert etat["statut"] == adoption.NON_TESTABLE
    assert "FORGE_TESTS_QUALIF_URL" in etat["motif"]
    assert adoption.solde([etat])["solde"] == 0


def test_un_ecart_anonyme_ou_sans_motif_est_refuse(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    _declarer(
        projet,
        [
            {"cas": "T2-0481-1", "ecarte_par": "", "motif": "hors périmètre"},
            {"cas": "T2-0481-2", "ecarte_par": "Sébastien", "motif": ""},
        ],
    )

    charges = adoption.charger(projet)

    for ref in ("T2-0481-1", "T2-0481-2"):
        etat = adoption.statut(charges, ref)
        assert etat["statut"] == adoption.REFUSE
        assert "decision nommee" in etat["motif"]


def test_un_ecart_nomme_solde_le_cas_avec_qui_quand_pourquoi(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    _declarer(
        projet,
        [
            {
                "cas": "T2-0481-1",
                "ecarte_par": "Sébastien",
                "date": "2026-08-17",
                "motif": "pan retiré du périmètre MVP",
            }
        ],
    )

    etat = adoption.statut(adoption.charger(projet), "T2-0481-1")

    assert etat["statut"] == adoption.ECARTE
    assert "Sébastien" in etat["motif"] and "2026-08-17" in etat["motif"]
    assert "pan retiré du périmètre MVP" in etat["motif"]
    assert adoption.solde([etat])["solde"] == 0


# --- Le cahier PRODUIT porte son contrat et son solde -----------------------------------------
def test_le_cahier_porte_son_contrat_en_tete_et_ne_se_declare_plus_proposition(
    tmp_path: Path,
) -> None:
    projet = _projet(tmp_path)

    texte, references = _cahiers(projet, tmp_path / "depot")

    assert references, "aucun cas dérivé produit : le reste du test ne prouverait rien"
    # Les trois états, le solde attendu, et la phrase qui les rend opposables.
    assert "trois états, solde attendu ZÉRO (R-40)" in texte
    assert "adopté et exécuté" in texte
    assert "`non_testable` motivé" in texte
    assert "écarté par une décision humaine nommée" in texte
    assert "reste-à-faire" in texte
    # Le cahier ne se déclare plus lui-même une proposition (le défaut fondateur de TF-0349).
    assert "Ces cas sont des **PROPOSITIONS**" not in texte


def test_cahier_non_solde_se_denonce_lui_meme(tmp_path: Path) -> None:
    """ROUGE de bout en bout : aucun cas déclaré, donc aucun soldé — et le cahier le DIT."""
    projet = _projet(tmp_path)

    texte, references = _cahiers(projet, tmp_path / "depot")

    assert f"= {len(references)} cas NON SOLDÉ(S)" in texte
    assert "À ADOPTER ET EXÉCUTER — non soldé" in texte
    assert "cahier SOLDÉ" not in texte


def test_cahier_entierement_solde_publie_un_solde_nul(tmp_path: Path) -> None:
    """VERT de bout en bout : les trois états couvrent tous les cas dérivés, le solde tombe à 0.

    Les références ne sont pas devinées : elles sont relues du cahier du premier passage, ce que
    la stabilité des références rend possible (RT-13) — et c est ce même mécanisme qu un produit
    réel utilise pour déclarer ses adoptions.
    """
    projet = _projet(tmp_path)
    _, references = _cahiers(projet, tmp_path / "depot-1")
    test_du_projet = projet / "tests" / "test_facture.py"
    test_du_projet.parent.mkdir(parents=True, exist_ok=True)
    test_du_projet.write_text("# @cas " + " ".join(references) + "\n", encoding="utf-8")
    lignes: list[dict] = []
    for rang, ref in enumerate(references):
        if rang % 3 == 0:
            lignes.append({"cas": ref, "test": "tests/test_facture.py"})
        elif rang % 3 == 1:
            lignes.append(
                {"cas": ref, "non_testable": True, "champs_requis": ["FORGE_TESTS_QUALIF_URL"]}
            )
        else:
            lignes.append(
                {
                    "cas": ref,
                    "ecarte_par": "Sébastien",
                    "date": "2026-08-17",
                    "motif": "pan hors périmètre MVP",
                }
            )
    _declarer(projet, lignes)

    texte, secondes = _cahiers(projet, tmp_path / "depot-2")

    assert secondes == references, "les références de cas doivent rester stables d un run à l autre"
    assert "= 0 — cahier SOLDÉ" in texte
    assert "NON SOLDÉ" not in texte
    assert "À ADOPTER ET EXÉCUTER — non soldé" not in texte
    # Et chaque état soldé est NOMMÉ dans le cahier, avec ce qui le justifie.
    assert "**ADOPTÉ ET EXÉCUTÉ** par le projet" in texte
    assert "**NON TESTABLE ici, motivé**" in texte
    assert "**ÉCARTÉ par décision humaine nommée**" in texte
