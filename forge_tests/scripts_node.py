"""Scripts Node d'un produit sans `package.json` — inventaire et suite `node:test` (TF-2387).

Le fait, remonté par le produit marketing (lot 20261109c, ledger seq 267) : sur un produit dont le
code est fait de scripts Node sans `package.json`, l'audit rendait PARTIEL sans inventorier
`scripts/*.mjs` ni jouer la suite `node:test`. `modules` vide, `essais.fourni` faux, aucune mention
de `scripts/` au rapport, et le non-jugé ne le disait pas : le verdict ne portait pas sur le code du
produit, et rien ne l'annonçait.

Décision du 10/11/2026 : l'audit inventorie `scripts/*.mjs` et joue `node --test` sur un produit
sans `package.json`, ou publie au non-jugé que ce code n'est pas couvert. Les deux voies sont
tenues : la suite est jouée quand elle existe, et quand elle n'existe pas le rapport le dit en
nommant les scripts non couverts.

Ce que le module fait :
  - applicable seulement si `scripts/` porte des `.mjs` et qu'il n'y a pas de `package.json` à la
    racine (avec lui, la suite JavaScript relève des pans `front` et `back` du produit) ;
  - joue `node --test` depuis la racine du produit, avec le rapporteur JUnit (les essais, test par
    test, rejoignent la section `essais` du rapport) et le rapporteur lcov (les scripts chargés par
    au moins un test sont « exercés », les autres sont nommés « jamais chargés par un test ») ;
  - un test rouge fait échouer le verdict, un test sauté le rend PARTIEL (TF-2254), un délai dépassé
    rend `DELAI_DEPASSE` (TF-2311, réglage `FORGE_TESTS_DELAI_SCRIPTS_S`).
"""

from __future__ import annotations

import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from forge_tests import execution
from forge_tests.junit import JunitIllisible, depuis_junit
from forge_tests.noyau import Essai

DOSSIER = "scripts"
DOMAINE = "scripts"
QUOI = "suite node:test des scripts"
#: Délai par défaut de la suite `node:test`, en secondes.
DELAI_DEFAUT = 900
ENV_DELAI = "FORGE_TESTS_DELAI_SCRIPTS_S"

#: Ce que `node --test` découvre par défaut (documentation de Node) : un fichier de test est
#: reconnu à son nom. L'inventaire des scripts les écarte, sinon une suite se compterait comme code.
_NOM_DE_TEST = re.compile(
    r"(\.test|[-_]test)\.(mjs|cjs|js)$|^test[-.].*\.(mjs|cjs|js)$|^test\.(mjs|cjs|js)$"
)

NON_JUGE = [
    "scripts : la suite `node:test` du produit est jouée EN PLACE, depuis sa racine (comme la "
    "suite backend) : un test qui écrit dans l'arbre le fait sous le nom du produit, la lecture "
    "seule (G-1) ne peut pas être garantie sur ce chemin",
    "scripts : seuls les scripts `.mjs` du dossier `scripts/` sont inventoriés ; un module "
    "`.cjs`, `.js` ou `.ts`, ou un script rangé ailleurs, n'entre pas dans l'inventaire",
    "scripts : « exercé » veut dire chargé par au moins une ligne de test (rapporteur lcov de "
    "`node --test --experimental-test-coverage`) ; une ligne atteinte n'implique pas qu'elle soit "
    "ASSERTÉE, et la mutation ne rejoue pas ces scripts",
]


def _scripts(cible: Path) -> list[Path]:
    racine = cible / DOSSIER
    if not racine.is_dir():
        return []
    return sorted(p for p in racine.rglob("*.mjs") if "node_modules" not in p.parts)


def inventaire(cible: Path) -> list[str]:
    """Les scripts du produit (hors fichiers de test), chemins relatifs à la racine, en `/`."""
    return [
        p.relative_to(cible).as_posix() for p in _scripts(cible) if not _NOM_DE_TEST.search(p.name)
    ]


def sans_objet(cible: Path) -> str | None:
    """La PREUVE que ce chemin ne s'applique pas, ou None s'il s'applique."""
    if (cible / "package.json").is_file():
        return (
            "`package.json` présent à la racine : la suite JavaScript de ce produit relève de ses "
            "pans front et back, pas de ce chemin"
        )
    if not _scripts(cible):
        return f"aucun `{DOSSIER}/*.mjs` sous la racine : ce produit n'a pas de scripts Node"
    return None


