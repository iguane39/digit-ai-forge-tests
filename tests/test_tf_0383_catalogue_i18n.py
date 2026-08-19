"""TF-0383 — le pan i18n lisait le BUILD SERVI et jamais le CATALOGUE DE CHAÎNES.

Le fait, mesuré le 19/08/2026 sur un produit client livré dont le `CLAUDE.md` déclare
« i18n 7 languages (fr, en, es, pt, it, ro, pl), auto-detect from browser, **fallback French** » :
son catalogue porte **245 clés** en `fr` et en `en`, et **95** en `es`, `it`, `pl`, `pt`, `ro`.
Soit **150 clés manquantes par locale, 61 %** — 750 chaînes servies en français par le repli, sans
qu'aucun message ne le signale.

**Et le pan rendait `SKIP`, 0 finding.** Il lit le build servi, et sa limite déclarée dit « seule
une locale PRÉFIXÉE est jugée sur sa langue ». Ce produit choisit sa langue par détection
navigateur, sans préfixe d'URL : toutes les routes existent dans toutes les locales et le repli
remplit les trous. Le pan était **structurellement aveugle** à cette forme — la forme dominante du
parc (3 projets sur 22 portent un catalogue, aucun n'est préfixé).

Ce que ces tests tiennent, dans les deux sens :

  · les trois contrôles **constatent** (complétude, paramètres, constance des libellés d'action) ;
  · ils **restent muets** sur un catalogue sain — sans quoi un contrôle qui hurle sur tout
    passerait pour un contrôle ;
  · un catalogue qu'on ne sait pas lire est **NOMMÉ**, jamais confondu avec une absence de
    catalogue ;
  · et la **justesse** d'une traduction est déclarée non jugée : c'est la condition pour que les
    trois autres soient crus.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import catalogue_i18n as catalogue
from forge_tests.adaptateurs import i18n


def _catalogue(racine: Path, contenus: dict[str, dict], dossier: str = "src/i18n/locales") -> Path:
    cible = racine / dossier
    cible.mkdir(parents=True, exist_ok=True)
    for locale, objet in contenus.items():
        (cible / f"{locale}.json").write_text(
            json.dumps(objet, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return cible


# --- (d) COMPLÉTUDE — le cas mesuré ------------------------------------------------------------
def test_une_locale_trouee_est_constatee_avec_son_COMPTE_et_ses_CLES(tmp_path: Path) -> None:
    """Le compte exact d'abord, les premières clés ensuite : un total anonyme ne se corrige pas,
    et 150 clés listées ne se lisent pas."""
    _catalogue(tmp_path, {
        "fr": {"accueil": {"titre": "Bonjour", "sous_titre": "Bienvenue"}, "nav": {"aide": "Aide"}},
        "en": {"accueil": {"titre": "Hello", "sous_titre": "Welcome"}, "nav": {"aide": "Help"}},
        "es": {"accueil": {"titre": "Hola"}},
    })

    lus, _ = catalogue.catalogues(tmp_path)
    verdict = catalogue.juger(lus["src/i18n/locales"])

    assert verdict["union"] == 3
    assert verdict["manquantes"]["es"] == ["accueil.sous_titre", "nav.aide"]
    assert "fr" not in verdict["manquantes"] and "en" not in verdict["manquantes"]


def test_la_completude_se_mesure_contre_l_UNION_jamais_une_locale_elue(tmp_path: Path) -> None:
    """Choisir une locale de référence serait une inférence. Le pan mesure déjà la parité de
    routes « contre l'UNION des routes de toutes les locales » — même règle, même raison."""
    _catalogue(tmp_path, {
        "fr": {"a": "A", "b": "B"},
        "en": {"a": "A", "c": "C"},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert verdict["union"] == 3, "a + b + c, aucune locale ne fait autorite"
    assert verdict["manquantes"] == {"en": ["b"], "fr": ["c"]}


# --- (e) INTÉGRITÉ DES PARAMÈTRES -------------------------------------------------------------
def test_un_parametre_PERDU_est_nomme_quand_la_MAJORITE_fait_foi(tmp_path: Path) -> None:
    """Un paramètre perdu rend un trou dans la phrase servie à l'utilisateur — mais l'affirmer
    demande de savoir qui fait foi. Ici deux locales sur trois s'accordent : la majorité tranche,
    et la troisième est nommée avec ce qu'elle a perdu."""
    _catalogue(tmp_path, {
        "fr": {"salut": "Bonjour {{nom}}, vous avez {{n}} messages"},
        "de": {"salut": "Hallo {{nom}}, Sie haben {{n}} Nachrichten"},
        "en": {"salut": "Hello {{nom}}, you have messages"},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert len(verdict["divergences"]) == 1
    ecart = verdict["divergences"][0]
    assert ecart["locale"] == "en"
    assert ecart["perdus"] == ["n"] and ecart["inventes"] == []
    assert "majorite" in ecart["reference"], "le verdict DIT qui fait foi"


def test_un_parametre_INVENTE_est_nomme_quand_la_MAJORITE_fait_foi(tmp_path: Path) -> None:
    _catalogue(tmp_path, {
        "fr": {"salut": "Bonjour {{nom}}"},
        "de": {"salut": "Hallo {{nom}}"},
        "en": {"salut": "Hello {{nom}}, ref {{reference}}"},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert verdict["divergences"][0]["locale"] == "en"
    assert verdict["divergences"][0]["inventes"] == ["reference"]


def test_SANS_majorite_le_desaccord_est_NOMME_sans_prendre_parti(tmp_path: Path) -> None:
    """DÉFAUT DE MA PREMIÈRE ÉCRITURE, révélé par ce cas. Je prenais pour référence le jeu de
    paramètres LE PLUS RICHE : sur deux locales, cela transforme mécaniquement un paramètre
    INVENTÉ chez l'une en paramètre PERDU chez l'autre. Rien dans la donnée ne permet de
    distinguer les deux, et le prétendre était une affirmation que la donnée ne porte pas."""
    _catalogue(tmp_path, {
        "fr": {"salut": "Bonjour {{nom}}"},
        "en": {"salut": "Hello {{nom}}, ref {{reference}}"},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert len(verdict["divergences"]) == 1
    ecart = verdict["divergences"][0]
    assert ecart["reference"] == "aucune majorite"
    assert ecart["perdus"] == [] and ecart["inventes"] == [], "on ne tranche pas"
    assert ecart["desaccord"] == {"en": ["nom", "reference"], "fr": ["nom"]}


def test_l_ORDRE_des_parametres_n_est_PAS_compare(tmp_path: Path) -> None:
    """Deux langues n'ordonnent pas leurs paramètres pareil, et l'exiger serait un faux défaut.
    Sans ce test, la règle serait juste par hasard sur les fixtures et fausse sur du réel."""
    _catalogue(tmp_path, {
        "fr": {"phrase": "{{a}} avant {{b}}"},
        "de": {"phrase": "{{b}} kommt nach {{a}}"},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert verdict["divergences"] == []


def test_les_trois_familles_de_parametres_sont_lues() -> None:
    assert catalogue.parametres("Bonjour {{nom}}") == {"nom"}
    assert catalogue.parametres("Bonjour {nom}") == {"nom"}
    assert catalogue.parametres("Bonjour %(nom)s") == {"nom"}
    assert catalogue.parametres("%s et %s") == {"%1", "%2"}, "sans nom, on n affirme que le NOMBRE"


# --- (f) CONSTANCE — resserrée aux libellés d'ACTION -------------------------------------------
def test_un_libelle_d_ACTION_rendu_de_deux_facons_est_constate(tmp_path: Path) -> None:
    """`voix.md` §Actions : « un libellé, un seul, d'un bout à l'autre du parcours » — « Publier »
    produit « Publié », jamais « Envoyer » puis « Soumis »."""
    _catalogue(tmp_path, {
        "fr": {"actions": {"publier": "Publish", "envoyer": "Publish"}},
        "en": {"actions": {"publier": "Publish", "envoyer": "Submit"}},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert len(verdict["inconstances"]) == 1
    assert verdict["inconstances"][0]["locale"] == "en"
    assert sorted(verdict["inconstances"][0]["rendus"]) == ["Publish", "Submit"]


def test_une_chaine_HORS_action_ne_declenche_PAS_la_constance(tmp_path: Path) -> None:
    """Le resserrage, et il est mesuré : étendu à toutes les chaînes, ce contrôle rendait
    6 constats sur un catalogue réel, 6 FAUX POSITIFS — du français correct (« Tous »/« Toutes »,
    « Approuvé »/« Approuvée », accord en genre). Un contrôle à ce taux de bruit ne se corrige
    pas, il se fait ignorer."""
    _catalogue(tmp_path, {
        "fr": {"statut": {"approuvee": "approved"}, "verdict": {"approuve": "approved"}},
        "en": {"statut": {"approuvee": "Approuvée"}, "verdict": {"approuve": "Approuvé"}},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert verdict["inconstances"] == [], "aucun segment d action : pas de constat"


def test_est_action_reconnait_au_SEGMENT_pas_a_la_sous_chaine() -> None:
    """`transaction.total` contient « action » sans être une action."""
    assert catalogue.est_action("actions.publier")
    assert catalogue.est_action("bouton.envoyer")
    assert catalogue.est_action("cta_principal.libelle")
    assert not catalogue.est_action("transaction.total")
    assert not catalogue.est_action("statut.approuvee")


# --- Le sens qui manquerait : le silence sur un catalogue SAIN ---------------------------------
def test_un_catalogue_SAIN_ne_produit_AUCUN_constat(tmp_path: Path) -> None:
    """Sans cette moitié, un contrôle qui hurlerait sur tout passerait ce fichier de test."""
    _catalogue(tmp_path, {
        "fr": {"accueil": {"titre": "Bonjour {{nom}}"}, "actions": {"publier": "Publier"}},
        "en": {"accueil": {"titre": "Hello {{nom}}"}, "actions": {"publier": "Publish"}},
    })

    verdict = catalogue.juger(catalogue.catalogues(tmp_path)[0]["src/i18n/locales"])

    assert verdict["manquantes"] == {}
    assert verdict["divergences"] == []
    assert verdict["inconstances"] == []


# --- Ce qu'on ne sait pas lire est NOMMÉ -------------------------------------------------------
def test_un_catalogue_TYPESCRIPT_est_nomme_jamais_confondu_avec_une_absence(tmp_path: Path) -> None:
    """La forme réelle d'un autre produit du parc (`src/i18n/messages.ts`). Le taire ferait
    conclure « rien à mesurer » sur un produit qui a tout à mesurer."""
    dossier = tmp_path / "src" / "i18n"
    dossier.mkdir(parents=True)
    (dossier / "messages.ts").write_text("export const messages = {}", encoding="utf-8")

    lus, non_lus = catalogue.catalogues(tmp_path)

    assert lus == {}, "aucun JSON par locale : rien de comparable"
    assert len(non_lus) == 1
    assert "messages.ts" in non_lus[0]
    assert "NON LU" in non_lus[0]


def test_un_JSON_ILLISIBLE_est_refuse_sans_perdre_les_autres(tmp_path: Path) -> None:
    """Croire « locale vide » parce que le fichier est cassé serait le pire des deux."""
    dossier = _catalogue(tmp_path, {"fr": {"a": "A"}, "en": {"a": "A"}})
    (dossier / "es.json").write_text("{ ceci n est pas du JSON", encoding="utf-8")

    lus, non_lus = catalogue.catalogues(tmp_path)

    assert sorted(lus["src/i18n/locales"]) == ["en", "fr"]
    assert any("es.json" in m and "illisible" in m for m in non_lus)
    assert any("jamais compté comme locale vide" in m for m in non_lus)


def test_un_dossier_a_UNE_seule_locale_n_est_pas_un_catalogue(tmp_path: Path) -> None:
    """Rien à comparer : une locale seule ne prouve ni complétude ni manque."""
    _catalogue(tmp_path, {"fr": {"a": "A"}})

    assert catalogue.catalogues(tmp_path)[0] == {}


def test_les_dependances_ne_sont_PAS_parcourues(tmp_path: Path) -> None:
    """Ce contrôle tourne sur TOUT audit : descendre dans `node_modules` serait un coût payé
    partout, tout le temps — et y trouverait les catalogues d'autrui."""
    _catalogue(tmp_path, {"fr": {"a": "A"}, "en": {"a": "A"}},
               dossier="node_modules/une-dep/locales")

    assert catalogue.catalogues(tmp_path)[0] == {}


# --- Le câblage : le pan MESURE là où il rendait SKIP ------------------------------------------
def test_le_pan_JUGE_le_catalogue_MEME_SANS_build_servi(tmp_path: Path) -> None:
    """Le cœur de l'item. Un produit à repli de langue sans préfixe d'URL n'a rien à montrer au
    build (toutes les routes existent partout, remplies par la langue par défaut) et tout à
    montrer au catalogue. Avant cette levée : SKIP, 0 finding."""
    _catalogue(tmp_path, {
        "fr": {"a": "A", "b": "B", "c": "C"},
        "en": {"a": "A", "b": "B", "c": "C"},
        "es": {"a": "A"},
    })
    (tmp_path / "package.json").write_text('{"dependencies":{"i18next":"1"}}', encoding="utf-8")

    sortie = i18n.analyser(tmp_path)

    assert i18n.build_servi(tmp_path) is None, "aucun build : c est la situation mesuree"
    assert sortie.verdict == "FAIL", "le pan rendait SKIP avec 0 finding sur ce cas"
    assert any("2 cle(s) MANQUANTE(S)" in f.message for f in sortie.findings)
    assert any("es" in f.localisation for f in sortie.findings)


def test_le_pan_DIT_que_les_controles_du_build_ne_sont_pas_joues(tmp_path: Path) -> None:
    """Loi 3 : mesurer une moitié et se taire sur l'autre ferait lire le verdict comme complet."""
    _catalogue(tmp_path, {"fr": {"a": "A"}, "en": {"a": "A"}})

    sortie = i18n.analyser(tmp_path)

    declare = " ".join(sortie.non_juge)
    assert "AUCUN build servi lu" in declare
    assert "parite de routes" in declare and "langue du contenu ne sont pas joues" in declare


def test_le_pan_reste_muet_sur_un_produit_SANS_catalogue_ni_build(tmp_path: Path) -> None:
    """Garde anti-régression : l'immense majorité des produits est monolingue et doit rester NA,
    sans quoi tous les rapports deviendraient PARTIELS pour un pan qui n'a rien à mesurer."""
    (tmp_path / "README.md").write_text("un produit monolingue", encoding="utf-8")

    sortie = i18n.analyser(tmp_path)

    assert sortie.verdict == "NA"


def test_la_JUSTESSE_est_declaree_NON_JUGEE() -> None:
    """La condition pour que les trois contrôles soient crus. La doctrine du socle de marque le dit
    déjà pour la voix, et se transpose mot pour mot."""
    declare = " ".join(catalogue.NON_JUGE)

    assert "la JUSTESSE d une traduction n est PAS jugee" in declare
    assert "peut etre integralement mal traduit" in declare
    assert "la justesse n est pas decidable par script" in declare
    # et la contradiction possible entre les deux points d observation est un RÉSULTAT
    assert "cette contradiction est un RESULTAT" in declare
