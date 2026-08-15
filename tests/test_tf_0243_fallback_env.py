"""TF-0243 — le `.env` du DEPOT forge ne designe plus jamais l instance a auditer.

Fait mesure le 15/08/2026 (lot 20260815a, ledger seq 15). `charger_env` lisait
`<projet>/.env.forge-tests` PUIS, a defaut, le `.env` du depot forge-tests. Un produit neuf,
qui n avait pas encore de configuration a lui, a donc herite du `FORGE_TESTS_BASE_URL` laisse
la par l audit precedent : le pan `qualif` est alle parcourir l instance Railway d un AUTRE
produit et en a rapporte 9 constats `qualif:effet` + 2 constats d accessibilite sur `/login`,
`/recover-password` et `/admin/*` — routes inexistantes chez l audite — avec un seuil qualif
de 67 % calcule sur cette surface etrangere. Un cycle entier de boucle de fermeture perdu.

Ce que ces tests fixent :

  1. **le fallback ne fuit plus** — les cles qui DESIGNENT une instance (`CLES_INSTANCE`) sont
     ecartees du `.env` du depot. Le reste (compte de lecture, confort) continue d en venir :
     c est la configuration de l operateur, elle est legitime ;
  2. **le projet reste souverain** — la meme cle posee par le projet, elle, passe toujours ;
  3. **l absence d instance est un REFUS EXPLICITE**, pas un audit du mauvais site : sans
     BASE_URL, les pans qui en dependent concluent NA ou SKIP en NOMMANT le champ a fournir.
     C est exactement ce que les six echecs pytest pre-existants de TF-0217/TF-0222 mesuraient
     — ils tombaient parce que le `.env` du poste leur servait une instance reelle.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests import authentification

INSTANCE_ETRANGERE = "https://frontend-production-2193.up.railway.app"
INSTANCE_DU_PROJET = "https://compta-qualif.exemple.test"


@pytest.fixture()
def env_propre():
    """`charger_env` ecrit dans `os.environ` : sans restauration, un test verrait la config
    d un autre — et c est precisement le defaut que ce fichier mesure."""
    memoire = dict(os.environ)
    for nom in [n for n in os.environ if n.startswith("FORGE_TESTS_")]:
        del os.environ[nom]
    yield
    os.environ.clear()
    os.environ.update(memoire)


@pytest.fixture()
def depot(tmp_path: Path, monkeypatch) -> Path:
    """Un `.env` de DEPOT factice : le vrai depend du poste, donc il ne prouve rien."""
    chemin = tmp_path / "depot" / ".env"
    chemin.parent.mkdir(parents=True)
    chemin.write_text(
        "\n".join(
            [
                "# configuration laissee par l audit precedent",
                f"FORGE_TESTS_BASE_URL={INSTANCE_ETRANGERE}",
                "FORGE_TESTS_QUALIF_URL=https://qualif-d-un-autre.up.railway.app",
                "FORGE_TESTS_API_URL=https://backend-production-0a21.up.railway.app",
                "FORGE_TESTS_LOGIN=auditeur@exemple.test",
                "FORGE_TESTS_PASSWORD=secret-de-l-operateur",
                "FORGE_TESTS_SANS_EXECUTION=1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(authentification, "ENV_DEPOT", chemin)
    return chemin


# --- 1. Le sens ROUGE : le fallback ne fournit plus d instance ---------------------------------
def test_le_fallback_du_depot_ne_fournit_JAMAIS_une_instance(
    tmp_path: Path, env_propre, depot
) -> None:
    """Le defaut, reproduit a l identique : un projet SANS configuration a lui.

    Avant TF-0243, les trois URL du depot atterrissaient dans `os.environ` et l audit partait
    mesurer un produit qui n etait pas le sien."""
    projet = tmp_path / "produit-neuf"
    projet.mkdir()
    assert not (projet / authentification.ENV_PROJET).exists()

    authentification.charger_env(projet)

    for cle in authentification.CLES_INSTANCE:
        assert cle not in os.environ, f"{cle} a fui depuis le `.env` du depot"


def test_le_compte_de_l_operateur_continue_DE_VENIR_du_depot(
    tmp_path: Path, env_propre, depot
) -> None:
    """Sur-correction interdite : le `.env` du depot garde sa raison d etre.

    Le compte de lecture et les reglages de confort sont communs a tous les audits du poste —
    les ecarter aussi obligerait a recopier un mot de passe dans chaque projet, ce qui
    multiplierait les endroits ou un secret peut fuir."""
    projet = tmp_path / "produit-neuf"
    projet.mkdir()

    authentification.charger_env(projet)

    assert os.environ["FORGE_TESTS_LOGIN"] == "auditeur@exemple.test"
    assert os.environ["FORGE_TESTS_PASSWORD"] == "secret-de-l-operateur"
    assert os.environ["FORGE_TESTS_SANS_EXECUTION"] == "1"


def test_l_ecart_est_DECLARABLE_et_nomme_les_cles_ecartees(
    tmp_path: Path, env_propre, depot
) -> None:
    """Un silence serait un autre defaut : l operateur qui a rempli le mauvais fichier doit
    pouvoir apprendre pourquoi son URL n est pas prise."""
    projet = tmp_path / "produit-neuf"
    projet.mkdir()

    assert authentification.cles_instance_ignorees(projet) == list(
        authentification.CLES_INSTANCE
    )


# --- 2. Le sens VERT : le projet reste souverain -----------------------------------------------
def test_l_instance_DECLAREE_PAR_LE_PROJET_est_toujours_honoree(
    tmp_path: Path, env_propre, depot
) -> None:
    """La correction ne ferme pas l audit d instance servie : elle en deplace la source."""
    projet = tmp_path / "compta"
    projet.mkdir()
    (projet / authentification.ENV_PROJET).write_text(
        f"FORGE_TESTS_BASE_URL={INSTANCE_DU_PROJET}\n", encoding="utf-8"
    )

    authentification.charger_env(projet)

    assert os.environ["FORGE_TESTS_BASE_URL"] == INSTANCE_DU_PROJET
    # ... et le projet qui declare son instance n a plus rien d ecarte a apprendre.
    assert "FORGE_TESTS_BASE_URL" not in authentification.cles_instance_ignorees(projet)


def test_une_variable_posee_par_l_operateur_pour_CE_run_prime_toujours(
    tmp_path: Path, env_propre, depot
) -> None:
    """`charger_env` n a jamais surcharge l environnement, et ce n est pas ce lot qui le change :
    un `FORGE_TESTS_BASE_URL=… forge-tests …` en ligne de commande reste un geste explicite,
    scope a ce run, et il fait foi."""
    projet = tmp_path / "produit-neuf"
    projet.mkdir()
    os.environ["FORGE_TESTS_BASE_URL"] = INSTANCE_DU_PROJET

    authentification.charger_env(projet)

    assert os.environ["FORGE_TESTS_BASE_URL"] == INSTANCE_DU_PROJET
    assert authentification.cles_instance_ignorees(projet) == [
        "FORGE_TESTS_QUALIF_URL",
        "FORGE_TESTS_API_URL",
    ]


# --- 3. L effet mesure sur les pans : un REFUS, jamais un audit du mauvais site -----------------
def test_sans_instance_les_pans_de_rendu_REFUSENT_d_auditer(
    tmp_path: Path, env_propre, depot
) -> None:
    """Le fait qui compte pour le produit : la fuite ne se solde pas par un audit silencieux
    d une instance etrangere, mais par un verdict qui NOMME ce qu il manque."""
    from forge_tests.adaptateurs import accessibilite, visuel

    projet = tmp_path / "compta-sfr"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / "main.py").write_text("app = FastAPI()\n", encoding="utf-8")

    for sortie in (accessibilite.analyser(projet), visuel.analyser(projet)):
        assert sortie.verdict == "NA"
        assert "FORGE_TESTS_BASE_URL" in sortie.non_juge[-1]
    # Et rien n a ete parcouru : l instance etrangere n a meme pas ete resolue.
    assert accessibilite._base_servie(projet) == ""


def test_le_pan_qualif_reclame_son_URL_au_lieu_de_parcourir_celle_d_un_autre(
    tmp_path: Path, env_propre, depot
) -> None:
    """Le pan par lequel les 9 constats etrangers etaient entres."""
    from forge_tests import qualification
    from forge_tests.adaptateurs import qualif

    projet = tmp_path / "produit-neuf"
    projet.mkdir()
    qualification.oublier(projet)
    sortie = qualif.analyser(projet)
    requis = set(qualification.requis(projet, "acces"))
    qualification.oublier(projet)

    assert sortie.verdict == "SKIP"
    assert requis == {"FORGE_TESTS_QUALIF_URL"}
