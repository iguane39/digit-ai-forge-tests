"""Recette de la phase 1 — critère de sortie S-01, vérifié PAR EXÉCUTION.

Rejoue le framework sur la paire de bancs et vérifie, défaut par défaut :
  - sur le banc ROUGE : chaque défaut du corpus produit au moins un finding NOMMÉ ;
  - sur le banc VERT  : aucun finding BLOQUANT.

Précision du critère, posée le 2026-08-02 : le corpus disait « aucun finding ». À l époque
tous les findings étaient bloquants. Depuis, la mutation nomme ses survivants en sévérité
`signale` — nommés parce qu on ne masque rien, non bloquants parce que le SEUIL est le juge.
Un survivant résiduel au-dessus du seuil est une information, pas un échec. Le critère porte
donc sur les findings BLOQUANTS, et le compte des `signale` est affiché à part.

Un défaut détecté « globalement » ne compte pas : la détection doit porter sur des éléments
identifiés, sinon on retombe sur l absence silencieuse que le framework existe pour supprimer.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import functools
import http.server
import os
import re
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# La recette porte sur les bancs LOCAUX. Le `.env` de l operateur decrit une instance SERVIE
# (projet client en recette) : laisse actif, les pans accessibilite et visuel auditaient cette
# instance distante au lieu du banc — le banc VERT sortait alors a 10 findings bloquants et
# S-01 devenait ininterpretable. Neutralise ici, jamais lu par accident.
os.environ["FORGE_TESTS_BASE_URL"] = ""

from forge_tests import classes as noms_de_classes  # noqa: E402
from forge_tests.__main__ import analyser  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
ROUGE = RACINE / "fixtures" / "banc-rouge"
VERT = RACINE / "fixtures" / "banc-vert"

# Chaque défaut du corpus : son code, son pan, son libellé, le préfixe d identifiant qui prouve sa
# détection, et la CLASSE de finding qui le nomme.
#
# TF-0310 — la classe fait partie du contrat de l entrée depuis le 17/08. Le préfixe seul
# débordait : `interface:` (H-13) appariait aussi le `interface:ecart-servi:` de H-20, et
# `migration:` (H-05) appariait aussi le `migration:<nom>:retour` de classe `divergence`. Une
# entrée pouvait sortir [DETECTE] sur le défaut d une AUTRE — le corpus mesurait moins que ce
# qu il affiche, et la disparition du défaut propre à l entrée passait inaperçue. Le prix de ce
# contrat est assumé : une classe renommée par un adaptateur fait sortir son entrée en [MANQUE],
# ce qui est exactement ce qu on veut d un contrat (bruyant, jamais silencieux).

# TF-0334 — la classe se lit desormais dans `forge_tests.classes`, source unique des noms. Le
# littéral recopié ici ET dans l adaptateur laissait un renommage sortir en [MANQUE] sans dire
# POURQUOI : « l adaptateur ne détecte plus » et « la classe s appelle autrement » s écrivaient
# pareil. Les prefixes, eux, restent des litteraux : ils portent sur des IDENTIFIANTS d elements
# fabriques par le pan, pas sur un nom declare quelque part.
CORPUS = [
    ("D-01", "front", "parcours Front tronqué", ("route:", "element:"),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    ("H-02", "api", "codes d erreur jamais exercés", ("code:",),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    ("H-03", "api", "méthodes HTTP jamais atteintes", ("endpoint:",),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    ("H-04", "data", "contraintes jamais violées", ("contrainte:",),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    # La classe écarte ici le `migration:<nom>:retour` de classe `divergence` — une migration sans
    # section de retour est un autre défaut, dont le pendant au corpus est H-12.
    ("H-05", "migrations", "migrations ni inversées ni rejouées", ("migration:",),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    ("H-06", "batch", "branches de rejet et reprise non parcourues", ("branche:", "rejet:"),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    ("H-07", "fichiers", "chemins de parsing non exercés", ("chemin:",),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    ("H-08", "back", "assertions permissives", ("mutant:", "seuil:back"),
     (noms_de_classes.MUTANT_SURVIVANT, noms_de_classes.SEUIL_NON_TENU)),
    ("H-09", "securite", "execution dynamique non signalee", ("securite:",),
     (noms_de_classes.SECURITE,)),
    ("H-10", "accessibilite", "controles sans nom accessible", ("a11y:",),
     (noms_de_classes.ACCESSIBILITE,)),
    ("H-11", "visuel", "regression visuelle de mise en page", ("visuel:",),
     (noms_de_classes.REGRESSION_VISUELLE,)),
    ("H-12", "migrations", "migration qui defait la precedente", ("divergence:migration:",),
     (noms_de_classes.DIVERGENCE,)),
    # La classe écarte ici l ecart servi/versionné de H-20, qui vit dans le même pan et sous le
    # même préfixe : c est le débordement qui a motivé TF-0310.
    ("H-13", "interface", "affordances inertes — bouton, lien et formulaire sans effet",
     ("interface:",), (noms_de_classes.AFFORDANCE_INERTE,)),
    # A-2 : le principe fondateur applique a l etage du MODULE. `app/recherche.py` du banc
    # rouge n est importe par aucun test : il doit sortir NOMME, jamais fondu dans un total.
    ("A-2", "back", "module source jamais importe par la suite", ("module-non-exerce:",),
     (noms_de_classes.MODULE_NON_EXERCE,)),
    # A-3 : un seuil n est opposable que s il attrape quelque chose. Le banc rouge porte des
    # modules metier dont la suite ne tue pas la moitie des mutants.
    ("A-3", "back", "seuil de mutation par module de logique metier viole",
     ("seuil:mutation-module:",), (noms_de_classes.SEUIL_NON_TENU,)),
    # A-4 : le parcours navigateur d une instance SERVIE — 404 sur lien, trace d exception
    # rendue, marqueur de contenu absent, erreur console, affordance sans le moindre ecouteur.
    ("A-4", "qualif", "instance servie : route en defaut et affordance sans effet",
     ("qualif:",), (noms_de_classes.ROUTE_EN_DEFAUT, noms_de_classes.AFFORDANCE_SANS_EFFET)),
    # TF-0200 (verdict O2 de l etude du 14/08) : le pan `prompts`, v0 STATIQUE et GRATUITE.
    # H-14 — un modele designe par un ALIAS mouvant : le systeme sous test change sans qu un
    # seul commit ne bouge (`claude-opus-4-1-20250805` retire le 2026-08-05, alias `-latest`
    # de Google remappes a dates fixes). H-15 — un prompt adressable qu AUCUN cas n exerce.
    ("H-14", "prompts", "modele designe par un alias mouvant, jamais epingle", ("modele:",),
     (noms_de_classes.MODELE_NON_EPINGLE,)),
    ("H-15", "prompts", "prompt adressable sans aucun cas au corpus", ("prompt:",),
     (noms_de_classes.ELEMENT_NON_EXERCE,)),
    # TF-0203 (precision humaine du 14/08 : « un produit trigger, l enclenchement de batch »).
    # Le pan `batch` mesurait l INTERIEUR du traitement en supposant qu il demarre. Le banc
    # rouge porte un lot qu aucun declencheur n atteint : le constat sortait bien du pan, mais
    # n etait declare dans AUCUNE entree de ce corpus — un defaut detecte hors contrat n est
    # pas un defaut couvert.
    ("H-16", "batch", "traitement par lot qu aucun declencheur n enclenche",
     ("job-sans-declencheur", "trigger:"), (noms_de_classes.JOB_SANS_DECLENCHEUR,)),
    # TF-0293 — le pan `i18n` (TF-0284) etait prouve par 21 tests et par ses deux bancs, mais
    # ABSENT de ce corpus : la recette qui prononce S-01 ne le mesurait pas. Ses pages sont
    # portees au BUILD SERVI des bancs historiques (`dist\`), et ses TROIS defauts — les trois
    # payes en production le 15/08, chacun trouve a la main en quelques minutes — recoivent ici
    # l entree qu ils n avaient pas. Les prefixes DISTINGUENT les trois : un seul `i18n:` aurait
    # fait passer les trois pour couverts des que l un sortait, ce qui est exactement l absence
    # silencieuse que ce corpus existe pour supprimer.
    ("H-17", "i18n", "route servie dans une locale et pas dans une autre",
     ("i18n:route:en:/tarifs",), (noms_de_classes.I18N,)),
    ("H-18", "i18n", "menu d une locale ampute par rapport au menu le plus riche",
     ("i18n:navigation:",), (noms_de_classes.I18N,)),
    ("H-19", "i18n", "page servie sous une locale non francaise avec du contenu francais",
     ("i18n:route:en:/blog",), (noms_de_classes.I18N,)),
    # TF-0300 — l ecart SERVI <-> VERSIONNE (TF-0288) n avait au corpus AUCUNE entree : ses
    # branches PASS et SKIP etaient mesurees par la recette sur les deux bancs, mais la branche
    # qui ACCUSE ne reposait que sur pytest. Exactement l ecart que TF-0293 vient de fermer pour
    # le pan i18n. Le banc rouge porte donc desormais la source du site (`site/`) : son menu
    # anglais promet trois entrees de premier niveau quand `dist/en/index.html` n en sert que
    # deux — la page des tarifs, jamais deployee au menu. Le banc vert n a pas de source de site :
    # son controle reste en SKIP, et aucun constat nouveau n y apparait.
    #
    # Le prefixe est celui de la CLASSE, pas le `interface:` de H-13 : les deux se lisent dans le
    # meme pan, et un prefixe commun aurait fait passer H-13 pour couvert des que l ecart sort.
    # Le debordement INVERSE (`interface:` de H-13 appariant ce constat) etait declare ici en
    # commentaire faute de mecanisme : TF-0310 l a ferme, l appariement portant desormais aussi
    # sur la classe.
    ("H-20", "interface", "menu promis par la source versionnee et non servi par la production",
     ("interface:ecart-servi:",), (noms_de_classes.ECART_SERVI_VERSIONNE,)),
]

# RT-8 — le lecteur SQL, verifie sur pieces. Ces cas ne passent par aucun banc : ils portent
# sur le decoupage lui-meme, et c est LUI qui fabriquait de fausses instructions. Un `;` dans
# un commentaire produisait une instruction jamais envoyee au moteur, donc une migration
# declaree non exercee — un FAIL a tort, constate en production sur `0004_catalogues.sql`.
LECTURE_SQL = [
    (
        "point-virgule dans un commentaire de ligne",
        "-- attention ; ce commentaire ne fabrique rien\nCREATE TABLE t (id INT);",
        ["CREATE TABLE t (id INT)"],
    ),
    (
        "point-virgule en fin de ligne commentee",
        "CREATE TABLE t (id INT);  -- fin de section ;\n",
        ["CREATE TABLE t (id INT)"],
    ),
    (
        "commentaire AU MILIEU d une instruction",
        "CREATE UNIQUE INDEX i\n  -- unicite stricte ; posee ici\n  ON t (c);",
        ["CREATE UNIQUE INDEX i ON t (c)"],
    ),
    (
        "commentaire de bloc porteur d un point-virgule",
        "/* note ; sur deux\n   lignes */\nALTER TABLE t ADD COLUMN c INT;",
        ["ALTER TABLE t ADD COLUMN c INT"],
    ),
    (
        "instruction precedee d un commentaire de tete (jadis rejetee en bloc)",
        "-- ce qui suit est une VRAIE instruction\nDROP INDEX i;",
        ["DROP INDEX i"],
    ),
    (
        "point-virgule dans un litteral de chaine",
        "COMMENT ON INDEX i IS 'un seul compte ; unicite metier';",
        ["COMMENT ON INDEX i IS 'un seul compte ; unicite metier'"],
    ),
    (
        "double tiret dans un litteral : ce n est pas un commentaire",
        "INSERT INTO t (c) VALUES ('a--b'); SELECT 1;",
        ["INSERT INTO t (c) VALUES ('a--b')", "SELECT 1"],
    ),
]


class _ServeurMuet(http.server.SimpleHTTPRequestHandler):
    """Serveur de fichiers silencieux : ses journaux noieraient le verdict de la recette."""

    def log_message(self, *_args: object) -> None:  # noqa: D102
        return


@contextlib.contextmanager
def servir(dossier: Path):
    """Sert `dossier` en HTTP sur un port libre — l instance SERVIE que le pan qualif exige.

    Le pan qualif juge une application EN SERVICE : il ne peut donc pas être exercé par un banc
    de fichiers, comme les onze autres pans. Le servir ici est ce qui rend le pan recevable à la
    recette au lieu d être « prouvé sur le produit et cru sur parole ». Le serveur est celui de
    la bibliothèque standard, le navigateur est réel, les erreurs console sont réelles, les 404
    sont réels — seul le PEUPLEMENT est écrit en dur dans les pages du banc, car peupler une
    application est la responsabilité du projet audité, pas du framework.
    """
    fabrique = functools.partial(_ServeurMuet, directory=str(dossier))
    serveur = socketserver.ThreadingTCPServer(("127.0.0.1", 0), fabrique)
    serveur.daemon_threads = True
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


def analyser_servi(banc: Path) -> dict:
    """Analyse le banc AVEC son instance servie déclarée — sinon le pan qualif sortirait SKIP."""
    with servir(banc / "qualif-web") as url:
        os.environ["FORGE_TESTS_QUALIF_URL"] = url
        # TF-0138 — meme geste que QUALIF_URL ci-dessus, SCOPE au seul temps de l analyse : les
        # DEUX bancs portent `trace: "off"` dans leur propre playwright.config (fixe avant que
        # `_mode_trace` respecte le choix du projet, TF-0132). Sans cette variable, le pan front
        # declare desormais — a raison — la couverture NON MESURABLE plutot que nulle (TF-0138),
        # mais la recette redevient alors aveugle a D-01 (le parcours front tronque du banc
        # rouge n a plus aucun moyen d etre CONSTATE) et ne peut plus prouver que le banc vert
        # est exerce a 100 % — seulement qu il ne dit rien. Le poste qui rejoue la recette n a
        # pas la contrainte poste-client de TF-0132 (ecriture de trace bloquee) : forcer la
        # mesure ici est le mot de l OPERATEUR de la recette. `pop` en `finally`, comme
        # QUALIF_URL : un module-level serait importe par d autres tests (test_tf_0116,
        # test_tf_0136) et polluerait leur process pytest entier — constate en fixture rouge
        # sur `tests/test_tf_0132.py`, qui verifie precisement l ABSENCE de cette variable.
        os.environ["FORGE_TESTS_PLAYWRIGHT_TRACE"] = "on"
        try:
            return analyser(banc)
        finally:
            os.environ.pop("FORGE_TESTS_QUALIF_URL", None)
            os.environ.pop("FORGE_TESTS_PLAYWRIGHT_TRACE", None)


def verifier_divergences() -> int:
    """RT-9 / RT-10 — l analyse statique des divergences, vérifiée sur pièces.

    Les deux cas viennent d un produit réel et ne passent par aucun banc : le premier porte sur
    la RÉSOLUTION d un appel, le second sur l EXCLUSION d un montage. Tous deux se jouent sur
    du texte source, pas sur une exécution — les vérifier ici est le seul moyen de les empêcher
    de pourrir en silence.
    """
    import tempfile

    from forge_tests.adaptateurs.api import _montages, _sous_montage
    from forge_tests.invariants import codes_par_fonction

    echecs = 0
    print("-" * 78)
    print("  RT-9 / RT-10 — divergences : garde deportee resolue, montage statique exclu")

    source = '''
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

app = FastAPI()


def _refuser_doublon() -> None:
    raise HTTPException(status_code=409, detail="deja enregistre")


def _valider(x) -> None:
    if not x:
        raise HTTPException(status_code=400, detail="vide")


@app.post("/api/comptes", responses={201: {}, 400: {}, 409: {}})
def creer(corps: dict) -> dict:
    _valider(corps.get("nom"))
    if corps.get("nom") in ("deja",):
        _refuser_doublon()
    return corps


@app.get("/api/comptes", responses={200: {}})
def lister() -> dict:
    return {}


app.mount("/static", StaticFiles(directory="ui/static"), name="static")
'''
    with tempfile.TemporaryDirectory() as temporaire:
        racine = Path(temporaire)
        (racine / "backend" / "app").mkdir(parents=True)
        fichier = racine / "backend" / "app" / "main.py"
        fichier.write_text(source, encoding="utf-8")

        codes = codes_par_fonction(fichier)
        cas = [
            ("un helper local qui leve 409 est une garde de la route (RT-9)",
             409 in codes.get("creer", set())),
            ("un helper local qui leve 400 l est aussi, meme derriere un `if`",
             400 in codes.get("creer", set())),
            ("une route qui ne leve rien n herite d aucun code",
             not codes.get("lister")),
            ("le helper lui-meme garde ses propres codes",
             codes.get("_refuser_doublon") == {409}),
        ]
        prefixes = _montages(racine)
        cas.extend(
            [
                ("le montage `/static` est reconnu (RT-10)", prefixes == ["/static"]),
                ("un code emis sous le montage est EXCLU du controle de divergence",
                 _sous_montage("code:GET /static/app.js=200", prefixes)),
                ("le montage lui-meme est exclu", _sous_montage("code:GET /static=404", prefixes)),
                ("une vraie route de meme prefixe textuel n est PAS exclue",
                 not _sous_montage("code:GET /statistiques=200", prefixes)),
                ("sans montage, aucune exclusion", not _sous_montage("code:GET /x=200", [])),
            ]
        )
    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def verifier_gardes_multi_modules() -> int:
    """TF-0135 — les gardes d une route sont lues sur TOUS les modules, jamais le seul main.py.

    Repro Approval2 : une app a routeurs (main.py qui ne fait qu `include_router`, les GET/POST
    et leurs gardes vivant dans `app/api/routes_admin.py`) faisait ressortir la table des
    handlers VIDE — `fonction` valait None pour toute route, et `code in (400, 409) and code
    not in gardes` devenait vrai pour TOUT code declare. Trois findings BLOQUANTS faux sur un
    code dont les trois handlers levent bien leur code dans leur PROPRE corps.

    Fixture a double sens : le TEMOIN rejoue le comportement D AVANT (main.py seul) sur les
    memes pieces et prouve qu il produit bien les findings faux — sans ce temoin, le controle
    APRES ne prouverait rien. Le second cas (route enregistree par `add_api_route`, que l AST
    ne reconnait pas comme decorateur) reste NON RESOLU meme apres correctif : il doit degrader
    en NON_JUGE motive, jamais retomber en finding bloquant.
    """
    import tempfile

    from forge_tests.adaptateurs.api import _divergences_gardes, _fichiers_sources
    from forge_tests.invariants import codes_par_fonction, handlers
    from forge_tests.noyau import Element

    echecs = 0
    print("-" * 78)
    print("  TF-0135 — gardes d une route a routeurs : lues sur tous les modules,"
          " jamais main.py seul")

    main_py = (
        "from fastapi import FastAPI\n"
        "from app.api import routes_admin\n"
        "\n"
        "app = FastAPI()\n"
        "app.include_router(routes_admin.router)\n"
    )
    routes_admin_py = (
        "from fastapi import APIRouter, HTTPException\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "\n"
        "def _refuser_deja_revoquee() -> None:\n"
        "    raise HTTPException(status_code=409, detail=\"deja revoquee\")\n"
        "\n"
        "\n"
        "@router.post(\"/admin/revoke\", responses={200: {}, 409: {}})\n"
        "def revoke_endpoint(demande_id: int) -> dict:\n"
        "    if demande_id < 0:\n"
        "        _refuser_deja_revoquee()\n"
        "    return {\"id\": demande_id}\n"
        "\n"
        "\n"
        "def reassign_endpoint(demande_id: int) -> dict:\n"
        "    if demande_id < 0:\n"
        "        raise HTTPException(status_code=409, detail=\"deja reassignee\")\n"
        "    return {\"id\": demande_id}\n"
        "\n"
        "\n"
        "router.add_api_route(\n"
        "    \"/admin/reassign\", reassign_endpoint, methods=[\"POST\"],"
        " responses={200: {}, 409: {}}\n"
        ")\n"
    )

    with tempfile.TemporaryDirectory() as temporaire:
        racine = Path(temporaire)
        (racine / "backend" / "app" / "api").mkdir(parents=True)
        (racine / "backend" / "app" / "main.py").write_text(main_py, encoding="utf-8")
        (racine / "backend" / "app" / "api" / "routes_admin.py").write_text(
            routes_admin_py, encoding="utf-8"
        )
        source_main = racine / "backend" / "app" / "main.py"

        inv = [
            Element(
                "code:POST /admin/revoke=409", "api", "POST /admin/revoke -> 409",
                str(source_main),
            ),
            Element(
                "code:POST /admin/reassign=409", "api", "POST /admin/reassign -> 409",
                str(source_main),
            ),
        ]

        # TEMOIN — comportement D AVANT TF-0135, rejoue LITTERALEMENT (main.py seul, et le
        # `fonction or ""` qui degradait un handler non resolu en gardes VIDES au lieu de
        # suspendre le jugement) : la table est VIDE, tout code 400/409 declare devient une
        # divergence BLOQUANTE fausse. C est le bug REEL constate — `_divergences_gardes`
        # inclut deja le correctif et ne peut donc pas servir de temoin du bug.
        table_avant = handlers(source_main)
        gardes_avant = codes_par_fonction(source_main)
        findings_avant = []
        for element in inv:
            signature, code_txt = element.id[len("code:") :].rsplit("=", 1)
            methode, chemin = signature.split(" ", 1)
            code = int(code_txt)
            fonction = table_avant.get((methode, chemin))
            gardes = gardes_avant.get(fonction or "", set())
            if code in (400, 409) and code not in gardes:
                findings_avant.append(element.id)

        # APRES — tous les modules source sont lus.
        sources = _fichiers_sources(racine)
        table = handlers(sources)
        gardes = codes_par_fonction(sources)
        # TF-0728 : le croisement avec la couverture DYNAMIQUE prend un quatrieme terme. Ce cas
        # ne mesure QUE la resolution des gardes multi-modules : la couverture y est VIDE, sinon
        # les deux mecanismes se masqueraient l un l autre.
        findings, non_juge, _confirmes = _divergences_gardes(
            inv, table, gardes, source_main, set()
        )

        cas = [
            ("TEMOIN rouge : main.py seul -> 2 findings BLOQUANTS faux (le bug reel constate)",
             len(findings_avant) == 2),
            ("_fichiers_sources decouvre le fichier de routeur, pas le seul main.py",
             any(p.name == "routes_admin.py" for p in sources)),
            ("APRES correctif : la route decoree et sa garde deportee sont resolues -> 0 finding",
             not [f for f in findings if "admin/revoke" in f.id]),
            ("APRES correctif : la route enregistree par add_api_route reste NON RESOLUE "
             "(limite declaree de l AST) mais ne devient PAS bloquante",
             not [f for f in findings if "admin/reassign" in f.id]),
            ("le cas non resolu degrade en NON_JUGE, motive et nomme, jamais en silence",
             any("admin/reassign" in m and "409" in m for m in non_juge)),
            ("aucun finding bloquant residuel sur l ensemble du cas", not findings),
        ]
        for libelle, ok in cas:
            echecs += not ok
            print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def _empreintes(banc: Path) -> dict[str, str]:
    """SHA-256 de chaque source du banc — la seule preuve recevable de « lecture seule ».

    TF-0116 : le paquet muté est DÉCOUVERT (`forge_tests.disposition.paquet_sources`), plus
    supposé sous `backend/app` — voir `forge_tests/adaptateurs/mutation.py`. Une empreinte
    figée sur `backend/app` dériverait silencieusement de ce que la mutation altère RÉELLEMENT
    dès qu un projet (ou un banc futur) range son paquet ailleurs ; ce contrôle suit donc la
    même découverte, avec le même repli.
    """
    import hashlib

    from forge_tests.disposition import paquet_sources

    racine = paquet_sources(banc) or (banc / "backend" / "app")
    return {
        chemin.as_posix(): hashlib.sha256(chemin.read_bytes()).hexdigest()
        for chemin in sorted(racine.rglob("*.py"))
    }


def alterations(empreintes_avant: dict[Path, dict[str, str]]) -> list[str]:
    """G-1 — fichiers dont l empreinte a changé depuis `empreintes_avant` : altération résiduelle
    du banc après audit, nommée. Isolée de `main()` pour rester vérifiable sans payer le prix
    d un audit complet (TF-0116) : un banc et un instantané suffisent à l exercer.
    """
    return [
        f"{banc.name}/{chemin}"
        for banc, avant in empreintes_avant.items()
        for chemin, empreinte in avant.items()
        if _empreintes(banc).get(chemin) != empreinte
    ]


def _fichiers_de_l_arbre(racine: Path) -> list[str] | None:
    """Chemins que git connaît : suivis, plus non suivis NON ignorés. `None` si git est muet.

    TF-0294 — le périmètre est celui de git, et c est ce qui rend l empreinte honnête. La recette
    écrit légitimement pendant qu elle tourne : `__pycache__`, caches de pytest et de ruff,
    traces de navigateur, `test-results\\` des bancs — tout cela est IGNORÉ par le `.gitignore`
    du dépôt, donc absent du relevé. Ce qui reste est exactement ce qu une campagne concurrente
    éditerait : du code, des tests, des fixtures, un registre.
    """
    import subprocess

    fichiers: list[str] = []
    for arguments in (["ls-files"], ["ls-files", "--others", "--exclude-standard"]):
        try:
            resultat = subprocess.run(
                ["git", "-C", str(racine), *arguments],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if resultat.returncode != 0:
            return None
        fichiers.extend(ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip())
    return sorted(set(fichiers))


def empreinte_arbre(racine: Path | None = None) -> dict[str, str] | None:
    """SHA-256 de chaque fichier de l arbre de travail. `None` = empreinte NON RELEVÉE.

    `None` et `{}` ne disent pas la même chose : le premier est « git n a pas répondu, la
    stabilité n est pas mesurable », le second « un arbre sans aucun fichier ». Les confondre
    ferait passer une non-mesure pour une mesure rassurante — le silence que ce dépôt interdit.
    """
    import hashlib

    cible = racine or RACINE
    fichiers = _fichiers_de_l_arbre(cible)
    if fichiers is None:
        return None
    empreintes: dict[str, str] = {}
    for relatif in fichiers:
        chemin = cible / relatif
        try:
            empreintes[relatif] = hashlib.sha256(chemin.read_bytes()).hexdigest()
        except OSError:
            # Un fichier listé par git mais illisible à l instant du relevé : ABSENT du relevé,
            # donc vu comme « disparu » au second passage s il l était au premier. C est le
            # comportement voulu : un fichier qui va et vient sous la recette est une instabilité.
            continue
    return empreintes


def instabilites(
    avant: dict[str, str] | None,
    apres: dict[str, str] | None,
    deja_nommes: list[str] | None = None,
) -> list[str]:
    """TF-0294 — ce qui a bougé dans l arbre entre deux relevés, nommé fichier par fichier.

    `deja_nommes` reçoit les altérations G-1 (`alterations`) : un source de banc que la
    restauration après mutation n a pas rendu à l octet près est un ÉCHEC MESURÉ de la recette,
    déjà nommé par la section `corpus`. Le compter ici une seconde fois transformerait une
    régression réelle en « arbre instable, verdict refusé » — c est-à-dire masquerait précisément
    ce que la recette venait de trouver.
    """
    if avant is None or apres is None:
        return []
    ecartes = [nomme.replace("\\", "/") for nomme in (deja_nommes or [])]
    bouges: list[str] = []
    for relatif in sorted(set(avant) | set(apres)):
        if relatif not in apres:
            etat = "disparu"
        elif relatif not in avant:
            etat = "apparu"
        elif avant[relatif] != apres[relatif]:
            etat = "modifie"
        else:
            continue
        if any(nomme.endswith(relatif) for nomme in ecartes):
            continue
        bouges.append(f"{relatif} ({etat})")
    return bouges


def verifier_lecture_seule() -> int:
    """G-1 — la mutation restaure le source A L OCTET PRES, fins de ligne comprises.

    Le 2026-08-06, un audit d ASD Mail Manager a laissé **23 fichiers source du produit
    modifiés**. La mutation avait bien été défaite ; c est la restauration qui écrivait par
    `Path.write_text`, lequel traduit `\\n` en `os.linesep` — les modules en LF ressortaient en
    CRLF. Aucun banc ne pouvait le voir : leurs sources sont déjà en CRLF sur cette machine, et
    le périmètre d avant A-1 ne touchait que huit modules déjà convertis par un audit antérieur.

    Le cas est donc vérifié sur pièces, avec un fichier en LF **et** un fichier en CRLF, sur le
    chemin d écriture réel de l adaptateur (`poser`, `restaurer`).
    """
    import tempfile

    from forge_tests.adaptateurs.mutation import Mutant, appliquer, poser, restaurer

    echecs = 0
    print("-" * 78)
    print("  G-1 — lecture seule : la mutation restaure le source a l OCTET PRES")

    corps = "def f(x):\n    if x > 0:\n        return x + 1\n    return 0\n"
    cas: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as temporaire:
        for style, fins in (("LF", b"\n"), ("CRLF", b"\r\n")):
            fichier = Path(temporaire) / f"module_{style}.py"
            attendu = corps.replace("\n", fins.decode())
            fichier.write_bytes(attendu.encode("utf-8"))
            avant = fichier.read_bytes()

            texte = fichier.read_text(encoding="utf-8")
            mutant = Mutant(fichier.name, 1, texte.splitlines()[1].find(" > "), " > ", " >= ")
            poser(fichier, appliquer(texte, mutant))
            mute = fichier.read_bytes() != avant
            reecrits = restaurer({fichier: avant})
            cas.append((f"le mutant est bien pose sur un fichier en {style}", mute))
            cas.append(
                (f"apres restauration, le fichier en {style} est identique a l octet pres",
                 fichier.read_bytes() == avant)
            )
            cas.append(
                (f"la restauration d un fichier en {style} se DECLARE (fichier reecrit)",
                 reecrits == [fichier])
            )

            # Le chemin fautif, pour prouver que le cas DISCRIMINE : `write_text` ne preserve
            # pas les octets d un fichier en LF sur une plateforme ou os.linesep vaut CRLF.
            fichier.write_text(texte, encoding="utf-8")
            identique = fichier.read_bytes() == avant
            marque = "preserve" if identique else "ALTERE"
            print(f"             (temoin : `write_text` {marque} un fichier en {style})")
            fichier.write_bytes(avant)
    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def verifier_chemins_de_couverture() -> int:
    """A-5 — tout pan non couvert sort un CHEMIN, pas seulement un motif.

    Aux bancs, TOUS les pans attendus sont couverts : le mécanisme n y est jamais exercé. Il l est
    ici sur un rapport sans aucune sortie d adaptateur — le cas où TOUS les pans manquent — car
    un chemin de couverture qui pourrit en silence rendrait la sortie d un audit partiel aussi
    inexploitable qu avant : une liste de manques au lieu d une liste de travaux.
    """
    from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE
    from forge_tests.noyau import POUR_COUVRIR_DEFAUT, rapport

    echecs = 0
    print("-" * 78)
    print("  A-5 — pans non couverts : un chemin de couverture, jamais un constat seul")

    chemins = {
        module.PAN: module.POUR_COUVRIR
        for module in REGISTRE.values()
        if getattr(module, "POUR_COUVRIR", None)
    }
    vide = rapport([], PANS_ATTENDUS, pour_couvrir=chemins)
    entrees = vide["pans_non_couverts"]
    cas = [
        (f"les {len(PANS_ATTENDUS)} pans attendus sortent non couverts",
         len(entrees) == len(PANS_ATTENDUS)),
        ("chaque entree porte {pan, motif, pour_couvrir}",
         all({"pan", "motif", "pour_couvrir"} <= set(e) for e in entrees)),
        ("aucun chemin n est vide", all(e["pour_couvrir"].strip() for e in entrees)),
        ("aucun pan attendu ne retombe sur le chemin generique",
         not [e for e in entrees if e["pour_couvrir"] == POUR_COUVRIR_DEFAUT]),
        ("chaque adaptateur du registre declare son POUR_COUVRIR",
         len(chemins) == len({m.PAN for m in REGISTRE.values() if hasattr(m, "PAN")})),
    ]
    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    if not echecs:
        print(f"             -> {entrees[0]['pan']} : {entrees[0]['pour_couvrir'][:90]}…")
    return echecs


def verifier_reprise_apres_enrichissement() -> int:
    """A-5/A-7 — enrichir un champ du rapport ne doit pas casser la relecture des anciens.

    `pans_non_couverts` est passé de `["qualif"]` à `[{pan, motif, pour_couvrir}]`. Une reprise
    qui refuserait l ancienne forme transformerait une amélioration de rapport en rupture
    d outil : le rapport de la semaine dernière deviendrait illisible, et le cycle « première
    passe, saisie des identifiants, seconde passe » que la reprise existe pour permettre serait
    cassé au moment précis où il sert.
    """
    from forge_tests.adaptateurs import PANS_ATTENDUS
    from forge_tests.reprise import fusionner, pans_a_rejouer

    echecs = 0
    print("-" * 78)
    print("  A-5 / A-7 — reprise : les deux formes de `pans_non_couverts` restent relisibles")

    socle = {
        "findings": [], "adaptateurs": [{"pan": "api", "verdict": "PASS"}],
        "couverture_par_pan": {}, "non_testables": [],
    }
    neuf = {
        **socle,
        "pans_non_couverts": [{"pan": "qualif", "motif": "m", "pour_couvrir": "chemin qualif"}],
        "seuils": {"mutation_globale": {"valeur": 0.7}}, "modules": [{"module": "app/x.py"}],
    }
    ancien = {**socle, "pans_non_couverts": ["qualif"]}
    vide = {
        "adaptateurs": [], "couverture_par_pan": {}, "mutation": {}, "pans_non_couverts": [],
        "motifs_non_couverture": {}, "findings": [], "non_testables": [], "non_juge": [],
    }
    fusion = fusionner(neuf, vide, "r.json", ["qualif"], PANS_ATTENDUS)
    cas = [
        ("un rapport A-5 designe ses pans a rejouer", pans_a_rejouer(neuf) == ["qualif"]),
        ("un rapport ANTERIEUR a A-5 aussi", pans_a_rejouer(ancien) == ["qualif"]),
        ("la fusion reconstruit {pan, motif, pour_couvrir}",
         all({"pan", "motif", "pour_couvrir"} <= set(e) for e in fusion["pans_non_couverts"])),
        ("les seuils du rapport repris survivent a la fusion", bool(fusion["seuils"])),
        ("l inventaire de modules aussi", fusion["modules"] == [{"module": "app/x.py"}]),
    ]
    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def verifier_qualification() -> int:
    """RT-6a — un manque de CONFIGURATION doit devenir un non-testable nommé, pas un silence.

    Le mécanisme ne se déclenche que sur un projet réellement mal configuré : aucun banc ne
    peut donc l exercer. Il est vérifié ici sur pièces, faute de quoi il pourrait pourrir sans
    que rien ne le dise — exactement le genre d angle mort que le framework existe pour ôter.
    """
    from forge_tests import qualification
    from forge_tests.noyau import SortieAdaptateur

    echecs = 0
    print("-" * 78)
    print("  RT-6a — qualification : ce que la configuration absente rend non testable")

    traces = [
        ("KeyError Python", "KeyError: 'ZZ_JETON_CLIENT'", "ZZ_JETON_CLIENT"),
        ("message explicite", "RuntimeError: ZZ_CLE_API is not set", "ZZ_CLE_API"),
        ("pydantic-settings", "ZZ_MOT_DE_PASSE\n  Field required", "ZZ_MOT_DE_PASSE"),
        ("saut pytest", "SKIPPED [1] tests/test_x.py:4: requires ZZ_URL_TIERS", "ZZ_URL_TIERS"),
    ]
    for libelle, trace, attendu in traces:
        qualification.oublier("/projet-fictif")
        trouves = qualification.detecter("/projet-fictif", "backend", trace)
        ok = attendu in trouves
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] detection — {libelle} ({attendu})")

    # Une variable CITEE mais FOURNIE n est pas un manque : ce serait du bruit, pas un fait.
    os.environ["ZZ_DEJA_FOURNIE"] = "valeur"
    qualification.oublier("/projet-fictif")
    bruit = qualification.detecter("/projet-fictif", "backend", "KeyError: 'ZZ_DEJA_FOURNIE'")
    ok = not bruit
    echecs += not ok
    print(f"  [{'OK     ' if ok else 'ECHEC  '}] une variable FOURNIE n est pas declaree manquante")
    del os.environ["ZZ_DEJA_FOURNIE"]

    # Bout en bout : trace -> declaration -> non_testables portes par la sortie d adaptateur.
    qualification.oublier("/projet-fictif")
    qualification.detecter("/projet-fictif", "backend", "KeyError: 'ZZ_JETON_CLIENT'")
    sortie = SortieAdaptateur("api-fictif", "api", "/projet-fictif", "SKIP")
    qualification.qualifier([sortie], Path("/projet-fictif"), {})
    ok = bool(sortie.non_testables) and sortie.non_testables[0].champs_requis == ["ZZ_JETON_CLIENT"]
    echecs += not ok
    print(f"  [{'OK     ' if ok else 'ECHEC  '}] un pan SKIP mal configure porte ses champs_requis")
    qualification.oublier("/projet-fictif")
    return echecs


def verifier_champs_par_pan() -> int:
    """RT-13 — les champs d un pan SKIP sont les SIENS, jamais empruntes a un autre pan.

    Le domaine « acces » est un sac partage : l authentification y depose le compte, le pan
    `qualif` son URL d instance peuplee. Tout pan en SKIP repartait avec le sac entier — le pan
    `data` reclamait `FORGE_TESTS_QUALIF_URL`, qui ne l aurait jamais debloque. Cout mesure :
    16 actions `manuelle_utilisateur` fausses au rapport ASD du 07/08.

    Aucun banc ne peut l exercer : aux bancs, tous les pans sont couverts. Le cas est donc
    verifie sur pieces, avec sa contrepartie ROUGE — le champ EST bien dans le sac partage,
    faute de quoi le controle serait vide et ne prouverait rien.
    """
    from forge_tests import qualification
    from forge_tests.adaptateurs import REGISTRE as ADAPTATEURS
    from forge_tests.noyau import SortieAdaptateur

    echecs = 0
    print("-" * 78)
    print("  RT-13 — champs requis : chaque pan publie les SIENS, jamais ceux d un autre")

    cible = "/projet-fictif-rt13"
    qualification.oublier(cible)
    # Ce que les adaptateurs declarent vraiment quand ils ne peuvent pas mesurer : l URL de
    # l instance peuplee (pan `qualif`) et le compte de lecture (authentification).
    qualification.declarer(cible, "acces", ("FORGE_TESTS_QUALIF_URL",))
    qualification.declarer(cible, "acces", ("FORGE_TESTS_LOGIN", "FORGE_TESTS_PASSWORD"))
    # Une variable PROPRE AU PROJET, citee par une trace : aucun adaptateur ne la revendique.
    qualification.detecter(cible, "backend", "KeyError: 'ZZ_JETON_CLIENT'")

    partage = qualification.requis(cible, "backend", "acces")
    sorties = [
        SortieAdaptateur("data-sql", "data", cible, "SKIP"),
        SortieAdaptateur("qualif-navigateur", "qualif", cible, "SKIP"),
    ]
    qualification.qualifier(sorties, Path(cible), ADAPTATEURS)
    champs = {
        sortie.pan: set(sortie.non_testables[0].champs_requis) if sortie.non_testables else set()
        for sortie in sorties
    }
    revendiques = qualification.proprietaires(ADAPTATEURS)
    qualification.oublier(cible)

    cas = [
        # ROUGE : sans ce temoin, le controle passerait sur un sac vide et ne prouverait rien.
        ("temoin : le domaine partage porte bien FORGE_TESTS_QUALIF_URL",
         "FORGE_TESTS_QUALIF_URL" in partage),
        ("le pan qui la REVENDIQUE la recoit (qualif)",
         "FORGE_TESTS_QUALIF_URL" in champs["qualif"]),
        ("un pan qui ne la revendique pas ne l EMPRUNTE plus (data)",
         "FORGE_TESTS_QUALIF_URL" not in champs["data"]),
        ("le compte de lecture ne fuit pas non plus vers un pan de fichiers (data)",
         not {"FORGE_TESTS_LOGIN", "FORGE_TESTS_PASSWORD"} & champs["data"]),
        # Le filtre ne doit pas SUR-filtrer : une variable du projet audite n a pas de
        # proprietaire declare et doit continuer d atteindre les pans de son domaine.
        ("un champ que nul adaptateur ne revendique atteint toujours le pan (ZZ_JETON_CLIENT)",
         "ZZ_JETON_CLIENT" in champs["data"]),
        ("chaque champ revendique l est par au moins un pan du registre",
         all(pans for pans in revendiques.values())),
    ]
    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    detail = " · ".join(
        f"{champ} -> {', '.join(sorted(pans))}" for champ, pans in sorted(revendiques.items())
    )
    print(f"             revendications : {detail}")
    return echecs


def verifier_registre_dette() -> int:
    """Le registre de dette COMMITTÉ dit-il encore la dette du code d aujourd hui ?

    Le registre était régénéré à la main. Régénéré à la main, il n est pas régénéré : la dette
    du jour se lit alors dans un fichier qui décrit le code d avant-hier, et personne ne le
    sait. Le contrôle est donc joué ici, et il ÉCHOUE — il ne signale pas.

    Deux règles de sémantique sont vérifiées avec lui (TF-0004) : l identité d une entrée
    survit à la REFORMULATION de son énoncé, et le statut `ok` — le seul qui prétende à une
    fermeture — exige une `preuve` nommée. Chaque règle porte sa contrepartie rouge : un
    contrôle qu on ne voit jamais échouer ne contrôle rien.
    """
    import json
    import tempfile

    from forge_tests import dette

    echecs = 0
    print("-" * 78)
    print("  TF-0002/TF-0004 — registre de dette : synchronise, et fermetures prouvees")

    ecarts_reels = dette.verifier()
    cas = [(f"le registre committe est SYNCHRONISE avec le code ({len(ecarts_reels)} ecart(s))",
            not ecarts_reels)]
    for ecart in ecarts_reels[:5]:
        print(f"             -> {ecart}")

    with tempfile.TemporaryDirectory() as temporaire:
        copie = Path(temporaire) / "registre.json"
        contenu = json.loads(dette.REGISTRE.read_text(encoding="utf-8"))

        # ROUGE 1 — une entree du code absente du registre doit etre DENONCEE.
        ampute = {**contenu, "dette": contenu["dette"][1:]}
        copie.write_text(
            json.dumps(ampute, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        cas.append(("un registre ampute d une entree est DENONCE", bool(dette.verifier(copie))))

        # ROUGE 2 — `ok` sans preuve : une dette ne se ferme pas parce qu on l a decretee close.
        sans_preuve = json.loads(json.dumps(contenu))
        sans_preuve["dette"][0]["statut"] = "ok"
        sans_preuve["dette"][0].pop("preuve", None)
        copie.write_text(
            json.dumps(sans_preuve, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        motifs = dette.verifier(copie)
        cas.append(("un statut `ok` SANS preuve est refuse",
                    any("SANS preuve" in motif for motif in motifs)))

    # VERT — la meme entree, fermee SUR PREUVE, passe : le controle DISCRIMINE.
    courant = dette.collecter()
    premier = courant[0]
    identite = f"{premier['domaine']}-042"
    ferme = {
        identite: {
            "id": identite, "domaine": premier["domaine"], "enonce": premier["enonce"],
            "statut": "ok", "preuve": "recette : verifier_registre_dette",
        }
    }
    projete = {e["id"]: e for e in dette.projeter(ferme)["dette"]}
    cas.append(("une entree fermee SUR PREUVE garde son `ok` et sa preuve",
                projete.get(identite, {}).get("statut") == "ok"
                and bool(projete.get(identite, {}).get("preuve"))))

    # IDENTITE — l enonce est REFORMULE dans le code : l entree ne doit pas etre remplacee par
    # un couple « resolue + todo neuf ». C est ce couple qui produisait 27 fausses resolutions.
    reformule = {
        identite: {
            "id": identite, "domaine": premier["domaine"],
            "enonce": premier["enonce"] + " (ancienne formulation, mot en plus)",
            "statut": "assume", "note": "note a preserver",
        }
    }
    declarees: list[str] = []
    projete = {e["id"]: e for e in dette.projeter(reformule, declarees)["dette"]}
    garde = projete.get(identite, {})
    cas.append(("un enonce REFORMULE conserve son identifiant, son statut et sa note",
                garde.get("statut") == "assume" and garde.get("note") == "note a preserver"
                and garde.get("enonce") == premier["enonce"]))
    cas.append(("le rapprochement par ressemblance est DECLARE, jamais silencieux",
                bool(declarees)))

    # RETRAIT — un enonce disparu du code SANS preuve n est pas une fermeture.
    orphelin = {
        "labo-001": {
            "id": "labo-001", "domaine": "labo",
            "enonce": "labo : enonce sans aucun equivalent dans le code du depot",
            "statut": "todo",
        }
    }
    projete = {e["id"]: e for e in dette.projeter(orphelin)["dette"]}
    cas.append(("un enonce disparu du code sort `retiree`, jamais `ok`",
                projete.get("labo-001", {}).get("statut") == dette.STATUT_RETIRE))

    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    compte = dette.resume()
    print("             registre : " + " · ".join(f"{s}={n}" for s, n in sorted(compte.items())))
    if declarees:
        for ligne in declarees[:3]:
            print(f"             -> {ligne}")
    return echecs


def verifier_suite_unitaire() -> int:
    """La suite unitaire du dépôt, jouée PAR la recette — sinon rien ne la lance.

    Forge Tests n avait pour harnais que cette recette : « un `pytest` à la racine ne collecte
    rien » était l écart déclaré au README. Une suite unitaire qu aucune vérification ne joue
    serait le même écart sous un autre nom — la loi du dépôt vaut d abord pour lui-même. Elle
    est donc une section comme les autres, et son échec fait tomber S-01.
    """
    import subprocess

    print("-" * 78)
    print("  TF-0006 — suite unitaire du depot (pytest)")
    try:
        resultat = subprocess.run(
            # Pas de `-q` ici : `addopts` le porte deja, et un second `-q` supprimerait
            # justement la ligne de bilan (« N passed ») que la recette affiche.
            [sys.executable, "-m", "pytest"],
            cwd=RACINE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as erreur:
        print(f"  [ECHEC  ] pytest non lancable : {type(erreur).__name__}: {erreur}")
        return 1
    lignes = [ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip()]
    bilans = [ligne for ligne in lignes if "passed" in ligne or "failed" in ligne]
    resume = bilans[-1] if bilans else (lignes[-1] if lignes else "aucune sortie")
    ok = resultat.returncode == 0
    print(f"  [{'OK     ' if ok else 'ECHEC  '}] pytest : {resume[:80]}")
    if not ok:
        for ligne in lignes[-15:]:
            print(f"             {ligne}")
    return 0 if ok else 1


def _resoudre_ruff() -> tuple[list[str], str] | None:
    """Localise ruff : module de l interpréteur courant SI disponible, sinon exécutable du PATH.

    L appel figé `sys.executable -m ruff` supposait ruff installé dans l interpréteur qui joue
    la recette. Lancée hors du venv canonique (`python recette/verifier_corpus.py` d un poste),
    la section sortait « ruff : aucune sortie » — un ÉCHEC dont le motif réel (l outil n est pas
    là) restait tu, indiscernable d un ruff cassé, sur un dépôt par ailleurs propre. La
    résolution est donc explicite, et son origine est AFFICHÉE au verdict.
    """
    import importlib.util
    import shutil

    if importlib.util.find_spec("ruff") is not None:
        return [sys.executable, "-m", "ruff"], "module de l interpreteur"
    executable = shutil.which("ruff")
    if executable:
        return [executable], f"executable du PATH : {executable}"
    return None


def verifier_lint() -> int:
    """Le linter du dépôt, joué PAR la recette — TF-0226.

    Même raison que la suite unitaire ci-dessus, et le constat qui l a imposée est du même
    genre : `ruff` était configuré dans `pyproject.toml`, rendait 21 erreurs, et aucun des
    pas de cette recette ne l appelait. Un linter que rien ne joue n est pas un garde-fou,
    c est une décoration — la même classe de défaut qu une consigne citée par aucun run.

    Le pas est armé APRÈS avoir soldé les 21 : un pas qui naît rouge est un pas qu on
    désarme au premier run pressé, et il aurait valu mieux ne pas l écrire.

    Le périmètre suit celui de la configuration : le code, les tests, et la recette
    elle-même — s en exclure serait juger les autres sans se juger soi.

    Un ruff INTROUVABLE (ni module, ni PATH) se DIT avec son motif et reste un ÉCHEC :
    « outil absent » n est jamais « dépôt propre » — c est la loi 3, l oubli n existe pas.
    """
    import subprocess

    print("-" * 78)
    print("  TF-0226 — linter du depot (ruff)")
    resolution = _resoudre_ruff()
    if resolution is None:
        # DÉCLARÉ, jamais silencieux ni confondu avec un contrôle vert : l outil est ABSENT.
        print("  [ECHEC  ] ruff INTROUVABLE : ni module de l interpreteur courant "
              f"({sys.executable}), ni executable `ruff` sur le PATH.")
        print("             Un linter absent du poste n est pas un depot propre — le controle")
        print("             n a PAS eu lieu. Pour l installer : `uv sync` (groupe dev), ou")
        print("             rejouer la recette via `uv run python recette/verifier_corpus.py`.")
        return 1
    commande, origine = resolution
    try:
        resultat = subprocess.run(
            [*commande, "check", "forge_tests", "tests", "recette",
             "--output-format", "concise"],
            cwd=RACINE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as erreur:
        # DÉCLARÉ, jamais silencieux : un linter absent du poste n est pas un dépôt propre.
        print(f"  [ECHEC  ] ruff non lancable ({origine}) : {type(erreur).__name__}: {erreur}")
        return 1
    lignes = [ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip()]
    ok = resultat.returncode == 0
    resume = (lignes[-1] if lignes else "aucune sortie")[:80]
    print(f"  [{'OK     ' if ok else 'ECHEC  '}] ruff ({origine}) : {resume}")
    if not ok:
        for ligne in lignes[:15]:
            print(f"             {ligne}")
        if resultat.stderr.strip():
            print(f"             stderr : {resultat.stderr.strip().splitlines()[0][:80]}")
    return 0 if ok else 1


def verifier_lecture_sql() -> int:
    """Nombre de cas de lecture SQL en echec. Zero attendu."""
    from forge_tests.sql import decouper

    echecs = 0
    print("-" * 78)
    print("  RT-8 — lecture SQL : filtrer AVANT de decouper")
    for libelle, source, attendu in LECTURE_SQL:
        obtenu = decouper(source)
        ok = obtenu == attendu
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
        if not ok:
            print(f"             attendu {attendu}")
            print(f"             obtenu  {obtenu}")
    return echecs


def _findings(
    rapport: dict, prefixes: tuple[str, ...], classes: tuple[str, ...] = ()
) -> list[dict]:
    """Les findings qui prouvent CETTE entrée du corpus — préfixe d identifiant ET classe.

    TF-0310 : le préfixe seul débordait. `interface:` (H-13, affordances inertes) appariait aussi
    `interface:ecart-servi:` (H-20), et `migration:` (H-05, migrations ni inversées ni rejouées)
    appariait aussi le `migration:<nom>:retour` de classe `divergence`. Une entrée pouvait donc
    sortir [DETECTE] sur le défaut d une AUTRE : un corpus qui mesure moins que ce qu il affiche,
    et le jour où le défaut propre à l entrée disparaît, personne ne l apprend.

    La classe est le discriminant naturel : c est elle que l adaptateur pose pour dire DE QUOI il
    parle, et deux défauts distincts n en partagent pas une par accident. `classes` vide est
    refusé par `test_tf_0310_appariement_par_classe.py` — un défaut sans classe déclarée
    rouvrirait le trou en silence.
    """
    return [
        f
        for f in rapport["findings"]
        if f["id"].startswith(prefixes) and (not classes or f.get("classe") in classes)
    ]


# --- Mandats 1 a 4 : cahiers derives, jeux synthetiques, dashboard, actions -------------------
JOUR_RECETTE = datetime.date(2026, 8, 7)


def _rapport_sur_pieces() -> dict:
    """Rapport de laboratoire exercant CHAQUE classe de finding, plus les deux causes d inaction.

    Aucun banc ne peut le produire : il faudrait un projet a la fois mal configure, sans
    adaptateur pour un pan, et porteur des onze classes de defaut. Le construire ici est le
    seul moyen de verifier la classification TERNAIRE sur toute son etendue — et notamment la
    branche `forge`, qui ne se declenche que sur une classe que la forge ne sait pas classer.
    """
    from forge_tests.actions import classifier

    classes = [
        ("element-non-exerce", "api", "code:GET /api/x=401"),
        ("element-non-exerce", "batch", "branche:batch.py:42"),
        ("element-non-exerce", "data", "contrainte:c_unique"),
        ("seuil-non-tenu", "api", "seuil:api"),
        ("mutant-survivant", "back", "mutant:app/calcul.py:12:+->-"),
        ("module-non-exerce", "back", "module-non-exerce:app/recherche.py"),
        ("affordance-inerte", "interface", "interface:ui/page.html:13:button"),
        ("affordance-sans-effet", "qualif", "qualif:effet:/:3:button"),
        ("divergence", "api", "divergence:code:GET /api/x=500"),
        ("route-en-defaut", "qualif", "qualif:route:/panne"),
        ("securite", "securite", "securite:app/main.py:8"),
        ("accessibilite", "accessibilite", "a11y:/inscription"),
        ("regression-visuelle", "visuel", "visuel:/accueil"),
        ("sonde-muette", "api", "sonde-muette:api"),
        # Classe INCONNUE du classifieur : elle doit produire un defaut d AUDITEUR nomme,
        # jamais un finding sans suite.
        ("classe-inventee-demain", "api", "futur:quelque-chose"),
    ]
    findings = [
        {
            "id": identifiant,
            "classe": classe,
            "pan": pan,
            "localisation": "labo",
            "message": f"constat mesure sur {identifiant}",
            "severite": "bloquant",
            "risque": 20 + rang,
        }
        for rang, (classe, pan, identifiant) in enumerate(classes)
    ]
    non_testables = [
        {
            "element": "pan:qualif",
            "champs_requis": ["FORGE_TESTS_QUALIF_URL"],
            "pan": "qualif",
            "motif": "qualif : non exercable sans configuration (constate)",
        }
    ]
    pans_non_couverts = [
        {"pan": "qualif", "motif": "instance non servie", "pour_couvrir": "servir l instance"},
        {"pan": "visuel", "motif": "adaptateur absent", "pour_couvrir": "ecrire l adaptateur"},
    ]
    return {
        "verdict": "PARTIEL",
        "adaptateurs": [],
        "couverture_par_pan": {
            "api": {
                "inventorie": 3, "exerce": 2, "ratio": 0.6667, "seuil": 1.0,
                "elements_exerces": ["code:GET /api/x=200", "endpoint:GET /api/x"],
                "elements_non_exerces": ["code:GET /api/x=401"],
            }
        },
        "mutation": {},
        "seuils": {
            "couverture_surface_api": {
                "valeur": 1.0, "severite": "bloquant", "porte_sur": "endpoints x codes",
                "justification": "exhaustivite de surface",
            }
        },
        "modules": [{"module": "app/calcul.py", "exerce": True, "mute": True}],
        "pans_non_couverts": pans_non_couverts,
        "motifs_non_couverture": {},
        "bandes_de_risque": {"critique": 0, "standard": len(findings), "differe": 0, "non_cote": 0},
        "findings": findings,
        "non_testables": non_testables,
        "non_juge": [],
        "actions": classifier(findings, non_testables, pans_non_couverts),
    }


def verifier_actions() -> int:
    """Mandat 2 — la classification TERNAIRE vit au RAPPORT, et n oublie aucun finding."""
    from forge_tests.actions import CATEGORIES, ETAPES, repartition

    echecs = 0
    print("-" * 78)
    print("  M2 — actions[] : une suite classee pour chaque constat, au rapport JSON")

    labo = _rapport_sur_pieces()
    actions = labo["actions"]
    compte = repartition(actions)
    refs = [a["finding_ref"] for a in actions]

    manquants = [
        f"{f['pan']}/{f['id']}"
        for f in labo["findings"]
        if f"{f['pan']}/{f['id']}" not in refs
    ]
    inconnue = [
        a for a in actions if a["finding_ref"] == "api/futur:quelque-chose"
    ]
    cas = [
        ("chaque finding porte exactement une action", not manquants
         and len([r for r in refs if not r.startswith(("non-testable:", "pan-non-couvert:"))])
         == len(labo["findings"])),
        ("au moins une action par CATEGORIE",
         all(compte["par_categorie"][c] >= 1 for c in CATEGORIES)),
        ("au moins une action par ETAPE CIBLE",
         all(compte["par_etape"][e] >= 1 for e in ETAPES)),
        ("une classe de finding inconnue sort un DEFAUT D AUDITEUR (etape `forge`)",
         bool(inconnue) and inconnue[0]["etape_cible"] == "forge"),
        ("la configuration absente est `manuelle_utilisateur` / `mep-config`",
         any(a["categorie"] == "manuelle_utilisateur" and a["etape_cible"] == "mep-config"
             for a in actions if a["finding_ref"].startswith("non-testable:"))),
        ("un pan sans adaptateur est un defaut de la FORGE, pas de l exploitant",
         any(a["etape_cible"] == "forge" for a in actions
             if a["finding_ref"] == "pan-non-couvert:visuel")),
        ("aucune categorie hors vocabulaire",
         all(a["categorie"] in CATEGORIES for a in actions)),
        ("aucune etape hors vocabulaire", all(a["etape_cible"] in ETAPES for a in actions)),
        ("toute action porte un attendu non vide",
         all(str(a.get("attendu") or "").strip() for a in actions)),
    ]
    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    print(
        "             repartition — "
        + " · ".join(f"{c}={compte['par_categorie'][c]}" for c in CATEGORIES)
    )
    detail = " · ".join(f"{e}={compte['par_etape'][e]}" for e in ETAPES)
    print("             etapes     — " + detail)
    return echecs


def verifier_jeux_de_donnees() -> int:
    """Mandat 1 — le garde-fou des jeux de donnees REFUSE, il ne signale pas."""
    from forge_tests.livrables import jeux

    echecs = 0
    print("-" * 78)
    print("  M1 — jeux de donnees : synthetiques, et prouves tels AVANT ecriture")

    os.environ["ZZ_CLE_API_PROJET"] = "valeur-de-production-a-ne-jamais-recopier"
    try:
        cas = []
        propre = jeux.construire(
            [
                {
                    "code": "T2", "famille": "technique",
                    "sous_chapitres": [{"libelle": "table t", "elements": [{"id": "table:t"}]}],
                }
            ],
            "Produit",
        )
        try:
            jeux.verifier(propre, None)
            cas.append(("un jeu genere par la forge passe le garde-fou", True))
        except jeux.DonneeNonSynthetique as refus:
            cas.append((f"un jeu genere par la forge passe le garde-fou ({refus})", False))

        for libelle, charge in (
            ("un courriel d un domaine REEL est refuse", {"a": "jean.dupont@asdpatrimoine.fr"}),
            ("une cle d API est refusee", {"a": "sk-live-0123456789abcdefghij"}),
            ("un jeton JWT est refuse", {"a": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.zz"}),
            ("une empreinte hexadecimale longue est refusee", {"a": "a" * 40}),
            ("une URL a identifiants est refusee", {"a": "postgres://u:motdepasse@h/db"}),
        ):
            refuse = False
            try:
                jeux.verifier(charge, None)
            except jeux.DonneeNonSynthetique:
                refuse = True
            cas.append((libelle, refuse))

        refuse = False
        try:
            jeux.verifier({"a": "extrait : valeur-de-production-a-ne-jamais-recopier"}, None)
        except jeux.DonneeNonSynthetique:
            refuse = True
        cas.append(("une valeur de configuration du projet audite est refusee", refuse))

        # Le courriel synthetique, lui, doit passer : un garde-fou qui refuse tout ne garde rien.
        passe = True
        try:
            jeux.verifier({"a": f"alix.martel@{jeux.DOMAINE}"}, None)
        except jeux.DonneeNonSynthetique:
            passe = False
        cas.append(("un courriel du domaine reserve passe (le garde-fou DISCRIMINE)", passe))
    finally:
        del os.environ["ZZ_CLE_API_PROJET"]

    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def verifier_cahiers(rouge: dict) -> int:
    """Mandat 1 — exhaustivite opposable, sceau qui trahit l edition, deux runs identiques."""
    import tempfile

    from forge_tests.adaptateurs import REGISTRE as ADAPTATEURS
    from forge_tests.livrables import produire
    from forge_tests.livrables import surface as surface_mod
    from forge_tests.livrables.nommage import empreinte, verifier_sceau

    echecs = 0
    print("-" * 78)
    print("  M1 — cahiers derives : exhaustivite, sceau, determinisme")

    cas: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        premiers = produire(rouge, ROUGE, Path(t1), jour=JOUR_RECETTE, rapport_nom="rouge.json")
        seconds = produire(rouge, ROUGE, Path(t2), jour=JOUR_RECETTE, rapport_nom="rouge.json")

        # 1. Determinisme : deux productions du MEME rapport donnent le MEME octet.
        for nature in ("fonctionnel", "technique", "jeu", "dashboard"):
            identique = (
                empreinte(premiers[nature].read_bytes()) == empreinte(seconds[nature].read_bytes())
            )
            cas.append((f"deux runs produisent un {nature} identique (sha256)", identique))

        # 2. Le sceau atteste le corps, et TRAHIT une edition manuelle.
        for nature in ("fonctionnel", "technique"):
            texte = premiers[nature].read_text(encoding="utf-8")
            intact, motif = verifier_sceau(texte)
            cas.append((f"le cahier {nature} est scelle et intact ({motif[:40]}…)", intact))
            altere, _ = verifier_sceau(texte.replace("au moins un cas", "au moins deux cas", 1))
            cas.append((f"une edition manuelle du cahier {nature} est TRAHIE par le sceau",
                        not altere))
        cas.append(("un document sans sceau n est pas repute intact",
                    not verifier_sceau("# cahier ecrit a la main")[0]))

        # 3. Exhaustivite opposable : chaque element du rapport porte un cas OU est declare.
        fonctionnel = premiers["fonctionnel"].read_text(encoding="utf-8")
        technique = premiers["technique"].read_text(encoding="utf-8")
        ensemble = fonctionnel + technique
        inventaire = surface_mod.inventaire(rouge)
        absents = [
            element["id"]
            for elements in inventaire.values()
            for element in elements
            if element["id"] not in ensemble
        ]
        cas.append(
            (f"chaque element inventorie figure au cahier ({len(absents)} absent(s))", not absents)
        )
        if absents:
            print(f"             absents : {', '.join(absents[:5])}")

        # 4. Chapitres DERIVES : autant de chapitres que le registre en declare, pas un de moins.
        attendus = {c["code"] for c in surface_mod.chapitres(ADAPTATEURS)}
        vus = {code for code in attendus if f"## {code} — " in ensemble}
        cas.append((f"les {len(attendus)} chapitres derives du registre sont tous presents",
                    vus == attendus))

    # 5. ROUGE — un element NON COUVERT doit etre NOMME, avec sa raison. Sur un rapport ou tout
    #    est mesurable, le mecanisme ne se declenche pas : on l exerce sur pieces.
    labo = _rapport_sur_pieces()
    with tempfile.TemporaryDirectory() as t3:
        chemins = produire(labo, ROUGE, Path(t3), jour=JOUR_RECETTE, rapport_nom="labo.json")
        texte = chemins["fonctionnel"].read_text(encoding="utf-8")
        cas.append(("un element non testable est NOMME en « non couvert »",
                    "pan:qualif" in texte and "NON COUVERTS" in texte))
        cas.append(("sa raison cite le champ a fournir",
                    "FORGE_TESTS_QUALIF_URL" in texte))
        cas.append(("un pan sans adaptateur sort GRISE avec son chemin de couverture",
                    "ecrire l adaptateur" in texte or "ecrire l adaptateur" in
                    chemins["technique"].read_text(encoding="utf-8")))

    # 6. G-1 — deposer les livrables DANS le projet audite est refuse avant toute ecriture.
    from forge_tests.livrables import DepotInterdit

    refuse = False
    try:
        produire(labo, ROUGE, ROUGE / "propositions", jour=JOUR_RECETTE)
    except DepotInterdit:
        refuse = True
    cas.append(("G-1 : un depot DANS le projet audite est refuse", refuse))
    cas.append(("G-1 : rien n a ete ecrit dans le projet",
                not (ROUGE / "propositions").exists()))

    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def verifier_dashboard(rouge: dict) -> int:
    """Mandat 2 — totaux strictement egaux au rapport, zero secret, charte PASS."""
    import subprocess
    import tempfile

    from forge_tests.livrables import dashboard as dash
    from forge_tests.livrables import produire

    echecs = 0
    print("-" * 78)
    print("  M2 — dashboard : totaux exacts, zero reseau, zero secret, charte PASS")

    cas: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as temporaire:
        chemins = produire(rouge, ROUGE, Path(temporaire), jour=JOUR_RECETTE, rapport_nom="r.json")
        page = chemins["dashboard"].read_text(encoding="utf-8")

        cas.append(("les totaux affiches sont EGAUX au rapport", not dash.controler(page, rouge)))

        # Le controle doit DISCRIMINER : on fausse un total, il doit le voir.
        attendus = dash.totaux(rouge)
        faux = page.replace(
            f'data-total="echecs">{attendus["echecs"]}<',
            f'data-total="echecs">{attendus["echecs"] - 1}<',
            1,
        )
        ecarts = dash.controler(faux, rouge)
        cas.append((f"un total VOLONTAIREMENT faux est detecte ({(ecarts or ['—'])[0][:52]}…)",
                    bool(ecarts)))
        manque = page.replace('data-total="non_joues"', 'data-total="autrechose"', 1)
        cas.append(("un total RETIRE de la page est detecte", bool(dash.controler(manque, rouge))))

        # Zero reseau : aucune ressource DISTANTE. Le controle porte sur ce qui declenche une
        # requete (href, src, @import, url()), pas sur la presence du texte « http » — l URL de
        # l instance auditee figure legitimement dans les constats du pan qualif, et l interdire
        # reviendrait a censurer le sujet meme de l audit.
        for interdit in ('href="http', "href='http", 'src="', "src='", "@import", "url(http",
                         "<script src", "fetch(", "XMLHttpRequest"):
            cas.append((f"aucune ressource distante — « {interdit} » absent",
                        interdit not in page))
        # Favicon-lettre (13/08) : un <link rel="icon" href="data:…"> ne charge RIEN — le
        # littéral « <link » n'est plus banni en bloc, chaque <link> est jugé : seul l'icône
        # en data: URI est licite, tout autre <link (stylesheet, preconnect…) reste interdit.
        liens = re.findall(r"<link\b[^>]*>", page)
        cas.append(("aucun <link> autre que le favicon data: (contrôle affiné, pas affaibli)",
                    all('rel="icon"' in lien and 'href="data:' in lien for lien in liens)
                    and len(liens) == 1))
        cas.append(("un repli systeme est declare pour chaque police",
                    "system-ui" in page and "Syne" not in page))
        # Contrat de themes TF-0153 (mandat humain du 13/08) : un livrable d audit s ouvre
        # CLAIR chez tous ses lecteurs — l auto-sombre herite de l OS est retire (c est lui
        # qui a valu le retour humain), le sombre reste un CHOIX persiste. L assertion
        # inverse donc l ancienne exigence, elle ne l affaiblit pas : trois controles au
        # lieu d un.
        cas.append(("themes TF-0153 : clair par defaut STRICT (pas d auto-sombre OS)",
                    "prefers-color-scheme: dark" not in page))
        cas.append(("themes TF-0153 : palette sombre portee, au choix du lecteur",
                    ':root[data-theme="sombre"]' in page))
        cas.append(("themes TF-0153 : bascule presente et persistee",
                    "bascule-theme" in page and "localStorage" in page))
        cas.append(("les six onglets sont presents",
                    all(f'data-cible="{o}"' in page for o in
                        ("synthese", "fonctionnels", "techniques", "echecs", "non-joues",
                         "actions"))))

        # Charte et rendu Digit-AI, par les DEUX oracles du skill s ils sont installes. Le
        # premier lit le source (charte, a11y, print) ; le second RESSORT la page dans un vrai
        # navigateur a trois largeurs et mesure debordements, contrastes et chevauchements.
        # Aucun des deux ne remplace l autre : `check_html` a longtemps sorti PASS sur une page
        # dont les pastilles etaient a 3,07:1 de contraste — un statut illisible, donc un statut
        # qu on ne lit pas. Absent l oracle, la non-mesure est DECLAREE, pas contournee.
        scripts = Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "scripts"
        for nom, arguments in (
            ("check_html.py", []),
            ("render_page.py", ["--widths", "1280,768,390"]),
        ):
            oracle = scripts / nom
            if not oracle.exists():
                print(f"             [DECLARE] oracle absent ({oracle}) — non joue")
                continue
            issue = subprocess.run(
                [sys.executable, str(oracle), str(chemins["dashboard"]), *arguments],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            cas.append((f"{nom} : PASS (code {issue.returncode})", issue.returncode == 0))
            if issue.returncode != 0:
                print((issue.stdout or "")[-1200:])

    # Zero secret : une valeur d environnement sensible qui se retrouverait dans la page.
    os.environ["ZZ_JETON_DASHBOARD"] = "jeton-tres-secret-1234"
    try:
        pollue = {
            **rouge,
            "findings": [
                {
                    "id": "x", "classe": "securite", "pan": "securite", "localisation": "l",
                    "message": "fuite : jeton-tres-secret-1234", "severite": "bloquant",
                    "risque": 1,
                }
            ],
        }
        contexte = {
            "produit": "P", "date": "2026-08-07", "verdict": "FAIL", "rapport_nom": "r.json",
            "rapport_sha": "0" * 64,
        }
        vue = dash.construire(pollue, contexte, [])
        leve = False
        try:
            dash.verifier_absence_de_secrets(vue, None)
        except dash.SecretDansLeDashboard:
            leve = True
        cas.append(("une valeur d environnement dans la page est REFUSEE avant ecriture", leve))
    finally:
        del os.environ["ZZ_JETON_DASHBOARD"]

    for libelle, ok in cas:
        echecs += not ok
        print(f"  [{'OK     ' if ok else 'ECHEC  '}] {libelle}")
    return echecs


def prealables_absents(rapports: dict[str, dict | None]) -> dict[str, dict[str, str]]:
    """{banc: {pan: motif}} — les pans dont la mesure est tombée faute d un PRÉALABLE
    D ENVIRONNEMENT, jamais faute d un défaut du framework — TF-0299.

    Le 17/08, Docker Desktop arrêté a rendu 10 défauts du corpus en [MANQUE] (12/22) :
    indiscernables d une régression, le lecteur devait DÉDUIRE le démon absent. La section lint
    déclare déjà un ruff introuvable comme tel (TF-0226) ; même idiome ici, à ceci près que le
    préalable ne tombe pas sur une seule section mais sur les pans que la mesure a perdus — ils
    sont donc DÉRIVÉS du rapport (motif porteur du marqueur), jamais écrits en dur : une liste de
    pans « dépendants du conteneur » mentirait au premier pan ajouté.
    """
    from forge_tests.execution import PREALABLE_ABSENT

    absents: dict[str, dict[str, str]] = {}
    for nom, rapport in rapports.items():
        if not rapport:
            continue
        touches = {
            pan: motif
            for pan, motif in (rapport.get("motifs_non_couverture") or {}).items()
            if PREALABLE_ABSENT in motif
        }
        if touches:
            absents[nom] = touches
    return absents


def verifier_corpus_des_bancs(
    rouge: dict, vert: dict, alteres: list[str], empreintes_avant: dict,
    prealables: dict[str, dict[str, str]] | None = None,
) -> int:
    """Le cœur historique : les défauts plantés au banc rouge, le banc vert sans bloquant."""
    # TF-0299 — les pans que le préalable manquant a privés de mesure. Un défaut de leur ressort
    # n est ni détecté ni MANQUANT : sa mesure n a pas eu lieu, et l écrire « MANQUE » serait
    # accuser le framework d une régression qu il n a pas.
    sans_mesure = set((prealables or {}).get("rouge", {}))
    suspendus: list[tuple[str, str, str]] = []
    detectes = 0
    for code, pan, libelle, prefixes, classes in CORPUS:
        trouves = _findings(rouge, prefixes, classes)
        ok = bool(trouves)
        if not ok and pan in sans_mesure:
            suspendus.append((code, pan, libelle))
            print(f"  [NON MESURABLE] {code} ({pan:<10}) {libelle}")
            continue
        detectes += ok
        marque = "DETECTE" if ok else "MANQUE "
        print(f"  [{marque}] {code} ({pan:<10}) {libelle}")
        for f in trouves[:2]:
            print(f"             -> {f['id']}")
        if len(trouves) > 2:
            print(f"             -> ... et {len(trouves) - 2} autre(s) élément(s) nommé(s)")

    if suspendus:
        print("-" * 78)
        print(
            f"  PRÉALABLE D ENVIRONNEMENT ABSENT : {len(suspendus)} défaut(s) NON MESURABLES, "
            "nommés ici"
        )
        print("  un par un — ils ne sont NI détectés NI manquants, leur mesure n a pas eu lieu :")
        for code, pan, libelle in suspendus:
            print(f"             -> {code} ({pan:<10}) {libelle}")
        for pan, motif in sorted((prealables or {}).get("rouge", {}).items()):
            print(f"             pan {pan:<12} : {motif}")

    print("-" * 78)
    print(
        f"  banc ROUGE : {detectes}/{len(CORPUS) - len(suspendus)} défauts détectés"
        + (f" ({len(suspendus)} NON MESURABLES) · " if suspendus else " · ")
        + f"{len(rouge['findings'])} findings nommés"
    )
    bloquants_vert = [f for f in vert["findings"] if f.get("severite") == "bloquant"]
    signales_vert = [f for f in vert["findings"] if f.get("severite") != "bloquant"]
    print(f"  banc VERT  : {len(bloquants_vert)} finding(s) bloquant(s) — attendu 0")
    # TF-0299 — « 0 bloquant » sur un banc dont des pans n ont pas ete mesures est un vert
    # partiel : le dire est le meme devoir que pour le rouge, sinon la moitie saine du critere
    # se lit comme une preuve alors qu elle n en est pas une.
    sans_mesure_vert = sorted((prealables or {}).get("vert", {}))
    if sans_mesure_vert:
        print(
            f"               ATTENTION : {len(sans_mesure_vert)} pan(s) NON MESURE(S) faute d un "
            "prealable d environnement"
        )
        print(f"               ({', '.join(sans_mesure_vert)}) — ce « 0 bloquant » est PARTIEL")
    print(f"               {len(signales_vert)} signale(s) non bloquant(s), nommes :")
    for f in signales_vert:
        print(f"                 - {f['id']}")
    print(f"  verdicts   : rouge={rouge['verdict']} · vert={vert['verdict']}")

    # RT-6a — la section existe TOUJOURS, meme vide : son absence serait indiscernable d un
    # « rien a signaler », qui est precisement le silence que le framework interdit.
    for nom, rap in (("ROUGE", rouge), ("VERT", vert)):
        assert "non_testables" in rap, f"banc {nom} : section non_testables absente du rapport"
    print(
        f"  non_testables : rouge={len(rouge['non_testables'])} · "
        f"vert={len(vert['non_testables'])} (section presente dans les deux)"
    )

    # A-2/A-3 — l inventaire de modules et les seuils opposables sont des SECTIONS du rapport :
    # leur absence serait indiscernable d un « rien a dire », le silence que la forge interdit.
    for nom, rap in (("ROUGE", rouge), ("VERT", vert)):
        assert rap.get("modules"), f"banc {nom} : section modules[] absente ou vide"
        assert rap.get("seuils"), f"banc {nom} : section seuils absente du rapport"
    for entree in rouge["pans_non_couverts"] + vert["pans_non_couverts"]:
        assert entree.get("pour_couvrir"), f"pan {entree.get('pan')} : chemin de couverture absent"
    print(
        f"  modules[]     : rouge={len(rouge['modules'])} · vert={len(vert['modules'])} "
        f"({sum(1 for m in rouge['modules'] if m.get('exerce') is False)} jamais exerce(s) "
        "au rouge)"
    )
    print(f"  seuils        : {len(vert['seuils'])} seuils opposables publies au rapport")
    print(
        "  A-5 chemins   : "
        f"{len(rouge['pans_non_couverts'])} pan(s) non couvert(s) au rouge, chacun avec son "
        "`pour_couvrir`"
    )

    empreintes = sum(len(v) for v in empreintes_avant.values())
    print(
        f"  G-1 sources   : {empreintes} fichier(s) empreinte(s) "
        + ("— AUCUN altere par l audit" if not alteres else f"— ALTERES : {', '.join(alteres)}")
    )
    # Les défauts NON MESURABLES ne comptent pas comme échecs : ce serait rendre un verdict sur une
    # mesure qui n a pas eu lieu. C est le verdict d ENSEMBLE qui est suspendu (voir `verdict_s01`),
    # pas cette section qui accuse à leur place.
    return (len(CORPUS) - len(suspendus) - detectes) + len(bloquants_vert) + len(alteres)


# --- Sections de la recette --------------------------------------------------------------------
# Le prix de la recette est celui des audits complets des bancs : mutation, navigateur,
# conteneur. Les contrôles sur pièces, eux, coûtent quelques centièmes. Les séparer permet de
# rejouer en quelques secondes le seul mécanisme qu un correctif touche, au lieu de payer trois
# minutes pour vérifier une ligne. `bancs` dit CE QU IL FAUT AUDITER pour la section — et rien
# de plus : les cahiers et le dashboard se dérivent du seul rapport rouge, auditer le banc vert
# pour eux serait une minute et demie payée pour un rapport que personne ne lit.
SECTIONS: dict[str, dict] = {
    "corpus": {
        "bancs": ("rouge", "vert"),
        # Le compte est DÉRIVÉ du corpus : écrit en dur, il aurait menti au premier défaut
        # ajouté — c est arrivé au 17e (TF-0200, pan `prompts`).
        "titre": f"{len(CORPUS)} défauts du banc rouge, banc vert sans bloquant, empreintes G-1",
    },
    "unitaire": {"bancs": (), "titre": "TF-0006 — suite unitaire du dépôt (pytest)"},
    "lint": {"bancs": (), "titre": "TF-0226 — linter du dépôt (ruff)"},
    "sql": {"bancs": (), "titre": "RT-8 — lecture SQL"},
    "qualification": {"bancs": (), "titre": "RT-6a / RT-13 — configuration absente"},
    "dette": {"bancs": (), "titre": "TF-0002 / TF-0004 — registre de dette"},
    "divergences": {"bancs": (), "titre": "RT-9 / RT-10 — gardes et montages"},
    "chemins": {"bancs": (), "titre": "A-5 / A-7 — chemins de couverture et reprise"},
    "lecture-seule": {"bancs": (), "titre": "G-1 — restauration après mutation"},
    "actions": {"bancs": (), "titre": "M2 — actions[]"},
    "jeux": {"bancs": (), "titre": "M1 — jeux de données synthétiques"},
    "cahiers": {"bancs": ("rouge",), "titre": "M1 — cahiers dérivés"},
    "dashboard": {"bancs": ("rouge",), "titre": "M2 — dashboard"},
}


def verdict_s01(
    succes: bool, partielle: bool, prealables: dict[str, dict[str, str]]
) -> tuple[list[str], int]:
    """(lignes à imprimer, code de sortie) — le verdict, et RIEN d autre : TF-0299.

    Trois états déjà là, un quatrième posé ici, et l ordre entre eux est le sujet :

      - recette PARTIELLE : S-01 non prononcé (le sélecteur ne juge pas les sections tues) ;
      - **PRÉALABLE D ENVIRONNEMENT ABSENT et tout le reste vert** : S-01 non prononcé, code 3.
        C est le tranchage de TF-0299, et il suit TF-0294 à la lettre : « un verdict rendu sur une
        mesure impossible n est pas un verdict ». Un « NON TENU » ici serait le FAUX verdict que
        l item dénonce — dix défauts non mesurés ne sont pas dix régressions. La sémantique de S-01
        n est pas touchée : NON TENU garde son sens, TENU gagne une condition qu il avait déjà
        implicitement (la mesure a eu lieu) ;
      - préalable absent MAIS une section réellement rouge : « NON TENU » reste VRAI — quelque
        chose est rouge indépendamment du conteneur, et le taire au nom d une mesure manquante
        absoudrait un échec réel. Le préalable est alors dit, le verdict est rendu ;
      - rien à signaler : TENU ou NON TENU comme avant.
    """
    lignes: list[str] = []
    if prealables:
        for banc, pans in sorted(prealables.items()):
            lignes.append(
                f"  PRÉALABLE D ENVIRONNEMENT ABSENT — banc {banc} : "
                f"{len(pans)} pan(s) sans mesure ({', '.join(sorted(pans))})"
            )
    if partielle:
        return lignes, 0 if succes else 1
    if prealables and succes:
        lignes.append(
            "  S-01 NON PRONONCÉ — la mesure n a pas eu lieu pour les pans ci-dessus : le corpus"
        )
        lignes.append(
            "  n a donc pas ete mesuré en entier. Ni TENU (rien ne le prouve), ni NON TENU (aucune"
        )
        lignes.append(
            "  régression constatée). Lever le préalable, puis rejouer la recette ENTIÈRE."
        )
        return lignes, 3
    lignes.append("  S-01 TENU" if succes else "  S-01 NON TENU")
    return lignes, 0 if succes else 1


def _jouer(nom: str, rouge: dict | None, vert: dict | None, contexte: dict) -> int:
    if nom == "corpus":
        return verifier_corpus_des_bancs(
            rouge, vert, contexte["alteres"], contexte["empreintes_avant"],
            contexte["prealables"],
        )
    if nom == "unitaire":
        return verifier_suite_unitaire()
    if nom == "lint":
        return verifier_lint()
    if nom == "sql":
        return verifier_lecture_sql()
    if nom == "qualification":
        return verifier_qualification() + verifier_champs_par_pan()
    if nom == "dette":
        return verifier_registre_dette()
    if nom == "divergences":
        return verifier_divergences() + verifier_gardes_multi_modules()
    if nom == "chemins":
        return verifier_chemins_de_couverture() + verifier_reprise_apres_enrichissement()
    if nom == "lecture-seule":
        return verifier_lecture_seule()
    if nom == "actions":
        return verifier_actions()
    if nom == "jeux":
        return verifier_jeux_de_donnees()
    if nom == "cahiers":
        return verifier_cahiers(rouge)
    return verifier_dashboard(rouge)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verifier_corpus",
        description=(
            "Recette du corpus — critère de sortie S-01. Sans option, la recette ENTIÈRE est "
            "jouée et seule celle-là peut prononcer S-01."
        ),
    )
    parser.add_argument(
        "--section",
        nargs="+",
        choices=sorted(SECTIONS),
        default=None,
        metavar="SECTION",
        help=(
            "ne jouer que ces sections : "
            + " · ".join(
                f"{nom} ({'+'.join(d['bancs']) if d['bancs'] else 'sur pièces'})"
                for nom, d in SECTIONS.items()
            )
        ),
    )
    args = parser.parse_args(argv)

    choisies = list(args.section) if args.section else list(SECTIONS)
    partielle = len(choisies) < len(SECTIONS)
    a_auditer = {banc for nom in choisies for banc in SECTIONS[nom]["bancs"]}

    print("=" * 78)
    print("RECETTE PHASE 1 — critère de sortie S-01")
    if partielle:
        print(f"  SÉLECTION : {', '.join(choisies)}")
        print(f"  BANCS AUDITÉS : {', '.join(sorted(a_auditer)) or 'aucun (contrôles sur pièces)'}")

    # TF-0294 — l empreinte de l ARBRE DE TRAVAIL, relevée avant le premier contrôle. Le 15/08,
    # deux « S-01 NON TENU » ont été rendus sur un dépôt qu une campagne concurrente modifiait
    # pendant que la recette tournait : des échecs FANTÔMES, indiscernables d une régression
    # réelle, dont un a coûté une instruction complète avant d être écarté. Un verdict rendu sur
    # un arbre instable n est pas un verdict — il est donc REFUSÉ, jamais rendu NON TENU.
    arbre_avant = empreinte_arbre()
    if arbre_avant is None:
        print("  ARBRE : empreinte NON RELEVÉE (git muet) — la stabilité ne sera pas vérifiable")
    else:
        print(f"  ARBRE : {len(arbre_avant)} fichier(s) empreinté(s) à l ouverture (TF-0294)")
    print("=" * 78)

    rouge = vert = None
    contexte: dict = {"alteres": [], "empreintes_avant": {}, "prealables": {}}
    if a_auditer:
        # G-1 : l empreinte des sources des bancs AVANT tout audit. La mutation les altere le
        # temps d un mutant ; si un seul octet survit a la restauration, la recette le dit.
        bancs = [b for b in (ROUGE, VERT) if b.name.endswith(tuple(a_auditer))]
        contexte["empreintes_avant"] = {banc: _empreintes(banc) for banc in bancs}
        if "rouge" in a_auditer:
            rouge = analyser_servi(ROUGE)
        if "vert" in a_auditer:
            vert = analyser_servi(VERT)
        contexte["alteres"] = alterations(contexte["empreintes_avant"])
        # TF-0299 — relevé AVANT les sections : ce que les audits ont déclaré non mesurable faute
        # d un préalable d ENVIRONNEMENT. Les sections le lisent pour le DIRE, le verdict pour ne
        # pas prononcer sur une mesure qui n a pas eu lieu.
        contexte["prealables"] = prealables_absents({"rouge": rouge, "vert": vert})

    echecs = {nom: _jouer(nom, rouge, vert, contexte) for nom in choisies}

    # TF-0294 — second relevé, APRÈS le dernier contrôle : l arbre est-il resté celui qu on a
    # jugé ? Les altérations G-1 sont écartées — elles sont un échec MESURÉ de la restauration
    # après mutation, déjà nommé par la section `corpus`, et non le fait d une session tierce.
    bouges = instabilites(arbre_avant, empreinte_arbre(), contexte["alteres"])

    print("=" * 78)
    for nom, compte in echecs.items():
        print(f"  {'OK   ' if not compte else 'ECHEC'}  {nom:<14} {SECTIONS[nom]['titre']}")
    succes = not any(echecs.values())
    if bouges:
        # Verdict DISTINCT : ni TENU, ni NON TENU. Ce que la recette a mesuré porte sur un état
        # du dépôt qui n existe plus — rendre un verdict serait attribuer à une régression ce qui
        # peut n être que la campagne du voisin. Code de sortie 2, pour que l appelant le
        # distingue lui aussi de l échec (1) et du succès (0).
        print(f"  ARBRE INSTABLE — VERDICT REFUSÉ : {len(bouges)} fichier(s) ont bougé pendant la")
        print("  recette. Le verdict porte sur un arbre qui n existe plus : il n est ni TENU ni")
        print("  NON TENU. Rejouer la recette sur un arbre STABLE (aucune autre session en")
        print("  écriture sur ce dépôt).")
        for ligne in bouges[:15]:
            print(f"             -> {ligne}")
        if len(bouges) > 15:
            print(f"             -> ... et {len(bouges) - 15} autre(s)")
        return 2
    if arbre_avant is None:
        print("  ARBRE : stabilité NON VÉRIFIÉE (git muet) — le verdict ci-dessous est rendu sans")
        print("  cette garantie, et cela se dit plutôt que de se taire (TF-0294).")
    if partielle:
        # Une recette partielle ne PRONONCE PAS S-01. Le dire serait le mensonge que le
        # selecteur rendrait facile : « vert » sur trois sections, silence sur les huit autres.
        non_jouees = [nom for nom in SECTIONS if nom not in choisies]
        print(
            f"  RECETTE PARTIELLE — S-01 NON PRONONCÉ ({len(non_jouees)} section(s) non "
            f"jouée(s) : {', '.join(non_jouees)})"
        )
    lignes, code = verdict_s01(succes, partielle, contexte["prealables"])
    for ligne in lignes:
        print(ligne)
    return code


if __name__ == "__main__":
    sys.exit(main())
