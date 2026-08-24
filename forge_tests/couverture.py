"""Revue statique de la CONFIGURATION de couverture — le chiffre avant la mesure.

TF-0589 (lot Approval2 20260824d, 24/08/2026).

Un contre-oracle mesure ce que la suite atteint. Aucun ne regardait le RÉGLAGE qui produit ce
chiffre — or trois défauts y vivaient en même temps, tous sous un seuil VERT, et c'est leur
simultanéité qui fait la règle : chacun seul aurait pu passer pour un réglage discutable ; les
trois ensemble rendaient la mesure inutilisable tout en la rendant rassurante.

**(1) LE DÉNOMINATEUR N'ÉTAIT PAS DÉCLARÉ.** La configuration listait ce qu'on RETIRE
(`coverage.exclude`) ; personne n'avait déclaré ce qu'on MESURE. Les répertoires de recette et
d'actifs publics entraient donc dans le calcul, **comptés à 0 %** :

    instructions   75,33 % affiché   →   84,68 % sur le périmètre réel
    fonctions      61,5 %  affiché   →   62,92 %

Neuf points d'écart, et le SENS de l'erreur importe peu : la couverture pouvait **monter** parce
qu'un fichier de recette avait été supprimé. *Un chiffre dont le dénominateur n'est pas déclaré
n'est pas une mesure, c'est un nombre.*

**(2) UN SEUIL GLOBAL NE PEUT PAS ÉCHOUER SUR UN ÉCRAN NON TESTÉ.** Le seuil valait 70 % / 60 %
sur tout le code source, et il était vert. Derrière ce vert : un écran de gouvernance
(délégations, accès partagés — du fonctionnel écrit et livré) à **1,88 %**, et la page de retour
d'authentification, passage obligé de TOUTE session, à **12,5 %**. Les modules bien couverts,
nombreux et petits, compensent arithmétiquement les écrans, rares et gros : **il n'existe aucune
valeur de seuil global qui aurait signalé ces deux fichiers** sans faire échouer tout le reste.
C'est exactement l'arbitrage déjà tranché pour la mutation dans `seuils.py` — « un score global
de 0,70 se tient très bien avec un module métier à 0,0 noyé dans la masse » — appliqué ici à la
couverture, deux ans de recul plus tard sur un autre indicateur.

**(3) L'INDICATEUR RAPPORTÉ N'ÉTAIT PAS CELUI QUI PORTAIT LE RISQUE.** Un composant d'actions
affichait **90,6 % d'instructions et 37,5 % de fonctions** : les boutons étaient *rendus*,
presque aucun n'était *cliqué*. La console d'administration — export d'audit, réassignation
d'approbation — était à **25 % de fonctions**. Le rapport mettait les instructions en avant :
c'est l'indicateur qu'un simple rendu suffit à faire monter, donc celui qui rassure le plus et
prouve le moins.

**LA QUATRIÈME RÈGLE EST UNE LEÇON DE POSE, ET ELLE VIENT DE LA MISE EN ŒUVRE RÉELLE** : *le
plancher se cale SOUS le niveau atteint, pas dessus.* Un cliquet à ras de la mesure casse au
premier remaniement légitime, et une porte qui casse pour rien finit désarmée (R-33 bis du
pilot). Sur le cas fondateur : niveau atteint 97,5 % / 87,2 %, plancher posé à 80 % / 60 %.
Cette règle-là ne se mécanise pas ici — on ne connaît pas le niveau atteint en lisant une
configuration — mais elle est écrite dans le message de la règle (2), là où quelqu'un s'apprête
à choisir un chiffre.

Aucune exécution, aucun réseau : ce module lit des fichiers de configuration.
"""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Finding
from forge_tests.risque import coter

PAN = "front"

#: Les configurations de couverture reconnues. La liste est FERMÉE et se lit : un outil absent
#: d'ici n'est pas jugé, et c'est déclaré plutôt que deviné.
CONFIGS = (
    "vitest.config.ts", "vitest.config.js", "vitest.config.mjs",
    "vite.config.ts", "vite.config.js",
    "jest.config.ts", "jest.config.js", "jest.config.mjs", "jest.config.cjs",
    ".nycrc", ".nycrc.json", "pyproject.toml", ".coveragerc", "setup.cfg",
)

