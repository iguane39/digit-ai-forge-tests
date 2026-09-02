"""TF-0665 — un nombre affiché que rien du dépôt ne rend est un nombre orphelin.

LE FAIT. Sur une page de profil d'un produit servi, la capacité était annoncée à **23
personnes** dans la méta-description et à **30** dans l'introduction — *sur la même page* —,
quand la donnée du dépôt en donne **22** pour les trois hébergements que ce profil sélectionne.
Le nombre **23 ne correspond à AUCUNE source** : ni juste, ni recopié de travers. Sans origine.

POURQUOI LES TROIS CONTRÔLES DÉJÀ LIVRÉS LE MANQUENT TOUS, chacun pour sa raison : la cohérence
interlangue ne le voit pas (les sept langues disent 23) ; la cohérence interne (TF-0663) ne le
voit pas (« personnes » n'est ni une distance ni une durée — borne DÉCLARÉE) ; la confrontation
des nombres à la donnée (TF-0644) ne le voit pas (elle ne juge que les pivots DÉCLARÉS au
glossaire, et la capacité n'en est pas un).

CE CONTRÔLE EST D'UNE AUTRE NATURE : les trois lisent un catalogue et comparent, celui-ci
**recalcule depuis la donnée** — la somme des capacités des hébergements que la sélection
désigne. Le point dur est là, et il est tenu ci-dessous par les chiffres du cas fondateur :
la table rendue vaut 2, 6, 8, 10, **22**, 30 ; **23 n'y est pas**.

FIXTURE À DOUBLE SENS : la chaîne fautive du 26/08 (23) est nommée ; les chaînes saines (30,
issue de la somme des cinq ; 22, issue de la somme d'une sélection ; 10, une valeur brute) sont
acceptées.

LA PRÉCISION EST MESURÉE, PAS SUPPOSÉE — trois versions sur le même corpus réel de 4 886
chaînes : naïve 405 accusations, bornée 67, ciblée 6, et **aucune des trois ne trouve un
défaut** (le 23 avait été corrigé depuis). D'où le drapeau éteint par défaut, tenu ici aussi.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import orphelins

#: La donnée du cas fondateur, telle que le dépôt l'écrit : cinq hébergements, leur capacité.
_DONNEES = """
export const HEBERGEMENTS = [
  { slug: 'chalet', nom: 'Le Chalet', capMin: 1, capMax: 2, base: 95 },
  { slug: 'j1', nom: 'Le J1', capMin: 1, capMax: 6, base: 105 },
  { slug: 'j2', nom: 'Le J2', capMin: 1, capMax: 6, base: 105 },
  { slug: 'saloon', nom: 'Le Saloon', capMin: 3, capMax: 6, base: 150 },
  { slug: 'familial', nom: 'Le Familial', capMin: 5, capMax: 10, base: 204 },
];
"""

_SELECTIONS = {
    "couple": ["chalet", "j1"],
    "tribu": ["familial", "saloon", "j2"],
    "seminaire": ["familial", "saloon", "j2"],
}

_DENOMBRABLE = {
    "champ": "capMax",
    "selections": _SELECTIONS,
    "termes": {"fr": "personnes", "en": "people"},
}


def _rendues(tmp_path: Path) -> dict[int, list[str]]:
    fichier = tmp_path / "data.mjs"
    fichier.write_text(_DONNEES, encoding="utf-8")
    lus, anonymes = orphelins.enregistrements([fichier])
    assert anonymes == [], "chaque enregistrement porte un `slug` : aucun anonyme attendu"
    return orphelins.valeurs_rendues(lus, "capMax", _SELECTIONS)


def test_la_table_des_valeurs_rendues_recalcule_depuis_la_donnee(tmp_path: Path) -> None:
    """Le point dur de l'item : connaître la SÉLECTION, donc savoir rendre 22."""
    rendues = _rendues(tmp_path)

    assert rendues[30] == ["somme(capMax) sur 5 enregistrement(s)"]
    # 22 = familial + saloon + j2 : la somme sur la sélection, que rien d'autre ne rend.
    assert "somme(capMax) sur la sélection « seminaire »" in rendues[22]
    assert "somme(capMax) sur la sélection « couple »" in rendues[8]
    assert rendues[10] == ["capMax(familial)", "max(capMax)"]
    # ET LE FAIT DE L'ITEM : 23 n'est rendu par rien.
    assert 23 not in rendues


