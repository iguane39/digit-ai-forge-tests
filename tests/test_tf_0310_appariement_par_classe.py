"""TF-0310 — aucune entrée du corpus ne peut plus être couverte par le défaut d une AUTRE.

L appariement d une entrée de `CORPUS` reposait sur le seul préfixe d identifiant, et deux
préfixes débordaient :

  - `interface:` (H-13, affordances inertes) appariait aussi `interface:ecart-servi:` (H-20) —
    débordement DÉCLARÉ en commentaire par la campagne du 17/08, faute de mécanisme pour le
    fermer ;
  - `migration:` (H-05, migrations ni inversées ni rejouées) appariait aussi le
    `migration:<nom>:retour` de classe `divergence`, qui est le défaut de H-12.

Tant que les deux défauts sont plantés, la recette affiche 23/23 et personne ne voit rien. Le jour
où l un disparaît, son entrée reste [DETECTE] — portée par le voisin. Un corpus qui mesure moins
que ce qu il affiche est pire qu un corpus plus petit : il rassure.

Le discriminant est la CLASSE du finding — celle que l adaptateur pose pour dire de QUOI il parle.
Ce fichier est le contre-oracle du contrat des entrées, sur les trois exigences de l item :

  1. chaque entrée déclare au moins une classe (sinon le trou se rouvre en silence) ;
  2. chaque entrée sort [DETECTE] par SON propre défaut ;
  3. le défaut retiré, SON entrée — et elle seule — sort [MANQUE].
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recette import verifier_corpus as vc  # noqa: E402


def _finding(identifiant: str, classe: str, pan: str = "x") -> dict:
    return {"id": identifiant, "classe": classe, "pan": pan, "severite": "bloquant"}


def _representants() -> dict[str, list[dict]]:
    """{code: [findings qui prouvent CETTE entrée]} — dérivés du contrat, jamais écrits en dur.

    Un représentant par couple (préfixe, classe) déclaré : c est l étendue exacte de ce que
    l entrée accepte, donc l étendue exacte de ce qu il faut éprouver.
    """
    return {
        code: [
            _finding(f"{prefixe}temoin-{code}", classe, pan)
            for prefixe in prefixes
            for classe in classes
        ]
        for code, pan, _libelle, prefixes, classes in vc.CORPUS
    }


# --- Exigence 1 : le contrat lui-même ----------------------------------------------------------
def test_chaque_entree_DECLARE_sa_classe() -> None:
    """Une entrée sans classe retomberait sur le seul préfixe : le trou serait rouvert pour elle,
    et en silence. `_findings` tolère la liste vide (les appelants de laboratoire s en servent),
    c est donc ICI que le contrat s exige."""
    muettes = [entree[0] for entree in vc.CORPUS if not entree[4]]

    assert not muettes, f"entrées de corpus sans classe déclarée : {muettes}"


def test_chaque_entree_porte_bien_ses_cinq_champs() -> None:
    """Le contrat a changé de forme le 17/08 : cinq champs, pas quatre. Une entrée ajoutée à
    l ancienne forme casserait la boucle de la recette au lieu de le dire ici."""
    for entree in vc.CORPUS:
        assert len(entree) == 5, entree[0]


# --- Exigence 2 : chaque entrée détectée par SON défaut ----------------------------------------
@pytest.mark.parametrize("code", [entree[0] for entree in vc.CORPUS])
def test_chaque_entree_est_DETECTEE_par_son_propre_defaut(code: str) -> None:
    """Le sens vert du contrat : le resserrement ne doit avoir aveuglé aucune entrée."""
    representants = _representants()
    entree = next(e for e in vc.CORPUS if e[0] == code)

    trouves = vc._findings({"findings": representants[code]}, entree[3], entree[4])

    assert trouves, f"{code} n est plus détectée par son propre défaut"


# --- Exigence 3 : le défaut retiré, SON entrée sort [MANQUE] -----------------------------------
@pytest.mark.parametrize("code", [entree[0] for entree in vc.CORPUS])
def test_le_defaut_RETIRE_fait_MANQUER_son_entree_et_elle_SEULE(code: str) -> None:
    """Le cœur de l item, joué 23 fois. Le banc rouge porte tous les défauts d un coup : c est
    ici, en retirant celui d une entrée à la fois, qu on prouve qu aucune n est portée par une
    autre. AVANT le resserrement, H-13 restait [DETECTE] sans une seule affordance inerte —
    l écart servi/versionné de H-20 suffisait à la couvrir."""
    representants = _representants()
    prives = {
        autre: findings for autre, findings in representants.items() if autre != code
    }
    rapport = {"findings": [f for findings in prives.values() for f in findings]}

    manquantes = [
        entree[0]
        for entree in vc.CORPUS
        if not vc._findings(rapport, entree[3], entree[4])
    ]

    assert manquantes == [code], (
        f"défaut de {code} retiré : attendu [MANQUE] pour {code} seule, obtenu {manquantes}"
    )


# --- Les deux débordements NOMMÉS, mesurés un par un ------------------------------------------
def test_H13_n_est_plus_couverte_par_l_ecart_servi_de_H20() -> None:
    """Le débordement fondateur, à la lettre : un banc où AUCUNE affordance n est inerte mais où
    l écart servi/versionné sort. AVANT : H-13 [DETECTE]. C est le faux vert de l item."""
    rapport = {"findings": [_finding("interface:ecart-servi:en", "ecart-servi-versionne")]}
    h13 = next(e for e in vc.CORPUS if e[0] == "H-13")
    h20 = next(e for e in vc.CORPUS if e[0] == "H-20")

    assert vc._findings(rapport, h13[3], h13[4]) == []
    assert vc._findings(rapport, h20[3], h20[4]) != []
    # Le sens inverse tient toujours : l affordance inerte reste bien le défaut de H-13.
    inerte = {"findings": [_finding("interface:ui/page.html:13:button", "affordance-inerte")]}
    assert vc._findings(inerte, h13[3], h13[4]) != []
    assert vc._findings(inerte, h20[3], h20[4]) == []


def test_H05_n_est_plus_couverte_par_la_divergence_de_migration() -> None:
    """Second débordement, celui que personne n avait déclaré : `migration:<nom>:retour` de classe
    `divergence` (une migration non inversable) partage le préfixe de H-05, qui parle d une
    migration jamais rejouée. Deux défauts, deux entrées — H-12 est le pendant de l autre."""
    rapport = {"findings": [_finding("migration:002_statut:retour", "divergence")]}
    h05 = next(e for e in vc.CORPUS if e[0] == "H-05")

    assert vc._findings(rapport, h05[3], h05[4]) == []


# --- Le garde-fou GÉNÉRAL : plus aucun croisement, quel que soit l ajout futur -----------------
def test_AUCUN_defaut_d_une_entree_n_apparie_une_autre_entree() -> None:
    """Le contrôle exhaustif, 23 x 23. Fermer les deux débordements connus ne prouve rien sur le
    prochain : une entrée ajoutée demain avec un préfixe qui déborde doit tomber ICI, pas six
    campagnes plus tard sur un faux vert."""
    representants = _representants()
    croisements = [
        (code, entree[0])
        for code, findings in representants.items()
        for entree in vc.CORPUS
        if entree[0] != code and vc._findings({"findings": findings}, entree[3], entree[4])
    ]

    assert croisements == [], f"défauts appariant l entrée d un autre : {croisements}"
