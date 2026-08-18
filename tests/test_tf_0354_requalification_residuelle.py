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


def test_l_encart_du_cahier_offre_les_TROIS_issues_et_nomme_leur_fichier_unique() -> None:
    """Le défaut : le lecteur voyait le fichier de déclaration cité pour la seule adoption.

    Il pouvait en conclure que `non_testable` et « écarté » se déclarent ailleurs — ou nulle
    part. Ils vont dans le MÊME fichier ; l'encart doit le dire.
    """
    encart = cahiers._libelle_adoption(None)

    assert encart.count(adoption.FICHIER) == 1, "le fichier de déclaration se nomme une fois"
    assert "TOUTES LES TROIS" in encart
    assert "second sidecar" in encart, "l'absence d'un second fichier se dit, elle ne se devine pas"
    for marqueur in ("test", "non_testable", "champs_requis", "ecarte_par", "motif"):
        assert marqueur in encart, f"issue non outillée dans l'encart : {marqueur}"
