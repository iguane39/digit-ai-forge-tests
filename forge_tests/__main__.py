"""CLI de Forge Tests — lecture seule par défaut sur le projet analysé."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE
from forge_tests.noyau import RapportRefuse, rapport

# Codes de sortie du CDC : 0 conforme · 1 défauts bloquants · 2 refus ou erreur d exécution ·
# 3 diagnostic partiel (un pan sans adaptateur, non bloquant par décision `s` de la spec).
SORTIE_OK, SORTIE_FAIL, SORTIE_ERREUR, SORTIE_PARTIEL = 0, 1, 2, 3

# TF-0259 — un `--livrables` pointé DANS le projet audité est refusé (G-1, comportement voulu).
# Ce refus sortait en 2, confondu avec toute panne de génération : l opérateur ne pouvait pas
# distinguer « j ai mal désigné le dossier » de « la génération a échoué ». Le code 4 est neuf,
# et il l est sans risque — audit des consommateurs du 15/08/2026 : le contrat publié du pilot
# ne documente que 0/1/3 (`references\ETAPES-RUN.md`, `INVENTAIRE.md`, son `CLAUDE.md`), le seul
# consommateur EXÉCUTABLE de la CLI (`conductor/gates/affordances_gate.py` de forge-development)
# ne lit jamais `returncode` mais le JSON de stdout, et aucun script, oracle ou CI de
# l écosystème ne teste un code de sortie de forge-tests. Le 2 reste donc ce qu il était pour
# tout le reste : personne ne perd un routage, l opérateur gagne une distinction.
SORTIE_REFUS_G1 = 4


def analyser(cible: Path, pans: list[str] | None = None) -> dict:
    from forge_tests.avancement import Avancement
    from forge_tests.instance import au_rapport as instance_au_rapport
    from forge_tests.qualification import qualifier

    # TF-0096 (contrat TF-0094 du pilot) : un audit n'est plus silencieux — chaque pan est
    # une unité nommée, émise toutes les 3 min (stderr + <cible>/forge/avancement.jsonl si
    # le dossier de run existe ; jamais de création dans un projet audité sans forge/).
    retenus = [(nom, module) for nom, module in REGISTRE.items()
               if pans is None or module.PAN in pans]
    dossier_run = str(cible / "forge") if (cible / "forge").is_dir() else None
    av = Avancement(dossier_run, unite="pan", raf=[m.PAN for _, m in retenus],
                    libelle=f"audit forge-tests de {cible.name}")
    sorties = []
    for _nom, module in retenus:
        av.en_cours(module.PAN)
        sorties.append(module.analyser(cible))
        av.unite_finie(module.PAN)
    av.final()
    # RT-6a — point d application UNIQUE : ce qu aucune execution ne pouvait atteindre FAUTE DE
    # CONFIGURATION est nomme ici, pour tous les adaptateurs, avec les champs a fournir.
    qualifier(sorties, cible, REGISTRE)
    # A-5 — le chemin de couverture est declare PAR L ADAPTATEUR (il sait ce qui lui manque),
    # jamais par le noyau : celui-ci ne connait aucune technologie et ne saurait pas quoi dire.
    chemins = {
        module.PAN: getattr(module, "POUR_COUVRIR", None)
        for module in REGISTRE.values()
        if hasattr(module, "PAN") and getattr(module, "POUR_COUVRIR", None)
    }
    # TF-0340/0341 — ce que l audit laisse debout, et de quoi l instance auditee a ete batie.
    # Mesure APRES les pans : c est l etat en fin d audit qui interesse le lecteur du rapport.
    # TF-0352/0353 — le journal de boucle du PROJET, lu tel quel. La forge ne l écrit jamais :
    # c est la campagne qui le tient, et un journal écrit par l outil qu il juge ne prouverait
    # rien. Absent, le rapport le DIT (« aucun journal de boucle »), il ne se tait pas.
    from forge_tests import boucle as _boucle

    # TF-0539 : la forge DEPOSE le gabarit de configuration qu'elle reclame, au lieu de laisser
    # le projet le reconstituer a la main depuis un rapport de 1,1 Mo. Elle n'ecrase jamais un
    # `.env.forge-tests` existant ni un gabarit deja annote — le dépôt se DIT, dans les trois cas.
    # TF-0580 : une copie VENDORISEE qui a diverge de sa source sert des valeurs perimees en
    # silence. Mesure du 24/08 : un site annoncait v1.6.2 et 80 services quand l'amont portait
    # v1.8.0 et 83, sur un site dont l'argument entier est la preuve datee.
    from forge_tests import vendorisation as _vend
    _vendor = _vend.constats(cible)

    from forge_tests import gabarit_env as _gab
    _depot = _gab.deposer(cible)
    # TF-0620 (mesure du pilot du 25/08) : la forge PRESCRIT `.env.forge-tests` chez le projet, et
    # ce fichier porte des identifiants. La protection etait SUPPOSEE — « gitignore que l'operateur
    # remplit » — et le tirage a rendu 1 projet conforme sur 3, les deux autres versionnes, l'un
    # publie sur origin/main. Une affordance est cablee ou elle n'existe pas (loi transverse n° 1).
    _protection = _gab.proteger(cible)

    return rapport(sorties, PANS_ATTENDUS, pour_couvrir=chemins,
                   instance=instance_au_rapport(cible),
                   boucle=_boucle.verdict(_boucle.lire(cible)),
                   gabarit_env={**_depot, "protection_gitignore": _protection},
                   vendorisation=_vendor)


_DEBUT = _dt.datetime.now().astimezone()


def _resume(rap: dict) -> str:
    # Forme DÉGRADÉE du message de fin (gabarits\\RESTITUTION.md v2, 14/08) : un outil qui
    # imprime au terminal doit au minimum porter son HORODATAGE et son verdict. Sans l heure,
    # deux sorties du meme jour ne s ordonnent pas — et il en tombe plusieurs par jour sur un
    # meme produit. La duree, elle, dit si le traitement a ete tronque.
    fin = _dt.datetime.now().astimezone()
    duree = fin - _DEBUT
    lignes = [
        f"forge-tests · {rap.get('cible') or ''}".rstrip(" ·"),
        f"termine le {fin.strftime('%Y-%m-%d a %Hh%M')} ({fin.tzname()}) "
        f"· duree {int(duree.total_seconds() // 60)} min {int(duree.total_seconds() % 60)} s",
        "",
        f"verdict global : {rap['verdict']}",
        "",
    ]
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
            + (
                f" · {mutation['modules_mutes']}/{mutation['modules_inventories']} modules mutés"
                if "modules_mutes" in mutation
                else ""
            )
        )
        # TF-0744 : le COUT du pan, decompose par classe. La moyenne globale seule a publie une
        # valeur arithmetiquement impossible (115 x 37 s = 71 min pour 67 min de campagne) et
        # ne decrit de toute facon aucun mutant reel : sous `-x`, un mutant tue s arrete au
        # premier echec quand un survivant parcourt la suite entiere.
        cout = mutation.get("cout") or {}
        if cout.get("mesure"):
            deco = cout["decomposition"]
            lignes.append(
                f"  {'':<12} cout {cout['duree_pan_s']:.0f} s / {cout['mutants_joues']} mutants "
                f"= {cout['s_par_mutant']:.1f} s par mutant"
            )
            for nom_classe in ("tues", "survivants"):
                classe = deco[nom_classe]
                if not classe["mutants"]:
                    continue
                lignes.append(
                    f"  {'':<12}   {nom_classe:<11} {classe['mutants']:>3} mutants "
                    f"· {classe['moyenne_s']:.1f} s en moyenne "
                    f"· {classe['part_du_pan']:.0%} du temps de mutation"
                )
            lignes.append(f"  {'':<12}   {cout['mecanisme']}")
    if rap.get("seuils"):
        lignes.append("")
        lignes.append("seuils opposables (versionnés dans forge_tests/seuils.py)")
        for nom, detail in sorted(rap["seuils"].items()):
            lignes.append(
                f"  {nom:<28} {detail['valeur']:>6.0%}  [{detail['severite']}] "
                f"{detail['porte_sur']}"
            )
    modules = rap.get("modules") or []
    if modules:
        exerces = [m for m in modules if m.get("exerce")]
        jamais = [m for m in modules if m.get("exerce") is False]
        mutes = [m for m in modules if m.get("mute")]
        exclus = [m for m in modules if m.get("exclu")]
        lignes.append("")
        lignes.append(
            f"modules sources : {len(modules)} inventoriés · {len(exerces)} exercés · "
            f"{len(mutes)} mutés · {len(jamais)} JAMAIS exercés · {len(exclus)} exclus"
        )
        for module in jamais:
            lignes.append(f"  JAMAIS EXERCE  {module['module']}")
        for module in exclus:
            lignes.append(f"  exclu          {module['module']} — {module['exclu'][:70]}")
    if rap["pans_non_couverts"]:
        lignes.append("")
        lignes.append("pans NON COUVERTS — motif ET chemin de couverture, jamais un constat seul :")
        for entree in rap["pans_non_couverts"]:
            lignes.append(f"  {entree['pan']:<14} {entree['motif'][:100]}")
            lignes.append(f"  {'':<14} pour couvrir -> {entree['pour_couvrir'][:110]}")
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
    # RT-18 : un constat DÉCLARÉ par le projet (contesté avec contre-preuve, bloqué par
    # configuration ou par du code supplanté) reste au rapport et sort du décompte principal.
    # Les deux nombres sont donnés côte à côte : un décompte qui baisserait sans dire pourquoi
    # serait exactement l inverse de ce que la déclaration existe pour rendre lisible.
    from forge_tests.declarations import est_ecarte

    opposables = [f for f in rap["findings"] if not est_ecarte(f)]
    ecartes = [f for f in rap["findings"] if est_ecarte(f)]
    lignes.append("")
    lignes.append(
        f"findings nommés : {len(opposables)}  "
        f"(critique {bandes['critique']} · standard {bandes['standard']} · "
        f"différé {bandes['differe']} · non coté {bandes['non_cote']})"
    )
    declarations = rap.get("declarations") or {}
    compte = declarations.get("compte") or {}
    if declarations:
        lignes.append(
            f"constats déclarés par le projet ({declarations.get('fichier')}) : "
            f"{compte.get('constats_ecartes', 0)} écarté(s) du décompte · "
            f"{compte.get('refusee', 0)} déclaration(s) REFUSÉE(S) · "
            f"{compte.get('perimee', 0)} périmée(s) · "
            f"{compte.get('inconnues', 0)} sans constat correspondant"
        )
        for entree in declarations.get("entrees") or []:
            if entree.get("statut") in ("refusee", "perimee"):
                lignes.append(
                    f"  DECLARATION {entree['statut'].upper():<8} {entree.get('constat') or '?'}"
                    f" — {entree.get('motif_du_refus')}"
                )
    if ecartes:
        lignes.append("")
        lignes.append(
            "écartés du décompte, TOUJOURS mesurés — motif typé et contre-preuve en regard :"
        )
        for f in ecartes[:8]:
            declaration = f.get("declaration") or {}
            lignes.append(
                f"  {f['id']} — {declaration.get('motif')} · preuve "
                f"{declaration.get('preuve')} · déclaré par {declaration.get('par')} le "
                f"{declaration.get('date')}"
            )
    if opposables:
        lignes.append("")
        lignes.append("les plus risqués")
        for f in opposables[:8]:
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
    # La liste est DERIVEE du registre : ecrite a la main, elle aurait deja diverge au douzieme
    # pan. Un `--help` qui ment sur les valeurs acceptees est un piege, pas une documentation.
    parser.add_argument(
        "--pans",
        nargs="*",
        default=None,
        metavar="PAN",
        help="restreindre à ces pans : " + ", ".join(PANS_ATTENDUS),
    )
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
        "--livrables",
        type=Path,
        default=None,
        metavar="DOSSIER",
        help=(
            "produire les livrables derives dans ce dossier de PROPOSITION, HORS du projet "
            "audite (G-1) : cahier de tests fonctionnels, cahier de tests techniques, jeu de "
            "donnees synthetique et dashboard HTML autonome. Regeneres a chaque audit, y "
            "compris sous `--reprendre`"
        ),
    )
    parser.add_argument(
        "--precedent",
        type=Path,
        action="append",
        default=None,
        metavar="RAPPORT.json",
        help=(
            "rapport anterieur servant de point de comparaison : le dashboard affiche alors la "
            "TENDANCE de chaque compteur. REPETABLE (TF-0159, barre Allure B3) : plusieurs "
            "--precedent, du plus ancien au plus recent, donnent une tendance multi-runs. "
            "Sans lui, l onglet Synthese le declare"
        ),
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

    # TF-0243 — l écart se DÉCLARE avant la mesure. Un opérateur qui a rempli le `.env` du
    # dépôt au lieu de celui du projet verrait sinon des pans « sans objet » sans jamais
    # apprendre que son URL a été volontairement écartée. Sur stderr : `--json` doit rendre
    # un stdout parsable.
    from forge_tests.authentification import ENV_PROJET, cles_instance_ignorees

    ecartees = cles_instance_ignorees(args.cible.resolve())
    if ecartees:
        print(
            "[TF-0243] "
            + ", ".join(ecartees)
            + " lue(s) dans le `.env` du dépôt forge-tests : IGNORÉE(S). Ces clés désignent "
            "une instance déployée et ne valent que déclarées par le projet audité "
            f"(`{args.cible}/{ENV_PROJET}`) — un audit ne part jamais sur l instance laissée "
            "par le run précédent.",
            file=sys.stderr,
        )

    try:
        # Chemin ABSOLU : un adaptateur qui lance un sous-processus avec un `cwd` différent ne
        # peut pas résoudre un binaire donné en relatif. Le résoudre ici évite un SKIP silencieux.
        if args.reprendre is not None:
            from forge_tests.reprise import charger, fusionner, pans_a_rejouer

            ancien = charger(args.reprendre)
            # RT-18 : un rapport antérieur peut avoir été produit AVEC les déclarations du
            # projet appliquées. Réintégrer avant de fusionner, c est repartir de la mesure
            # entière : sinon une déclaration retirée entre deux runs ne rendrait jamais son
            # constat, et la reprise croirait le pan vert.
            from forge_tests.declarations import reintegrer

            reintegrer(ancien)
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
        # RT-18 — point d application UNIQUE des déclarations du projet, APRÈS la fusion de
        # `--reprendre` comme après un audit complet : le rapport publié et les livrables qui
        # en dérivent lisent donc le même décompte. Lecture seule chez l audité (G-1).
        from forge_tests.declarations import appliquer as appliquer_declarations

        appliquer_declarations(rap, args.cible.resolve())
        if args.generer is not None:
            from forge_tests.execution import schema_openapi
            from forge_tests.generateur import ecrire
            from forge_tests.generateur_data import ecrire as ecrire_data

            produit = ecrire(
                rap, args.generer.resolve(), schema=schema_openapi(str(args.cible.resolve()))
            )
            produit_data = ecrire_data(rap, args.cible.resolve(), args.generer.resolve())
            # TF-0343 — la matrice des droits, une cellule par (action x profil). Ecrite ici
            # parce qu elle DERIVE d une declaration du projet, comme les autres cas : la
            # forge ne devine pas quel code un contrat promet a quel profil.
            from forge_tests.droits import ecrire as ecrire_droits

            produit_droits = ecrire_droits(args.cible.resolve(), args.generer.resolve())
            for chemin, pan in (
                (produit, "api"), (produit_data, "data"), (produit_droits, "matrice des droits")
            ):
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

    # Le rapport est publié AVANT les livrables, et ce n est pas un détail d ordre : un audit
    # complet coûte des dizaines de minutes de mutation, et une production de livrables qui
    # échouerait (référentiel d exigences introuvable, dossier interdit par G-1) emporterait
    # avec elle la mesure entière. La mesure est le fait ; les livrables en sont une vue.
    texte = json.dumps(rap, ensure_ascii=False, indent=2) if args.json else _resume(rap)
    _publier(texte, args.sortie)

    if args.livrables is not None:
        # Mandat 4 : le point d application est ICI, apres la fusion de `--reprendre` comme
        # apres un audit complet. Les livrables suivent donc TOUJOURS le rapport publie — une
        # reprise qui laisserait un dashboard perime serait pire qu aucun dashboard : on y
        # lirait des chiffres d avant en croyant lire ceux d apres.
        from forge_tests.livrables import DepotInterdit, produire, resume

        precedent = None
        if args.precedent:
            from forge_tests.reprise import charger as charger_rapport

            charges = [charger_rapport(p) for p in args.precedent]
            # TF-0159 : un seul --precedent garde le contrat historique (dict) ; plusieurs
            # donnent la tendance multi-runs (liste, du plus ancien au plus recent).
            precedent = charges[0] if len(charges) == 1 else charges
        try:
            chemins = produire(
                rap,
                args.cible.resolve(),
                args.livrables.resolve(),
                precedent=precedent,
                rapport_nom=(args.sortie.name if args.sortie else None),
            )
        except DepotInterdit as refus:
            # Le motif DOIT se lire en queue de sortie. Il y était déjà écrit, et pourtant
            # illisible : stdout est bufferisé, stderr ne l est pas, si bien que le rapport se
            # vidait APRÈS le message. Constaté le 15/08 sur BdL — le motif tombait ligne 24
            # d une sortie de 69, l opérateur qui lit la fin ne voyait qu un exit 2 muet, et
            # deux exécutions ont été perdues avant le diagnostic. Le `flush` remet l ordre.
            sys.stdout.flush()
            print(
                f"\nG-1 : livrables HORS projet requis — chemin reçu : {args.livrables}\n"
                f"{refus}\n"
                "le rapport, lui, est publie : la mesure n est pas perdue",
                file=sys.stderr,
            )
            return SORTIE_REFUS_G1
        except Exception as erreur:  # noqa: BLE001 — l echec se DECLARE, le rapport reste publie
            # Même `flush` et pour la même raison : un motif de panne noyé au milieu de la
            # sortie n est pas un motif publié.
            sys.stdout.flush()
            print(
                f"livrables NON PRODUITS — {type(erreur).__name__}: {erreur}\n"
                "le rapport, lui, est publie : la mesure n est pas perdue",
                file=sys.stderr,
            )
            return SORTIE_ERREUR
        # Sur stderr : `--livrables --json` doit laisser un stdout JSON PUR.
        print(resume(chemins), file=sys.stderr)

    if rap["verdict"] == "PARTIEL":
        return SORTIE_PARTIEL
    return SORTIE_FAIL if rap["verdict"] == "FAIL" else SORTIE_OK


if __name__ == "__main__":
    sys.exit(main())
