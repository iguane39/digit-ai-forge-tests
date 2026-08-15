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

from forge_tests import seuils
from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "i18n-build-servi", "i18n"
SEUIL = seuils.valeur("couverture_surface_i18n")
SEUIL_DENSITE_FR = seuils.valeur("densite_mots_outils_francais")

POUR_COUVRIR = (
    "construire le produit et désigner le dossier du BUILD SERVI dans FORGE_TESTS_I18N_BUILD "
    "(`out/`, `dist/`, `_site/`… : l'arborescence de pages telle que le visiteur la reçoit). "
    "Le pan la découvre seul quand elle est à sa place conventionnelle sous la racine du "
    "projet ; il ne lit AUCUN site distant et n'ouvre aucun navigateur"
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
    "i18n : la parite de NAVIGATION compare le NOMBRE d entrees du menu de la page d accueil de "
    "chaque locale au menu le PLUS RICHE ; deux menus de meme taille aux entrees differentes "
    "passent le controle, et un sous-menu qui ne s ouvre qu au clic (non rendu dans le HTML "
    "servi) n est pas compte",
    "i18n : la langue du contenu est jugee par HEURISTIQUE — densite de mots-outils francais "
    "sur le texte visible de la page. Le lexique est FRANCAIS et lui seul : le pan detecte du "
    "francais servi sous une locale non francaise, jamais l inverse ni un autre couple de "
    "langues",
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


class _Page(HTMLParser):
    """Ce qu une page servie dit d elle-même : sa langue déclarée, son menu, son texte."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.menu: list[str] = []
        self.texte: list[str] = []
        self._muet = 0
        self._dans_menu = 0
        self._lien_de_menu = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        table = {nom.lower(): (valeur or "") for nom, valeur in attrs}
        if tag == "html" and table.get("lang"):
            self.lang = table["lang"]
        if tag in ("script", "style", "template"):
            self._muet += 1
            return
        if tag == "nav":
            self._dans_menu += 1
            return
        if tag == "a" and self._dans_menu:
            self._lien_de_menu = True
            self.menu.append(table.get("aria-label") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "template") and self._muet:
            self._muet -= 1
        elif tag == "nav" and self._dans_menu:
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


def densite_mots_outils_fr(texte: str) -> tuple[float, int]:
    """(part des mots-outils français dans le texte, nombre de mots). Déterministe, sans modèle.

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
    outils = sum(1 for mot in mots if mot in MOTS_OUTILS_FR)
    return outils / len(mots), len(mots)


def _sans_accents(texte: str) -> str:
    """Le lexique est écrit sans accents : le texte lu est ramené au même alphabet."""
    table = str.maketrans("àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ", "aaaeeeeiioouuucAAAEEEEIIOOUUUC")
    return texte.translate(table)


def _constat_de_langue(fichier: Path) -> tuple[float, int] | None:
    """Densité de français d une page, ou None si le volume ne permet pas de conclure."""
    page = _lire(fichier)
    densite, mots = densite_mots_outils_fr(_sans_accents(" ".join(page.texte)))
    if mots < _MINIMUM_MOTS:
        return None
    return densite, mots


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


def analyser(cible: Path) -> SortieAdaptateur:
    non_juge = list(NON_JUGE)
    build = build_servi(cible)
    if build is None:
        motif = sans_objet(cible)
        if motif:
            return SortieAdaptateur(
                NOM, PAN, str(cible), "NA", non_juge=[*non_juge, f"i18n : SANS OBJET — {motif}"]
            )
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *non_juge,
                "i18n : produit multilingue par ses sources, mais AUCUN build servi lu — "
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
                        classe="i18n",
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
            mesure = _constat_de_langue(servie) if locale and locale != "fr" else None
            if mesure is not None and mesure[0] >= SEUIL_DENSITE_FR:
                densite, mots = mesure
                findings.append(
                    Finding(
                        id=identifiant,
                        classe="i18n",
                        localisation=str(servie),
                        message=(
                            f"page servie sous « /{locale} » dont le contenu est FRANÇAIS : "
                            f"{densite:.0%} de mots-outils français sur {mots} mots (seuil "
                            f"{SEUIL_DENSITE_FR:.0%}) — heuristique, contestable par déclaration"
                        ),
                        risque=coter(PAN, identifiant, str(servie)),
                    )
                )
                continue
            tenus.append(identifiant)

    # (b) PARITÉ DE NAVIGATION — le menu de la page d accueil de chaque locale. 4 entrées contre
    #     9, non détecté depuis juin : personne ne comparait deux locales entre elles.
    menus = {
        locale: _lire(fichier).menu
        for locale, routes in par_locale.items()
        if (fichier := routes.get("/")) is not None
    }
    muettes = [locale or "defaut" for locale, menu in menus.items() if not menu]
    if muettes:
        non_juge.append(
            "i18n : aucune entree de menu lisible (`<nav>`) sur la page d accueil des locales "
            f"{', '.join(sorted(muettes))} — parite de navigation NON jugee pour elles"
        )
    lisibles = {locale: menu for locale, menu in menus.items() if menu}
    if len(lisibles) > 1:
        plus_riche = max(sorted(lisibles), key=lambda locale: len(lisibles[locale]))
        for locale, menu in sorted(lisibles.items()):
            if len(menu) >= len(lisibles[plus_riche]):
                continue
            identifiant = f"i18n:navigation:{locale or 'defaut'}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe="i18n",
                    localisation=str(par_locale[locale]["/"]),
                    message=(
                        f"menu de la locale « {locale or 'defaut'} » : {len(menu)} entree(s) "
                        f"contre {len(lisibles[plus_riche])} en "
                        f"« {plus_riche or 'defaut'} » — manquent "
                        f"{len(lisibles[plus_riche]) - len(menu)} entree(s)"
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
