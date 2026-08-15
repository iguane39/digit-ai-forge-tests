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
# TF-0283 : composants dont les liens à destination LITTÉRALE sont jugés. React seulement : les
# dialectes de gabarit de Vue et Svelte ont leur propre grammaire d attributs, et prétendre les
# lire avec ce scanner produirait exactement le faux positif que la limite d origine évitait.
EXTENSIONS_COMPOSANTS = (".jsx", ".tsx")
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
    "interface : les composants de framework (.jsx, .tsx, .vue, .svelte) ne sont pas analyses "
    "comme gabarits — seule la DESTINATION litterale des liens des composants React (.jsx, .tsx) "
    "est jugee (TF-0283) ; leur surface est inventoriee par le pan front via `data-testid`",
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
    "interface/liens : la locale d un composant est deduite de son arborescence ou de son nom "
    "(`.../en/Header.tsx`, `HeaderEn.tsx`) ; un composant qui rend PLUSIEURS locales selon une "
    "prop n a pas de locale propre et ses liens ne sont pas juges sur ce critere",
    "interface/liens : « logo » et « bascule de langue » sont reconnus par HEURISTIQUE — mention "
    "de `logo` dans le contenu du lien, libelle egal a un nom de langue ou attribut `hrefLang`. "
    "Un logo sans le mot `logo` ni `hrefLang` echappe au controle, et le lien ainsi reconnu se "
    "conteste comme tout constat (`declarations`)",
    "interface/liens : le libelle d un lien est lu jusqu a la premiere fermeture de meme balise ; "
    "un lien qui en imbrique un autre de meme nom verrait son libelle tronque",
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
_NOM_ATTRIBUT = re.compile(r"[A-Za-z_][-\w:.]*")
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


def _liens_jsx(texte: str) -> list[dict]:
    """Liens d un composant React, avec leur destination littérale (ou None si calculée)."""
    liens: list[dict] = []
    for balise in _BALISES_LIEN:
        for ouverture in re.finditer(rf"<{balise}(?=[\s/>])", texte):
            fin = _fin_de_balise(texte, ouverture.end())
            if fin is None:
                continue
            attributs = _attributs_jsx(texte[ouverture.end():fin])
            destination: str | None = None
            exprimee = False
            for nom in _ATTRIBUTS_DESTINATION:
                if nom not in attributs:
                    continue
                valeur = attributs[nom]
                if valeur is None:
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
    for dossier in sorted(cible.rglob("public")):
        if not dossier.is_dir() or any(partie in _EXCLUS for partie in dossier.parts):
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
    locales = {
        segment
        for chemin in chemins
        for segment in [chemin.split("/")[1] if chemin.count("/") >= 1 else ""]
        if segment in _LOCALES_CONNUES
    }
    return {"chemins": chemins, "motifs": motifs, "locales": locales}


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


def _relever_composants(cible: Path) -> tuple[list[dict], int]:
    """Liens des composants React, jugés. Le second membre compte les destinations EXPRIMÉES."""
    fichiers = _fichiers(cible, EXTENSIONS_COMPOSANTS)
    if not fichiers:
        return [], 0
    arbre = _arborescence(cible)
    locales = set(arbre["locales"])
    releve: list[dict] = []
    exprimees = 0
    for fichier in fichiers:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        liens = _liens_jsx(texte)
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
    return releve, exprimees


def _relever(cible: Path) -> tuple[list[dict], bool, int]:
    """Affordances du projet (gabarits ET liens de composants), motif de défaut de chacune.

    Troisième membre : le nombre de destinations EXPRIMÉES rencontrées — comptées pour être
    déclarées, jamais jugées.
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
    composants, exprimees = _relever_composants(cible)
    releve += composants
    return releve, tronque, exprimees


def inventaire(cible: Path) -> list[Element]:
    releve, _, _ = _relever(cible)
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
    releve, tronque, exprimees = _relever(cible)
    non_juge = list(NON_JUGE)
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
    if not releve:
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
            "ratio": round(cables / total, 4),
            "seuil": SEUIL,
            "elements_exerces": sorted(e["id"] for e in releve if not e["motif"]),
            "elements_non_exerces": [e["id"] for e in inertes],
        },
    )