def test_rouge_la_chaine_fautive_du_26_08_est_nommee(tmp_path: Path) -> None:
    """« hébergement jusqu'à 23 personnes » — le nombre sans origine, restitué mot pour mot."""
    par_locale = {
        "fr": {
            "meta.profilSeminaire.desc": (
                "Séminaire d’équipe à 10 minutes du Mont : hébergement jusqu’à 23 personnes, "
                "salle de réunion, vidéo-projecteur."
            )
        }
    }
    resultat = orphelins.confronter(par_locale, _DENOMBRABLE, _rendues(tmp_path))

    assert resultat["juges"] == 1
    assert len(resultat["orphelins"]) == 1
    (seul,) = resultat["orphelins"]
    assert seul["vu"] == 23
    assert seul["cle"] == "meta.profilSeminaire.desc"
    assert seul["terme"] == "personnes"


def test_vert_les_nombres_que_la_donnee_rend_sont_acceptes(tmp_path: Path) -> None:
    """Trois origines différentes, toutes légitimes : une somme totale, une somme de sélection,
    une valeur brute. Un contrôle qui n'accepterait que la première accuserait les deux autres."""
    par_locale = {
        "fr": {
            "profils.seminaire.intro": "Réunissez votre équipe jusqu’à 30 personnes.",
            "profils.tribu.sub": "De 6 à 22 personnes, tous sur le même domaine.",
            "gites.familial.h2": "Le Familial accueille 10 personnes.",
        }
    }
    resultat = orphelins.confronter(par_locale, _DENOMBRABLE, _rendues(tmp_path))
    # « 6 à 22 personnes » ne compte QU'UNE fois : seul « 22 » touche le dénombrable. Le « 6 »
    # en est séparé par un mot ET par un autre nombre — le rapprocher inventerait un fait.
    assert resultat["juges"] == 3
    assert resultat["orphelins"] == []


def test_sans_selection_declaree_la_somme_partielle_devient_orpheline(tmp_path: Path) -> None:
    """La mesure de ce que coûte l'absence de sélection — c'est ce que l'item nommait le point
    à ne pas sous-estimer : sans la sélection, 22 n'existe nulle part et le contrôle l'accuse."""
    fichier = tmp_path / "data.mjs"
    fichier.write_text(_DONNEES, encoding="utf-8")
    lus, _ = orphelins.enregistrements([fichier])
    sans_selection = orphelins.valeurs_rendues(lus, "capMax", None)
    assert 22 not in sans_selection

    par_locale = {"fr": {"profils.tribu.sub": "De 6 à 22 personnes sur le même domaine."}}
    resultat = orphelins.confronter(par_locale, _DENOMBRABLE, sans_selection)
    assert [o["vu"] for o in resultat["orphelins"]] == [22]


def test_le_controle_ne_juge_que_ce_qui_est_attache_au_denombrable(tmp_path: Path) -> None:
    """La borne qui fait passer la mesure de 405 accusations à 6 : un nombre attaché à autre
    chose — une heure, un prix, un fait éditorial tiers — n'est PAS jugé."""
    par_locale = {
        "fr": {
            "piscine": "La piscine est ouverte de 11 h à 22 h.",
            "caution": "Caution de 500 € dont 100 € de ménage.",
            "aquarium": "Le grand aquarium et ses 600 espèces.",
            "acces": "Granville est à 45 minutes.",
        }
    }
    resultat = orphelins.confronter(par_locale, _DENOMBRABLE, _rendues(tmp_path))
    assert resultat == {"juges": 0, "orphelins": []}


def test_la_declaration_est_lue_et_ses_entrees_incompletes_sont_dites(tmp_path: Path) -> None:
    """Une définition sans `champ` ni `termes` ne juge rien : elle se DIT, elle ne se devine pas."""
    chemin = tmp_path / "DENOMBRABLES.json"
    chemin.write_text(
        json.dumps({"capacite": _DENOMBRABLE, "surface": {"champ": "surfaceM2"}}),
        encoding="utf-8",
    )
    lu = orphelins.lire_declaration(chemin)
    assert set(lu["denombrables"]) == {"capacite"}
    assert "surface" in lu["motif"]

    absent = orphelins.lire_declaration(tmp_path / "AUCUN.json")
    assert absent["denombrables"] == {} and "absents" in absent["motif"]


def test_les_fichiers_de_donnees_sont_declares_jamais_devines(
    tmp_path: Path, monkeypatch
) -> None:
    """Un fichier de données oublié ne rend pas ce contrôle muet : il le rend ACCUSATEUR."""
    (tmp_path / "data.mjs").write_text(_DONNEES, encoding="utf-8")
    monkeypatch.delenv(orphelins.VARIABLE_DONNEES, raising=False)
    assert orphelins.fichiers_de_donnees(tmp_path) == []

    monkeypatch.setenv(orphelins.VARIABLE_DONNEES, "data.mjs")
    assert [p.name for p in orphelins.fichiers_de_donnees(tmp_path)] == ["data.mjs"]