def _lire_lcov(texte: str, cible: Path) -> dict[str, int]:
    """{fichier relatif en `/` : lignes atteintes (LH)}. Un fichier absent n'a pas été chargé."""
    rendu: dict[str, int] = {}
    courant: str | None = None
    for ligne in texte.splitlines():
        if ligne.startswith("SF:"):
            brut = Path(ligne[3:].strip().replace("\\", "/"))
            try:  # relatif à la racine du produit (rapporteur lcov de node), ou absolu
                courant = (cible / brut).resolve().relative_to(cible.resolve()).as_posix()
            except ValueError:
                courant = brut.as_posix()
            rendu[courant] = 0
        elif ligne.startswith("LH:") and courant is not None:
            rendu[courant] = int(ligne[3:])
    return rendu


def _junit_par_fichier(xml_texte: str, cible: Path) -> str:
    """Remplace `classname="test"` (identique pour tout fichier) par le chemin relatif du fichier de
    test, pour que deux tests homonymes de deux fichiers gardent deux identifiants."""
    racine = ET.fromstring(xml_texte)  # noqa: S314 — produit par node à l'instant
    for cas in racine.iter("testcase"):
        fichier = cas.get("file") or ""
        try:
            cas.set("classname", Path(fichier).resolve().relative_to(cible.resolve()).as_posix())
        except (ValueError, OSError):
            cas.set("classname", Path(fichier).name or "test")
    return ET.tostring(racine, encoding="unicode")


@lru_cache(maxsize=16)
def _jouer(cible_str: str) -> dict:
    """Joue `node --test` une fois par projet et rend {statut, essais, lcov, code, queue}."""
    cible = Path(cible_str)
    execution._contrat_projet(cible)  # noqa: SLF001 — même contrat de projet que les autres suites
    execution._DELAIS_AUTRES.pop((str(cible), DOMAINE), None)  # noqa: SLF001
    execution._DEPASSEMENTS.pop((str(cible), QUOI), None)  # noqa: SLF001
    noeud = shutil.which("node")
    if noeud is None:
        return {"statut": "node_absent", "essais": [], "lcov": {}, "code": None, "queue": ""}
    delai, remede = execution._delai_regle(ENV_DELAI, DELAI_DEFAUT)  # noqa: SLF001
    with tempfile.TemporaryDirectory(prefix="forge-tests-node-") as temporaire:
        junit = Path(temporaire) / "junit.xml"
        lcov = Path(temporaire) / "lcov.info"
        resultat = execution._run(  # noqa: SLF001
            [
                noeud, "--test", "--experimental-test-coverage",
                "--test-reporter=junit", f"--test-reporter-destination={junit}",
                "--test-reporter=lcov", f"--test-reporter-destination={lcov}",
            ],
            banc=cible, domaine=DOMAINE, quoi=QUOI, remede=remede, cwd=cible, timeout=delai,
        )
        if resultat is None:
            depasse = execution._DEPASSEMENTS.get((str(cible), QUOI))  # noqa: SLF001
            if depasse is not None:
                execution._DELAIS_AUTRES[(str(cible), DOMAINE)] = depasse  # noqa: SLF001
                return {"statut": "delai_depasse", "essais": [], "lcov": {}, "code": None,
                        "queue": ""}
            return {"statut": "non_lancable", "essais": [], "lcov": {}, "code": None,
                    "queue": execution.motif_indisponibilite(
                        cible, DOMAINE, "lancement impossible")}
        queue = " | ".join(
            ligne.strip() for ligne in
            f"{resultat.stdout or ''}\n{resultat.stderr or ''}".splitlines() if ligne.strip()
        )[-300:]
        couverture = _lire_lcov(lcov.read_text(encoding="utf-8"), cible) if lcov.is_file() else {}
        essais: list[Essai] = []
        if junit.is_file():
            try:
                essais = depuis_junit(
                    _junit_par_fichier(junit.read_text(encoding="utf-8"), cible), "scripts"
                )
            except (JunitIllisible, ET.ParseError):
                essais = []
        if not essais:
            statut = "aucune_suite" if resultat.returncode == 0 else "non_lancable"
            return {"statut": statut, "essais": [], "lcov": couverture,
                    "code": resultat.returncode, "queue": queue}
        return {"statut": "joue", "essais": essais, "lcov": couverture,
                "code": resultat.returncode, "queue": queue}


