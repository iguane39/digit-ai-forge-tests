"""Adaptateur i18n — parité entre locales, mesurée sur le BUILD SERVI (TF-0284).

**Le trou, daté et mesuré.** Étude du 15/08/2026 : AUCUN oracle de l écosystème ne juge le
multilingue. Ni forge-tests, ni quality-oracles, ni les gates de forge-development. La
conséquence a été payée sur un produit en production, et trois fois plutôt qu une :

  - une route française sur 201 n avait pas d équivalent anglais — un visiteur anglophone
    tombait sur une impasse, et rien ne le disait ;
  - le menu anglais portait **4 entrées** quand le français en portait **9**, avec ses
    sous-menus. Non détecté depuis juin : aucune mesure ne comparait une locale à une autre ;
  - **9 pages sur 200** servies sous `/en` rendaient du contenu FRANÇAIS, par câblage de
    données qui renvoyait la langue par défaut quelle que soit la locale demandée.

Les trois ont été trouvés À LA MAIN, en quelques minutes, et les trois sont scriptables sans le
moindre modèle de langage. C est exactement la définition d un pan manquant : un contrôle que
l humain sait faire, que la machine sait refaire, et que personne ne faisait.

**Ce que le pan lit.** Le BUILD SERVI — l arborescence de pages telle que le visiteur la
reçoit. Ni le code source (une locale peut être déclarée et jamais construite), ni un site
distant (aucun réseau : le pan lit un dossier). C est le même point d observation que le pan
`qualif`, sans navigateur : la parité de deux arborescences ne demande pas de rendu.

**Trois contrôles, trois natures, dites comme telles.** (a) et (b) sont des comparaisons
EXACTES — une route est là ou elle n y est pas, un menu porte n entrées ou il n en porte pas
autant. (c) est une HEURISTIQUE : la densité de mots-outils français dans une page servie sous
une locale non française. Son seuil est déclaré (`seuils.py`), sa marge est large (un texte
français dépasse 0,25 quand un texte anglais reste sous 0,02) et ses constats se contestent
comme tout constat d audit — `.forge-tests-declarations.json`, motif typé et contre-preuve.
"""

from __future__ import annotations

import os
from html.parser import HTMLParser
from pathlib import Path

from forge_tests import catalogue_i18n as _catalogue
from forge_tests import classes, seuils
from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "i18n-build-servi", "i18n"
SEUIL = seuils.valeur("couverture_surface_i18n")
SEUIL_DENSITE_FR = seuils.valeur("densite_mots_outils_francais")

POUR_COUVRIR = (
    "construire le produit et désigner le dossier du BUILD SERVI dans FORGE_TESTS_I18N_BUILD "
    "(`out/`, `dist/`, `_site/`… : l'arborescence de pages telle que le visiteur la reçoit). "
    "Le pan la découvre seul quand elle est à sa place conventionnelle sous la racine du "
    "projet ; il ne lit AUCUN site distant et n'ouvre aucun navigateur. DÉCISION (RF-7, lot "
    "SCC-FR 20260820a) : les rendus SERVEUR / ISR qui n'émettent PAS d'arborescence (Next.js "
    "`output: 'standalone'`) sont HORS CHAMP de la parité de routes et de menus — le CATALOGUE "
    "SOURCE reste jugé (TF-0383), et la voie de levée est nommée : accepter une racine servie "
    "(FORGE_TESTS_BASE_URL, déjà employée par le pan accessibilité) comme source des routes par "
    "crawl des liens. C'est une décision écrite ici, plus une découverte au premier run"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
CHAPITRES = (
    {"code": "F6", "famille": "fonctionnel", "titre": "Internationalisation",
     "decoupe": "locale", "axe_cas": "etats"},
)

# RT-13 : le seul champ qui débloque CE pan. Ni compte, ni URL : un dossier de build.
CHAMPS_REQUIS = ("FORGE_TESTS_I18N_BUILD",)

NON_JUGE = [
    "i18n : le pan lit un BUILD SERVI (dossier de pages), jamais un site distant ni le code "
    "source — une locale declaree dans la configuration mais jamais construite est invisible "
    "ici, et c est voulu : ce qui n est pas servi n est pas ce que le visiteur recoit",
    "i18n : la parite de ROUTES se mesure contre l UNION des routes de toutes les locales — une "
    "route servie dans une seule langue manque donc dans les autres. Sur un produit ou la "
    "traduction est en cours PAR CHOIX, l ecart mesure est reel mais il peut etre voulu : il se "
    "conteste alors par declaration, il ne se devine pas",
    # TF-0295, levee 1 : l appariement par ENTREE remplace la comparaison de COMPTES. Ce qui
    # reste hors de portee est le sous-menu non rendu, et il est dit.
    "i18n : la parite de NAVIGATION apparie les entrees du menu de la page d accueil de chaque "
    "locale a celles du menu le PLUS RICHE, par DESTINATION delocalisee — deux menus de meme "
    "taille aux entrees differentes echouent donc, et les entrees manquantes sont nommees. Un "
    "sous-menu qui ne s ouvre qu au clic (absent du HTML servi) n est toujours pas compte, et "
    "une entree sans destination lisible est appariee sur son libelle, donc jamais entre deux "
    "langues",
    # TF-0295, levee 3 : le lexique n est plus le seul francais et il est declarable par projet.
    "i18n : la langue du contenu est jugee par HEURISTIQUE — densite des mots-outils d une "
    "langue sur le texte visible de la page. Le pan connait les lexiques `fr` et `en` et accepte "
    "ceux que le projet DECLARE (FORGE_TESTS_I18N_LEXIQUES) ; une langue servie sans lexique "
    "opposable n est pas jugee, et le rapport DIT contre quels lexiques il a mesure",
    "i18n : seule une locale PREFIXEE est jugee sur sa langue — la locale par defaut n a pas de "
    "prefixe, donc aucune langue opposable, et la deviner reviendrait a interroger le suspect",
    "i18n : une page de moins de 40 mots visibles n est pas jugee sur sa langue — sous ce "
    "volume, la densite de mots-outils n est plus un signal, c est du bruit",
    "i18n : l attribut `lang` du document n est pas oppose au contenu — un `lang=\"en\"` pose "
    "sur du francais est precisement le defaut, le croire reviendrait a interroger le suspect",
    "i18n : les pages conventionnelles de service (`404`, `500`, et tout segment commencant par "
    "`_`) sont hors comptage de parite : elles ne sont pas des routes du produit",
]

# Dossiers de build conventionnels, cherchés sous la racine du projet quand aucun n est déclaré.
DOSSIERS_BUILD = ("out", "dist", "build", "_site", "site", "www", "public")
_EXCLUS = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages", ".next", ".nuxt",
    ".svelte-kit", ".visuel", "htmlcov", "coverage", ".tox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", "vendor", ".forge", "forge", "output", "old", "Old", ".oracles",
}
# Pages de service : servies, mais ce ne sont pas des routes du produit.
_PAGES_DE_SERVICE = ("404", "500", "403", "offline")
_MINIMUM_MOTS = 40

