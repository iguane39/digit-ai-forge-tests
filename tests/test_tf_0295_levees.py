"""TF-0295 — les quatre limites declarees au non_juge par la campagne du 15/08, levees.

Aucune n etait un defaut : ce sont les frontieres que TF-0283 et TF-0284 ont NOMMEES plutot que
tues. Chacune correspondait a un cas reel possible, et chacune se leve ici avec sa fixture a
double sens — le sens rouge (le defaut sort) ET le sens vert (le cas sain ne sort pas). Sans le
second, une levee ne se distinguerait pas d un controle devenu bavard.

  1. la parite de navigation comparait des COMPTES : deux menus de meme taille aux entrees
     DIFFERENTES passaient. L appariement se fait desormais par ENTREE, cle = destination
     delocalisee, et les entrees manquantes sont NOMMEES ;
  2. le controle de destinations ne couvrait que `.jsx`/`.tsx` : `.vue` et `.svelte` entrent,
     chacun avec SA grammaire — la limite d origine etait juste, prendre `:to="lien"` pour un
     litteral aurait accuse un lien sain ;
  3. le controle de langue ne connaissait que « francais servi sous locale non francaise » : le
     lexique est une TABLE (`fr`, `en`) et un projet peut en DECLARER d autres ;
  4. la locale d un composant se deduisait de la seule arborescence LITTERALE : la configuration
     du framework (`locales: [...]` de Next) est lue aussi. C est la configuration d INS-0001 —
     avec un routage `app/[locale]/…`, aucun segment litteral n existe et les trois controles de
     locale etaient DESACTIVES sans que rien ne le dise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import i18n, interface

# ==============================================================================================
# Levee 1 — parite de navigation par ENTREE, plus par compte
# ==============================================================================================
_MENU = """<!doctype html>
<html lang="{lang}">
<head><title>{titre}</title></head>
<body><nav>{entrees}</nav>
<main><p>{corps}</p></main></body></html>
"""
# 40 mots au moins, sinon la langue n est pas jugee et le test mesurerait autre chose.
_CORPS_FR = (
    "Cette page est servie dans la langue par defaut du site. Le menu porte les entrees que le "
    "produit offre, et chaque entree mene vers une page qui existe dans cette langue comme dans "
    "les autres, ce qui est precisement ce que le controle de parite doit verifier ici."
)
_CORPS_EN = (
    "This page is served under the English locale prefix of the site. The menu carries the "
    "entries that the product offers, and each entry leads to a page which exists in this "
    "language as well as in the others, which is what the parity control has to verify here."
)


def _entrees(*destinations: str) -> str:
    return "".join(f'<a href="{cible}">{cible}</a>' for cible in destinations)


def _build(racine: Path, defaut: tuple[str, ...], anglais: tuple[str, ...]) -> Path:
    """Un build servi a deux locales, dont les menus portent les destinations demandees."""
    build = racine / "dist"
    (build / "en").mkdir(parents=True)
    (build / "index.html").write_text(
        _MENU.format(lang="fr", titre="Accueil", entrees=_entrees(*defaut), corps=_CORPS_FR),
        encoding="utf-8",
    )
    (build / "en" / "index.html").write_text(
        _MENU.format(lang="en", titre="Home", entrees=_entrees(*anglais), corps=_CORPS_EN),
        encoding="utf-8",
    )
    return racine


@pytest.fixture(autouse=True)
def _sans_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_TESTS_I18N_BUILD", raising=False)
    monkeypatch.delenv("FORGE_TESTS_I18N_LEXIQUES", raising=False)


def _constats_i18n(cible: Path) -> dict[str, str]:
    return {f.id: f.message for f in i18n.analyser(cible).findings}


def test_rouge_deux_menus_de_MEME_TAILLE_aux_entrees_differentes_echouent(tmp_path: Path) -> None:
    """LA levee : c est le cas que le controle par comptes laissait passer. Le menu anglais porte
    autant d entrees que le francais, mais il a perdu « /tarifs » et gagne « /blog »."""
    cible = _build(
        tmp_path,
        defaut=("/", "/tarifs", "/contact"),
        anglais=("/en", "/en/blog", "/en/contact"),
    )

    message = _constats_i18n(cible)["i18n:navigation:en"]

    assert "« /tarifs »" in message, message
    assert "3 entree(s) distincte(s) contre 3" in message, message


def test_vert_deux_menus_aux_MEMES_entrees_passent(tmp_path: Path) -> None:
    """Second sens : la levee ne doit pas accuser un menu traduit. Les libelles diffserent, les
    destinations non — et c est la destination qui est la cle."""
    cible = _build(
        tmp_path,
        defaut=("/", "/tarifs", "/contact"),
        anglais=("/en", "/en/tarifs", "/en/contact"),
    )

    assert "i18n:navigation:en" not in _constats_i18n(cible)


def test_les_entrees_sont_appariees_par_destination_DELOCALISEE(tmp_path: Path) -> None:
    """La cle de l appariement, isolee : `/en/tarifs` et `/tarifs` sont la MEME entree."""
    page = i18n._Page()
    page.feed(_MENU.format(lang="en", titre="t", entrees=_entrees("/en", "/en/tarifs"), corps="x"))

    assert i18n.entrees_de_menu(page, {"en"}) == ["/", "/tarifs"]


def test_une_entree_sans_destination_retombe_sur_son_libelle(tmp_path: Path) -> None:
    """Un menu peut porter un `<a>` sans `href` : il reste une entree, et deux entrees muettes
    ne doivent pas se confondre — sans quoi un menu ampute de l une passerait pour complet."""
    page = i18n._Page()
    page.feed('<nav><a aria-label="Aide">Aide</a><a></a><a></a></nav>')

    cles = i18n.entrees_de_menu(page, set())

    assert cles[0].startswith("libelle:")
    assert cles[1] != cles[2], cles


def test_le_menu_le_plus_riche_est_celui_qui_porte_le_plus_d_entrees_DISTINCTES(
    tmp_path: Path,
) -> None:
    """Un menu qui repete la meme destination n est pas plus riche : il est plus long."""
    cible = _build(
        tmp_path,
        defaut=("/", "/", "/", "/"),
        anglais=("/en", "/en/tarifs"),
    )

    # La reference est l anglais (2 entrees distinctes contre 1), donc c est le DEFAUT qui manque.
    constats = _constats_i18n(cible)
    assert "i18n:navigation:defaut" in constats, constats
    assert "« /tarifs »" in constats["i18n:navigation:defaut"]


# ==============================================================================================
# Levee 2 — les grammaires .vue et .svelte
# ==============================================================================================
_PAGES_NEXT = (
    "app/page.tsx", "app/tarifs/page.tsx", "app/en/page.tsx", "app/en/tarifs/page.tsx",
)

_VUE_FAUX = """<template>
  <header>
    <a href="/en/tarifs"><img src="/logo.svg" alt="le logo du site" /></a>
    <nav>
      <router-link to="/tarifs">Pricing</router-link>
      <router-link :to="destinationCalculee">Calcule</router-link>
    </nav>
  </header>
