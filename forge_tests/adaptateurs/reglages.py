"""Adaptateur réglages-plateforme — la campagne lit chaque réglage de plateforme exigé (TF-2229).

Pièce 5 de l'étude « Sécurité par défaut de bout en bout » du 06/11/2026 (décision D-178 (a)) :
le principe « réglage admissible appliqué à la création, vérifié à chaque livraison, exception
décidée » devient une loi transverse. Le point d'injection des tests : en campagne, chaque réglage
de plateforme que le produit EXIGE est lu, comparé à l'attendu du registre, et relié à l'exigence
qui le porte (traçabilité exigence vers test).

Ce pan lit trois choses :

  - **les exigences de réglage** du produit : une entrée de `EXIGENCES.json`
    (`FORGE_TESTS_EXIGENCES`, sinon `EXIGENCES.json`, `forge/EXIGENCES.json` ou
    `forge/etapes/conception/EXIGENCES.json`) qui porte la clé `reglage_plateforme` — le texte du
    réglage du registre (ou son début), ou un objet `{"plateforme", "reglage", "decision"}`.
    Convention de cette forge, comme `personas` ;
  - **le registre des réglages sûrs par défaut** du pilot
    (`references/REGLAGES-SURS-PAR-DEFAUT.json`, même schéma que l'étude : plateforme, reglage,
    source_url, source_lue_le, criteres, cmd_appliquer, cmd_lire, attendu, cmd_retour, classement).
    Chemin : `FORGE_TESTS_REGISTRE_REGLAGES`, sinon la racine du parc (`FORGE_ROOT`, à défaut le
    parent de ce dépôt) puis `digit-ai-factory/references/` ;
  - **l'état de la plateforme**, par la commande `cmd_lire` du registre, LUE SEULEMENT : une
    commande qui écrit (PUT, POST, PATCH, DELETE, corps de requête) est refusée. Les secrets
    (`$NOM`) se lisent dans l'environnement ou `.env.forge-tests`, jamais dans le rapport.

Deux branches, comme le registre les classe :

  - **`defaut`** : l'état lu doit valoir l'attendu du registre ;
  - **`decision`** : l'exigence porte la décision du porteur (`decision.choix` = `applique` ou
    `ecart-accepte`, `decision.valeur_decidee`, `decision.motif`). L'écart accepté est vérifié TEL
    QUE DÉCIDÉ : l'état lu doit valoir la valeur décidée. Un réglage `decision` sans décision
    consignée est un écart nu : constat.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Element, SortieAdaptateur, evaluer_surface

NOM, PAN, SEUIL = "reglages-plateforme", "reglages-plateforme", 1.0

POUR_COUVRIR = (
    "déclarer, pour chaque réglage de plateforme que le produit exige, une entrée d'EXIGENCES.json "
    "portant la clé `reglage_plateforme` (texte du réglage du registre, ou objet avec sa décision "
    "pour un réglage classé `decision`) ; fournir le registre (FORGE_TESTS_REGISTRE_REGLAGES) "
    "et les secrets que sa commande de lecture cite (variables d'environnement ou "
    "`.env.forge-tests`)"
)

CHAPITRES = (
    {"code": "T10", "famille": "technique", "titre": "Réglages de plateforme",
     "decoupe": "reglage", "axe_cas": "unitaire"},
)

NON_JUGE = [
    "reglages-plateforme : l'état lu est celui que la commande `cmd_lire` du registre rend AU "
    "MOMENT de l'audit, avec les droits du jeton fourni ; un jeton qui ne voit pas le réglage rend "
    "une lecture refusée, nommée, jamais un succès",
    "reglages-plateforme : la comparaison à l'attendu est mécanique pour une valeur simple "
    "(`true`, `on`, `enabled`, `0`) et pour « contient a, b et c » ; toute autre forme d'attendu "
    "(plages déclarées, seuils) est lue mais NON COMPARÉE, nommée au non-jugé avec la valeur lue",
    "reglages-plateforme : le registre est une référence datée, sourcée à la date de sa lecture "
    "(`source_lue_le`) ; un réglage dont l'éditeur a changé depuis se lit au registre à jour",
]

_VARIABLE_REGISTRE = "FORGE_TESTS_REGISTRE_REGLAGES"
_FICHIER_REGISTRE = Path("digit-ai-factory") / "references" / "REGLAGES-SURS-PAR-DEFAUT.json"
_CLES_REGISTRE = frozenset({
    "plateforme", "reglage", "source_url", "source_lue_le", "criteres", "cmd_appliquer",
    "cmd_lire", "attendu", "cmd_retour", "classement",
})
_EXIGENCES = ("EXIGENCES.json", "forge/EXIGENCES.json", "forge/etapes/conception/EXIGENCES.json")
_VARIABLE_EXIGENCES = "FORGE_TESTS_EXIGENCES"
_DELAI_LECTURE_S = 60

#: Un geste qui ÉCRIT : verbe HTTP d'écriture, corps de requête, champ de `gh api`. Une commande de
#: lecture n'en porte aucun ; le pan refuse de lancer celle qui en porte un.
_ECRITURE = re.compile(
    r"-X\s*(?:PUT|POST|PATCH|DELETE)\b|--request\s+(?:PUT|POST|PATCH|DELETE)\b"
    r"|\s(?:-d|--data\S*|--input|-f|-F|--field|--raw-field)\s",
    re.IGNORECASE,
)
_VARIABLE = re.compile(r"\$\{?([A-Z][A-Z0-9_]*)\}?")


class RegistreIllisible(ValueError):
    """Le registre des réglages n'est pas exploitable : refus, jamais un registre vide."""


