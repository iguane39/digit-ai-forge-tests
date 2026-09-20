"""Adaptateur Plancher visuel (Q4) — V1 débordement, V4 chevauchement et L2 sur le RENDU SERVI.

POURQUOI CE PAN EXISTE (TF-0480, 23/08/2026). Le plancher visuel — un texte ne déborde pas, deux
blocs ne se superposent pas, une colonne de texte n'est pas bridée au tiers de la fenêtre — était
atteignable sur un FICHIER HTML local et sur rien d'autre. Les trois autres portes étaient fermées,
chacune pour une raison VALABLE, et c'est ce qui rendait le trou invisible :

  1. `oracle-mobile` de forge-design déclare en tête que « ce qui exige un rendu réel (taille
     effective après cascade, gestes, DÉBORDEMENTS AU BREAKPOINT) est délégué à render_page.py » —
     une délégation vers un outil dont la signature prenait un chemin de fichier ;
  2. le pan `visuel` est un pan de NON-RÉGRESSION SUR GOLDENS, et sa propre doctrine dit qu'un
     golden absent produit un SKIP motivé : il ne peut donc RIEN dire au premier regard, et un
     golden accepté après coup ENTÉRINE un défaut déjà présent ;
  3. le pan `accessibilite` juge des règles axe-core, pas une mise en page.

PREUVE DU COÛT : sur un site public, un en-tête compressé et un menu anglais au tiers de la
largeur ont vécu de juin à août 2026, à travers DEUX campagnes de vérification déclarées
complètes.

CE QUE CE PAN NE FAIT PAS, et c'est ce qui lui donne sa forme. Il ne recopie aucune mesure : il
charge `MEASURE_JS` depuis le script du socle et l'évalue dans la page VIVANTE, exactement comme le
pan `contraste` livré par TF-0409. La géométrie reste mesurée à UN seul endroit du parc. Et il ne
mesure pas un fichier : un DOM capturé puis relu depuis le disque perd ses feuilles de style — un
débordement mesuré sur une page non stylée est un faux vert.

LE FAIT QUI REND CE PAN PRESQUE GRATUIT, et qu'il fallait voir : la mesure tournait DÉJÀ sur les
routes servies depuis TF-0409. Elle rend `v1_overflow`, `v4_overlap` et toute la famille `l2_*` en
même temps que `v2_contrast` — et le pan `contraste` ne lisait que le contraste. Le reste était
mesuré puis JETÉ. Ce pan ne fait pas tourner un contrôle de plus : il lit ce qui était déjà mesuré.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forge_tests import classes
from forge_tests.adaptateurs import accessibilite, contraste
from forge_tests.adaptateurs._parcours import parcourir
from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "plancher-rendu", "plancher"

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "servir le front (build présent et `npm`/navigateur disponibles) ou déclarer l'instance "
    "SERVIE dans FORGE_TESTS_BASE_URL, ET disposer du socle digit-ai-page-html installé "
    "(`scripts/render_page.py`, dont les mesures V1/V4/L2 sont chargées ici) : le pan juge la "
    "GÉOMÉTRIE RENDUE, il n'a rien à mesurer sur un fichier dont les feuilles de style ne se "
    "chargent pas"
)

CHAPITRES = (
    {"code": "F5", "famille": "fonctionnel", "titre": "Rendu visuel",
     "decoupe": "ecran", "axe_cas": "plancher"},
)

CHAMPS_REQUIS = (
    "FORGE_TESTS_BASE_URL",
    "FORGE_TESTS_LOGIN",
    "FORGE_TESTS_PASSWORD",
)

# LES FAMILLES ET LEUR POIDS SONT LUS DANS LE SOCLE (choix humain du 23/08/2026, option « source
# unique »). Ce pan tenait DEUX dictionnaires en copie — bloquantes d'un côté, averties de
# l'autre — et c'est cette forme de copie qui a laissé, chez forge-design, deux familles
# bloquantes se faire relire en simple avertissement sans que rien ne le dise. Le pan charge déjà
# la mesure depuis le socle : lire son poids au même endroit n'ajoute aucune dépendance.
#
# Le contraste n'est PAS repris ici : il a son pan (`contraste`), et la chaîne des consommateurs
# est jugée dans son ensemble par le pilot (règle N-10) — ce qui compte est qu'aucune famille ne
# soit lue par personne, pas que chacun lise tout.
HORS_PLANCHER = ("v2_contrast",)

# ---------------------------------------------------------------------------
# TF-1093 (20/09/2026) — LES FILTRES CROISES, SUR L INSTANCE SERVIE.
#
# CE QUE `NON_JUGE` DISAIT DE CE PAN, et qui etait vrai : « les etats atteints apres interaction
# ne sont pas mesures ici ; la matrice d etats du socle les joue sur un FICHIER, elle n est pas
# cablee sur une instance servie ». Ce pan parcourt pourtant DEJA des routes servies, dans un
# navigateur pilote. Ce qui manquait n etait pas l instance : c etait le GESTE.
#
# L OPTION EST DECLAREE, ET ABSENTE PAR DEFAUT. Croiser deux filtres sur chaque route coute
# autant de chargements que de croisements ; un pan de plancher ne paie pas ce prix sans qu on
# le lui demande. `FORGE_TESTS_PLANCHER_CROISEMENTS=1` l active, et son absence se DIT au
# non juge — jamais un silence qui se lirait comme « rien a croiser ».
#
# LA SOURCE DU GESTE EST LE SOCLE, JAMAIS UNE COPIE. La fonction `jouer_paires` vit dans
# `render_page.py` et n est pas recopiee ici — meme discipline que `MEASURE_JS`. Tant que la
# copie INSTALLEE du socle ne la porte pas, le pan se declare NON JUGE en nommant le remede :
# la propagation versionne -> installe est une decision humaine (gate TF-0391), pas un geste
# d adaptateur. `FORGE_TESTS_SOCLE_RENDER_PAGE` permet de viser une autre copie du socle.
#
# ET AUCUNE PAGE TIERCE N EST ACTIONNEE. Un croisement CLIQUE dans la page : sur une instance
# distante (recette, preproduction declaree par FORGE_TESTS_BASE_URL), ce pan lit, il
# n interagit pas. Seules les origines locales sont croisees ; les autres sont declarees.
OPTION_CROISEMENTS = "FORGE_TESTS_PLANCHER_CROISEMENTS"
ENV_SOCLE = "FORGE_TESTS_SOCLE_RENDER_PAGE"
HOTES_LOCAUX = {"localhost", "127.0.0.1", "::1"}
PAIRES_MAX = 12                  # plafond du pan : la couverture reelle est publiee a cote
CROISEMENTS_TIMEOUT_MS = 30000


def _socle_croisements() -> tuple[Any, str | None]:
    """La fonction `jouer_paires` du socle, ou (None, motif) — jamais une copie, jamais un vert.

    Le chemin par defaut est celui du socle INSTALLE, comme pour la mesure. Un socle sans
    `jouer_paires` n est pas une panne : c est une copie anterieure a TF-1093, et le pan le dit.
    """
    import importlib.util
    import os
    chemin = Path(os.environ.get(ENV_SOCLE) or contraste._SOCLE)  # noqa: SLF001 — un seul socle
    if not chemin.exists():
        return None, f"socle introuvable ({chemin})"
    try:
        spec = importlib.util.spec_from_file_location("_socle_croisements", chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as erreur:  # noqa: BLE001 — un socle illisible se declare, il n arrete rien
        return None, f"socle illisible ({type(erreur).__name__}) — {chemin}"
    fn = getattr(module, "jouer_paires", None)
    if fn is None:
        return None, (
            f"la copie du socle lue ici ne porte pas `jouer_paires` ({chemin}) — elle est "
            "anterieure a TF-1093. Remede : propager la source versionnee de "
            "`digit-ai-forge-agents/.claude/skills/digit-ai-page-html` vers la copie installee "
            "(decision humaine, gate TF-0391 : `node oracles/oracle-skills.mjs --appliquer`), "
            f"ou viser une autre copie par {ENV_SOCLE}"
        )
    return fn, None


def _croiser_sur_place(jouer: Any, page: Any, mesure: str) -> dict:
    """Joue les croisements sur la page VIVANTE deja ouverte par le parcours."""
    import shutil
    import tempfile
    from urllib.parse import urlsplit
    url = page.url
    hote = (urlsplit(url).hostname or "").lower()
    if hote not in HOTES_LOCAUX:
        return {"motif": f"origine `{hote or '?'}` NON LOCALE — aucun croisement n est CLIQUE "
                         "sur une instance tierce : ce pan la lit, il ne l actionne pas"}
    largeur = (page.viewport_size or {}).get("width") or 1280
    dossier = Path(tempfile.mkdtemp(prefix="plancher-croisements-"))
    try:
        return jouer(page, url, mesure, PAIRES_MAX, CROISEMENTS_TIMEOUT_MS,
                     dossier, "plancher", largeur)
    except Exception as erreur:  # noqa: BLE001 — une route isolee, jamais une fin de run
        # Le TYPE seul ne dit rien : `Error` est le nom de toute levee de Playwright, et un
        # motif qui s arrete la coute une enquete (mesure du 20/09). La cause part au rapport.
        return {"motif": f"croisements non joues ({type(erreur).__name__}) — "
                         f"{str(erreur).splitlines()[0][:200] if str(erreur) else 'sans message'}"}
    finally:
        # Les captures du socle sont jetees : ce pan lit des mesures du DOM et ne produit pas
        # d image (deja declare au non juge). Les garder salirait l arbre du produit audite.
        shutil.rmtree(dossier, ignore_errors=True)


def _familles_du_socle() -> tuple[dict[str, str], dict[str, str]]:
    """(bloquantes, averties) telles que le socle les déclare. Vides si le socle est absent."""
    import json
    import subprocess
    if not contraste._SOCLE.exists():  # noqa: SLF001 — un seul chemin de socle pour tout le parc
        return {}, {}
    for binaire in ("python", "python3", "py"):
        try:
            r = subprocess.run([binaire, "-X", "utf8", str(contraste._SOCLE), "--familles"],  # noqa: SLF001
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
        except Exception:  # noqa: BLE001 — interpréteur absent : on essaie le suivant
            continue
        if r.returncode != 0:
            continue
        try:
            lu = json.loads((r.stdout or "").strip())
        except Exception:  # noqa: BLE001
            continue
        if lu.get("schema") != "digit-ai/familles-mesure@1":
            continue
        bloquantes, averties = {}, {}
        for cle, v in (lu.get("familles") or {}).items():
            if cle in HORS_PLANCHER:
                continue
            if v.get("severite") == "bloquant":
                bloquantes[cle] = v.get("libelle", cle)
            elif v.get("severite") == "avertissement":
                averties[cle] = v.get("libelle", cle)
        return bloquantes, averties
    return {}, {}

NON_JUGE = [
    "plancher : mesure a l etat INITIAL de chaque route — les etats atteints apres interaction "
    "(menu ouvert, modale, filtre, message d erreur) ne sont pas mesures ici. La matrice "
    "d etats du socle (render_page.py --matrice-etats, TF-0493) n est pas cablee sur ce pan. "
    "Une seule porte est ouverte, et sur demande : les FILTRES CROISES (jouer_paires, TF-1093) "
    f"se jouent sur l instance SERVIE quand {OPTION_CROISEMENTS}=1 — option absente par defaut, "
    "etat declare a chaque execution, couverture publiee en « N paires jouees sur M possibles »",
    "plancher : V5 croisements de fleches et V6 images deformees restent une inspection "
    "HUMAINE sur captures — ce pan ne produit pas d image, il lit des mesures du DOM",
    "plancher : la largeur de fenetre est celle du parcours servi (une seule) — les "
    "breakpoints se jouent au pan `front` et par oracle-mobile, pas ici",
    "plancher : ce pan juge un PLANCHER, jamais une intention graphique. « Ce n est pas "
    "desirable » n est decidable par aucun script (doctrine du socle de marque)",
]


def _lire_croisements(route: str, croisements: dict, bloquantes: dict[str, str],
                      averties: dict[str, str], findings: list[Finding],
                      cible: Path) -> list[str]:
    """Traduit le rapport de croisements du socle en constats du pan. Rend son non juge.

    LA COUVERTURE SE DIT AVANT LES CONSTATS. « 0 bloquant » sur 3 croisements joues parmi 40
    n est pas le meme verdict que sur 40 joues parmi 40, et rien dans les constats ne permet de
    faire la difference : seule la couverture le dit.
    """
    dits: list[str] = []
    if croisements.get("motif"):
        return [f"plancher : [{route}] FILTRES CROISES NON JOUES — {croisements['motif']}"]
    jouees, possibles = croisements.get("jouees", 0), croisements.get("possibles", 0)
    ligne = (f"plancher : [{route}] filtres croises — {jouees} paire(s) jouee(s) sur "
             f"{possibles} possible(s) (plafond {croisements.get('plafond')}, "
             f"{croisements.get('colonnes', 0)} colonne(s) a facette). Enumeration par PAIRES : "
             "les croisements de trois facettes et plus ne sont pas juges")
    if possibles > jouees:
        ligne += (f". {possibles - jouees} croisement(s) NON JOUE(S) — ne pas lire ce verdict "
                  "comme une couverture complete")
    dits.append(ligne)
    for nom, c in (croisements.get("combinaisons") or {}).items():
        if not c.get("applique"):
            dits.append(f"plancher : [{route}] croisement « {nom} » NON JOUE — "
                        f"{c.get('motif', 'declencheur introuvable')}")
            continue
        for famille, quoi_dit in bloquantes.items():
            for ecart in (c.get("issues") or {}).get(famille, []) or []:
                quoi = str(ecart.get("what", "element"))
                identifiant = f"plancher:{route}:croisement:{famille}:{quoi[:40]}"
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.REGRESSION_VISUELLE,
                        localisation=route,
                        message=(f"[{route}] filtres croises « {nom} » — {quoi_dit} : {quoi} : "
                                 f"{ecart.get('detail', '')}"),
                        severite="bloquant",
                        risque=coter(PAN, identifiant, str(cible / "frontend")),
                    )
                )
        for famille, quoi_dit in averties.items():
            for ecart in (c.get("issues") or {}).get(famille, []) or []:
                dits.append(f"plancher : [{route}] croisement « {nom} » — {quoi_dit} "
                            f"(avertissement, jamais bloquant) — "
                            f"{ecart.get('what', 'element')} : {ecart.get('detail', '')}")
    return dits


def sans_objet(cible: Path) -> str | None:
    """Meme frontiere que le pan accessibilite : pas d interface, pas de geometrie a juger."""
    return accessibilite.sans_objet(cible)


def inventaire(cible: Path) -> list[Element]:
    routes, _ = accessibilite.routes_a_auditer(cible)
    return [
        Element(id=f"plancher:{route}", pan=PAN, libelle=f"plancher visuel de {route}",
                source=str(cible / "frontend"))
        for route in routes
    ]


def analyser(cible: Path) -> SortieAdaptateur:
    # La mesure est chargée depuis le socle, jamais recopiée : si le socle corrige sa géométrie,
    # ce pan en hérite sans une ligne. C'est aussi pour cela que la fonction est réutilisée
    # telle quelle depuis le pan `contraste` — deux chargeurs auraient divergé.
    mesure = contraste._mesure_js()  # noqa: SLF001 — un seul chargeur pour tout le parc
    FAMILLES_BLOQUANTES, FAMILLES_AVERTIES = _familles_du_socle()
    if mesure is not None and not FAMILLES_BLOQUANTES:
        # Le socle est là mais ne publie pas ses poids : on ne DEVINE pas une sévérité. Un poids
        # inventé rendrait un verdict qui a l'air d'un verdict.
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"plancher : le socle ne publie pas sa table de familles ({contraste._SOCLE} "  # noqa: SLF001
                "--familles) — sans elle, peser un constat reviendrait a recopier une liste, "
                "c'est-a-dire a recreer la double verite que ce changement supprime",
            ],
        )
    if mesure is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"plancher : mesures V1/V4/L2 introuvables — {contraste._SOCLE} absent ou "  # noqa: SLF001
                "illisible. Le pan ne recopie pas la geometrie : sans le socle, il se declare "
                "non mesure",
            ],
        )
    routes, provenance = accessibilite.routes_a_auditer(cible)
    if not routes:
        return accessibilite.verdict_sans_route(NOM, PAN, cible, NON_JUGE)

    # TF-1093 — l option est lue UNE fois, avant le parcours : son etat (active ou non, socle
    # capable ou non) se dit au rapport, que des croisements aient ete joues ou pas.
    import os
    croisements_demandes = os.environ.get(OPTION_CROISEMENTS, "").strip() not in ("", "0")
    croiser, motif_croisements = (_socle_croisements() if croisements_demandes else (None, None))

    def action(page: Any, _route: str) -> tuple[Any, str | None]:
        page.wait_for_timeout(150)  # styles et polices posees avant de mesurer la geometrie
        issues = page.evaluate(mesure)
        if croiser is not None and isinstance(issues, dict):
            issues["_croisements"] = _croiser_sur_place(croiser, page, mesure)
        return issues, None

    resultats, motifs = parcourir(cible, routes, action, prefixe="plancher")
    socle = [
        *NON_JUGE,
        f"plancher : {len(routes)} route(s) a mesurer — provenance : "
        + (provenance or "inventaire fourni a l adaptateur"),
    ]
    if not croisements_demandes:
        socle.append(
            f"plancher : FILTRES CROISES NON JOUES — option {OPTION_CROISEMENTS} absente. Un "
            "tableau filtrable dont l intersection de deux facettes ne laisse aucune ligne, "
            "sans un mot pour le dire, n est pas juge ici (TF-1093)")
    elif motif_croisements:
        socle.append(f"plancher : FILTRES CROISES NON JOUES — {motif_croisements}")
    if not resultats and not motifs:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*socle, "front non servi : build absent, npm ou navigateur manquant"],
        )

    findings: list[Finding] = []
    non_juge = [*socle, *motifs]
    mesurees: list[str] = []
    for route, issues in resultats.items():
        if not isinstance(issues, dict):
            non_juge.append(f"plancher : route {route} — mesure illisible, page non jugee")
            continue
        mesurees.append(route)
        # TF-1093 — les croisements voyagent DANS la mesure de la route (une action ne rend
        # qu une valeur) ; ils en sont retires avant que les familles ne soient lues, pour
        # qu aucune boucle ne prenne ce sac pour une famille de constats.
        croisements = issues.pop("_croisements", None)
        for famille, quoi_dit in FAMILLES_BLOQUANTES.items():
            for ecart in issues.get(famille, []) or []:
                quoi = str(ecart.get("what", "element"))
                detail = str(ecart.get("detail", ""))
                identifiant = f"plancher:{route}:{famille}:{quoi[:40]}"
                findings.append(
                    Finding(
                        id=identifiant,
                        classe=classes.REGRESSION_VISUELLE,
                        localisation=route,
                        message=f"[{route}] {quoi_dit} — {quoi} : {detail}",
                        severite="bloquant",
                        risque=coter(PAN, identifiant, str(cible / "frontend")),
                    )
                )
        # Le PLAFOND de V1 du socle (TF-0382) : quand l inventaire a ete tronque, le total exact
        # est ailleurs. Le taire ferait lire « 20 debordements » sur une page qui en a 200.
        tronque = issues.get("v1_tronque")
        if isinstance(tronque, dict) and tronque.get("total"):
            non_juge.append(
                f"plancher : [{route}] inventaire des debordements TRONQUE — "
                f"{tronque.get('total')} cause(s) reelle(s), "
                f"{len(issues.get('v1_overflow', []) or [])} detaillee(s) ; "
                f"{tronque.get('motif', 'borne declaree par le socle')}"
            )
        for famille, quoi_dit in FAMILLES_AVERTIES.items():
            for ecart in issues.get(famille, []) or []:
                non_juge.append(
                    f"plancher : [{route}] {quoi_dit} (avertissement, jamais bloquant) — "
                    f"{ecart.get('what', 'element')} : {ecart.get('detail', '')}"
                )
        # `unmeasured` est la part HONNETE de la mesure : la taire ferait lire le PASS comme
        # « toute la page est jugee ».
        for inconnu in issues.get("unmeasured", []) or []:
            non_juge.append(
                f"plancher : [{route}] {inconnu.get('what', 'element')} — "
                f"{inconnu.get('detail', 'non mesurable, a verifier a l oeil')}"
            )
        # TF-1093 — les FILTRES CROISES de cette route : leur couverture d abord, leurs
        # constats ensuite, au MEME bareme que l etat au repos (les familles du socle).
        if isinstance(croisements, dict):
            non_juge.extend(_lire_croisements(route, croisements, FAMILLES_BLOQUANTES,
                                              FAMILLES_AVERTIES, findings, cible))

    if not mesurees:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=sorted(set(non_juge)))
    non_juge.append(f"plancher : routes mesurees — {', '.join(mesurees)}")
    return SortieAdaptateur(
        adaptateur=NOM, pan=PAN, cible=str(cible),
        verdict="FAIL" if findings else "PASS",
        findings=findings, non_juge=sorted(set(non_juge)),
    )
