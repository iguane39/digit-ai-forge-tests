r"""Lire le GLOSSAIRE d'un projet multilingue, et confronter les NOMBRES servis à la donnée.

TF-0644 (lot AuxPortesDeLaBaie 20260825f, 26/08/2026), décision humaine « voie (b) ».

============================================================================================
LE FAIT, ET IL EST PARTI EN PRODUCTION
============================================================================================

La méta-description d'une page de réservation annonçait « 8 gîtes » **dans les sept langues,
français compris**, quand la donnée du produit en déclare **5**. Résidu du retrait de deux gîtes :
le run avait mis à jour l'intégralité du site sauf cette chaîne — dans toutes les locales à la
fois.

**NEUF contrôles projet ne l'ont pas vu**, dont un pan i18n complet et un audit SEO de 88 nœuds.
Aucun ne compare un nombre écrit dans une chaîne à la donnée dont il dérive.

**ET LA COMPARAISON ENTRE LOCALES N'AURAIT RIEN VU NON PLUS** — c'est ce qui rend une déclaration
nécessaire plutôt que commode. Les sept locales disaient toutes « 8 » : elles étaient parfaitement
*cohérentes entre elles*, et toutes fausses. Un contrôle qui prend la majorité pour référence,
comme le fait déjà ce pan pour les paramètres, aurait rendu PASS. Il faut un point fixe HORS du
catalogue.

============================================================================================
POURQUOI CE MODULE LIT UN MARKDOWN, ET CE QUE ÇA COÛTE
============================================================================================

Confronter « 8 gîtes » à la donnée demande deux choses : **le nombre**, que seul le produit
connaît, et **le nom dénombrable par locale** — sans quoi « 8 gîtes » en français et « 8 cottages »
en anglais ne se rapprochent pas.

Le second vit déjà dans `docs\projet\GLOSSAIRE.md`, le glossaire prescrit par R-53 du pilot : un
terme par section, une ligne par locale, avec le terme retenu. **Décision humaine du 26/08, voie
(b)** : ce module le LIT plutôt que de faire redéclarer les termes ailleurs — une donnée, un seul
endroit.

**LE COÛT DE CETTE VOIE EST RÉEL ET IL EST ASSUMÉ** : il existe désormais DEUX analyseurs du même
format, celui-ci en Python et `oracles\oracle-glossaire.mjs` en JavaScript chez le pilot. C'est la
classe de défaut qui a coûté dix listes d'exclusion divergentes (TF-0543). La contrepartie est
**câblée, pas promise** : `tests\test_tf_0644_glossaire.py` fait lire à CE parseur le gabarit de
référence du pilot et vérifie qu'il y retrouve ce que l'autre y voit. Si le format dérive d'un
côté, la recette rougit ici. Quand le gabarit n'est pas atteignable, le cas est DÉCLARÉ non joué —
jamais tenu pour vert par omission.

============================================================================================
CE QUI EST JUGÉ, ET CE QUI NE PEUT PAS L'ÊTRE
============================================================================================

Un écart est rendu quand une chaîne servie porte un nombre suivi du terme retenu de sa locale, et
que ce nombre diffère du fait déclaré. Rien d'autre n'est affirmé : ce module ne sait pas si la
phrase parle du produit, ni si le fait déclaré est juste.

Variables d'environnement :
  FORGE_TESTS_GLOSSAIRE  chemin du glossaire (défaut : `docs/projet/GLOSSAIRE.md` du projet)
  FORGE_TESTS_FAITS      chemin d'un JSON `{"<pivot>": <nombre>}` — la donnée du produit
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: Les colonnes du tableau d'un terme, dans l'ordre où le gabarit du pilot les pose.
COLONNES = ("locale", "retenu", "proscrits", "portee", "preuve", "verifie_le")

_CHAMP = re.compile(r"^\s*-\s+\*\*(categorie|pivot)\*\*\s*:\s*(.+?)\s*$", re.IGNORECASE)
_TITRE = re.compile(r"^##\s+(.+?)\s*$")

#: Un nombre écrit en chiffres, éventuellement avec un séparateur de milliers.
_NOMBRE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[   ]\d{3})*|\d+)(?![\w.,]*\d)")


def lire(chemin: Path | str) -> dict:
    """Le glossaire, découpé en TERMES. Ne lève jamais : un fichier absent rend un motif.

    Retourne `{"termes": [...], "motif": None}` ou `{"termes": [], "motif": "<pourquoi>"}` —
    « je ne sais pas lire » et « il n'y a rien à lire » ne se confondent pas, c'est la même
    distinction que le pan tient déjà pour les catalogues non lus.
    """
    p = Path(chemin)
    if not p.exists():
        return {"termes": [], "motif": f"glossaire absent : {p}"}
    try:
        texte = p.read_text(encoding="utf-8")
    except OSError as erreur:
        return {"termes": [], "motif": f"glossaire illisible : {erreur}"}

    # LA BORNE, la même que celle de l'oracle du pilot : un fichier qui ne se déclare pas
    # glossaire n'en est pas un, et le lire comme tel inventerait des termes.
    entete = re.match(r"^---\r?\n(.*?)\r?\n---", texte, re.DOTALL)
    if not entete or not re.search(r"^role\s*:.*(glossaire|terminologie)", entete.group(1),
                                   re.IGNORECASE | re.MULTILINE):
        return {"termes": [], "motif": f"{p} ne déclare pas `role:` … glossaire/terminologie"}

    termes: list[dict] = []
    courant: dict | None = None
    for brute in texte.splitlines():
        titre = _TITRE.match(brute)
        if titre:
            if courant:
                termes.append(courant)
            courant = {"nom": titre.group(1), "categorie": None, "pivot": None, "lignes": []}
            continue
        if courant is None:
            continue
        champ = _CHAMP.match(brute)
        if champ:
            courant[champ.group(1).lower()] = champ.group(2).strip()
            continue
        if brute.lstrip().startswith("|"):
            cellules = [c.strip() for c in brute.strip().strip("|").split("|")]
            if len(cellules) != len(COLONNES):
                continue
            if cellules[0].lower() == "locale":
                continue
            if set(cellules[0].replace(":", "").replace(" ", "")) <= {"-"}:
                continue
            courant["lignes"].append(dict(zip(COLONNES, cellules)))
    if courant:
        termes.append(courant)
    # Seules les sections qui portent une `categorie` sont des TERMES : les sections de doctrine
    # du gabarit n'en sont pas, et les lire comme tels inventerait du vocabulaire.
    return {"termes": [t for t in termes if t["categorie"]], "motif": None}


def faits_declares(chemin: Path | str | None) -> dict:
    """Les faits chiffrés du produit : `{"<pivot>": <nombre>}`. Ne lève jamais."""
    if not chemin:
        return {"faits": {}, "motif": "aucun fait déclaré (FORGE_TESTS_FAITS non renseigné)"}
    p = Path(chemin)
    if not p.exists():
        return {"faits": {}, "motif": f"faits déclarés absents : {p}"}
    try:
        brut = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return {"faits": {}, "motif": f"faits déclarés illisibles : {erreur}"}
    if not isinstance(brut, dict):
        return {"faits": {}, "motif": f"{p} : un objet `{{pivot: nombre}}` est attendu"}
    faits = {str(k): v for k, v in brut.items() if isinstance(v, int)}
    ignores = sorted(set(brut) - set(faits))
    motif = (f"{len(ignores)} fait(s) ignoré(s), valeur non entière : {', '.join(ignores[:5])}"
             if ignores else None)
    return {"faits": faits, "motif": motif}


def _formes(retenu: str) -> list[str]:
    """Les formes d'un terme à chercher dans une chaîne : le mot, plus un pluriel court.

    LA LIMITE EST ASSUMÉE ET DÉCLARÉE. Un pluriel se forme différemment dans chaque langue, et
    inventer une morphologie par locale serait affirmer ce que la donnée ne porte pas. On cherche
    donc le terme retenu suivi d'au plus DEUX caractères de mot — ce qui couvre `-s`, `-es`, `-en`,
    `-i`, et laisse passer les pluriels irréguliers. Un pluriel irrégulier n'est pas vu : c'est un
    manque, pas une erreur, et il est écrit au `non_juge`.
    """
    mot = re.escape(retenu.strip().strip("`"))
    return [rf"{mot}\w{{0,2}}\b"]


def confronter(par_locale: dict[str, dict[str, str]], termes: list[dict],
               faits: dict[str, int]) -> list[dict]:
    """Les écarts entre un nombre servi et le fait déclaré, chaîne par chaîne.

    Un écart n'est rendu que si TOUT est réuni : un pivot déclaré comme fait, une locale qui a un
    terme retenu, une chaîne où ce terme suit immédiatement un nombre, et un nombre différent.
    Chaque condition manquante rend SILENCE, jamais un verdict.
    """
    ecarts: list[dict] = []
    for terme in termes:
        pivot = (terme.get("pivot") or "").strip()
        if pivot not in faits:
            continue
        attendu = faits[pivot]
        for ligne in terme["lignes"]:
            locale = ligne["locale"].strip()
            retenu = (ligne.get("retenu") or "").strip().strip("`")
            plat = par_locale.get(locale)
            if not plat or not retenu:
                continue
            motifs = [re.compile(rf"{_NOMBRE.pattern}\s+(?:\w+\s+){{0,1}}{forme}",
                                 re.IGNORECASE | re.UNICODE) for forme in _formes(retenu)]
            for cle, valeur in sorted(plat.items()):
                if not isinstance(valeur, str):
                    continue
                for motif in motifs:
                    for trouve in motif.finditer(valeur):
                        brut = re.sub(r"[   ]", "", trouve.group(1))
                        if not brut.isdigit():
                            continue
                        vu = int(brut)
                        if vu == attendu:
                            continue
                        ecarts.append({
                            "locale": locale,
                            "cle": cle,
                            "pivot": pivot,
                            "terme": retenu,
                            "vu": vu,
                            "attendu": attendu,
                            "extrait": valeur.strip()[:120],
                        })
    return ecarts


def chemin_glossaire(cible: Path) -> Path:
    """Le glossaire du projet : la variable d'environnement, sinon le chemin prescrit par R-53."""
    declare = os.environ.get("FORGE_TESTS_GLOSSAIRE")
    return Path(declare) if declare else Path(cible) / "docs" / "projet" / "GLOSSAIRE.md"


