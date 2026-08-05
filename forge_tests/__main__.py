"""CLI de Forge Tests — lecture seule par défaut sur le projet analysé."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE
from forge_tests.noyau import RapportRefuse, rapport

# Codes de sortie du CDC : 0 conforme · 1 défauts bloquants · 2 refus ou erreur d exécution ·
# 3 diagnostic partiel (un pan sans adaptateur, non bloquant par décision `s` de la spec).
SORTIE_OK, SORTIE_FAIL, SORTIE_ERREUR, SORTIE_PARTIEL = 0, 1, 2, 3


def analyser(cible: Path, pans: list[str] | None = None) -> dict:
    from forge_tests.qualification import qualifier

    sorties = [
        module.analyser(cible)
        for nom, module in REGISTRE.items()
        if pans is None or module.PAN in pans
    ]
    # RT-6a — point d application UNIQUE : ce qu aucune execution ne pouvait atteindre FAUTE DE
    # CONFIGURATION est nomme ici, pour tous les adaptateurs, avec les champs a fournir.
    qualifier(sorties, cible, REGISTRE)
    return rapport(sorties, PANS_ATTENDUS)


def _resume(rap: dict) -> str:
    lignes = [f"verdict global : {rap['verdict']}", ""]
    lignes.append("couverture de surface par pan")
    for pan, surface in sorted(rap["couverture_par_pan"].items()):
        etat = "OK" if surface["ratio"] >= surface["seuil"] else "SOUS SEUIL"
        lignes.append(
            f"  {pan:<12} {surface['exerce']:>3}/{surface['inventorie']:<3} "
            f"= {surface['ratio']:.0%} (seuil {surface['seuil']:.0%}) {etat}"
        )
    for pan, mutation in sorted(rap["mutation"].items()):
        lignes.append(
            f"  {pan + ' (mutation)':<12} {mutation['tues']:>3}/{mutation['mutants_viables']:<3} "
            f"= {mutation['score']:.0%} tués"
        )
    if rap["pans_non_couverts"]:
        lignes.append("")
        lignes.append("pans NON COUVERTS — chacun avec son motif, jamais silencieux :")
        for pan in rap["pans_non_couverts"]:
            motif = rap.get("motifs_non_couverture", {}).get(pan, "adaptateur absent")
            lignes.append(f"  {pan:<14} {motif[:100]}")
    reprise = rap.get("reprise")
    if reprise:
        lignes.append("")
        lignes.append(f"reprise de {reprise['rapport_repris']}")
        lignes.append(f"  pans rejoues        : {', '.join(reprise['pans_rejoues']) or 'aucun'}")
        lignes.append(
            "  pans repris tels quels (deja verts, NON rejoues) : "
            + (", ".join(reprise["pans_repris_sans_rejeu"]) or "aucun")
        )
        for pan, detail in sorted(reprise["provenance"].items()):
            if detail["repris_de"]:
                lignes.append(
                    f"  {pan:<12} {len(detail['exerce_le_run']):>3} exerce(s) ce run · "
                    f"{len(detail['repris_de']):>3} repris du rapport"
                )
    if rap.get("non_testables"):
        lignes.append("")
        lignes.append("NON TESTABLES ici — configuration a fournir, puis `--reprendre` :")
        par_champs: dict[tuple[str, ...], list[str]] = {}
        for entree in rap["non_testables"]:
            par_champs.setdefault(tuple(entree["champs_requis"]), []).append(entree["element"])
        for champs, elements in sorted(par_champs.items()):
            lignes.append(f"  {len(elements):>3} element(s) — requiert {', '.join(champs)}")
            for element in elements[:3]:
                lignes.append(f"        {element}")
            if len(elements) > 3:
                lignes.append(f"        ... et {len(elements) - 3} autre(s)")
    bandes = rap["bandes_de_risque"]
    lignes.append("")
    lignes.append(
        f"findings nommés : {len(rap['findings'])}  "
        f"(critique {bandes['critique']} · standard {bandes['standard']} · "
        f"différé {bandes['differe']} · non coté {bandes['non_cote']})"
    )
    if rap["findings"]:
        lignes.append("")
        lignes.append("les plus risqués")
        for f in rap["findings"][:8]:
            cote = f"{f['risque']:>3}" if f["risque"] is not None else "  -"
            lignes.append(f"  risque {cote}  {f['id']}")
    return "\n".join(lignes)


def _forcer_utf8() -> None:
    """La console Windows est en cp1252 ; le rapport, lui, est accentué.

    Sans cela `--json` mourait en `UnicodeEncodeError` À L IMPRESSION, après avoir tout mesuré :
    l audit était bon, seul l affichage tuait le processus. `errors="replace"` garantit qu un
    caractère hors page de code dégrade l affichage, jamais le run.
    """
    for flux in (sys.stdout, sys.stderr):
        reconfigurer = getattr(flux, "reconfigure", None)
        if reconfigurer is not None:
            reconfigurer(encoding="utf-8", errors="replace")


def _publier(texte: str, sortie: Path | None) -> None:
    """Écrit le rapport sur stdout et, si demandé, à l identique dans un fichier."""
    print(texte)
    if sortie is None:
        return
    sortie = sortie.resolve()
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(texte + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _forcer_utf8()
    parser = argparse.ArgumentParser(prog="forge-tests", description="Accélérateur de tests")
    parser.add_argument("cible", type=Path, help="racine du projet à analyser")
    parser.add_argument("--json", action="store_true", help="sortie machine complète")
    parser.add_argument("--pans", nargs="*", default=None, help="restreindre à ces pans")
    parser.add_argument(
        "--generer",
        type=Path,
        default=None,
        help="deposer les cas generes dans ce dossier de PROPOSITION (jamais dans le projet)",
    )
    parser.add_argument(
        "--sortie",
        type=Path,
        default=None,
        help="persister le rapport dans ce fichier, a l identique de stdout",
    )
    parser.add_argument(
        "--reprendre",
        type=Path,
        default=None,
        metavar="RAPPORT.json",
        help=(
            "relire un rapport anterieur et ne rejouer QUE les pans non verts (elements non "
            "exerces, non testables, findings) ; le rapport produit fusionne les deux avec la "
            "provenance de chaque element"
        ),
    )
    args = parser.parse_args(argv)

    try:
        # Chemin ABSOLU : un adaptateur qui lance un sous-processus avec un `cwd` différent ne
        # peut pas résoudre un binaire donné en relatif. Le résoudre ici évite un SKIP silencieux.
        if args.reprendre is not None:
            from forge_tests.reprise import charger, fusionner, pans_a_rejouer

            ancien = charger(args.reprendre)
            rejoues = pans_a_rejouer(ancien)
            if args.pans is not None:
                rejoues = [p for p in rejoues if p in args.pans]
            # Une liste VIDE ne veut pas dire « tout rejouer » : elle veut dire « tout etait
            # vert ». Passer None a `analyser` relancerait l audit complet, exactement ce que
            # la reprise existe pour eviter.
            neuf = analyser(args.cible.resolve(), rejoues) if rejoues else {
                "adaptateurs": [], "couverture_par_pan": {}, "mutation": {},
                "pans_non_couverts": [], "motifs_non_couverture": {}, "findings": [],
                "non_testables": [], "non_juge": [],
            }
            rap = fusionner(
                ancien, neuf, str(args.reprendre), rejoues, PANS_ATTENDUS
            )
        else:
            rap = analyser(args.cible.resolve(), args.pans)
        if args.generer is not None:
            from forge_tests.execution import schema_openapi
            from forge_tests.generateur import ecrire
            from forge_tests.generateur_data import ecrire as ecrire_data

            produit = ecrire(
                rap, args.generer.resolve(), schema=schema_openapi(str(args.cible.resolve()))
            )
            produit_data = ecrire_data(rap, args.cible.resolve(), args.generer.resolve())
            for chemin, pan in ((produit, "api"), (produit_data, "data")):
                # Sur stderr : `--generer --json` doit produire un stdout JSON PUR, parsable
                # sans découpage par un appelant machine.
                message = f"cas generes ({pan}) -> {chemin}" if chemin else f"aucun cas ({pan})"
                print(message, file=sys.stderr)
    except RapportRefuse as refus:
        # Le refus est un VERDICT du noyau, pas un plantage : il se publie comme un rapport.
        _publier(
            json.dumps(
                {"verdict": "REFUSE", "motif": str(refus)}, ensure_ascii=False, indent=2
            ),
            args.sortie,
        )
        return SORTIE_ERREUR
    except Exception as erreur:  # noqa: BLE001 — une erreur d exécution se DÉCLARE, code 2
        import traceback

        traceback.print_exc(file=sys.stderr)
        _publier(
            json.dumps(
                {"verdict": "ERREUR", "motif": f"{type(erreur).__name__}: {erreur}"},
                ensure_ascii=False,
                indent=2,
            ),
            args.sortie,
        )
        return SORTIE_ERREUR

    texte = json.dumps(rap, ensure_ascii=False, indent=2) if args.json else _resume(rap)
    _publier(texte, args.sortie)
    if rap["verdict"] == "PARTIEL":
        return SORTIE_PARTIEL
    return SORTIE_FAIL if rap["verdict"] == "FAIL" else SORTIE_OK


if __name__ == "__main__":
    sys.exit(main())
