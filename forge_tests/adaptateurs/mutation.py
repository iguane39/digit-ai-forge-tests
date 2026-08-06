"""Adaptateur Mutation (Python) — second contre-oracle : ce qu on atteint, le vérifie-t-on ?

Mutation réellement exécutée : on altère la source, on relance la suite, on compte les
survivants. Un mutant survivant est nommé avec sa ligne — jamais un total agrégé seul.

**A-1 (2026-08-06) — le périmètre cesse d être une liste blanche.** Jusqu ici l adaptateur
lisait `backend/app/*.py` : un `glob` NON récursif. Sur le premier produit réel, cela mutait
sept modules de socle et ignorait `services/` et `fournisseurs/` — la logique métier, c est-à-
dire tout ce que l utilisateur voit. Le rapport annonçait « mutation 37/37, score 1,0 » sur un
produit dont les deux tiers du code n avaient jamais été touchés. Le périmètre est désormais
l arborescence ENTIÈRE des sources, et toute exclusion est **nominative, motivée, publiée**.

**A-2 — aucun module silencieux.** L adaptateur publie `modules[]` : chaque module source du
projet avec son état — exercé (lignes/branches couvertes), muté (score), ou **jamais exercé et
nommé**. C est le principe fondateur de la forge appliqué à l étage du module : on nomme, on
n agrège pas.

**Budget.** Le coût d une mutation est une exécution de suite par mutant. La couverture de
PÉRIMÈTRE (quels modules) est totale par défaut ; c est la PROFONDEUR (combien de mutants par
module) qui est échantillonnée, par `FORGE_TESTS_MUTANTS_PAR_MODULE` (défaut 3). Le choix est
délibéré : mieux vaut une mesure grossière sur tout le code qu une mesure fine sur un huitième.
L échantillon est déterministe (indices régulièrement espacés, jamais les N premiers, qui
seraient tous en tête de fichier) et le taux retenu est DÉCLARÉ au rapport.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from forge_tests import seuils
from forge_tests.execution import resume_fichiers
from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "mutation-python", "back"
SEUIL = seuils.valeur("mutation_globale")
DOSSIER_SOURCE = Path("backend/app")
SUITE = "tests"

POUR_COUVRIR = (
    "fournir un environnement Python du projet (`backend/.venv` ou `.venv`) avec sa suite "
    "verte, et un dossier de sources sous `backend/app` — la mutation altère la source puis "
    "rejoue la suite, elle ne peut rien mesurer sans l une ni l autre"
)

# Dossiers qui ne sont pas du code du projet : les muter mesurerait la suite d un tiers.
_DOSSIERS_EXCLUS = {
    "__pycache__", ".venv", "venv", "site-packages", "node_modules", ".git", "migrations",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", "tests",
}

_MUTANTS_PAR_MODULE_DEFAUT = 3
_PLAFOND_DEFAUT = 400

NON_JUGE = [
    "mutation : les mutants équivalents ne sont pas détectés — un survivant peut être un mutant "
    "sémantiquement identique à l original",
    "mutation : opérateurs arithmétiques, de comparaison, booléens, d appartenance, bornes "
    "numériques et suppression d instruction ; ni permutation d arguments, ni littéraux non "
    "numériques",
    "mutation : la profondeur est ECHANTILLONNEE par module (voir `mutation.taux_echantillon` "
    "au rapport) — un score de module porte sur les mutants JOUES, pas sur tous les mutants "
    "possibles ; le perimetre, lui, est total et ses exclusions sont nommees",
    "modules : un module est dit « exerce » des qu une ligne en est couverte — l etre ne dit "
    "pas qu il soit VERIFIE, c est le role du score de mutation qui l accompagne",
]

_SUBSTITUTIONS = (("+", "-"), ("-", "+"), ("*", "/"), ("/", "*"))
_COMPARAISONS = (
    (" < ", " <= "),
    (" > ", " >= "),
    (" == ", " != "),
    (" != ", " == "),
    (" <= ", " < "),
    (" >= ", " > "),
    (" and ", " or "),
    (" or ", " and "),
    (" in ", " not in "),
    (" is not ", " is "),
)
# Litteraux numeriques : decaler une borne revele les tests qui ne verifient que le sens.
_BORNES = ((" 0", " 1"), (" 1", " 0"), (" 100", " 99"))


@dataclass(frozen=True)
class Mutant:
    fichier: str  # chemin RELATIF au dossier `backend`, en posix — unique dans le projet
    ligne: int
    colonne: int
    avant: str
    apres: str

    @property
    def id(self) -> str:
        return f"mutant:{self.fichier}:{self.ligne + 1}:{self.avant.strip()}->{self.apres.strip()}"


# --- Découverte du périmètre ------------------------------------------------------------------
def _sans_code_executable(source: Path) -> bool:
    """Le module ne contient-il QUE des imports, des constantes de ré-export et sa docstring ?

    Un `__init__.py` de paquet est le cas type : le muter produit des mutants équivalents par
    construction (on ne peut pas « casser » un ré-export) qui feraient chuter le score sans
    désigner la moindre faiblesse de la suite. L exclusion est décidée sur le CONTENU, pas sur
    le nom : un `__init__.py` porteur de logique reste dans le périmètre.
    """
    try:
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for noeud in arbre.body:
        if isinstance(noeud, (ast.Import, ast.ImportFrom, ast.Pass)):
            continue
        if isinstance(noeud, ast.Expr) and isinstance(noeud.value, ast.Constant):
            continue  # docstring ou littéral isolé
        if isinstance(noeud, (ast.Assign, ast.AnnAssign)):
            valeur = noeud.value
            if valeur is None or isinstance(valeur, (ast.Constant, ast.Tuple, ast.List, ast.Set)):
                continue  # `__all__ = (...)`, `VERSION = "1.2"`
        return False
    return True


def _exclusions_declarees() -> list[str]:
    brut = os.environ.get("FORGE_TESTS_MUTATION_EXCLUT", "")
    return [motif.strip() for motif in brut.split(",") if motif.strip()]


def decouvrir(racine: Path, dossier: Path) -> tuple[list[Path], list[dict]]:
    """Tous les modules Python des sources, et la liste NOMMÉE des exclus avec leur motif.

    `racine` est le dossier `backend` (base des chemins relatifs), `dossier` la racine des
    sources. La découverte est récursive : `services/`, `fournisseurs/`, adaptateurs compris.
    """
    motifs = _exclusions_declarees()
    retenus: list[Path] = []
    exclus: list[dict] = []
    for source in sorted(dossier.rglob("*.py")):
        relatif = source.relative_to(racine).as_posix()
        if any(partie in _DOSSIERS_EXCLUS for partie in source.relative_to(dossier).parts[:-1]):
            exclus.append({"module": relatif, "motif": "dossier hors sources du projet"})
            continue
        vise = next((m for m in motifs if fnmatch.fnmatch(relatif, m)), None)
        if vise is not None:
            exclus.append(
                {
                    "module": relatif,
                    "motif": f"exclusion demandée par FORGE_TESTS_MUTATION_EXCLUT={vise!r}",
                }
            )
            continue
        if _sans_code_executable(source):
            exclus.append(
                {
                    "module": relatif,
                    "motif": (
                        "aucune instruction exécutable hors imports, docstring et constantes de "
                        "ré-export — tout mutant y serait équivalent par construction"
                    ),
                }
            )
            continue
        retenus.append(source)
    return retenus, exclus


def _lignes_calculantes(lignes: list[str]) -> list[int]:
    """Lignes portant du code EXÉCUTABLE, hors docstrings.

    Muter l intérieur d une docstring produit un mutant équivalent par construction, qui
    survit toujours et fait chuter le score sans rien signaler de vrai.
    """
    retenues: list[int] = []
    dans_docstring = False
    for i, ligne in enumerate(lignes):
        nu = ligne.strip()
        marqueurs = nu.count('"""') + nu.count("'''")
        if dans_docstring:
            if marqueurs:
                dans_docstring = False
            continue
        if marqueurs == 1:
            dans_docstring = True
            continue
        if marqueurs >= 2 or not nu or nu.startswith(("#", "from ", "import ", "@")):
            continue
        retenues.append(i)
    return retenues


