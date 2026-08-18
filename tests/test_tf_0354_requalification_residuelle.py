"""TF-0354 — les trois restes de la voie « proposition », et le verrou qui les tient fermés.

TF-0349 a fermé la voie en doctrine, au catalogue, au cahier et à l'oracle. Elle restait
ouverte à trois endroits, tous constatés le 18/08 : l'en-tête que le générateur ÉCRIT en tête
de chaque fichier de cas (« Un cas généré est une PROPOSITION » — le mot rouvert à chaque
lecture du code produit), le placeholder documenté `<dossier-proposition>`, et l'encart du
cahier qui nommait le fichier de déclaration pour UNE des trois issues R-40 seulement.

Le verrou porte sur ce que la forge PRODUIT, jamais sur ce qu'elle LIT : l'antériorité des
produits (`"statut": "proposition"`) reste acceptée — c'est la règle posée par TF-0349.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

NL = chr(10)

from forge_tests import adoption, generateur  # noqa: E402
from forge_tests.livrables import cahiers  # noqa: E402


def test_l_entete_ECRITE_dans_les_fichiers_de_cas_ne_dit_plus_proposition() -> None:
    """Le reste le plus visible : cet en-tête est relu par un humain à chaque cas généré."""
    assert "proposition" not in generateur.ENTETE.lower(), (
        "l'en-tête des cas générés rouvre la voie fermée par R-40 : un cas naît "
        "« à adopter et exécuter », état transitoire."
    )
    assert "adopter" in generateur.ENTETE.lower()


def test_l_entete_nomme_l_etat_de_naissance_ET_son_caractere_transitoire() -> None:
    """Requalifier n'est pas supprimer le mot : le lecteur doit savoir ce que le cas EST."""
    entete = generateur.ENTETE.lower()
    assert "transitoire" in entete
    assert "solde" in entete


def test_le_README_ne_documente_plus_le_placeholder_dossier_proposition() -> None:
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    assert "<dossier-proposition>" not in readme
    assert "<dossier-cas-derives>" in readme


def test_la_sequence_du_renommage_de_dossier_est_ECRITE_pas_presumee() -> None:
    """La convention de chemin `propositions/` survit ; ce qui est interdit, c'est le silence.

    Loi 3 : on s'écarte explicitement, jamais par omission — la séquence est déclarée au
    module qui porte le contrat.
    """
    doctrine = (RACINE / "forge_tests" / "adoption.py").read_text(encoding="utf-8")
    assert "TF-0354" in doctrine
    assert "propositions/" in doctrine and "casserait des appels" in doctrine


def test_l_encart_du_cahier_offre_les_TROIS_issues_ET_leurs_DEUX_fichiers() -> None:
    """Le défaut : le lecteur voyait le fichier de déclaration cité pour la seule adoption.

    Il pouvait en conclure que `non_testable` et « écarté » se déclarent ailleurs — ou nulle
    part. Ils se déclarent bien AILLEURS, et l'encart doit nommer où : R-40 (pilot) range les
    deux autres issues dans `forge/cas-ecartes.jsonl`, et l'oracle d'adoption du pilot renvoie
    vers ce sidecar tout écartement trouvé dans `cas-adoptes.jsonl`.
    """
    encart = cahiers._libelle_adoption(None)

    assert adoption.FICHIER in encart
    assert adoption.FICHIER_ECARTES in encart, "le sidecar de R-40 est nommé, pas deviné"
    assert "DEUX fichiers" in encart
    for marqueur in ("test", "non_testable", "champs_requis", "ecarte", "pourquoi"):
        assert marqueur in encart, f"issue non outillée dans l'encart : {marqueur}"


