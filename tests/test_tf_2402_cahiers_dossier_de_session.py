"""TF-2402 — le dossier de session de l'opérateur n'est pas une valeur de configuration du projet.

Fait remonté par l'agent du lot FT le 10/11/2026 : dans un arbre de travail posé sous
`%USERPROFILE%`, la section `cahiers` de la recette levait `DonneeNonSynthetique`. Le nom
`USERPROFILE` contient le segment `USER` du cercle large du garde-fou ; sa valeur
(`C:\\Users\\<compte>`) est le préfixe de chaque chemin absolu du projet audité, donc de chaque
identifiant de finding qui en porte un (`securite:sast:C:\\Users\\…\\recherche.py:13`), donc du jeu
de données dérivé du rapport.

Sens prouvés :
  - ROUGE  — sur l'état de départ, un jeu dont un identifiant porte un chemin sous `USERPROFILE`
             est refusé comme « donnée de configuration du projet audité » ;
  - VERT   — il passe, et le jeu produit par `construire` à partir d'un tel rapport passe aussi ;
  - CONTRE-ÉPREUVES — une variable voisine posée par un projet, et `USERNAME`, restent dans le
             corpus interdit : la liste des variables de session est fermée.
"""

from __future__ import annotations

import pytest

from forge_tests.livrables import jeux

PROFIL = "C:\\Users\\operateur-fictif"
CHEMIN_SOUS_LE_PROFIL = (
    PROFIL + "\\AppData\\Local\\Temp\\arbre-de-travail\\fixtures\\banc-rouge\\backend\\app\\r.py:13"
)


@pytest.fixture(autouse=True)
def _environnement_isole(monkeypatch: pytest.MonkeyPatch):
    """Les trois variables du test sont posées ici : le poste qui le joue ne change pas le sens."""
    for nom in ("USERPROFILE", "USERNAME", "ZZ_APP_USERPROFILE_TOKEN"):
        monkeypatch.delenv(nom, raising=False)


def _chapitres() -> list[dict]:
    return [
        {
            "code": "T7", "famille": "technique",
            "sous_chapitres": [
                {
                    "libelle": "securite",
                    "elements": [{"id": f"securite:sast:{CHEMIN_SOUS_LE_PROFIL}"}],
                }
            ],
        }
    ]


def test_rouge_un_chemin_sous_userprofile_n_est_pas_une_fuite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USERPROFILE", PROFIL)

    jeux.verifier({"a": f"securite:sast:{CHEMIN_SOUS_LE_PROFIL}"}, None)  # ne lève pas


def test_vert_le_jeu_derive_d_un_rapport_sous_le_profil_passe_le_garde_fou(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USERPROFILE", PROFIL)

    jeu = jeux.construire(_chapitres(), "Produit")

    # Sans ces lignes, le test pourrait passer sans que le chemin soit entré dans le jeu : il y
    # entre par `porte_sur` et par la clé de `jeux_par_cas` (mesuré le 12/11/2026).
    assert jeu["jeux"][0]["porte_sur"] == [f"securite:sast:{CHEMIN_SOUS_LE_PROFIL}"]
    assert f"securite:sast:{CHEMIN_SOUS_LE_PROFIL}" in jeu["jeux_par_cas"]
    jeux.verifier(jeu, None)  # ne lève pas


def test_contre_epreuve_une_variable_voisine_d_un_projet_reste_interdite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La liste est FERMÉE : seule la variable posée par le système sort du corpus."""
    monkeypatch.setenv("ZZ_APP_USERPROFILE_TOKEN", "jeton-de-production-a-ne-pas-recopier")

    with pytest.raises(jeux.DonneeNonSynthetique):
        jeux.verifier({"a": "extrait : jeton-de-production-a-ne-pas-recopier"}, None)


def test_contre_epreuve_username_reste_dans_le_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un identifiant de personne qui s'écrirait dans un jeu est une fuite."""
    monkeypatch.setenv("USERNAME", "jean.dupont-reel")

    with pytest.raises(jeux.DonneeNonSynthetique):
        jeux.verifier({"a": "auteur : jean.dupont-reel"}, None)


def test_contre_epreuve_le_profil_nu_n_ouvre_pas_la_porte_aux_autres_valeurs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exempter USERPROFILE ne désarme pas le garde-fou : un secret dans le même jeu est refusé."""
    monkeypatch.setenv("USERPROFILE", PROFIL)

    with pytest.raises(jeux.DonneeNonSynthetique):
        jeux.verifier({"a": f"{CHEMIN_SOUS_LE_PROFIL} sk-live-0123456789abcdefghij"}, None)
