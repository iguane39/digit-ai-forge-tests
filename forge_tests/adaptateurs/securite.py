"""Adaptateur Sécurité (Q4) — câblage des oracles existants, sans en réécrire un seul.

Trois oracles du registre `quality-oracles` existent, sont exécutables, et n avaient jamais été
appelés par Forge Tests : SAST (injection, exécution dangereuse), SCA (vulnérabilités de
dépendances), secrets. Les réécrire aurait violé la règle R3 — on s appuie sur l outil qui fait
foi. Cet adaptateur les invoque et traduit leur contrat de sortie dans celui du framework.

Propriété importante : leurs `non_juge` sont REPRIS tels quels. Ce que ces oracles ne jugent
pas devient de la dette déclarée du framework, pas une limite invisible héritée en silence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from forge_tests import classes
from forge_tests.disposition import motif_racine_execution, racine_execution
from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter
from forge_tests import exclusions

NOM, PAN = "securite-oracles", "securite"

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "fournir des sources Python lisibles sous la racine d'exécution du projet (`backend/` ou "
    "la racine du dépôt elle-même) : le pan est un contrôle statique, il n'a besoin d'aucune "
    "exécution mais il lui faut du code à lire"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "T7", "famille": "technique", "titre": "Sécurité",
     "decoupe": "module", "axe_cas": "unitaire"},
)

# RT-13 : le seul champ qui debloque CE pan — la racine des scripts d oracles a jouer. Un
# compte ou une instance servie ne l auraient jamais rendu mesurable.
CHAMPS_REQUIS = ("FORGE_TESTS_ORACLES",)

ORACLES = ("sast", "secrets", "sca")

_DEFAUT = Path.home() / ".claude" / "skills" / "quality-oracles" / "scripts"

# Nom attendu par le registre de dette. Les non_juge des oracles delegues s y ajoutent a
# l execution : ils dependent des outils reellement presents (semgrep, gitleaks, pip-audit).
NON_JUGE = [
    "securite : le perimetre scanne est le dossier du projet analyse ; ni l historique git, "
    "ni l infrastructure declaree ailleurs (conteneurs, pipelines, secrets d execution)",
    "securite : aucun test d intrusion ni d authentification/autorisation au niveau metier",
    "securite : le scan est BORNE aux sources du produit (dependances exclues — .venv, "
    "node_modules, dist, build…) ; un secret commis DANS une dependance versionnee ne serait "
    "pas vu ici, ce n est pas le meme risque ni le meme destinataire qu un secret du produit",
    # TF-0292 : la REGLE, promue ici depuis le non_juge de SORTIE ou TF-0280 l avait laissee.
    # La sortie continue de NOMMER les dossiers reellement ecartes — c est une mesure, elle
    # depend du projet ; la regle, elle, est vraie de tout projet et c est pour cela qu elle
    # entre au registre de dette, seul endroit ou les limites se comptent.
    "securite : le code VENDORISE (dossier de convention `vendor`) n est PAS scanne — "
    "dependance tierce EPINGLEE, copiee dans le depot pour la figer, jamais servie ni modifiee "
    "par le produit. Meme perimetre que `.venv` et que la gate `vendor/` de forge-development : "
    "un secret commis DANS un vendored se corrige en changeant l epingle, pas la ligne. Un "
    "projet qui nommerait `vendor` un dossier de SON produit le verrait donc ignore ici",
    # TF-0291 — meme famille que le Larsen du pan `prompts` (TF-0257) : l auditeur s accusait
    # lui-meme. La regle est declaree ici, comme celle de TF-0257 l est dans `prompts`.
    "securite : quand le projet audite EST forge-tests (signature du depot : le paquet "
    "`forge_tests`, sa recette et son registre de dette), ses bancs d essai `fixtures\\` et ses "
    "chaines de montage de test `tests\\` ne sont PAS scannes — un banc rouge PORTE le defaut "
    "qu il existe pour faire detecter, et une chaine de montage PLANTE le secret dont elle "
    "prouve la detection : les accuser mesure l auditeur, pas l audite (TF-0291). Le code de la "
    "forge (`forge_tests\\`, `recette\\`) reste scanne, et tout autre projet garde ses "
    "`fixtures\\` et ses `tests\\` sous controle",
]

# --- TF-0291, le LARSEN du pan securite -------------------------------------------------------
# Constat mesure le 15/08 : le pan joue sur forge-tests elle-meme sort 5 constats, TOUS sur de la
# matiere de test plantee expres — 2 SAST (`fixtures/banc-rouge/backend/app/recherche.py:13`, qui
# est le defaut du banc rouge, et `tests/test_tf_0279_id_sast_stable.py:47`, la chaine de montage
# qui prouve la stabilite de l identifiant SAST) et 3 secrets (des AKIA de fixture dans
# `test_correctifs_20260811.py`, `test_tf_0216_racine_plate.py`, `test_tf_0280_vendored_exclu.py`).
#
# C est le cousin exact du Larsen de TF-0257 : l auditeur mesure ses propres bancs. Le remede est
# le meme — reconnaitre l auditeur, et n exclure que ce qu il DECLARE comme matiere de test.
#
# La reconnaissance se fait sur la SIGNATURE du depot, jamais sur son nom : un depot renomme
# reste forge-tests, et un produit qui s appellerait `forge-tests` sans en etre un doit rester
# scanne entierement. Trois marqueurs, TOUS exiges.
_SIGNATURE_FORGE_TESTS = (
    Path("forge_tests") / "adaptateurs" / "__init__.py",
    Path("recette") / "verifier_corpus.py",
    Path("registre-dette.json"),
)
# Les emplacements que la forge DECLARE comme matiere de test. `fixtures\` est deja declare tel
# quel dans son `pyproject.toml` (« les bancs d essai sont des DONNEES d acceptation — produits
# factices figes —, pas le code de la forge ») ; `tests\` est le dossier des chaines de montage.
# Ancres a la RACINE de l application : un `tests\` niche dans `forge_tests\` resterait scanne.
_MATIERE_DE_TEST_DE_LA_FORGE = ("fixtures", "tests")


def est_la_forge_elle_meme(application: Path) -> bool:
    """Le projet audité est-il forge-tests ? Sur signature, jamais sur le nom du dossier."""
    return all((application / marqueur).exists() for marqueur in _SIGNATURE_FORGE_TESTS)


def _racine_oracles() -> Path | None:
    declare = os.environ.get("FORGE_TESTS_ORACLES")
    if declare and Path(declare).is_dir():
        return Path(declare)
    return _DEFAUT if _DEFAUT.is_dir() else None


# Nom conventionnel du dossier de code vendorise, partage par toute la chaine (voir TF-0280
# ci-dessous) : `vendor` chez forge-development comme dans les pans `interface` et `prompts`.
_VENDORISE = "vendor"

# TF-0099 : constate le 11/08 — `oracle-secrets` complete son scanner integre par un appel a
# `gitleaks detect -s <cible>` SANS aucune exclusion de repertoire (contrairement a son propre
# scanner JS, qui exclut deja node_modules/.venv/dist/build). Le reecrire aurait viole la regle
# R3 (« s appuyer sur l outil qui fait foi, ne pas le reecrire ») : la seule correction possible
# cote appelant est de ne JAMAIS lui tendre les dependances. 219 « fuites » confirmees, 100 %
# situees dans des bibliotheques tierces (cryptography, pyjwt, sqlalchemy…) sous .venv/ —
# aucune dans le code du produit.
_EXCLUS_DEPENDANCES = (
    ".venv", "venv", "node_modules", "dist", "build", "__pycache__",
    ".git", "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    # TF-0216 : depuis que la racine est DECOUVERTE, ce pan peut lire la racine du depot
    # elle-meme (projet plat) et non plus seulement `backend/`. Les dossiers d ARTEFACTS de la
    # convention pilot y vivent — `forge\` (livrables archives des cycles precedents, cf.
    # TF-0218), `output\`, ses archives `old\`/`Old\`, les PNG d oracles. Les tendre a l oracle
    # delegue rejouerait exactement RT-9/RT-4 dans le pan securite : volume copie sans rapport
    # avec le produit, et « fuites » imputees a des livrables de forge-tests plutot qu au code
    # audite. Meme raisonnement que pour `.venv` : un dossier jamais copie ne peut pas produire
    # de finding.
    "forge", "output", "old", "Old", ".oracles",
    # TF-0280 : le code VENDORISE — dependance tierce EPINGLEE, copiee dans le depot pour la
    # figer, jamais servie ni modifiee par le produit. C est une dependance qui a change de
    # dossier, pas du code du produit : meme risque, meme destinataire et meme remede que
    # `.venv` (mettre a jour l epingle, pas corriger la ligne). Le contrat existait deja
    # partout ailleurs — les gates de forge-development l excluent du lint
    # (`extend-exclude = ["vendor"]`, « code tiers epingle »), les pans `interface` et
    # `prompts` de cette forge aussi ; ce pan etait le SEUL a le tendre encore aux oracles.
    # Cout mesure sur forge-tests elle-meme : `tests/vendor/axe.min.js` (axe-core epingle,
    # jamais servi) produisait a lui seul 114 constats — 112 secrets, 2 SAST — soit un rapport
    # dont le lecteur devait ecarter la quasi-totalite a la main avant d apercevoir le produit.
    _VENDORISE,
    # TF-0536/0542/0543 (lot AuxPortesDeLaBaie 20260823) : le SOCLE commun vient desormais
    # d'une source unique. Le depot portait DIX listes divergentes (7 a 31 entrees) et
    # `input` ne figurait dans AUCUNE : sur un audit reel, 12 constats sur 15 portaient sur
    # `input\` — un site concurrent aspire et une ancienne version du site. Les entrees
    # ci-dessus restent ecrites ici : elles portent le motif de CE pan.
    *exclusions.socle(),
)


def _sources_du_produit(
    application: Path,
    tmp: Path,
    vendorises: list[str] | None = None,
    bancs: list[str] | None = None,
) -> Path:
    """Copie FILTRÉE de `application`, sans les dossiers de dépendances.

    Border ce que l oracle délégué reçoit est le seul levier qui ne réécrit pas gitleaks : un
    dossier qui ne contient jamais `.venv` ne peut pas produire de finding « dans » `.venv`,
    quel que soit le comportement interne de l outil invoqué.

    `vendorises` recueille les dossiers vendorisés réellement écartés : une exclusion se DIT au
    rapport, elle ne se pratique jamais en silence (TF-0280). Sans cette liste, un lecteur ne
    pourrait pas distinguer « aucun secret dans le vendored » de « le vendored n a pas été lu ».

    `bancs` fait de même pour la matière de test de la forge (TF-0291), et pour la même raison.
    L exclusion est ANCRÉE à la racine de l application : un `tests\\` niché dans le paquet reste
    scanné, seule la matière déclarée à la racine du dépôt de la forge sort du périmètre.
    """
    cible = tmp / "sources"
    filtre = shutil.ignore_patterns(*_EXCLUS_DEPENDANCES)
    forge = est_la_forge_elle_meme(application)

    def tracant(dossier: str, noms: list[str]) -> set[str]:
        exclus = set(filtre(dossier, noms))
        if forge and Path(dossier) == Path(application):
            for nom in noms:
                if nom in _MATIERE_DE_TEST_DE_LA_FORGE and (application / nom).is_dir():
                    exclus.add(nom)
                    if bancs is not None:
                        bancs.append(nom)
        if vendorises is not None:
            vendorises.extend(
                os.path.relpath(Path(dossier, nom), application)
                for nom in exclus
                if nom == _VENDORISE
            )
        return exclus

    shutil.copytree(application, cible, ignore=tracant)
    return cible


def _relocaliser(texte: str, scan: Path, application: Path) -> str:
    """Réécrit un chemin sous la copie filtrée en chemin sous l arbre réel du projet audité.

    Sans ce ré-étiquetage, chaque `localisation` publiée pointerait vers un dossier temporaire
    détruit à la fin de l analyse — illisible pour quiconque reçoit le rapport.

    TF-0279 — DEUX formes à ré-étiqueter, pas une. Les oracles délégués ne publient pas leur
    `where` dans le même repère : `oracle-secrets` donne un chemin ABSOLU (le remplacement de
    préfixe ci-dessous suffit, et c est pourquoi ses 112 constats se contestaient sans mal),
    `oracle-sast` donne `path.relative(process.cwd(), fichier)` — un chemin RELATIF où la copie
    filtrée n apparaît que par son suffixe `<brouillon aléatoire>\\sources\\`. Le préfixe absolu
    n y figurant nulle part, le remplacement échouait en silence et l identifiant du finding
    embarquait le nom TIRÉ AU SORT du dossier de la passe : deux exécutions du même défaut sur
    le même fichier produisaient deux identifiants distincts. Constaté sur trois passes
    (lgvdcxei, qyoth9pg, ccnh5t5j) : aucune ligne de `constats-contestes.jsonl` ne pouvait plus
    matcher, la contestation d un constat SAST était mécaniquement impossible.

    L ancre est donc le chemin PROJET dans les deux cas. Réécrire l oracle aurait violé R3 ;
    c est l appelant qui sait, lui, où il a copié quoi.
    """
    if str(scan) in texte:
        return texte.replace(str(scan), str(application))
    for separateur in ("\\", "/"):
        marque = f"{scan.parent.name}{separateur}{scan.name}"
        debut = texte.find(marque)
        if debut == -1:
            continue
        reste = texte[debut + len(marque):].lstrip("\\/")
        return str(application) + (os.sep + reste if reste else "")
    return texte


def _lancer(script: Path, cible: Path) -> dict | None:
    node = shutil.which("node")
    if node is None:
        return None
    try:
        resultat = subprocess.run(
            [node, str(script), str(cible)],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        # Delai depasse : le pan se declare non mesure, il n emporte pas l audit entier.
        return None
    sortie = (resultat.stdout or "").strip()
    if not sortie:
        return None
    try:
        return json.loads(sortie)
    except json.JSONDecodeError:
        return None


def analyser(cible: Path) -> SortieAdaptateur:
    racine = _racine_oracles()
    # Perimetre elargi : le code applicatif ET tout ce qui l entoure — configuration, tests,
    # scripts. Un secret en dur vit rarement dans le module metier.
    # TF-0216 : la racine est DECOUVERTE (`backend/` puis la racine plate), plus supposee. Sur un
    # produit a racine plate, `cible/'backend'` n existait pas et ce pan sortait SKIP alors que
    # ses sources etaient juste a cote, parfaitement lisibles.
    application = racine_execution(cible)
    # TF-0219 — DEUX causes, DEUX motifs. Le motif unique publiait « registre d oracles
    # introuvable » y compris quand le registre etait parfaitement resolu et que la vraie cause
    # etait l absence de sources a lire : un aller-retour de configuration inutile, mesure au
    # ledger du lot COMPTA (seq 17). Le `POUR_COUVRIR` de ce pan disait deja la bonne cause ;
    # le motif s aligne dessus. Le motif publie au rapport est le DERNIER de la liste.
    if racine is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "registre d oracles introuvable : definir FORGE_TESTS_ORACLES vers le dossier "
                "scripts de quality-oracles",
            ],
        )
    if not application.is_dir():
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"aucune source a lire : {application} n existe pas — le registre d oracles, "
                f"lui, EST resolu ({racine}). {motif_racine_execution(cible)}",
            ],
        )

    findings: list[Finding] = []
    # TF-0216 (garde-fou de methode) : le pan DIT sur quelle racine il a lu. Une decouverte qui
    # change d un projet a l autre sans se declarer serait pire que l ancre en dur qu elle
    # remplace — ce pan est le canal de publication toujours present pour cette phrase.
    non_juge: list[str] = [*NON_JUGE, f"securite : {motif_racine_execution(cible)}"]
    echec = False
    joues: list[str] = []

    vendorises: list[str] = []
    bancs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="forge-tests-securite-") as brouillon:
        scan = _sources_du_produit(application, Path(brouillon), vendorises, bancs)
        # TF-0291 : la MESURE de l exclusion — ce que CE scan a reellement ecarte parce que le
        # projet audite est la forge elle-meme. La regle vit dans `NON_JUGE` ; ici on nomme les
        # dossiers, et seulement s il y en a. Un lecteur doit pouvoir distinguer « rien a
        # signaler dans les bancs » de « les bancs n ont jamais ete lus ».
        if bancs:
            non_juge.append(
                "securite : matiere de test de la forge ECARTEE de ce scan — "
                + ", ".join(sorted(bancs))
                + " : le projet audite EST forge-tests (signature du depot). Un banc rouge PORTE "
                "le defaut qu il existe pour faire detecter, une chaine de montage PLANTE le "
                "secret dont elle prouve la detection. Le code de la forge, lui, reste scanne"
            )
        # TF-0280 : l exclusion se DIT, toujours, et elle NOMME ce qu elle a ecarte. Un pan qui
        # borne son perimetre sans le publier transforme un choix defendable en angle mort : le
        # lecteur d un rapport muet ne peut pas distinguer « rien a signaler dans le vendored »
        # de « le vendored n a jamais ete lu ». La phrase n est emise que si quelque chose a
        # reellement ete ecarte — declarer une exclusion qui n a rien exclu serait du bruit.
        # TF-0292 : la REGLE vit desormais dans `NON_JUGE` (elle est vraie de tout projet, donc
        # elle se compte au registre de dette). Ce qui reste ici est la MESURE — les dossiers
        # que CE scan a reellement ecartes — et elle ne s emet que s il y en a : declarer une
        # exclusion qui n a rien exclu serait du bruit, et un rapport se lit.
        if vendorises:
            non_juge.append(
                "securite : code VENDORISE ECARTE de ce scan — " + ", ".join(sorted(vendorises))
            )
        for nom in ORACLES:
            script = racine / f"oracle-{nom}.mjs"
            if not script.exists():
                non_juge.append(f"securite : oracle-{nom} absent du registre, non joue")
                continue
            rapport = _lancer(script, scan)
            if rapport is None:
                non_juge.append(f"securite : oracle-{nom} n a produit aucun verdict exploitable")
                continue
            joues.append(nom)
            # Les limites de l oracle delegue deviennent de la dette DECLAREE du framework.
            non_juge.extend(f"securite/{nom} : {ligne}" for ligne in rapport.get("non_juge", []))
            if rapport.get("verdict") != "FAIL":
                continue
            echec = True
            for brut in rapport.get("findings", []):
                if brut.get("sev") == "info":
                    continue
                ou = _relocaliser(str(brut.get("where") or application), scan, application)
                identifiant = f"securite:{nom}:{ou}"
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.SECURITE,
                        localisation=ou,
                        message=f"[{nom}] {brut.get('msg', '')}",
                        severite="bloquant" if brut.get("sev") == "bloquant" else "signale",
                        risque=coter(PAN, identifiant, str(application)),
                    )
                )

    if not joues:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*non_juge, "aucun oracle de securite n a pu etre joue"],
        )
    non_juge.append(f"securite : oracles reellement joues — {', '.join(joues)}")
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if echec and any(f.severite == "bloquant" for f in findings) else "PASS",
        findings=findings,
        non_juge=non_juge,
    )