NON_JUGE = [
    "couverture : la configuration est lue comme du TEXTE, sans evaluer le JavaScript. Un "
    "perimetre construit a l execution (variable, fonction, fusion de configurations) echappe "
    "aux trois regles — elles verront « pas de perimetre declare » la ou il y en a un",
    "couverture : le NIVEAU ATTEINT n est pas connu en lisant une configuration, donc la regle "
    "« le plancher se cale SOUS le niveau atteint, pas dessus » ne peut pas etre mecanisee ici. "
    "Elle est ecrite dans le message de la regle du seuil par fichier, la ou quelqu un s apprete "
    "a choisir un chiffre — c est le seul endroit ou elle sert",
    "couverture : la JUSTESSE d un perimetre declare. L oracle constate qu un `include` existe, "
    "jamais qu il vise le bon dossier — un perimetre declare et faux passe, et c est deja "
    "infiniment mieux qu un perimetre absent, qui derive a chaque fichier ajoute ou retire",
    "couverture : les outils hors de la liste fermee CONFIGS ne sont pas juges. Un projet qui "
    "configure sa couverture ailleurs (script npm, arguments de ligne de commande, CI) n est pas "
    "vu — la configuration en ligne de commande est le trou connu de cette famille",
]

#: Le périmètre déclaré en POSITIF. `include`, `source`, `--cov=` : selon l'outil, le nom change,
#: l'intention est la même — dire ce qu'on mesure au lieu de dire ce qu'on retire.
_PERIMETRE = re.compile(r"\b(include|source|source_pkgs|collectCoverageFrom|--cov=)\b")
#: Ce qu'on retire. Sa présence SEULE est le défaut : elle donne l'illusion d'un périmètre maîtrisé.
_EXCLUSION = re.compile(r"\b(exclude|omit|coveragePathIgnorePatterns|collectCoverageIgnore)\b")
#: Un seuil, quel que soit son nom d'outil.
_SEUIL = re.compile(r"\b(thresholds?|coverageThreshold|fail_under|check_coverage|watermarks)\b")
#: Le seuil PAR FICHIER — le seul qui puisse échouer sur un écran non testé.
_PAR_FICHIER = re.compile(r"\b(perFile|per_file|per-file)\b\s*[:=]\s*true")
#: L'indicateur qui prouve qu'un geste a été joué, et non qu'une ligne a été rendue.
_FONCTIONS = re.compile(r"\b(functions|fail_under_functions|funcs)\b")
_INSTRUCTIONS = re.compile(r"\b(statements|lines|branches)\b")


def _configs(cible: Path) -> list[Path]:
    return [
        chemin
        for chemin in sorted(cible.rglob("*"))
        if chemin.is_file()
        and chemin.name in CONFIGS
        and "node_modules" not in chemin.parts
        and ".venv" not in chemin.parts
    ]


#: La marque d'une SECTION de configuration de couverture — pas le mot « coverage » quelque part.
#: PREMIER PASSAGE DE CETTE RÈGLE, ET ELLE S'EST ACCUSÉE SUR LE BANC VERT DE LA FORGE : le motif
#: initial cherchait le mot, et il l'a trouvé dans une ligne de DÉPENDANCE — `"coverage>=7.15.2"`.
#: Un banc réputé sans défaut se serait mis à rendre un constat bloquant, et une règle qui accuse
#: le corpus de référence de sa propre forge n'aurait pas survécu à la première campagne pressée.
#: C'est la leçon N-23 du pilot appliquée telle quelle : jouer la liste sur le corpus réel, et
#: lire d'abord ce qu'elle attrape À TORT.
_SECTION_COUVERTURE = re.compile(
    r"\[tool\.coverage"                                                      # pyproject.toml
    r"|^\s*coverage\s*:\s*\{"                                                # vitest / vite
    r"|\bcollectCoverage\b|\bcoverageThreshold\b|\bcoverageDirectory\b"       # jest
    r"|\bcoverageProvider\b|\bcoverageReporters\b"
    r"|^\s*\[(?:run|report|paths)\]",                     # .coveragerc, setup.cfg
    re.MULTILINE,
)


def _parle_de_couverture(texte: str, nom: str) -> bool:
    """Une configuration qui ne CONFIGURE pas la couverture n'est pas jugée sur elle.

    `pyproject.toml` et `vite.config.ts` existent chez presque tous les projets et ne portent pas
    forcément de réglage de couverture ; y trouver le mot ne suffit pas, et c'est mesuré plutôt
    que supposé (voir `_SECTION_COUVERTURE`). Un `.nycrc` ou un `.coveragerc`, en revanche, EST
    une configuration de couverture de bout en bout — son nom le dit, rien à chercher dedans.
    """
    if nom in (".nycrc", ".nycrc.json", ".coveragerc"):
        return True
    return bool(_SECTION_COUVERTURE.search(texte))


