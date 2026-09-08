"""TF-0841 — la route de la mire n'est pas un identifiant, et elle bloquait tous les livrables.

LE FAIT (lot Produit-61, retour du 05/09/2026). `FORGE_TESTS_LOGIN_PATH=/admin/connexion`, écrit
dans le `.env.forge-tests` que le README documente. Le garde-fou des jeux de données lit ce
fichier, classe le nom sur ses SEGMENTS (TF-0215), voit `LOGIN`, et fait entrer `/admin/connexion`
au corpus des valeurs interdites. Une clé de cas générée reprenait légitimement cette route :
`DonneeNonSynthetique .jeux[9].cle`. **Quatre audits sans cahier ni dashboard** — le même coût,
au mot près, que le défaut fondateur de TF-0215.

La règle de TF-0215 tenait : *ce qui NOMME sort du corpus, ce qui AUTHENTIFIE y reste.* Elle
n'avait simplement pas prévu qu'un nom porte les deux. Une route de mire NOMME : le produit la
publie lui-même, tout visiteur la lit, la connaître n'ouvre rien. Le segment de LOCALISATION
l'emporte donc sur le segment authentifiant.

Et la borne, sans laquelle ce serait une porte ouverte : quand la valeur est connue, elle doit
elle aussi ressembler à un emplacement. `FORGE_TESTS_LOGIN_PATH=hunter2` reste interdit —
c'est un identifiant sous un nom trompeur, et le renommer ne doit pas suffire à le faire sortir.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests.livrables import jeux
from forge_tests.livrables.jeux import _valeurs_de_configuration, configure_l_auditeur

ROUTE_DE_MIRE = "/admin/connexion"


@pytest.fixture()
def env_propre():
    memoire = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _projet(tmp_path: Path, contenu: str) -> Path:
    projet = tmp_path / "produit"
    projet.mkdir(parents=True)
    (projet / ".env.forge-tests").write_text(contenu, encoding="utf-8")
    return projet


# --- La règle nouvelle, dans les deux sens ------------------------------------------------------


@pytest.mark.parametrize(
    ("nom", "valeur"),
    [
        ("FORGE_TESTS_LOGIN_PATH", ROUTE_DE_MIRE),
        ("FORGE_TESTS_LOGIN_URL", "https://produit.exemple.test/connexion"),
        ("FORGE_TESTS_QUALIF_LOGIN_ROUTE", "/se-connecter"),
        ("FORGE_TESTS_AUTH_ENDPOINT", "/oauth/token"),
    ],
)
def test_un_nom_qui_LOCALISE_sort_du_corpus_meme_s_il_authentifie(nom: str, valeur: str) -> None:
    """Sens vert : ces valeurs désignent une adresse que le produit publie lui-même."""
    assert configure_l_auditeur(nom, valeur) is True


@pytest.mark.parametrize(
    ("nom", "valeur"),
    [
        # FIXTURE ROUGE de la borne : le nom localise, la valeur non — c'est un identifiant.
        ("FORGE_TESTS_LOGIN_PATH", "hunter2"),
        ("FORGE_TESTS_LOGIN_URL", "Sup3rMotDePasse"),
        # Et ce que TF-0222 avait décidé ne bouge pas : aucun segment localisant ici.
        ("FORGE_TESTS_QUALIF_STORAGE_STATE", "C:/secrets/storageState.json"),
        ("FORGE_TESTS_QUALIF_LOGIN", "compta-audit-2026"),
        ("FORGE_TESTS_QUALIF_PASSWORD", "/pourtant/ca/ressemble/a/un/chemin"),
    ],
)
def test_ce_qui_AUTHENTIFIE_vraiment_reste_au_corpus(nom: str, valeur: str) -> None:
    """Sens rouge : le nom seul ne suffit pas, la valeur doit tenir la promesse du nom."""
    assert configure_l_auditeur(nom, valeur) is False


def test_sans_la_valeur_le_nom_decide_seul() -> None:
    """Appel historique à un seul argument : la règle se lit alors sur les segments du nom."""
    assert configure_l_auditeur("FORGE_TESTS_LOGIN_PATH") is True
    assert configure_l_auditeur("FORGE_TESTS_QUALIF_LOGIN") is False


# --- Le cas constaté, de bout en bout -----------------------------------------------------------


def test_la_route_de_mire_declaree_n_entre_plus_au_corpus(tmp_path: Path, env_propre) -> None:
    """Le fait du 05/09 : ce `.env.forge-tests` rendait quatre livrables impossibles."""
    projet = _projet(
        tmp_path,
        f"FORGE_TESTS_LOGIN_PATH={ROUTE_DE_MIRE}\n"
        "FORGE_TESTS_QUALIF_PASSWORD=Sup3rMotDePasseDAudit\n",
    )

    interdites = _valeurs_de_configuration(projet)

    assert ROUTE_DE_MIRE not in interdites
    # Le sens qui compte : le MÊME fichier porte un mot de passe, et lui ne sort pas.
    assert "Sup3rMotDePasseDAudit" in interdites


def test_un_jeu_dont_une_cle_reprend_la_route_de_mire_est_desormais_ecrit(
    tmp_path: Path, env_propre
) -> None:
    """Le refus constaté : `DonneeNonSynthetique .jeux[9].cle`. Il ne se produit plus."""
    projet = _projet(tmp_path, f"FORGE_TESTS_LOGIN_PATH={ROUTE_DE_MIRE}\n")
    jeu = {"jeux": [{"cle": f"POST {ROUTE_DE_MIRE}", "valeur": "cas nominal"}]}

    jeux.verifier(jeu, projet)  # ne lève pas : c'est tout le contrôle


def test_le_meme_jeu_reste_refuse_si_la_valeur_est_un_identifiant(
    tmp_path: Path, env_propre
) -> None:
    """FIXTURE ROUGE de bout en bout : renommer un secret en `_PATH` ne le fait pas sortir."""
    projet = _projet(tmp_path, "FORGE_TESTS_LOGIN_PATH=Sup3rMotDePasseDAudit\n")
    jeu = {"jeux": [{"cle": "compte Sup3rMotDePasseDAudit", "valeur": "cas nominal"}]}

    with pytest.raises(jeux.DonneeNonSynthetique) as refus:
        jeux.verifier(jeu, projet)

    assert "configuration du projet audité" in str(refus.value)