# --- Le registre ----------------------------------------------------------------------------------
def chemins_du_registre(cible: Path) -> list[Path]:
    """Où chercher le registre : variable explicite, racine du parc, parent du dépôt."""
    essais: list[Path] = []
    explicite = (os.environ.get(_VARIABLE_REGISTRE) or "").strip()
    if explicite:
        essais.append(Path(explicite))
    racine = (os.environ.get("FORGE_ROOT") or "").strip()
    if racine:
        essais.append(Path(racine) / _FICHIER_REGISTRE)
    essais.append(Path(__file__).resolve().parents[2].parent / _FICHIER_REGISTRE)
    return essais


def lire_registre(chemin: Path) -> list[dict]:
    try:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        raise RegistreIllisible(
            f"registre des réglages illisible ({chemin}) : {erreur}"
        ) from erreur
    if not isinstance(donnees, list) or not donnees:
        raise RegistreIllisible(f"registre des réglages vide ou mal formé ({chemin})")
    for rang, entree in enumerate(donnees, start=1):
        if not isinstance(entree, dict) or set(entree) != _CLES_REGISTRE:
            raise RegistreIllisible(
                f"entrée {rang} du registre : les clés ne sont pas exactement "
                f"{', '.join(sorted(_CLES_REGISTRE))}"
            )
        if entree["classement"] not in ("defaut", "decision"):
            raise RegistreIllisible(
                f"entrée {rang} du registre : classement {entree['classement']!r} "
                "(defaut ou decision attendu)"
            )
    return donnees


# --- Les exigences de réglage ---------------------------------------------------------------------
def _chemin_exigences(cible: Path) -> Path | None:
    brut = (os.environ.get(_VARIABLE_EXIGENCES) or "").strip()
    if brut:
        return Path(brut)
    for relatif in _EXIGENCES:
        if (cible / relatif).is_file():
            return cible / relatif
    return None


def declares(cible: Path) -> tuple[list[dict], list[str], Path | None]:
    """([{exigence, reglage, plateforme, decision}], notes, fichier) — ce que le produit EXIGE."""
    chemin = _chemin_exigences(cible)
    if chemin is None:
        return [], [], None
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return [], [f"reglages-plateforme : référentiel d'exigences illisible ({erreur})"], chemin
    trouves: list[dict] = []
    liste = donnees.get("exigences") if isinstance(donnees, dict) else None
    for entree in liste if isinstance(liste, list) else []:
        if not isinstance(entree, dict) or not entree.get("reglage_plateforme"):
            continue
        ref = entree["reglage_plateforme"]
        if isinstance(ref, str):
            ref = {"reglage": ref}
        if not isinstance(ref, dict) or not str(ref.get("reglage") or "").strip():
            continue
        trouves.append({
            "exigence": str(entree.get("id") or "?"),
            "reglage": str(ref["reglage"]).strip(),
            "plateforme": str(ref.get("plateforme") or "").strip(),
            "decision": ref.get("decision") if isinstance(ref.get("decision"), dict) else None,
        })
    return trouves, [], chemin


def _norme(texte: str) -> str:
    return re.sub(r"\s+", " ", texte).strip().lower()


def trouver(registre: list[dict], plateforme: str, reglage: str) -> dict | None:
    """L'entrée du registre qui porte ce réglage : texte exact, ou début de texte UNIQUE."""
    voulu = _norme(reglage)
    candidats = [
        e for e in registre
        if (not plateforme or _norme(e["plateforme"]) == _norme(plateforme))
        and _norme(e["reglage"]).startswith(voulu)
    ]
    exacts = [e for e in candidats if _norme(e["reglage"]) == voulu]
    if exacts:
        return exacts[0]
    return candidats[0] if len(candidats) == 1 else None


