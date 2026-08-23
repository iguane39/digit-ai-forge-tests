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

# Familles BLOQUANTES du socle, avec ce qu'elles disent au lecteur. Le libellé n'est pas
# décoratif : « v4_overlap » ne se corrige pas, « deux blocs se superposent » se corrige.
FAMILLES_BLOQUANTES = {
    "v1_overflow": "débordement horizontal",
    "v4_overlap": "chevauchement de blocs",
    "l2_width": "largeur de texte bridée",
    "l2_gouttiere": "gouttière d'étiquettes",
    "l2_conteneur": "conteneur de lecture calé à gauche",
    "l2_filet": "texte écrasé en filet",
}
# AVERTISSEMENTS : mesurés, publiés, et jamais bloquants. `l2_freres` (TF-0491) parce qu'une
# mesure de lecture étroite est un choix défendable qui se DÉCLARE ; V3/V7 parce que le socle
# lui-même les tient pour des avertissements.
FAMILLES_AVERTIES = {
    "l2_freres": "alignement entre frères empilés",
    "v3_align": "alignement d'une série",
    "v7_spacing": "rythme d'espacement",
}

NON_JUGE = [
    "plancher : mesure a l etat INITIAL de chaque route — les etats atteints apres interaction "
    "(menu ouvert, modale, filtre, message d erreur) ne sont pas mesures ici. La matrice "
    "d etats du socle (render_page.py --matrice-etats, TF-0493) les joue sur un FICHIER, elle "
    "n est pas cablee sur une instance servie",
    "plancher : V5 croisements de fleches et V6 images deformees restent une inspection "
    "HUMAINE sur captures — ce pan ne produit pas d image, il lit des mesures du DOM",
    "plancher : la largeur de fenetre est celle du parcours servi (une seule) — les "
    "breakpoints se jouent au pan `front` et par oracle-mobile, pas ici",
    "plancher : ce pan juge un PLANCHER, jamais une intention graphique. « Ce n est pas "
    "desirable » n est decidable par aucun script (doctrine du socle de marque)",
]


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

    def action(page: Any, _route: str) -> tuple[Any, str | None]:
        page.wait_for_timeout(150)  # styles et polices posees avant de mesurer la geometrie
        return page.evaluate(mesure), None

    resultats, motifs = parcourir(cible, routes, action, prefixe="plancher")
    socle = [
        *NON_JUGE,
        f"plancher : {len(routes)} route(s) a mesurer — provenance : "
        + (provenance or "inventaire fourni a l adaptateur"),
    ]
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

    if not mesurees:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=sorted(set(non_juge)))
    non_juge.append(f"plancher : routes mesurees — {', '.join(mesurees)}")
    return SortieAdaptateur(
        adaptateur=NOM, pan=PAN, cible=str(cible),
        verdict="FAIL" if findings else "PASS",
        findings=findings, non_juge=sorted(set(non_juge)),
    )