# --- La contradiction entre deux forges, trouvée en soldant TF-0354 -----------------------------
def test_le_sidecar_de_la_DOCTRINE_est_lu_sinon_bien_faire_est_puni(tmp_path) -> None:
    """Le défaut le plus coûteux des trois, et il n'était nommé nulle part.

    R-40 (pilot) prescrit `forge/cas-ecartes.jsonl` pour les deux autres issues, et
    `oracle-adoption-tests.mjs` (A2) renvoie vers ce sidecar tout écartement écrit dans
    `cas-adoptes.jsonl`. Ce module ne lisait QUE `cas-adoptes.jsonl` : un produit qui suivait
    la doctrine voyait ses déclarations invisibles ici, son solde ne descendait jamais, et le
    cahier lui répondait « reste-à-faire » pour avoir bien fait.
    """
    (tmp_path / "forge").mkdir()
    (tmp_path / adoption.FICHIER_ECARTES).write_text(
        NL.join([
            '{"cas": "T2-0481-1", "statut": "non_testable", '
            '"champs_requis": ["FORGE_TESTS_QUALIF_URL"]}',
            '{"cas": "F1-3025-2", "statut": "ecarte", "qui": "le commanditaire", '
            '"quand": "2026-08-18", "pourquoi": "hors perimetre"}',
        ]),
        encoding="utf-8",
    )

    declarations = adoption.charger(tmp_path)

    assert declarations["T2-0481-1"]["statut"] == adoption.NON_TESTABLE
    assert declarations["F1-3025-2"]["statut"] == adoption.ECARTE
    assert "le commanditaire" in declarations["F1-3025-2"]["motif"]


def test_le_vocabulaire_du_sidecar_est_TRADUIT_pas_refuse(tmp_path) -> None:
    """Le même objet porte deux vocabulaires selon le fichier : `ecarte_par`/`date`/`motif`
    ici, `qui`/`quand`/`pourquoi` là-bas. Refuser un écart parce qu'il emploie le mot de
    l'AUTRE outil aurait recréé la double vérité qu'on vient de fermer."""
    (tmp_path / "forge").mkdir()
    (tmp_path / adoption.FICHIER_ECARTES).write_text(
        '{"cas": "F1-1", "statut": "ecarte", "ecarte_par": "Sébastien", "date": "2026-08-18",'
        ' "motif": "remplacé par un contrôle amont"}\n',
        encoding="utf-8",
    )

    etat = adoption.charger(tmp_path)["F1-1"]

    assert etat["statut"] == adoption.ECARTE
    assert "Sébastien" in etat["motif"]


def test_l_anteriorite_reste_ACCEPTEE_aucun_produit_rattrape_en_masse(tmp_path) -> None:
    """Second sens : des produits ont écrit les trois formes dans `cas-adoptes.jsonl` avant le
    18/08. Les refuser d'un coup transformerait un solde nul en reste-à-faire chez eux."""
    (tmp_path / "forge").mkdir()
    (tmp_path / adoption.FICHIER).write_text(
        '{"cas": "T2-9", "non_testable": true, "champs_requis": ["FORGE_TESTS_API_URL"]}\n',
        encoding="utf-8",
    )

    assert adoption.charger(tmp_path)["T2-9"]["statut"] == adoption.NON_TESTABLE


def test_sur_un_cas_declare_DES_DEUX_COTES_la_doctrine_l_emporte(tmp_path) -> None:
    """Un produit en migration n'a pas à nettoyer l'ancien fichier avant que le nouveau compte."""
    (tmp_path / "forge").mkdir()
    (tmp_path / adoption.FICHIER).write_text(
        '{"cas": "F1-7", "non_testable": true, "champs_requis": ["ANCIEN"]}\n', encoding="utf-8"
    )
    (tmp_path / adoption.FICHIER_ECARTES).write_text(
        '{"cas": "F1-7", "statut": "ecarte", "qui": "Sébastien", "quand": "2026-08-18",'
        ' "pourquoi": "tranché depuis"}\n',
        encoding="utf-8",
    )

    assert adoption.charger(tmp_path)["F1-7"]["statut"] == adoption.ECARTE


def test_une_ADOPTION_fourvoyee_dans_le_sidecar_est_refusee_et_renvoyee(tmp_path) -> None:
    """Symétrique de la règle A2 du pilot : chaque fichier porte ce qui lui revient."""
    (tmp_path / "forge").mkdir()
    (tmp_path / adoption.FICHIER_ECARTES).write_text(
        '{"cas": "F1-4", "test": "e2e/10-nav.spec.ts"}\n', encoding="utf-8"
    )

    etat = adoption.charger(tmp_path)["F1-4"]

    assert etat["statut"] == adoption.REFUSE
    assert adoption.FICHIER in etat["motif"], "le refus dit OÙ la déclaration doit aller"
