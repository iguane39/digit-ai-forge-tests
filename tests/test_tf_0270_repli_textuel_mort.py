"""TF-0270 — le repli TEXTUEL du pan `data` etait du code mort, il est retire.

Fait mesure (balayage du 15/08) : `_repli_textuel` lisait les blocs de `<cible>/backend/tests`
et creditait un element dont le NOM apparaissait dans un test. Son appel a ete retire le 02/08
(commit 2497363, « plus aucun repli textuel dans le pan Data : l execution tranche pour toutes
les classes ») quand la sonde SQL a rendu les instructions envoyees mesurables. La fonction,
elle, est restee — avec son ancre en dur `<cible>/backend/tests`, invisible a la racine plate
que TF-0256 a rendue legitime. Deux couts si elle etait rebranchee : une couverture accordee a
une RESSEMBLANCE DE NOM (un test qui cite `uq_facture_numero` en commentaire suffirait), et une
ancre qui ne vaut plus que pour la moitie des dispositions de projet.

ROUGE : `test_un_test_qui_NOMME_la_contrainte_ne_la_couvre_pas` passe au vert (donc echoue a
prouver quoi que ce soit) si le repli est rebranche — mesure en rebranchant `_repli_textuel`
sur ce montage, la contrainte ressortait couverte sans qu aucune violation ait ete levee.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import data

_MIGRATION = """
CREATE TABLE facture (
  id INTEGER PRIMARY KEY,
  numero TEXT NOT NULL,
  CONSTRAINT uq_facture_numero UNIQUE (numero)
);
"""

# Un test qui PARLE de la contrainte sans jamais la faire lever : commentaire, nom de fonction,
# et meme un `raises` — exactement la forme que l ancien repli creditait.
_TEST_QUI_NOMME = '''
import pytest


# Verifie uq_facture_numero
def test_uq_facture_numero():
    with pytest.raises(Exception):
        pass
'''


def _projet(racine: Path) -> Path:
    (racine / "backend" / "migrations").mkdir(parents=True)
    (racine / "backend" / "migrations" / "001_facture.sql").write_text(
        _MIGRATION, encoding="utf-8"
    )
    (racine / "backend" / "tests").mkdir(parents=True)
    (racine / "backend" / "tests" / "test_facture.py").write_text(
        _TEST_QUI_NOMME, encoding="utf-8"
    )
    return racine


def test_le_repli_textuel_n_a_plus_de_code(tmp_path):
    """Le garde-fou du retrait : ni la fonction, ni le decoupeur qui n existait que pour elle."""
    assert not hasattr(data, "_repli_textuel")
    assert not hasattr(data, "blocs_de_test")


def test_un_test_qui_NOMME_la_contrainte_ne_la_couvre_pas(tmp_path, monkeypatch):
    """LE defaut evite : la couverture ne s achete pas avec une ressemblance de nom."""
    cible = _projet(tmp_path)
    monkeypatch.setattr(data, "violations_levees", lambda _: [])
    monkeypatch.setattr(data, "instructions_sql", lambda _: [])

    couvert = data.exerces(cible)

    assert couvert == set(), couvert


def test_une_violation_REELLEMENT_levee_couvre_la_contrainte(tmp_path, monkeypatch):
    """Contrepartie : le retrait n a rien retire a ce que l execution, elle, etablit."""
    cible = _projet(tmp_path)
    monkeypatch.setattr(
        data,
        "violations_levees",
        lambda _: ['UNIQUE constraint failed: facture.numero'],
    )
    monkeypatch.setattr(data, "instructions_sql", lambda _: [])

    couvert = data.exerces(cible)

    assert "contrainte:uq_facture_numero" in couvert, couvert
