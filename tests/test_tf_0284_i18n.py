"""TF-0284 — le pan `i18n` : parité entre locales, mesurée sur le build servi.

**Le trou, daté.** Étude du 15/08/2026 : aucun oracle de l écosystème ne jugeait le multilingue.
Trois défauts réels, tous trouvés À LA MAIN en quelques minutes sur un produit en production,
tous scriptables sans modèle de langage :

  - une route française sur 201 sans équivalent anglais ;
  - un menu anglais à 4 entrées quand le français en portait 9 — non détecté depuis juin ;
  - 9 pages sur 200 servies sous `/en` avec du contenu FRANÇAIS.

Les trois défauts vivent dans le BUILD SERVI des bancs HISTORIQUES du dépôt
(`fixtures/banc-rouge/dist`, `fixtures/banc-vert/dist`) : le banc rouge les porte, le banc vert
porte les mêmes pages corrigées. Le pan est joué de bout en bout dessus, exactement comme il le
sera sur un produit.

TF-0293 — ces pages vivaient d abord dans des bancs SÉPARÉS (`fixtures/i18n-rouge`,
`fixtures/i18n-vert`), posés hors des bancs historiques parce qu une campagne parallèle
travaillait sur le même dépôt le 15/08 et que le corpus S-01 mesure le banc vert à zéro finding
bloquant. Le pan était donc prouvé par ces 21 tests, mais ABSENT du corpus qui prononce S-01 : la
recette du dépôt ne le mesurait pas. Les pages sont désormais portées au build servi des bancs, et
les trois défauts ont leurs entrées de corpus (H-17, H-18, H-19). Le dossier `dist\\` est le choix
qui ne déplace la surface d aucun autre pan : `interface` et `securite` l excluent par convention,
`accessibilite` et `visuel` tirent leurs routes de la table de routage du front, `prompts` ne lit
pas le `.html`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, i18n

BANCS = Path(__file__).resolve().parent.parent / "fixtures"
ROUGE, VERT = BANCS / "banc-rouge", BANCS / "banc-vert"
# Le build SERVI de chaque banc — ce que le pan lit, et ce que la recette mesure au corpus.
BUILD_ROUGE, BUILD_VERT = ROUGE / "dist", VERT / "dist"


@pytest.fixture(autouse=True)
def _sans_build_declare(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le `.env` de l opérateur ne doit jamais désigner le build d un autre projet pendant la
    suite : le pan lirait alors autre chose que ce que le test croit lui montrer."""
    monkeypatch.delenv("FORGE_TESTS_I18N_BUILD", raising=False)


def _constats(cible: Path) -> dict[str, str]:
    return {f.id: f.message for f in i18n.analyser(cible).findings}


# --- Banc ROUGE : les trois défauts réels du 15/08 ---------------------------------------------
def test_rouge_une_route_sans_equivalent_dans_une_locale_est_nommee() -> None:
    """(a) — `/tarifs` existe en français, `/en/tarifs` n a jamais été construit."""
    message = _constats(ROUGE)["i18n:route:en:/tarifs"]
    assert "/en/tarifs" in message and "absente du build" in message


def test_rouge_le_menu_ampute_d_une_locale_est_nomme_avec_son_ecart() -> None:
    """(b) — 2 entrées contre 4 : le défaut qui a vécu de juin au 15/08 sans être vu."""
    message = _constats(ROUGE)["i18n:navigation:en"]
    assert "2 entree(s) contre 4" in message


def test_rouge_une_page_anglaise_servie_en_francais_est_nommee() -> None:
    """(c) — le câblage de données renvoie la langue par défaut quelle que soit la locale."""
    message = _constats(ROUGE)["i18n:route:en:/blog"]
    assert "FRANÇAIS" in message and "heuristique" in message


def test_rouge_trois_constats_et_TROIS_SEULEMENT() -> None:
    """Le compte exact. Un quatrième serait un faux positif — et un faux positif sur une page
    saine coûte la confiance qu on venait chercher."""
    assert len(_constats(ROUGE)) == 3


