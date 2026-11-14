"""TF-2525 — les colonnes composites des synthèses par pan sortent de la facette, et le constat
d'identifiants affichés se scinde en deux gestes.

Deux restes de TF-2292 / TF-2294, mesurés le 14/11/2026 par l'agent du lot te :

  1. sur la page d'un audit réel du banc rouge, `oracle-filtres-tableau` levait 4 G12 bloquants :
     les colonnes « KO » (le compte, puis « dont N bloq. ») et « lecture » (une phrase, puis le
     libellé cité) des deux synthèses par pan mêlent plusieurs fragments de texte balisés, et sans
     `data-tf-valeur` le composant les prend en entier pour valeur de facette : une valeur par
     ligne ;
  2. `identifiants-affiches-dans-le-texte-servi` portait deux gestes de destinataires différents :
     retirer le couple de la page (le développeur) et tenir le mot de passe pour exposé, donc le
     renouveler (l'utilisateur, seul à tenir le compte). La règle du destinataire (TF-2294) veut
     une classe par destinataire.

Sens prouvés, chacun avec sa fixture :
  - ROUGE avant correction — G12 sur « KO » et « lecture » ; un constat, un destinataire ;
  - VERT — les deux colonnes portent `data-filter-col="off"` et un motif, l'oracle ne lève plus
    G12 ; deux constats, `manuelle_dev` pour le retrait et `manuelle_utilisateur` pour la rotation ;
  - CONTRE-ÉPREUVES — une colonne simple reste dans la facette ; sur hôte local ou page
    générique, aucun des deux constats n'apparaît.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from forge_tests import actions, classes
from forge_tests.actions import classifier
from forge_tests.adaptateurs import qualif
from forge_tests.livrables import dashboard as dash

RACINE = Path(__file__).resolve().parent.parent
ORACLE = Path.home() / ".claude" / "skills" / "quality-oracles" / "scripts" / (
    "oracle-filtres-tableau.mjs"
)


def _page_d_un_audit_avec_bloquants() -> str:
    """Dix chapitres dont chaque constat est BLOQUANT : la colonne « KO » est alors composite
    (le compte puis « dont N bloq. »), comme sur la page d'un audit réel du banc rouge."""
    spec = importlib.util.spec_from_file_location(
        "preuve_socle_2525", RACINE / "recette" / "preuve_dashboard_socle.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chapitres = []
    for i in range(10):
        chapitre = copy.deepcopy(module.CHAPITRES[0])
        chapitre.update(code=f"F{i + 1}", titre=f"Parcours {i + 1}", pans=[f"pan{i}"])
        for sous in chapitre["sous_chapitres"]:
            for element in sous["elements"]:
                element["severite"] = "bloquant"
        chapitres.append(chapitre)
    return dash.construire(copy.deepcopy(module.RAPPORT), module.CONTEXTE, chapitres)


@pytest.fixture(scope="module")
def page() -> str:
    return _page_d_un_audit_avec_bloquants()


def _regles_de_l_oracle(html: str, tmp_path: Path) -> list[str]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover — dépend du poste
        pytest.skip("node absent du poste")
    fichier = tmp_path / "page.html"
    fichier.write_text(html, encoding="utf-8")
    resultat = subprocess.run(
        [node, str(ORACLE), str(fichier)], capture_output=True, text=True, encoding="utf-8"
    )
    return [f["regle"] for f in json.loads(resultat.stdout)["findings"]]


# --- 1. Les synthèses par pan -------------------------------------------------------------------
def test_les_colonnes_ko_et_lecture_des_syntheses_sortent_de_la_facette_avec_leur_motif(
    page: str,
) -> None:
    """Fixture verte, sans l'oracle du poste : les deux tables de synthèse (Synthèse, en-tête
    des onglets de famille) déclarent la sortie de « KO » et de « lecture », motivée."""
    en_tete = re.compile(r"<th\b([^>]*)>(KO|lecture)</th>")
    trouves = [(texte, attributs) for attributs, texte in en_tete.findall(page)]

    assert sorted(t for t, _ in trouves) == ["KO", "KO", "lecture", "lecture"]
    for texte, attributs in trouves:
        assert 'data-filter-col="off"' in attributs, texte
        assert re.search(r'data-filter-reason="[^"]{10,}"', attributs), texte


@pytest.mark.skipif(not ORACLE.exists(), reason="quality-oracles absent du poste")
def test_oracle_filtres_tableau_ne_rend_aucun_G12_sur_la_page_d_un_audit_avec_bloquants(
    page: str, tmp_path: Path
) -> None:
    """Fixture verte : 4 G12 bloquants avant (KO ×2, lecture ×2), 0 après."""
    assert "G12" not in _regles_de_l_oracle(page, tmp_path)


@pytest.mark.skipif(not ORACLE.exists(), reason="quality-oracles absent du poste")
def test_une_colonne_composite_rend_G12_tant_qu_elle_reste_dans_la_facette(tmp_path: Path) -> None:
    """Fixture rouge, puis remède joué : la colonne « KO » (compte + « dont N bloq. ») lève G12
    sans déclaration ; avec `colonnes_hors_facette`, la même table n'en lève plus. Prouve que le
    test précédent n'est pas vide."""
    lignes = [[f"c{i}", f'{i % 3} <span class="discret">dont 1 bloq.</span>'] for i in range(10)]

    sans = dash._tableau(["chapitre", "KO"], lignes, outille_force=True, identifiant="t")
    avec = dash._tableau(
        ["chapitre", "KO"], lignes, outille_force=True, identifiant="t",
        colonnes_hors_facette={"KO": "compte suivi de son détail : le tri suffit"},
    )

    assert "G12" in _regles_de_l_oracle(sans, tmp_path)
    assert "G12" not in _regles_de_l_oracle(avec, tmp_path)


def test_les_autres_colonnes_des_syntheses_restent_dans_la_facette(page: str) -> None:
    """Contre-épreuve : la sortie ne s'étend pas aux colonnes qui regroupent (famille, éléments,
    passés, non joués, non testables, résultat) — la facette y reste utile."""
    for libelle in ("famille", "éléments", "non joués", "non testables"):
        attributs = re.findall(rf"<th\b([^>]*)>{libelle}</th>", page)
        assert attributs, libelle
        assert not any('data-filter-col="off"' in a for a in attributs), libelle


# --- 2. Le constat d'identifiants affichés, un geste par destinataire ---------------------------
_CORPS_COUPLE_AFFICHE = (
    "<h1>Connexion</h1>"
    "<p>Essayez la démo — Identifiant : demo@exemple.com / Mot de passe : Demo1234</p>"
    '<form><input type="text" name="login"><input type="password" name="mdp"></form>'
)
_CORPS_GENERIQUE = (
    "<h1>Connexion</h1><form>"
    '<label for="login">Identifiant :</label><input id="login" type="text">'
    '<label for="mdp">Mot de passe :</label><input id="mdp" type="password"></form>'
)


def _releve(corps: str) -> list[dict]:
    return [{
        "route": "/connexion", "statut": 200, "url_finale": "", "problemes": [],
        "affordances": [], "corps": corps, "console": [], "role": "",
    }]


def _conclure(tmp_path: Path, base: str, corps: str):
    config = {"base": base, "marqueurs": {}, "storage_state": "", "bearer": ""}
    return qualif.conclure(tmp_path, config, _releve(corps), [], None, None)


def _action(finding) -> dict:
    return classifier([
        {"classe": finding.classe, "id": finding.id, "pan": "qualif", "message": finding.message}
    ])[0]


def test_le_couple_affiche_donne_deux_constats_un_par_destinataire(tmp_path: Path) -> None:
    sortie = _conclure(tmp_path, "https://produit.exemple.test", _CORPS_COUPLE_AFFICHE)

    retrait = [f for f in sortie.findings if f.classe == classes.IDENTIFIANTS_AFFICHES]
    rotation = [
        f for f in sortie.findings if f.classe == classes.IDENTIFIANTS_AFFICHES_A_RENOUVELER
    ]
    assert len(retrait) == 1 and len(rotation) == 1
    assert retrait[0].id != rotation[0].id

    assert _action(retrait[0])["categorie"] == "manuelle_dev"
    assert _action(retrait[0])["etape_cible"] == "development"
    geste = _action(rotation[0])
    assert geste["categorie"] == "manuelle_utilisateur"
    assert geste["etape_cible"] == "mep-config"
    assert "renouveler" in geste["attendu"]


def test_le_geste_du_developpeur_ne_porte_plus_celui_de_l_utilisateur(tmp_path: Path) -> None:
    """Rouge avant : la règle unique disait aussi « tenir ce mot de passe pour exposé »."""
    gabarit = actions._REGLES[classes.IDENTIFIANTS_AFFICHES][2]

    assert "retirer" in gabarit
    assert "exposé" not in gabarit and "compte réel" not in gabarit


def test_le_constat_de_rotation_ne_republie_pas_le_mot_de_passe(tmp_path: Path) -> None:
    sortie = _conclure(tmp_path, "https://produit.exemple.test", _CORPS_COUPLE_AFFICHE)

    rotation = next(
        f for f in sortie.findings if f.classe == classes.IDENTIFIANTS_AFFICHES_A_RENOUVELER
    )
    assert "Demo1234" not in rotation.message
    assert rotation.severite == "signale"


def test_le_retrait_reste_le_seul_bloquant_du_couple(tmp_path: Path) -> None:
    sortie = _conclure(tmp_path, "https://produit.exemple.test", _CORPS_COUPLE_AFFICHE)

    bloquants = [f.classe for f in sortie.findings if f.severite == "bloquant"
                 and f.classe in (classes.IDENTIFIANTS_AFFICHES,
                                  classes.IDENTIFIANTS_AFFICHES_A_RENOUVELER)]
    assert bloquants == [classes.IDENTIFIANTS_AFFICHES]


@pytest.mark.parametrize(
    ("base", "corps"),
    [("http://127.0.0.1:8091", _CORPS_COUPLE_AFFICHE),
     ("https://produit.exemple.test", _CORPS_GENERIQUE)],
    ids=["hote-local", "page-generique"],
)
def test_ni_hote_local_ni_page_generique_ne_donnent_l_un_ou_l_autre(
    tmp_path: Path, base: str, corps: str
) -> None:
    sortie = _conclure(tmp_path, base, corps)

    assert not [
        f for f in sortie.findings
        if f.classe in (classes.IDENTIFIANTS_AFFICHES, classes.IDENTIFIANTS_AFFICHES_A_RENOUVELER)
    ]


def test_la_classe_nouvelle_a_sa_regle_et_n_est_pas_un_defaut_d_auditeur() -> None:
    assert classes.IDENTIFIANTS_AFFICHES_A_RENOUVELER in classes.CLASSES
    action = classifier([
        {"classe": classes.IDENTIFIANTS_AFFICHES_A_RENOUVELER, "id": "r", "pan": "qualif",
         "message": "m"}
    ])[0]

    assert "DÉFAUT D'AUDITEUR" not in action["attendu"]
    assert action["categorie"] == "manuelle_utilisateur"
