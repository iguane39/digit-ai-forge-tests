"""TF-0215 (RT-1, lot COMPTA 20260814a) — le garde-fou refusait la configuration DOCUMENTÉE.

Fait mesuré sur le run `20260814-tests-fournisseur-a` (FastAPI + Jinja, ledger seq 6-7) : le produit
déclare `FORGE_TESTS_PRODUIT=Ventilation de facture Fournisseur-A` dans `<projet>/.env.forge-tests` —
l emplacement que le README documente. Ce fichier étant lu comme « configuration du projet
audité », la valeur entrait au corpus des valeurs interdites ; le champ `.produit` du jeu de
données, qui reprend ce même nom, était alors refusé : `DonneeNonSynthetique`, **exit 2, quatre
livrables non produits**. Le produit a dû contourner en passant la variable par l environnement
du processus.

Le garde-fou est bon et ne bouge pas : il a attrapé de vraies fuites (courriels réels, jetons,
empreintes). Le défaut est son PÉRIMÈTRE. La règle retenue, et ce que ces tests protègent dans
les DEUX sens :

    une variable `FORGE_TESTS_*` qui NOMME (PRODUIT, SOURCES, APP, BASE_URL, QUALIF_ROUTES,
    ORACLES…) configure l auditeur → hors du corpus interdit ;
    une variable `FORGE_TESTS_*` qui AUTHENTIFIE (PASSWORD, LOGIN, TOKEN, SECRET, KEY, CRED…)
    porte un compte de test RÉEL → elle y reste.

La surcorrection — exclure tout `FORGE_TESTS_*` — laisserait fuir le mot de passe du compte
d audit dans un cahier qui circule. C est l objet de la moitié des tests ci-dessous.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests.livrables import jeux
from forge_tests.livrables.jeux import _valeurs_de_configuration, configure_l_auditeur

# La configuration TELLE QUE LE README LA DOCUMENTE : `<projet>/.env.forge-tests`.
_ENV_DOCUMENTE = """\
FORGE_TESTS_PRODUIT=Ventilation de facture Fournisseur-A
FORGE_TESTS_BASE_URL=https://compta-qualif.exemple.test
FORGE_TESTS_SOURCES=C:\\dev\\compta-fournisseur-a
FORGE_TESTS_LOGIN=compta-audit-2026
FORGE_TESTS_PASSWORD=Sup3rMotDePasseDAudit
"""


@pytest.fixture()
def env_propre():
    """`charger_env` écrit dans `os.environ` sans le rendre : on le restaure intégralement.

    Sans cela, une variable chargée par un test contaminerait le corpus interdit du suivant —
    et le garde-fou testé ici serait jugé sur un environnement qu il n a pas vu.
    """
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    yield
    os.environ.clear()
    os.environ.update(memoire)


def _projet(tmp_path: Path, contenu: str = _ENV_DOCUMENTE) -> Path:
    projet = tmp_path / "compta-fournisseur-a"
    (projet / "app").mkdir(parents=True)
    (projet / ".env.forge-tests").write_text(contenu, encoding="utf-8")
    return projet


# --- La règle, énoncée puis vérifiée nom par nom -----------------------------------------------
@pytest.mark.parametrize(
    "nom",
    [
        "FORGE_TESTS_PRODUIT",
        "FORGE_TESTS_SOURCES",
        "FORGE_TESTS_APP",
        "FORGE_TESTS_BASE_URL",
        "FORGE_TESTS_API_URL",
        "FORGE_TESTS_QUALIF_URL",
        "FORGE_TESTS_QUALIF_ROUTES",
        "FORGE_TESTS_QUALIF_MARQUEURS",
        "FORGE_TESTS_QUALIF_CONNEXION",
        "FORGE_TESTS_EXIGENCES",
        # Piège de sous-chaîne : « oraCLEs » contient CLE. Le nom se lit par SEGMENTS.
        "FORGE_TESTS_ORACLES",
    ],
)
def test_ce_qui_NOMME_configure_l_auditeur(nom: str) -> None:
    assert configure_l_auditeur(nom) is True


@pytest.mark.parametrize(
    "nom",
    [
        "FORGE_TESTS_PASSWORD",
        "FORGE_TESTS_LOGIN",
        "FORGE_TESTS_LOGIN_PATH",
        "FORGE_TESTS_QUALIF_LOGIN",
        "FORGE_TESTS_QUALIF_PASSWORD",
        "FORGE_TESTS_API_KEY",
        "FORGE_TESTS_TOKEN",
        "FORGE_TESTS_SECRET",
        "FORGE_TESTS_CRED",
        "FORGE_TESTS_SESSION_COOKIE",
    ],
)
def test_ce_qui_AUTHENTIFIE_reste_un_secret(nom: str) -> None:
    """Sens rouge de la règle : ces noms portent un compte de test réel, ils restent interdits."""
    assert configure_l_auditeur(nom) is False


@pytest.mark.parametrize(
    "nom", ["DATABASE_URL", "STRIPE_SECRET_KEY", "PRODUIT", "SFR_API_KEY", ""]
)
def test_une_variable_du_PRODUIT_n_est_jamais_concernee(nom: str) -> None:
    """Le périmètre corrigé est celui de l AUDITEUR. Les variables de l audité ne bougent pas."""
    assert configure_l_auditeur(nom) is False


# --- Le corpus interdit, lu dans le `.env.forge-tests` documenté --------------------------------
def test_le_nom_du_produit_declare_n_entre_plus_au_corpus(tmp_path: Path, env_propre) -> None:
    interdites = _valeurs_de_configuration(_projet(tmp_path))
    assert "Ventilation de facture Fournisseur-A" not in interdites
    assert "https://compta-qualif.exemple.test" not in interdites


def test_le_compte_d_audit_declare_reste_au_corpus(tmp_path: Path, env_propre) -> None:
    """Le sens qui compte : ce fichier porte AUSSI le mot de passe, et lui ne sort pas."""
    interdites = _valeurs_de_configuration(_projet(tmp_path))
    assert "Sup3rMotDePasseDAudit" in interdites
    assert "compta-audit-2026" in interdites


def test_une_variable_du_projet_audite_reste_au_corpus(tmp_path: Path, env_propre) -> None:
    """Non-régression : le garde-fou d origine (fuites réelles) est intact."""
    projet = _projet(tmp_path, "DATABASE_URL=postgres://u:motdepasse@h/facturation\n")
    assert "postgres://u:motdepasse@h/facturation" in _valeurs_de_configuration(projet)


def test_la_regle_vaut_AUSSI_pour_l_environnement_du_processus(env_propre) -> None:
    """Le contournement appliqué par le produit (variable passée en env) n a plus lieu d être —
    et la variable qui authentifie reste collectée, quel que soit le canal."""
    os.environ["FORGE_TESTS_BASE_URL"] = "https://compta-qualif.exemple.test"
    os.environ["FORGE_TESTS_PASSWORD"] = "Sup3rMotDePasseDAudit"
    interdites = _valeurs_de_configuration(None)
    assert "https://compta-qualif.exemple.test" not in interdites
    assert "Sup3rMotDePasseDAudit" in interdites


def test_le_dashboard_masque_toujours_le_mot_de_passe_et_jamais_le_nom(
    tmp_path: Path, env_propre
) -> None:
    """Le second appelant du corpus (`dashboard._verifier_sans_secret`) suit la même règle."""
    secrets = _valeurs_de_configuration(_projet(tmp_path), secrets_seulement=True)
    assert "Sup3rMotDePasseDAudit" in secrets
    assert "Ventilation de facture Fournisseur-A" not in secrets


# --- Le cas réel, de bout en bout : les quatre livrables ---------------------------------------
def _rapport_minimal(projet: Path) -> dict:
    from forge_tests.noyau import Element, evaluer_surface, rapport

    inventaire = [
        Element("table:facture", "data", "table facture", str(projet / "app" / "modeles.py"))
    ]
    sortie = evaluer_surface(
        "data-sql", "data", str(projet), inventaire, {"table:facture"}, 0.9, []
    )
    return rapport([sortie], ["data"])


def test_le_jeu_de_donnees_du_produit_declare_passe_le_garde_fou(
    tmp_path: Path, env_propre
) -> None:
    """Reproduction directe du refus : le champ `.produit` reprend le nom lu au `.env`."""
    projet = _projet(tmp_path)
    jeu = jeux.construire([], "Ventilation de facture Fournisseur-A")

    jeux.verifier(jeu, projet)  # AVANT TF-0215 : DonneeNonSynthetique, exit 2

    assert jeu["produit"] == "Ventilation de facture Fournisseur-A"


def test_sans_l_exclusion_le_meme_jeu_serait_refuse(
    tmp_path: Path, env_propre, monkeypatch
) -> None:
    """ROUGE explicite : on neutralise la seule règle ajoutée, et le défaut REVIENT à l identique.

    C est ce test qui empêche le précédent d être vert pour une raison quelconque."""
    projet = _projet(tmp_path)
    monkeypatch.setattr(jeux, "configure_l_auditeur", lambda nom: False)
    jeu = jeux.construire([], "Ventilation de facture Fournisseur-A")

    with pytest.raises(jeux.DonneeNonSynthetique) as refus:
        jeux.verifier(jeu, projet)

    assert "produit" in str(refus.value)


def test_les_quatre_livrables_sont_produits_avec_la_configuration_documentee(
    tmp_path: Path, env_propre
) -> None:
    """Le coût constaté du défaut : « exit 2, 4 livrables non produits ». Ils le sont désormais.

    Le nom du produit n est pas passé à la main : il est LU dans `<projet>/.env.forge-tests`
    par `nom_du_produit`, c est-à-dire par le chemin exact du run réel.
    """
    from forge_tests.livrables import produire

    projet = _projet(tmp_path)

    chemins = produire(_rapport_minimal(projet), projet, tmp_path / "livrables")

    assert sorted(chemins) == ["dashboard", "fonctionnel", "jeu", "technique"]
    assert all(chemin.exists() for chemin in chemins.values())
    assert all(
        chemin.name.startswith("Ventilation de facture Fournisseur-A - ") for chemin in chemins.values()
    )
    # Et le livrable qui circule ne porte toujours pas le mot de passe du compte d audit.
    assert "Sup3rMotDePasseDAudit" not in chemins["dashboard"].read_text(encoding="utf-8")
    assert "Sup3rMotDePasseDAudit" not in chemins["jeu"].read_text(encoding="utf-8")
