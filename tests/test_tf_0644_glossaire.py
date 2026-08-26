r"""TF-0644 — un nombre servi se confronte à la donnée, et le glossaire donne le mot par locale.

LE PREMIER CAS DE CE FICHIER EST LA CONTREPARTIE D'UNE DÉCISION HUMAINE, pas un test de plus.

Le 26/08, la voie (b) a été retenue : ce paquet LIT le glossaire Markdown du produit plutôt que de
faire redéclarer les termes dans un fichier machine. Une donnée, un seul endroit — et, en échange,
DEUX analyseurs du même format : celui-ci en Python, et `oracles\oracle-glossaire.mjs` en
JavaScript chez le pilot. C'est exactement la classe de défaut qui a coûté dix listes d'exclusion
divergentes (TF-0543).

Le coût a été nommé au moment de décider ; il est ici **câblé**. `test_conformite_au_gabarit_du_pilot`
fait lire à CE parseur le gabarit de référence du pilot — le fichier même que l'autre analyseur
juge — et vérifie qu'il y retrouve la structure attendue. Si le format dérive d'un côté, cette
recette rougit. Quand le gabarit n'est pas atteignable depuis ce poste, le cas est DÉCLARÉ non joué
plutôt que tenu pour vert : *le silence d'une sonde n'est pas un verdict.*
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from forge_tests import glossaire

GABARIT = """---
role: la terminologie opposable du projet — glossaire
verifie_le: 2026-08-26
---

# Glossaire — recette

## logement de vacances

- **categorie** : visibilite
- **pivot** : gîte