def analyser_configuration(cible: Path) -> list[Finding]:
    """Les trois règles, sur les configurations de couverture du projet."""
    findings: list[Finding] = []
    for fichier in _configs(cible):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        if not _parle_de_couverture(texte, fichier.name):
            continue
        relatif = fichier.relative_to(cible).as_posix()

        # (a) LE DÉNOMINATEUR SE DÉCLARE EN POSITIF.
        if not _PERIMETRE.search(texte):
            identifiant = f"couverture:perimetre-non-declare:{relatif}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.COUVERTURE_PERIMETRE_NON_DECLARE,
                    localisation=relatif,
                    message=(
                        "la couverture est configuree SANS perimetre declare en positif "
                        "(`include`, `source`, `collectCoverageFrom`)"
                        + (" — seules des EXCLUSIONS sont posees, ce qui donne l illusion d un "
                           "perimetre maitrise" if _EXCLUSION.search(texte) else "")
                        + ". Son denominateur DERIVE alors a chaque fichier ajoute ou retire : "
                        "un chiffre dont le denominateur n est pas declare n est pas une mesure, "
                        "c est un nombre. Mesure du 24/08 : repertoires de recette et d actifs "
                        "publics comptes A 0 % dans le calcul, 75,33 % affiche pour 84,68 % reels "
                        "— et la couverture pouvait MONTER parce qu un fichier de recette avait "
                        "ete supprime"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )

        if not _SEUIL.search(texte):
            continue  # pas de seuil du tout : c'est un autre sujet, et il n'est pas celui-ci

        # (b) LE SEUIL PORTE PAR FICHIER.
        if not _PAR_FICHIER.search(texte):
            identifiant = f"couverture:seuil-global-seul:{relatif}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.COUVERTURE_SEUIL_GLOBAL_SEUL,
                    localisation=relatif,
                    message=(
                        "un seuil de couverture est pose, mais AUCUN seuil par fichier "
                        "(`perFile: true` ou l equivalent de l outil). Un seuil global ne peut "
                        "PAS echouer sur un ecran non teste : les modules bien couverts, nombreux "
                        "et petits, compensent arithmetiquement les ecrans, rares et gros. Mesure "
                        "du 24/08 : sous un seuil global VERT vivaient un ecran de gouvernance a "
                        "1,88 % et la page de retour d authentification, passage oblige de TOUTE "
                        "session, a 12,5 % — et il n existe AUCUNE valeur de seuil global qui les "
                        "aurait signales sans faire echouer tout le reste. Le seuil global peut "
                        "rester, il ne suffit pas. En posant le plancher par fichier : LE CALER "
                        "SOUS LE NIVEAU ATTEINT, PAS DESSUS — un cliquet a ras de la mesure casse "
                        "au premier remaniement legitime, et une porte qui casse pour rien finit "
                        "desarmee (cas reel : niveau 97,5 %/87,2 %, plancher pose a 80 %/60 %)"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )

        # (c) LE SEUIL SUR LES FONCTIONS EST DÛ À CÔTÉ DE CELUI SUR LES INSTRUCTIONS.
        if _INSTRUCTIONS.search(texte) and not _FONCTIONS.search(texte):
            identifiant = f"couverture:fonctions-sans-seuil:{relatif}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.COUVERTURE_FONCTIONS_SANS_SEUIL,
                    localisation=relatif,
                    severite="signale",
                    message=(
                        "un seuil porte sur les instructions ou les lignes, AUCUN sur les "
                        "FONCTIONS. Sur du code d interface, une ligne couverte par un simple "
                        "RENDU ne prouve rien d un geste utilisateur : c est l indicateur qui "
                        "rassure le plus et prouve le moins. Mesure du 24/08 : un composant "
                        "d actions a 90,6 % d instructions et 37,5 % de FONCTIONS — les boutons "
                        "etaient rendus, presque aucun n etait clique ; et la console d "
                        "administration (export d audit, reassignation d approbation) a 25 % de "
                        "fonctions. SIGNALE et non bloquant : un projet sans interface peut "
                        "legitimement s en tenir aux instructions, et l ecart se lit"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )
    return findings
