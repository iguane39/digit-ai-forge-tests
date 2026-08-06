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

import contextlib
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


def _empreintes(banc: Path) -> dict[str, str]:
    """SHA-256 de chaque source du banc — la seule preuve recevable de « lecture seule »."""
    import hashlib

    return {
        chemin.as_posix(): hashlib.sha256(chemin.read_bytes()).hexdigest()
        for chemin in sorted((banc / "backend" / "app").rglob("*.py"))
    }


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


def main() -> int:
    # G-1 : l empreinte des sources des bancs AVANT tout audit. La mutation les altere le temps
    # d un mutant ; si un seul octet survit a la restauration, la recette le dit ici.
    empreintes_avant = {banc: _empreintes(banc) for banc in (ROUGE, VERT)}

    rouge = analyser_servi(ROUGE)
    vert = analyser_servi(VERT)

    alteres = [
        f"{banc.name}/{chemin}"
        for banc, avant in empreintes_avant.items()
        for chemin, empreinte in avant.items()
        if _empreintes(banc).get(chemin) != empreinte
    ]

    print("=" * 78)
    print("RECETTE PHASE 1 — critère de sortie S-01")
    print("=" * 78)

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

    echecs_sql = verifier_lecture_sql()
    echecs_qualification = verifier_qualification()
    echecs_divergences = verifier_divergences()
    echecs_chemins = verifier_chemins_de_couverture()
    echecs_chemins += verifier_reprise_apres_enrichissement()
    echecs_g1 = verifier_lecture_seule() + len(alteres)

    succes = (
        detectes == len(CORPUS)
        and not bloquants_vert
        and not echecs_sql
        and not echecs_qualification
        and not echecs_divergences
        and not echecs_chemins
        and not echecs_g1
    )
    print("=" * 78)
    print("  S-01 TENU" if succes else "  S-01 NON TENU")
    return 0 if succes else 1


if __name__ == "__main__":
    sys.exit(main())
