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

from forge_tests import classes, seuils
from forge_tests.disposition import motif_indetermine, paquet_sources, racine_execution
from forge_tests.execution import PREALABLE_ABSENT, motif_indisponibilite, resume_fichiers
from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "mutation-python", "back"
SEUIL = seuils.valeur("mutation_globale")
DOSSIER_SOURCE = Path("backend/app")  # conservé pour mémoire : la racine est DÉCOUVERTE
SUITE = "tests"

POUR_COUVRIR = (
    "fournir un environnement Python du projet (`backend/.venv` ou `.venv`) avec sa suite "
    "verte, et un paquet de sources sous `backend/` — la mutation altère la source puis "
    "rejoue la suite, elle ne peut rien mesurer sans l'une ni l'autre"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T6", "famille": "technique", "titre": "Robustesse de la suite",
     "decoupe": "module", "axe_cas": "unitaire"},
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

    **Les f-strings en font partie, et ne le faisaient pas.** Depuis Python 3.12, le texte d une
    f-string n est plus un jeton `STRING` mais une suite de `FSTRING_MIDDLE` : ce filtre, écrit
    sous 3.11, ne le reconnaissait plus. Chaque `f"colonnes attendues plat/quantite"` offrait
    donc un mutant `/` -> `*` qui ne change QUE le libellé d un message — équivalent par
    construction, survivant garanti. Constaté le 2026-08-06 : c est ce qui donnait 0,00 aux
    modules `fournisseurs/` d ASD Mail Manager, dont le code est surtout fait de messages, et
    ce qui rendait leur score illisible au lieu d accuser la suite à juste titre.
    """
    import io
    import tokenize

    # `getattr` : les trois jetons n existent pas sous Python 3.11, où le filtre d origine
    # suffisait. Le code doit rester juste sur les deux versions, pas sur la plus récente.
    interdits = {tokenize.STRING, tokenize.COMMENT}
    for nom in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        jeton = getattr(tokenize, nom, None)
        if jeton is not None:
            interdits.add(jeton)

    zones: dict[int, list[tuple[int, int]]] = {}
    try:
        jetons = list(tokenize.generate_tokens(io.StringIO(texte).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return zones
    for jeton in jetons:
        if jeton.type not in interdits:
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


def appliquer(original: str, mutant: Mutant) -> str:
    """Source du module une fois le mutant posé."""
    lignes = original.splitlines()
    ligne = lignes[mutant.ligne]
    lignes[mutant.ligne] = (
        ligne[: mutant.colonne] + mutant.apres + ligne[mutant.colonne + len(mutant.avant) :]
    )
    return "\n".join(lignes) + "\n"


def poser(fichier: Path, texte: str) -> None:
    """Écrit un mutant SANS traduction de fins de ligne.

    `Path.write_text` passe par `open(mode="w")`, qui traduit `\\n` en `os.linesep` : sur
    Windows un module en LF ressortait en CRLF. Pour un mutant c est sans conséquence — il ne
    vit qu une exécution de suite — mais l idiome est le même que celui de la restauration, et
    c est là qu il faisait des dégâts. Un seul point d écriture, en octets, pour les deux.
    """
    fichier.write_bytes(texte.encode("utf-8"))


def restaurer(octets: dict[Path, bytes]) -> list[Path]:
    """Remet chaque fichier dans son état EXACT. Renvoie ceux qu il a fallu réécrire.

    Garde-fou G-1. Le 2026-08-06, un audit d ASD Mail Manager a laissé 23 fichiers source du
    produit modifiés : la mutation était bien défaite, mais la restauration passait par
    `write_text` et retournait les fins de ligne LF en CRLF. Une lecture seule qui réécrit les
    fins de ligne n est pas une lecture seule. L écart était resté invisible tant que le
    périmètre tenait dans huit modules déjà convertis par un audit antérieur — c est
    l élargissement du périmètre (A-1) qui l a révélé.
    """
    reecrits: list[Path] = []
    for fichier, contenu in octets.items():
        try:
            if fichier.read_bytes() == contenu:
                continue
        except OSError:
            pass
        fichier.write_bytes(contenu)
        reecrits.append(fichier)
    return reecrits


def compilables(original: str, mutants: list[Mutant], nom: str) -> list[Mutant]:
    """Mutants qui COMPILENT — les seuls dont la survie veuille dire quelque chose.

    Filtrer AVANT d échantillonner, et non après, est ce qui garantit à chaque module son
    score. La première version tirait trois mutants au hasard régulier puis jetait ceux qui ne
    compilaient pas : sur le premier produit réel, huit modules — dont `auth.py`, `rbac.py` et
    `services/courrier.py` — voyaient leurs trois mutants tomber tous les trois, et sortaient
    SANS SCORE, avec un motif faux (« plafond ou délai ») alors que le plafond n avait pas
    mordu. Un module de logique métier sans score est exactement le silence que A-1 solde.

    Le coût est nul à l échelle de la mesure : compiler un module prend quelques millisecondes,
    là où jouer un mutant coûte une exécution complète de la suite.
    """
    retenus: list[Mutant] = []
    for mutant in mutants:
        try:
            compile(appliquer(original, mutant), nom, "exec")
        except (SyntaxError, ValueError):
            continue
        retenus.append(mutant)
    return retenus


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


class InterpreteurInutilisable(RuntimeError):
    """Le python désigné existe mais ne s exécute pas — venv d un autre système, lien mort,
    fichier tronqué. TF-0216 : sans cette classe, l `OSError` remontait jusqu au noyau, qui
    sortait en exit 2 et perdait le rapport ENTIER. Un interpréteur injouable rend un pan non
    mesurable, il ne fait pas perdre les onze autres."""


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


def _suite_verte_ou_injouable(racine: Path, python: Path) -> bool:
    """`_suite_verte`, mais un interpréteur qui refuse de démarrer se DÉCLARE au lieu de lever."""
    try:
        return _suite_verte(racine, python)
    except OSError as erreur:  # WinError 193, ENOEXEC, permission refusée…
        raise InterpreteurInutilisable(
            f"l interpréteur « {python} » existe mais ne s exécute pas sur ce système "
            f"({type(erreur).__name__}: {erreur}) — venv construit ailleurs, lien mort ou "
            "binaire tronqué. Recréer l environnement virtuel du projet, puis rejouer"
        ) from erreur


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
                    classe=classes.MODULE_NON_EXERCE,
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
                    classe=classes.SEUIL_NON_TENU,
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
                    classe=classes.SEUIL_NON_TENU,
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
    # TF-0216 (RT-2, lot COMPTA) : la racine d exécution est DÉCOUVERTE, plus ancrée en dur sur
    # `backend\`. Laisser l ancre ici pendant que `paquet_sources` suit la racine découverte
    # faisait diverger les deux sur un projet à racine plate : `source.relative_to(racine)`
    # levait, le noyau rattrapait tout en exit 2, et le rapport ENTIER était perdu — strictement
    # pire que le SKIP d avant. Un correctif qui aggrave le cas qu il vise n en est pas un.
    racine = racine_execution(cible)
    dossier = paquet_sources(cible)
    python = racine / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = racine / ".venv" / "bin" / "python"
    # TF-0402 (RF-4, lot SCC-FR) — « écosystème non couvert » et « configuration manquante » ne
    # sont pas le même verdict, et les confondre coûte double : une configuration réclamée pour
    # un pan structurellement inatteignable use la crédibilité des actions (TF-0381), et un
    # SEUIL BLOQUANT sans porteur est, au dashboard, indiscernable d'un seuil tenu — la pire des
    # deux formes de silence. Un back Node (package.json sans paquet Python) n'est pas un back
    # mal configuré : cet adaptateur ne sait PAS le muter, et la justification du seuil cite
    # Stryker (l'outil JS) qui n'est câblé nulle part.
    if (dossier is None or not dossier.is_dir()) and (racine / "package.json").is_file():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "mutation : ÉCOSYSTÈME NON COUVERT — le back de ce projet est Node "
                f"(`{(racine / 'package.json').as_posix()}`, aucun paquet Python), et cet "
                "adaptateur ne mute que du Python. Ce n'est PAS une configuration manquante : "
                "aucune variable ne rendra ce pan mesurable ici. Le seuil BLOQUANT "
                f"`mutation_globale` ({SEUIL:.2f}) n'a donc AUCUN PORTEUR sur ce projet — sa "
                "justification cite Stryker, l'outil JS, câblé nulle part (RF-4) : un pan "
                "mutation JS est le remède, pas une configuration",
            ],
        )
    if dossier is None or not dossier.is_dir():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"mutation : sources du projet non localisables — {motif_indetermine(cible)}",
            ],
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

    # G-1, deux representations DISTINCTES du même fichier, et c est volontaire :
    #   - `originaux` en TEXTE (fins de ligne normalisees par `read_text`) sert au calcul des
    #     mutants, exactement comme `generer_mutants` qui lit de la meme facon — les colonnes
    #     restent alignees ;
    #   - `octets` est le contenu EXACT du fichier, seul admis pour la restauration.
    # Restaurer depuis le texte reecrivait `\n` en `\r\n` sur Windows : le 2026-08-06, un audit
    # d ASD Mail Manager a ainsi modifie 23 fichiers source du produit — mutation restauree,
    # fins de ligne retournees. Une lecture seule qui reecrit les fins de ligne n est pas une
    # lecture seule ; l ecart ne se voyait pas tant que le perimetre tenait dans huit modules
    # deja convertis par un audit precedent.
    originaux = {f: f.read_text(encoding="utf-8") for f in retenus}
    octets = {f: f.read_bytes() for f in retenus}
    plan: list[tuple[Path, Mutant]] = []
    par_fichier: dict[Path, list[Mutant]] = {}
    candidats_par_fichier: dict[Path, int] = {}
    for fichier in retenus:
        relatif = fichier.relative_to(racine).as_posix()
        # Viabilite d abord, echantillon ensuite : l inverse laissait des modules entiers sans
        # score quand leurs trois tires ne compilaient pas (voir `viables`).
        candidats = compilables(
            originaux[fichier], generer_mutants(fichier, relatif), str(fichier)
        )
        candidats_par_fichier[fichier] = len(candidats)
        tires = echantillonner(candidats, par_module)
        par_fichier[fichier] = tires
        plan.extend((fichier, m) for m in tires)
    if len(plan) > plafond:
        non_juge.append(
            f"mutation : plafond global de {plafond} mutants atteint — "
            f"{len(plan) - plafond} mutants non joués, score calculé sur le sous-ensemble DÉCLARÉ"
        )
        plan = plan[:plafond]

    survivants: list[Mutant] = []
    viables_par_fichier: dict[Path, int] = {}
    survivants_par_fichier: dict[Path, list[Mutant]] = {}
    viables = 0
    interrompu: str | None = None
    # TF-0096 : la mutation était LE process silencieux d origine (~45 min sans un signal,
    # run Approval2 du 11/08). Unité = module ; sous-découpe = mutant k/n dans le module —
    # une unité qui occupe plus d une fenêtre montre son avancement INTERNE.
    from forge_tests.avancement import Avancement

    ordre_fichiers = list(dict.fromkeys(f for f, _ in plan))
    dossier_run = str(cible / "forge") if (cible / "forge").is_dir() else None
    av = Avancement(
        dossier_run, unite="module",
        raf=[f.relative_to(racine).as_posix() for f in ordre_fichiers],
        libelle=f"mutation de {cible.name} ({len(plan)} mutants)",
    )
    try:
        try:
            verte = _suite_verte_ou_injouable(racine, python)
        except InterpreteurInutilisable as injouable:
            # TF-0216 : ce pan devient non mesurable, les onze autres restent mesurés.
            inventaire = _inventaire_modules(racine, retenus, exclus, couverture, {})
            av.final()
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                findings=_findings_modules(dossier, inventaire),
                non_juge=[*non_juge, f"back : interpréteur injouable — {injouable}"],
                modules=inventaire,
            )
        if not verte:
            inventaire = _inventaire_modules(racine, retenus, exclus, couverture, {})
            av.final()
            # TF-0299 — « suite rouge avant mutation » est FAUX quand la suite n a pas pu
            # démarrer : le démon de conteneurs injoignable la fait échouer avant le premier
            # test, et ce pan accusait alors la suite d un projet sain. Le motif déjà DÉCLARÉ par
            # l exécution (elle a lancé la même suite quelques lignes plus haut, `resume_fichiers`)
            # porte le préalable manquant : le reprendre ici évite deux diagnostics du même fait.
            prealable = motif_indisponibilite(cible, "backend", "")
            return SortieAdaptateur(
                NOM, PAN, str(cible), "SKIP",
                findings=_findings_modules(dossier, inventaire),
                non_juge=[
                    *non_juge,
                    f"back : {prealable}"
                    if PREALABLE_ABSENT in prealable
                    else "suite rouge avant mutation : score non calculable",
                ],
                modules=inventaire,
            )
        fichier_courant: Path | None = None
        joues_module = 0
        for fichier, mutant in plan:
            if fichier != fichier_courant:
                if fichier_courant is not None:
                    av.unite_finie(fichier_courant.relative_to(racine).as_posix())
                fichier_courant = fichier
                joues_module = 0
                av.en_cours(fichier.relative_to(racine).as_posix(),
                            interne=f"mutants 0/{len(par_fichier[fichier])}")
            mute = appliquer(originaux[fichier], mutant)
            # Garde-fou : le plan ne contient que des mutants deja compiles par `compilables`.
            # Le revalider coute quelques millisecondes et interdit qu une regression du filtre
            # fasse jouer un mutant qui ne compile pas — donc invariablement « tue ».
            try:
                compile(mute, str(fichier), "exec")
            except SyntaxError:
                continue  # hors du denominateur
            viables += 1
            viables_par_fichier[fichier] = viables_par_fichier.get(fichier, 0) + 1
            poser(fichier, mute)
            if _suite_verte(racine, python):
                survivants.append(mutant)
                survivants_par_fichier.setdefault(fichier, []).append(mutant)
            restaurer({fichier: octets[fichier]})
            joues_module += 1
            av.sous_etape(f"mutants {joues_module}/{len(par_fichier[fichier])}")
        if fichier_courant is not None:
            av.unite_finie(fichier_courant.relative_to(racine).as_posix())
    except subprocess.TimeoutExpired:
        # Un délai dépassé ne doit jamais emporter l audit entier : le pan se DÉCLARE non
        # mesuré (le `finally` restaure les sources avant toute chose).
        interrompu = (
            "mutation : délai dépassé pendant le jeu des mutants — score partiel sur les "
            f"{viables} mutant(s) déjà joués, les autres pans restent mesurés"
        )
    finally:
        # Restauration a l OCTET PRES, inconditionnelle : c est le garde-fou G-1 lui-meme.
        restaurer(octets)
        _purger_bytecode(racine)
        av.final()  # TF-0096 : l émission finale part même sur interruption
    if interrompu:
        non_juge.append(interrompu)

    scores: dict[str, dict] = {}
    for fichier in retenus:
        relatif = fichier.relative_to(racine).as_posix()
        viables_f = viables_par_fichier.get(fichier, 0)
        if not viables_f:
            candidats = candidats_par_fichier.get(fichier, 0)
            tires = len(par_fichier.get(fichier, []))
            # Trois causes DISTINCTES d absence de score. Les confondre sous un motif unique
            # ferait passer un module non mesure pour un module non mesurable — et le second
            # ne se repare pas, alors que le premier se repare en relancant.
            if not candidats:
                motif = (
                    "aucun mutant compilable — le module ne porte aucune expression mutable "
                    "sans casser la syntaxe"
                )
            elif not tires:
                motif = f"{candidats} mutant(s) compilable(s), aucun echantillonne"
            else:
                motif = (
                    f"{tires} mutant(s) echantillonne(s) sur {candidats} compilable(s), aucun "
                    "joue — plafond global atteint ou delai depasse"
                )
            scores[relatif] = {"mute": False, "motif_non_mute": motif}
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
            classe=classes.MUTANT_SURVIVANT,
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
                classe=classes.SEUIL_NON_TENU,
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
