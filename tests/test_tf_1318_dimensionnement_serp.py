"""TF-1318 — le dimensionnement SERP d'un site traduit, jugé locale par locale.

LE FAIT. Le lot `Produit-02 - RETOURS - 20260826f` du pilot nomme le « dimensionnement SERP »
comme une étape de la chaîne « audite les traductions » (B6). Sur le produit d'origine, un
contrôleur PROPRE AU PRODUIT la tenait — il « compte des caractères » (lot `20260826d`) — et le
produit suivant n'en aura pas. Une traduction change la longueur d'un titre : sa taille se juge
donc langue par langue, et non une fois pour la langue d'origine.

LA BORNE EST UNE DONNÉE, PAS DU CODE : la troncature d'un moteur change sans préavis et se fait
en pixels. Le projet la déclare, sourcée et datée, dans `FORGE_TESTS_SERP_BORNES` ; rien de
déclaré, rien de jugé, et une borne sans source ni date est REFUSÉE avec son motif.

FIXTURE À DOUBLE SENS : un build servi à trois locales, dont les titres et descriptions sont posés
à une longueur connue. La verte tient dans ses bornes ; chaque rouge en dépasse UNE, et le constat
nomme la locale, la route, la balise, la longueur et la borne.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import i18n

#: Les variables qui changeraient ce que le pan lit. Le `.env` d'un opérateur ne doit jamais faire
#: juger au pan autre chose que ce que le test croit lui montrer.
_VARIABLES = (
    "FORGE_TESTS_I18N_BUILD", "FORGE_TESTS_SERP_BORNES", "FORGE_TESTS_I18N_ROUTES",
    "FORGE_TESTS_I18N_CHAINES", "FORGE_TESTS_I18N_LEXIQUES", "FORGE_TESTS_GLOSSAIRE",
    "FORGE_TESTS_FAITS", "FORGE_TESTS_ORPHELINS", "FORGE_TESTS_DENOMBRABLES", "FORGE_TESTS_DONNEES",
)

TITRE_FR = "Gîte au pied du Mont-Saint-Michel"                       # 33 caractères
TITRE_DE_COURT = "Ferienhaus am Mont-Saint-Michel"                    # 31 caractères
TITRE_DE_LONG = "Ferienhaus mit Hallenbad und Garten am Fuße des Mont-Saint-Michel, Normandie"
DESCRIPTION = "Cinq gîtes, une piscine couverte, la baie à dix minutes."
DESCRIPTION_LONGUE = ("Cinco casas rurales con piscina cubierta, jardín y vistas a la bahía, "
                      "a diez minutos del Mont-Saint-Michel, para familias, grupos y seminarios "
                      "durante todo el año entero.")                          # 170 caractères


@pytest.fixture(autouse=True)
def _environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for nom in _VARIABLES:
        monkeypatch.delenv(nom, raising=False)


def _page(titre: str, description: str, *, icone: str = "") -> str:
    return (f'<!doctype html><html lang="x"><head><title>{titre}</title>'
            f'<meta name="description" content="{description}"></head>'
            f"<body>{icone}<p>Texte court.</p></body></html>")


def _build(tmp_path: Path, *, de: str = TITRE_DE_COURT, es_description: str = DESCRIPTION,
           icone: str = "") -> Path:
    """Un build servi à trois locales : `fr` par défaut (sans préfixe), `de` et `es` préfixées."""
    build = tmp_path / "dist"
    (build / "de").mkdir(parents=True)
    (build / "es").mkdir()
    (build / "index.html").write_text(_page(TITRE_FR, DESCRIPTION, icone=icone), encoding="utf-8")
    (build / "de" / "index.html").write_text(_page(de, DESCRIPTION), encoding="utf-8")
    (build / "es" / "index.html").write_text(
        _page("Casa rural junto al Mont-Saint-Michel", es_description), encoding="utf-8")
    return build


def _bornes(tmp_path: Path, **surcharges: object) -> Path:
    corps = {"source": "gabarit SERP du projet, relevé sur la page de résultats",
             "verifie_le": "2026-09-23",
             "bornes": {"title": {"max": 60}, "description": {"max": 155}}, **surcharges}
    chemin = tmp_path / "bornes-serp.json"
    chemin.write_text(json.dumps(corps), encoding="utf-8")
    return chemin


def _jouer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, build: Path | None,
           bornes: Path | None) -> i18n.SortieAdaptateur:
    if build is not None:
        monkeypatch.setenv("FORGE_TESTS_I18N_BUILD", str(build))
    if bornes is not None:
        monkeypatch.setenv("FORGE_TESTS_SERP_BORNES", str(bornes))
    return i18n.analyser(tmp_path)


def _serp(sortie: i18n.SortieAdaptateur) -> dict[str, str]:
    return {f.id: f.message for f in sortie.findings if f.id.startswith("i18n:serp:")}


# --- VERT ----------------------------------------------------------------------------------------
def test_vert_des_titres_dans_leurs_bornes_ne_donnent_aucun_constat(tmp_path, monkeypatch) -> None:
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path), _bornes(tmp_path))
    assert _serp(sortie) == {}
    motif = next(m for m in sortie.non_juge if "dimensionnement SERP" in m)
    assert "juge contre les bornes declarees" in motif and "2026-09-23" in motif
    assert "3 page(s)" in motif and "0 hors borne" in motif


def test_vert_une_borne_par_locale_l_emporte_sur_la_borne_commune(tmp_path, monkeypatch) -> None:
    """L'allemand a droit à 80 : son titre de 76 caractères tient, et rien n'est accusé."""
    bornes = _bornes(tmp_path, par_locale={"de": {"title": {"max": 80}}})
    assert _serp(_jouer(tmp_path, monkeypatch, _build(tmp_path, de=TITRE_DE_LONG), bornes)) == {}


def test_vert_le_title_d_une_icone_svg_n_est_pas_additionne_au_titre(tmp_path, monkeypatch) -> None:
    """Un `<title>` d'icône, plus loin dans la page, n'est pas le titre de résultat."""
    icone = f"<svg><title>{'Icone de navigation principale du site ' * 3}</title></svg>"
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path, icone=icone), _bornes(tmp_path))
    assert _serp(sortie) == {}


# --- ROUGE ---------------------------------------------------------------------------------------
def test_rouge_un_titre_allemand_au_dela_du_maximum_est_nomme(tmp_path, monkeypatch) -> None:
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path, de=TITRE_DE_LONG), _bornes(tmp_path))
    constats = _serp(sortie)
    assert set(constats) == {"i18n:serp:de:/:title"}
    message = constats["i18n:serp:de:/:title"]
    assert f"{len(TITRE_DE_LONG)} caractere(s)" in message and "maximum declare de 60" in message
    assert "/de" in message and "2026-09-23" in message


def test_rouge_une_description_au_dela_du_maximum_est_nommee(tmp_path, monkeypatch) -> None:
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path, es_description=DESCRIPTION_LONGUE),
                    _bornes(tmp_path))
    assert set(_serp(sortie)) == {"i18n:serp:es:/:description"}
    assert sortie.verdict == "FAIL"


def test_rouge_un_titre_en_deca_d_un_minimum_declare_est_nomme(tmp_path, monkeypatch) -> None:
    bornes = _bornes(tmp_path, bornes={"title": {"min": 32, "max": 60}})
    constats = _serp(_jouer(tmp_path, monkeypatch, _build(tmp_path), bornes))
    assert set(constats) == {"i18n:serp:de:/:title"}
    assert "en deca du minimum declare de 32" in constats["i18n:serp:de:/:title"]


# --- BORNES --------------------------------------------------------------------------------------
def test_rien_de_declare_rien_de_juge_et_le_rapport_le_dit(tmp_path, monkeypatch) -> None:
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path, de=TITRE_DE_LONG), None)
    assert _serp(sortie) == {}
    assert any("dimensionnement SERP (TF-1318) NON juge" in m and "aucune borne declaree" in m
               for m in sortie.non_juge)


def test_une_borne_sans_source_ni_date_est_refusee_et_n_accuse_rien(tmp_path, monkeypatch) -> None:
    chemin = tmp_path / "bornes-serp.json"
    chemin.write_text(json.dumps({"bornes": {"title": {"max": 10}}}), encoding="utf-8")
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path), chemin)
    assert _serp(sortie) == {}
    assert any("NON opposables" in m for m in sortie.non_juge)


def test_des_bornes_declarees_sans_build_servi_le_disent(tmp_path, monkeypatch) -> None:
    sortie = _jouer(tmp_path, monkeypatch, None, _bornes(tmp_path))
    assert any("NON joue" in m and "AUCUN build servi" in m for m in sortie.non_juge)


def test_le_constat_se_range_par_locale_et_recoit_une_suite_a_donner(tmp_path, monkeypatch) -> None:
    from forge_tests.actions import classifier
    from forge_tests.livrables.surface import sous_chapitre

    assert sous_chapitre("locale", "i18n:serp:de:/:title") == ("locale de", True)
    sortie = _jouer(tmp_path, monkeypatch, _build(tmp_path, de=TITRE_DE_LONG), _bornes(tmp_path))
    actions = classifier([{**vars(f), "pan": "i18n"} for f in sortie.findings])
    assert {action["categorie"] for action in actions} == {"manuelle_dev"}
