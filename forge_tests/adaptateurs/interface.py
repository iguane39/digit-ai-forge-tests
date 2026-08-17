"""Adaptateur Interface — contre-oracle STATIQUE « toute affordance est câblée ou n existe pas ».

RT-7. L audit v0.1.0 d un produit réel affichait 100 % sur tous les pans mesurés ; l utilisateur
a trouvé douze défauts en dix minutes, dont des boutons qui ne faisaient RIEN. La couverture
endpoint x code ne pouvait pas les voir : elle mesure ce que la suite atteint, et une suite
n atteint jamais un bouton mort — il n y a rien à atteindre. Ce pan mesure autre chose, en
amont de toute exécution : la PROMESSE d interface. Un `<button>` promet un effet, un `<a>`
promet une destination, un `<form>` promet un envoi. Le contre-oracle vérifie que la promesse
est tenue quelque part dans le code, et NOMME celles qui ne le sont pas.

Il est délibérément statique : c est ce qui le rend disponible là où Playwright ne l est pas —
projet non constructible, front servi par le backend, gabarit rendu côté serveur. Le pan front
mesure l EXERCICE des éléments, celui-ci leur EXISTENCE fonctionnelle ; les deux sont
orthogonaux et aucun ne remplace l autre.

**Liens des composants React (TF-0283).** Les composants `.jsx`/`.tsx` étaient déclarés hors
périmètre — « leur câblage est une expression du langage, pas un attribut du gabarit ». La
phrase reste vraie du CÂBLAGE (un `onClick` compilé par un framework), elle était fausse de la
DESTINATION : un `<Link href="/en/blog">` porte une chaîne littérale, aussi lisible que le
`href` d un gabarit. Payé le 15/08/2026 sur un produit en production : logo anglais pointant
vers `/en/blog`, lien Contact des en-tête ET pied de page anglais pointant vers la page
FRANÇAISE, bascule « Français » pointant vers `/blog` — quatre liens faux, tous dans des `.tsx`,
tous invisibles à l auditeur, tous livrés, signalés deux fois par l humain. Le pan lit donc
aussi les destinations LITTÉRALES des `<a>`, `<Link>` et `<NavLink>` des composants, et juge
trois choses : la destination existe dans l arborescence, elle est cohérente avec la locale du
composant, et les deux liens dont la cible est CONNUE D AVANCE — le logo (racine de sa locale)
et la bascule de langue (racine de la locale visée) — pointent bien où ils le promettent. Une
destination EXPRIMÉE (`href={...}`) ne se devine pas : elle est comptée et déclarée en
`non_juge`, jamais jugée.

**Écart SERVI ↔ VERSIONNÉ (TF-0288).** Le pan tient désormais les deux termes que personne ne
comparait : ce que la source promet en navigation, et ce que le build servi en rend. Cas
fondateur INS-0001 — `HeaderEn.tsx` portait 8 entrées et 36 liens, utilisé par 36 pages EN sur
36 ; la production en servait 3. L écart vivait entre la source et le servi, et la cause évidente
(compléter le composant) aurait été un développement inutile sur un défaut de DÉPLOIEMENT. Le
contrôle réutilise la grammaire de composants ci-dessus pour la source et la lecture du build
servi du pan `i18n` pour le servi — en écrire de nouveaux aurait fait diverger deux lectures de
la même chose. Verdict machine, trois issues, toutes DÉCLARÉES au rapport.

Loi appliquée : *une affordance est câblée, ou elle n existe pas*. Ce que l analyse statique ne
peut pas voir — un gestionnaire posé à l exécution par un framework, une délégation d événement
sur un ancêtre — est déclaré en `non_juge`, jamais deviné dans un sens ni dans l autre.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN, SEUIL = "interface-statique", "interface", 1.0

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "fournir au moins un gabarit servi (.html, .jinja, .twig...) hors artefacts de "
    "construction, ou des composants React (.jsx/.tsx) portant des liens à destination "
    "littérale : le pan lit les affordances du GABARIT et les DESTINATIONS des liens de "
    "composants ; le câblage des composants (gestionnaires posés à l'exécution) relève du "
    "pan front"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "F3", "famille": "fonctionnel", "titre": "Affordances",
     "decoupe": "fichier", "axe_cas": "unitaire"},
)


# Gabarits rendus tels quels par un serveur ou servis en statique. Le CÂBLAGE des composants de
# framework (.jsx, .tsx, .vue, .svelte) reste hors périmètre — c est une expression du langage,
# pas un attribut du gabarit, et le juger ici produirait du faux positif. Leurs DESTINATIONS
# littérales, elles, sont lues depuis TF-0283 (voir `EXTENSIONS_COMPOSANTS` plus bas).
EXTENSIONS = (".html", ".htm", ".jinja", ".jinja2", ".j2", ".twig", ".ejs", ".hbs")
EXTENSIONS_JS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte")
# TF-0283 : composants dont les liens à destination LITTÉRALE sont jugés.
#
# TF-0295 (levée 2) — Vue et Svelte entrent, chacun avec SA grammaire (voir `_GRAMMAIRES`). La
# limite d origine était juste : prétendre lire `:to="lien"` avec le scanner JSX aurait pris une
# expression pour un littéral et accusé un lien sain. Elle se lève en DÉCLARANT les dialectes,
# pas en élargissant le scanner à l aveugle.
EXTENSIONS_COMPOSANTS = (".jsx", ".tsx", ".vue", ".svelte")
_EXCLUS = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages", "dist", "build",
    ".next", ".nuxt", ".svelte-kit", ".visuel", "htmlcov", "coverage", ".tox", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", "vendor", ".forge",
    # RT-9/RT-10 (lot bourse-aux-vacants 20260814a) : les dossiers d ARTEFACTS de la convention
    # pilot — `output\` (regle 16 : tout livrable date y est copie), ses archives `old\`/`Old\`
    # et les PNG d oracles. Sans eux, ce pan inventoriait les DASHBOARDS produits par
    # forge-tests elle-meme : 6 -> 27 elements entre deux audits sans qu une ligne de gabarit
    # change. Trois defauts en un : auto-audit (G-1), inventaire qui recompense l accumulation,
    # et mesure non reproductible apres rangement.
    "output", "old", "Old", ".oracles",
    # TF-0218 (RT-4, lot COMPTA 20260814a) : `forge\` est le dossier de RUN du pilot, jamais du
    # produit. La convention ETAPES-RUN y archive les livrables du cycle N-1
    # (`forge\etapes\tests\livrables\` : dashboards HTML, cahiers de tests), que ce pan
    # inventoriait ensuite comme surface du produit au cycle N — 344 elements au cycle 2 dont
    # 262 issus de ces archives, contre 82 elements produit au cycle 1. Meme defaut que RT-9,
    # meme remede : la mesure est POLLUEE et, pire, CROISSANTE a chaque cycle — un produit
    # inchange verrait sa surface grossir indefiniment du seul fait d avoir ete audite.
    "forge",
}
_PLAFOND_JS = 8_000_000  # octets de corpus JS lus ; au-delà, la troncature est DÉCLARÉE

NON_JUGE = [
    "interface : controle STATIQUE — un gestionnaire pose a l execution par un framework "
    "(React, Vue, delegation d evenement sur un ancetre, composant compile) est INVISIBLE ici ; "
    "un element declare inerte doit etre lu comme « aucun cablage lisible dans les sources »",
    "interface : un element juge cable ne l est que par PRESUMPTION — son identifiant, sa "
    "classe ou son attribut de donnees est cite dans le JS du projet. La coincidence de chaine "
    "suffit a le blanchir : le pan attrape l inerte flagrant, il ne certifie pas le cable",
    "interface : le cablage prouve l existence d un gestionnaire, jamais que son effet soit "
    "OBSERVABLE par l utilisateur — un handler vide passerait pour cable",
    # TF-0295, levee 2 : Vue et Svelte rejoignent React, chacun avec sa grammaire declaree.
    "interface : les composants de framework (.jsx, .tsx, .vue, .svelte) ne sont pas analyses "
    "comme gabarits — seule la DESTINATION litterale de leurs liens est jugee (TF-0283, etendu "
    "a `.vue` et `.svelte` par TF-0295) ; leur CABLAGE reste hors perimetre et leur surface est "
    "inventoriee par le pan front via `data-testid`",
    "interface : une ancre `#nom` dont la cible n existe pas dans le document n est pas jugee "
    "morte — la cible peut etre injectee au rendu",
    # TF-0283 — les limites du controle des liens de composants, chacune payee d un faux verdict
    # possible si elle etait tue.
    "interface/liens : une destination EXPRIMEE (`href={chemin}`, template avec `${...}`, "
    "constante importee) n est pas resolue — elle est comptee et declaree NON JUGEE, jamais "
    "supposee bonne ni mauvaise",
    "interface/liens : un lien RELATIF (sans `/` initial) n est pas juge — sa resolution depend "
    "de l URL de rendu, que l analyse statique ne connait pas",
    "interface/liens : l existence d une destination se juge sur l arborescence ENUMEREE "
    "(routes Next `app/`+`pages/`, tables react-router et TanStack, gabarits et fichiers "
    "`public/`) ; une route posee a l execution ou par un proxy est invisible ici, et si aucune "
    "route n est enumerable le controle d existence est DESACTIVE plutot que devine",
    # TF-0295, levee 4 : la CONFIGURATION du framework est lue elle aussi, et l absence de
    # locale opposable suspend le jugement au lieu de le deviner.
    "interface/liens : la locale d un composant est deduite de son arborescence ou de son nom "
    "(`.../en/Header.tsx`, `HeaderEn.tsx`), et les locales OPPOSABLES sont lues dans "
    "l arborescence litterale ET dans la configuration du framework (`locales: [...]` de Next, "
    "nuxt, next-intl — TF-0295) ; un composant qui rend PLUSIEURS locales selon une prop n a pas "
    "de locale propre et ses liens ne sont pas juges sur ce critere. Quand le produit route ses "
    "locales par un segment DYNAMIQUE sans les declarer, aucune racine de locale n est "
    "connaissable : logo, bascule de langue et coherence de locale sont alors NON JUGES, et le "
    "rapport le dit — les deviner accusait un logo correct",
    "interface/liens : les grammaires de destination sont DECLAREES par dialecte — React "
    "(`href`, `to`, expression `{...}`), Vue (`to`, `:to`, `v-bind:href`, la forme liee etant "
    "toujours EXPRIMEE) et Svelte (`href`, interpolation dans la chaine). Un dialecte absent de "
    "la table (Angular, Astro, Solid) n est pas lu, et un attribut de destination pose par une "
    "bibliotheque de routage inconnue non plus",
    "interface/liens : « logo » et « bascule de langue » sont reconnus par HEURISTIQUE — mention "
    "de `logo` dans le contenu du lien, libelle egal a un nom de langue ou attribut `hrefLang`. "
    "Un logo sans le mot `logo` ni `hrefLang` echappe au controle, et le lien ainsi reconnu se "
    "conteste comme tout constat (`declarations`)",
    "interface/liens : le libelle d un lien est lu jusqu a la premiere fermeture de meme balise ; "
    "un lien qui en imbrique un autre de meme nom verrait son libelle tronque",
    # TF-0288 — les frontieres du controle d ecart servi/versionne, chacune payee d un faux
    # verdict possible si elle etait tue.
    "interface/ecart-servi : le controle compare les entrees de NAVIGATION — les liens vivant "
    "dans un `<nav>` LITTERAL, des deux cotes (composant source et page servie). Un menu rendu "
    "par un composant `<Nav>`, marque `role=\"navigation\"` ou construit a l execution echappe "
    "aux deux lecteurs : c est voulu, les deux cotes doivent voir la meme chose sous peine de "
    "mesurer l ecart des lecteurs et non celui du produit",
    "interface/ecart-servi : la comparaison n est pas symetrique — une entree SERVIE qu aucune "
    "source ne promet n est PAS jugee. Elle peut venir d un autre composant, d un gabarit rendu "
    "cote serveur ou d une forme de menu non reconnue : l accuser serait accuser la limite du "
    "lecteur. Seul le manque de ce que la source PROMET est un constat",
    "interface/ecart-servi : le terme « versionne » est le WORKING TREE, pas une reference git — "
    "un produit hors git n a donc pas de version opposable, seulement des fichiers. Le contrôle "
    "reste jouable et le dit ; poser git est le prealable, pas ce controle",
    "interface/ecart-servi : la confrontation porte sur la page d ACCUEIL de chaque locale "
    "servie. Un menu qui differerait sur une page profonde seulement n est pas vu — c est le cas "
    "fondateur (INS-0001) qui fixe ce perimetre, ou les 36 pages EN partageaient le meme "
    "composant",
    "interface/ecart-servi : une destination EXPRIMEE d un composant n entre pas dans les "
    "entrees promises — comparer ce qu on n a pas resolu accuserait un deploiement correct",
]

# Attributs qui portent un gestionnaire, tous dialectes confondus.
_PREFIXES_HANDLER = (
    "on", "@", "v-on:", "x-on:", "x-bind:", "hx-", "wire:", "ng-", "data-action",
    "data-controller", "data-bs-toggle", "data-toggle", "data-turbo", "up-", "formaction",
)
_HREF_MORTS = ("", "#", "javascript:", "javascript:void(0)", "javascript:void(0);", "javascript:;")
_TYPES_INTERACTIFS = ("submit", "button", "reset", "image")


class _Lecteur(HTMLParser):
    """Relève les affordances d un gabarit : boutons, liens, formulaires — avec leur ligne."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.affordances: list[dict] = []
        self.ancres: set[str] = set()
        self.scripts: list[str] = []
        self._ouverts: list[dict] = []
        self._formulaires: list[dict] = []
        self._dans_script = False

    # -- collecte -------------------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        table = {nom.lower(): (valeur or "") for nom, valeur in attrs}
        if table.get("id"):
            self.ancres.add(table["id"])
        if tag == "script":
            self._dans_script = True
            return
        if tag == "form":
            entree = self._nouvelle(tag, table)
            self._formulaires.append(entree)
            self._ouverts.append(entree)
            return
        if tag in ("button", "a"):
            entree = self._nouvelle(tag, table)
            self._ouverts.append(entree)
            return
        if tag == "input" and table.get("type", "").lower() in _TYPES_INTERACTIFS:
            entree = self._nouvelle(tag, table)
            entree["libelle"] = table.get("value") or table.get("alt") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._dans_script = False
            return
        if tag == "form" and self._formulaires:
            self._formulaires.pop()
        for indice in range(len(self._ouverts) - 1, -1, -1):
            if self._ouverts[indice]["tag"] == tag:
                del self._ouverts[indice:]
                return

    def handle_data(self, data: str) -> None:
        if self._dans_script:
            self.scripts.append(data)
            return
        for entree in self._ouverts:
            if entree["tag"] in ("button", "a"):
                entree["libelle"] = (entree["libelle"] + " " + data).strip()

    # -- interne --------------------------------------------------------------------------
    def _nouvelle(self, tag: str, table: dict[str, str]) -> dict:
        entree = {
            "tag": tag,
            "attributs": table,
            "ligne": self.getpos()[0],
            "libelle": table.get("aria-label") or table.get("title") or "",
            "formulaire": self._formulaires[-1] if self._formulaires else None,
        }
        self.affordances.append(entree)
        return entree


