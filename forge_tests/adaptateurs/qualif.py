"""Adaptateur Qualif populée — parcours navigateur d une instance SERVIE et PEUPLÉE (A-4).

Généralisation du prototype `forge/etapes/mep/qualif_populee.py` d ASD Mail Manager (14 pages,
Playwright, staging peuplé). Le prototype prouvait la valeur du contrôle ; il était écrit POUR
un produit — routes en dur, marqueurs en dur, peuplement en dur. Ici le même contrôle devient
un pan du framework : les routes se découvrent, les marqueurs se dérivent, le peuplement reste
la responsabilité du projet audité (c est lui qui sait ce que « peuplé » veut dire chez lui).

Ce que le pan mesure, et que rien d autre ne mesure :

  - **0 erreur serveur** — une route qui rend un 5xx, une trace Python ou une page d exception
    de gabarit. La couverture endpoint x code ne la voit pas : elle mesure ce que la SUITE
    atteint, et une suite verte n atteint pas la page que l utilisateur ouvre en premier ;
  - **0 erreur console** — une exception JavaScript non rattrapée casse l interface sans
    qu aucun test serveur ne bronche ;
  - **un marqueur de contenu par route** — une page qui répond 200 en n affichant rien est un
    faux vert. Le marqueur est configurable ; à défaut il est dérivé du titre de la page ;
  - **élément interactif -> effet, DYNAMIQUE** — pendant du contrôle statique RT-7. Le pan
    `interface` lit les gabarits ; celui-ci interroge le DOM RENDU par le navigateur, via le
    protocole DevTools : il voit donc les gestionnaires posés à l exécution par un framework,
    que l analyse statique déclare explicitement hors de sa portée.

**Aucun clic n est émis.** L instance visée est peuplée et servie : cliquer y déclencherait des
écritures réelles (suppression, envoi de courriel, appel d API tierce facturée). Le pan lit les
écouteurs attachés, il ne les déclenche pas — limite déclarée, et c est le prix de la
non-destructivité sur une instance de qualification.

Sans instance servie, le pan ne devine rien : il sort SKIP avec son motif et les champs à
fournir, que le mécanisme central de qualification (RT-6a) publie en `non_testables[]`. Une
fois l URL fournie, `--reprendre` rejoue ce seul pan.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from forge_tests import seuils
from forge_tests.noyau import Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "qualif-navigateur", "qualif"
SEUIL = seuils.valeur("couverture_surface_qualif")

POUR_COUVRIR = (
    "servir une instance PEUPLÉE du produit (jeu de démonstration injecté, traitements joués) "
    "et déclarer son URL dans FORGE_TESTS_QUALIF_URL ; fournir un compte par "
    "FORGE_TESTS_QUALIF_LOGIN / FORGE_TESTS_QUALIF_PASSWORD si les routes sont protégées. "
    "Options : FORGE_TESTS_QUALIF_ROUTES (routes d'amorce, virgule), "
    "FORGE_TESTS_QUALIF_MARQUEURS (JSON route -> marqueur de contenu), "
    "FORGE_TESTS_QUALIF_CONNEXION (route de la mire), FORGE_TESTS_QUALIF_PLAFOND (routes max)"
)

# Chapitre(s) de cahier de tests que ce pan alimente. Le cahier et le dashboard les
# DERIVENT du registre : une liste ecrite ailleurs aurait laisse un pan futur invisible.
# `decoupe` nomme l axe de sous-chapitrage ; un axe inconnu retombe sur « element », et le
# repli est DECLARE au cahier plutot que silencieux.
CHAPITRES = (
    {"code": "F1", "famille": "fonctionnel", "titre": "Parcours bout en bout",
     "decoupe": "parcours", "axe_cas": "etats"},
    {"code": "F2", "famille": "fonctionnel", "titre": "Écrans × états",
     "decoupe": "ecran", "axe_cas": "etats"},
)


CHAMPS_REQUIS = ("FORGE_TESTS_QUALIF_URL",)

NON_JUGE = [
    "qualif : le pan LIT les ecouteurs attaches a chaque affordance, il ne CLIQUE jamais — sur "
    "une instance peuplee un clic ecrit vraiment (suppression, envoi, appel tiers facture). Un "
    "gestionnaire attache mais dont le corps ne fait rien passerait donc pour un effet",
    "qualif : les routes sont decouvertes par exploration des liens depuis la racine ; une "
    "route atteignable seulement apres une action (formulaire poste, menu ouvert au clic) "
    "n est pas visitee — la declarer en amorce avec FORGE_TESTS_QUALIF_ROUTES",
    "qualif : le marqueur de contenu par defaut est le titre de la page (premier `h1` non vide, "
    "sinon `title`) ; il atteste qu une page a RENDU quelque chose, pas qu elle ait rendu les "
    "BONNES donnees — un marqueur metier se declare par FORGE_TESTS_QUALIF_MARQUEURS",
    "qualif : quand une delegation d evenement est posee sur `document` ou `body`, aucun "
    "element ne peut plus etre declare inerte avec certitude — les elements concernes sont "
    "NOMMES en non_juge au lieu d etre accuses",
]

# Affordances jugees, alignees sur le pan `interface` : meme loi, autre point d observation.
_SELECTEUR = (
    "button, a, form, input[type=submit], input[type=button], input[type=image], [role=button]"
)
_HREF_MORTS = {"", "#", "javascript:;", "javascript:void(0)", "javascript:void(0);"}
_PREFIXES_HANDLER = (
    "on", "@", "v-on:", "x-on:", "x-bind:", "hx-", "wire:", "ng-", "data-action",
    "data-controller", "data-bs-toggle", "data-toggle", "data-turbo", "up-", "formaction",
)
_TRACES = (
    "internal server error",
    "traceback (most recent call last)",
    "jinja2.exceptions",
    "templatenotfound",
    "werkzeug.debug",
    "django.core.exceptions",
)
_PLAFOND_DEFAUT = 40

# Descripteur de chaque affordance, lu dans le DOM RENDU (et non dans le gabarit source).
_JS_AFFORDANCES = """
() => Array.from(document.querySelectorAll(__SELECTEUR__)).map((e, i) => {
  const attributs = {};
  for (const a of e.attributes) attributs[a.name.toLowerCase()] = a.value;
  const formulaire = e.closest('form');
  return {
    rang: i,
    tag: e.tagName.toLowerCase(),
    attributs,
    libelle: (e.getAttribute('aria-label') || e.textContent || e.value || '').trim().slice(0, 60),
    dans_formulaire: formulaire !== null,
    action_formulaire: formulaire ? (formulaire.getAttribute('action') || '') : null,
    handler_formulaire: formulaire
      ? Array.from(formulaire.attributes).some(a => a.name.toLowerCase().startsWith('on'))
      : false,
  };
})
""".replace("__SELECTEUR__", json.dumps(_SELECTEUR))

_JS_LIENS = (
    "() => Array.from(document.querySelectorAll('a[href]'))"
    ".map(a => a.getAttribute('href'))"
)
_JS_TITRE = """
() => {
  const h = Array.from(document.querySelectorAll('h1'))
    .map(e => (e.textContent || '').trim()).find(t => t.length > 2);
  return h || (document.title || '').trim();
}
"""


def _config(cible: Path) -> dict:
    from forge_tests.authentification import charger_env

    charger_env(cible)
    base = (
        os.environ.get("FORGE_TESTS_QUALIF_URL")
        or os.environ.get("FORGE_TESTS_BASE_URL")
        or ""
    ).strip()
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    marqueurs: dict[str, str] = {}
    brut = (os.environ.get("FORGE_TESTS_QUALIF_MARQUEURS") or "").strip()
    if brut:
        try:
            lu = json.loads(brut)
            if isinstance(lu, dict):
                marqueurs = {str(k): str(v) for k, v in lu.items()}
        except json.JSONDecodeError:
            marqueurs = {}
    plafond = (os.environ.get("FORGE_TESTS_QUALIF_PLAFOND") or "").strip()
    return {
        "base": base.rstrip("/"),
        "amorces": [
            r.strip()
            for r in (os.environ.get("FORGE_TESTS_QUALIF_ROUTES") or "").split(",")
            if r.strip()
        ],
        "marqueurs": marqueurs,
        "connexion": (os.environ.get("FORGE_TESTS_QUALIF_CONNEXION") or "").strip(),
        "login": (os.environ.get("FORGE_TESTS_QUALIF_LOGIN") or os.environ.get(
            "FORGE_TESTS_LOGIN"
        ) or "").strip(),
        "mdp": (os.environ.get("FORGE_TESTS_QUALIF_PASSWORD") or os.environ.get(
            "FORGE_TESTS_PASSWORD"
        ) or "").strip(),
        "plafond": int(plafond) if plafond.isdigit() else _PLAFOND_DEFAUT,
    }


def _route(url: str, base: str) -> str | None:
    """Chemin interne d une URL, ou None si elle sort du domaine audité."""
    if url.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    absolu = urljoin(base + "/", url)
    depart, arrivee = urlparse(base), urlparse(absolu)
    if (arrivee.scheme, arrivee.netloc) != (depart.scheme, depart.netloc):
        return None
    return (arrivee.path or "/").rstrip("/") or "/"


# --- Écouteurs réellement attachés, via le protocole DevTools ---------------------------------
def _ecouteurs(page) -> tuple[list[set[str]] | None, bool, str | None]:  # noqa: ANN001
    """(types d événements par affordance, délégation détectée, motif d indisponibilité).

    `None` en premier membre veut dire « le protocole n a pas répondu » : le jugement retombe
    alors sur les seuls attributs, comme le pan statique, et le dit.
    """
    try:
        session = page.context.new_cdp_session(page)
        session.send("DOM.enable")
        session.send("Runtime.enable")
        racine = session.send("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]
        noeuds = session.send(
            "DOM.querySelectorAll", {"nodeId": racine, "selector": _SELECTEUR}
        )["nodeIds"]
        par_element: list[set[str]] = []
        for noeud in noeuds:
            if not noeud:
                par_element.append(set())
                continue
            objet = session.send("DOM.resolveNode", {"nodeId": noeud})["object"]["objectId"]
            listes = session.send("DOMDebugger.getEventListeners", {"objectId": objet})
            par_element.append({e.get("type", "") for e in listes.get("listeners", [])})
        delegation = False
        for expression in ("document", "document.body"):
            objet = session.send("Runtime.evaluate", {"expression": expression})["result"].get(
                "objectId"
            )
            if not objet:
                continue
            listes = session.send("DOMDebugger.getEventListeners", {"objectId": objet})
            types = {e.get("type", "") for e in listes.get("listeners", [])}
            delegation = delegation or bool(types & {"click", "submit", "mousedown", "pointerdown"})
        session.detach()
    except Exception as erreur:  # noqa: BLE001 — le protocole se DECLARE indisponible, il ne tue rien
        return None, False, f"{type(erreur).__name__}: {erreur}"
    return par_element, delegation, None


def _a_un_effet(descripteur: dict, types: set[str] | None) -> str | None:
    """None si l affordance a un effet observable ; sinon le motif de son inertie, en clair."""
    table = descripteur["attributs"]
    if "disabled" in table or table.get("aria-disabled") == "true":
        return None  # inertie VOULUE et déclarée
    if any(nom.startswith(_PREFIXES_HANDLER) for nom in table):
        return None
    if types and (types & {"click", "submit", "mousedown", "pointerdown", "keydown"}):
        return None

    tag = descripteur["tag"]
    if tag == "a":
        href = table.get("href")
        if href is None:
            return "lien sans attribut href : aucune destination, aucun effet"
        if href.strip().lower() in _HREF_MORTS:
            return f"lien dont href vaut « {href.strip() or '(vide)'} » et sans écouteur attaché"
        return None
    if tag == "form":
        if (table.get("action") or "").strip() not in ("", "#"):
            return None
        return "formulaire sans action ni écouteur de soumission : rien n'est envoyé"

    type_ = table.get("type", "").lower()
    if type_ == "reset":
        return None  # effet natif garanti par le navigateur
    soumet = type_ == "submit" or (type_ == "" and descripteur["dans_formulaire"])
    if soumet and descripteur["dans_formulaire"]:
        action = (descripteur.get("action_formulaire") or "").strip()
        if action not in ("", "#") or descripteur.get("handler_formulaire"):
            return None
        return (
            "bouton de soumission d'un formulaire sans action ni écouteur : le clic n'envoie rien"
        )
    if soumet and table.get("form"):
        return None  # rattaché à un formulaire nommé ailleurs
    return "élément interactif sans écouteur attaché, sans destination et sans soumission"


# --- Parcours ---------------------------------------------------------------------------------
def _connecter(page, config: dict) -> str | None:  # noqa: ANN001
    """Ouvre une session si un compte est fourni. Renvoie un motif d échec, ou None."""
    if not (config["login"] and config["mdp"]):
        return None
    candidates = [config["connexion"]] if config["connexion"] else ["/connexion", "/login"]
    for route in candidates:
        if not route:
            continue
        try:
            page.goto(config["base"] + route, wait_until="domcontentloaded", timeout=30000)
        except Exception:  # noqa: BLE001
            continue
        mdp = page.query_selector("input[type=password]")
        if mdp is None:
            continue
        identifiant = page.query_selector(
            "input[type=email], input[name*=mail i], input[name*=login i], "
            "input[name*=user i], input[type=text]"
        )
        if identifiant is None:
            continue
        identifiant.fill(config["login"])
        mdp.fill(config["mdp"])
        bouton = page.query_selector("button[type=submit], input[type=submit], button")
        if bouton is None:
            continue
        bouton.click()
        page.wait_for_load_state("networkidle")
        return None
    return (
        "aucune mire de connexion trouvee (routes essayees : "
        + ", ".join(c for c in candidates if c)
        + ") — la declarer par FORGE_TESTS_QUALIF_CONNEXION"
    )


def _visiter(page, config: dict) -> tuple[list[dict], list[str]]:  # noqa: ANN001
    """Visite chaque route atteignable et relève tout ce qui s y voit."""
    base = config["base"]
    a_visiter: deque[str] = deque(["/", *config["amorces"]])
    vues: set[str] = set()
    releve: list[dict] = []
    avertissements: list[str] = []
    journal: list[str] = []
    page.on("console", lambda m: journal.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: journal.append(str(e)))

    while a_visiter and len(vues) < config["plafond"]:
        route = a_visiter.popleft()
        if route in vues:
            continue
        vues.add(route)
        journal.clear()
        problemes: list[str] = []
        statut: int | None = None
        try:
            reponse = page.goto(base + route, wait_until="networkidle", timeout=45000)
            statut = reponse.status if reponse is not None else None
        except Exception as erreur:  # noqa: BLE001 — une route injoignable est un CONSTAT
            problemes.append(f"navigation impossible : {type(erreur).__name__}")
            releve.append(
                {"route": route, "statut": None, "problemes": problemes, "affordances": [],
                 "corps": "", "console": []}
            )
            continue
        corps = page.content()
        if statut is None:
            problemes.append("aucune réponse HTTP observée")
        elif statut >= 500:
            problemes.append(f"erreur serveur HTTP {statut}")
        elif statut >= 400:
            problemes.append(f"route atteignable par un lien mais HTTP {statut}")
        minuscule = corps.lower()
        for trace in _TRACES:
            if trace in minuscule:
                problemes.append(f"trace d'exception rendue dans la page (« {trace} »)")
                break
        marqueur = config["marqueurs"].get(route)
        if marqueur is None:
            try:
                marqueur = page.evaluate(_JS_TITRE) or ""
            except Exception:  # noqa: BLE001
                marqueur = ""
            if not marqueur.strip():
                problemes.append(
                    "aucun marqueur de contenu : ni `h1` ni `title` non vide — la page répond "
                    "mais n'affiche rien d'identifiable"
                )
        elif marqueur.lower() not in minuscule:
            problemes.append(f"marqueur de contenu absent : {marqueur!r}")

        affordances: list[dict] = []
        if statut is not None and statut < 400:
            try:
                descripteurs = page.evaluate(_JS_AFFORDANCES)
            except Exception:  # noqa: BLE001
                descripteurs = []
            types, delegation, motif = _ecouteurs(page)
            if motif is not None:
                avertissements.append(
                    f"qualif : protocole DevTools indisponible sur {route} ({motif}) — "
                    "affordances jugees sur leurs seuls attributs, comme en statique"
                )
            for descripteur in descripteurs:
                rang = descripteur["rang"]
                attaches = types[rang] if types is not None and rang < len(types) else None
                affordances.append(
                    {
                        "rang": rang,
                        "tag": descripteur["tag"],
                        "libelle": " ".join((descripteur["libelle"] or "").split())[:60],
                        "motif": _a_un_effet(descripteur, attaches),
                        "delegation": delegation,
                    }
                )
            if delegation:
                avertissements.append(
                    f"qualif : delegation d evenement posee sur document/body de {route} — les "
                    "affordances sans ecouteur propre y sont NON JUGEES, jamais accusees"
                )
            # Les liens de cette page alimentent le parcours.
            try:
                for href in page.evaluate(_JS_LIENS):
                    suivant = _route(href or "", base)
                    if suivant is not None and suivant not in vues:
                        a_visiter.append(suivant)
            except Exception:  # noqa: BLE001
                pass
        releve.append(
            {
                "route": route,
                "statut": statut,
                "problemes": problemes,
                "affordances": affordances,
                # Tronque : sur une instance reelle, garder 40 pages entieres en memoire pour
                # n en relire que le debut a la recherche d une variable citee serait un cout
                # sans contrepartie.
                "corps": corps[:20000],
                "console": list(journal),
            }
        )
    return releve, avertissements


def analyser(cible: Path) -> SortieAdaptateur:
    from forge_tests.qualification import declarer, detecter

    config = _config(cible)
    if not config["base"]:
        declarer(cible, "acces", CHAMPS_REQUIS)
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "qualif : aucune instance servie declaree — le pan exige une application EN "
                "SERVICE et PEUPLEE, il ne peut ni la construire ni la peupler lui-meme ; "
                "fournir FORGE_TESTS_QUALIF_URL puis `--reprendre` le rapport",
            ],
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                "qualif : Playwright absent de l environnement de Forge Tests — "
                "`uv sync` puis `uv run playwright install chromium`",
            ],
        )

    non_juge = list(NON_JUGE)
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            page = navigateur.new_page()
            echec = _connecter(page, config)
            if echec:
                non_juge.append(f"qualif : {echec}")
            releve, avertissements = _visiter(page, config)
            navigateur.close()
    except Exception as erreur:  # noqa: BLE001 — un pan qui ne peut pas voir le DECLARE
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *non_juge,
                f"qualif : instance {config['base']} non parcourable "
                f"({type(erreur).__name__}: {erreur})",
            ],
        )
    if not releve:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*non_juge, f"qualif : aucune route atteinte sur {config['base']}"],
        )
    non_juge.extend(sorted(set(avertissements)))

    inventaire: list[str] = []
    exerces: list[str] = []
    findings: list[Finding] = []
    non_testables: list = []
    from forge_tests.noyau import NonTestable

    for page_vue in releve:
        route = page_vue["route"]
        identifiant = f"qualif:route:{route}"
        inventaire.append(identifiant)
        # RT-6a : une route qui echoue en CITANT une configuration absente n accuse pas le
        # projet — elle nomme ce qu il manque ici, et `--reprendre` la rejouera une fois fourni.
        manquants = detecter(cible, "acces", f"{page_vue['corps']}\n" + "\n".join(
            page_vue["console"]
        )) if page_vue["problemes"] or page_vue["console"] else set()
        if manquants:
            non_testables.append(
                NonTestable(
                    element=identifiant,
                    champs_requis=sorted(manquants),
                    pan=PAN,
                    motif=(
                        f"qualif : {route} échoue en citant une configuration absente — "
                        f"fournir {', '.join(sorted(manquants))}, puis `--reprendre` le rapport"
                    ),
                )
            )
            continue
        ennuis = list(page_vue["problemes"])
        if page_vue["console"]:
            ennuis.append(f"erreur console : {page_vue['console'][0][:120]}")
        if ennuis:
            findings.append(
                Finding(
                    id=identifiant,
                    classe="route-en-defaut",
                    localisation=f"{config['base']}{route}",
                    message=f"{route} — " + " · ".join(ennuis),
                    risque=coter(PAN, identifiant, str(cible)),
                )
            )
        else:
            exerces.append(identifiant)
        for affordance in page_vue["affordances"]:
            cle = (
                f"qualif:effet:{route}:{affordance['rang']}:{affordance['tag']}"
            )
            inventaire.append(cle)
            if affordance["motif"] is None:
                exerces.append(cle)
            elif affordance["delegation"]:
                exerces.append(cle)  # non jugeable : deja NOMME en non_juge, jamais accuse
            else:
                findings.append(
                    Finding(
                        id=cle,
                        classe="affordance-sans-effet",
                        localisation=f"{config['base']}{route}",
                        message=(
                            f"{affordance['tag']} « {affordance['libelle'] or 'sans libellé'} » "
                            f"sur {route} — {affordance['motif']}"
                        ),
                        risque=coter(PAN, cle, str(cible)),
                    )
                )

    total = len(inventaire)
    ratio = len(exerces) / total if total else 0.0
    if total and ratio < SEUIL:
        findings.insert(
            0,
            Finding(
                id=f"seuil:{PAN}",
                classe="seuil-non-tenu",
                localisation=config["base"],
                message=(
                    f"qualification {ratio:.0%} sous le seuil {SEUIL:.0%} — "
                    f"{total - len(exerces)} élément(s) en défaut sur {total}"
                ),
                severite=seuils.severite("couverture_surface_qualif"),
                risque=coter(PAN, f"seuil:{PAN}", str(cible)),
            ),
        )
    findings.sort(key=lambda f: f.risque or 0, reverse=True)
    non_juge.append(
        f"qualif : {len(releve)} route(s) parcourue(s) sur {config['base']} — "
        f"{sum(len(p['affordances']) for p in releve)} affordance(s) lue(s) dans le DOM rendu"
    )
    return SortieAdaptateur(
        adaptateur=NOM,
        pan=PAN,
        cible=str(cible),
        verdict="FAIL" if [f for f in findings if f.severite == "bloquant"] else "PASS",
        findings=findings,
        non_juge=non_juge,
        non_testables=non_testables,
        surface={
            "inventorie": total,
            "exerce": len(exerces),
            "ratio": round(ratio, 4),
            "seuil": SEUIL,
            "elements_exerces": sorted(exerces),
            "elements_non_exerces": sorted(set(inventaire) - set(exerces)),
        },
    )
