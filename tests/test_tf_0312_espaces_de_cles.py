"""TF-0312 — l'écart servi↔versionné ne compare plus deux espaces de clés différents.

Défaut LATENT de TF-0288, reproduit le 17/08 hors des deux bancs. Les deux termes délocalisent
leurs clés, mais pas avec la même liste de locales :

  - le SERVI, avec les locales qu il PRÉFIXE réellement (`/en/tarifs` -> `/tarifs`) ;
  - la SOURCE, avec les seules locales que son arborescence DÉCLARE.

Quand la source n en déclare aucune — nav dans un composant, routes non lisibles par ce lecteur —
et que le build servi en sert une, la source promet `/en/tarifs` là où le servi rend `/tarifs` :
aucune entrée ne s apparie et le contrôle accuse un déploiement CORRECT. Mesuré : 3 entrées
« manquantes » par locale sur un servi qui les rendait toutes les trois. Un faux positif sur un
contrôle né avant-hier lui coûterait sa crédibilité avant son premier vrai cas.

Deux remèdes, dans cet ordre :

  1. ALIGNER quand c est déterminable — les locales que le servi préfixe sont un FAIT constaté :
     les rendre à la lecture de la source met les deux termes dans le même espace ;
  2. SUSPENDRE le jugement sinon, avec motif déclaré — une entrée `/xx/…` dont `xx` est une locale
     connue que NI la source NI le servi ne nomme est indéterminable (patron TF-0295 levée 4).

Double sens sur chaque remède : la fixture qui reproduisait la fausse accusation et la fixture
d un VRAI écart, qui doit rester constaté.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import interface

# Le menu du composant source : trois entrées de premier niveau, toutes préfixées `/en`.
_NAV_SOURCE = ("/en", "/en/tarifs", "/en/blog")

_COMPOSANT = """export default function HeaderEn() {{
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


def _composant(entrees: tuple[str, ...]) -> str:
    liens = "\n".join(f'        <Link href="{e}">{e}</Link>' for e in entrees)
    return _COMPOSANT.format(liens=liens)


def _page(lang: str, titre: str, entrees: tuple[str, ...]) -> str:
    liens = "\n".join(f'    <a href="{e}">{e}</a>' for e in entrees)
    return _PAGE.format(lang=lang, titre=titre, liens=liens)


def _produit(
    racine: Path,
    *,
    nav_source: tuple[str, ...] = _NAV_SOURCE,
    composant: str = "HeaderEn.tsx",
    servies_en: tuple[str, ...] = _NAV_SOURCE,
    servies_defaut: tuple[str, ...] = ("/", "/tarifs", "/blog"),
    locale_servie: str | None = "en",
    config_locales: tuple[str, ...] = (),
) -> Path:
    """Un produit dont la SOURCE ne déclare aucune locale — c est tout le sujet.

    Aucun dossier `app/` : le lecteur de routes ne trouve donc ni `/en/…` littéral ni
    configuration, et `_arborescence(…)["locales"]` sort VIDE. C est la situation réelle d un
    produit dont le routage vit dans un dialecte que ce lecteur ne parcourt pas.

    `locale_servie=None` retire le préfixe du build : plus personne ne nomme la locale, et le
    jugement doit alors être suspendu au lieu d être rendu. `config_locales` la déclare au
    framework — le second sens de la suspension.
    """
    (racine / "components").mkdir(parents=True)
    (racine / "components" / composant).write_text(_composant(nav_source), encoding="utf-8")
    if config_locales:
        codes = ", ".join(f'"{code}"' for code in config_locales)
        (racine / "next.config.js").write_text(
            f'module.exports = {{ i18n: {{ locales: [{codes}], defaultLocale: "fr" }} }};\n',
            encoding="utf-8",
        )

    build = racine / "dist"
    build.mkdir()
    (build / "index.html").write_text(_page("fr", "Accueil", servies_defaut), encoding="utf-8")
    if locale_servie is not None:
        (build / locale_servie).mkdir()
        (build / locale_servie / "index.html").write_text(
            _page(locale_servie, "Home", servies_en), encoding="utf-8"
        )
    return racine


@pytest.fixture(autouse=True)
def _sans_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_TESTS_I18N_BUILD", raising=False)


# --- Fixture ROUGE : la fausse accusation d avant, qui doit avoir DISPARU ----------------------
def test_un_deploiement_CORRECT_n_est_plus_accuse_quand_la_source_ne_declare_aucune_locale(
    tmp_path: Path,
) -> None:
    """Le cas reproduit le 17/08. AVANT : `manquantes` portait les 3 entrées sous CHAQUE locale —
    six constats `mep-config` contre un servi irréprochable. Le premier vrai cas du contrôle
    serait arrivé après ce faux, et personne ne l aurait cru."""
    cible = _produit(tmp_path)

    assert interface._arborescence(cible)["locales"] == set()  # la source n en déclare AUCUNE
    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "PASS", ecart["manquantes"]
    assert ecart["manquantes"] == {}
    assert "SUSPENDU" not in ecart["motif"]  # déterminable : aligné, pas suspendu


def test_l_alignement_passe_bien_par_les_locales_du_SERVI(tmp_path: Path) -> None:
    """La mécanique du remède 1, mesurée là où elle opère : la lecture de la source rend des clés
    délocalisées dès qu on lui donne les locales que le build PRÉFIXE — un fait constaté, jamais
    une supposition. Sans elles, elle garde `/en/tarifs`, et c est la fausse accusation."""
    cible = _produit(tmp_path)

    sans, _f, _l = interface.navigation_source(cible)
    avec, _f, _l = interface.navigation_source(cible, {"en"})

    assert sans[""] == {"/en", "/en/tarifs", "/en/blog"}
    # Les locales rendues, le composant `HeaderEn` est reconnu comme le menu de `en` et ses clés
    # sont délocalisées : le MÊME espace que celui du lecteur du build.
    assert avec["en"] == {"/", "/tarifs", "/blog"}


# --- Fixture VERTE (du remède) : un VRAI écart reste constaté ----------------------------------
def test_un_VRAI_ecart_reste_detecte_et_nomme_dans_le_meme_montage(tmp_path: Path) -> None:
    """Le sens qui absoudrait, et c est le garde-fou essentiel : aligner les espaces de clés ne
    doit pas rendre le contrôle aveugle. Le servi ampute ici la page des tarifs — le cas
    fondateur INS-0001 en réduction, sur le montage même qui produisait le faux positif."""
    cible = _produit(tmp_path, servies_en=("/en", "/en/blog"))

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "FAIL"
    assert ecart["manquantes"] == {"en": ["/tarifs"]}


# --- Remède 2 : SUSPENDRE quand aucun des deux termes ne nomme la locale -----------------------
# Le menu est ici porté par un composant SANS locale au nom (`Header.tsx`) : ses entrées sont donc
# promises à toutes les locales, et l une d elles est préfixée `de` — que rien ne déclare.
_NAV_MELEE = ("/", "/tarifs", "/de/tarifs")


def test_une_locale_que_PERSONNE_ne_declare_suspend_le_jugement_au_lieu_de_l_accuser(
    tmp_path: Path,
) -> None:
    """Ni la source ni le servi ne nomme `de` : `/de/tarifs` peut être la version allemande de
    `/tarifs` comme une page `/de/…` légitime. Indéterminable — donc non jugé, et DIT. Le faux
    positif serait de trancher (patron TF-0295 levée 4 : la provenance des locales se déclare)."""
    cible = _produit(
        tmp_path,
        nav_source=_NAV_MELEE,
        composant="Header.tsx",
        locale_servie=None,
        servies_defaut=("/", "/tarifs"),
    )

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "PASS", ecart["manquantes"]
    assert "SUSPENDU" in ecart["motif"]
    assert "/de/tarifs" in ecart["motif"]  # l entrée non jugée est NOMMÉE


def test_la_suspension_n_est_PAS_une_amnistie_les_autres_entrees_restent_jugees(
    tmp_path: Path,
) -> None:
    """Second sens, et c est le garde-fou : la suspension porte sur les entrées indéterminables,
    JAMAIS sur le contrôle entier. Le servi ampute ici `/tarifs` — constaté, pendant que
    `/de/tarifs` reste non jugé."""
    cible = _produit(
        tmp_path,
        nav_source=_NAV_MELEE,
        composant="Header.tsx",
        locale_servie=None,
        servies_defaut=("/",),
    )

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "FAIL", ecart["motif"]
    assert ecart["manquantes"] == {"": ["/tarifs"]}
    assert "SUSPENDU" in ecart["motif"]


def test_la_locale_DECLAREE_par_la_configuration_ne_suspend_RIEN(tmp_path: Path) -> None:
    """Troisième sens : la même source, le même servi, mais `next.config.js` nomme `de`. Le terme
    est alors déterminable, `/de/tarifs` redevient `/tarifs`, et plus rien n est suspendu."""
    cible = _produit(
        tmp_path,
        nav_source=_NAV_MELEE,
        composant="Header.tsx",
        locale_servie=None,
        servies_defaut=("/", "/tarifs"),
        config_locales=("fr", "de"),
    )

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "PASS", ecart["manquantes"]
    assert "SUSPENDU" not in ecart["motif"]


def test_quand_TOUT_est_indeterminable_le_controle_se_TAIT_au_lieu_de_dire_PASS(
    tmp_path: Path,
) -> None:
    """Le dernier sens : si aucune entrée n est comparable, « chaque entrée promise est servie »
    serait un PASS mensonger — la comparaison n a pas eu lieu. Verdict SKIP, motif à l appui."""
    cible = _produit(
        tmp_path,
        nav_source=("/de", "/de/tarifs"),
        composant="Header.tsx",
        locale_servie=None,
        servies_defaut=("/", "/tarifs"),
    )

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "SKIP", ecart
    assert ecart["manquantes"] == {}
    assert "AUCUNE entree comparable" in ecart["motif"]
    assert "SUSPENDU" in ecart["motif"]