| locale | retenu | proscrits | portee | preuve | verifie_le |
|---|---|---|---|---|---|
| fr | gîte | aucun | partout | catalogue servi · usage du secteur | 2026-08-26 |
| en | cottage | aucun | partout | catalogue servi · complétions | 2026-08-26 |
"""


def _ecrire(tmp_path: Path, nom: str, contenu: str) -> Path:
    chemin = tmp_path / nom
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# ---------------------------------------------------------------------------------------------
# LA CONTREPARTIE DU CHOIX (b) — les deux analyseurs lisent le MÊME fichier de référence
# ---------------------------------------------------------------------------------------------

def _gabarit_du_pilot() -> Path | None:
    """Le gabarit de référence du pilot, s'il est atteignable depuis ce poste.

    Cherché par `FORGE_ROOT` d'abord — la variable que tout le parc emploie — puis à la place
    conventionnelle. Rien n'est deviné au-delà : un chemin inventé rendrait un SKIP indiscernable
    d'un vrai manque.
    """
    racines = []
    if os.environ.get("FORGE_ROOT"):
        racines.append(Path(os.environ["FORGE_ROOT"]))
    racines.append(Path(__file__).resolve().parents[2])
    for racine in racines:
        candidat = racine / "digit-ai-factory" / "gabarits" / "GLOSSAIRE.md"
        if candidat.exists():
            return candidat
    return None


def test_conformite_au_gabarit_du_pilot():
    """Ce parseur retrouve, dans le gabarit du pilot, ce que l'analyseur JavaScript y voit.

    Les trois termes et six lignes attendus ne sont pas un nombre magique : ce sont ceux que le
    gabarit porte, et que son propre oracle compte (« 3 terme(s) », « 6 ligne(s) »).
    """
    gabarit = _gabarit_du_pilot()
    if gabarit is None:
        pytest.skip(
            "gabarit `digit-ai-factory/gabarits/GLOSSAIRE.md` non atteignable depuis ce poste — "
            "la conformite des DEUX analyseurs du meme format n est PAS verifiee ici. Poser "
            "FORGE_ROOT, ou jouer cette recette sur un poste portant le parc"
        )
    lu = glossaire.lire(gabarit)
    assert lu["motif"] is None, f"le gabarit du pilot n est pas lu : {lu['motif']}"
    assert len(lu["termes"]) == 3, (
        f"{len(lu['termes'])} terme(s) lus au lieu de 3 — le format a derive d un cote. "
        "C est precisement le risque assume en choisissant la voie (b)"
    )
    lignes = [l for t in lu["termes"] for l in t["lignes"]]
    assert len(lignes) == 6, f"{len(lignes)} ligne(s) lues au lieu de 6"
    # Les champs que la confrontation emploie doivent exister, sinon elle est muette en silence.
    for terme in lu["termes"]:
        assert terme["pivot"], f"terme « {terme['nom']} » sans pivot — la jointure avec les faits est impossible"
        for ligne in terme["lignes"]:
            assert ligne["locale"] and ligne["retenu"], f"ligne incomplete dans « {terme['nom']} »"


# ---------------------------------------------------------------------------------------------
# LA LECTURE
# ---------------------------------------------------------------------------------------------

def test_lit_les_termes_et_leurs_locales(tmp_path):
    lu = glossaire.lire(_ecrire(tmp_path, "GLOSSAIRE.md", GABARIT))
    assert lu["motif"] is None
    assert len(lu["termes"]) == 1
    terme = lu["termes"][0]
    assert terme["pivot"] == "gîte"
    assert {l["locale"]: l["retenu"] for l in terme["lignes"]} == {"fr": "gîte", "en": "cottage"}


def test_un_fichier_qui_ne_se_declare_pas_glossaire_est_refuse_avec_son_motif(tmp_path):
    """La borne : sans elle, ce module lirait n importe quel Markdown comme du vocabulaire."""
    lu = glossaire.lire(_ecrire(tmp_path, "autre.md", "---\nrole: une note\n---\n\n## un titre\n"))
    assert lu["termes"] == []
    assert "glossaire" in (lu["motif"] or "")


def test_un_glossaire_absent_rend_un_motif_et_non_une_exception(tmp_path):
    lu = glossaire.lire(tmp_path / "nexiste-pas.md")
    assert lu["termes"] == []
    assert "absent" in (lu["motif"] or "")


# ---------------------------------------------------------------------------------------------
# LA CONFRONTATION — le cas fondateur, et ses bornes
# ---------------------------------------------------------------------------------------------

def _termes():
    return [{"nom": "logement", "categorie": "visibilite", "pivot": "gîte",
             "lignes": [{"locale": "fr", "retenu": "gîte"}, {"locale": "en", "retenu": "cottage"}]}]


def test_le_cas_fondateur_toutes_les_locales_coherentes_et_toutes_fausses():
    """« 8 gites » dans les DEUX langues quand la donnee en declare 5.

    C est le defaut reel, et c est aussi la preuve que la comparaison ENTRE locales ne suffit
    pas : les deux locales s accordent parfaitement, et les deux sont fausses.
    """
    par_locale = {
        "fr": {"reservation.meta": "Réservez parmi nos 8 gîtes en Normandie"},
        "en": {"reservation.meta": "Book one of our 8 cottages in Normandy"},
    }
    ecarts = glossaire.confronter(par_locale, _termes(), {"gîte": 5})
    assert len(ecarts) == 2, f"attendu 2 ecarts, obtenu {ecarts}"
    assert {e["locale"] for e in ecarts} == {"fr", "en"}
    assert all(e["vu"] == 8 and e["attendu"] == 5 for e in ecarts)


def test_le_bon_nombre_ne_rend_aucun_ecart():
    """La contre-epreuve : sans elle, une regle qui crie toujours passerait le cas precedent."""
    par_locale = {"fr": {"m": "Nos 5 gîtes vous attendent"}, "en": {"m": "Our 5 cottages await"}}
    assert glossaire.confronter(par_locale, _termes(), {"gîte": 5}) == []


def test_un_pivot_non_declare_comme_fait_reste_silencieux():
    """SILENCE, jamais un verdict : sans fait declare, il n y a rien a confronter."""
    par_locale = {"fr": {"m": "Nos 8 gîtes"}}
    assert glossaire.confronter(par_locale, _termes(), {}) == []


def test_un_nombre_sans_le_terme_retenu_reste_silencieux():
    """Le nombre seul ne prouve rien : c est le TERME qui dit de quoi on parle."""
    par_locale = {"fr": {"m": "Ouvert 7 jours sur 7, à 8 km de la mer"}}
    assert glossaire.confronter(par_locale, _termes(), {"gîte": 5}) == []


def test_le_pluriel_court_est_reconnu_le_terme_au_singulier_aussi():
    par_locale = {"fr": {"a": "8 gîtes disponibles", "b": "1 gîte disponible"}}
    ecarts = glossaire.confronter(par_locale, _termes(), {"gîte": 5})
    assert {e["cle"] for e in ecarts} == {"a", "b"}


# ---------------------------------------------------------------------------------------------
# TF-0656 — LE TERME RETENU EST-IL RÉELLEMENT EMPLOYÉ ?
#
# Le fait, parti en production dans trois langues sur sept : le retenu employé ZÉRO fois quand le
# proscrit l'était 82, 79 et 82 fois. Le glossaire avait été corrigé la veille ; les chaînes n'ont
# jamais suivi, et la règle était « non jugée — à relire à l'œil ».
# ---------------------------------------------------------------------------------------------

def _terme_proscrit():
    return [{"nom": "hebergement", "categorie": "contractuel", "pivot": "gîte",
             "lignes": [{"locale": "de", "retenu": "Ferienhaus", "proscrits": "`Gite` — mot français"}]}]


def test_le_retenu_a_zero_emploi_pendant_que_le_proscrit_regne_est_un_ECHEC():
    par_locale = {"de": {"a": "Unser Gite in der Normandie", "b": "Das Gite ist gemütlich",
                         "c": "Gite mit Pool"}}
    ecarts = glossaire.confronter_emploi(par_locale, _terme_proscrit())
    assert len(ecarts) == 1, f"attendu 1 ecart, obtenu {ecarts}"
    assert ecarts[0]["retenu"] == "Ferienhaus" and ecarts[0]["proscrit"] == "Gite"
    assert ecarts[0]["vus_proscrit"] == 3, "le compte du proscrit n est pas rendu — un total anonyme ne se corrige pas"


def test_le_retenu_employe_ne_declenche_rien_meme_si_le_proscrit_traine():
    """Contre-épreuve : sans elle, une règle qui crierait dès qu'un proscrit apparaît passerait le cas rouge."""
    par_locale = {"de": {"a": "Unser Ferienhaus in der Normandie", "b": "Das Gite ist gemütlich"}}
    assert glossaire.confronter_emploi(par_locale, _terme_proscrit()) == []