# Codes ISO 639-1 des langues qu un site multilingue préfixe couramment. Liste FERMÉE : prendre
# `/id/42` pour une locale sur un site qui n en a pas fabriquerait une parité imaginaire, donc
# des constats contre des routes parfaitement saines.
LOCALES_CONNUES = frozenset(
    ("en", "fr", "de", "es", "it", "nl", "pt", "pl", "ru", "ja", "zh", "ar", "sv", "da", "fi",
     "cs", "tr", "ko", "el", "he", "hu", "ro", "uk")
)

# Mots-outils FRANÇAIS non ambigus : aucun n est un mot anglais courant. `on`, `en`, `a`, `as`,
# `no`, `son`, `pas`, `car`, `plus` en sont volontairement ABSENTS — ce sont eux qui feraient
# monter la densité d un texte anglais, c est-à-dire qui accuseraient une page saine.
MOTS_OUTILS_FR = frozenset((
    "le", "les", "des", "du", "une", "dans", "pour", "avec", "sur", "par", "qui", "que", "est",
    "sont", "nous", "vous", "cette", "aux", "chez", "mais", "donc", "etre", "ete", "leur",
    "leurs", "nos", "vos", "ses", "cet", "ces", "elle", "elles", "ils", "notre", "votre",
    "ainsi", "depuis", "entre", "sans", "sous", "alors", "aussi", "comme", "tous", "toute",
    "toutes", "peut", "doit", "fait", "faire", "chaque", "lors", "afin", "dont", "ou", "est-ce",
    "quelle", "quel", "quelles", "quels", "lorsque", "parce", "apres", "avant", "deja", "encore",
    "jamais", "toujours", "beaucoup", "moins", "tres", "bien", "celui", "celle", "ceux", "quand",
    "puis", "ni", "tandis",
))

# TF-0295 (levée 3) — le lexique n est plus le seul français. Le pan ne connaissait qu UN couple,
# « français servi sous locale non française » : un produit dont les pages `/fr` rendent de
# l anglais — le cas symétrique, tout aussi réel — passait sans un mot. Le contrôle est désormais
# une TABLE de lexiques, et la règle est générale : sous la locale L, la présence dense du
# lexique d une langue M ≠ L est un constat.
#
# Mêmes précautions que pour le français, et elles sont la condition du contrôle : aucun mot
# ambigu entre les deux langues. « on », « en », « a », « as », « son », « plus », « car »,
# « pas », « no », « or », « si », « ni », « nos », « ces » sont donc ABSENTS des deux lexiques —
# ce sont eux qui feraient monter la densité d une page saine, c est-à-dire qui accuseraient à
# tort. Le seuil, lui, est commun et opposable (`seuils.py`).
MOTS_OUTILS_EN = frozenset((
    "the", "and", "with", "this", "that", "these", "those", "from", "have", "has", "had",
    "which", "they", "their", "them", "our", "your", "been", "were", "will", "would", "should",
    "could", "about", "into", "than", "then", "when", "what", "who", "whom", "whose", "how",
    "there", "here", "because", "while", "after", "before", "each", "any", "all", "not", "but",
    "for", "are", "was", "its", "his", "her", "him", "you", "of", "to", "in", "is", "be", "by",
    "at", "an", "so", "if", "we", "it", "also", "such", "both", "very", "many", "more", "most",
    "other", "some", "only", "own", "same", "through", "during", "between", "under", "over",
    "again", "further", "once", "always", "never", "already", "still", "just", "does", "did",
))