def test_rouge_le_pan_echoue_et_publie_sa_couverture() -> None:
    sortie = i18n.analyser(ROUGE)
    assert sortie.verdict == "FAIL"
    assert sortie.surface["inventorie"] == 8  # 2 locales x 4 routes attendues
    assert sortie.surface["exerce"] == 6
    assert sortie.surface["seuil"] == 1.0


# --- Banc VERT : les mêmes pages, corrigées -----------------------------------------------------
def test_vert_aucun_constat_sur_le_banc_corrige() -> None:
    sortie = i18n.analyser(VERT)
    assert sortie.verdict == "PASS"
    assert sortie.findings == []
    assert sortie.surface["ratio"] == 1.0


def test_vert_la_locale_par_defaut_n_est_jamais_jugee_sur_sa_langue() -> None:
    """Les pages de `/` sont en français et c est la langue du site : les juger avec le lexique
    français condamnerait tout produit francophone dès la première page."""
    assert all("FRANÇAIS" not in message for message in _constats(VERT).values())


# --- L heuristique de langue, dans les deux sens ------------------------------------------------
def test_l_heuristique_separe_un_texte_francais_d_un_texte_anglais() -> None:
    """La marge est ce qui rend un seuil heuristique opposable : elle se mesure, ici, en clair."""
    francais = (
        "Cette page est servie dans la langue par defaut du site, qui est le francais. Elle "
        "presente les activites de la maison et les moyens de nous joindre."
    )
    anglais = (
        "This page is served under the English locale prefix. It introduces what the company "
        "does, the teams behind the work and the ways to reach us."
    )
    densite_fr, _ = i18n.densite_mots_outils_fr(francais)
    densite_en, _ = i18n.densite_mots_outils_fr(anglais)
    assert densite_fr >= i18n.SEUIL_DENSITE_FR * 2, densite_fr
    assert densite_en < i18n.SEUIL_DENSITE_FR / 2, densite_en


def test_le_lexique_exclut_les_mots_ambigus() -> None:
    """`on`, `en`, `a`, `plus`, `car`, `son`, `no` sont anglais AUSSI : les compter ferait monter
    la densité d une page saine, c est-à-dire accuserait à tort."""
    for mot in ("on", "en", "a", "as", "no", "son", "plus", "car", "pas"):
        assert mot not in i18n.MOTS_OUTILS_FR


def test_une_page_trop_courte_n_est_pas_jugee_sur_sa_langue(tmp_path: Path) -> None:
    """Sous 40 mots la densité n est plus un signal, c est du bruit — et un pan qui juge du
    bruit produit des constats qu on apprend à ignorer."""
    build = tmp_path / "out"
    (build / "en").mkdir(parents=True)
    (build / "index.html").write_text(
        "<html lang=fr><body><nav><a href=/>Accueil</a></nav><p>Bonjour le monde.</p></body>",
        encoding="utf-8",
    )
    (build / "en" / "index.html").write_text(
        "<html lang=en><body><nav><a href=/en>Home</a></nav><p>Le site est en francais.</p>"
        "</body>",
        encoding="utf-8",
    )
    assert i18n.analyser(tmp_path).findings == []


# --- Découverte du build, et refus de deviner ---------------------------------------------------
def test_le_build_declare_l_emporte_sur_la_decouverte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORGE_TESTS_I18N_BUILD", str(BUILD_ROUGE))
    assert i18n.build_servi(tmp_path) == BUILD_ROUGE


def test_un_produit_monolingue_sort_en_NA_avec_sa_preuve(tmp_path: Path) -> None:
    """Ne pas être multilingue n est pas un défaut d internationalisation."""
    build = tmp_path / "dist"
    build.mkdir()
    (build / "index.html").write_text("<html lang=fr><body><h1>Seul</h1></body>", encoding="utf-8")
    sortie = i18n.analyser(tmp_path)
    assert sortie.verdict == "NA"
    assert "aucune page prefixee par une locale" in sortie.non_juge[-1]


def test_un_produit_sans_build_ni_signe_i18n_sort_en_NA(tmp_path: Path) -> None:
    """Sinon TOUS les rapports de TOUS les produits deviendraient PARTIELS pour un pan qui n a
    rien à mesurer chez eux."""
    (tmp_path / "app.py").write_text("print('bonjour')\n", encoding="utf-8")
    sortie = i18n.analyser(tmp_path)
    assert sortie.verdict == "NA"
    assert "n est pas multilingue" in sortie.non_juge[-1]