# --- La lecture -----------------------------------------------------------------------------------
def _valeur_declaree(cible: Path, cle: str) -> str:
    from forge_tests.authentification import ENV_AUDIT, ENV_PROJET, _valeurs

    brut = os.environ.get(cle)
    if brut and brut.strip():
        return brut.strip()
    for fichier in (ENV_PROJET, ENV_AUDIT):
        valeur = _valeurs(Path(cible) / fichier).get(cle, "").strip()
        if valeur:
            return valeur
    return ""


def _executer(commande: str, env: dict[str, str]) -> tuple[int, str, str]:
    """Joue la commande de lecture sous `bash`, les secrets dans l'ENVIRONNEMENT du processus."""
    bash = shutil.which("bash")
    if bash is None:
        return 127, "", "bash introuvable sur cette machine"
    try:
        resultat = subprocess.run(  # noqa: S603 — commande du registre du pilot, lecture seule
            [bash, "-c", commande], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_DELAI_LECTURE_S, env={**os.environ, **env},
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"délai de {_DELAI_LECTURE_S} s dépassé"
    return resultat.returncode, resultat.stdout or "", resultat.stderr or ""


def lire(cible: Path, entree: dict) -> tuple[str | None, str | None]:
    """(valeur lue, None) ou (None, motif de non-lecture). Jamais de secret dans le motif."""
    commande = entree["cmd_lire"]
    if _ECRITURE.search(f" {commande} "):
        return None, "la commande de lecture du registre ÉCRIT (verbe, corps de requête) : refusée"
    if not commande.startswith(("curl", "gh ")):
        return None, "commande de lecture non reconnue (curl ou gh attendus) : non jouée"
    noms = sorted(set(_VARIABLE.findall(commande)))
    valeurs = {nom: _valeur_declaree(cible, nom) for nom in noms}
    absentes = [nom for nom, valeur in valeurs.items() if not valeur]
    if absentes:
        return None, "variable(s) absente(s) : " + ", ".join(absentes)
    code, sortie, erreur = _executer(commande, valeurs)
    if code != 0:
        premiere = (erreur.strip().splitlines() or ["sans message"])[0][:120]
        return None, f"lecture en échec (code {code}) : {premiere}"
    return sortie.strip(), None


# --- La comparaison -------------------------------------------------------------------------------
_SCALAIRE = re.compile(r"^(true|false|on|off|enabled|disabled|\d+)(?:\s*\(.*\))?(?:\s+pour\s+.*)?$",
                       re.IGNORECASE)


def _jeton(texte: str) -> str:
    return texte.strip().strip("\"'").strip().lower()


def evaluer(attendu: str, lu: str) -> tuple[str, str]:
    """('PASS' | 'FAIL' | 'NON_COMPARABLE', détail) — comparaison mécanique, jamais devinée."""
    brut = attendu.strip()
    scalaire = _SCALAIRE.match(brut)
    if scalaire:
        voulu = scalaire.group(1).lower()
        if _jeton(lu) == voulu:
            return "PASS", f"lu « {_jeton(lu)} »"
        return "FAIL", f"lu « {lu.strip()[:80]} », attendu « {voulu} »"
    if brut.lower().startswith("contient "):
        noms = [n for n in re.split(r",|\bet\b", brut[len("contient "):]) if n.strip()]
        manquants = [n.strip() for n in noms if n.strip().lower() not in lu.lower()]
        if manquants:
            return "FAIL", f"lu « {lu.strip()[:120]} », manque : {', '.join(manquants)}"
        return "PASS", "tous les éléments attendus sont présents"
    return "NON_COMPARABLE", f"attendu « {brut[:120]} » : forme non mécanisable"


# --- Le pan ---------------------------------------------------------------------------------------
def _identifiant(exigence: dict) -> str:
    """`reglage:<exigence>:<début du réglage>` — le même, que le registre soit lu ou non."""
    mots = re.sub(r"[^a-z0-9]+", "-", _norme(exigence["reglage"])).strip("-")[:40]
    return f"reglage:{exigence['exigence']}:{mots}"


def _element(exigence: dict, source: str) -> Element:
    return Element(_identifiant(exigence), PAN,
                   f"réglage « {exigence['reglage']} » exigé par {exigence['exigence']}", source)


def inventaire(cible: Path) -> list[Element]:
    exigences, _notes, fichier = declares(cible)
    return [_element(e, str(fichier) if fichier else str(cible)) for e in exigences]


def analyser(cible: Path) -> SortieAdaptateur:
    exigences, notes, fichier = declares(cible)
    if not exigences:
        return evaluer_surface(
            NOM, PAN, str(cible), [], set(), SEUIL, [*NON_JUGE, *notes],
            sans_objet=(
                "aucune exigence de réglage de plateforme (clé `reglage_plateforme` "
                "d'EXIGENCES.json) dans ce projet"
            ),
        )
    registre, chemin_registre = None, None
    essayes = chemins_du_registre(cible)
    for essai in essayes:
        if essai.is_file():
            chemin_registre = essai
            break
    if chemin_registre is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, *notes,
                      "reglages-plateforme : registre des réglages INTROUVABLE — cherché : "
                      + " ; ".join(str(p) for p in essayes)
                      + f". {len(exigences)} exigence(s) de réglage non lue(s)"],
        )
    try:
        registre = lire_registre(chemin_registre)
    except RegistreIllisible as erreur:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*NON_JUGE, *notes, f"reglages-plateforme : {erreur}"],
        )

    elements: list[Element] = []
    exerces: set[str] = set()
    messages: dict[str, tuple[str, str]] = {}
    non_juge = [*NON_JUGE, *notes]
    for exigence in exigences:
        entree = trouver(registre, exigence["plateforme"], exigence["reglage"])
        element_id = _identifiant(exigence)
        elements.append(_element(exigence, str(fichier)))
        if entree is None:
            messages[element_id] = (
                classes.REGLAGE_PLATEFORME_HORS_ATTENDU,
                f"l'exigence {exigence['exigence']} cite un réglage « {exigence['reglage']} » "
                "que le registre ne porte pas (ou en plusieurs exemplaires) : invérifiable",
            )
            continue
        decision = exigence["decision"]
        sans_choix = not decision or not str(decision.get("choix") or "").strip()
        if entree["classement"] == "decision" and sans_choix:
            messages[element_id] = (
                classes.REGLAGE_DECIDE_NON_TENU,
                f"« {entree['reglage']} » (exigence {exigence['exigence']}) est classé "
                "DÉCISION au registre et l'exigence ne consigne aucune décision "
                "(`decision.choix`, `decision.valeur_decidee`, `decision.motif`) : un écart "
                "nu, ni appliqué ni accepté",
            )
            continue
        lu, motif = lire(cible, entree)
        if lu is None:
            non_juge.append(
                f"reglages-plateforme : « {entree['reglage']} » ({exigence['exigence']}) "
                f"NON LU — {motif}"
            )
            elements.pop()
            continue
        a_decide = entree["classement"] == "decision" and decision is not None
        ecart_accepte = a_decide and str(decision.get("choix")) == "ecart-accepte"
        attendu = (
            str(decision.get("valeur_decidee") or "") if ecart_accepte else entree["attendu"]
        )
        if ecart_accepte and not attendu.strip():
            messages[element_id] = (
                classes.REGLAGE_DECIDE_NON_TENU,
                f"« {entree['reglage']} » : écart accepté sans `decision.valeur_decidee` — "
                "il n'y a "
                "rien à vérifier tel que décidé",
            )
            continue
        verdict, detail = evaluer(attendu, lu)
        if verdict == "PASS":
            exerces.add(element_id)
        elif verdict == "NON_COMPARABLE":
            non_juge.append(
                f"reglages-plateforme : « {entree['reglage']} » ({exigence['exigence']}) lu "
                f"« {lu[:120]} » — {detail}"
            )
            elements.pop()
        else:
            classe = (
                classes.REGLAGE_DECIDE_NON_TENU if a_decide
                else classes.REGLAGE_PLATEFORME_HORS_ATTENDU
            )
            cadre = (
                "ÉCART ACCEPTÉ, non tenu tel que décidé" if ecart_accepte
                else "hors de l'attendu du registre"
            )
            messages[element_id] = (
                classe,
                f"« {entree['reglage']} » ({entree['plateforme']}, exigence "
                f"{exigence['exigence']}) {cadre} : {detail}. Application : commande "
                "`cmd_appliquer` du registre ; retour : `cmd_retour`",
            )
    if not elements:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=non_juge + [
            "reglages-plateforme : aucun réglage exigé n'a pu être lu et comparé — "
            f"{len(exigences)} exigence(s) déclarée(s)"])
    sortie = evaluer_surface(NOM, PAN, str(cible), elements, exerces, SEUIL, non_juge)
    for constat in sortie.findings:
        if constat.id in messages:
            constat.classe, constat.message = messages[constat.id]
    return sortie
