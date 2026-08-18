"""Revue statique de la suite de tests du projet — les faux verts, avant de les payer.

TF-0344 / TF-0345 (campagne du 17/08/2026).

Un contre-oracle mesure ce que la suite ATTEINT et ce qu'elle VÉRIFIE. Aucun ne regardait la
suite elle-même **en tant que texte** — or trois faux verts sont tombés le même jour, sur la
même campagne, et aucun oracle ne les a vus. Ils ont trois formes, et deux d'entre elles sont
détectables sans rien exécuter. C'est cette moitié-là que ce module rend mécanique.

**(1) Assertion d'ABSENCE sans preuve de PRÉSENCE.** `toHaveCount(0)` passe sur une page encore
en chargement : il n'y a rien parce que rien n'est encore là. Le test du passage de main
séquentiel était vert en isolation et rouge en exécution complète, pour cette seule raison.
*Règle : toute assertion d'absence est précédée d'une assertion de présence sur le même écran.*

**(2) MOTIF satisfait par le DÉCLENCHEUR.** `getByText(/Refused|Refus/i)` matche le bouton
« Refuse ». L'assertion « le refus est enregistré » passait donc AVANT toute décision, ce qui
supprimait la barrière de synchronisation entre profils : instabilité un run sur deux, 30 s de
timeout par occurrence. Après correction, la suite complète est passée de 3,6 min à 36 s, avec
trois passages verts consécutifs — et le même défaut dormait dans un spec antérieur, vert depuis
le 12/08. *Règle : aucun motif d'assertion ne doit pouvoir être satisfait par le déclencheur de
l'action qu'il vérifie.* C'est la plus rentable des trois, et la plus facile à voir : un motif
d'assertion qui est un préfixe du libellé cliqué dans le même test.

**(3) CELLULE MUTANTE sur objet PARTAGÉ.** Dans la matrice des droits, l'approbation réussie du
profil N faisait avancer le circuit et ouvrait le tour du profil N+1, qui rendait 201 au lieu de
409 — faux échec. *Règle : toute cellule dont le succès mute l'état exige un objet neuf.* Elle
n'est pas détectable ici (il faudrait savoir ce que « muter » veut dire chez le projet) : elle
est portée par le patron de matrice des droits (TF-0343), qui la rend structurelle plutôt que
vérifiée après coup. Ce module la DÉCLARE en non-jugé, il ne fait pas semblant de la voir.

**(4) DONNÉE DE TEST RECOPIÉE (TF-0345).** Le PNG de référence des parcours e2e — 3316
caractères de base64 — était recopié dans chaque spec. En le reprenant pour la suite
inter-profils, 80 caractères ont sauté : le fichier gardait sa signature PNG et une taille
plausible, mais le worker sortait « broken data stream » et l'envoi restait bloqué. Quatre tests
en timeout, pour une cause invisible à la lecture du diff — le symptôme (Send jamais activé)
pointait vers la chaîne de conversion, pas vers la donnée. *Règle : une donnée de test partagée
se RÉFÉRENCE (un module dédié, importé), elle ne se recopie pas ; et si elle est générée, elle
se VALIDE à la génération plutôt qu'on ne fasse confiance au littéral.*
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Finding
from forge_tests.risque import coter

PAN = "front"

#: Les fichiers relus. Les suites Python ne sont PAS revues ici : les trois faux verts mesurés
#: sont des idiomes de navigateur, et transposer leurs motifs à pytest sans cas réel
#: fabriquerait du bruit. L'écart est déclaré (loi 3), il n'est pas tu.
SUFFIXES_SPEC = (".spec.ts", ".spec.js", ".spec.tsx", ".spec.jsx", ".test.ts", ".test.tsx")

#: Un littéral en dessous de cette longueur n'est pas une « donnée de test » : c'est un libellé.
#: 200 caractères est le seuil au-dessus duquel une recopie ne se relit plus à l'œil — le cas
#: fondateur en portait 3316, et l'écart de 80 caractères y était invisible.
LONGUEUR_DONNEE = 200

#: Deux littéraux longs qui se ressemblent à ce point sont la même donnée, recopiée. En dessous,
#: ce sont deux données différentes qui partagent un encodage.
RESSEMBLANCE = 0.90

NON_JUGE = [
    "revue de suite : la CELLULE MUTANTE sur objet partage (TF-0344, piege 3) n est pas "
    "detectable statiquement — savoir qu une action MUTE l etat demande de connaitre le metier. "
    "Elle est tenue par le patron de matrice des droits (TF-0343), qui exige un objet neuf pour "
    "toute cellule dont le succes mute l etat",
    "revue de suite : seules les suites de NAVIGATEUR sont relues (.spec.ts et voisins) — les "
    "suites Python ne le sont pas, faute de cas reel sur leurs idiomes",
    "revue de suite : lecture TEXTUELLE, pas d analyse de flot — un motif construit a "
    "l execution (variable, gabarit) echappe a ces regles",
]

_TEST = re.compile(r"^\s*(?:test|it)(?:\.\w+)*\s*\(\s*[\"'`](?P<nom>[^\"'`]+)", re.MULTILINE)

# Les assertions d ABSENCE réellement rencontrées, et leurs proches immédiates.
_ABSENCE = re.compile(
    r"toHaveCount\(\s*0\s*\)|\.not\s*\.\s*to(?:BeVisible|BeAttached|BeInViewport|HaveText)\(",
)
# Les assertions de PRÉSENCE qui acquittent la règle : elles prouvent que l écran est bien rendu.
_PRESENCE = re.compile(
    r"(?<!not\.)\bto(?:BeVisible|BeAttached|HaveText|ContainText|HaveURL|HaveTitle)\("
    r"|toHaveCount\(\s*[1-9]"
    r"|waitFor(?:LoadState|Selector|URL|Response)?\(",
)

# Un libellé cliqué : `getBy…('X')` ou `getBy…({ name: 'X' })` suivi d un `.click()` dans la
# même expression. La grammaire reste volontairement étroite — mieux vaut manquer un cas que
# fabriquer un faux positif sur un contrôle né pour supprimer des faux verts.
_CLIC = re.compile(
    r"getBy(?:Role|Text|Label|TestId|Title|Placeholder)\("
    r"(?:[^()]*?name\s*:\s*)?[\"'`/](?P<libelle>[^\"'`/]{2,60})[\"'`/]?[^;]{0,200}?\.click\(",
    re.DOTALL,
)
# Un motif d assertion : le texte cherché dans un `expect(...)`.
_MOTIF_ASSERTION = re.compile(
    r"expect\([^;]{0,200}?getBy(?:Role|Text|Label|Title)\("
    r"(?:[^()]*?name\s*:\s*)?(?P<delim>[\"'`]|/)(?P<motif>[^\"'`/]{2,60})(?P=delim)",
    re.DOTALL,
)
_LITTERAL_LONG = re.compile(
    r"[\"'`]([A-Za-z0-9+/=_-]{" + str(LONGUEUR_DONNEE) + r",})[\"'`]"
)


def _specs(cible: Path) -> list[Path]:
    fichiers = [
        chemin
        for chemin in sorted(cible.rglob("*"))
        if chemin.is_file()
        and chemin.name.endswith(SUFFIXES_SPEC)
        and "node_modules" not in chemin.parts
    ]
    return fichiers


def _blocs_de_test(texte: str) -> list[tuple[str, str]]:
    """(nom du test, corps) — découpe par déclaration de test, sans parser le JavaScript."""
    debuts = list(_TEST.finditer(texte))
    blocs = []
    for rang, trouve in enumerate(debuts):
        fin = debuts[rang + 1].start() if rang + 1 < len(debuts) else len(texte)
        blocs.append((trouve.group("nom"), texte[trouve.end():fin]))
    return blocs


def _alternatives(motif: str) -> list[str]:
    """`Refused|Refus` → les deux : une seule alternative satisfaite suffit à faire un faux vert."""
    return [part.strip() for part in motif.split("|") if part.strip()]


def absence_sans_presence(cible: Path) -> list[Finding]:
    """Piège 1 — une assertion d'absence qu'aucune assertion de présence ne précède."""
    findings: list[Finding] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        for nom, corps in _blocs_de_test(fichier.read_text(encoding="utf-8", errors="replace")):
            absence = _ABSENCE.search(corps)
            if not absence:
                continue
            presence = _PRESENCE.search(corps)
            if presence is not None and presence.start() < absence.start():
                continue
            identifiant = f"revue:absence-sans-presence:{relatif}:{nom}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.FAUX_VERT_ABSENCE,
                    localisation=relatif,
                    message=(
                        f"« {nom} » affirme une ABSENCE (`{absence.group(0)}`) sans qu aucune "
                        "assertion de PRESENCE ne l ait precedee sur le meme ecran : sur une "
                        "page encore en chargement, il n y a rien parce que rien n est encore "
                        "la. Vert en isolation, rouge en execution complete — mesure le 17/08"
                    ),
                    risque=coter(PAN, identifiant, relatif),
                )
            )
    return findings


def motif_satisfait_par_le_declencheur(cible: Path) -> list[Finding]:
    """Piège 2 — le plus rentable, et le seul entièrement mécanisable des trois.

    Un motif d'assertion qui est un PRÉFIXE du libellé cliqué dans le même test peut être
    satisfait par le déclencheur lui-même : l'assertion passe avant que l'action ait produit
    quoi que ce soit, et la barrière de synchronisation disparaît.
    """
    findings: list[Finding] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        for nom, corps in _blocs_de_test(fichier.read_text(encoding="utf-8", errors="replace")):
            cliques = [trouve.group("libelle").strip() for trouve in _CLIC.finditer(corps)]
            if not cliques:
                continue
            for trouve in _MOTIF_ASSERTION.finditer(corps):
                for motif in _alternatives(trouve.group("motif")):
                    collisions = [
                        libelle
                        for libelle in cliques
                        if libelle.lower().startswith(motif.lower())
                    ]
                    if not collisions:
                        continue
                    identifiant = f"revue:motif-du-declencheur:{relatif}:{nom}:{motif}"
                    findings.append(
                        Finding(
                            id=identifiant,
                            classe=classes.FAUX_VERT_MOTIF,
                            localisation=relatif,
                            message=(
                                f"« {nom} » : le motif d assertion « {motif} » est un prefixe du "
                                f"libelle CLIQUE « {collisions[0]} » — l assertion peut etre "
                                "satisfaite par le declencheur lui-meme, avant toute action. "
                                "Mesure : instabilite 1 run sur 2, 30 s de timeout par "
                                "occurrence, suite passee de 3,6 min a 36 s apres correction"
                            ),
                            risque=coter(PAN, identifiant, relatif),
                        )
                    )
                    break
    return findings


def donnees_recopiees(cible: Path) -> list[Finding]:
    """TF-0345 — une donnée de test partagée se référence ; elle ne se recopie pas.

    Deux constats, et le second est le plus coûteux : la copie IDENTIQUE (la cause) et la copie
    DÉRIVÉE (le symptôme — 80 caractères perdus, quatre tests en timeout, un diagnostic égaré
    vers la chaîne de conversion parce que le symptôme ne pointe pas vers la donnée).
    """
    litteraux: list[tuple[str, str]] = []
    for fichier in _specs(cible):
        relatif = fichier.relative_to(cible).as_posix()
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        litteraux.extend((relatif, trouve.group(1)) for trouve in _LITTERAL_LONG.finditer(texte))

    findings: list[Finding] = []
    vus: set[tuple[str, str]] = set()
    for rang, (fichier_a, valeur_a) in enumerate(litteraux):
        for fichier_b, valeur_b in litteraux[rang + 1:]:
            if fichier_a == fichier_b:
                continue
            paire = tuple(sorted((fichier_a, fichier_b)))
            if paire in vus:
                continue
            ratio = SequenceMatcher(None, valeur_a, valeur_b).quick_ratio()
            if ratio < RESSEMBLANCE:
                continue
            vus.add(paire)
            identique = valeur_a == valeur_b
            identifiant = f"revue:donnee-recopiee:{paire[0]}:{paire[1]}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.DONNEE_DE_TEST_RECOPIEE,
                    localisation=paire[0],
                    message=(
                        (
                            f"la meme donnee de test ({len(valeur_a)} caracteres) est RECOPIEE "
                            f"dans {paire[0]} et {paire[1]}"
                            if identique
                            else (
                                f"deux litteraux longs quasi identiques ({ratio:.0%}) entre "
                                f"{paire[0]} ({len(valeur_a)} car.) et {paire[1]} "
                                f"({len(valeur_b)} car.) : une recopie a DERIVE"
                            )
                        )
                        + " — une donnee de test partagee se REFERENCE (un module dedie, "
                        "importe) et se VALIDE a la generation. Cas fondateur : 80 caracteres "
                        "perdus dans la recopie d un PNG base64, quatre tests en timeout, et un "
                        "diagnostic egare vers la chaine de conversion"
                    ),
                    risque=coter(PAN, identifiant, paire[0]),
                )
            )
    return findings


def analyser_suite(cible: Path) -> list[Finding]:
    """Les trois règles mécanisables, sur les specs du projet. Aucune exécution, aucun réseau."""
    return [
        *absence_sans_presence(cible),
        *motif_satisfait_par_le_declencheur(cible),
        *donnees_recopiees(cible),
    ]