def test_un_produit_qui_SE_DIT_multilingue_sans_build_sort_en_SKIP(tmp_path: Path) -> None:
    """Le manque est alors le BUILD, pas le sujet : c est un pan NON MESURÉ, et il se répare en
    fournissant un dossier — jamais un « sans objet » qui l enterrerait."""
    (tmp_path / "package.json").write_text('{"dependencies": {"next-intl": "^3"}}', "utf-8")
    sortie = i18n.analyser(tmp_path)
    assert sortie.verdict == "SKIP"
    assert "FORGE_TESTS_I18N_BUILD" in sortie.non_juge[-1]
    assert i18n.CHAMPS_REQUIS == ("FORGE_TESTS_I18N_BUILD",)


def test_les_pages_de_service_ne_comptent_pas_dans_la_parite(tmp_path: Path) -> None:
    """Une `404.html` n est pas une route du produit : l exiger dans chaque locale fabriquerait
    un manque qui n en est pas un."""
    build = tmp_path / "out"
    (build / "en").mkdir(parents=True)
    for chemin in (build / "index.html", build / "en" / "index.html"):
        chemin.write_text("<html><body><nav><a href=/>x</a></nav></body>", encoding="utf-8")
    (build / "404.html").write_text("<html><body>perdu</body>", encoding="utf-8")
    assert i18n.analyser(tmp_path).findings == []


# --- Intégration au framework -------------------------------------------------------------------
def test_le_pan_est_enregistre_et_attendu() -> None:
    assert REGISTRE["i18n-build-servi"] is i18n
    assert i18n.PAN in PANS_ATTENDUS


def test_chaque_constat_recoit_une_suite_a_donner() -> None:
    """Un constat sans destinataire est un constat qui ne sera pas traité — et une classe
    inconnue de `actions.py` repartirait vers la forge au lieu du développeur."""
    from forge_tests.actions import classifier

    findings = [{**vars(f), "pan": "i18n"} for f in i18n.analyser(ROUGE).findings]
    actions = classifier(findings)
    assert len(actions) == 3
    assert all("DÉFAUT D'AUDITEUR" not in action["attendu"] for action in actions)
    assert {action["categorie"] for action in actions} == {"manuelle_dev"}


def test_le_chapitre_du_cahier_est_declare_et_son_axe_est_connu() -> None:
    """Un axe inconnu retombe sur « éléments non rattachés » : lisible, mais c est un repli."""
    from forge_tests.livrables.surface import chapitres

    codes = {chapitre["code"]: chapitre for chapitre in chapitres(REGISTRE)}
    assert codes["F6"]["titre"] == "Internationalisation"
    assert codes["F6"]["axe_connu"] is True


def test_les_constats_se_rangent_par_locale_dans_le_cahier() -> None:
    from forge_tests.livrables.surface import sous_chapitre

    assert sous_chapitre("locale", "i18n:route:en:/tarifs") == ("locale en", True)
    assert sous_chapitre("locale", "i18n:navigation:en") == ("locale en", True)


def test_l_inventaire_est_le_produit_cartesien_locales_x_routes() -> None:
    """Une route qui n existe que dans une langue occupe une case VIDE dans les autres : c est
    cette case qui devient un constat, et elle n existe que si l inventaire la pose."""
    inventorie = i18n.inventaire(ROUGE)
    assert len(inventorie) == 8
    assert "i18n:route:en:/tarifs" in {element.id for element in inventorie}
    assert all(element.pan == "i18n" for element in inventorie)


def test_les_deux_seuils_du_pan_sont_opposables_et_publies() -> None:
    """Un seuil qui vit en constante privée d un adaptateur n est pas opposable (A-3)."""
    from forge_tests.seuils import au_rapport

    publies = au_rapport()
    assert publies["couverture_surface_i18n"]["valeur"] == 1.0
    assert publies["densite_mots_outils_francais"]["valeur"] == 0.08
    assert "heuristique" in publies["densite_mots_outils_francais"]["porte_sur"]
