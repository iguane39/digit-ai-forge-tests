"""Recette de NON-PERTE du ciblage par ligne mutee (D-36 (a), 01/09/2026).

LA DECISION QUE CET OUTIL SERT. Le ciblage — pour un mutant donne, ne rejouer que les tests qui
couvrent la ligne alteree au lieu de la suite entiere — est ECRIT, EPROUVE et ETEINT. La decision
humaine du 01/09 (D-36, option a) le laisse eteint et demande de le VERIFIER lors de la prochaine
campagne reelle.

POURQUOI CET OUTIL EXISTE, et c est la seule raison. « On verifiera » n est pas un mecanisme :
une consigne s execute ou elle decore. La verification demandee est une COMPARAISON — deux
campagnes sur le meme code, l une pleine, l autre ciblee — et une comparaison faite de memoire,
sur deux rapports lus a quelques minutes d intervalle, est exactement le genre de preuve qui
n en est pas une. Ici la comparaison est jouee, et son verdict est une sortie machine.

LA CONDITION, telle que l etude du 01/09 la pose et telle qu elle est reprise ici : la campagne
ciblee rend EXACTEMENT la meme liste de survivants que la campagne pleine. Pas « un score
proche », pas « le meme ordre de grandeur » — la meme liste, aux memes identifiants. Toute
divergence est un defaut de l optimisation, jamais un arrondi acceptable.

TROIS PIEGES, et chacun rendrait le verdict faux dans le sens qui rassure :

  1. LE SENS DE L ECART N EST PAS SYMETRIQUE. Un survivant que la campagne ciblee liste EN PLUS
     est une perte de temps ; un survivant qu elle PERD est un faux vert — le mutant a ete
     declare tue par une selection qui n a jamais joue le test qui l aurait tue. Les deux sont
     des echecs, mais ils ne coutent pas la meme chose, et le rapport les nomme separement.
  2. DEUX CAMPAGNES VIDES SE RESSEMBLENT BEAUCOUP. Si les deux passes ne mutent rien — projet
     sans environnement, suite rouge, pan saute —, les listes sont identiques et la comparaison
     rendrait PASS sans avoir rien compare. C est SANS_OBJET, jamais PASS.
  3. L ECHANTILLON DOIT ETRE LE MEME DES DEUX COTES. La profondeur de mutation est echantillonnee
     et le tirage est deterministe, donc deux passes du meme code jouent les memes mutants — mais
     seulement si les variables de tirage ne bougent pas entre les deux. Elles sont donc figees
     ici, et leur valeur est publiee au rapport : une comparaison dont les deux cotes n ont pas
     joue les memes mutants ne prouve rien.

    python recette/non_perte_ciblage.py <projet>

Sortie : JSON {verdict: PASS|FAIL|SANS_OBJET, ...} · exit 0 = tenue · 1 = perte mesuree ·
2 = rien a comparer (les deux campagnes n ont mute aucun mutant).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_tests.adaptateurs import mutation  # noqa: E402


def _campagne(projet: Path, ciblage: bool) -> dict:
    """Une passe complete du pan mutation, ciblage arme ou non.

    Les variables de tirage sont FIGEES et l environnement est restaure : sans cela, une valeur
    heritee du shell de l operateur pourrait differer entre les deux passes, et la comparaison
    porterait sur deux echantillons distincts sans que rien ne le dise.
    """
    avant = {c: os.environ.get(c) for c in (
        "FORGE_TESTS_MUTATION", "FORGE_TESTS_MUTATION_CIBLAGE",
        "FORGE_TESTS_MUTANTS_PAR_MODULE", "FORGE_TESTS_MUTATION_PLAFOND",
    )}
    try:
        os.environ["FORGE_TESTS_MUTATION"] = "1"          # la campagne est a la demande (D-34)
        os.environ["FORGE_TESTS_MUTANTS_PAR_MODULE"] = str(
            avant["FORGE_TESTS_MUTANTS_PAR_MODULE"] or mutation._MUTANTS_PAR_MODULE_DEFAUT)
        os.environ["FORGE_TESTS_MUTATION_PLAFOND"] = str(
            avant["FORGE_TESTS_MUTATION_PLAFOND"] or mutation._PLAFOND_DEFAUT)
        if ciblage:
            os.environ["FORGE_TESTS_MUTATION_CIBLAGE"] = "1"
        else:
            os.environ.pop("FORGE_TESTS_MUTATION_CIBLAGE", None)
        sortie = mutation.analyser(projet)
    finally:
        for cle, valeur in avant.items():
            if valeur is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = valeur
    donnees = sortie.mutation or {}
    return {
        "verdict_pan": sortie.verdict,
        "mutants_viables": donnees.get("mutants_viables", 0),
        "survivants": sorted(donnees.get("survivants", [])),
        "score": donnees.get("score"),
        "echantillon": donnees.get("taux_echantillon"),
    }


def comparer(pleine: dict, ciblee: dict) -> dict:
    """Le verdict de non-perte. Fonction PURE : c est elle que le banc eprouve."""
    if not pleine["mutants_viables"] and not ciblee["mutants_viables"]:
        return {
            "verdict": "SANS_OBJET",
            "motif": "aucun mutant viable des deux cotes — il n y a rien a comparer. Deux "
                     "campagnes vides se ressemblent parfaitement, et rendre PASS ici serait "
                     "declarer tenue une condition jamais eprouvee",
        }
    perdus = [s for s in pleine["survivants"] if s not in ciblee["survivants"]]
    ajoutes = [s for s in ciblee["survivants"] if s not in pleine["survivants"]]
    if not perdus and not ajoutes:
        return {
            "verdict": "PASS",
            "motif": f"{len(pleine['survivants'])} survivant(s), liste identique des deux cotes "
                     f"sur {pleine['mutants_viables']} mutant(s) viable(s)",
        }
    return {
        "verdict": "FAIL",
        "motif": "la campagne ciblee ne rend pas la meme liste de survivants que la campagne "
                 "pleine — toute divergence est un defaut de l optimisation, jamais un arrondi",
        "survivants_PERDUS": perdus,
        "survivants_AJOUTES": ajoutes,
        "gravite": (
            "PERDU = FAUX VERT : le mutant a ete declare tue par une selection qui n a jamais "
            "joue le test qui l aurait tue. C est le seul defaut qu un banc de tests ne doit "
            "jamais produire." if perdus else
            "AJOUTE seulement : la campagne ciblee est plus pessimiste que la pleine — du temps "
            "perdu, pas un faux vert. Reste un echec de la condition de non-perte."
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage : python recette/non_perte_ciblage.py <projet>", file=sys.stderr)
        return 2
    projet = Path(argv[1]).resolve()
    pleine = _campagne(projet, ciblage=False)
    ciblee = _campagne(projet, ciblage=True)
    verdict = comparer(pleine, ciblee)
    print(json.dumps({
        "recette": "non-perte du ciblage par ligne mutee",
        "decision": "D-36 (a) du 01/09/2026 — le ciblage reste eteint et se verifie a la "
                    "prochaine campagne reelle",
        "projet": str(projet),
        "campagne_pleine": pleine,
        "campagne_ciblee": ciblee,
        **verdict,
    }, ensure_ascii=False, indent=1))
    return {"PASS": 0, "FAIL": 1, "SANS_OBJET": 2}[verdict["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
