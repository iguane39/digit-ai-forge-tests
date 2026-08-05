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

import os
import sys
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
    rouge = analyser(ROUGE)
    vert = analyser(VERT)

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
    print(f"  banc ROUGE : {detectes}/{len(CORPUS)} défauts détectés · {len(rouge['findings'])} findings nommés")
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

    echecs_sql = verifier_lecture_sql()
    echecs_qualification = verifier_qualification()

    succes = (
        detectes == len(CORPUS)
        and not bloquants_vert
        and not echecs_sql
        and not echecs_qualification
    )
    print("=" * 78)
    print("  S-01 TENU" if succes else "  S-01 NON TENU")
    return 0 if succes else 1


if __name__ == "__main__":
    sys.exit(main())