def test_BORNE_une_locale_qui_ne_parle_pas_du_concept_n_est_pas_accusee():
    """Le retenu à zéro n'est un défaut QUE si le proscrit règne : les deux conditions ensemble."""
    par_locale = {"de": {"a": "Nichts zu diesem Thema"}}
    assert glossaire.confronter_emploi(par_locale, _terme_proscrit()) == []


def test_BORNE_un_proscrit_sans_accents_graves_n_est_pas_un_terme():
    """La convention du gabarit : un mot proscrit s'écrit `ainsi`, sa glose non.

    Sans cette borne, la glose « ne pas employer le mot allemand courant » ferait chercher des
    mots qui ne sont pas des termes proscrits.
    """
    termes = [{"nom": "h", "categorie": "contractuel", "pivot": "gîte",
               "lignes": [{"locale": "de", "retenu": "Ferienhaus", "proscrits": "Gite est proscrit"}]}]
    par_locale = {"de": {"a": "Unser Gite in der Normandie"}}
    assert glossaire.confronter_emploi(par_locale, termes) == []


def test_les_faits_declares_ignorent_les_valeurs_non_entieres_et_le_disent(tmp_path):
    chemin = _ecrire(tmp_path, "FAITS.json", json.dumps({"gîte": 5, "prix": "cinq"}))
    lu = glossaire.faits_declares(chemin)
    assert lu["faits"] == {"gîte": 5}
    assert "prix" in (lu["motif"] or "")


def test_aucun_fait_declare_rend_un_motif_et_non_une_exception():
    lu = glossaire.faits_declares(None)
    assert lu["faits"] == {}
    assert "FORGE_TESTS_FAITS" in (lu["motif"] or "")


