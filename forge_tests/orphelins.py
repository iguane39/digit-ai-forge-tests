r"""Un nombre affiché que RIEN du dépôt ne rend — le contrôle, et sa précision MESURÉE.

TF-0665 (détaché de TF-0663, mandat « 2a » du 26/08/2026 ; livré le 02/09/2026).

============================================================================================
LE FAIT
============================================================================================

Sur une page de profil d'un produit servi, la capacité était annoncée à **23 personnes** dans
la méta-description et à **30** dans l'introduction — *sur la même page* —, quand la donnée du
dépôt en donne **22** pour les trois hébergements que ce profil sélectionne. Le nombre **23 ne
correspond à AUCUNE SOURCE du dépôt** : il n'est ni juste, ni une erreur de recopie d'un chiffre
existant. Il n'a pas d'origine.

**Trois contrôles livrés le manquent tous, et chacun pour une raison différente** :

  * la cohérence INTERLANGUE ne le voit pas — les sept langues disent 23, unanimement ;
  * la cohérence INTERNE (TF-0663) ne le voit pas — « personnes » n'est ni une distance ni une
    durée, et cette borne était DÉCLARÉE, pas oubliée ;
  * la confrontation des nombres à la donnée (TF-0644) ne le voit pas — elle ne confronte que
    les **pivots DÉCLARÉS au glossaire**, et la capacité n'en est pas un.

Ce contrôle est d'une autre nature que les trois : ils lisent un catalogue et comparent ; **il
doit RECALCULER depuis la donnée** — la somme des capacités des hébergements que ce profil
sélectionne — donc connaître la sélection.

============================================================================================
LA PRÉCISION EST MESURÉE, ET C'EST ELLE QUI DÉCIDE DE LA FORME DU CONTRÔLE
============================================================================================

Corpus réel d'un produit servi : **4 886 chaînes, 7 locales**, données du dépôt lues.

| Version | Ce qu'elle juge | Accusations | Dont défauts | Précision |
|---|---|---|---|---|
| naïve | tout nombre non trouvé littéralement dans la donnée | **405** | 0 | **0 %** |
| bornée | nombre suivi d'un nom commun, hors heures / années / prix | **67** | 0 | **0 %** |
| ciblée | nombre attaché à un **dénombrable DÉCLARÉ** (« personnes ») | **6** | 0 | **0 %** |

*Un contrôle qui accuse à côté ne se publie pas.* Les trois versions sont à précision nulle sur
ce corpus — mais elles n'échouent pas de la même façon, et l'écart est ce qui rend la suite
actionnable. La version naïve accuse des heures (« de 11 à **22** Uhr »), des prix (« dont
€ **50** de caution ») et des faits éditoriaux tiers (« l'aquarium et ses **600** espèces ») :
elle est irrécupérable. La version ciblée n'accuse plus que **six chaînes, qui sont le MÊME
fait dans six locales** : « Grande pièce de vie avec espace repas (**12** personnes) ». Ce n'est
pas un nombre orphelin, c'est un **dénombrable homonyme** — 12 places à table, pas 12 couchages.

**CE QUI MANQUE POUR LE RENDRE BLOQUANT**, dit précisément parce que le corpus le dit : le
discriminant n'est ni le nombre, ni le nom commun — c'est **le SUJET que le nom qualifie**. Tant
que la déclaration ne porte que « personnes », le contrôle ne peut pas distinguer la capacité
d'un hébergement de celle d'une table. Il faudrait que la déclaration porte la PORTÉE du
dénombrable (quelles clés du catalogue parlent d'hébergement), ou que le catalogue la porte.

**CONSÉQUENCE, ET ELLE EST CÂBLÉE** : le contrôle vit derrière `FORGE_TESTS_ORPHELINS=1`,
**absent par défaut** (loi transverse n° 2). Sans le drapeau, il compte, mesure et **DÉCLARE**
ses candidats en `non_juge` — jamais un finding. Avec le drapeau, il émet des findings
`signale`, jamais bloquants. Ce qu'il ne fait dans aucun des deux cas : se taire.

============================================================================================
CE QU'IL SAIT RECALCULER
============================================================================================

Les valeurs qu'un dépôt REND, pour un champ numérique donné :

  * la valeur elle-même, par enregistrement (`capMax(familial)` = 10) ;
  * la **somme**, le **compte**, le **min** et le **max** sur l'ensemble ;
  * la **somme et le compte sur chaque SÉLECTION DÉCLARÉE** — c'est le point dur de l'item, et
    c'est ce qui fait la différence entre « 22 est juste » et « 22 n'existe nulle part ».

Sur le cas fondateur, la table rendue vaut : 2, 6, 8 (sélection couple), 10, 22 (les trois
sélections à trois hébergements), 30 (les cinq). **23 n'y est pas** — et 30, 22 et 10 y sont.

Déclaration : `FORGE_TESTS_DENOMBRABLES` (défaut `docs/projet/DENOMBRABLES.json`) —
`{"<nom>": {"champ": "capMax", "termes": {"fr": "personnes", …},
            "selections": {"seminaire": ["familial", "saloon", "j2"], …}}}`.
Données : `FORGE_TESTS_DONNEES` (chemins séparés par une virgule, relatifs au projet).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

VARIABLE_DENOMBRABLES = "FORGE_TESTS_DENOMBRABLES"
VARIABLE_DONNEES = "FORGE_TESTS_DONNEES"
VARIABLE_ACTIF = "FORGE_TESTS_ORPHELINS"

#: Précision mesurée le 02/09/2026 sur le corpus réel décrit en tête. C'est le seul chiffre qui
#: autorise ou refuse une publication bloquante — écrit ici, jamais recopié ailleurs (loi 4).
PRECISION_MESUREE = 0.0
#: Au-dessous de ce seuil, le contrôle ne peut pas être bloquant. Il est écrit pour que le jour
#: où la précision est remesurée, la comparaison soit mécanique et non un souvenir.
SEUIL_PRECISION_BLOQUANTE = 0.80

#: Un objet littéral PLAT — les enregistrements de données en sont (`{ slug: 'x', capMax: 6 }`).
#: Les objets à accolades imbriquées ne sont pas lus : le dire coûte moins cher que de les lire
#: mal, et un enregistrement mal découpé fabriquerait des sommes fausses.
_OBJET = re.compile(r"\{([^{}]*)\}", re.DOTALL)
#: `champ: 12` ou `"champ": 12` — les deux dialectes, JS et JSON.
_CHAMP_NOMBRE = re.compile(r"[\"']?([A-Za-z_$][\w$]*)[\"']?\s*:\s*(-?\d+)(?![\w.])")
#: La clé qui NOMME l'enregistrement. Sans elle, une sélection déclarée ne peut rien désigner.
_CHAMP_CLE = re.compile(r"[\"']?(slug|key|cle|id|nom|name)[\"']?\s*:\s*[\"']([^\"']+)[\"']")


def lire_declaration(chemin: Path | str | None) -> dict:
    """Les dénombrables déclarés par le produit. Ne lève jamais : un motif remplace un silence."""
    if not chemin:
        return {"denombrables": {}, "motif": f"aucun dénombrable déclaré ({VARIABLE_DENOMBRABLES})"}
    p = Path(chemin)
    if not p.exists():
        return {"denombrables": {}, "motif": f"dénombrables déclarés absents : {p}"}
    try:
        brut = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        return {"denombrables": {}, "motif": f"dénombrables illisibles : {erreur}"}
    if not isinstance(brut, dict):
        return {"denombrables": {}, "motif": f"{p} : un objet `{{nom: definition}}` est attendu"}
    retenus, ignores = {}, []
    for nom, definition in brut.items():
        if (
            isinstance(definition, dict)
            and isinstance(definition.get("champ"), str)
            and isinstance(definition.get("termes"), dict)
            and definition["termes"]
        ):
            retenus[str(nom)] = definition
        else:
            ignores.append(str(nom))
    motif = (
        f"{len(ignores)} dénombrable(s) ignoré(s), `champ` ou `termes` manquant : "
        f"{', '.join(ignores[:5])}"
        if ignores
        else None
    )
    return {"denombrables": retenus, "motif": motif}


def chemin_declaration(cible: Path) -> str | None:
    """Le chemin déclaré, sinon la convention — et None si la convention n'existe pas ici."""
    declare = (os.environ.get(VARIABLE_DENOMBRABLES) or "").strip()
    if declare:
        return declare
    defaut = Path(cible) / "docs" / "projet" / "DENOMBRABLES.json"
    return str(defaut) if defaut.exists() else None


