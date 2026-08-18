"""TF-0370 — les contrôles de données cherchaient le vide, jamais le faux.

Le fait : la recette avait établi « 5 annonces sans commune » en testant `city-insee-code ===
null`. Or **11 annonces sur 1 249 portaient latitude=0 ET longitude=0** — le golfe de Guinée, au
large de l'Afrique, avec des adresses françaises réelles (anomalie 9873, priorité 1).

Et elles passaient les CINQ invariants du parc, dont « coordonnées PRÉSENTES ». Le repli
`COALESCE(ads.latitude, ST_Y(cities.centroid))` ne jouait pas non plus : **0 n'est pas NULL**.

La mesure avait trouvé le voisin immédiat — le champ vide — et manquait le champ FAUX, qui est le
cas rapporté par l'utilisateur.

Deux choses sont tenues ici, et la seconde compte autant que la première : le contrôle de
plausibilité, ET l'aveu de sa limite — un contrôle par CHAMP ne peut pas voir (0,0), puisque 0
est une latitude valide et 0 une longitude valide.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import domaine


def _ecrire(chemin: Path, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


_SCHEMA = '''
from marshmallow import Schema, fields, validate

class AdvertSchema(Schema):
    latitude = fields.Float(validate=validate.Range(min=-90, max=90))
    longitude = fields.Float(validate=validate.Range(min=-180, max=180))
    statut = fields.Str(validate=validate.OneOf(["actif", "archive", "brouillon"]))
'''

_SQL = """
CREATE TABLE ads (
  id TEXT PRIMARY KEY,
  surface INT CHECK (surface BETWEEN 5 AND 5000),
  categorie TEXT CHECK (categorie IN ('bureau', 'commerce', 'entrepot'))
);
"""


# --- La lecture des domaines DÉJÀ déclarés --------------------------------------------------------
def test_les_domaines_du_SCHEMA_sont_lus_la_ou_le_projet_les_ecrit(tmp_path: Path) -> None:
    """« Le domaine n'est pas à deviner : il est déjà déclaré dans le schéma que la forge lit. »"""
    _ecrire(tmp_path / "backend" / "schemas.py", _SCHEMA)

    d = domaine.domaines_declares(tmp_path)

    assert d["latitude"] == {"type": "intervalle", "min": -90, "max": 90,
                             "source": "schemas.py · validate.Range"}
    assert d["statut"]["type"] == "enumeration"
    assert "archive" in d["statut"]["valeurs"]


def test_les_CHECK_du_SQL_sont_lus_aussi_car_les_projets_emploient_les_deux(tmp_path: Path) -> None:
    _ecrire(tmp_path / "migrations" / "001.sql", _SQL)

    d = domaine.domaines_declares(tmp_path)

    assert d["surface"]["min"] == 5 and d["surface"]["max"] == 5000
    assert d["categorie"]["valeurs"] == ["bureau", "commerce", "entrepot"]


# --- Le contrôle : PRÉSENT puis PLAUSIBLE ---------------------------------------------------------
def test_une_valeur_HORS_domaine_est_constatee_avec_ses_LIGNES_NOMMEES(tmp_path: Path) -> None:
    """Un total anonyme n'est pas un constat : ce sont les lignes qui se corrigent."""
    _ecrire(tmp_path / "backend" / "schemas.py", _SCHEMA)
    d = domaine.domaines_declares(tmp_path)

    r = domaine.juger_champ("latitude", [48.8, 999.0, 43.2, -200.0], d,
                            cle=lambda rang: f"#{4860 + rang}")

    assert r["statut"] == domaine.HORS_DOMAINE
    assert r["hors_domaine"] == [1, 3]
    assert "#4861 = 999.0" in r["motif"]
    assert "présentes, donc invisibles au contrôle de présence" in r["motif"]


def test_une_valeur_dans_le_domaine_est_CONFORME_et_le_dit_sur_quoi(tmp_path: Path) -> None:
    _ecrire(tmp_path / "backend" / "schemas.py", _SCHEMA)
    d = domaine.domaines_declares(tmp_path)

    r = domaine.juger_champ("latitude", [48.8, 43.2], d)

    assert r["statut"] == domaine.CONFORME
    assert "validate.Range" in r["motif"], "un PASS dit d'où vient le domaine qu'il a appliqué"


