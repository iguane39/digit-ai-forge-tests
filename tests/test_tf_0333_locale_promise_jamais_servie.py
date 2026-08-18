"""TF-0333 — une locale promise par la source et JAMAIS servie est désormais confrontée.

Le contrôle écart servi↔versionné (TF-0288) itérait sur les locales SERVIES : il comparait
menu à menu, locale par locale, pour chaque locale que le build rendait. Une locale que la
source promet et que le build ne sert pas DU TOUT n entrait dans aucune itération — elle
sortait donc en PASS sur une promesse jamais confrontée.

C est le symétrique exact du cas fondateur INS-0001 : là, c était le servi qui manquait des
entrées ; ici, c est une locale entière. Le contrôle né pour attraper cette famille d écarts
laissait passer sa forme la plus grosse : un produit qui cesse de servir `/en` en entier.

Trois sens tenus ici : la locale absente est CONSTATÉE ; le déploiement correct n est pas
accusé ; et le cas indéterminable (build qui ne préfixe aucune locale) est SUSPENDU et DIT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import interface

CONFIG_NEXT = 'module.exports = { i18n: { locales: ["fr", "en", "de"], defaultLocale: "fr" } };'

_NAV_COMMUNE = ("/", "/tarifs", "/blog")
_NAV_EN = ("/en", "/en/tarifs", "/en/blog")

_COMPOSANT = """export default function {nom}() {{
  return (
    <header>
      <nav>
{liens}
      </nav>
    </header>
  );
}}
"""
_PAGE = """<!doctype html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>{titre}</title></head>
<body>
  <header><nav>
{liens}
  </nav></header>
  <main><h1>{titre}</h1></main>
</body>
</html>
"""


def _ecrire_composant(chemin: Path, nom: str, entrees: tuple[str, ...]) -> None:
    liens = "\n".join(f'        <Link href="{e}">{e}</Link>' for e in entrees)
    chemin.write_text(_COMPOSANT.format(nom=nom, liens=liens), encoding="utf-8")


def _ecrire_page(chemin: Path, lang: str, titre: str, entrees: tuple[str, ...]) -> None:
    liens = "\n".join(f'    <a href="{e}">{e}</a>' for e in entrees)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(_PAGE.format(lang=lang, titre=titre, liens=liens), encoding="utf-8")


def _produit(
    racine: Path,
    *,
    locales_servies: tuple[str, ...] = (),
    servir_en: bool = False,
) -> Path:
    """Source : un menu commun + un `HeaderEn.tsx` qui promet la navigation ANGLAISE.

    Le build sert toujours la locale par défaut. `locales_servies` liste les locales que le
    build PRÉFIXE réellement — c est le seul levier des trois cas ci-dessous.
    """
    # La source DÉCLARE ses locales au framework : sans quoi `HeaderEn.tsx` n est rattaché à
    # aucune locale (TF-0295) et la promesse anglaise n existe pas comme terme opposable.
    (racine / "next.config.js").write_text(
        CONFIG_NEXT,
        encoding="utf-8",
    )
    composants = racine / "components"
    composants.mkdir(parents=True)
    _ecrire_composant(composants / "Header.tsx", "Header", _NAV_COMMUNE)
    _ecrire_composant(composants / "HeaderEn.tsx", "HeaderEn", _NAV_EN)

    build = racine / "dist"
    _ecrire_page(build / "index.html", "fr", "Accueil", _NAV_COMMUNE)
    for locale in locales_servies:
        entrees = _NAV_EN if locale == "en" else _NAV_COMMUNE
        _ecrire_page(build / locale / "index.html", locale, locale.upper(), entrees)
    if servir_en and "en" not in locales_servies:
        _ecrire_page(build / "en" / "index.html", "en", "Home", _NAV_EN)
    return racine


@pytest.fixture(autouse=True)
def _sans_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_TESTS_I18N_BUILD", raising=False)


# --- Fixture ROUGE : la locale entière jamais servie -------------------------------------------
def test_une_locale_promise_par_la_source_et_jamais_servie_est_CONSTATEE(tmp_path: Path) -> None:
    """AVANT : PASS. Le build sert `de`, donc la boucle itérait sur `de` — et `en`, promis par
    `HeaderEn.tsx`, n était comparé à rien du tout."""
    cible = _produit(tmp_path, locales_servies=("de",))

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "FAIL", ecart["motif"]
    assert "en" in ecart["manquantes"], ecart["manquantes"]
    assert ecart["locales_jamais_servies"] == ["en"]


def test_le_constat_DIT_que_la_locale_entiere_manque_pas_qu_un_menu_est_ampute(
    tmp_path: Path,
) -> None:
    """Les deux écarts ne se réparent pas pareil : redéployer une locale n est pas corriger un
    menu. Un message qui les confond envoie chercher des entrées dans une page inexistante."""
    cible = _produit(tmp_path, locales_servies=("de",))

    findings = interface._findings_ecart(cible, interface.ecart_servi_versionne(cible))
    message = next(f.message for f in findings if f.id.endswith(":en"))

    assert "NULLE PART" in message
    assert "locale entiere absente du deploiement" in message
    assert "menu ampute" in message


# --- Second sens : un déploiement complet reste innocent ----------------------------------------
def test_une_locale_promise_ET_servie_completement_ne_declenche_RIEN(tmp_path: Path) -> None:
    cible = _produit(tmp_path, locales_servies=("en",))

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "PASS", ecart["manquantes"]
    assert ecart["locales_jamais_servies"] == []


# --- Troisième sens : l indéterminable est SUSPENDU, jamais tu -----------------------------------
def test_un_build_qui_ne_prefixe_AUCUNE_locale_suspend_le_jugement_et_le_DIT(
    tmp_path: Path,
) -> None:
    """Un produit peut construire un déploiement par langue : accuser serait accuser la limite
    du lecteur. Mais se taire serait le silence que TF-0333 vient de supprimer — donc on DIT."""
    cible = _produit(tmp_path, locales_servies=())

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["locales_jamais_servies"] == []
    assert "SUSPENDU sur 1 locale(s) promise(s)" in ecart["motif"]
    assert "TF-0333" in ecart["motif"]


def test_une_locale_servie_SANS_page_racine_est_nommee_au_motif(tmp_path: Path) -> None:
    """Le second silence du même patron : `if accueil is None: continue` sautait la locale sans
    rien en dire — un `continue` muet dans la boucle qui prononce le verdict."""
    cible = _produit(tmp_path, locales_servies=("en",))
    (cible / "dist" / "en" / "index.html").unlink()
    _ecrire_page(cible / "dist" / "en" / "tarifs" / "index.html", "en", "Tarifs", _NAV_EN)

    ecart = interface.ecart_servi_versionne(cible)

    assert "sans page racine" in ecart["motif"], ecart["motif"]
    assert "« en »" in ecart["motif"]