def _fichiers(cible: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Fichiers du projet, artefacts de construction et dépendances tierces exclus."""
    retenus: list[Path] = []
    for chemin in sorted(cible.rglob("*")):
        if chemin.suffix.lower() not in extensions or not chemin.is_file():
            continue
        if any(partie in _EXCLUS for partie in chemin.parts):
            continue
        retenus.append(chemin)
    return retenus


def _corpus_js(cible: Path) -> tuple[str, bool]:
    """Tout le JavaScript du projet, concaténé. Le second membre dit s il a été tronqué."""
    morceaux: list[str] = []
    volume = 0
    for chemin in _fichiers(cible, EXTENSIONS_JS):
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        volume += len(texte)
        if volume > _PLAFOND_JS:
            return "\n".join(morceaux), True
        morceaux.append(texte)
    return "\n".join(morceaux), False


def _cite(jeton: str, corpus: str) -> bool:
    """Le jeton est-il cité dans le code ? Sous trois caractères, le hasard décide — on refuse."""
    jeton = (jeton or "").strip()
    if len(jeton) < 3:
        return False
    return re.search(rf"(?<![\w-]){re.escape(jeton)}(?![\w-])", corpus) is not None


def _a_un_handler(table: dict[str, str]) -> bool:
    return any(nom.startswith(_PREFIXES_HANDLER) for nom in table)


def _cite_par_le_code(table: dict[str, str], corpus: str) -> bool:
    """Identifiant, classe ou attribut de données de l élément, cité quelque part dans le JS."""
    if _cite(table.get("id", ""), corpus):
        return True
    for classe in table.get("class", "").split():
        if _cite(classe, corpus):
            return True
    for nom in table:
        if not nom.startswith("data-"):
            continue
        suffixe = nom[5:]
        chameau = re.sub(r"-(\w)", lambda m: m.group(1).upper(), suffixe)
        if _cite(nom, corpus) or _cite(chameau, corpus):
            return True
    return False


def _formulaire_cable(formulaire: dict | None, corpus: str) -> bool:
    if formulaire is None:
        return False
    table = formulaire["attributs"]
    action = table.get("action", "").strip()
    if action and action not in ("#",):
        return True
    return _a_un_handler(table) or _cite_par_le_code(table, corpus)


def _juger(entree: dict, corpus: str) -> str | None:
    """None si l affordance est câblée ; sinon le motif de son inertie, en clair."""
    table = entree["attributs"]
    if "disabled" in table or table.get("aria-disabled") == "true":
        return None  # inertie VOULUE et déclarée : ce n est pas une promesse non tenue
    if _a_un_handler(table):
        return None

    if entree["tag"] == "a":
        href = table.get("href")
        if href is None:
            return "lien sans attribut href : aucune destination, aucun effet"
        cible = href.strip()
        if cible.lower() in _HREF_MORTS or cible.lower().startswith("javascript:void"):
            if _cite_par_le_code(table, corpus):
                return None
            return f"lien dont href vaut « {cible or '(vide)'} » : aucune destination réelle"
        return None

    if entree["tag"] == "form":
        if _formulaire_cable(entree, corpus):
            return None
        return "formulaire sans action ni gestionnaire de soumission : rien n'est envoyé"

    # button et input[type=submit|button|reset|image]
    type_ = table.get("type", "").lower()
    if type_ == "reset":
        return None  # effet natif garanti par le navigateur
    dans_formulaire = entree["formulaire"] is not None or bool(table.get("form"))
    # HTML : un bouton sans `type` dans un formulaire vaut `submit`.
    soumet = type_ == "submit" or (type_ == "" and dans_formulaire)
    if soumet and entree["formulaire"] is not None:
        if _formulaire_cable(entree["formulaire"], corpus):
            return None
        return (
            "bouton de soumission d'un formulaire lui-même sans action ni gestionnaire : "
            "le clic n'envoie rien"
        )
    if soumet and table.get("form"):
        return None  # rattache a un formulaire nomme ailleurs : hors de portee, non accuse
    if _cite_par_le_code(entree["attributs"], corpus):
        return None
    return "bouton sans type submit, sans gestionnaire et jamais référencé par le code"


def _libelle(entree: dict) -> str:
    texte = " ".join((entree["libelle"] or "").split())
    return texte[:60] or f"<{entree['tag']}> sans libellé"


# --- Liens des composants React (TF-0283) -----------------------------------------------------
# Tout ce qui suit ne lit QUE du littéral. Une valeur exprimée n est pas résolue, elle est
# comptée et déclarée : c est la seule façon d ajouter un contrôle sans ajouter de faux verdict.

_BALISES_LIEN = ("a", "Link", "NavLink")
_ATTRIBUTS_DESTINATION = ("href", "to")

# TF-0295 (levée 2) — une grammaire par dialecte, DÉCLARÉE. Trois choses la définissent : les
# balises qui portent un lien, les attributs qui portent sa destination, et les formes d attribut
# qui sont des EXPRESSIONS par nature (`:to` de Vue, `v-bind:href`). Une expression n est jamais
# jugée : elle est comptée et déclarée, exactement comme `href={x}` en JSX.
_GRAMMAIRES: dict[str, dict[str, tuple[str, ...]]] = {
    ".jsx": {"balises": _BALISES_LIEN, "destinations": _ATTRIBUTS_DESTINATION, "liees": ()},
    ".tsx": {"balises": _BALISES_LIEN, "destinations": _ATTRIBUTS_DESTINATION, "liees": ()},
    # Vue : `<router-link to="/en">` est littéral, `<router-link :to="lien">` est une expression.
    # `<nuxt-link>` suit la même grammaire. Le `<a href>` d un `<template>` est du HTML ordinaire.
    ".vue": {
        "balises": ("a", "router-link", "RouterLink", "nuxt-link", "NuxtLink", "NuxtLinkLocale"),
        "destinations": _ATTRIBUTS_DESTINATION,
        "liees": (":href", ":to", "v-bind:href", "v-bind:to"),
    },
    # Svelte : la destination est un attribut HTML, l interpolation se fait par `{...}` — dans
    # l attribut nu (`href={x}`) comme dans la chaîne (`href="{x}"`). Les deux se déclarent.
    ".svelte": {
        "balises": ("a", "Link", "NavLink"),
        "destinations": _ATTRIBUTS_DESTINATION,
        "liees": (),
    },
}
# Le nom d attribut accepte `:` et `@` en tête : ce sont les liaisons de Vue (`:to`, `@click`).
# Sans cela, `:to="lien"` était lu comme `to="lien"` — une expression prise pour un littéral,
# donc un lien sain accusé de pointer vers « lien ». C est le faux positif exact que la limite
# d origine de TF-0283 évitait en ne lisant pas Vue du tout.
_NOM_ATTRIBUT = re.compile(r"[A-Za-z_:@][-\w:.]*")
# Une valeur de chaîne qui porte une interpolation n est pas un littéral (Svelte, Angular…).
_INTERPOLATION = re.compile(r"\{[^{}]*\}|\$\{")
_ESPACES = " \t\r\n"
_EXTENSIONS_ROUTE = (".js", ".jsx", ".ts", ".tsx")
# Codes ISO 639-1 des langues qu un site multilingue préfixe couramment. La liste est FERMÉE, et
# c est délibéré : prendre `/id/42` ou `/no/…` pour une locale sur un site qui n en a pas
# fabriquerait un faux positif de LOCALE, c est-à-dire le pire des constats — celui qui accuse un
# lien juste. Une locale non listée fait retomber le contrôle en non jugé, jamais en verdict.
_LOCALES_CONNUES = frozenset(
    ("en", "fr", "de", "es", "it", "nl", "pt", "pl", "ru", "ja", "zh", "ar", "sv", "da", "fi",
     "cs", "tr", "ko", "el", "he", "hu", "ro", "uk")
)
# Libellé d un lien -> locale qu il promet d atteindre. Sert à reconnaître une bascule de langue.
_NOMS_DE_LANGUE = {
    "francais": "fr", "français": "fr", "french": "fr", "fr": "fr",
    "english": "en", "anglais": "en", "en": "en",
    "deutsch": "de", "allemand": "de", "german": "de", "de": "de",
    "espanol": "es", "español": "es", "espagnol": "es", "spanish": "es", "es": "es",
    "italiano": "it", "italien": "it", "italian": "it", "it": "it",
    "nederlands": "nl", "neerlandais": "nl", "néerlandais": "nl", "dutch": "nl", "nl": "nl",
    "portugues": "pt", "português": "pt", "portugais": "pt", "pt": "pt",
}
# Destinations qui sortent du périmètre d un contrôle d arborescence LOCALE.
_HORS_PERIMETRE = ("http://", "https://", "//", "mailto:", "tel:", "sms:", "data:", "#", "?")


def _fin_de_chaine(texte: str, depart: int) -> int | None:
    """Index du guillemet fermant de la chaîne ouverte en `depart` (échappements respectés)."""
    guillemet = texte[depart]
    indice = depart + 1
    while indice < len(texte):
        if texte[indice] == "\\":
            indice += 2
            continue
        if texte[indice] == guillemet:
            return indice
        indice += 1
    return None


def _fin_expression(texte: str, depart: int) -> int | None:
    """Index de l accolade fermante de l expression ouverte en `depart`, imbrications comprises."""
    profondeur = 0
    indice = depart
    while indice < len(texte):
        caractere = texte[indice]
        if caractere in "\"'`":
            fin = _fin_de_chaine(texte, indice)
            if fin is None:
                return None
            indice = fin + 1
            continue
        if caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur -= 1
            if profondeur == 0:
                return indice
        indice += 1
    return None


def _fin_de_balise(texte: str, depart: int) -> int | None:
    """Index du `>` qui ferme la balise ouverte en `depart`.

    Un `>` vit aussi dans `onClick={() => f()}` et dans une chaîne : le scanner suit donc les
    accolades et les chaînes. Une regex `<a[^>]*>` coupait la balise au milieu d une fonction
    fléchée et perdait le `href` qui suivait — un lien faux passé pour absent.
    """
    profondeur = 0
    indice = depart
    while indice < len(texte):
        caractere = texte[indice]
        if caractere in "\"'`":
            fin = _fin_de_chaine(texte, indice)
            if fin is None:
                return None
            indice = fin + 1
            continue
        if caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur = max(0, profondeur - 1)
        elif caractere == ">" and profondeur == 0:
            return indice
        indice += 1
    return None


def _litteral(expression: str) -> str | None:
    """Valeur d une expression JSX quand elle est LITTÉRALE ; None quand elle est calculée."""
    texte = expression.strip()
    if len(texte) >= 2 and texte[0] == texte[-1] and texte[0] in "\"'":
        return texte[1:-1]
    if len(texte) >= 2 and texte[0] == texte[-1] == "`" and "${" not in texte:
        return texte[1:-1]
    return None


def _attributs_jsx(fragment: str) -> dict[str, str | None]:
    """Attributs d une balise JSX — nom -> valeur littérale, ou None si la valeur est CALCULÉE.

    La distinction est le cœur du contrôle : `href="/en"` se juge, `href={lien}` se déclare.
    """
    table: dict[str, str | None] = {}
    indice, taille = 0, len(fragment)
    while indice < taille:
        trouve = _NOM_ATTRIBUT.match(fragment, indice)
        if trouve is None:
            indice += 1
            continue
        nom = trouve.group(0)
        indice = trouve.end()
        while indice < taille and fragment[indice] in _ESPACES:
            indice += 1
        if indice >= taille or fragment[indice] != "=":
            table.setdefault(nom, "")  # attribut booléen JSX (`disabled`)
            continue
        indice += 1
        while indice < taille and fragment[indice] in _ESPACES:
            indice += 1
        if indice >= taille:
            break
        caractere = fragment[indice]
        if caractere in "\"'":
            fin = _fin_de_chaine(fragment, indice)
            if fin is None:
                break
            table[nom] = fragment[indice + 1:fin]
            indice = fin + 1
        elif caractere == "{":
            fin = _fin_expression(fragment, indice)
            if fin is None:
                break
            table[nom] = _litteral(fragment[indice + 1:fin])
            indice = fin + 1
        else:
            table.setdefault(nom, "")
    return table


def _texte_visible(fragment: str) -> str:
    """Texte lisible d un fragment JSX : balises et expressions ôtées."""
    sans_balises = re.sub(r"<[^>]*>", " ", fragment)
    sans_expressions = re.sub(r"\{[^{}]*\}", " ", sans_balises)
    return " ".join(sans_expressions.split())


def _spans_de_nav(texte: str) -> list[tuple[int, int]]:
    """Intervalles (début, fin) des éléments `<nav>` du composant — TF-0288.

    Seul le `<nav>` LITTÉRAL est reconnu, et c est délibéré : c est exactement ce que le lecteur
    du build servi reconnaît lui aussi (`i18n._Page`). Les deux côtés de la comparaison doivent
    voir la même chose, sinon l écart mesuré serait celui des deux lecteurs, pas celui du
    produit. Un menu rendu par un composant `<Nav>` ou marqué `role="navigation"` échappe donc
    aux deux, et c est déclaré.
    """
    spans: list[tuple[int, int]] = []
    for ouverture in re.finditer(r"<nav(?=[\s/>])", texte, flags=re.IGNORECASE):
        fermeture = texte.lower().find("</nav", ouverture.end())
        spans.append((ouverture.start(), fermeture if fermeture != -1 else len(texte)))
    return spans


def _liens_jsx(texte: str, grammaire: dict[str, tuple[str, ...]] | None = None) -> list[dict]:
    """Liens d un composant, avec leur destination littérale (ou None si calculée).

    `grammaire` déclare les balises, les attributs de destination et les formes LIÉES du dialecte
    (TF-0295, levée 2). Par défaut : React, la grammaire d origine de TF-0283.
    """
    regles = grammaire or _GRAMMAIRES[".jsx"]
    navs = _spans_de_nav(texte)
    liens: list[dict] = []
    for balise in regles["balises"]:
        for ouverture in re.finditer(rf"<{re.escape(balise)}(?=[\s/>])", texte):
            fin = _fin_de_balise(texte, ouverture.end())
            if fin is None:
                continue
            attributs = _attributs_jsx(texte[ouverture.end():fin])
            destination: str | None = None
            exprimee = False
            # Les formes LIÉES d abord : `:to="lien"` et `to="/en"` peuvent cohabiter, et c est
            # la liée qui gagne à l exécution. La lire en second aurait jugé la morte.
            for nom in (*regles["liees"], *regles["destinations"]):
                if nom not in attributs:
                    continue
                valeur = attributs[nom]
                if valeur is None or nom in regles["liees"] or _INTERPOLATION.search(valeur):
                    exprimee = True
                else:
                    destination = valeur
                break
            fermeture = texte.find(f"</{balise}", fin)
            contenu = texte[fin + 1:fermeture] if fermeture != -1 else ""
            liens.append(
                {
                    "tag": balise,
                    "ligne": texte.count("\n", 0, ouverture.start()) + 1,
                    "attributs": attributs,
                    "destination": destination,
                    "exprimee": exprimee,
                    # TF-0288 : ce lien est-il une entrée de NAVIGATION ? Le contrôle d écart
                    # servi ↔ versionné compare des menus, et un lien de pied de page ou de
                    # corps de texte n en est pas un — les mélanger produirait un écart massif
                    # et faux dès le premier produit.
                    "dans_nav": any(
                        debut < ouverture.start() < fin for debut, fin in navs
                    ),
                    "contenu": contenu,
                    "libelle": _texte_visible(contenu)
                    or attributs.get("aria-label")
                    or attributs.get("title")
                    or "",
                }
            )
    return sorted(liens, key=lambda lien: lien["ligne"])


# --- Arborescence des destinations -------------------------------------------------------------
def _segments_next(parties: tuple[str, ...]) -> list[str]:
    """Segments d URL d un chemin de fichier Next : groupes ôtés, paramètres templatés."""
    segments: list[str] = []
    for partie in parties:
        if partie in (".", "") or partie.startswith("@"):
            continue
        if partie.startswith("(") and partie.endswith(")"):
            continue  # groupe de routes : structure l arborescence, n apparaît pas dans l URL
        if partie.startswith(("[[", "[...")):
            segments.append("*")  # segment attrape-tout : `[[...slug]]`, `[...slug]`
        elif partie.startswith("["):
            segments.append(":" + partie.strip("[]."))
        else:
            segments.append(partie)
    return segments


def _routes_next(cible: Path) -> list[str]:
    """Routes déclarées par l arborescence Next — App Router (`app/`) et Pages Router (`pages/`).

    Les deux conventions cohabitent dans un même dépôt ; les lire toutes deux évite de conclure
    « aucune route » sur un produit qui en a deux cents.
    """
    routes: list[str] = []
    for fichier in _fichiers(cible, _EXTENSIONS_ROUTE):
        parties = fichier.parts
        if fichier.stem == "page" and "app" in parties:
            rang = len(parties) - 1 - parties[::-1].index("app")
            segments = _segments_next(parties[rang + 1:-1])
            routes.append("/" + "/".join(segments) if segments else "/")
            continue
        if "pages" in parties:
            rang = len(parties) - 1 - parties[::-1].index("pages")
            reste = list(parties[rang + 1:-1]) + [fichier.stem]
            if reste and reste[0] == "api":
                continue
            if any(nom.startswith("_") for nom in reste):
                continue
            if reste and reste[-1] == "index":
                reste = reste[:-1]
            segments = _segments_next(tuple(reste))
            routes.append("/" + "/".join(segments) if segments else "/")
    return routes


def _pages_statiques(cible: Path) -> list[str]:
    """Destinations servies telles quelles : gabarits `.html` et fichiers de `public/`."""
    chemins: list[str] = []
    for fichier in _fichiers(cible, (".html", ".htm")):
        relatif = fichier.relative_to(cible).as_posix()
        chemins.append("/" + relatif)
        if fichier.stem == "index":
            parent = fichier.parent.relative_to(cible).as_posix()
            chemins.append("/" + parent if parent != "." else "/")
        else:
            chemins.append("/" + relatif.rsplit(".", 1)[0])
    # `public/` est cherché à la racine et un niveau dessous (`frontend/public`, `apps/web/public`)
    # — pas par un `rglob` sur tout l arbre : `node_modules` contient des centaines de `public/`
    # qu il faudrait traverser pour tous les écarter.
    candidats = [cible / "public"]
    for enfant in sorted(cible.iterdir()) if cible.is_dir() else []:
        if enfant.is_dir() and enfant.name not in _EXCLUS:
            candidats.append(enfant / "public")
    for dossier in candidats:
        if not dossier.is_dir():
            continue
        for fichier in sorted(dossier.rglob("*")):
            if fichier.is_file():
                chemins.append("/" + fichier.relative_to(dossier).as_posix())
    return chemins


def _normaliser(destination: str) -> str:
    """Chemin comparable : requête et ancre ôtées, barre finale ôtée (sauf la racine)."""
    chemin = destination.split("?")[0].split("#")[0].strip()
    if len(chemin) > 1 and chemin.endswith("/"):
        chemin = chemin.rstrip("/")
    return chemin or "/"


def _routes_declarees_par_le_front(cible: Path) -> list[str]:
    """Routes que le pan `front` sait déjà lire (table `routes.jsx`, TanStack, react-router).

    Réutilisées telles quelles : les redécouvrir ici ferait diverger deux lectures de la même
    table de routage, et un lien serait « cassé » pour un pan et sain pour l autre.
    """
    from forge_tests.adaptateurs import front

    try:
        inventaire_front = front.inventaire(cible)
    except Exception:  # noqa: BLE001 — table illisible : le pan le dit, il ne tombe pas
        return []
    return [e.id.split(":", 1)[1] for e in inventaire_front if e.id.startswith("route:")]


# --- Locales DÉCLARÉES par la configuration du framework (TF-0295, levée 4) --------------------
# La locale d un composant était déduite de la seule arborescence LITTÉRALE. Or un produit Next
# internationalisé ne porte aucun segment de locale littéral : ses routes vivent sous
# `app/[locale]/…`, et la liste des locales est DÉCLARÉE dans la configuration. Conséquence
# mesurée sur ce patron : `arbre["locales"]` sortait VIDE, donc `HeaderEn.tsx` n avait plus de
# locale reconnaissable, donc les contrôles de logo, de bascule et de cohérence de locale étaient
# tous DÉSACTIVÉS — sur le patron d application le plus courant, et sans que rien ne le dise.
# C est exactement la configuration d INS-0001.
_FICHIERS_CONFIG_LOCALES = (
    "next.config.js", "next.config.mjs", "next.config.cjs", "next.config.ts",
    "i18n.js", "i18n.ts", "i18n.config.js", "i18n.config.ts",
    "i18n/routing.ts", "i18n/routing.js", "src/i18n/routing.ts", "src/i18n/routing.js",
    "i18n/request.ts", "src/i18n/request.ts",
    "nuxt.config.ts", "nuxt.config.js", "svelte.config.js",
)
# `locales: ['fr', 'en']`, `locales = ["fr","en"]`, `defaultLocale: 'fr'`. Seul le LITTÉRAL est lu :
# une liste construite à l exécution n est pas devinée.
_LOCALES_CONFIG = re.compile(r"locales\s*[:=]\s*\[([^\]]*)\]", re.IGNORECASE)
_LOCALE_DEFAUT_CONFIG = re.compile(
    r"default(?:Locale|Lang)\s*[:=]\s*[\"'`]([A-Za-z-]{2,5})[\"'`]", re.IGNORECASE
)
_CHAINE_SIMPLE = re.compile(r"[\"'`]([A-Za-z-]{2,5})[\"'`]")
# Segment dynamique de locale : il PROUVE que le produit est internationalisé par configuration,
# mais il ne dit pas quelles locales — c est la configuration qui les nomme.
_SEGMENTS_DYNAMIQUES_LOCALE = ("[locale]", "[lang]", "[lng]", "[...locale]", "[[...locale]]")


def locales_declarees(cible: Path) -> set[str]:
    """Locales que la CONFIGURATION du framework déclare — jamais devinées.

    Filtrées par `_LOCALES_CONNUES` pour la même raison que partout ailleurs ici : prendre une
    valeur quelconque pour une locale fabriquerait une parité imaginaire, donc des constats contre
    des liens sains.
    """
    trouvees: set[str] = set()
    for nom in _FICHIERS_CONFIG_LOCALES:
        fichier = cible / nom
        if not fichier.is_file():
            continue
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for corps in _LOCALES_CONFIG.findall(texte):
            trouvees |= {
                code.lower()
                for code in _CHAINE_SIMPLE.findall(corps)
                if code.split("-")[0].lower() in _LOCALES_CONNUES
            }
        for code in _LOCALE_DEFAUT_CONFIG.findall(texte):
            if code.split("-")[0].lower() in _LOCALES_CONNUES:
                trouvees.add(code.split("-")[0].lower())
    return {code.split("-")[0] for code in trouvees}


def _locale_par_configuration(cible: Path) -> bool:
    """Le produit route-t-il ses locales par un segment DYNAMIQUE (`app/[locale]/…`) ?"""
    return any(
        partie in _SEGMENTS_DYNAMIQUES_LOCALE
        for fichier in _fichiers(cible, _EXTENSIONS_ROUTE)
        for partie in fichier.parts
    )


def _arborescence(cible: Path) -> dict:
    """Ce que le projet DÉCLARE comme destinations atteignables, et les locales qu il préfixe."""
    from forge_tests.adaptateurs import front

    declarees: list[str] = list(_routes_next(cible))
    declarees += _routes_declarees_par_le_front(cible)
    declarees += _pages_statiques(cible)

    chemins = {_normaliser(route) for route in declarees if route.startswith("/")}
    motifs = [
        front.motif_de_route(route)
        for route in {r for r in declarees if r.startswith("/") and (":" in r or "*" in r)}
    ]
    litterales = {
        segment
        for chemin in chemins
        for segment in [chemin.split("/")[1] if chemin.count("/") >= 1 else ""]
        if segment in _LOCALES_CONNUES
    }
    # TF-0295 (levée 4) : l arborescence littérale ET la configuration. Les deux sources sont
    # tenues à part pour que le rapport puisse DIRE laquelle a parlé — « aucune locale » et
    # « locales lues dans next.config » ne sont pas le même rapport.
    configurees = locales_declarees(cible)
    return {
        "chemins": chemins,
        "motifs": motifs,
        "locales": litterales | configurees,
        "locales_litterales": litterales,
        "locales_configurees": configurees,
        "routage_dynamique": _locale_par_configuration(cible),
    }


def _connue(destination: str, arbre: dict) -> bool:
    if destination in arbre["chemins"]:
        return True
    if f"{destination}/index.html" in arbre["chemins"]:
        return True
    return any(motif.match(destination) for motif in arbre["motifs"])


def _locale_du_composant(fichier: Path, cible: Path, locales: set[str]) -> str | None:
    """Locale que ce composant SERT — depuis son arborescence, sinon depuis son nom."""
    parties = fichier.relative_to(cible).parts
    for partie in parties[:-1]:
        if partie.lower() in locales:
            return partie.lower()
    tige = fichier.stem
    for locale in sorted(locales):
        if re.search(rf"(?:^|[-_.]){locale}$", tige, flags=re.IGNORECASE):
            return locale
        if tige.endswith(locale.capitalize()) or tige.endswith(locale.upper()):
            return locale
    return None


def _locale_de_la_destination(destination: str, locales: set[str]) -> str | None:
    """Locale préfixant une destination — None quand elle est servie sans préfixe (locale par
    défaut du site)."""
    segment = destination.split("/")[1] if destination.count("/") >= 1 else ""
    return segment if segment in locales else None


def _racine_de_locale(locale: str | None, locales: set[str]) -> str:
    return f"/{locale}" if locale and locale in locales else "/"


def _prefixer(destination: str, locale: str, locales: set[str]) -> str:
    """La même destination, servie dans `locale`."""
    actuelle = _locale_de_la_destination(destination, locales)
    reste = destination[len(f"/{actuelle}"):] if actuelle else destination
    return _normaliser(f"/{locale}{reste}" if reste != "/" else f"/{locale}")


def _langue_visee(lien: dict) -> str | None:
    """Locale qu un lien PROMET d atteindre : bascule de langue déclarée ou libellée."""
    attributs = lien["attributs"]
    for nom in ("hrefLang", "hreflang", "lang"):
        valeur = attributs.get(nom)
        if valeur:
            code = valeur.split("-")[0].lower()
            if code in _LOCALES_CONNUES:
                return code
    libelle = (lien["libelle"] or "").strip().lower()
    return _NOMS_DE_LANGUE.get(libelle)


def _porte_un_logo(lien: dict) -> bool:
    """Le lien enveloppe-t-il le logo du site ? Heuristique DÉCLARÉE, contestable comme telle."""
    matiere = " ".join(
        [lien["contenu"], *(str(v) for v in lien["attributs"].values() if v)]
    ).lower()
    return "logo" in matiere


def _juger_lien(lien: dict, locale_composant: str | None, arbre: dict) -> str | None:
    """None si le lien tient sa promesse ; sinon le motif, en clair."""
    destination = lien["destination"]
    if destination is None:
        return None  # destination exprimée : comptée en non jugé, jamais accusée
    chemin = _normaliser(destination)
    if not chemin.startswith("/") or chemin.lower().startswith(_HORS_PERIMETRE):
        return None  # externe, protocole, ancre ou lien relatif : hors de portée déclarée
    locales = arbre["locales"]

    # 1. La destination existe-t-elle ? Contrôle DÉSACTIVÉ si rien n a pu être énuméré : accuser
    #    tous les liens d un projet dont on n a pas su lire les routes serait le faux positif
    #    massif que ce pan existe pour ne pas produire.
    if arbre["chemins"] and not _connue(chemin, arbre):
        return (
            f"destination « {chemin} » absente de l arborescence : ni route déclarée, ni page "
            "servie"
        )

    # TF-0295 (levée 4) — les trois contrôles qui suivent ont tous besoin de la RACINE d une
    #    locale, et cette racine n est connaissable que si les locales le sont. Sur un produit qui
    #    route ses locales par un segment DYNAMIQUE (`app/[locale]/…`) sans les déclarer nulle
    #    part, affirmer que l accueil d un composant est « / » est une DEVINETTE — et elle
    #    accusait un `HeaderEn.tsx` dont le logo pointe correctement vers `/en`. Le jugement se
    #    SUSPEND donc, et la suspension se déclare au rapport (`_declarations_de_composants`) :
    #    un cas non résolu dégrade en non jugé motivé, jamais en finding.
    if arbre.get("routage_dynamique") and not locales:
        return None

    # 2. Le logo — sa cible est CONNUE D AVANCE : la racine de la locale qu il sert. Un logo qui
    #    mène à une page profonde emmène tout le site sur cette page, depuis chaque écran.
    if _porte_un_logo(lien):
        attendue = _racine_de_locale(locale_composant, locales)
        if chemin != attendue:
            return (
                f"lien du logo vers « {chemin} » au lieu de l'accueil « {attendue} » : depuis "
                "chaque écran, le logo emmène ailleurs que chez lui"
            )
        return None

    # 3. La bascule de langue — sa cible est connue d avance elle aussi : la racine de la locale
    #    visée. Elle est jugée AVANT la cohérence de locale, sinon toute bascule légitime
    #    (un lien anglais qui pointe vers le français, c est son métier) sortirait accusée.
    visee = _langue_visee(lien)
    if visee and visee != locale_composant:
        attendue = _racine_de_locale(visee if visee in locales else None, locales)
        if chemin != attendue:
            return (
                f"bascule de langue « {lien['libelle']} » vers « {chemin} » au lieu de "
                f"« {attendue} » : elle envoie tout le site sur une page unique"
            )
        return None

    # 4. La cohérence de locale — un composant qui sert une locale ne renvoie pas vers une autre
    #    quand SA version existe. La condition « la contrepartie existe » n est pas un adoucissement
    #    mais la preuve du défaut : sans elle, un lien vers une page qui n existe que dans une
    #    langue serait accusé alors qu il n a pas d autre choix.
    if locale_composant is None:
        return None
    locale_cible = _locale_de_la_destination(chemin, locales)
    if locale_cible == locale_composant:
        return None
    contrepartie = _prefixer(chemin, locale_composant, locales)
    if not _connue(contrepartie, arbre):
        return None
    servie = f"« /{locale_cible} »" if locale_cible else "sans préfixe de locale"
    return (
        f"composant de la locale « {locale_composant} » pointant vers « {chemin} » ({servie}) "
        f"alors que « {contrepartie} » existe"
    )


# --- Écart SERVI ↔ VERSIONNÉ (TF-0288, volet détection — verdict O3 de l étude 20260817a) ------
# Le cas fondateur, INS-0001 (15/08/2026) : le menu anglais amputé n était PAS dans le composant.
# `HeaderEn.tsx` portait ses 8 entrées de premier niveau et ses 36 liens, et il était utilisé par
# 36 pages EN sur 36 ; la production en servait TROIS. L écart vivait entre la SOURCE et le SERVI,
# et aucun oracle de l écosystème ne comparait ces deux termes-là. Sans le bloc (b) de
# l instruction, la réponse évidente aurait été d ajouter les entrées manquantes au composant :
# un développement inutile sur un défaut de DÉPLOIEMENT, et un troisième « toujours pas ».
#
# Ce contrôle tient les deux termes, et il les tient avec des lecteurs DÉJÀ livrés : la grammaire
# de composants de TF-0283/TF-0295 pour la source, la lecture du build servi de TF-0284 pour le
# servi. En écrire de nouveaux aurait fait diverger deux lectures de la même chose.
CLASSE_ECART_SERVI = "ecart-servi-versionne"


def _entree_delocalisee(destination: str, locales: set[str]) -> str:
    """Clé comparable d une entrée de menu — le pendant SOURCE d `i18n.entrees_de_menu`."""
    chemin = _normaliser(destination)
    segments = chemin.split("/")
    if len(segments) > 1 and segments[1] in locales:
        reste = chemin[len(f"/{segments[1]}"):]
        return reste.rstrip("/") or "/"
    return chemin


def navigation_source(cible: Path) -> tuple[dict[str, set[str]], list[str], int]:
    """(entrées de navigation promises par locale, fichiers lus, nombre de liens de nav lus).

    La clé `""` porte les entrées des composants SANS locale propre : ils servent toutes les
    locales, donc leurs entrées sont promises partout. Une destination EXPRIMÉE n entre pas — on
    ne compare pas ce qu on n a pas résolu, sous peine d accuser un déploiement correct.
    """
    fichiers = _fichiers(cible, EXTENSIONS_COMPOSANTS)
    if not fichiers:
        return {}, [], 0
    arbre = _arborescence(cible)
    locales = set(arbre["locales"])
    promises: dict[str, set[str]] = {}
    lus: list[str] = []
    liens_lus = 0
    for fichier in fichiers:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        liens = [
            lien
            for lien in _liens_jsx(texte, _GRAMMAIRES.get(fichier.suffix.lower()))
            if lien["dans_nav"] and lien["destination"] and lien["destination"].startswith("/")
        ]
        if not liens:
            continue
        locale = _locale_du_composant(fichier, cible, locales) or ""
        lus.append(fichier.relative_to(cible).as_posix())
        liens_lus += len(liens)
        promises.setdefault(locale, set()).update(
            _entree_delocalisee(lien["destination"], locales) for lien in liens
        )
    return promises, sorted(lus), liens_lus


def ecart_servi_versionne(cible: Path) -> dict:
    """Ce que la SOURCE promet en navigation, contre ce que le BUILD SERVI en rend — TF-0288.

    Verdict machine, trois issues et pas une de plus :

      - **SKIP** quand un des deux termes manque. Sans source lisible, il n y a pas de versionné
        opposable et la comparaison n a pas de sens ; sans build servi, il n y a rien à comparer.
        Le motif DIT lequel manque : « pas de source » et « pas de build » ne se réparent pas de
        la même façon.
      - **FAIL** quand une entrée promise par la source n est pas servie. Les entrées manquantes
        sont NOMMÉES : c est tout l enjeu du cas fondateur — savoir que l écart est un défaut de
        déploiement et non de code se lit dans la liste des entrées absentes.
      - **PASS** quand chaque entrée promise est servie.

    Le sens de la comparaison n est pas symétrique, et c est voulu : une entrée SERVIE qu aucune
    source ne promet n est pas jugée ici. Elle peut venir d un autre composant, d un `<Nav>` que
    ce lecteur ne reconnaît pas, ou d une page rendue côté serveur — l accuser serait accuser la
    limite du lecteur.
    """
    from forge_tests.adaptateurs import i18n

    promises, fichiers_lus, liens_lus = navigation_source(cible)
    build = i18n.build_servi(cible)
    if not promises:
        return {
            "verdict": "SKIP",
            "motif": (
                "ecart servi/versionne : aucune navigation SOURCE lisible (pas de composant "
                f"{', '.join(EXTENSIONS_COMPOSANTS)} portant des liens litteraux dans un `<nav>` "
                f"sous {cible}) — sans source, il n y a pas de versionne OPPOSABLE et la "
                "comparaison n a pas d objet. C est l aggravant du cas fondateur : un produit "
                "hors git ne dit pas ce qui est deploye"
            ),
            "manquantes": {},
        }
    if build is None:
        return {
            "verdict": "SKIP",
            "motif": (
                "ecart servi/versionne : navigation SOURCE lue "
                f"({liens_lus} lien(s) de `<nav>` dans {', '.join(fichiers_lus)}) mais AUCUN "
                "build servi a confronter — declarer le dossier construit dans "
                f"FORGE_TESTS_I18N_BUILD (cherche : {', '.join(i18n.DOSSIERS_BUILD)})"
            ),
            "manquantes": {},
        }

    pages = i18n.pages_servies(build)
    locales_servies = i18n.locales_servies(pages)
    par_locale = i18n._par_locale(pages, locales_servies)
    communes = promises.get("", set())
    manquantes: dict[str, list[str]] = {}
    servies_par_locale: dict[str, int] = {}
    for locale in sorted(par_locale):
        accueil = par_locale[locale].get("/")
        if accueil is None:
            continue
        servies = set(i18n.entrees_de_menu(i18n._lire(accueil), locales_servies))
        servies_par_locale[locale or "defaut"] = len(servies)
        attendues = communes | promises.get(locale, set())
        absentes = sorted(attendues - servies)
        if absentes:
            manquantes[locale] = absentes
    return {
        "verdict": "FAIL" if manquantes else "PASS",
        "motif": (
            "ecart servi/versionne : navigation SOURCE lue "
            f"({liens_lus} lien(s) de `<nav>` dans {', '.join(fichiers_lus)}) confrontee au "
            f"build servi `{build}` — entrees servies par locale : "
            + " · ".join(f"{nom}={compte}" for nom, compte in sorted(servies_par_locale.items()))
        ),
        "manquantes": manquantes,
        "build": str(build),
        "fichiers": fichiers_lus,
        "pages": {locale: str(par_locale[locale]["/"]) for locale in par_locale
                  if par_locale[locale].get("/") is not None},
    }


def _findings_ecart(cible: Path, ecart: dict) -> list[Finding]:
    """Un constat par locale dont le menu servi est amputé — les entrées manquantes NOMMÉES."""
    findings: list[Finding] = []
    for locale, absentes in sorted(ecart["manquantes"].items()):
        identifiant = f"interface:ecart-servi:{locale or 'defaut'}"
        localisation = ecart["pages"].get(locale, ecart.get("build", str(cible)))
        findings.append(
            Finding(
                id=identifiant,
                classe=CLASSE_ECART_SERVI,
                localisation=localisation,
                message=(
                    f"la source versionnee promet {len(absentes)} entree(s) de navigation que le "
                    f"build SERVI ne rend pas sous « {locale or 'defaut'} » : "
                    + ", ".join(f"« {entree} »" for entree in absentes)
                    + " — le code est deja correct, c est le SERVI qui a derive (defaut de "
                    "deploiement, pas de developpement)"
                ),
                risque=coter(PAN, identifiant, localisation),
            )
        )
    return findings


def _relever_composants(cible: Path) -> tuple[list[dict], int, list[str]]:
    """Liens des composants, jugés. Puis le compte des destinations EXPRIMÉES, puis ce qui se
    DÉCLARE au rapport : les dialectes réellement lus, et d où viennent les locales (TF-0295)."""
    fichiers = _fichiers(cible, EXTENSIONS_COMPOSANTS)
    if not fichiers:
        return [], 0, []
    arbre = _arborescence(cible)
    locales = set(arbre["locales"])
    declarations = _declarations_de_composants(fichiers, arbre)
    releve: list[dict] = []
    exprimees = 0
    for fichier in fichiers:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        # TF-0295 (levée 2) : chaque composant est lu avec la grammaire de SON dialecte.
        liens = _liens_jsx(texte, _GRAMMAIRES.get(fichier.suffix.lower()))
        if not liens:
            continue
        locale = _locale_du_composant(fichier, cible, locales)
        relatif = fichier.relative_to(cible).as_posix()
        vus: dict[str, int] = {}
        for lien in liens:
            exprimees += 1 if lien["exprimee"] and lien["destination"] is None else 0
            racine = f"interface:{relatif}:{lien['ligne']}:{lien['tag']}"
            rang = vus.get(racine, 0)
            vus[racine] = rang + 1
            libelle = " ".join((lien["libelle"] or "").split())[:60]
            releve.append(
                {
                    "id": racine if rang == 0 else f"{racine}#{rang}",
                    "fichier": str(fichier),
                    "libelle": libelle or f"<{lien['tag']}> sans libellé",
                    "tag": lien["tag"],
                    "classe": "lien-casse",
                    "motif": _juger_lien(lien, locale, arbre),
                }
            )
    return releve, exprimees, declarations


def _declarations_de_composants(fichiers: list[Path], arbre: dict) -> list[str]:
    """Ce que le contrôle des liens de composants DIT de lui-même — TF-0295.

    Deux phrases, et chacune répare un silence : quels dialectes ont été lus (avant, seul React
    l était et rien ne le disait), et d où viennent les locales opposables. « Aucune locale » et
    « locales lues dans la configuration » ne donnent pas le même verdict aux contrôles de logo,
    de bascule de langue et de cohérence — les taire rendait leur DÉSACTIVATION invisible.
    """
    lus = sorted({fichier.suffix.lower() for fichier in fichiers} & set(_GRAMMAIRES))
    declarations = [
        "interface/liens : dialectes de composant lus — "
        + ", ".join(f"`{suffixe}`" for suffixe in lus)
        + " ; chacun avec SA grammaire de destination (les formes liees de Vue, `:to` et "
        "`v-bind:href`, et les interpolations Svelte sont comptees EXPRIMEES, jamais jugees)"
    ]
    sources: list[str] = []
    if arbre["locales_litterales"]:
        sources.append(
            "arborescence litterale (" + ", ".join(sorted(arbre["locales_litterales"])) + ")"
        )
    if arbre["locales_configurees"]:
        sources.append(
            "configuration du framework (" + ", ".join(sorted(arbre["locales_configurees"])) + ")"
        )
    if sources:
        declarations.append(
            "interface/liens : locales opposables lues depuis " + " et ".join(sources)
        )
    elif arbre["routage_dynamique"]:
        declarations.append(
            "interface/liens : le produit route ses locales par un segment DYNAMIQUE "
            "(`app/[locale]/…`) mais AUCUNE liste de locales n est lisible dans sa configuration "
            "— logo, bascule de langue et coherence de locale sont donc NON JUGES : declarer les "
            "locales (`locales: ['fr','en']` dans next.config) les rendrait opposables"
        )
    else:
        declarations.append(
            "interface/liens : aucune locale opposable (ni segment litteral, ni liste declaree "
            "dans la configuration) — le produit est traite comme monolingue et les controles de "
            "logo, de bascule de langue et de coherence de locale ne s appliquent pas"
        )
    return declarations


def _relever(cible: Path) -> tuple[list[dict], bool, int, list[str]]:
    """Affordances du projet (gabarits ET liens de composants), motif de défaut de chacune.

    Troisième membre : le nombre de destinations EXPRIMÉES rencontrées — comptées pour être
    déclarées, jamais jugées. Quatrième : ce que le contrôle des liens de composants déclare de
    son propre périmètre (dialectes lus, provenance des locales — TF-0295).
    """
    corpus, tronque = _corpus_js(cible)
    releve: list[dict] = []
    for fichier in _fichiers(cible, EXTENSIONS):
        lecteur = _Lecteur()
        try:
            lecteur.feed(fichier.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 — un gabarit illisible se DECLARE, il n emporte rien
            continue
        # Le script en ligne du document fait partie de son cablage : l ignorer declarerait
        # inerte tout bouton d une page autonome, ce qui est exactement le faux positif a eviter.
        local = corpus + "\n" + "\n".join(lecteur.scripts)
        relatif = fichier.relative_to(cible).as_posix()
        vus: dict[str, int] = {}
        for entree in lecteur.affordances:
            racine = f"interface:{relatif}:{entree['ligne']}:{entree['tag']}"
            rang = vus.get(racine, 0)
            vus[racine] = rang + 1
            releve.append(
                {
                    "id": racine if rang == 0 else f"{racine}#{rang}",
                    "fichier": str(fichier),
                    "libelle": _libelle(entree),
                    "tag": entree["tag"],
                    "motif": _juger(entree, local),
                }
            )
    # TF-0283 : les liens des composants React rejoignent le MÊME relevé. Les tenir à part aurait
    # produit une seconde surface, un second seuil et un second verdict pour la même loi.
    composants, exprimees, declarations = _relever_composants(cible)
    releve += composants
    return releve, tronque, exprimees, declarations


def inventaire(cible: Path) -> list[Element]:
    releve, _, _, _ = _relever(cible)
    return [
        Element(e["id"], PAN, f"{e['tag']} « {e['libelle']} »", e["fichier"]) for e in releve
    ]


def sans_objet(cible: Path) -> str | None:
    """PREUVE que ce projet n a pas de gabarits à lire (NA) — jamais une supposition.

    RT-9-bis : sur quatre audits du même produit, l inventaire a fait 6 → 27 → 335 → 0 sans
    qu une ligne de gabarit change. Les trois premiers chiffres venaient des ARTEFACTS
    (corrigé par RT-9) ; le quatrième est la vérité — ce produit n a pas de gabarit serveur.
    Le dire « non énumérable » accusait l adaptateur là où il n y a simplement rien.

    Le critère est POSITIF et discriminant : aucun fichier de gabarit hors artefacts, ET des
    sources de framework présentes (l interface est construite à l exécution). Sans la seconde
    moitié, un projet dont on n aurait rien su lire passerait pour un projet sans interface.
    """
    if _fichiers(cible, EXTENSIONS):
        return None
    sources = _fichiers(cible, EXTENSIONS_JS)
    if not sources:
        return None  # ni gabarit ni source : on ne sait rien, ce n est pas un « sans objet »
    return (
        f"aucun gabarit ({', '.join(EXTENSIONS[:3])}…) hors artefacts, mais "
        f"{len(sources)} source(s) de framework : l interface est construite à l exécution — "
        "elle relève du pan `qualif`, qui la juge servie, pas d un gabarit statique"
    )


def analyser(cible: Path) -> SortieAdaptateur:
    releve, tronque, exprimees, declarations = _relever(cible)
    non_juge = [*NON_JUGE, *declarations]

    # TF-0288 — l ecart SERVI ↔ VERSIONNE. Le contrôle se DIT toujours, dans les trois issues :
    # un SKIP muet aurait rendu « aucun ecart » indiscernable de « la comparaison n a pas eu
    # lieu », et c est précisément cette confusion qui a coûté deux « toujours pas » sur INS-0001.
    ecart = ecart_servi_versionne(cible)
    non_juge.append(f"interface/{ecart['verdict'].lower()} — {ecart['motif']}")
    findings_ecart = _findings_ecart(cible, ecart)

    if exprimees:
        non_juge.append(
            f"interface/liens : {exprimees} destination(s) de lien EXPRIMEE(S) dans les "
            "composants (`href={...}`) — comptees, NON jugees : leur valeur depend de "
            "l execution"
        )
    if tronque:
        non_juge.append(
            "interface : corpus JavaScript tronque au-dela de 8 Mo — au-dela, un element "
            "pourrait etre declare inerte alors que son cablage vit dans la partie non lue"
        )
    # `not findings_ecart` : un ecart mesuré ne peut pas sortir sous un verdict NA ni SKIP — ce
    # serait un constat rendu puis enterré par le verdict qui l accompagne.
    if not releve and not findings_ecart:
        motif_sans_objet = sans_objet(cible)
        if motif_sans_objet:
            # NA (14/08) : ce pan lit des GABARITS (HTML, Jinja, Twig…). Un produit dont
            # l'interface est construite à l'exécution par un framework n'en a pas — et ne
            # pas avoir de gabarit n'est pas un défaut de gabarit. C'est le cas de RT-9-bis :
            # après l'exclusion des artefacts (RT-9), l'inventaire de ce produit est tombé à
            # zéro, et « surface non énumérable » accusait à tort là où il n'y a rien.
            return SortieAdaptateur(
                NOM, PAN, str(cible), "NA",
                non_juge=[*non_juge, f"interface : SANS OBJET sur ce projet — {motif_sans_objet}"],
            )
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *non_juge,
                "interface : aucun gabarit exploitable — ni .html ni gabarit serveur hors "
                f"artefacts de construction sous {cible} : surface d interface non enumerable",
            ],
        )

    inertes = [e for e in releve if e["motif"]]
    findings = [
        Finding(
            id=e["id"],
            # TF-0283 : un lien qui pointe à côté n est pas « inerte » — il a bien un effet, et
            # c est le mauvais. Deux classes, donc deux suites à donner (`forge_tests.actions`).
            classe=e.get("classe", "affordance-inerte"),
            localisation=f"{e['fichier']}",
            message=f"{e['tag']} « {e['libelle']} » — {e['motif']}",
            risque=coter(PAN, e["id"], e["fichier"]),
        )
        for e in inertes
    ]
    # TF-0288 : l ecart servi/versionne rejoint les MEMES findings — un seul verdict, une seule
    # liste de travaux. Il ne rejoint PAS la surface : ce n est pas une affordance de plus, c est
    # une comparaison entre deux etats du meme produit, et l ajouter au ratio le rendrait faux.
    findings += findings_ecart
    findings.sort(key=lambda f: f.risque or 0, reverse=True)
    total = len(releve)
    cables = total - len(inertes)
    non_juge.append(
        f"interface : {total} affordance(s) relevee(s) dans "
        f"{len({e['fichier'] for e in releve})} gabarit(s) et composant(s) — {cables} "
        "tenue(s) de facon lisible"
    )
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if findings else "PASS",
        findings=findings,
        non_juge=non_juge,
        surface={
            "inventorie": total,
            "exerce": cables,
            # `total` peut valoir 0 : un ecart servi/versionne mesure sans qu aucune affordance
            # de gabarit n ait ete relevee est un cas licite (TF-0288), pas une division.
            "ratio": round(cables / total, 4) if total else 0.0,
            "seuil": SEUIL,
            "elements_exerces": sorted(e["id"] for e in releve if not e["motif"]),
            "elements_non_exerces": [e["id"] for e in inertes],
        },
    )
