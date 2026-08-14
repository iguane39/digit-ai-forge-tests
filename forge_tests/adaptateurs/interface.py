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
    "construction : le pan lit les affordances du GABARIT, les composants de framework "
    "(.jsx/.vue) relèvent du pan front"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "F3", "famille": "fonctionnel", "titre": "Affordances",
     "decoupe": "fichier", "axe_cas": "unitaire"},
)


# Gabarits rendus tels quels par un serveur ou servis en statique. Les composants de framework
# (.jsx, .tsx, .vue, .svelte) sont volontairement HORS périmètre : leur câblage est une
# expression du langage, pas un attribut du gabarit — les juger ici produirait du faux positif.
EXTENSIONS = (".html", ".htm", ".jinja", ".jinja2", ".j2", ".twig", ".ejs", ".hbs")
EXTENSIONS_JS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte")
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
    "comme gabarits ; leur surface est inventoriee par le pan front via `data-testid`",
    "interface : une ancre `#nom` dont la cible n existe pas dans le document n est pas jugee "
    "morte — la cible peut etre injectee au rendu",
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


def _relever(cible: Path) -> tuple[list[dict], bool]:
    """Toutes les affordances du projet, avec le motif d inertie de chacune (ou None)."""
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
    return releve, tronque


def inventaire(cible: Path) -> list[Element]:
    releve, _ = _relever(cible)
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
    releve, tronque = _relever(cible)
    non_juge = list(NON_JUGE)
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
            classe="affordance-inerte",
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
        f"{len({e['fichier'] for e in releve})} gabarit(s) — {cables} cablee(s) de facon lisible"
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
