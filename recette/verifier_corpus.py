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

from forge_tests.__main__ import analyser  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
ROUGE = RACINE / "fixtures" / "banc-rouge"
VERT = RACINE / "fixtures" / "banc-vert"

# Chaque défaut du corpus, et le préfixe d identifiant qui prouve sa détection.
CORPUS = [
    ("D-01", "front", "parcours Front tronqué", ("route:", "element:")),
    ("H-02", "api", "codes d erreur jamais exercés", ("code:",)),
    ("H-03", "api", "méthodes HTTP jamais atteintes", ("endpoint:",)),
    ("H-04", "data", "contraintes jamais violées", ("contrainte:",)),
    ("H-05", "migrations", "migrations ni inversées ni rejouées", ("migration:",)),
    ("H-06", "batch", "branches de rejet et reprise non parcourues", ("branche:", "rejet:")),
    ("H-07", "fichiers", "chemins de parsing non exercés", ("chemin:",)),
    ("H-08", "back", "assertions permissives", ("mutant:", "seuil:back")),
    ("H-09", "securite", "execution dynamique non signalee", ("securite:",)),
    ("H-10", "accessibilite", "controles sans nom accessible", ("a11y:",)),
    ("H-11", "visuel", "regression visuelle de mise en page", ("visuel:",)),
    ("H-12", "migrations", "migration qui defait la precedente", ("divergence:migration:",)),
    ("H-13", "interface", "affordances inertes — bouton, lien et formulaire sans effet",
     ("interface:",)),
    # A-2 : le principe fondateur applique a l etage du MODULE. `app/recherche.py` du banc
    # rouge n est importe par aucun test : il doit sortir NOMME, jamais fondu dans un total.
    ("A-2", "back", "module source jamais importe par la suite", ("module-non-exerce:",)),
    # A-3 : un seuil n est opposable que s il attrape quelque chose. Le banc rouge porte des
    # modules metier dont la suite ne tue pas la moitie des mutants.
    ("A-3", "back", "seuil de mutation par module de logique metier viole",
     ("seuil:mutation-module:",)),
    # A-4 : le parcours navigateur d une instance SERVIE — 404 sur lien, trace d exception
    # rendue, marqueur de contenu absent, erreur console, affordance sans le moindre ecouteur.
    ("A-4", "qualif", "instance servie : route en defaut et affordance sans effet",
     ("qualif:",)),
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
        try:
            return analyser(banc)
        finally:
            os.environ.pop("FORGE_TESTS_QUALIF_URL", None)


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
    print("  TF-0135 — gardes d une route a routeurs : lues sur tous les modules, jamais main.py seul")

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
        findings, non_juge = _divergences_gardes(inv, table, gardes, source_main)

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

    Aux bancs, les douze pans sont couverts : le mécanisme n y est donc jamais exercé. Il l est
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
        ("les douze pans attendus sortent non couverts", len(entrees) == len(PANS_ATTENDUS)),
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

    Aucun banc ne peut l exercer : aux bancs, les douze pans sont couverts. Le cas est donc
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


def _findings(rapport: dict, prefixes: tuple[str, ...]) -> list[dict]:
    return [f for f in rapport["findings"] if f["id"].startswith(prefixes)]


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
                         "<link", "<script src", "fetch(", "XMLHttpRequest"):
            cas.append((f"aucune ressource distante — « {interdit} » absent",
                        interdit not in page))
        cas.append(("un repli systeme est declare pour chaque police",
                    "system-ui" in page and "Syne" not in page))
        cas.append(("les deux themes sont portes (clair et sombre)",
                    "prefers-color-scheme: dark" in page and 'data-theme="sombre"' in page))
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


def verifier_corpus_des_bancs(
    rouge: dict, vert: dict, alteres: list[str], empreintes_avant: dict
) -> int:
    """Le cœur historique : les 16 défauts plantés au banc rouge, le banc vert sans bloquant."""
    detectes = 0
    for code, pan, libelle, prefixes in CORPUS:
        trouves = _findings(rouge, prefixes)
        ok = bool(trouves)
        detectes += ok
        marque = "DETECTE" if ok else "MANQUE "
        print(f"  [{marque}] {code} ({pan:<10}) {libelle}")
        for f in trouves[:2]:
            print(f"             -> {f['id']}")
        if len(trouves) > 2:
            print(f"             -> ... et {len(trouves) - 2} autre(s) élément(s) nommé(s)")

    print("-" * 78)
    print(
        f"  banc ROUGE : {detectes}/{len(CORPUS)} défauts détectés · "
        f"{len(rouge['findings'])} findings nommés"
    )
    bloquants_vert = [f for f in vert["findings"] if f.get("severite") == "bloquant"]
    signales_vert = [f for f in vert["findings"] if f.get("severite") != "bloquant"]
    print(f"  banc VERT  : {len(bloquants_vert)} finding(s) bloquant(s) — attendu 0")
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
    return (len(CORPUS) - detectes) + len(bloquants_vert) + len(alteres)


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
        "titre": "16 défauts du banc rouge, banc vert sans bloquant, empreintes G-1",
    },
    "unitaire": {"bancs": (), "titre": "TF-0006 — suite unitaire du dépôt (pytest)"},
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


def _jouer(nom: str, rouge: dict | None, vert: dict | None, contexte: dict) -> int:
    if nom == "corpus":
        return verifier_corpus_des_bancs(
            rouge, vert, contexte["alteres"], contexte["empreintes_avant"]
        )
    if nom == "unitaire":
        return verifier_suite_unitaire()
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
    print("=" * 78)

    rouge = vert = None
    contexte: dict = {"alteres": [], "empreintes_avant": {}}
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

    echecs = {nom: _jouer(nom, rouge, vert, contexte) for nom in choisies}

    print("=" * 78)
    for nom, compte in echecs.items():
        print(f"  {'OK   ' if not compte else 'ECHEC'}  {nom:<14} {SECTIONS[nom]['titre']}")
    succes = not any(echecs.values())
    if partielle:
        # Une recette partielle ne PRONONCE PAS S-01. Le dire serait le mensonge que le
        # selecteur rendrait facile : « vert » sur trois sections, silence sur les huit autres.
        non_jouees = [nom for nom in SECTIONS if nom not in choisies]
        print(
            f"  RECETTE PARTIELLE — S-01 NON PRONONCÉ ({len(non_jouees)} section(s) non "
            f"jouée(s) : {', '.join(non_jouees)})"
        )
    else:
        print("  S-01 TENU" if succes else "  S-01 NON TENU")
    return 0 if succes else 1


if __name__ == "__main__":
    sys.exit(main())