def _zones_litterales(texte: str) -> dict[int, list[tuple[int, int]]]:
    """Plages de colonnes occupées par des chaînes et des commentaires, par ligne (0-indexée).

    Muter à l intérieur d une chaîne ne mute pas du CODE. Pire : quand la même constante sert
    au code et au test (« REJ-VIDE », « utf-8 »), le mutant est équivalent par construction et
    survit toujours — il fait chuter le score sans jamais désigner une faiblesse de la suite.
    """
    import io
    import tokenize

    zones: dict[int, list[tuple[int, int]]] = {}
    try:
        jetons = list(tokenize.generate_tokens(io.StringIO(texte).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return zones
    for jeton in jetons:
        if jeton.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (ligne_debut, col_debut), (ligne_fin, col_fin) = jeton.start, jeton.end
        for ligne in range(ligne_debut, ligne_fin + 1):
            debut = col_debut if ligne == ligne_debut else 0
            fin = col_fin if ligne == ligne_fin else 10**6
            zones.setdefault(ligne - 1, []).append((debut, fin))
    return zones


def generer_mutants(source: Path, nom_court: str) -> list[Mutant]:
    texte = source.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    zones = _zones_litterales(texte)

    def dans_litteral(ligne: int, colonne: int) -> bool:
        return any(debut <= colonne < fin for debut, fin in zones.get(ligne, ()))

    mutants: list[Mutant] = []
    for i in _lignes_calculantes(lignes):
        ligne = lignes[i]
        for avant, apres in (*_COMPARAISONS, *_BORNES):
            position = ligne.find(avant)
            if position >= 0 and not dans_litteral(i, position + 1):
                mutants.append(Mutant(nom_court, i, position, avant, apres))
        for j, caractere in enumerate(ligne):
            if dans_litteral(i, j):
                continue
            for avant, apres in _SUBSTITUTIONS:
                if caractere == avant:
                    mutants.append(Mutant(nom_court, i, j, avant, apres))
        # Suppression d instruction : neutraliser un appel dont le retour n est pas utilise.
        # Un test qui ne verifie que l absence d exception ne le remarque jamais.
        nu = ligne.strip()
        if nu.endswith(")") and "=" not in nu and not nu.startswith(("return", "raise", "assert")):
            indentation = len(ligne) - len(ligne.lstrip())
            mutants.append(Mutant(nom_court, i, indentation, nu[:1], "pass  # "))
    return mutants


def echantillonner(mutants: list[Mutant], combien: int) -> list[Mutant]:
    """`combien` mutants répartis sur TOUT le module, jamais les `combien` premiers.

    Prendre la tête de liste concentrerait l échantillon sur les premières lignes du fichier —
    imports, constantes, première fonction — et laisserait systématiquement le corps du module
    non mesuré. L espacement régulier est déterministe : deux audits du même code jouent les
    mêmes mutants, et un écart de score se lit comme un écart de suite, pas de tirage.
    """
    if combien <= 0 or len(mutants) <= combien:
        return list(mutants)
    pas = len(mutants) / combien
    return [mutants[int(i * pas)] for i in range(combien)]


def _purger_bytecode(racine: Path) -> None:
    """Un mutant a la MÊME TAILLE que l original ; si la restauration tombe dans la même
    seconde, Python réutilise un .pyc périmé et la suite juge un code qui n existe plus."""
    for cache in racine.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _suite_verte(racine: Path, python: Path) -> bool:
    _purger_bytecode(racine)
    resultat = subprocess.run(
        [
            str(python), "-m", "pytest", SUITE, "-q", "--no-header",
            "-p", "no:cacheprovider", "-p", "no:warnings", "-x",
        ],
        cwd=racine,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return resultat.returncode == 0


def _entier_env(nom: str, defaut: int) -> int:
    brut = (os.environ.get(nom) or "").strip()
    if not brut.lstrip("-").isdigit():
        return defaut
    return int(brut)


def _inventaire_modules(
    racine: Path,
    retenus: list[Path],
    exclus: list[dict],
    couverture: dict[str, dict] | None,
    scores: dict[str, dict],
) -> list[dict]:
    """A-2 — chaque module source avec son état : exercé, muté, ou jamais exercé et NOMMÉ."""
    inventaire: list[dict] = []
    for source in retenus:
        relatif = source.relative_to(racine).as_posix()
        mesure = (couverture or {}).get(relatif)
        entree: dict = {
            "module": relatif,
            "categorie": "metier" if seuils.est_metier(source.stem) else "socle",
            "exclu": None,
        }
        if couverture is None:
            entree["exerce"] = None
            entree["motif_non_mesure"] = "couverture non mesurable (suite non exécutée)"
        elif mesure is None:
            # Le module n apparaît même pas au relevé de coverage : il n a jamais été importé.
            entree.update(
                exerce=False, lignes_couvertes=0, lignes_total=None,
                branches_couvertes=0, branches_total=None,
                ratio_lignes=0.0, ratio_branches=0.0,
            )
        else:
            lignes_total = mesure["lignes_total"] or 0
            branches_total = mesure["branches_total"] or 0
            entree.update(
                exerce=mesure["lignes_couvertes"] > 0,
                lignes_couvertes=mesure["lignes_couvertes"],
                lignes_total=lignes_total,
                branches_couvertes=mesure["branches_couvertes"],
                branches_total=branches_total,
                ratio_lignes=(
                    round(mesure["lignes_couvertes"] / lignes_total, 4) if lignes_total else 0.0
                ),
                ratio_branches=(
                    round(mesure["branches_couvertes"] / branches_total, 4)
                    if branches_total
                    else None
                ),
            )
        entree.update(scores.get(relatif) or {"mute": False, "motif_non_mute": "non joué"})
        inventaire.append(entree)
    for entree in exclus:
        inventaire.append(
            {
                "module": entree["module"],
                "categorie": "exclu",
                "exclu": entree["motif"],
                "exerce": None,
                "mute": False,
            }
        )
    return sorted(inventaire, key=lambda e: e["module"])


def _findings_modules(dossier: Path, inventaire: list[dict]) -> list[Finding]:
    """Un module jamais exercé est NOMMÉ ; un module sous seuil est NOMMÉ avec son seuil."""
    findings: list[Finding] = []
    seuil_metier = seuils.valeur("mutation_module_metier")
    seuil_branches = seuils.valeur("branches_module_exerce")
    for entree in inventaire:
        if entree["categorie"] == "exclu":
            continue
        chemin = str(dossier.parent / entree["module"])
        identifiant = f"module-non-exerce:{entree['module']}"
        if entree.get("exerce") is False:
            findings.append(
                Finding(
                    id=identifiant,
                    classe="module-non-exerce",
                    localisation=chemin,
                    message=(
                        f"{entree['module']} : module source jamais importé par la suite — "
                        "aucune ligne couverte, aucun mutant ne peut y être jugé"
                    ),
                    risque=coter(PAN, identifiant, chemin),
                )
            )
            continue
        score = entree.get("score_mutation")
        if (
            entree["categorie"] == "metier"
            and score is not None
            and score < seuil_metier
        ):
            identifiant = f"seuil:mutation-module:{entree['module']}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe="seuil-non-tenu",
                    localisation=chemin,
                    message=(
                        f"{entree['module']} : score de mutation {score:.0%} sous le seuil "
                        f"par module de logique métier {seuil_metier:.0%} "
                        f"({entree.get('tues')}/{entree.get('mutants_viables')} mutants tués)"
                    ),
                    severite=seuils.severite("mutation_module_metier"),
                    risque=coter(PAN, identifiant, chemin),
                )
            )
        ratio = entree.get("ratio_branches")
        if entree.get("exerce") and ratio is not None and ratio < seuil_branches:
            identifiant = f"seuil:branches:{entree['module']}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe="seuil-non-tenu",
                    localisation=chemin,
                    message=(
                        f"{entree['module']} : couverture de branches {ratio:.0%} sous le seuil "
                        f"par module exercé {seuil_branches:.0%} "
                        f"({entree.get('branches_couvertes')}/{entree.get('branches_total')})"
                    ),
                    severite=seuils.severite("branches_module_exerce"),
                    risque=coter(PAN, identifiant, chemin),
                )
            )
    return findings


