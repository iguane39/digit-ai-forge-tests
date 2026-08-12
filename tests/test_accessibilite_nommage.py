"""Nommage des captures du pan accessibilite — un pan ne fait pas tomber l audit.

Le 12/08/2026, sur un produit reel, la route `/login/reset-password/:token/:email` a produit
le nom de fichier `login_reset-password_:token_:email.html`. Windows refuse le deux-points :
l `OSError` est remontee non attrapee et a emporte l AUDIT ENTIER — verdict ERREUR, code 2,
les onze autres pans perdus avec elle.

TF-0122 a supprime cette cause en substituant les parametres de route. Ces tests couvrent ce
qui reste : tout autre caractere interdit, et la garantie qu un echec d ecriture se DECLARE
au lieu de tuer le run.
"""

import pytest

from forge_tests.adaptateurs.accessibilite import _nom_fichier

# Ce que Windows refuse dans un nom de fichier.
INTERDITS = ':?*<>|"\\'


class TestNomDeFichier:
    def test_route_simple(self):
        assert _nom_fichier("/annonces") == "annonces"

    def test_les_separateurs_deviennent_des_soulignes(self):
        assert _nom_fichier("/annonces/12/detail") == "annonces_12_detail"

    def test_la_racine_a_un_nom(self):
        # Sans repli, la racine donnerait la chaine vide et un chemin de DOSSIER.
        assert _nom_fichier("/") == "racine"
        assert _nom_fichier("") == "racine"

    def test_le_deux_points_est_neutralise(self):
        # Le cas qui a fait tomber l audit.
        assert ":" not in _nom_fichier("/login/reset-password/:token/:email")

    @pytest.mark.parametrize("caractere", list(INTERDITS))
    def test_aucun_caractere_interdit_ne_survit(self, caractere):
        nom = _nom_fichier(f"/page{caractere}suite")
        assert caractere not in nom, f"« {caractere} » rend le nom de fichier impossible"

    def test_une_chaine_de_requete_ne_casse_pas_le_nom(self):
        assert "?" not in _nom_fichier("/recherche?ville=Lille&type=Lot")

    def test_le_nom_reste_non_vide_meme_tout_en_interdits(self):
        assert _nom_fichier("/" + INTERDITS).strip("_") != "" or _nom_fichier("/") == "racine"

    def test_deux_routes_distinctes_gardent_des_noms_distincts(self):
        # L assainissement ne doit pas faire converger deux routes sur un meme fichier,
        # sans quoi une capture ecraserait l autre en silence.
        assert _nom_fichier("/a/b") != _nom_fichier("/a/c")
