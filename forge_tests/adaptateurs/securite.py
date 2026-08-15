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

from forge_tests.disposition import motif_racine_execution, racine_execution
from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

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
]


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
)


def _sources_du_produit(
    application: Path, tmp: Path, vendorises: list[str] | None = None
) -> Path:
    """Copie FILTRÉE de `application`, sans les dossiers de dépendances.

    Border ce que l oracle délégué reçoit est le seul levier qui ne réécrit pas gitleaks : un
    dossier qui ne contient jamais `.venv` ne peut pas produire de finding « dans » `.venv`,
    quel que soit le comportement interne de l outil invoqué.

    `vendorises` recueille les dossiers vendorisés réellement écartés : une exclusion se DIT au
    rapport, elle ne se pratique jamais en silence (TF-0280). Sans cette liste, un lecteur ne
    pourrait pas distinguer « aucun secret dans le vendored » de « le vendored n a pas été lu ».
    """
    cible = tmp / "sources"
    filtre = shutil.ignore_patterns(*_EXCLUS_DEPENDANCES)

    def tracant(dossier: str, noms: list[str]) -> set[str]:
        exclus = filtre(dossier, noms)
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
    with tempfile.TemporaryDirectory(prefix="forge-tests-securite-") as brouillon:
        scan = _sources_du_produit(application, Path(brouillon), vendorises)
        # TF-0280 : l exclusion se DIT, toujours, et elle NOMME ce qu elle a ecarte. Un pan qui
        # borne son perimetre sans le publier transforme un choix defendable en angle mort : le
        # lecteur d un rapport muet ne peut pas distinguer « rien a signaler dans le vendored »
        # de « le vendored n a jamais ete lu ». La phrase n est emise que si quelque chose a
        # reellement ete ecarte — declarer une exclusion qui n a rien exclu serait du bruit.
        if vendorises:
            non_juge.append(
                "securite : code VENDORISE non scanne — "
                + ", ".join(sorted(vendorises))
                + " : dependance tierce EPINGLEE, copiee dans le depot et jamais servie ; meme "
                "perimetre que `.venv` et que la gate `vendor/` de forge-development. Un secret "
                "commis DANS un vendored se corrige en changeant l epingle, pas la ligne"
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
                        classe="securite",
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
