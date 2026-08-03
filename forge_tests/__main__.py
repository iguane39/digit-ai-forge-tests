"""CLI de Forge Tests — lecture seule par défaut sur le projet analysé."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE
from forge_tests.noyau import rapport


def analyser(cible: Path, pans: list[str] | None = None) -> dict:
    sorties = [
        module.analyser(cible)
        for nom, module in REGISTRE.items()
        if pans is None or module.PAN in pans
    ]
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


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    # Chemin ABSOLU : un adaptateur qui lance un sous-processus avec un `cwd` différent ne peut
    # pas résoudre un binaire donné en relatif. Le résoudre ici évite un SKIP silencieux.
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
            print(f"cas generes ({pan}) -> {chemin}" if chemin else f"aucun cas ({pan})")
    print(json.dumps(rap, ensure_ascii=False, indent=2) if args.json else _resume(rap))
    if rap["verdict"] == "PARTIEL":
        return 3
    return 1 if rap["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