def test_le_drapeau_est_absent_par_defaut(monkeypatch) -> None:
    """Loi transverse n° 2 : la précision mesurée est sous le seuil, donc la voie reste éteinte."""
    monkeypatch.delenv(orphelins.VARIABLE_ACTIF, raising=False)
    assert orphelins.actif() is False
    assert orphelins.PRECISION_MESUREE < orphelins.SEUIL_PRECISION_BLOQUANTE
    monkeypatch.setenv(orphelins.VARIABLE_ACTIF, "1")
    assert orphelins.actif() is True


def test_l_homonyme_mesure_est_bien_ce_que_le_controle_ne_sait_pas_distinguer(
    tmp_path: Path,
) -> None:
    """Les SIX accusations mesurées, réduites à leur fait : 12 places à table, pas 12 couchages.

    Ce test ne demande pas au contrôle de se taire — il ne sait pas encore. Il FIGE la limite,
    pour que le jour où la portée du dénombrable sera déclarée, le cas devienne rouge ici.
    """
    par_locale = {
        "fr": {"gites.familial.pieces.0.items.0": "Grande pièce de vie avec espace repas "
                                                  "(12 personnes)"}
    }
    resultat = orphelins.confronter(par_locale, _DENOMBRABLE, _rendues(tmp_path))
    assert [o["vu"] for o in resultat["orphelins"]] == [12], (
        "limite CONNUE et déclarée : le discriminant est le SUJET que le nom qualifie, "
        "et la déclaration ne le porte pas encore (registre de dette `orphelins-002`)"
    )


def test_le_controle_est_cable_dans_le_pan_i18n_et_publie_ce_qu_il_a_regarde(
    tmp_path: Path, monkeypatch
) -> None:
    """Une affordance est câblée ou elle n'existe pas : le contrôle est joué par le pan, pas
    seulement testable en laboratoire. Éteint, il DÉCLARE ses candidats ; allumé, il les nomme."""
    from forge_tests.adaptateurs.i18n import _findings_orphelins

    (tmp_path / "data.mjs").write_text(_DONNEES, encoding="utf-8")
    (tmp_path / "DENOMBRABLES.json").write_text(
        json.dumps({"capacite": _DENOMBRABLE}), encoding="utf-8"
    )
    monkeypatch.setenv(orphelins.VARIABLE_DENOMBRABLES, str(tmp_path / "DENOMBRABLES.json"))
    monkeypatch.setenv(orphelins.VARIABLE_DONNEES, "data.mjs")
    par_locale = {
        "fr": {
            "meta.desc": "Hébergement jusqu’à 23 personnes.",
            "intro": "Réunissez jusqu’à 30 personnes.",
        }
    }

    # ÉTEINT (défaut) : aucun finding, mais le candidat est DIT avec la précision mesurée.
    monkeypatch.delenv(orphelins.VARIABLE_ACTIF, raising=False)
    findings, motifs = _findings_orphelins(tmp_path, par_locale, "i18n")
    assert findings == []
    resume = next(m for m in motifs if "denombrable « capacite »" in m)
    assert "2 nombre(s) attache(s) juge(s)" in resume and "1 sans origine" in resume
    assert "ABSENT" in resume and "precision mesuree 0%" in resume
    assert any("annonce 23 personnes" in m for m in motifs)

    # ALLUMÉ : le candidat devient un finding `signale`, jamais bloquant.
    monkeypatch.setenv(orphelins.VARIABLE_ACTIF, "1")
    findings, motifs = _findings_orphelins(tmp_path, par_locale, "i18n")
    assert len(findings) == 1
    (seul,) = findings
    assert seul.severite == "signale"
    assert "annonce 23 personnes" in seul.message
    assert "AUCUNE source du depot ne rend ce nombre" in seul.message


def test_sans_declaration_le_controle_le_dit_au_lieu_de_se_taire(
    tmp_path: Path, monkeypatch
) -> None:
    """« Rien à juger » et « rien jugé » ne sont pas la même phrase — la seconde se DIT."""
    from forge_tests.adaptateurs.i18n import _findings_orphelins

    monkeypatch.delenv(orphelins.VARIABLE_DENOMBRABLES, raising=False)
    monkeypatch.delenv(orphelins.VARIABLE_DONNEES, raising=False)
    findings, motifs = _findings_orphelins(tmp_path, {"fr": {"a": "23 personnes"}}, "i18n")
    assert findings == []
    assert len(motifs) == 1 and "NON juges" in motifs[0]