def essais_de_la_cible(cible: Path | str) -> list[Essai] | None:
    """Les essais `node:test` joués, ou None si ce chemin ne s'applique pas ou n'a rien joué."""
    cible = Path(cible)
    if sans_objet(cible) is not None:
        return None
    mesure = _jouer(str(cible))
    return mesure["essais"] or None


def section(cible: Path | str) -> dict:
    """La section `scripts_node` du rapport : toujours présente, vide de mesure mais motivée quand
    elle ne s'applique pas. `echecs` nomme les tests rouges (ils font échouer le verdict)."""
    cible = Path(cible)
    motif = sans_objet(cible)
    if motif is not None:
        return {"applicable": False, "motif": motif, "inventaire": [], "exerces": [],
                "non_exerces": [], "echecs": [], "statut": "sans_objet", "non_juge": []}
    scripts = inventaire(cible)
    mesure = _jouer(str(cible))
    exerces = sorted(s for s in scripts if mesure["lcov"].get(s, 0) > 0)
    non_exerces = sorted(s for s in scripts if s not in exerces)
    echecs = sorted(
        {e.id: {"id": e.id, "message": (e.pourquoi or "")[:200]}
         for e in mesure["essais"] if e.verdict == "non_passant"}.values(),
        key=lambda e: e["id"],
    )
    statut = mesure["statut"]
    lignes = list(NON_JUGE)
    nom_scripts = f"{len(scripts)} script(s) Node sous `{DOSSIER}/`"
    if statut == "joue":
        essais = mesure["essais"]
        lignes.append(
            f"scripts : {nom_scripts} inventorié(s) ; `node --test` joué, {len(essais)} essai(s) "
            f"({sum(e.verdict == 'passant' for e in essais)} passant(s), "
            f"{sum(e.verdict == 'non_passant' for e in essais)} rouge(s), "
            f"{sum(e.verdict == 'non_execute' for e in essais)} non exécuté(s)) ; "
            f"{len(exerces)} script(s) exercé(s)"
            + (f", {len(non_exerces)} JAMAIS CHARGÉ(S) par un test : {', '.join(non_exerces)}"
               if non_exerces else "")
        )
    elif statut == "aucune_suite":
        lignes.append(
            f"scripts : {nom_scripts} inventorié(s) : {', '.join(scripts)} ; `node --test` n'a "
            "découvert AUCUNE suite — ce code n'est PAS couvert, et le verdict de cet audit ne "
            "porte pas sur lui"
        )
    elif statut == "delai_depasse":
        depasse = execution._DELAIS_AUTRES.get((str(cible), DOMAINE), {})  # noqa: SLF001
        delai = int(depasse.get("delai") or DELAI_DEFAUT)
        lignes.append(
            f"scripts : {nom_scripts} inventorié(s) ; DELAI_DEPASSE : `node --test` interrompu à "
            f"{float(depasse.get('duree') or 0):.0f} s (délai {delai} s) — régler {ENV_DELAI} "
            f"(secondes), par exemple {ENV_DELAI}={2 * delai}. Ce code n'est pas mesuré"
        )
    elif statut == "node_absent":
        lignes.append(
            f"scripts : {nom_scripts} inventorié(s) ; `node` introuvable sur ce poste — la suite "
            "n'a pas été jouée, ce code n'est PAS couvert"
        )
    else:
        lignes.append(
            f"scripts : {nom_scripts} inventorié(s) ; `node --test` non exécutable (code "
            f"{mesure['code']}) — ce code n'est PAS couvert. Fin de trace : {mesure['queue']}"
        )
    return {
        "applicable": True, "motif": "", "inventaire": scripts, "exerces": exerces,
        "non_exerces": non_exerces, "echecs": echecs, "statut": statut, "non_juge": lignes,
    }