# Le lexique d une langue, par code ISO 639-1. Une clé de plus suffit à ouvrir un couple de plus :
# c est ce que « extensible » veut dire ici. Un projet peut en DÉCLARER d autres sans toucher au
# code, par `FORGE_TESTS_I18N_LEXIQUES` (voir `lexiques()`).
LEXIQUES: dict[str, frozenset[str]] = {"fr": MOTS_OUTILS_FR, "en": MOTS_OUTILS_EN}
# Sous ce nombre de mots, un lexique DÉCLARÉ ne fait pas un contrôle : une poignée de mots-outils
# ne discrimine rien et fabriquerait des constats au hasard. Le refus est déclaré, pas silencieux.
_LEXIQUE_MINIMAL = 20


class _Page(HTMLParser):
    """Ce qu une page servie dit d elle-même : sa langue déclarée, son menu, son texte."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.menu: list[str] = []
        # TF-0295 (1) : la DESTINATION de chaque entrée, dans le même ordre que `menu`. C est
        # elle qui rend deux menus comparables ENTRÉE PAR ENTRÉE : les libellés, eux, sont
        # traduits — « Accueil » et « Home » sont la même entrée et aucun rapprochement textuel
        # ne peut le savoir.
        self.destinations: list[str] = []
        self.texte: list[str] = []
        self._muet = 0
        self._dans_menu = 0
        self._lien_de_menu = False
        # TF-0464 (22/08) : le CHROME PARTAGE ne se limite pas au <nav>. Mesure sur
        # digit-ai.fr, 201 pages en production : le pied de page francais porte 21 liens,
        # l anglais 3 — et les deux pieds sont des <footer> SANS <nav>. Le pan lisait donc
        # 0 contre 0 et rendait PASS : un silence indiscernable d un succes, le pire mode de
        # defaillance d un oracle. La garde existante (`muettes`) ne se declenchait pas
        # puisque l en-tete, lui, EST un <nav> : la navigation passait pour vue et
        # l amputation du pied disparaissait sans un mot. Le repere s etend donc a <footer>
        # et a role="contentinfo"/"navigation" — meme classe de defaut que celui qui a FONDE
        # le pan (menu anglais a 4 entrees contre 9), autre repere, meme silence.
        self._reperes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        table = {nom.lower(): (valeur or "") for nom, valeur in attrs}
        if tag == "html" and table.get("lang"):
            self.lang = table["lang"]
        if tag in ("script", "style", "template"):
            self._muet += 1
            return
        role = (table.get("role") or "").strip().lower()
        if tag in ("nav", "footer") or role in ("navigation", "contentinfo"):
            self._dans_menu += 1
            self._reperes += 1
            return
        if tag == "a" and self._dans_menu:
            self._lien_de_menu = True
            self.menu.append(table.get("aria-label") or "")
            self.destinations.append(table.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "template") and self._muet:
            self._muet -= 1
        elif tag in ("nav", "footer") and self._dans_menu:
            self._dans_menu -= 1
        elif tag == "a" and self._lien_de_menu:
            self._lien_de_menu = False

    def handle_data(self, data: str) -> None:
        if self._muet:
            return
        if self._lien_de_menu and self.menu:
            self.menu[-1] = (self.menu[-1] + " " + data).strip()
        self.texte.append(data)


def _lire(fichier: Path) -> _Page:
    page = _Page()
    try:
        page.feed(fichier.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — une page illisible se DECLARE, elle n emporte pas le pan
        return page
    return page


def build_servi(cible: Path) -> Path | None:
    """Le dossier de build à lire : déclaré, sinon découvert, sinon rien — jamais supposé."""
    declare = os.environ.get("FORGE_TESTS_I18N_BUILD")
    if declare and Path(declare).is_dir():
        return Path(declare)
    for nom in DOSSIERS_BUILD:
        candidat = cible / nom
        if candidat.is_dir() and (candidat / "index.html").is_file():
            return candidat
    if (cible / "index.html").is_file():
        return cible  # le projet EST le build servi (site statique à plat)
    return None


def _route(fichier: Path, build: Path) -> str | None:
    """Route servie par ce fichier, ou None si ce n est pas une route du produit."""
    relatif = fichier.relative_to(build)
    if any(partie in _EXCLUS or partie.startswith("_") for partie in relatif.parts):
        return None
    if fichier.stem in _PAGES_DE_SERVICE:
        return None
    if fichier.name == "index.html":
        parent = relatif.parent.as_posix()
        return "/" if parent == "." else "/" + parent
    return "/" + relatif.as_posix()[: -len(fichier.suffix)]


def pages_servies(build: Path) -> dict[str, Path]:
    """Route servie -> fichier qui la rend."""
    pages: dict[str, Path] = {}
    for fichier in sorted(build.rglob("*.html")):
        route = _route(fichier, build)
        if route is not None:
            pages.setdefault(route, fichier)
    return pages


def locales_servies(pages: dict[str, Path]) -> set[str]:
    """Locales PRÉFIXÉES réellement servies. La locale par défaut, elle, n a pas de préfixe."""
    trouvees = set()
    for route in pages:
        segments = route.split("/")
        if len(segments) > 1 and segments[1] in LOCALES_CONNUES:
            trouvees.add(segments[1])
    return trouvees


def _sans_prefixe(route: str, locale: str) -> str:
    reste = route[len(f"/{locale}"):]
    return reste or "/"


def _par_locale(pages: dict[str, Path], locales: set[str]) -> dict[str, dict[str, Path]]:
    """locale -> {route SANS son préfixe: fichier}. La locale par défaut a la clé « »."""
    table: dict[str, dict[str, Path]] = {locale: {} for locale in locales}
    table[""] = {}
    for route, fichier in pages.items():
        segments = route.split("/")
        locale = segments[1] if len(segments) > 1 and segments[1] in locales else ""
        table[locale][_sans_prefixe(route, locale) if locale else route] = fichier
    return table


def _route_servie(locale: str, route: str) -> str:
    if not locale:
        return route
    return f"/{locale}" if route == "/" else f"/{locale}{route}"


# --- Parité de navigation : par ENTRÉE, jamais par compte (TF-0295, levée 1) -------------------
def entrees_de_menu(page: _Page, locales: set[str]) -> list[str]:
    """Clés comparables des entrées du menu de `page`, dans l ordre du document.

    La clé est la DESTINATION délocalisée : `/en/tarifs` sous la locale `en` et `/tarifs` sous la
    locale par défaut sont la MÊME entrée. Le libellé ne peut pas servir de clé — il est traduit,
    c est tout l objet du sujet. Une entrée sans destination lisible retombe sur son libellé,
    faute de mieux, et une entrée sans ni l un ni l autre porte son rang : sans cela deux entrées
    muettes se confondraient et un menu amputé de l une passerait pour complet.
    """
    cles: list[str] = []
    for rang, (libelle, destination) in enumerate(
        zip(page.menu, page.destinations, strict=True)
    ):
        brut = (destination or "").split("?")[0].split("#")[0].strip()
        if brut.startswith("/"):
            chemin = brut.rstrip("/") or "/"
            segments = chemin.split("/")
            if len(segments) > 1 and segments[1] in locales:
                chemin = _sans_prefixe(chemin, segments[1])
            cles.append(chemin)
        elif brut:
            cles.append(brut)  # externe, `mailto:`, ancre : comparable tel quel
        elif libelle.strip():
            cles.append(f"libelle:{libelle.strip().lower()}")
        else:
            cles.append(f"rang:{rang}")
    return cles


def lexiques() -> dict[str, frozenset[str]]:
    """Les lexiques opposables : ceux du code, plus ceux que le projet DÉCLARE (TF-0295).

    `FORGE_TESTS_I18N_LEXIQUES` désigne un fichier JSON `{"de": ["der", "die", …], …}`. Un
    lexique déclaré remplace celui du code pour la même langue — un produit sait mieux que la
    forge quels mots-outils il n emploie jamais dans l autre langue. Un fichier illisible, une
    langue inconnue ou un lexique trop court sont IGNORÉS et le motif se dit au rapport
    (`motifs_de_lexique`), jamais silencieusement pris pour bon.
    """
    table = dict(LEXIQUES)
    for code, mots in _lexiques_declares()[0].items():
        table[code] = mots
    return table


def _lexiques_declares() -> tuple[dict[str, frozenset[str]], list[str]]:
    """(lexiques déclarés retenus, motifs de ce qui a été écarté)."""
    import json

    chemin = (os.environ.get("FORGE_TESTS_I18N_LEXIQUES") or "").strip()
    if not chemin:
        return {}, []
    fichier = Path(chemin)
    if not fichier.is_file():
        return {}, [f"lexiques declares introuvables : {chemin}"]
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        return {}, [f"lexiques declares illisibles ({type(erreur).__name__}) : {chemin}"]
    if not isinstance(charge, dict):
        return {}, [f"lexiques declares : objet JSON attendu, {type(charge).__name__} lu"]
    retenus: dict[str, frozenset[str]] = {}
    motifs: list[str] = []
    for code, mots in sorted(charge.items()):
        if code not in LOCALES_CONNUES:
            motifs.append(f"lexique declare « {code} » : locale inconnue, ignore")
            continue
        if not isinstance(mots, list) or len(mots) < _LEXIQUE_MINIMAL:
            motifs.append(
                f"lexique declare « {code} » : moins de {_LEXIQUE_MINIMAL} mots-outils, ignore "
                "— un lexique trop court ne discrimine rien et accuserait au hasard"
            )
            continue
        retenus[code] = frozenset(str(mot).strip().lower() for mot in mots if str(mot).strip())
    return retenus, motifs


def densite_mots_outils(texte: str, lexique: frozenset[str]) -> tuple[float, int]:
    """(part des mots-outils de `lexique` dans le texte, nombre de mots). Sans modèle.

    Le compte porte sur des mots ENTIERS et minusculés ; les accents ne sont pas requis (une
    page servie en `latin-1` mal décodée perdrait ses accents mais garderait ses mots-outils).
    """
    mots = [
        "".join(caractere for caractere in mot.lower() if caractere.isalpha() or caractere == "-")
        for mot in texte.split()
    ]
    mots = [mot for mot in mots if mot]
    if not mots:
        return 0.0, 0
    outils = sum(1 for mot in mots if mot in lexique)
    return outils / len(mots), len(mots)


def densite_mots_outils_fr(texte: str) -> tuple[float, int]:
    """La densité du lexique FRANÇAIS — le premier couple, conservé sous son nom d origine."""
    return densite_mots_outils(texte, MOTS_OUTILS_FR)


def _sans_accents(texte: str) -> str:
    """Le lexique est écrit sans accents : le texte lu est ramené au même alphabet."""
    table = str.maketrans("àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ", "aaaeeeeiioouuucAAAEEEEIIOOUUUC")
    return texte.translate(table)


def _constat_de_langue(
    fichier: Path, locale: str, table: dict[str, frozenset[str]] | None = None
) -> tuple[str, float, int] | None:
    """(langue détectée, densité, nombre de mots) quand une page trahit une AUTRE langue que sa
    locale — sinon None (page saine, ou volume insuffisant pour conclure).

    TF-0295 (levée 3) : la règle est générale. Sous la locale L, chaque lexique d une langue
    M ≠ L est mesuré, et c est le plus dense au-delà du seuil qui est retenu — nommer deux
    langues pour une même page serait dire deux fois le même défaut.
    """
    page = _lire(fichier)
    texte = _sans_accents(" ".join(page.texte))
    mesures = [
        (code, *densite_mots_outils(texte, lexique))
        for code, lexique in sorted((table or lexiques()).items())
        if code != locale
    ]
    if not mesures or mesures[0][2] < _MINIMUM_MOTS:
        return None
    code, densite, mots = max(mesures, key=lambda mesure: mesure[1])
    return (code, densite, mots) if densite >= SEUIL_DENSITE_FR else None


def _signes_i18n(cible: Path) -> list[str]:
    """Preuves POSITIVES qu un produit prétend être multilingue, hors build servi.

    Sans elles, un produit monolingue — l immense majorité — sortirait en SKIP à chaque audit et
    rendrait tous les rapports PARTIELS pour un pan qui n a rien à mesurer chez lui.
    """
    signes: list[str] = []
    for nom in ("package.json", "next.config.js", "next.config.mjs", "next.config.ts"):
        fichier = cible / nom
        if not fichier.is_file():
            continue
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for marqueur in ("next-intl", "react-i18next", "i18next", "vue-i18n", "\"i18n\"", "i18n:"):
            if marqueur in texte:
                signes.append(f"{nom} mentionne {marqueur}")
                break
    # `os.walk` et non `rglob` : l arborescence des dépendances se COUPE au lieu d être
    # parcourue. Ce contrôle tourne sur TOUT audit de TOUT produit — descendre dans
    # `node_modules` pour n en rien tirer serait un coût payé partout, tout le temps.
    for racine, dossiers, _ in os.walk(cible):
        dossiers[:] = sorted(nom for nom in dossiers if nom not in _EXCLUS)
        for nom in dossiers:
            chemin = Path(racine, nom)
            if nom in ("locales", "messages", "translations", "i18n"):
                signes.append(f"dossier de traductions `{chemin.relative_to(cible).as_posix()}`")
            elif nom.strip("[]") in ("locale", "lang", "lng"):
                signes.append(f"segment de route `{nom}`")
        if len(signes) >= 5:
            break
    return signes[:5]


def sans_objet(cible: Path) -> str | None:
    """PREUVE que ce produit n a pas de périmètre i18n (NA) — jamais une supposition.

    Deux formes d absence, et une seule est un « sans objet » : le produit qui ne se prétend
    nulle part multilingue. Celui qui le prétend mais dont le build n est pas là est un pan NON
    MESURÉ, ce qui est tout autre chose et se répare en fournissant le dossier.
    """
    build = build_servi(cible)
    if build is not None:
        if locales_servies(pages_servies(build)):
            return None
        return (
            f"build servi lu ({build.name}) : aucune page prefixee par une locale — ce produit "
            "est servi dans une seule langue, il n y a pas de parite a mesurer"
        )
    if _signes_i18n(cible):
        return None  # il se prétend multilingue : le manque est le BUILD, pas le sujet
    return (
        "aucun build servi sous la racine et aucun signe d internationalisation (ni dependance "
        "i18n, ni dossier de traductions, ni segment de route de locale) : ce produit n est pas "
        "multilingue"
    )


def inventaire(cible: Path) -> list[Element]:
    """Éléments de surface : une route ATTENDUE par locale servie (la locale par défaut incluse).

    Le produit cartésien EST la mesure : une route qui n existe que dans une langue occupe une
    case vide dans les autres, et c est cette case vide qui devient un constat nommé.
    """
    build = build_servi(cible)
    if build is None:
        return []
    pages = pages_servies(build)
    locales = locales_servies(pages)
    if not locales:
        return []
    par_locale = _par_locale(pages, locales)
    attendues = sorted({route for routes in par_locale.values() for route in routes})
    return [
        Element(
            f"i18n:route:{locale or 'defaut'}:{route}",
            PAN,
            f"route « {_route_servie(locale, route)} » (locale {locale or 'defaut'})",
            str(par_locale[locale].get(route) or build),
        )
        for locale in sorted(par_locale)
        for route in attendues
    ]


def _findings_catalogue(cible: Path) -> tuple[list[Finding], list[str]]:
    """Les trois contrôles du CATALOGUE SOURCE — TF-0383. Le second point d'observation du pan.

    Le build servi dit ce que le visiteur reçoit ; le catalogue dit ce que le produit PRÉTEND
    savoir dire. Un produit à repli de langue sans préfixe d'URL sert toutes ses routes dans
    toutes ses locales et remplit les trous avec la langue par défaut : le build est parfait, le
    catalogue est troué, et seul le second le montre. Mesuré sur un produit client livré : 150
    clés manquantes par locale sur 5 des 7 langues déclarées, et le pan rendait SKIP.
    """
    lus, non_lus = _catalogue.catalogues(cible)
    findings: list[Finding] = []
    motifs = [f"i18n : catalogue non lu — {motif}" for motif in non_lus]

    if not lus:
        return findings, motifs

    for dossier, par_locale in sorted(lus.items()):
        verdict = _catalogue.juger(par_locale)
        motifs.append(
            f"i18n : catalogue `{dossier}` lu — {len(verdict['locales'])} locale(s) "
            f"({', '.join(verdict['locales'])}), {verdict['union']} cle(s) a l UNION ; comptes "
            + ", ".join(f"{loc} {n}" for loc, n in verdict["comptes"].items())
        )
        # (d) COMPLÉTUDE — une locale déclarée dont le catalogue est troué sert la langue de repli
        # sans le dire. Le finding porte sur la LOCALE et nomme ses premières clés : un total
        # anonyme ne se corrige pas, et 150 clés listées ne se lisent pas.
        for locale, absentes in sorted(verdict["manquantes"].items()):
            part = len(absentes) / verdict["union"] if verdict["union"] else 0
            findings.append(
                Finding(
                    id=f"i18n:catalogue:{dossier}:{locale}",
                    classe=classes.I18N,
                    localisation=f"{dossier}/{locale}.json",
                    message=(
                        f"locale « {locale} » : {len(absentes)} cle(s) MANQUANTE(S) sur "
                        f"{verdict['union']} ({part:.0%}) — servies dans la langue de repli sans "
                        f"qu aucun message ne le signale. Premieres : "
                        + ", ".join(absentes[:6])
                        + (f" (+{len(absentes) - 6} autres)" if len(absentes) > 6 else "")
                    ),
                    risque=coter(PAN, f"i18n:catalogue:{locale}", dossier),
                )
            )
        # (e) INTÉGRITÉ DES PARAMÈTRES — un paramètre perdu rend un trou dans la phrase, un
        # paramètre inventé rend le littéral. Les deux sont servis à l utilisateur.
        for ecart in verdict["divergences"]:
            findings.append(
                Finding(
                    id=f"i18n:parametre:{dossier}:{ecart['locale']}:{ecart['cle']}",
                    classe=classes.I18N,
                    localisation=f"{dossier}/{ecart['locale']}.json",
                    message=(
                        f"« {ecart['cle']} » en « {ecart['locale']} » : parametre(s) "
                        + (f"PERDU(S) {', '.join(ecart['perdus'])}" if ecart["perdus"] else "")
                        + (" et " if ecart["perdus"] and ecart["inventes"] else "")
                        + (f"INVENTE(S) {', '.join(ecart['inventes'])}"
                           if ecart["inventes"] else "")
                        + f" — attendus {ecart['attendus']}, trouves {ecart['trouves']}"
                    ),
                    risque=coter(PAN, "i18n:parametre", dossier),
                )
            )
        # (f) CONSTANCE — sur les seuls libelles d ACTION (`voix.md` §Actions). Le resserrage est
        # mesure : etendu a toutes les chaines, ce controle rendait 6 faux positifs sur 6.
        for ecart in verdict["inconstances"]:
            findings.append(
                Finding(
                    id=f"i18n:constance:{dossier}:{ecart['locale']}:{ecart['cles'][0]}",
                    classe=classes.I18N,
                    localisation=f"{dossier}/{ecart['locale']}.json",
                    message=(
                        f"libelle d action rendu de {len(ecart['rendus'])} facons en "
                        f"« {ecart['locale']} » pour une meme source : "
                        + " · ".join(f"« {r} »" for r in ecart["rendus"])
                        + f" — cles {', '.join(ecart['cles'])}. Un libelle, un seul, d un bout a "
                        "l autre du parcours"
                    ),
                    risque=coter(PAN, "i18n:constance", dossier),
                )
            )
    return findings, motifs


def analyser(cible: Path) -> SortieAdaptateur:
    non_juge = [*NON_JUGE, *_catalogue.NON_JUGE]
    # TF-0383 — le CATALOGUE se juge d abord, et INDEPENDAMMENT du build servi. C est tout le
    # sujet : un produit a repli de langue sans prefixe d URL n a rien a montrer au build (toutes
    # les routes existent partout, remplies par la langue par defaut) et tout a montrer au
    # catalogue. Avant cette levee, le pan rendait SKIP sur un produit dont 5 locales sur 7
    # portaient 61 % de trous — mesure du 19/08.
    findings_catalogue, motifs_catalogue = _findings_catalogue(cible)
    non_juge.extend(motifs_catalogue)

    build = build_servi(cible)
    if build is None:
        if findings_catalogue or any("catalogue `" in m for m in motifs_catalogue):
            # Le catalogue a parle : le pan MESURE, meme sans build. Le build reste nomme comme
            # ce qui manque pour juger la parite de routes et la langue servie.
            non_juge.append(
                "i18n : AUCUN build servi lu — les controles de parite de routes, de navigation "
                "et de langue du contenu ne sont pas joues ici ; seul le CATALOGUE SOURCE l est. "
                f"Declarer le dossier construit dans FORGE_TESTS_I18N_BUILD (cherche : "
                f"{', '.join(DOSSIERS_BUILD)} sous {cible})"
            )
            return SortieAdaptateur(
                NOM, PAN, str(cible),
                "FAIL" if findings_catalogue else "PASS",
                findings=findings_catalogue,
                non_juge=non_juge,
            )
        motif = sans_objet(cible)
        if motif:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "NA", non_juge=[*non_juge, f"i18n : SANS OBJET — {motif}"]
            )
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *non_juge,
                "i18n : produit multilingue par ses sources, mais AUCUN build servi lu NI "
                "catalogue de chaines JSON par locale — "
                f"declarer le dossier construit dans FORGE_TESTS_I18N_BUILD (cherche : "
                f"{', '.join(DOSSIERS_BUILD)} sous {cible})",
            ],
        )

    pages = pages_servies(build)
    locales = locales_servies(pages)
    if not locales:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "NA",
            non_juge=[*non_juge, f"i18n : SANS OBJET — {sans_objet(cible)}"],
        )

    par_locale = _par_locale(pages, locales)
    attendues = sorted({route for routes in par_locale.values() for route in routes})
    non_juge.append(
        f"i18n : build lu `{build}` — {len(pages)} page(s) servie(s), locales "
        f"{', '.join(sorted(nom or 'defaut (sans prefixe)' for nom in par_locale))} ; parite "
        f"mesuree contre l UNION des routes ({len(attendues)} routes attendues par locale)"
    )
    # TF-0295 (levée 3) : QUELS lexiques ont jugé, et ce qui a été écarté. « aucun français
    # détecté » et « la langue n a été mesurée contre aucun lexique » ne sont pas le même rapport.
    table = lexiques()
    declares, motifs_lexique = _lexiques_declares()
    non_juge.append(
        "i18n : langue du contenu jugee contre les lexiques "
        + ", ".join(f"{code} ({len(mots)} mots-outils)" for code, mots in sorted(table.items()))
        + (
            f" — dont declares par le projet : {', '.join(sorted(declares))}"
            if declares
            else " — aucun lexique declare par le projet (FORGE_TESTS_I18N_LEXIQUES)"
        )
    )
    non_juge.extend(f"i18n : {motif}" for motif in motifs_lexique)

    findings: list[Finding] = []
    tenus: list[str] = []

    # (a) PARITÉ DE ROUTES — une comparaison exacte : la route est servie dans cette locale, ou
    #     elle ne l est pas. C est le contrôle qui a manqué à la route 201/201 du 15/08.
    # (c) LANGUE DU CONTENU — heuristique, sur les seules locales non françaises réellement
    #     servies. Portée sur le MÊME élément de surface que (a) : une route servie dans la
    #     mauvaise langue n est pas « couverte », elle est servie à côté.
    for locale in sorted(par_locale):
        for route in attendues:
            identifiant = f"i18n:route:{locale or 'defaut'}:{route}"
            servie = par_locale[locale].get(route)
            if servie is None:
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.I18N,
                        localisation=str(build),
                        message=(
                            f"route « {_route_servie(locale, route)} » absente du build : servie "
                            f"dans {len([1 for autre in par_locale if route in par_locale[autre]])}"
                            f" locale(s) sur {len(par_locale)}, pas dans "
                            f"« {locale or 'defaut'} »"
                        ),
                        risque=coter(PAN, identifiant, str(build)),
                    )
                )
                continue
            # TF-0295 (levée 3) : toute locale PRÉFIXÉE est jugée, contre tous les lexiques sauf
            # le sien. La locale par défaut, elle, n a pas de préfixe et donc pas de langue
            # opposable — la juger reviendrait à deviner la langue du site.
            mesure = _constat_de_langue(servie, locale, table) if locale else None
            if mesure is not None:
                langue, densite, mots = mesure
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.I18N,
                        localisation=str(servie),
                        message=(
                            f"page servie sous « /{locale} » dont le contenu est en "
                            f"« {langue} » : {densite:.0%} de mots-outils {langue} sur {mots} "
                            f"mots (seuil {SEUIL_DENSITE_FR:.0%}) — heuristique, contestable "
                            "par déclaration"
                        ),
                        risque=coter(PAN, identifiant, str(servie)),
                    )
                )
                continue
            tenus.append(identifiant)

    # (b) PARITÉ DE NAVIGATION — le menu de la page d accueil de chaque locale. 4 entrées contre
    #     9, non détecté depuis juin : personne ne comparait deux locales entre elles.
    #
    #     TF-0295 (levée 1) : l appariement se fait par ENTRÉE, plus par COMPTE. Deux menus de
    #     même taille aux entrées DIFFÉRENTES passaient le contrôle — un menu qui a perdu
    #     « Tarifs » et gagné « Blog » est amputé pour le visiteur, et il l est en silence. La
    #     clé est la destination délocalisée, seule chose qu on puisse comparer entre deux
    #     langues, et les entrées manquantes sont NOMMÉES.
    menus = {
        locale: entrees_de_menu(_lire(fichier), locales)
        for locale, routes in par_locale.items()
        if (fichier := routes.get("/")) is not None
    }
    muettes = [locale or "defaut" for locale, menu in menus.items() if not menu]
    if muettes:
        non_juge.append(
            "i18n : aucune entree de navigation lisible (`<nav>`, `<footer>`, role=navigation "
            "ou contentinfo) sur la page d accueil des locales "
            f"{', '.join(sorted(muettes))} — parite de navigation NON jugee pour elles"
        )
    lisibles = {locale: menu for locale, menu in menus.items() if menu}
    if len(lisibles) > 1:
        # La référence est le menu le plus RICHE en entrées distinctes : c est celui qui dit ce
        # que le produit sait offrir. À égalité, la locale de plus petit nom, pour que deux runs
        # sur le même build rendent le même verdict.
        plus_riche = max(sorted(lisibles), key=lambda locale: len(set(lisibles[locale])))
        reference = dict.fromkeys(lisibles[plus_riche])  # ordre du document, doublons ôtés
        for locale, menu in sorted(lisibles.items()):
            manquantes = [entree for entree in reference if entree not in set(menu)]
            if not manquantes:
                continue
            identifiant = f"i18n:navigation:{locale or 'defaut'}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.I18N,
                    localisation=str(par_locale[locale]["/"]),
                    message=(
                        f"menu de la locale « {locale or 'defaut'} » : {len(set(menu))} "
                        f"entree(s) distincte(s) contre {len(reference)} en "
                        f"« {plus_riche or 'defaut'} » — manquent "
                        f"{len(manquantes)} entree(s) : "
                        + ", ".join(f"« {entree} »" for entree in manquantes)
                    ),
                    risque=coter(PAN, identifiant, str(par_locale[locale]["/"])),
                )
            )

    findings.sort(key=lambda finding: finding.risque or 0, reverse=True)
    total = len(par_locale) * len(attendues)
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if findings else "PASS",
        findings=findings,
        non_juge=non_juge,
        surface={
            "inventorie": total,
            "exerce": len(tenus),
            "ratio": round(len(tenus) / total, 4) if total else 0.0,
            "seuil": SEUIL,
            "elements_exerces": sorted(tenus),
            "elements_non_exerces": sorted(
                f"i18n:route:{locale or 'defaut'}:{route}"
                for locale in par_locale
                for route in attendues
                if f"i18n:route:{locale or 'defaut'}:{route}" not in set(tenus)
            ),
        },
    )