def test_un_champ_SANS_domaine_declare_le_DIT_au_lieu_d_inventer(tmp_path: Path) -> None:
    """« Le domaine se déclare, il ne se devine pas » — la troisième issue, et elle est
    indispensable : un domaine inventé déclarerait conforme exactement ce qui est là."""
    r = domaine.juger_champ("prix", [100, 200], {})

    assert r["statut"] == domaine.NON_DECLARABLE
    assert "aucun domaine DÉCLARÉ" in r["motif"]
    assert "il ne se devine pas" in r["motif"]


def test_la_PRESENCE_n_est_pas_rejugee_elle_est_comptee_a_part(tmp_path: Path) -> None:
    """Le confondre avec « hors domaine » ferait rendre deux fois le même constat, et ferait
    croire que le contrôle de présence est redondant — il est son JUMEAU."""
    _ecrire(tmp_path / "backend" / "schemas.py", _SCHEMA)
    d = domaine.domaines_declares(tmp_path)

    r = domaine.juger_champ("latitude", [48.8, None, None, 999.0], d)

    assert r["absentes"] == 2
    assert r["hors_domaine"] == [3], "les None ne sont pas comptés hors domaine"


def test_une_enumeration_hors_domaine_est_vue(tmp_path: Path) -> None:
    _ecrire(tmp_path / "backend" / "schemas.py", _SCHEMA)
    d = domaine.domaines_declares(tmp_path)

    r = domaine.juger_champ("statut", ["actif", "supprime"], d)

    assert r["statut"] == domaine.HORS_DOMAINE
    assert "'supprime'" in r["motif"]


def test_le_cas_du_golfe_de_GUINEE_est_constate_par_le_controle_de_COUPLE(tmp_path: Path) -> None:
    """Le cœur de l'item. Chaque coordonnée est DANS son domaine — 0 est une latitude valide et 0
    une longitude valide. Seul le COUPLE est faux, et aucun contrôle par champ ne peut le voir."""
    lignes = [
        {"latitude": 49.5, "longitude": 0.9},
        {"latitude": 0, "longitude": 0},
        {"latitude": 48.7, "longitude": 6.2},
        {"latitude": 0.0, "longitude": 0.0},
    ]

    constats = domaine.juger_couples(lignes)

    assert len(constats) == 1
    assert constats[0]["rangs"] == [1, 3]
    assert "golfe de Guinée" in constats[0]["motif"]
    assert "leur COMBINAISON qui est fausse" in constats[0]["motif"]


def test_le_controle_par_CHAMP_declare_conformes_les_memes_lignes(tmp_path: Path) -> None:
    """La preuve que le contrôle de couple n'est pas un luxe : sur les MÊMES lignes, le contrôle
    par champ — celui que l'item demandait — dit CONFORME. Les deux sont nécessaires."""
    _ecrire(tmp_path / "backend" / "schemas.py", _SCHEMA)
    d = domaine.domaines_declares(tmp_path)

    lat = domaine.juger_champ("latitude", [49.5, 0, 48.7, 0.0], d)
    lon = domaine.juger_champ("longitude", [0.9, 0, 6.2, 0.0], d)

    assert lat["statut"] == domaine.CONFORME
    assert lon["statut"] == domaine.CONFORME


def test_un_parc_SAIN_ne_declenche_aucun_constat_de_couple() -> None:
    constats = domaine.juger_couples([{"latitude": 49.5, "longitude": 0.9}])

    assert constats == []


def test_la_LIMITE_du_controle_par_champ_est_declaree() -> None:
    """Loi 3. Sans cet aveu, « tous les champs conformes » se lirait « la donnée est bonne » —
    ce qui était exactement le cas des 11 annonces."""
    declare = " ".join(domaine.NON_JUGE)

    assert "tautologie" in declare, "un domaine déduit des valeurs observées"
    assert "combinaison fausse dont chaque terme est valide" in declare
    assert "JUMEAU" in declare, "la présence n'est pas redondante"