def chemin_faits(cible: Path) -> str | None:
    """Le fichier de faits chiffrés — déclaré, jamais deviné : seul le produit connaît sa donnée."""
    declare = os.environ.get("FORGE_TESTS_FAITS")
    if declare:
        return declare
    defaut = Path(cible) / "docs" / "projet" / "FAITS.json"
    return str(defaut) if defaut.exists() else None


NON_JUGE = [
    "glossaire : la JUSTESSE d un fait declare n est pas jugee. Ce module confronte une chaine a "
    "un nombre DECLARE par le produit ; si la declaration est fausse, l ecart rendu est faux dans "
    "l autre sens. C est un point fixe assume, pas une verite mesuree",
    "glossaire : un PLURIEL IRREGULIER n est pas vu. Le terme retenu est cherche suivi d au plus "
    "deux caracteres de mot — ce qui couvre -s, -es, -en, -i. Inventer une morphologie par locale "
    "serait affirmer ce que la donnee ne porte pas ; le manque est donc declare plutot que comble "
    "au jugé",
    "glossaire : un nombre ECRIT EN LETTRES (« huit gites ») n est pas vu. Le lexique des nombres "
    "varie par langue et le deduire du glossaire n a pas de sens",
    "glossaire : la comparaison ENTRE LOCALES ne remplace pas cette confrontation et c est mesure "
    "— le defaut fondateur disait « 8 » dans les SEPT langues, parfaitement coherent entre locales "
    "et integralement faux. Il faut un point fixe HORS du catalogue",
]
