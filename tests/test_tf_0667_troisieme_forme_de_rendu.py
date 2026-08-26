"""TF-0667 — « sans objet » est plus grave que « non couvert ».

LE FAIT (lot Produit-02 20260826h, 26/08/2026). Cinq pans qui regardent une page rendue
— visuel, accessibilite, contraste, clavier, plancher — ont ete declares SANS OBJET sur un
projet de **203 fichiers HTML**, au motif litteral « ce projet ne rend aucune page ».

LA CONTRADICTION ETAIT INTERNE AU MEME RAPPORT : le pan i18n y annoncait 203 elements
inventories, ratio 1.0, lus dans ce meme dossier via une cle que le produit declarait deja. Deux
pans du meme audit en desaccord sur l existence des pages du produit, et un seul avait raison.

LE DETECTEUR NE CONNAISSAIT QUE TROIS SIGNAUX — un dossier `frontend/`, une instance servie, des
routes declarees — qu un SITE STATIQUE GENERE ne presente JAMAIS, quelle que soit sa taille.

CONSEQUENCE MESUREE : le verdict affichait une couverture d interface de 100 % pendant que TOUT
CE QUI POURRAIT VOIR UNE PAGE ETAIT ETEINT. C est ce trou qui a laisse passer un surtitre
identique repete sur la meme page — visible de n importe quel oeil, invisible de toute la chaine.

POINT DE DOCTRINE. Un pan NON COUVERT est un trou qui demande a etre comble et qui FIGURE au
verdict. Un pan SANS OBJET est un trou DECLARE INEXISTANT, qui disparait du raisonnement de qui
lit le rapport. Quand le motif d un sans-objet est une INFERENCE et non un fait declare par le
produit, il doit au minimum etre FALSIFIABLE AU RAPPORT.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests.adaptateurs import accessibilite


@pytest.fixture()
def projet(tmp_path: Path) -> Path:
    """Un projet qui MONTRE du code — sans quoi le detecteur rend SKIP, pas sans-objet."""
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    return tmp_path


def test_un_projet_sans_aucune_page_reste_SANS_OBJET(projet: Path):
    """La borne : le correctif ne doit pas faire disparaitre le sans-objet la ou il est JUSTE."""
    assert accessibilite.sans_objet(projet) is not None


def test_un_repertoire_de_HTML_GENERE_n_est_PLUS_declare_sans_page(projet: Path):
    """203 fichiers HTML ne sont pas « aucune page ». C est le cas fondateur."""
    site = projet / "site"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    assert accessibilite.sans_objet(projet) is None


def test_le_dossier_DECLARE_par_le_produit_prime_sur_les_emplacements_usuels(
        projet: Path, monkeypatch: pytest.MonkeyPatch):
    """On ne devine pas : la cle que le produit declare passe en premier.

    C est le remede minimal demande par le retour — faire converger la detection de « ce produit
    rend des pages » vers UNE SEULE SOURCE, celle que le produit declare.
    """
    genere = projet / "www-construit"
    genere.mkdir()
    (genere / "a.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_BUILD", "www-construit")
    assert accessibilite.sans_objet(projet) is None


def test_BORNE_un_dossier_construit_VIDE_ne_fait_pas_croire_a_des_pages(projet: Path):
    """Un dossier vide ne prouve pas qu il y a quelque chose a rendre : il prouve qu on n a rien
    trouve. Le sans-objet reste — sinon le correctif remplacerait un trou par un autre."""
    (projet / "site").mkdir()
    assert accessibilite.sans_objet(projet) is not None


def test_le_motif_du_sans_objet_est_FALSIFIABLE_au_rapport(projet: Path):
    """SANS OBJET est plus grave que NON COUVERT : un trou declare inexistant disparait du
    raisonnement. Le motif doit donc porter DE QUOI LE RENVERSER — ici, les emplacements
    consultes et la cle a declarer. Un simple decompte l aurait retourne."""
    motif = accessibilite.sans_objet(projet) or ""
    assert "FORGE_TESTS_I18N_BUILD" in motif
    assert "falsifiable" in motif.lower()
    assert ".html" in motif


def test_la_cle_declaree_en_chemin_ABSOLU_est_honoree(projet: Path, tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch):
    """Un build peut vivre hors du depot ; le refuser forcerait a recopier des pages."""
    ailleurs = tmp_path / "hors-depot"
    ailleurs.mkdir()
    (ailleurs / "p.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_BUILD", str(ailleurs))
    assert accessibilite.sans_objet(projet) is None


def test_BORNE_un_projet_SANS_code_visible_reste_un_SKIP_et_non_un_sans_objet(tmp_path: Path):
    """Un dossier vide — cible mal designee, sources ailleurs — ne prouve pas qu il n y a rien a
    rendre. Cette borne existait avant TF-0667 ; le correctif ne doit pas l avoir emportee."""
    assert accessibilite.sans_objet(tmp_path) is None
    assert not os.listdir(tmp_path)