def analyser(cible: Path) -> SortieAdaptateur:
    racine = cible / "backend"
    dossier = cible / DOSSIER_SOURCE
    python = racine / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = racine / ".venv" / "bin" / "python"
    if not dossier.is_dir():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, f"mutation : aucun dossier de sources sous {dossier}"],
        )

    retenus, exclus = decouvrir(racine, dossier)
    par_module = _entier_env("FORGE_TESTS_MUTANTS_PAR_MODULE", _MUTANTS_PAR_MODULE_DEFAUT)
    plafond = _entier_env("FORGE_TESTS_MUTATION_PLAFOND", _PLAFOND_DEFAUT)
    non_juge = list(NON_JUGE)
    if exclus:
        non_juge.append(
            "mutation : "
            + str(len(exclus))
            + " module(s) EXCLUS du périmètre, chacun nommé avec son motif dans `modules[]` : "
            + ", ".join(e["module"] for e in exclus)
        )

    # La couverture se lit AVANT toute mutation : la suite doit être mesurée sur le code
    # d origine, jamais sur un arbre en cours d altération.
    couverture = resume_fichiers(cible)

    if not python.exists():
        inventaire = _inventaire_modules(racine, retenus, exclus, couverture, {})
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            findings=_findings_modules(dossier, inventaire),
            non_juge=[
                *non_juge,
                f"mutation : aucun environnement Python du projet ({racine / '.venv'}) — "
                f"{len(retenus)} module(s) inventorié(s), aucun muté",
            ],
            modules=inventaire,
        )

    originaux = {f: f.read_text(encoding="utf-8") for f in retenus}
    plan: list[tuple[Path, Mutant]] = []
    par_fichier: dict[Path, list[Mutant]] = {}
    for fichier in retenus:
        relatif = fichier.relative_to(racine).as_posix()
        tires = echantillonner(generer_mutants(fichier, relatif), par_module)
        par_fichier[fichier] = tires
        plan.extend((fichier, m) for m in tires)
    if len(plan) > plafond:
        non_juge.append(
            f"mutation : plafond global de {plafond} mutants atteint — "
            f"{len(plan) - plafond} mutants non joués, score calculé sur le sous-ensemble DÉCLARÉ"
        )
        plan = plan[:plafond]

    joues: dict[Path, list[Mutant]] = {}
    for fichier, mutant in plan:
        joues.setdefault(fichier, []).append(mutant)

    survivants: list[Mutant] = []
    viables_par_fichier: dict[Path, int] = {}
    survivants_par_fichier: dict[Path, list[Mutant]] = {}
    viables = 0
    interrompu: str | None = None
    try:
        if not _suite_verte(racine, python):
            inventaire = _inventaire_modules(racine, retenus, exclus, couverture, {})
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                findings=_findings_modules(dossier, inventaire),
                non_juge=[*non_juge, "suite rouge avant mutation : score non calculable"],
                modules=inventaire,
            )
        for fichier, mutant in plan:
            original = originaux[fichier]
            lignes = original.splitlines()
            ligne = lignes[mutant.ligne]
            lignes[mutant.ligne] = (
                ligne[: mutant.colonne] + mutant.apres + ligne[mutant.colonne + len(mutant.avant) :]
            )
            mute = "\n".join(lignes) + "\n"
            try:
                compile(mute, str(fichier), "exec")
            except SyntaxError:
                continue  # mutant non viable : hors du dénominateur
            viables += 1
            viables_par_fichier[fichier] = viables_par_fichier.get(fichier, 0) + 1
            fichier.write_text(mute, encoding="utf-8")
            if _suite_verte(racine, python):
                survivants.append(mutant)
                survivants_par_fichier.setdefault(fichier, []).append(mutant)
            fichier.write_text(original, encoding="utf-8")
    except subprocess.TimeoutExpired:
        # Un délai dépassé ne doit jamais emporter l audit entier : le pan se DÉCLARE non
        # mesuré (le `finally` restaure les sources avant toute chose).
        interrompu = (
            "mutation : délai dépassé pendant le jeu des mutants — score partiel sur les "
            f"{viables} mutant(s) déjà joués, les autres pans restent mesurés"
        )
    finally:
        for fichier, contenu in originaux.items():
            fichier.write_text(contenu, encoding="utf-8")
        _purger_bytecode(racine)
    if interrompu:
        non_juge.append(interrompu)

    scores: dict[str, dict] = {}
    for fichier in retenus:
        relatif = fichier.relative_to(racine).as_posix()
        viables_f = viables_par_fichier.get(fichier, 0)
        if not viables_f:
            possible = len(par_fichier.get(fichier, []))
            scores[relatif] = {
                "mute": False,
                "motif_non_mute": (
                    "aucun mutant viable — le module ne porte aucune expression mutable"
                    if not possible
                    else "mutants non joués (plafond global ou délai dépassé)"
                ),
            }
            continue
        tues_f = viables_f - len(survivants_par_fichier.get(fichier, []))
        scores[relatif] = {
            "mute": True,
            "mutants_viables": viables_f,
            "tues": tues_f,
            "score_mutation": round(tues_f / viables_f, 4),
            "survivants": [m.id for m in survivants_par_fichier.get(fichier, [])],
        }

    inventaire = _inventaire_modules(racine, retenus, exclus, couverture, scores)
    tues = viables - len(survivants)
    score = tues / viables if viables else 0.0
    findings = [
        Finding(
            id=m.id,
            classe="mutant-survivant",
            localisation=f"{racine / m.fichier}:{m.ligne + 1}",
            message=f"mutant {m.avant.strip()} -> {m.apres.strip()} non tué : la suite reste verte",
            severite="signale",
            risque=coter(PAN, m.id, str(racine / m.fichier)),
        )
        for m in survivants
    ]
    findings.extend(_findings_modules(dossier, inventaire))
    if viables and score < SEUIL:
        findings.append(
            Finding(
                id=f"seuil:{PAN}",
                classe="seuil-non-tenu",
                localisation=str(cible),
                message=f"score de mutation {score:.0%} sous le seuil {SEUIL:.0%}",
                severite=seuils.severite("mutation_globale"),
                risque=coter(PAN, f"seuil:{PAN}", str(dossier)),
            )
        )
    findings.sort(key=lambda f: f.risque or 0, reverse=True)
    mutes = [e for e in inventaire if e.get("mute")]
    bloquants = [f for f in findings if f.severite == "bloquant"]
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if bloquants else "PASS",
        findings=findings,
        non_juge=non_juge,
        mutation={
            "mutants_viables": viables,
            "tues": tues,
            "score": round(score, 4),
            "seuil": SEUIL,
            "modules_inventories": len(retenus),
            "modules_mutes": len(mutes),
            "modules_exclus": exclus,
            "taux_echantillon": {
                "mutants_par_module": par_module,
                "plafond_global": plafond,
                "variable": "FORGE_TESTS_MUTANTS_PAR_MODULE",
            },
            "modules": [e["module"] for e in mutes],
            "score_par_module": {
                e["module"]: e["score_mutation"] for e in mutes if "score_mutation" in e
            },
            "survivants": [m.id for m in survivants],
        },
        modules=inventaire,
    )