</template>
"""

_VUE_JUSTE = """<template>
  <header>
    <a href="/en"><img src="/logo.svg" alt="le logo du site" /></a>
    <nav>
      <router-link to="/en/tarifs">Pricing</router-link>
      <router-link :to="destinationCalculee">Calcule</router-link>
    </nav>
  </header>
</template>
"""

_SVELTE_FAUX = """<header>
  <a href="/en/tarifs"><img src="/logo.svg" alt="le logo du site" /></a>
  <nav>
    <a href="/tarifs">Pricing</a>
    <a href="{lienCalcule}">Calcule</a>
  </nav>
</header>
"""

_SVELTE_JUSTE = """<header>
  <a href="/en"><img src="/logo.svg" alt="le logo du site" /></a>
  <nav>
    <a href="/en/tarifs">Pricing</a>
    <a href="{lienCalcule}">Calcule</a>
  </nav>
</header>
"""


def _produit_composant(racine: Path, nom: str, contenu: str) -> Path:
    for page in _PAGES_NEXT:
        chemin = racine / page
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("export default function Page() { return <main />; }\n", "utf-8")
    composants = racine / "components"
    composants.mkdir(parents=True, exist_ok=True)
    (composants / nom).write_text(contenu, encoding="utf-8")
    return racine


def _motifs(cible: Path) -> list[str]:
    releve, _, _ = interface._relever_composants(cible)
    return [entree["motif"] for entree in releve if entree["motif"]]


@pytest.mark.parametrize(
    ("nom", "faux"),
    [("HeaderEn.vue", _VUE_FAUX), ("HeaderEn.svelte", _SVELTE_FAUX)],
)
def test_rouge_un_logo_et_un_lien_de_locale_faux_sont_attrapes_dans_le_dialecte(
    tmp_path: Path, nom: str, faux: str
) -> None:
    """Les MEMES deux defauts que TF-0283 attrapait en `.tsx`, dans les deux autres dialectes :
    un logo qui mene ailleurs que chez lui, et un lien anglais vers la page francaise."""
    motifs = _motifs(_produit_composant(tmp_path / nom, nom, faux))

    assert any("logo" in motif and "/en" in motif for motif in motifs), motifs
    assert any("coherence" in motif or "alors que" in motif for motif in motifs), motifs


@pytest.mark.parametrize(
    ("nom", "juste"),
    [("HeaderEn.vue", _VUE_JUSTE), ("HeaderEn.svelte", _SVELTE_JUSTE)],
)
def test_vert_les_memes_composants_corriges_ne_produisent_aucun_constat(
    tmp_path: Path, nom: str, juste: str
) -> None:
    assert _motifs(_produit_composant(tmp_path / nom, nom, juste)) == []


def test_une_liaison_Vue_est_EXPRIMEE_donc_jamais_jugee(tmp_path: Path) -> None:
    """La limite d origine de TF-0283 etait JUSTE : lire `:to="destinationCalculee"` avec le
    scanner JSX aurait juge une expression comme un chemin litteral et accuse un lien sain. Le
    dialecte est donc declare, pas devine — et la liaison est comptee EXPRIMEE."""
    cible = _produit_composant(tmp_path, "HeaderEn.vue", _VUE_JUSTE)

    releve, exprimees, _ = interface._relever_composants(cible)

    assert exprimees == 1, [entree["libelle"] for entree in releve]
    assert not [entree for entree in releve if entree["motif"]]


def test_une_interpolation_Svelte_dans_la_chaine_est_EXPRIMEE_aussi(tmp_path: Path) -> None:
    """`href="{lien}"` est une chaine qui PORTE une expression : la prendre au mot accuserait un
    lien dont la destination vaut « {lien} »."""
    cible = _produit_composant(tmp_path, "HeaderEn.svelte", _SVELTE_JUSTE)

    _releve, exprimees, _ = interface._relever_composants(cible)

    assert exprimees == 1


def test_une_liaison_v_bind_est_reconnue_comme_une_liaison(tmp_path: Path) -> None:
    liens = interface._liens_jsx(
        '<router-link v-bind:to="calcule">x</router-link>', interface._GRAMMAIRES[".vue"]
    )
    assert liens and liens[0]["exprimee"] and liens[0]["destination"] is None


def test_la_liaison_l_emporte_sur_l_attribut_statique_de_meme_nom(tmp_path: Path) -> None:
    """`to="/mort" :to="vivant"` — c est la liaison qui gagne a l execution. Juger la morte
    aurait accuse (ou blanchi) un lien qui n existe pas."""
    liens = interface._liens_jsx(
        '<router-link to="/mort" :to="vivant">x</router-link>', interface._GRAMMAIRES[".vue"]
    )
    assert liens and liens[0]["exprimee"] and liens[0]["destination"] is None


def test_le_dialecte_reellement_lu_se_DECLARE_au_rapport(tmp_path: Path) -> None:
    cible = _produit_composant(tmp_path, "HeaderEn.vue", _VUE_JUSTE)

    _releve, _exprimees, declarations = interface._relever_composants(cible)

    assert any("`.vue`" in ligne for ligne in declarations), declarations


def test_le_scanner_JSX_reste_intact(tmp_path: Path) -> None:
    """TEMOIN de non-regression : le nom d attribut accepte desormais `:` et `@` en tete pour
    Vue. Le JSX d origine doit continuer de se lire exactement pareil."""
    liens = interface._liens_jsx('<Link href="/en/blog" onClick={() => f(a > b)}>Blog</Link>')

    assert liens and liens[0]["destination"] == "/en/blog"
    assert not liens[0]["exprimee"]


# ==============================================================================================
# Levee 3 — le lexique est une table, et il est declarable
# ==============================================================================================
def _build_langue(racine: Path, texte_sous_fr: str) -> Path:
    """Un build a deux locales PREFIXEES : `/fr` et `/en`. La page `/fr` porte `texte_sous_fr`."""
    build = racine / "dist"
    (build / "fr").mkdir(parents=True)
    (build / "en").mkdir(parents=True)
    (build / "index.html").write_text(
        _MENU.format(lang="fr", titre="Racine", entrees=_entrees("/fr", "/en"), corps=_CORPS_FR),
        encoding="utf-8",
    )
    (build / "fr" / "index.html").write_text(
        _MENU.format(lang="fr", titre="Accueil", entrees=_entrees("/fr", "/en"),
                     corps=texte_sous_fr),
        encoding="utf-8",
    )
    (build / "en" / "index.html").write_text(
        _MENU.format(lang="en", titre="Home", entrees=_entrees("/fr", "/en"), corps=_CORPS_EN),
        encoding="utf-8",
    )
    return racine


def test_rouge_de_l_ANGLAIS_servi_sous_une_locale_francaise_est_nomme(tmp_path: Path) -> None:
    """Le second couple, celui que le pan ne savait pas voir : le cas SYMETRIQUE de celui du
    15/08. Un produit dont les pages `/fr` rendent de l anglais passait sans un mot."""
    cible = _build_langue(tmp_path, _CORPS_EN)

    message = _constats_i18n(cible)["i18n:route:fr:/"]

    assert "« en »" in message and "mots-outils en" in message, message


def test_vert_du_francais_servi_sous_la_locale_francaise_ne_l_est_pas(tmp_path: Path) -> None:
    """Second sens, non negociable : le lexique francais ne doit pas condamner une page
    francaise servie sous `/fr`. Sous la locale L, seuls les lexiques M != L sont mesures."""
    cible = _build_langue(tmp_path, _CORPS_FR)

    assert "i18n:route:fr:/" not in _constats_i18n(cible)


def test_les_deux_lexiques_ne_partagent_aucun_mot(tmp_path: Path) -> None:
    """La condition du controle : un mot present dans les deux ferait monter la densite d une
    page saine dans les deux sens, c est-a-dire accuserait a tort des deux cotes."""
    assert not (i18n.MOTS_OUTILS_FR & i18n.MOTS_OUTILS_EN)


def test_un_lexique_DECLARE_par_le_projet_est_retenu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """« Parametrable » : une langue de plus sans toucher au code de la forge."""
    fichier = tmp_path / "lexiques.json"
    fichier.write_text(
        json.dumps({"de": ["der", "die", "das", "und", "mit", "auf", "fuer", "ist", "sind",
                           "nicht", "eine", "einen", "einem", "dass", "auch", "wird", "werden",
                           "haben", "kann", "aber", "durch", "beim", "diese", "dieser"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("FORGE_TESTS_I18N_LEXIQUES", str(fichier))

    table = i18n.lexiques()

    assert "de" in table and len(table["de"]) >= 20
    assert {"fr", "en"} <= set(table)  # les lexiques du code restent


def test_un_lexique_declare_TROP_COURT_est_refuse_et_le_motif_se_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un lexique de trois mots ne discrimine rien : le retenir fabriquerait des constats au
    hasard. Le refus est DECLARE, jamais silencieux."""
    fichier = tmp_path / "lexiques.json"
    fichier.write_text(json.dumps({"de": ["der", "die", "das"]}), encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_LEXIQUES", str(fichier))

    retenus, motifs = i18n._lexiques_declares()

    assert "de" not in retenus
    assert any("moins de" in motif for motif in motifs), motifs


def test_un_fichier_de_lexiques_introuvable_se_dit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORGE_TESTS_I18N_LEXIQUES", str(tmp_path / "absent.json"))

    retenus, motifs = i18n._lexiques_declares()

    assert not retenus
    assert any("introuvables" in motif for motif in motifs), motifs


def test_le_rapport_DIT_contre_quels_lexiques_il_a_mesure(tmp_path: Path) -> None:
    """« aucun anglais detecte » et « la langue n a ete mesuree contre aucun lexique » ne sont
    pas le meme rapport, et seul le premier se verifie."""
    sortie = i18n.analyser(_build_langue(tmp_path, _CORPS_FR))

    mesures = [ligne for ligne in sortie.non_juge if "jugee contre les lexiques" in ligne]
    assert mesures, sortie.non_juge
    assert "fr (" in mesures[0] and "en (" in mesures[0], mesures[0]
    assert "aucun lexique declare par le projet" in mesures[0], mesures[0]


# ==============================================================================================
# Levee 4 — la locale se lit aussi dans la configuration du framework
# ==============================================================================================
_CONFIG_NEXT = (
    "const nextConfig = {\n"
    "  i18n: { locales: ['fr', 'en'], defaultLocale: 'fr' },\n"
    "};\nexport default nextConfig;\n"
)
# Le patron d INS-0001 : routage par segment DYNAMIQUE, aucun segment de locale litteral.
_PAGES_DYNAMIQUES = ("app/[locale]/page.tsx", "app/[locale]/tarifs/page.tsx")
_ENTETE_ANGLAIS_FAUX = """
export default function HeaderEn() {
  return (
    <header>
      <a href="/tarifs"><img src="/logo.svg" alt="le logo du site" /></a>
    </header>
  );
}
"""
# Le MEME composant, correct : le logo de l en-tete anglais mene a l accueil anglais.
_ENTETE_ANGLAIS_JUSTE = """
export default function HeaderEn() {
  return (
    <header>
      <a href="/en"><img src="/logo.svg" alt="le logo du site" /></a>
    </header>
  );
}
"""


def _produit_dynamique(racine: Path, *, avec_config: bool, entete: str) -> Path:
    for page in _PAGES_DYNAMIQUES:
        chemin = racine / page
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("export default function Page() { return <main />; }\n", "utf-8")
    composants = racine / "components"
    composants.mkdir(parents=True, exist_ok=True)
    (composants / "HeaderEn.tsx").write_text(entete, encoding="utf-8")
    if avec_config:
        (racine / "next.config.mjs").write_text(_CONFIG_NEXT, encoding="utf-8")
    return racine


def test_les_locales_sont_lues_dans_la_configuration_du_framework(tmp_path: Path) -> None:
    produit = _produit_dynamique(tmp_path, avec_config=True, entete=_ENTETE_ANGLAIS_JUSTE)
    assert interface.locales_declarees(produit) == {"fr", "en"}


def test_rouge_un_logo_anglais_faux_est_attrape_grace_a_la_CONFIGURATION(tmp_path: Path) -> None:
    """La configuration d INS-0001 : routage `app/[locale]/…`, donc AUCUN segment de locale
    litteral. Sans la levee, `arbre["locales"]` sortait vide et l accueil de `HeaderEn.tsx` etait
    suppose etre « / » — le pan disait alors la mauvaise chose, ou rien."""
    motifs = _motifs(_produit_dynamique(
        tmp_path, avec_config=True, entete=_ENTETE_ANGLAIS_FAUX
    ))

    assert any("logo" in motif and "/en" in motif for motif in motifs), motifs


def test_vert_le_meme_logo_CORRECT_passe_grace_a_la_configuration(tmp_path: Path) -> None:
    """Second sens : la levee ne rend pas le pan bavard. Le logo anglais qui mene a `/en` est
    juste, et il faut la configuration pour le SAVOIR — sans elle, l accueil attendu valait « / »
    et ce lien parfaitement correct sortait ACCUSE. C est le faux positif que la levee ote."""
    assert _motifs(_produit_dynamique(
        tmp_path, avec_config=True, entete=_ENTETE_ANGLAIS_JUSTE
    )) == []


def test_temoin_sans_configuration_le_jugement_de_locale_est_SUSPENDU_et_dit(
    tmp_path: Path,
) -> None:
    """Le temoin de la levee : sans configuration ni segment litteral, la racine d une locale
    n est pas connaissable. La deviner accusait le logo correct ci-dessus ; le pan suspend donc
    son jugement — et il le DIT, plutot que de se taire (un cas non resolu degrade en non juge
    motive, jamais en finding)."""
    cible = _produit_dynamique(tmp_path, avec_config=False, entete=_ENTETE_ANGLAIS_JUSTE)

    releve, _exprimees, declarations = interface._relever_composants(cible)

    assert not [entree for entree in releve if entree["motif"]]
    assert any("segment DYNAMIQUE" in ligne and "NON JUGES" in ligne for ligne in declarations), (
        declarations
    )


def test_la_provenance_des_locales_se_DECLARE(tmp_path: Path) -> None:
    _releve, _exprimees, declarations = interface._relever_composants(
        _produit_dynamique(tmp_path, avec_config=True, entete=_ENTETE_ANGLAIS_JUSTE)
    )

    assert any(
        "configuration du framework" in ligne and "en, fr" in ligne for ligne in declarations
    ), declarations


def test_une_valeur_qui_n_est_pas_une_locale_connue_n_en_devient_pas_une(tmp_path: Path) -> None:
    """Prendre `['default', 'legacy']` pour des locales fabriquerait une parite imaginaire, donc
    des constats contre des liens parfaitement sains."""
    (tmp_path / "next.config.mjs").write_text(
        "export default { i18n: { locales: ['default', 'legacy'] } };\n", encoding="utf-8"
    )

    assert interface.locales_declarees(tmp_path) == set()


def test_une_locale_regionale_est_ramenee_a_sa_langue(tmp_path: Path) -> None:
    """`fr-BE` et `en-GB` prefixent des routes dont la langue est `fr` et `en`."""
    (tmp_path / "next.config.mjs").write_text(
        "export default { i18n: { locales: ['fr-BE', 'en-GB'], defaultLocale: 'fr-BE' } };\n",
        encoding="utf-8",
    )

    assert interface.locales_declarees(tmp_path) == {"fr", "en"}


def test_l_arborescence_litterale_continue_de_parler_seule(tmp_path: Path) -> None:
    """TEMOIN : la levee AJOUTE une source, elle ne remplace pas l ancienne. Un produit dont les
    locales sont dans les chemins et qui n a aucune configuration doit rester jugeable."""
    for page in _PAGES_NEXT:
        chemin = tmp_path / page
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("export default function Page() { return <main />; }\n", "utf-8")

    arbre = interface._arborescence(tmp_path)

    assert arbre["locales_litterales"] == {"en"}
    assert arbre["locales_configurees"] == set()
    assert arbre["locales"] == {"en"}
