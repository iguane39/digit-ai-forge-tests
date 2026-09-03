r"""Lire le GLOSSAIRE d'un projet multilingue, et confronter les NOMBRES servis à la donnée.

TF-0644 (lot Produit-02 20260825f, 26/08/2026), décision humaine « voie (b) ».

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

#: `genre` est une SEPTIÈME colonne, OPTIONNELLE (TF-0660). Un glossaire écrit avant le 26/08
#: n'en porte pas et reste valide : c'est la règle qui a bougé, pas le dépôt.
COLONNE_GENRE = "genre"

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
    illisibles: list[tuple] = []
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
            # SIX colonnes, ou SEPT avec `genre`. Une AUTRE largeur n'est pas sautée en
            # silence : le silence d'une sonde n'est pas un verdict, et une ligne ignorée
            # sans mot dire fait rendre PASS à un tableau que l'oracle du pilot, lui,
            # refuse bruyamment. Les deux analyseurs doivent être d'accord sur ce point.
            if len(cellules) not in (len(COLONNES), len(COLONNES) + 1):
                illisibles.append((courant["nom"], len(cellules)))
                continue
            if cellules[0].lower() == "locale":
                continue
            if set(cellules[0].replace(":", "").replace(" ", "")) <= {"-"}:
                continue
            # `strict=False` ASSUMÉ : une ligne à 7 colonnes (avec `genre`) est légitime et
            # se complète juste après — une paire stricte la rejetterait au lieu de la lire.
            ligne = dict(zip(COLONNES, cellules, strict=False))
            if len(cellules) == len(COLONNES) + 1:
                ligne[COLONNE_GENRE] = cellules[len(COLONNES)]
            courant["lignes"].append(ligne)
    if courant:
        termes.append(courant)
    # Seules les sections qui portent une `categorie` sont des TERMES : les sections de doctrine
    # du gabarit n'en sont pas, et les lire comme tels inventerait du vocabulaire.
    motif = None
    if illisibles:
        detail = " · ".join(f"{n} ({v} colonnes)" for n, v in illisibles[:4])
        motif = (f"{len(illisibles)} ligne(s) de tableau à largeur inattendue, DONC NON "
                 f"LUES : {detail}. Six colonnes attendues, sept avec `genre`")
    return {"termes": [t for t in termes if t["categorie"]], "motif": motif}


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


def _occurrences(plat: dict[str, str], mot: str) -> int:
    """Combien de fois `mot` apparaît dans les chaînes servies d'une locale.

    Comparaison insensible à la casse, bornée aux frontières de mot quand la langue le permet.
    On ne cherche PAS une forme fléchie : un terme employé au pluriel uniquement compterait zéro,
    et c'est déclaré au `non_juge` plutôt que deviné par une morphologie inventée par langue.
    """
    if not mot:
        return 0
    motif = re.compile(rf"(?<!\w){re.escape(mot)}\w{{0,2}}(?!\w)", re.IGNORECASE | re.UNICODE)
    return sum(len(motif.findall(v)) for v in plat.values() if isinstance(v, str))


def confronter_emploi(par_locale: dict[str, dict[str, str]], termes: list[dict]) -> list[dict]:
    """Le terme RETENU est-il réellement employé, ou le proscrit règne-t-il encore ?

    ============================================================================================
    POURQUOI CE CONTRÔLE EST DUR ET NON CONDITIONNEL (TF-0656, 26/08/2026)
    ============================================================================================

    LE FAIT, mesuré sur un produit et parti EN PRODUCTION. Un contrôle de glossaire rendait
    « glossaire OK — 8 termes × 7 langues, aucun écart », puis listait À PART dix règles « non
    jugé — à relire à l'œil ». Trois d'entre elles portaient le terme d'hébergement en `de`, `es`
    et `pt`. Mesure : le terme RETENU y était employé **zéro** fois, quand le mot qu'il devait
    remplacer l'était **82, 79 et 82** fois. Le glossaire avait été corrigé la veille, motif rédigé
    et sonde citée ; les chaînes n'ont jamais suivi. Aucun œil ne l'a relu — l'audit du lendemain
    l'a trouvé en une commande.

    LE POINT N'EST PAS QUE LA RÈGLE SOIT CONDITIONNELLE, c'est qu'elle soit MESURABLE et qu'on la
    délègue quand même. *Un terme retenu à zéro emploi dans une langue où le concept est employé 82
    fois est un échec, pas une nuance* : aucune information supplémentaire n'est nécessaire pour
    trancher, donc ce n'est pas un arbitrage.

    CE QUI DÉCLENCHE, ET RIEN DE PLUS : le retenu à ZÉRO **et** un proscrit employé au moins une
    fois. Les deux conditions ensemble, parce que chacune seule serait fausse — un retenu à zéro
    dans une locale qui ne parle pas du concept n'est pas un défaut, et un proscrit employé à côté
    d'un retenu employé peut être une citation ou un titre d'œuvre.
    """
    ecarts: list[dict] = []
    for terme in termes:
        for ligne in terme["lignes"]:
            locale = ligne["locale"].strip()
            plat = par_locale.get(locale)
            if not plat:
                continue
            retenu = (ligne.get("retenu") or "").strip().strip("`")
            if not retenu:
                continue
            vus_retenu = _occurrences(plat, retenu)
            if vus_retenu:
                continue
            # Le mot proscrit s'écrit entre accents graves : c'est la convention du gabarit, et
            # c'est ce qui le distingue de la glose qui l'explique.
            for proscrit in re.findall(r"`([^`]+)`", ligne.get("proscrits") or ""):
                vus_proscrit = _occurrences(plat, proscrit.strip())
                if not vus_proscrit:
                    continue
                ecarts.append({
                    "locale": locale,
                    "pivot": (terme.get("pivot") or "").strip(),
                    "retenu": retenu,
                    "proscrit": proscrit.strip(),
                    "vus_proscrit": vus_proscrit,
                })
    return ecarts


#: Un fait chiffré attaché à un NOM PROPRE : « Granville … 45 minutes ». Le nom propre est ce qui
#: rend deux affirmations comparables — sans lui, « 3 chambres » et « 2 chambres » parlent de deux
#: logements différents et les rapprocher serait inventer une contradiction.
_FAIT_NOMME = re.compile(
    r"(?<![\w'’])([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][\wÀ-ÿ'’-]{2,})[^.;!?\n]{0,60}?"
    r"(?<![\w.,])(\d{1,4})\s*(minutes?|min\b|heures?|h\b|km\b|kilom[èe]tres?|m\b|m[èe]tres?)",
    re.UNICODE,
)


#: Les DÉTERMINANTS, par locale et par genre. C'est une classe FERMÉE — quelques dizaines de
#: mots énumérables —, et c'est précisément ce qui rend le contrôle publiable. La règle large
#: (« tout mot en -o/-os dans une chaîne portant un terme féminin ») a été MESURÉE sur le corpus
#: réel d'un produit : 268 accusations, à précision ~0 — `minutos`, `seminarios`, `invierno`,
#: `carro` sont des noms masculins parfaitement légitimes. Un suffixe ne distingue pas
#: `adaptados` (participe, faux) de `descuentos` (nom, juste). Elle a donc été REFUSÉE.
DETERMINANTS = {
    "es": {"m": ["el", "los", "un", "unos", "ningún", "ninguno", "otro", "otros", "todo",
                 "todos", "algún", "alguno", "algunos", "este", "estos", "ese", "esos",
                 "aquel", "aquellos", "nuestro", "nuestros", "mucho", "muchos", "poco",
                 "pocos", "tanto", "tantos", "cuánto", "mismo", "mismos"],
           "f": ["la", "las", "una", "unas", "ninguna", "otra", "otras", "toda", "todas",
                 "alguna", "algunas", "esta", "estas", "esa", "esas", "aquella", "aquellas",
                 "nuestra", "nuestras", "mucha", "muchas", "poca", "pocas", "tanta",
                 "tantas", "cuánta", "misma", "mismas"]},
    "pt": {"m": ["o", "os", "um", "uns", "nenhum", "nenhuns", "outro", "outros", "todo",
                 "todos", "algum", "alguns", "este", "estes", "esse", "esses", "aquele",
                 "aqueles", "nosso", "nossos", "muito", "muitos", "pouco", "poucos",
                 "tanto", "tantos", "mesmo", "mesmos"],
           "f": ["a", "as", "uma", "umas", "nenhuma", "nenhumas", "outra", "outras", "toda",
                 "todas", "alguma", "algumas", "esta", "estas", "essa", "essas", "aquela",
                 "aquelas", "nossa", "nossas", "muita", "muitas", "pouca", "poucas",
                 "tanta", "tantas", "mesma", "mesmas"]},
    "it": {"m": ["il", "lo", "i", "gli", "un", "uno", "nessun", "nessuno", "altro", "altri",
                 "tutto", "tutti", "questo", "questi", "quello", "quegli", "nostro",
                 "nostri", "molto", "molti", "poco", "pochi", "tanto", "tanti"],
           "f": ["la", "le", "una", "un'", "nessuna", "altra", "altre", "tutta", "tutte",
                 "questa", "queste", "quella", "quelle", "nostra", "nostre", "molta",
                 "molte", "poca", "poche", "tanta", "tante"]},
    "fr": {"m": ["le", "un", "ce", "cet", "tout", "tous", "aucun", "notre", "nos", "quel",
                 "quels", "chaque", "certains", "plusieurs", "mon", "son"],
           "f": ["la", "une", "cette", "toute", "toutes", "aucune", "quelle", "quelles",
                 "certaines", "ma", "sa"]},
}

#: Le genre déclaré, ramené à `m` / `f`. `n` et `invariable` ne sont PAS jugés : le contrôle
#: repose sur une opposition binaire de déterminants, et l'allemand ou l'anglais n'entrent pas
#: dans ce moule. Déclarer ce qu'on ne juge pas coûte moins cher que de le juger mal.
_GENRES_JUGES = ("m", "f")

_ACCENTS = str.maketrans("áàâäéèêëíìîïóòôöúùûüçãõñ", "aaaaeeeeiiiioooouuuucaon")


def _sans_accents(mot: str) -> str:
    return mot.translate(_ACCENTS)


def _avec_variantes(mots: list[str]) -> list[str]:
    """Chaque déterminant, plus sa forme sans accents — « NINGÚN » et « Ningun » se valent.

    Le corpus servi n'est pas garanti accentué : un catalogue peut porter les deux formes, et
    un contrôle qui n'en voit qu'une se tait sur l'autre en silence.
    """
    return sorted({m for mot in mots for m in (mot, _sans_accents(mot))})


DETERMINANTS = {loc: {g: _avec_variantes(mots) for g, mots in genres.items()}
                for loc, genres in DETERMINANTS.items()}

# LE GARDE QUI REND CETTE EXPANSION SÛRE. Retirer les accents peut faire se rejoindre deux mots
# de genres OPPOSÉS — et le contrôle accuserait alors une phrase juste. La mesure de TF-0660 a
# vu exactement ce piège une fois : en portugais, `é` (copule) écrasé sur `e` (« et ») avait
# produit quatre accusations, toutes fausses. Ici la collision est VÉRIFIÉE, pas espérée.
for _loc, _g in DETERMINANTS.items():
    _collision = set(_g["m"]) & set(_g["f"])
    if _collision:                                                       # pragma: no cover
        raise AssertionError(
            f"locale {_loc} : {sorted(_collision)} appartiennent aux DEUX genres une fois "
            "les accents retirés — le contrôle d'accord accuserait des phrases justes")



def confronter_genre(par_locale: dict, termes: list[dict]) -> list[dict]:
    """Un DÉTERMINANT resté au genre d'origine, COLLÉ devant le terme retenu. TF-0660.

    LE FAIT. Onze fautes d'accord — cinq en espagnol, cinq en portugais — sont parties EN
    PRODUCTION derrière une CI verte et six contrôleurs au vert. Le run avait substitué le
    terme d'hébergement : `gîte` (m.) devient `casa rural` (f.), `casa de férias` (f.). Les
    accords ADJACENTS au nom ont été traités par la passe de substitution ; ceux qui en
    étaient SÉPARÉS DE PLUSIEURS MOTS ont survécu — « NINGÚN casa rural disponible »,
    « 1 OTRO casa rural … ya está RESERVADO ».

    Aucun contrôleur ne pouvait le voir : ils comparent des arborescences de clés, cherchent
    la présence d'un terme, mesurent l'écart au français, comptent des caractères. AUCUN NE
    LIT UNE PHRASE. Une langue peut être structurellement conforme, terminologiquement
    exacte, dimensionnée pour la SERP — et fautive.

    CE QUI EST JUGÉ, ET RIEN D'AUTRE : un déterminant du genre OPPOSÉ, immédiatement suivi du
    terme retenu. L'adjacence et la classe fermée sont ce qui rend l'accusation sûre. Mesuré
    sur le corpus réel relu : 0 accusation — le contrôle se tait quand il n'y a rien.

    CE QUI EST ÉCARTÉ, ET LE MOTIF VAUT D'ÊTRE LU : le participe après copule (« están
    especialmente ADAPTADOS ») se chercherait bien, la copule étant elle aussi une classe
    fermée — mais LA COPULE NE NOMME PAS SON SUJET. Le corpus a exhibé le contre-exemple :
    « A Irène e o Samuel SÃO verdadeiramente acolhedores e SIMPÁTICOS » — masculin pluriel
    JUSTE, dans une chaîne qui parle par ailleurs du logement. Un contrôle qui ne sait pas de
    QUI on parle accuserait cette phrase. Il n'est donc pas écrit.

    Ne remplace pas une relecture humaine : attrape la classe qui est passée ici.
    """
    ecarts: list[dict] = []
    for terme in termes:
        for ligne in terme.get("lignes", []):
            loc = (ligne.get("locale") or "").strip().lower()
            genre = (ligne.get(COLONNE_GENRE) or "").strip().lower()
            retenu = (ligne.get("retenu") or "").replace("`", "").strip()
            if loc not in DETERMINANTS or genre not in _GENRES_JUGES or not retenu:
                continue
            oppose = "f" if genre == "m" else "m"
            fautifs = DETERMINANTS[loc][oppose]
            # `_formes()` rend deja des fragments d'expression PRETS (mot echappe + pluriel
            # court). Les re-echapper les rendait litteraux et le motif ne trouvait plus rien —
            # une regle muette, exactement ce qu'un controle ne doit jamais etre en silence.
            formes = "|".join(sorted(_formes(retenu), key=len, reverse=True))
            dets = "|".join(re.escape(d) for d in sorted(fautifs, key=len, reverse=True))
            # `\s+` et non `\s*` : un déterminant élidé (« un'casa ») n'est pas de la même
            # classe et se juge mal — on ne l'accuse pas.
            motif = re.compile(rf"(?<![\w'’])({dets})\s+({formes})(?![\wÀ-ÿ])",
                               re.IGNORECASE | re.UNICODE)
            for cle, valeur in sorted((par_locale.get(loc) or {}).items()):
                if not isinstance(valeur, str):
                    continue
                for m in motif.finditer(valeur):
                    ecarts.append({
                        "locale": loc, "cle": cle, "terme": terme.get("nom"),
                        "retenu": retenu, "genre": genre,
                        "vu": m.group(0), "determinant": m.group(1),
                    })
    return ecarts


def confronter_coherence_interne(par_locale: dict[str, dict[str, str]]) -> list[dict]:
    """Une MÊME locale se contredit-elle sur un fait chiffré attaché à un nom propre ?

    ============================================================================================
    POURQUOI (TF-0663, 26/08/2026)
    ============================================================================================

    LE FAIT. Un audit a comparé six familles de faits sur SEPT LANGUES et rendu **zéro écart** ; un
    contrôle mécanique des nombres l'a confirmé, 25 divergences sur 735 chaînes dont 22 étaient des
    formats de localisation légitimes. *La comparaison interlangue était saine.* Elle a pourtant
    laissé passer deux faits FAUX — parce qu'ils étaient faux **de la même façon dans les sept
    langues**.

    Le plus net : une ville annoncée à **40 minutes** dans une clé et à **45 minutes** dans deux
    autres, dans les sept langues à la fois. Deux affirmations contre une, et rien pour les
    départager parce que rien ne regardait UNE langue avec elle-même.

    *Vérifier que sept langues disent la même chose ne vérifie pas qu'une seule soit cohérente avec
    elle-même.* C'est la même leçon que la confrontation des nombres à la donnée déclarée
    (TF-0644), sur un autre axe : là il fallait un point fixe HORS du catalogue, ici il faut
    regarder DANS une locale au lieu d'entre les locales.

    CE QUI DÉCLENCHE : le même nom propre, la même unité, et **deux valeurs différentes** dans la
    même locale. Le nom propre est ce qui rend les deux affirmations comparables — sans lui,
    « 3 chambres » et « 2 chambres » parlent de deux logements différents, et les rapprocher serait
    inventer une contradiction là où il n'y en a pas.
    """
    ecarts: list[dict] = []
    for locale, plat in sorted(par_locale.items()):
        vus: dict[tuple[str, str], dict[str, list[str]]] = {}
        for cle, valeur in sorted(plat.items()):
            if not isinstance(valeur, str):
                continue
            for nom, nombre, unite in _FAIT_NOMME.findall(valeur):
                sujet = (nom.casefold(), unite.casefold().rstrip("s"))
                vus.setdefault(sujet, {}).setdefault(nombre, []).append(cle)
        for (nom, unite), valeurs in sorted(vus.items()):
            if len(valeurs) < 2:
                continue
            ecarts.append({
                "locale": locale,
                "sujet": nom,
                "unite": unite,
                "valeurs": {v: cles for v, cles in sorted(valeurs.items())},
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
    "glossaire : le controle d accord ne juge QUE le determinant colle au terme retenu. Le "
    "PARTICIPE APRES COPULE (« estan especialmente adaptados ») est ECARTE : la copule ne "
    "nomme pas son sujet, et le corpus a exhibe le contre-exemple — « A Irene e o Samuel sao "
    "verdadeiramente acolhedores e simpaticos », masculin JUSTE dans une chaine qui parle par "
    "ailleurs du logement. Un controle qui ne sait pas de QUI on parle accuserait cette phrase",
    "glossaire : le controle d accord ne connait de determinants que pour es, pt, it et fr. Une "
    "locale hors de cette table n est pas jugee — l allemand et l anglais n entrent pas dans une "
    "opposition binaire de determinants, et les y forcer inventerait des fautes",
    "glossaire : la coherence interne ne voit un fait que si le NOM PROPRE PRECEDE le nombre dans "
    "la meme phrase — « a 45 minutes de Granville » n est pas rapproche de « Granville : 40 "
    "minutes ». Elargir l ordre ferait rapprocher des sujets differents ; le manque est declare "
    "plutot que comble au juge",
    "glossaire : seules les unites de DISTANCE et de DUREE sont confrontees. Un fait chiffre sans "
    "unite (« 23 personnes ») n est pas juge : sans unite, deux nombres attaches au meme "
    "nom propre peuvent parler de deux grandeurs differentes",
    "glossaire : un terme employe UNIQUEMENT sous une forme flechie eloignee (pluriel irregulier, "
    "declinaison) compte ZERO emploi. Inventer une morphologie par langue serait affirmer "
    "ce que la donnee ne porte pas ; le manque est declare plutot que comble au juge",
    "glossaire : le controle d emploi ne se declenche que si le retenu est a ZERO **et** qu un "
    "proscrit est employe. Un retenu a zero dans une locale qui ne parle pas du concept n est pas "
    "un defaut, et un proscrit employe a cote d un retenu employe peut etre une citation",
    "glossaire : la comparaison ENTRE LOCALES ne remplace pas cette confrontation et c est mesure "
    "— le defaut fondateur disait « 8 » dans les SEPT langues, parfaitement coherent entre locales "
    "et integralement faux. Il faut un point fixe HORS du catalogue",
]