# ---------------------------------------------------------------------------------------------
# (i) UNE LOCALE SE CONTREDIT-ELLE AVEC ELLE-MEME ? — TF-0663
#
# LE FAIT : un audit a compare six familles de faits sur SEPT langues et rendu ZERO ecart. Les
# sept locales etaient parfaitement d'accord — et deux faits etaient FAUX, de la MEME facon
# partout. Une ville annoncee a 40 minutes dans une cle, a 45 dans deux autres.
#
# Verifier que sept langues disent la meme chose ne verifie pas qu'UNE SEULE soit coherente avec
# elle-meme. Ce controle ne compare donc RIEN entre locales : il regarde DANS chacune.
# ---------------------------------------------------------------------------------------------

def test_une_locale_qui_annonce_40_puis_45_minutes_pour_la_meme_ville_est_un_ECHEC():
    """Le cas fondateur, et il a franchi sept comparaisons interlangues sans en heurter une."""
    par_locale = {"fr": {
        "listing.intro": "Granville est a 40 minutes de la maison.",
        "contact.distances": "Granville : 45 minutes en voiture.",
    }}
    ecarts = glossaire.confronter_coherence_interne(par_locale)
    assert len(ecarts) == 1, ecarts
    assert ecarts[0]["sujet"] == "granville"
    assert ecarts[0]["unite"] == "minute"
    # L'ecart NOMME les cles en desaccord : sans elles, le rapport dit qu'il y a un probleme
    # sans dire ou, et la correction redevient une chasse.
    assert set(ecarts[0]["valeurs"]) == {"40", "45"}
    assert ecarts[0]["valeurs"]["40"] == ["listing.intro"]


def test_une_locale_coherente_avec_elle_meme_ne_declenche_rien():
    par_locale = {"fr": {
        "listing.intro": "Granville est a 45 minutes de la maison.",
        "contact.distances": "Granville : 45 minutes en voiture.",
    }}
    assert glossaire.confronter_coherence_interne(par_locale) == []


def test_BORNE_un_fait_chiffre_SANS_unite_n_est_pas_juge():
    """Sans unite, deux nombres attaches au meme nom propre peuvent parler de deux grandeurs.

    « Granville compte 13 000 habitants » et « Granville, 4 plages » ne se contredisent pas. Le
    controle prefere ne rien dire plutot que d'accuser une phrase juste.
    """
    par_locale = {"fr": {
        "a": "Granville compte 13 000 habitants.",
        "b": "Granville offre 4 plages.",
    }}
    assert glossaire.confronter_coherence_interne(par_locale) == []


def test_BORNE_deux_unites_differentes_sur_le_meme_sujet_ne_se_contredisent_pas():
    """45 minutes et 30 km decrivent le meme trajet sans desaccord : l'unite fait partie du sujet."""
    par_locale = {"fr": {
        "a": "Granville est a 45 minutes.",
        "b": "Granville est a 30 km.",
    }}
    assert glossaire.confronter_coherence_interne(par_locale) == []


def test_BORNE_deux_villes_differentes_ne_sont_pas_rapprochees():
    """C'est le NOM PROPRE qui rend deux enonces comparables — sans lui, on compare des trajets."""
    par_locale = {"fr": {
        "a": "Granville est a 45 minutes.",
        "b": "Avranches est a 20 minutes.",
    }}
    assert glossaire.confronter_coherence_interne(par_locale) == []


def test_BORNE_une_contradiction_dans_une_locale_n_accuse_pas_les_autres():
    """Le controle regarde DANS chaque locale : l'ecart porte le nom de celle qui se contredit."""
    par_locale = {
        "fr": {"a": "Granville est a 40 minutes.", "b": "Granville : 45 minutes."},
        "en": {"a": "Granville is 45 minutes away.", "b": "Granville: 45 minutes by car."},
    }
    ecarts = glossaire.confronter_coherence_interne(par_locale)
    assert [e["locale"] for e in ecarts] == ["fr"]