def fichiers_de_donnees(cible: Path) -> list[Path]:
    """Les fichiers de DONNÉES du produit — déclarés, jamais devinés.

    Deviner serait ici particulièrement coûteux : un fichier de données manquant ne rend pas le
    contrôle muet, il le rend ACCUSATEUR — tout ce que ce fichier rendait devient orphelin.
    """
    declare = (os.environ.get(VARIABLE_DONNEES) or "").strip()
    if not declare:
        return []
    trouves: list[Path] = []
    for morceau in declare.replace(os.pathsep, ",").split(","):
        brut = morceau.strip()
        if not brut:
            continue
        chemin = Path(brut)
        candidat = chemin if chemin.is_absolute() else Path(cible) / chemin
        if candidat.is_file():
            trouves.append(candidat)
        elif any(c in brut for c in "*?["):
            trouves.extend(sorted(p for p in Path(cible).glob(brut) if p.is_file()))
    return trouves


def enregistrements(fichiers: list[Path]) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Les enregistrements lus : `{clé : {champ : nombre}}`, plus ce qu'on n'a pas su nommer.

    Un objet sans clé nommante entre quand même, sous une clé de POSITION : ses valeurs comptent
    pour les agrégats globaux, elles ne peuvent simplement pas être visées par une sélection.
    """
    lus: dict[str, dict[str, int]] = {}
    anonymes: list[str] = []
    for fichier in fichiers:
        try:
            texte = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError as erreur:
            anonymes.append(f"{fichier.name} illisible : {erreur}")
            continue
        for rang, corps in enumerate(_OBJET.findall(texte)):
            nombres = {champ: int(valeur) for champ, valeur in _CHAMP_NOMBRE.findall(corps)}
            if not nombres:
                continue
            nomme = _CHAMP_CLE.search(corps)
            cle = nomme.group(2) if nomme else f"{fichier.stem}#{rang}"
            if not nomme:
                anonymes.append(cle)
            lus[cle] = {**lus.get(cle, {}), **nombres}
    return lus, anonymes


def valeurs_rendues(
    lus: dict[str, dict[str, int]], champ: str, selections: dict[str, list[str]] | None = None
) -> dict[int, list[str]]:
    """Tout ce que le dépôt sait RENDRE pour ce champ : valeurs, agrégats, sommes par sélection.

    Fonction pure. C'est le cœur de l'item : sans les sommes par SÉLECTION, « 22 » — la capacité
    des trois hébergements d'un profil — n'existe nulle part et le contrôle l'accuserait.
    """
    table: dict[int, list[str]] = {}

    def _poser(valeur: int, origine: str) -> None:
        table.setdefault(valeur, []).append(origine)

    portant = {cle: nombres[champ] for cle, nombres in lus.items() if champ in nombres}
    for cle, valeur in sorted(portant.items()):
        _poser(valeur, f"{champ}({cle})")
    if portant:
        valeurs = list(portant.values())
        _poser(sum(valeurs), f"somme({champ}) sur {len(valeurs)} enregistrement(s)")
        _poser(len(valeurs), f"compte({champ})")
        _poser(min(valeurs), f"min({champ})")
        _poser(max(valeurs), f"max({champ})")
    for nom, cles in sorted((selections or {}).items()):
        retenues = [portant[c] for c in cles if c in portant]
        if not retenues:
            continue
        _poser(sum(retenues), f"somme({champ}) sur la sélection « {nom} »")
        _poser(len(retenues), f"compte({champ}) sur la sélection « {nom} »")
    return table


#: Un nombre ATTACHÉ à un dénombrable : le nombre, au plus un mot intercalé, puis le terme. Le
#: mot intercalé couvre « 30 à 40 personnes » et « 12 grandes personnes » sans ouvrir la fenêtre
#: au point de rapprocher deux propositions différentes.
def _motif_attache(terme: str) -> re.Pattern[str]:
    mot = re.escape(terme.strip().strip("`"))
    return re.compile(
        rf"(?<![\w.,:/€$£%-])(\d{{1,4}})\s+(?:[\wÀ-ÿ'’-]+\s+)?{mot}\w{{0,2}}(?![\wÀ-ÿ])",
        re.IGNORECASE | re.UNICODE,
    )


_BALISES = re.compile(r"<[^>]+>")


def confronter(
    par_locale: dict[str, dict[str, str]],
    denombrable: dict,
    rendues: dict[int, list[str]],
) -> dict:
    """Les nombres attachés à ce dénombrable, et ceux que RIEN du dépôt ne rend.

    Rend toujours les DEUX comptes — `juges` et `orphelins`. Publier les seuls orphelins ferait
    lire « 6 accusations » sans jamais dire sur combien : c'est-à-dire sans précision, donc sans
    moyen de décider si le contrôle est publiable.
    """
    juges = 0
    orphelins: list[dict] = []
    motifs = {loc: _motif_attache(terme) for loc, terme in denombrable["termes"].items() if terme}
    for locale, plat in sorted(par_locale.items()):
        motif = motifs.get(locale)
        if motif is None:
            continue
        for cle, valeur in sorted(plat.items()):
            if not isinstance(valeur, str):
                continue
            texte = _BALISES.sub(" ", valeur)
            for trouve in motif.finditer(texte):
                vu = int(trouve.group(1))
                juges += 1
                if vu in rendues:
                    continue
                orphelins.append({
                    "locale": locale,
                    "cle": cle,
                    "vu": vu,
                    "terme": denombrable["termes"][locale],
                    "extrait": texte.strip()[:120],
                })
    return {"juges": juges, "orphelins": orphelins}


def actif() -> bool:
    """Loi transverse n° 2 : la voie neuve vit derrière un drapeau ABSENT par défaut, tant que
    la précision mesurée reste sous `SEUIL_PRECISION_BLOQUANTE`."""
    return (os.environ.get(VARIABLE_ACTIF) or "").strip() in {"1", "oui", "true"}


NON_JUGE = [
    "orphelins : la PRECISION de ce controle est MESUREE, et elle est de 0 % sur le corpus reel "
    "de 4 886 chaines sur lequel il a ete eprouve — 6 accusations, aucune n etant un defaut. Il "
    "vit donc derriere FORGE_TESTS_ORPHELINS=1, ABSENT PAR DEFAUT : sans le drapeau il compte, "
    "mesure et DECLARE ses candidats, il n emet aucun finding. Le seuil de publication bloquante "
    "est de 80 %",
    "orphelins : les six accusations mesurees sont le MEME fait dans six locales — « grande piece "
    "de vie avec espace repas (12 personnes) ». Ce n est pas un nombre orphelin, c est un "
    "DENOMBRABLE HOMONYME : 12 places a table, pas 12 couchages. Le discriminant n est donc ni le "
    "nombre ni le nom commun, c est le SUJET que le nom qualifie — et la declaration ne le porte "
    "pas. C est ce qui manque pour rendre le controle bloquant",
    "orphelins : sans DECLARATION de denombrables, le controle ne juge rien. La version naive "
    "(tout nombre absent de la donnee) a ete mesuree sur le meme corpus : 405 accusations, "
    "0 defaut — elle accuse des heures, des prix et des faits editoriaux tiers. Elle est REFUSEE, "
    "pas remise a plus tard",
    "orphelins : les fichiers de donnees sont DECLARES (FORGE_TESTS_DONNEES), jamais devines. Un "
    "fichier de donnees oublie ne rend pas ce controle muet, il le rend ACCUSATEUR — tout ce que "
    "ce fichier rendait deviendrait orphelin",
    "orphelins : seuls les objets litteraux PLATS sont lus comme enregistrements. Un objet a "
    "accolades imbriquees n est pas decoupe, donc ses valeurs n entrent dans aucun agregat — un "
    "enregistrement mal decoupe fabriquerait des sommes fausses, ce qui est pire qu un manque",
    "orphelins : un nombre ECRIT EN LETTRES, ou attache au denombrable par plus d un mot "
    "intercale, n est pas vu. Elargir la fenetre rapprocherait deux propositions differentes",
]
