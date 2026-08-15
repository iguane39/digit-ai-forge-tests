"""Dashboard d exécution — page autonome, dont la SEULE source est le rapport JSON.

Pourquoi une seule source : un tableau de bord qui recalcule quoi que ce soit finit par
diverger du rapport, et c est lui qu on regarde. Deux lecteurs du même audit — l un par le
HTML, l autre par `jq` — auraient alors deux vérités, et la discussion porterait sur l outil
au lieu du produit. Ici le HTML ne fait que RENDRE : la classification des actions est calculée
dans `forge_tests.actions` et portée par le rapport ; les totaux sont dérivés du rapport et
republiés en clair dans la page (`data-total`), pour qu un contrôle puisse les recomparer.

Trois contraintes dures, toutes vérifiées :

  - **autonome** : double-cliquable, zéro requête réseau. Pas de police distante (repli
    système déclaré), pas de script externe, pas d image distante. Un livrable d audit part
    par courriel et s ouvre chez quelqu un qui n a pas le dépôt ;
  - **zéro secret** : aucune VALEUR d environnement n entre dans la page. Les noms de
    variables manquantes, oui — c est l information utile ; leurs valeurs, jamais. Le
    garde-fou est codé, il ne repose pas sur la vigilance ;
  - **totaux exacts** : `controler()` relit les totaux affichés et les recompare au rapport.
    Un dashboard qui arrondit est un dashboard qui ment.

Campagne TF-0153 (13/08/2026, cahier de retours validé par l humain) — la page est
l INTERFACE DE DÉCISION du verdict de tests, lisible sans connaître le framework :

  - **clair par défaut, strictement** : un livrable d audit circule et s ouvre pareil chez
    tous. Le sombre est un CHOIX du lecteur (bascule persistée), plus jamais un défaut hérité
    de l OS — c est ce défaut hérité qui a valu le retour humain du 13/08. L impression reste
    claire quel que soit le choix ;
  - **exploration à trois niveaux** (barre Allure, registre la-barre) : tout agrégat cliquable
    mène à sa liste filtrée, et le DÉTAIL d un cas (préconditions, jeu, étapes, attendu,
    exigences) se déplie sur place — c est la dérivation des cahiers, MÊMES références
    stables, embarquée au lieu d être réécrite ;
  - **glossaire d affichage** (`glossaire.py`) : libellés parlants sur identifiants GELÉS
    (contrat pilot §3 bis) — le `jq` du DOSSIER-MEP et la recette lisent les mêmes clés
    qu avant ;
  - **rien de muet** : un élément passé dit « ✓ Passé — aucun constat » (une cellule vide est
    indistinguable d un bug d affichage) ; chaque nombre porte libellé, part et descriptif.

Socle graphique : boilerplate `digit-ai-page-html` (tokens `:root`, Roboto pour les titres,
DM Sans pour le corps, `@media print`). Les liens Google Fonts du boilerplate sont retirés —
ils sont incompatibles avec la contrainte « zéro réseau ». Le repli système est explicite dans
chaque `font-family`, ce que le contrôle de charte exige.

Campagne TF-0235 (15/08/2026, volet P4) — la page se conçoit pour SES lecteurs, référentiel
`REFERENTIEL-RESTITUTION.md` de forge-design. Ce dashboard est de la famille **« suivi »**
(`<body data-restitution="suivi">`) : il est revisité d un audit à l autre, et ses deux
lecteurs types y entrent par des questions opposées —

  - le **pilote** : « est-ce que ça dérive ? où, depuis quand, de combien ? » ;
  - l **opérateur** : « qu y a-t-il dans la file, que traiter d abord ? ».

Ce que la doctrine change ici, sans rien retirer (iso-contenu strict — les six panneaux, leurs
tables et leurs lignes restent) :

  - **vue d ensemble qui conclut** : un `.verdict` explicite (au lieu d un verdict noyé dans
    une phrase), les compteurs devenus des KPI COMPLETS (valeur, définition, repère de lecture,
    action) — un chiffre sans repère ne se lit pas, il se devine ;
  - **figures à question** : chaque graphique porte en `figcaption` la question à laquelle il
    répond, et ne naît QUE si la donnée existe. Pas de rapport précédent fourni ⇒ pas de
    graphique de tendance : un écart déclaré au manifeste, jamais une courbe inventée. La piste
    d une barre est le FOND CSS du `svg`, jamais un second `rect` — deux rects superposés sont
    un chevauchement au sens du contrôle de rendu du socle ;
  - **chemins d entrée par lecteur** (`.chemins`) : « vous êtes le pilote / l opérateur,
    commencez ici » — chaque chemin est un bouton câblé vers sa vue, jamais un texte mort ;
  - **manifeste d écarts** (`.ecarts`) : ce que cette page ne fait pas se DÉCLARE, calculé sur
    l état réel du rapport — « aucun écart » se déclare aussi. Les limites de mesure déjà
    portées par `NON_JUGE` y entrent : elles vivaient dans le registre de dette, pas sous les
    yeux du lecteur ;
  - **routeur à ancres** : une ancre qui pointe dans un panneau masqué OUVRE le panneau avant
    d y défiler — sans quoi la moitié des renvois de la page seraient des affordances mortes.
"""

from __future__ import annotations

import hashlib
import html as _html
import re
from pathlib import Path

from forge_tests import declarations as _declarations
from forge_tests.actions import (
    CATEGORIES,
    ETAPES,
    PREFIXE_NON_TESTABLE,
    PREFIXE_PAN_NON_COUVERT,
    repartition,
)
from forge_tests.livrables import glossaire as _glossaire
from forge_tests.livrables import surface as _surface
from forge_tests.livrables.jeux import _valeurs_de_configuration
from forge_tests.livrables.libelles import libelle_element as _libelle_element
from forge_tests.livrables.libelles import objectif_element as _objectif_element

NON_JUGE = [
    "dashboard : la page rend le rapport, elle ne le juge pas — un chiffre surprenant se "
    "conteste sur le rapport JSON, jamais sur le HTML",
    "dashboard : l etat d un seuil est derive du RAPPROCHEMENT entre sa valeur et les findings "
    "`seuil-non-tenu` qui la citent ; deux seuils de meme valeur ne sont pas discernables par "
    "ce rapprochement et sont alors tous deux marques « non tenu »",
    "dashboard : la tendance compare deux rapports par leurs TOTAUX — elle ne dit pas si ce "
    "sont les memes elements qui ont bouge",
    "dashboard : le detail d un cas est la derivation des cahiers (memes references stables) — "
    "sa pertinence pedagogique est celle du cahier, la page ne l ameliore pas",
    "dashboard : un constat DECLARE par le projet (RT-18) sort du compteur « Constats d echec » "
    "et reste integralement affiche, avec son motif type et sa contre-preuve — la page rend la "
    "declaration, elle ne la valide pas",
    "dashboard : une figure n existe que si la donnee existe — une figure ABSENTE signale une "
    "donnee absente du rapport, jamais une donnee nulle ou un choix de mise en page",
]


class SecretDansLeDashboard(RuntimeError):
    """Une valeur de configuration a été retrouvée dans la page. Rien n est écrit."""


# --- Totaux -----------------------------------------------------------------------------------
def totaux(rapport: dict) -> dict[str, int]:
    """Compteurs publiés par la page. Une seule définition, pour le rendu ET pour le contrôle."""
    inventaire = _surface.inventaire(rapport)
    elements = [e for liste in inventaire.values() for e in liste]
    # RT-18 : un constat que le PROJET a déclaré (contesté avec contre-preuve, bloqué par
    # configuration absente ou par du code supplanté) sort du décompte principal — jamais de la
    # page : il reste dans l inventaire, dans la table des échecs, et dans son propre compteur.
    tous = rapport.get("findings") or []
    findings = [f for f in tous if not _declarations.est_ecarte(f)]
    declares = [f for f in tous if _declarations.est_ecarte(f)]
    actions = rapport.get("actions") or []
    compte = repartition(actions)
    valeurs = {
        "elements": len(elements),
        "passes": sum(1 for e in elements if e["etat"] == "exerce"),
        "echecs": len(findings),
        "declares": len(declares),
        "echecs_bloquants": sum(1 for f in findings if f.get("severite") == "bloquant"),
        "non_testables": len(rapport.get("non_testables") or []),
        "pans_non_couverts": len(rapport.get("pans_non_couverts") or []),
        "actions": len(actions),
    }
    valeurs["non_joues"] = valeurs["non_testables"] + valeurs["pans_non_couverts"]
    for categorie in CATEGORIES:
        valeurs[f"actions_{categorie}"] = compte["par_categorie"].get(categorie, 0)
    for etape in ETAPES:
        valeurs[f"etape_{etape.replace('-', '_')}"] = compte["par_etape"].get(etape, 0)
    return valeurs


_TOTAL_AFFICHE = re.compile(
    r'data-total="(?P<cle>[a-z_]+)"[^>]*>(?P<valeur>-?\d+)<', re.IGNORECASE
)


def controler(page: str, rapport: dict) -> list[str]:
    """Divergences entre les totaux AFFICHÉS et ceux du rapport. Liste vide = page fidèle."""
    attendus = totaux(rapport)
    affiches = {
        m["cle"]: int(m["valeur"]) for m in _TOTAL_AFFICHE.finditer(page)
    }
    ecarts = []
    for cle, valeur in sorted(attendus.items()):
        if cle not in affiches:
            ecarts.append(f"total « {cle} » absent de la page (attendu {valeur})")
        elif affiches[cle] != valeur:
            ecarts.append(
                f"total « {cle} » affiché {affiches[cle]}, rapport {valeur} — la page ment"
            )
    for cle in sorted(set(affiches) - set(attendus)):
        ecarts.append(f"total « {cle} » affiché sans contrepartie au rapport ({affiches[cle]})")
    return ecarts


def verifier_absence_de_secrets(page: str, cible: Path | None) -> None:
    """Lève si un SECRET entre dans la page. Le nom d un champ manquant, oui ; sa valeur, non.

    Le garde-fou porte sur le premier cercle (jeton, clé, mot de passe), pas sur toute valeur
    de configuration : l URL de l instance auditée figure légitimement au rapport — elle EST le
    sujet de l audit — et la masquer rendrait les constats du pan `qualif` inintelligibles. Le
    second cercle, lui, reste interdit dans les jeux de données, qui doivent être intégralement
    fabriqués. La frontière est déclarée, pas commode.
    """
    for valeur in _valeurs_de_configuration(cible, secrets_seulement=True):
        if valeur and valeur in page:
            raise SecretDansLeDashboard(
                "un secret (jeton, clé, mot de passe — variable sensible ou `.env` du projet) "
                "figure dans le dashboard. Un livrable d audit circule : seuls les NOMS des "
                "champs manquants y sont publiables, jamais leurs valeurs"
            )


# --- Rendu ------------------------------------------------------------------------------------
def _e(valeur: object) -> str:
    return _html.escape(str(valeur if valeur is not None else ""), quote=True)


def _texte_libre(valeur: object) -> str:
    """Texte LIBRE d un constat mesuré : peut légitimement citer le vocabulaire technique du
    projet audité (SQL, code, schéma — ex. « NOT NULL »). Loi transverse n° 3 : une valeur
    ABSENTE ne doit jamais s afficher en littéral technique — mais un constat qui NOMME une
    contrainte « NOT NULL » n en est pas une, c est le fait mesuré lui-même. `_e` traite déjà
    toute valeur manquante en chaîne vide (jamais ce littéral) ; `data-litteral-ok` dit à
    l oracle socle (L11) que le mot « NULL » rencontré ici est un terme du domaine, cité
    fidèlement, pas une valeur non traitée qui a fuité.
    """
    return f"<span data-litteral-ok>{_e(valeur)}</span>"


# Tokens SOMBRES, une seule définition — servie deux fois : au choix explicite du lecteur
# (`data-theme="sombre"`) et au forçage inverse de l impression (jamais de papier sombre).
_TOKENS_SOMBRES = """
      --bg:#0B1120; --surface:#131C2E; --card:#131C2E; --ink:#E8EDF7; --muted:#9BA9C0;
      --faint:#6B7A93; --line:#25324A; --amber-fill:#2A2113; --amber-line:#4A3A1A;
      --teal-fill:#0E2A28; --teal-line:#1C4A46; --green-fill:#0F2A1B; --green-line:#1D4A2F;
      --red-fill:#2C1414; --red-line:#5A2222; --blue:#7CA6FF; --green:#4ADE80;
      --amber:#FBBF24; --red:#F87171; --teal:#5EEAD4;
      --amber-ink:#FBBF24; --teal-ink:#5EEAD4; --green-ink:#4ADE80; --red-ink:#F87171;
"""

_TOKENS_CLAIRS = """
      --blue:#2563EB; --bg:#FAFBFF; --surface:#FFFFFF; --card:#FFFFFF;
      --ink:#0F172A; --muted:#64748B; --faint:#94A3B8; --line:#E6EAF2;
      --amber:#D97706; --amber-fill:#FFFBEB; --amber-line:#FDE9C8;
      --teal:#0E9488; --teal-fill:#EFFDFB; --teal-line:#C7F0EA;
      --green:#15803D; --green-fill:#F2FCF5; --green-line:#CFEEDD;
      --red:#B91C1C; --red-fill:#FEF2F2; --red-line:#FBD5D5;
      --amber-ink:#92400E; --teal-ink:#115E59; --green-ink:#14532D; --red-ink:#991B1B;
"""

# Favicon-lettre en `data:` URI — coupée en deux constantes, non par coquetterie : la ligne
# entière fait 398 caractères et un `data:` URI ne se replie pas (le retour à la ligne
# entrerait dans la valeur de l attribut). L assemblage rend une sortie identique au
# caractère près, ce que prouve l empreinte du dashboard en recette.
_FAVICON_AVANT = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'"
    "%3E%3Crect width='64' height='64' rx='14' fill='%232563EB'/%3E%3Ctext x='32' y='44'"
    " font-family='Segoe UI,Roboto,sans-serif' font-size='38' font-weight='700'"
    " fill='white' text-anchor='middle'%3E"
)
_FAVICON_APRES = "%3C/text%3E%3C/svg%3E"


_STYLE = f"""
    /* CLAIR PAR DÉFAUT, STRICTEMENT (TF-0153, retour humain du 13/08). L auto-sombre hérité
       de l OS (`prefers-color-scheme`) est retiré : un livrable d audit circule et doit
       s ouvrir identique chez tous ses lecteurs. Le sombre reste à un clic, persisté. */
    :root {{{_TOKENS_CLAIRS}
      /* Encres des pastilles. Le ton d accent de la charte sert aux FILETS ; posé en TEXTE sur
         son propre fond pâle, l ambre tombe à 3,07:1 — sous les 4,5:1 de WCAG AA, mesuré par
         `render_page.py`. Un statut illisible est un statut qu on ne lit pas : la pastille a
         donc son encre propre, foncée, et le ton d accent reste à la bordure. */
      --r:12px; --r-sm:8px;
      --head:"Roboto", system-ui, -apple-system, "Segoe UI", sans-serif;
      --sans:"DM Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
      --mono:"JetBrains Mono", ui-monospace, "Consolas", monospace;
    }}
    :root[data-theme="sombre"] {{{_TOKENS_SOMBRES}}}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
           line-height:1.55; font-size:16px; }}
    /* E4 : 75-100 % de la fenêtre, toujours — 92vw sous ~1826px, plafond confort 1680px,
       plancher 75vw au-delà. Jamais de plafond px nu. */
    .wrap {{ max-width:clamp(75vw, 1680px, 92vw); margin:0 auto; padding:32px 24px 64px; }}
    h1,h2,h3,h4 {{ font-family:var(--head); font-weight:800; color:var(--ink); line-height:1.2; }}
    h1 {{ font-size:2rem; margin:0 0 .25em; }}
    h2 {{ font-size:1.4rem; font-weight:700; margin:0 0 .6em; }}
    h3 {{ font-size:1.1rem; font-weight:700; margin:1.6em 0 .4em; }}
    h4 {{ font-size:1rem; font-weight:700; margin:1.2em 0 .3em; color:var(--muted); }}
    p {{ margin:0 0 1em; }}
    a {{ color:var(--blue); }}
    code, pre {{ font-family:var(--mono); font-size:.86em; }}
    header.doc {{ border-bottom:2px solid var(--blue); padding-bottom:16px; margin-bottom:20px; }}
    .eyebrow {{ color:var(--muted); font-size:.85rem; letter-spacing:.04em;
               text-transform:uppercase; margin:0 0 .3em; }}
    .card {{ background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
            padding:18px 22px; margin:16px 0; }}
    .grille {{ display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; align-items:stretch; }}
    .tuile {{ flex:1 1 170px; background:var(--surface); border:1px solid var(--line);
             border-radius:var(--r); padding:14px 16px; text-align:left; }}
    /* H3 (standard listes) : un KPI qui compte des éléments AFFICHÉS est un bouton — il mène
       à sa liste, éventuellement filtrée. Un KPI d éléments hors page reste un div et DIT où
       ils vivent. Jamais d affordance morte. */
    button.tuile {{ font:inherit; color:inherit; cursor:pointer; display:flex;
                    flex-direction:column; gap:2px; }}
    button.tuile:hover {{ border-color:var(--blue); }}
    button.tuile:focus-visible, .theme-toggle:focus-visible, a:focus-visible,
    summary:focus-visible, .outillage button:focus-visible, .lien-chapitre:focus-visible,
    .outillage input:focus-visible {{ outline:3px solid var(--blue); outline-offset:2px; }}
    .tuile .chiffre {{ font-family:var(--head); font-size:1.9rem; font-weight:900;
                      display:block; line-height:1.1; }}
    .tuile .quoi {{ color:var(--ink); font-size:.85rem; font-weight:700; }}
    .tuile .part {{ color:var(--muted); font-size:.78rem; }}
    .tuile .delta {{ font-size:.78rem; font-weight:700; }}
    .tuile .delta.mieux {{ color:var(--green-ink); }}
    .tuile .delta.pire {{ color:var(--red-ink); }}
    .tuile .tuile-d {{ color:var(--muted); font-size:.75rem; }}
    .tuile .tuile-va {{ color:var(--blue); font-size:.75rem; font-weight:700; margin-top:auto; }}
    .badge {{ display:inline-block; border-radius:999px; padding:2px 11px; font-size:.8rem;
             font-weight:700; border:1px solid var(--line); }}
    .b-pass {{ background:var(--green-fill); border-color:var(--green-line);
              color:var(--green-ink); }}
    .b-fail {{ background:var(--red-fill); border-color:var(--red-line); color:var(--red-ink); }}
    .b-part {{ background:var(--amber-fill); border-color:var(--amber-line);
              color:var(--amber-ink); }}
    .b-info {{ background:var(--teal-fill); border-color:var(--teal-line);
              color:var(--teal-ink); }}
    .etat-badge {{ white-space:nowrap; }}
    nav.toc {{ display:flex; flex-wrap:wrap; gap:4px 18px; margin:0 0 12px; font-size:.85rem; }}
    nav.toc a {{ color:var(--blue); text-decoration:none; }}
    nav.toc a:hover {{ text-decoration:underline; }}
    nav.toc .toc-d {{ color:var(--muted); }}
    nav.onglets {{ display:flex; flex-wrap:wrap; gap:6px; margin:0 0 20px;
                  border-bottom:1px solid var(--line); }}
    nav.onglets button {{ font-family:var(--sans); font-size:.95rem; font-weight:600;
      background:transparent; color:var(--muted); border:1px solid transparent;
      border-bottom:none; border-radius:var(--r-sm) var(--r-sm) 0 0; padding:9px 15px;
      cursor:pointer; }}
    nav.onglets button[aria-selected="true"] {{ background:var(--surface); color:var(--ink);
      border-color:var(--line); }}
    .theme-toggle {{ font:inherit; font-size:.85rem; border:1px solid var(--line);
      background:var(--surface); color:var(--ink); border-radius:999px; padding:4px 14px;
      cursor:pointer; }}
    .zone-tableau {{ overflow-x:auto; }}
    table {{ border-collapse:collapse; width:100%; font-size:.88rem; table-layout:fixed; }}
    th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--line);
             vertical-align:top; overflow-wrap:anywhere; }}
    th {{ font-family:var(--head); font-size:.78rem; text-transform:uppercase;
         letter-spacing:.03em; color:var(--muted); }}
    th[data-tri] {{ cursor:pointer; }}
    th[data-tri]:hover {{ color:var(--ink); }}
    th .tri-marque {{ font-size:.9em; }}
    .grise {{ opacity:.72; border-style:dashed; }}
    .filtres {{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px; }}
    .filtres button {{ font-family:var(--sans); font-size:.85rem; border:1px solid var(--line);
      background:var(--surface); color:var(--ink); border-radius:999px; padding:5px 13px;
      cursor:pointer; }}
    .filtres button[aria-pressed="true"] {{ background:var(--blue); color:#fff;
      border-color:var(--blue); }}
    /* H1/H2 (standard listes) : recherche + réinitialisation + compteur par tableau outillé. */
    .outillage {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 8px; }}
    .outillage input[type="search"] {{ flex:1 1 240px; font:inherit; font-size:.88rem;
      color:var(--ink); background:var(--surface); border:1px solid var(--line);
      border-radius:var(--r-sm); padding:6px 10px; }}
    .outillage .outil-reinit {{ font:inherit; font-size:.85rem; border:1px solid var(--line);
      background:var(--surface); color:var(--ink); border-radius:var(--r-sm); padding:6px 12px;
      cursor:pointer; }}
    .outillage .outil-compte {{ color:var(--muted); font-size:.82rem; }}
    /* Compte PAR TABLE (G5) : la barre du chapitre agrège toutes ses sous-listes — ce compte-ci
       dit laquelle un filtre vient de vider. Discret : c'est un repère, pas un titre. */
    .compte-table {{ color:var(--muted); font-size:.78rem; margin:4px 0 16px; text-align:right; }}
    .compte-table.zero {{ color:var(--red); font-weight:600; }}
    /* TF-0175 — libellés d'éléments : le lisible d'abord, l'id technique en second. */
    .lib {{ font-weight:600; }}
    /* TF-0175 — détail de cas en LIGNE PLEINE LARGEUR (retour n°6) : cartes côte à côte. */
    .btn-detail {{ font:inherit; font-size:.8rem; color:var(--blue); background:var(--surface);
      border:1px solid var(--line); border-radius:var(--r-sm); padding:3px 10px;
      cursor:pointer; white-space:nowrap; }}
    .btn-detail[aria-expanded="true"] {{ background:var(--blue); color:#fff;
      border-color:var(--blue); }}
    .btn-detail:focus-visible {{ outline:3px solid var(--blue); outline-offset:2px; }}
    tr[data-detail] > td {{ background:var(--bg); border-bottom:2px solid var(--line);
      padding:14px 16px; }}
    .cas-grille {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr));
      gap:12px; }}
    .cas-carte {{ background:var(--surface); border:1px solid var(--line);
      border-radius:var(--r-sm); padding:12px 14px; font-size:.86rem; }}
    .cas-carte p {{ margin:0 0 .5em; }}
    .cas-carte ol {{ margin:.2em 0 .6em; padding-left:1.4em; }}
    .cas-ref {{ color:var(--muted); }}
    /* RT-12 — constat de la route porteuse, rendu sous le constat propre de l'élément. */
    .porteur {{ color:var(--muted); font-size:.92em; }}
    .outil-chapitre {{ margin:6px 0 10px; }}
    /* Chapitres REPLIABLES (retour humain du 14/08) : chevron qui tourne, repli au choix
       du lecteur — ouverts par défaut, le papier déplie tout. */
    details.pli > summary {{ cursor:pointer; list-style:none; }}
    details.pli > summary::-webkit-details-marker {{ display:none; }}
    details.pli > summary h3 {{ display:flex; align-items:center; gap:10px; margin:0; }}
    details.pli > summary .chevron {{ color:var(--blue); font-size:.85em;
      transition:transform .15s ease; transform:rotate(-90deg); }}
    details.pli[open] > summary .chevron {{ transform:none; }}
    details.pli > summary:hover h3 {{ color:var(--blue); }}
    .pli-commandes {{ margin:10px 0 0; }}
    /* KPIs d'état par chapitre (retour humain du 14/08) : compteurs cliquables qui filtrent
       les tables du chapitre. Habillés sur les mêmes pastilles que les badges d'état. */
    .kpis-chapitre {{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 10px; }}
    .kpi-etat {{ font:inherit; font-size:.84rem; font-weight:700; border-radius:999px;
      border:1px solid var(--line); padding:4px 13px; cursor:pointer; }}
    .kpi-etat[aria-pressed="true"] {{ outline:2px solid var(--blue); outline-offset:1px; }}
    .kpi-etat:focus-visible {{ outline:3px solid var(--blue); outline-offset:2px; }}
    /* Colonne « objectif du test » : lisible mais discrète — la donnée d'abord. */
    .objectif {{ font-size:.84rem; color:var(--muted); }}
    /* Actions structurées Quoi / Pourquoi / Vous obtiendrez (retour humain du 14/08). */
    .actions-vous > li {{ margin:0 0 14px; }}
    .actions-vous .a-quoi, .actions-vous .a-pourquoi, .actions-vous .a-obtenu {{
      display:block; margin:2px 0; }}
    .actions-vous .a-pourquoi, .actions-vous .a-obtenu {{ color:var(--muted);
      font-size:.92em; }}
    .discret {{ color:var(--muted); font-size:.86rem; }}
    /* --- Restitution lisible (TF-0235, famille « suivi ») ---------------------------------
       Composants du référentiel, habillés sur les tokens DÉJÀ posés : pas une couleur de plus,
       pas une police de plus. Le verdict conclut, le KPI porte sa lecture, la figure pose sa
       question, le chemin nomme son lecteur, le manifeste déclare ce que la page ne fait pas. */
    .verdict {{ background:var(--surface); border:1px solid var(--line);
      border-left:4px solid var(--blue); border-radius:var(--r); padding:14px 18px;
      margin:0 0 16px; }}
    .verdict p {{ margin:0 0 .45em; }}
    .verdict p:last-child {{ margin:0; }}
    .verdict .v-lecture {{ color:var(--muted); font-size:.9rem; }}
    /* Un KPI complet (RL-3) : la valeur porte `aria-describedby` vers son repère — le chiffre
       n est jamais annoncé seul, ni à l œil ni au lecteur d écran. */
    .tuile .k-repere {{ display:block; font-size:.78rem; color:var(--ink);
      background:var(--bg); border:1px solid var(--line); border-radius:var(--r-sm);
      padding:6px 8px; margin:6px 0 0; }}
    figure.graphe {{ background:var(--surface); border:1px solid var(--line);
      border-radius:var(--r); padding:14px 18px; margin:16px 0; }}
    figure.graphe figcaption {{ font-family:var(--head); font-weight:700; font-size:1rem;
      margin:0 0 4px; }}
    figure.graphe .g-sous {{ color:var(--muted); font-size:.84rem; margin:0 0 12px; }}
    .g-ligne {{ display:grid; grid-template-columns:minmax(110px, 30%) 1fr auto; gap:10px;
      align-items:center; margin:0 0 7px; font-size:.84rem; }}
    .g-nom {{ overflow-wrap:anywhere; }}
    /* La PISTE est le fond du svg (CSS), jamais un second rect : deux rects superposés dans
       un même svg sont un chevauchement, et le contrôle de rendu du socle le refuse. */
    .g-piste {{ display:block; width:100%; height:10px; background:var(--line);
      border-radius:3px; }}
    .g-empile {{ display:block; width:100%; height:14px; background:var(--line);
      border-radius:4px; }}
    .g-val {{ color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}
    .g-legende {{ list-style:none; display:flex; flex-wrap:wrap; gap:6px 18px;
      margin:12px 0 0; padding:0; font-size:.82rem; }}
    .g-puce {{ display:inline-block; width:10px; height:10px; border-radius:3px;
      margin-right:6px; vertical-align:baseline; }}
    .chemins {{ list-style:none; display:grid;
      grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:12px;
      margin:12px 0 0; padding:0; }}
    .chemin {{ background:var(--surface); border:1px solid var(--line);
      border-left:3px solid var(--blue); border-radius:var(--r-sm); padding:12px 14px;
      font-size:.88rem; }}
    .chemin b {{ display:block; font-family:var(--head); margin:0 0 3px; }}
    .chemin .c-question {{ display:block; color:var(--muted); margin:0 0 7px; }}
    .chemin .c-va {{ display:block; margin:8px 0 0; text-decoration:none; }}
    .chemin .c-va:hover {{ text-decoration:underline; }}
    footer.ecarts {{ margin-top:32px; background:var(--surface); border:1px solid var(--line);
      border-radius:var(--r); padding:16px 20px; font-size:.86rem; }}
    footer.ecarts h2 {{ font-size:1.05rem; margin:0 0 .4em; }}
    footer.ecarts h3 {{ font-size:.92rem; margin:1em 0 .3em; }}
    footer.ecarts ul {{ margin:0; padding-left:1.2em; }}
    footer.ecarts li {{ margin:0 0 6px; color:var(--muted); }}
    .lien-chapitre {{ font:inherit; color:var(--blue); background:none; border:none;
      cursor:pointer; text-align:left; padding:0; text-decoration:underline; }}
    footer.doc {{ margin-top:44px; padding-top:14px; border-top:1px solid var(--line);
                 color:var(--muted); font-size:.85rem; }}
    /* Sur mobile, un tableau à sept colonnes ne « défile » pas : il sort de l écran et le
       lecteur ne sait pas qu il manque quelque chose. Les lignes se replient donc en blocs,
       chaque cellule reprenant son intitulé de colonne (`data-label`). Rien n est masqué —
       c est la seule mise en page qui tienne la promesse « aucune absence silencieuse »
       jusque dans le rendu. Mesuré : sans cela, V1 sort douze débordements à 390 px. */
    @media (max-width:640px) {{
      .wrap {{ padding:22px 14px 44px; }}
      h1 {{ font-size:1.5rem; }}
      table, thead, tbody, tr, th, td {{ display:block; width:auto; }}
      thead {{ position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }}
      tr {{ border:1px solid var(--line); border-radius:var(--r-sm); margin:0 0 10px;
           padding:6px 8px; }}
      td {{ border:none; padding:3px 0; }}
      td::before {{ content:attr(data-label) " · "; color:var(--muted); font-size:.76rem;
                   text-transform:uppercase; letter-spacing:.03em; }}
      td:empty {{ display:none; }}
    }}
    @page {{ size:A4 landscape; margin:14mm; }}
    @media print {{
      /* Le papier est TOUJOURS clair, même si le lecteur avait choisi le sombre à l écran. */
      :root, :root[data-theme="sombre"] {{{_TOKENS_CLAIRS}}}
      body {{ background:#FFFFFF; }}
      .wrap {{ max-width:none; padding:0; }}
      nav.onglets, .filtres, .theme-toggle, .outillage, .tuile-va,
      .kpis-chapitre {{ display:none; }}
      .panneau {{ display:block !important; page-break-before:always; }}
      .card, .tuile, tr, figure.graphe, .chemin {{ break-inside:avoid;
        page-break-inside:avoid; }}
      /* Les pistes et les puces des figures sont des FONDS : sans cette demande explicite,
         le papier rend des barres sans échelle et une légende sans couleur. */
      .g-piste, .g-empile, .g-puce {{ -webkit-print-color-adjust:exact;
        print-color-adjust:exact; }}
      /* Le papier montre tout : aucun filtre écran ne masque une ligne à l impression,
         et les détails de cas sont tous dépliés. */
      tr[data-tf-hidden], tr[hidden], tr[data-detail] {{ display:table-row !important; }}
      .btn-detail {{ display:none; }}
      @media (max-width:640px) {{
        tr[data-tf-hidden], tr[hidden], tr[data-detail] {{ display:block !important; }}
      }}
    }}
"""

_SCRIPT = """
(function () {
  var onglets = document.querySelectorAll('nav.onglets button');
  var panneaux = document.querySelectorAll('.panneau');
  function montrer(cible) {
    onglets.forEach(function (b) {
      b.setAttribute('aria-selected', String(b.dataset.cible === cible));
    });
    panneaux.forEach(function (p) { p.hidden = (p.id !== cible); });
  }
  onglets.forEach(function (b) {
    b.addEventListener('click', function () { montrer(b.dataset.cible); });
  });
  montrer(onglets.length ? onglets[0].dataset.cible : '');

  // Trois masquages composables — recherche, sévérité (tuile), filtres d axes — chacun son
  // attribut, la visibilité est DÉRIVÉE : aucun mécanisme n écrase l autre. D-12 (filtres de
  // colonne) reste indépendant via display/data-tf-hidden, et compose de fait.
  function majVisibilite(tr) {
    tr.hidden = tr.hasAttribute('data-rech-cache') || tr.hasAttribute('data-sev-cache')
      || tr.hasAttribute('data-axe-cache') || tr.hasAttribute('data-etat-cache');
    if (tr.hidden) replierDetail(tr); // la ligne de détail suit sa ligne mère
  }
  var filtres = document.querySelectorAll('.filtres button');
  function appliquerFiltresActions() {
    var choix = {};
    document.querySelectorAll('.filtres button[aria-pressed="true"]').forEach(function (a) {
      choix[a.dataset.axe] = a.dataset.valeur;
    });
    document.querySelectorAll('#table-actions tbody tr').forEach(function (tr) {
      var ok = Object.keys(choix).every(function (axe) {
        return tr.dataset[axe] === choix[axe];
      });
      if (ok) { tr.removeAttribute('data-axe-cache'); }
      else { tr.setAttribute('data-axe-cache', ''); }
      majVisibilite(tr);
    });
    recompterTout();
  }
  filtres.forEach(function (b) {
    b.addEventListener('click', function () {
      var actif = b.getAttribute('aria-pressed') === 'true';
      filtres.forEach(function (a) {
        if (a.dataset.axe === b.dataset.axe) { a.setAttribute('aria-pressed', 'false'); }
      });
      b.setAttribute('aria-pressed', actif ? 'false' : 'true');
      appliquerFiltresActions();
    });
  });

  // Sommaire → onglets : une ancre vers un panneau masqué serait morte ; le clic bascule.
  document.querySelectorAll('nav.toc a').forEach(function (a) {
    a.addEventListener('click', function () { montrer(a.getAttribute('href').slice(1)); });
  });

  // Bascule de thème (S-G1 adapté TF-0153) : CLAIR par défaut strict, choix PERSISTÉ.
  var bascule = document.getElementById('bascule-theme');
  var racine = document.documentElement;
  function poserTheme(theme) {
    if (theme === 'sombre') { racine.setAttribute('data-theme', 'sombre'); }
    else { racine.removeAttribute('data-theme'); }
    try { localStorage.setItem('digitai-theme-dashboard', theme); } catch (e) {}
    if (bascule) {
      bascule.textContent = theme === 'sombre' ? 'Thème clair' : 'Thème sombre';
      bascule.setAttribute('aria-pressed', theme === 'sombre' ? 'true' : 'false');
    }
  }
  var memorise = null;
  try { memorise = localStorage.getItem('digitai-theme-dashboard'); } catch (e) {}
  poserTheme(memorise === 'sombre' ? 'sombre' : 'clair');
  if (bascule) {
    bascule.addEventListener('click', function () {
      poserTheme(racine.getAttribute('data-theme') === 'sombre' ? 'clair' : 'sombre');
    });
  }

  // --- Standard H — outillage des tableaux : recherche, réinitialisation, compteur, tri ---
  var norm = function (s) {
    return String(s || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
  };
  // TF-0175 : un « bloc outillé » est soit une table à barre propre (.bloc-tableau), soit un
  // CHAPITRE entier (section[data-outille]) dont la barre gouverne TOUTES les tables.
  function lignesDe(bloc) {
    return Array.prototype.slice.call(bloc.querySelectorAll('table tbody tr'))
      .filter(function (tr) { return !tr.hasAttribute('data-detail'); });
  }
  function detailDe(tr) {
    var d = tr.nextElementSibling;
    return (d && d.hasAttribute('data-detail')) ? d : null;
  }
  function replierDetail(tr) {
    var d = detailDe(tr);
    if (d) { d.hidden = true; }
    var b = tr.querySelector('.btn-detail');
    if (b) {
      b.setAttribute('aria-expanded', 'false');
      b.textContent = b.textContent.replace('▾', '▸');
    }
  }
  function visible(tr) {
    return !tr.hidden && tr.style.display !== 'none' && !tr.hasAttribute('data-rech-cache');
  }
  // Compteurs NOMMÉS (data-tf-count-for) : le rattachement d'une table à son compte, que le
  // composant D-12 lit pour savoir où annoncer les lignes masquées. Ils restent écrits ICI et
  // nulle part ailleurs — le composant ne connaît que SES propres filtres de colonne, si bien
  // que son compte serait faux dès qu'une recherche ou un KPI d'état filtre aussi. Le
  // `.outil-compte` d'un bloc garde son écrivain d'origine (juste en dessous) : l'attribut n'y
  // est qu'un marqueur.
  function majComptesMarques(bloc) {
    bloc.querySelectorAll('[data-tf-count-for]:not(.outil-compte)').forEach(function (cpt) {
      var table = document.getElementById(cpt.getAttribute('data-tf-count-for'));
      if (!table) return;
      var lignes = Array.prototype.slice.call(table.querySelectorAll('tbody tr'))
        .filter(function (tr) { return !tr.hasAttribute('data-detail'); });
      var vues = 0;
      lignes.forEach(function (tr) { if (visible(tr)) vues++; });
      cpt.textContent = vues + ' / ' + lignes.length + ' ligne(s) affichée(s)';
      cpt.classList.toggle('zero', vues === 0);
    });
  }
  function recompter(bloc) {
    majComptesMarques(bloc);
    var compte = bloc.querySelector('.outil-compte');
    if (!compte) return;
    var lignes = lignesDe(bloc), vues = 0;
    lignes.forEach(function (tr) { if (visible(tr)) vues++; });
    var unite = bloc.hasAttribute('data-outille')
      ? 'élément(s) affiché(s)' : 'ligne(s) affichée(s)';
    compte.textContent = vues + ' / ' + lignes.length + ' ' + unite;
  }
  function recompterTout() {
    document.querySelectorAll('.bloc-tableau, section[data-outille]').forEach(recompter);
  }
  // Dépliage du détail de cas (ligne pleine largeur, retour n°6)
  document.querySelectorAll('.btn-detail').forEach(function (b) {
    b.addEventListener('click', function () {
      var tr = b.closest('tr');
      var d = detailDe(tr);
      if (!d) return;
      var ouvert = !d.hidden;
      d.hidden = ouvert;
      b.setAttribute('aria-expanded', ouvert ? 'false' : 'true');
      b.textContent = ouvert ? b.textContent.replace('▾', '▸') : b.textContent.replace('▸', '▾');
    });
  });
  document.querySelectorAll('.bloc-tableau, section[data-outille]').forEach(function (bloc) {
    var recherche = bloc.querySelector('.outil-recherche');
    var reinit = bloc.querySelector('.outil-reinit');
    var lignes = lignesDe(bloc);
    lignes.forEach(function (tr) { tr.dataset.texte = norm(tr.textContent); });
    if (recherche) {
      recherche.addEventListener('input', function () {
        var q = norm(recherche.value.trim());
        lignes.forEach(function (tr) {
          if (q && tr.dataset.texte.indexOf(q) === -1) {
            tr.setAttribute('data-rech-cache', '');
          } else {
            tr.removeAttribute('data-rech-cache');
          }
          majVisibilite(tr);
        });
        recompter(bloc);
      });
    }
    if (reinit) {
      reinit.addEventListener('click', function () {
        if (recherche) recherche.value = '';
        lignes.forEach(function (tr) {
          tr.removeAttribute('data-rech-cache');
          tr.removeAttribute('data-sev-cache');
          tr.removeAttribute('data-axe-cache');
          tr.removeAttribute('data-etat-cache');
          majVisibilite(tr);
        });
        // KPIs d'état du chapitre : relâcher.
        bloc.querySelectorAll('.kpi-etat[aria-pressed="true"]').forEach(function (k) {
          k.setAttribute('aria-pressed', 'false');
        });
        // Filtres de colonne D-12 : recocher tout + événement change (l API n expose pas de reset).
        bloc.querySelectorAll('.tf-opt').forEach(function (cb) {
          if (!cb.checked) {
            cb.checked = true;
            cb.dispatchEvent(new Event('change', { bubbles: true }));
          }
        });
        // Filtres boutons (actions) : relâcher.
        bloc.querySelectorAll('.filtres button[aria-pressed="true"]').forEach(function (b) {
          b.setAttribute('aria-pressed', 'false');
        });
        appliquerFiltresActions();
        recompter(bloc);
      });
    }
    // Recompte après toute interaction interne (filtres D-12 compris).
    bloc.addEventListener('change', function () { recompter(bloc); });
    bloc.addEventListener('click', function (ev) {
      if (ev.target.closest('.tf-panel, .tf-btn, .filtres')) recompter(bloc);
    });
    // Tri par en-tête : clic = croissant, re-clic = décroissant. Numérique quand ça se lit.
    bloc.querySelectorAll('th[data-tri]').forEach(function (th) {
      th.addEventListener('click', function (ev) {
        if (ev.target.closest('.tf-btn, .tf-panel')) return; // le filtre D-12 vit dans le th
        var table = th.closest('table');
        var corps = table.tBodies[0];
        var idx = Array.prototype.indexOf.call(th.parentNode.cells, th);
        var sens = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
        table.querySelectorAll('th').forEach(function (t) {
          t.removeAttribute('aria-sort');
          var m = t.querySelector('.tri-marque'); if (m) m.remove();
        });
        th.setAttribute('aria-sort', sens === 1 ? 'ascending' : 'descending');
        var marque = document.createElement('span');
        marque.className = 'tri-marque';
        marque.textContent = sens === 1 ? ' ↑' : ' ↓';
        th.appendChild(marque);
        var tris = Array.prototype.slice.call(corps.rows);
        tris.sort(function (a, b) {
          var va = a.cells[idx] ? a.cells[idx].textContent.trim() : '';
          var vb = b.cells[idx] ? b.cells[idx].textContent.trim() : '';
          var na = parseFloat(va.replace(',', '.').replace('%', ''));
          var nb = parseFloat(vb.replace(',', '.').replace('%', ''));
          if (!isNaN(na) && !isNaN(nb)) return (na - nb) * sens;
          return norm(va) < norm(vb) ? -sens : (norm(va) > norm(vb) ? sens : 0);
        });
        tris.forEach(function (tr) { corps.appendChild(tr); });
      });
    });
    recompter(bloc);
  });

  // --- H3 : tuiles-KPI cliquables — onglet cible, ancre, filtre optionnel -----------------
  function defiler(id) {
    var cible = document.getElementById(id);
    if (cible) cible.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  document.querySelectorAll('button.tuile').forEach(function (t) {
    t.addEventListener('click', function () {
      if (t.dataset.cible) montrer(t.dataset.cible);
      if (t.dataset.filtreAxe && t.dataset.filtreValeur) {
        // Réutilise les filtres boutons existants (actions) : presser le bon, relâcher les autres.
        document.querySelectorAll('.filtres button[data-axe="' + t.dataset.filtreAxe + '"]')
          .forEach(function (b) {
            b.setAttribute('aria-pressed',
              b.dataset.valeur === t.dataset.filtreValeur ? 'true' : 'false');
          });
        appliquerFiltresActions();
      }
      if (t.dataset.filtreSeverite) {
        var table = document.getElementById('table-echecs');
        if (table) {
          Array.prototype.forEach.call(table.tBodies[0].rows, function (tr) {
            if (tr.dataset.severite === t.dataset.filtreSeverite) {
              tr.removeAttribute('data-sev-cache');
            } else { tr.setAttribute('data-sev-cache', ''); }
            majVisibilite(tr);
          });
          recompterTout();
        }
      }
      if (t.dataset.ancre) setTimeout(function () { defiler(t.dataset.ancre); }, 0);
    });
  });
  document.querySelectorAll('.lien-chapitre').forEach(function (l) {
    l.addEventListener('click', function () {
      if (l.dataset.cible) montrer(l.dataset.cible);
      if (l.dataset.ancre) setTimeout(function () { defiler(l.dataset.ancre); }, 0);
    });
  });

  // --- KPIs d'état par chapitre (retour humain du 14/08) : cliquer filtre les tables du
  //     chapitre sur cet état ; re-cliquer montre tout. Un seul état actif à la fois.
  document.querySelectorAll('.kpi-etat').forEach(function (k) {
    k.addEventListener('click', function () {
      var section = k.closest('section');
      if (!section) return;
      var actif = k.getAttribute('aria-pressed') === 'true';
      section.querySelectorAll('.kpi-etat').forEach(function (a) {
        a.setAttribute('aria-pressed', 'false');
      });
      k.setAttribute('aria-pressed', actif ? 'false' : 'true');
      var etat = actif ? null : k.dataset.etat;
      lignesDe(section).forEach(function (tr) {
        if (etat && tr.dataset.etat !== etat) {
          tr.setAttribute('data-etat-cache', '');
        } else {
          tr.removeAttribute('data-etat-cache');
        }
        majVisibilite(tr);
      });
      recompter(section);
    });
  });

  // --- Ouvrir tout / fermer tout (retour humain du 14/08) : les chapitres de l'ONGLET.
  document.querySelectorAll('.pli-tout').forEach(function (b) {
    b.addEventListener('click', function () {
      var panneau = b.closest('.panneau');
      if (!panneau) return;
      panneau.querySelectorAll('details.pli').forEach(function (d) {
        d.open = b.dataset.sens === 'ouvrir';
      });
    });
  });

  // --- Routeur à ancres (TF-0235) : une ancre qui pointe DANS un panneau masqué ouvre le
  //     panneau avant d y défiler. Sans lui, la moitié des renvois de la page — chemins de
  //     lecteur, repères de KPI, liens du sommaire — seraient des affordances mortes.
  function vueDe(element) {
    var panneau = element && element.closest ? element.closest('.panneau') : null;
    if (panneau) return panneau.id;
    return (element && element.classList && element.classList.contains('panneau'))
      ? element.id : '';
  }
  function ouvrirAncre(id) {
    var cible = document.getElementById(id);
    if (!cible) return false;
    var vue = vueDe(cible);
    if (vue) montrer(vue);
    setTimeout(function () { defiler(id); }, 0);
    return true;
  }
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      var id = a.getAttribute('href').slice(1);
      if (id && ouvrirAncre(id)) ev.preventDefault();
    });
  });
  if (location.hash.length > 1) {
    ouvrirAncre(decodeURIComponent(location.hash.slice(1)));
  }

  // À l impression navigateur, tout détail se déplie : le papier ne cache rien — les
  // chapitres repliés aussi.
  var etatDetails = [];
  window.addEventListener('beforeprint', function () {
    etatDetails = [];
    document.querySelectorAll('details.cas, details.pli').forEach(function (d) {
      etatDetails.push(d.open); d.open = true;
    });
  });
  window.addEventListener('afterprint', function () {
    document.querySelectorAll('details.cas, details.pli').forEach(function (d, i) {
      d.open = etatDetails[i] === true;
    });
  });
})();
"""


def _badge_etat(etat: str) -> str:
    picto, libelle, classe, descriptif = _glossaire.etat(etat)
    return (
        f'<span class="badge etat-badge {classe}" title="{_e(descriptif)}">'
        f"{_e(picto)}&nbsp;{_e(libelle)}</span>"
    )


def _tuile(
    cle: str,
    valeur: int,
    delta: int | None = None,
    part: str = "",
    cible: str = "",
    ancre: str = "",
    filtre_axe: str = "",
    filtre_valeur: str = "",
    filtre_severite: str = "",
    libelle: str = "",
    descriptif: str = "",
    hors_page: str = "",
    repere: str = "",
) -> str:
    """Tuile-KPI. Cliquable (bouton) dès qu une cible existe — H3 : jamais un nombre seul.

    `hors_page` : un KPI dont les éléments ne sont PAS affichés dans la page ne se rend pas
    cliquable ; il dit où ils vivent (c est son descriptif de repli).

    `repere` (TF-0235, règle RL-3) : le REPÈRE DE LECTURE — ce à quoi le chiffre se compare
    pour vouloir dire quelque chose. Une tuile qui en porte un devient un KPI complet au sens
    du référentiel de restitution : valeur (`.k-valeur`), définition (`.kpi-d`), repère
    (`.k-repere`, désigné par `aria-describedby` — le chiffre n est jamais annoncé seul) et
    action (le lien « voir la liste » quand la tuile est cliquable). Le repère est DÉRIVÉ du
    rapport par l appelant : « 12 sur 40 » est un fait, « en progrès » serait un jugement.
    """
    if not libelle or not descriptif:
        libelle_g, descriptif_g = _glossaire.compteur(cle)
        libelle = libelle or libelle_g
        descriptif = descriptif or descriptif_g
    kpi = " kpi" if repere else ""
    ancre_repere = f"repere-{cle}"
    interieur = [
        # `data-total` reste le DERNIER attribut, collé au nombre : c est sous cette forme
        # que le contrôle de fidélité et la recette lisent les totaux affichés depuis TF-0063.
        f'<span class="chiffre{" k-valeur" if repere else ""}"'
        + (f' aria-describedby="{ancre_repere}"' if repere else "")
        + f' data-total="{cle}">{valeur}</span>',
        f'<span class="quoi">{_e(libelle)}</span>',
    ]
    if part:
        interieur.append(f'<span class="part">{_e(part)}</span>')
    if delta is not None and delta != 0:
        favorable = delta > 0 if cle in ("elements", "passes") else delta < 0
        sens = "mieux" if favorable else "pire"
        interieur.append(
            f'<span class="delta {sens}">{delta:+d} vs rapport précédent</span>'
        )
    interieur.append(
        f'<span class="tuile-d{" kpi-d" if repere else ""}">{_e(descriptif)}</span>'
    )
    if repere:
        interieur.append(
            f'<span class="k-repere" id="{ancre_repere}">{_e(repere)}</span>'
        )
    if hors_page:
        interieur.append(f'<span class="tuile-d">{_e(hors_page)}</span>')
        return f'<div class="tuile{kpi}">{"".join(interieur)}</div>'
    if not cible and not ancre:
        return f'<div class="tuile{kpi}">{"".join(interieur)}</div>'
    interieur.append(
        '<span class="tuile-va k-action" aria-hidden="true">→ voir la liste</span>'
    )
    attributs = ""
    if cible:
        attributs += f' data-cible="{_e(cible)}"'
    if ancre:
        attributs += f' data-ancre="{_e(ancre)}"'
    if filtre_axe and filtre_valeur:
        attributs += f' data-filtre-axe="{_e(filtre_axe)}" data-filtre-valeur="{_e(filtre_valeur)}"'
    if filtre_severite:
        attributs += f' data-filtre-severite="{_e(filtre_severite)}"'
    return (
        f'<button type="button" class="tuile{kpi}"{attributs} '
        f'title="{_e(descriptif)} — cliquer : afficher la liste">{"".join(interieur)}</button>'
    )


def _badge_verdict(verdict: str) -> str:
    classe = {"PASS": "b-pass", "FAIL": "b-fail", "PARTIEL": "b-part"}.get(verdict, "b-info")
    sens = {
        "PASS": "tous les seuils opposables sont tenus",
        "FAIL": "au moins un constat bloquant ou un seuil non tenu",
        "PARTIEL": "des pans n ont pas pu être joués dans cet environnement",
    }.get(verdict, "verdict global porté par le rapport JSON")
    return f'<span class="badge {classe}" title="{_e(sens)}">{_e(verdict)}</span>'


# --- Restitution lisible — composants du référentiel (TF-0235, famille « suivi ») --------------
# Tout ce qui suit se NOURRIT du rapport : pas un chiffre, pas une part, pas une tendance qui ne
# soit dérivée de ce que la page affiche déjà par ailleurs. Une donnée absente ne produit pas un
# graphique vide ni une estimation : elle produit un écart, déclaré au manifeste.


def _elements_de(chapitres: list[dict]) -> list[dict]:
    """Tous les éléments inventoriés, à plat — la MÊME dérivation que les tables et les KPI."""
    return [e for c in chapitres for s in c["sous_chapitres"] for e in s["elements"]]


def _verdict_bloc(rapport: dict, contexte: dict, valeurs: dict[str, int],
                  seuils_non_tenus: list[str], nb_seuils: int) -> str:
    """RL-1 — la vue d ensemble CONCLUT. Le verdict est celui du rapport ; la phrase qui le
    justifie est dérivée des mêmes compteurs que les KPI, jamais d une appréciation.
    """
    verdict = str(rapport.get("verdict"))
    elements, passes = valeurs["elements"], valeurs["passes"]
    part = f"{round(100 * passes / elements)} %" if elements else "sans objet"
    if nb_seuils and seuils_non_tenus:
        etat_seuils = (
            f"{len(seuils_non_tenus)} seuil(s) opposable(s) non tenu(s) sur {nb_seuils}"
        )
    elif nb_seuils:
        etat_seuils = f"les {nb_seuils} seuils opposables sont tenus"
    else:
        etat_seuils = "aucun seuil opposable n est déclaré au rapport"
    return (
        f'<div class="verdict" data-verdict="{_e(verdict)}">'
        f"<p><strong>Verdict de la campagne :</strong> {_badge_verdict(verdict)} — "
        f"{etat_seuils}.</p>"
        f'<p class="v-lecture">{passes} élément(s) passés sur {elements} inventoriés '
        f"({part}). {valeurs['echecs']} constat(s) au décompte, dont "
        f"{valeurs['echecs_bloquants']} bloquant(s). {valeurs['non_joues']} élément(s) "
        f"n ont pas pu être joués ici, et {valeurs['actions']} action(s) sont proposées "
        "en suite.</p>"
        f'<p class="v-lecture">Rapport source <code>{_e(contexte["rapport_nom"])}</code> '
        f"(sha256, 16 premiers hex : <code>{_e(contexte['rapport_sha'][:16])}</code>) — "
        "la page rend ce rapport, elle ne le juge pas.</p>"
        "</div>"
    )


def _figure_empilee(question: str, sous_titre: str,
                    segments: list[tuple[str, int, str]]) -> str:
    """RL-4 — barre empilée. `segments` = (libellé, valeur, jeton de couleur du thème).

    Les segments sont JUXTAPOSÉS dans un seul `svg` : aucun rect n en recouvre un autre. La
    piste vide est le fond CSS du `svg`. La légende est en HTML, pas dans le SVG — elle doit
    rester lisible quand la figure est réduite, et se retrouver à la recherche de la page.
    """
    total = sum(max(0, v) for _, v, _ in segments)
    if not total:
        return ""
    portions, depart = [], 0.0
    for libelle, valeur, jeton in segments:
        largeur = 100.0 * max(0, valeur) / total
        portions.append((libelle, valeur, jeton, depart, largeur))
        depart += largeur
    rects = "".join(
        f'<rect x="{x:.2f}" y="0" width="{max(0.0, w):.2f}" height="8" '
        f'fill="var(--{jeton})"></rect>'
        for _, _, jeton, x, w in portions
    )
    aria = ", ".join(f"{libelle} : {valeur}" for libelle, valeur, _, _, _ in portions)
    legende = "".join(
        f'<li><span class="g-puce" style="background:var(--{jeton})" aria-hidden="true">'
        f"</span><strong>{valeur}</strong> {_e(libelle)}</li>"
        for libelle, valeur, jeton, _, _ in portions
    )
    return (
        f'<figure class="graphe"><figcaption>{_e(question)}</figcaption>'
        f'<p class="g-sous">{_e(sous_titre)}</p>'
        f'<svg class="g-empile" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" '
        f'aria-label="{_e(aria)}">{rects}</svg>'
        f'<ul class="g-legende">{legende}</ul></figure>'
    )


def _figure_barres(question: str, sous_titre: str,
                   lignes: list[tuple[str, str, float]]) -> str:
    """RL-4 — barres horizontales. `lignes` = (nom, valeur affichée, part de 0 à 1).

    Un seul `rect` par `svg`, pour la même raison que ci-dessus : la piste est le fond CSS.
    """
    if not lignes:
        return ""
    corps = "".join(
        f'<div class="g-ligne"><span class="g-nom">{_e(nom)}</span>'
        f'<svg class="g-piste" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" '
        f'aria-label="{_e(nom)} : {_e(val)}">'
        f'<rect x="0" y="0" width="{max(0.0, min(100.0, part * 100)):.1f}" height="8" '
        f'rx="1" fill="var(--blue)"></rect></svg>'
        f'<span class="g-val">{_e(val)}</span></div>'
        for nom, val, part in lignes
    )
    return (
        f'<figure class="graphe"><figcaption>{_e(question)}</figcaption>'
        f'<p class="g-sous">{_e(sous_titre)}</p>{corps}</figure>'
    )


def _figure_etats(chapitres: list[dict]) -> str:
    """« Où en sont les éléments inventoriés ? » — la répartition par état MESURÉ.

    Mêmes états, mêmes pictos et mêmes libellés que les badges des tables : la figure et les
    lignes disent la même chose, sinon le lecteur arbitrerait entre deux vérités.
    """
    elements = _elements_de(chapitres)
    if not elements:
        return ""
    comptes: dict[str, int] = {}
    for element in elements:
        comptes[element["etat"]] = comptes.get(element["etat"], 0) + 1
    jetons = {
        "exerce": "green", "defaut": "red", "non_exerce": "amber",
        "non_testable": "teal", "exclu": "faint",
    }
    segments = []
    for etat, jeton in jetons.items():
        n = comptes.get(etat, 0)
        if not n:
            continue
        picto, libelle, _, _ = _glossaire.etat(etat)
        segments.append((f"{picto} {libelle}", n, jeton))
    return _figure_empilee(
        f"Où en sont les {len(elements)} éléments inventoriés ?",
        "Répartition par état mesuré. La somme des segments fait l inventaire entier — "
        "aucun état n est regroupé ni écarté de la figure.",
        segments,
    )


def _figure_pans(chapitres: list[dict]) -> str:
    """« Quels pans tirent le taux de réussite vers le bas ? » — un pan, sa part de passés.

    Ne rend que les pans MESURÉS : un pan sans élément n a pas de taux, et une barre à zéro
    se lirait comme un échec au lieu d une absence de mesure. Les pans non mesurés restent
    intégralement dans la table « Résultats par pan testé », avec leur motif.
    """
    lignes = []
    for chapitre in chapitres:
        elements = [e for s in chapitre["sous_chapitres"] for e in s["elements"]]
        if not elements:
            continue
        passes = sum(1 for e in elements if e["etat"] == "exerce")
        lignes.append(
            (
                f"{chapitre['code']} — {chapitre['titre']}",
                f"{passes}/{len(elements)} ({round(100 * passes / len(elements))} %)",
                passes / len(elements),
            )
        )
    if not lignes:
        return ""
    lignes.sort(key=lambda ligne: ligne[2])
    return _figure_barres(
        "Quels pans tirent le taux de passés vers le bas ?",
        f"{len(lignes)} pan(s) mesuré(s), du moins au mieux servi. Un pan sans élément "
        "inventorié n a pas de taux : il est dit dans la table ci-dessous, avec sa raison.",
        lignes,
    )


def _figure_tendance(rapport: dict, precedent: dict | list[dict] | None) -> str:
    """« Le taux de passés dérive-t-il d un rapport à l autre ? » — un point par rapport.

    Aucune donnée de tendance sans rapport précédent FOURNI : la figure n existe alors pas, et
    l absence est déclarée au manifeste d écarts. Une courbe à un seul point serait une courbe
    inventée.
    """
    if not precedent:
        return ""
    serie = (precedent if isinstance(precedent, list) else [precedent]) + [rapport]
    lignes = []
    for rang, point in enumerate(serie):
        compte = totaux(point)
        elements, passes = compte["elements"], compte["passes"]
        if not elements:
            continue
        nom = "ce rapport" if rang == len(serie) - 1 else f"R-{len(serie) - 1 - rang}"
        lignes.append(
            (nom, f"{passes}/{elements} ({round(100 * passes / elements)} %)",
             passes / elements)
        )
    if len(lignes) < 2:
        return ""
    return _figure_barres(
        "Le taux de passés dérive-t-il d un rapport à l autre ?",
        "Un point par rapport fourni, du plus ancien au plus récent. Chaque point compare "
        "des TOTAUX : il ne dit pas si ce sont les mêmes éléments qui ont bougé.",
        lignes,
    )


def _chemins() -> str:
    """RL-9 — « vous êtes X, commencez ici », pour les deux lecteurs de la famille « suivi ».

    Chaque chemin est un BOUTON câblé vers sa vue (loi transverse n° 1 : une affordance sans
    effet observable est un défaut) — pas une phrase qui décrit un parcours que le lecteur
    devrait refaire à la main.
    """
    def va(libelle: str, cible: str, ancre: str = "") -> str:
        # Le bouton porte une phrase ENTIÈRE : un lien posé au milieu d une phrase coupe le
        # texte en deux blocs, et la seconde moitié s ouvre sur une ponctuation orpheline
        # (règle L1 du socle, constatée sur ce même bloc à la génération).
        return (
            f'<button type="button" class="lien-chapitre c-va" data-cible="{_e(cible)}"'
            + (f' data-ancre="{_e(ancre)}"' if ancre else "")
            + f">→ {_e(libelle)}</button>"
        )

    entrees = [
        (
            "Vous pilotez",
            "Est-ce que ça dérive ? où, depuis quand, de combien ?",
            "Restez sur cette vue : le verdict conclut, et chaque indicateur porte le repère "
            "auquel il se compare.",
            [
                va("Voir la tendance, compteur par compteur", "synthese", "tendance"),
                va("Voir les résultats par pan testé", "synthese", "table-par-pan"),
            ],
        ),
        (
            "Vous opérez",
            "Qu y a-t-il dans la file, que traiter d abord ?",
            "La file est déjà ordonnée : la configuration d abord, parce qu elle débloque la "
            "mesure, puis les arbitrages par risque décroissant.",
            [
                va("Voir les suites à donner, quoi et pourquoi", "actions",
                   "synthese-actions"),
                va("Voir les constats par risque décroissant", "echecs", "table-echecs"),
            ],
        ),
    ]
    return (
        "<h3>Par où commencer, selon qui vous êtes</h3>"
        '<ul class="chemins">'
        + "".join(
            f'<li class="chemin"><b>{_e(qui)}</b>'
            f'<span class="c-question">{_e(question)}</span>'
            f"<span>{_e(conduite)}</span>{''.join(liens)}</li>"
            for qui, question, conduite, liens in entrees
        )
        + "</ul>"
    )


def _ecarts_declares(rapport: dict, valeurs: dict[str, int], chapitres: list[dict],
                     precedent: dict | list[dict] | None, nb_seuils: int) -> list[str]:
    """Les écarts RÉELS de CETTE page, calculés sur l état du rapport — jamais une liste figée.

    Un écart n est pas un aveu de faiblesse du gabarit : c est le refus d afficher une figure
    ou un repère que la donnée ne porte pas. La liste vide veut dire « aucun écart », et se
    déclare comme telle.
    """
    ecarts: list[str] = []
    if not precedent:
        ecarts.append(
            "Aucun rapport précédent n a été fourni (option --precedent) : la dérive n est "
            "pas mesurable sur ce run. La page n affiche donc ni graphique ni écart de "
            "tendance — la question « depuis quand ? » du pilote reste sans réponse ici, "
            "faute de donnée, jamais par choix de mise en page."
        )
    if not nb_seuils:
        ecarts.append(
            "Aucun seuil opposable n est déclaré au rapport : les indicateurs se situent par "
            "rapport à l inventaire, pas par rapport à un engagement chiffré. Le repère de "
            "lecture des chiffres en est d autant plus faible."
        )
    if not _elements_de(chapitres):
        ecarts.append(
            "Aucun élément inventorié : la figure de répartition par état et celle des pans "
            "n existent pas sur ce rapport. Les chapitres restent affichés avec leur motif "
            "de non-mesure."
        )
    if not (rapport.get("findings") or []):
        ecarts.append(
            "Aucun constat mesuré sur ce rapport : la vue « Échecs » est vide de lignes. "
            "Elle reste ouverte — une vue retirée laisserait croire que la question n a pas "
            "été posée."
        )
    if not valeurs["actions"]:
        ecarts.append(
            "Aucune action proposée par le rapport : la file de travail de l opérateur est "
            "vide sur ce run. Le chemin de lecture « vous opérez » mène donc à une vue sans "
            "entrée, et le dit."
        )
    return ecarts


def _manifeste_ecarts(ecarts: list[str]) -> str:
    """RL-10 — le manifeste. « Aucun écart » se déclare aussi ; l absence, elle, se tairait.

    Deux registres, tous deux dus au lecteur : ce que la page N A PAS PU faire sur CE rapport
    (écarts calculés), et ce qu elle ne juge JAMAIS par construction (`NON_JUGE`, jusqu ici
    visible du seul registre de dette de la forge — donc de personne, côté lecteur).
    """
    items = ecarts or [
        "Aucun écart déclaré : sur les données de ce rapport, la vue d ensemble conclut, "
        "les indicateurs portent leur repère, les figures ont leur donnée et les vues sont "
        "toutes accessibles."
    ]
    return (
        '<footer class="ecarts">'
        "<h2>Ce que cette page ne fait pas — manifeste d écarts</h2>"
        "<h3>Sur ce rapport</h3><ul>"
        + "".join(f"<li>{_e(x)}</li>" for x in items)
        + "</ul><h3>Par construction, quel que soit le rapport</h3><ul>"
        + "".join(f"<li>{_e(x)}</li>" for x in NON_JUGE)
        + "</ul></footer>"
    )


# L3 du socle : un en-tête qui annonce une valeur classante (« sévérité ») renvoie à son
# barème par aria-describedby — la note existe une fois dans la page (voir construire()).
_DESCRIBEDBY = {"sévérité": "note-severite", "risque": "note-risque"}

# L4 du socle : au-delà de ce nombre de lignes, une table sans filtre ne se parcourt plus —
# le composant maison (data-filterable) est inliné une fois par page (D-12, provenance).
# Le standard H y ajoute recherche, tri et réinitialisation, au même seuil.
_SEUIL_FILTRE = 8


def _tableau(
    entetes: list[str],
    lignes: list[list[str]],
    attributs: list[str] | None = None,
    identifiant: str = "",
    chapitre: bool = False,
    details_lignes: list[str] | None = None,
    outille_force: bool = False,
) -> str:
    """Tableau accessible. Chaque cellule porte son intitulé de colonne (`data-label`).

    Sans ce report, le repli mobile — où l en-tête disparaît — produirait des colonnes de
    valeurs sans nom : lisible sur grand écran, indéchiffrable sur téléphone.

    Les en-têtes passent par le glossaire : libellé parlant affiché + tooltip (title), les
    identifiants de colonnes restant ceux du rapport. Dès `_SEUIL_FILTRE` lignes, le tableau
    est OUTILLÉ (standard H) : recherche insensible aux accents, réinitialisation, compteur
    `aria-live`, tri par en-tête — en plus des filtres de colonne D-12 (`data-filterable`).
    """
    if not lignes:
        return '<p class="discret">Aucune entrée.</p>'
    # Mode CHAPITRE (TF-0175, retour humain n°4) : l'outillage (recherche/réinit/compteur)
    # vit au niveau du CHAPITRE — le sous-chapitrage fragmentait les listes sous le seuil et
    # vidait « pour chaque liste, des filtres » (76 tables sur 79 nues au constat). Ici :
    # tri sur TOUTES les tables, filtres de colonne dès 4 lignes, jamais de barre par table.
    # `outille_force` (retour humain du 14/08, onglet Non joués) : certaines tables doivent
    # leurs outils quel que soit leur volume — le lecteur y CHERCHE un pan ou un champ précis.
    outille = (len(lignes) >= _SEUIL_FILTRE or outille_force) and not chapitre
    tete = ""
    affiches = []
    for t in entetes:
        affiche, info = _glossaire.entete(t)
        affiches.append(affiche)
        attribut = f' aria-describedby="{_DESCRIBEDBY[t]}"' if t in _DESCRIBEDBY else ""
        attribut += f' title="{_e(info)}"' if info else ""
        attribut += ' data-tri=""' if (outille or chapitre) else ""
        tete += f"<th{attribut}>{_e(affiche)}</th>"
    corps = ""
    for rang, ligne in enumerate(lignes):
        ouverture = f"<tr{(attributs or [''] * len(lignes))[rang]}>"
        cellules = "".join(
            f'<td data-label="{_e(affiches[i]) if i < len(affiches) else ""}">{c}</td>'
            for i, c in enumerate(ligne)
        )
        corps += ouverture + cellules + "</tr>"
        # Ligne de détail PLEINE LARGEUR (retour humain n°6) : le détail d'un cas ne vit
        # plus dans une cellule étroite — il se déplie sous la ligne, sur toute la largeur.
        detail = (details_lignes or [])[rang] if details_lignes else ""
        if detail:
            corps += (
                f'<tr data-detail hidden><td colspan="{len(entetes)}" '
                f'data-label="détail">{detail}</td></tr>'
            )
    filtre = outille or (chapitre and len(lignes) >= 4)
    # G4/G5 du composant D-12 : une table filtrable SANS id ne peut être ni initialisée ni
    # reliée à son compteur. L identifiant explicite prime ; à défaut il se DÉRIVE du contenu,
    # donc il est stable d un audit à l autre — un id tiré au hasard aurait fait diverger deux
    # rendus du même rapport, et le déterminisme des livrables est vérifié en recette.
    if filtre and not identifiant:
        graine = " ".join([*entetes, *(c for ligne in lignes for c in ligne)])
        identifiant = "table-" + hashlib.sha256(graine.encode("utf-8")).hexdigest()[:10]
    marque = f' id="{identifiant}"' if identifiant else ""
    filtrable = " data-filterable" if filtre else ""
    table = (
        f'<div class="zone-tableau"><table{marque}{filtrable}><thead><tr>{tete}</tr></thead>'
        f"<tbody>{corps}</tbody></table></div>"
    )
    if not outille:
        # Mode CHAPITRE : la barre d outils (recherche, réinitialisation, compteur) vit au
        # niveau du chapitre et son compteur AGRÈGE toutes les tables (TF-0175). Un agrégat ne
        # dit pas laquelle des sous-listes un filtre vient de vider : chaque table filtrable
        # porte donc son propre compte, discret, et c est lui que le composant D-12 nomme
        # (`data-tf-count-for`). Il reste écrit par le script maison — voir `majComptesMarques`.
        if filtre:
            table += (
                f'<p class="compte-table" data-tf-count-for="{identifiant}" aria-live="polite">'
                f"{len(lignes)} / {len(lignes)} ligne(s) affichée(s)</p>"
            )
        return table
    outillage = (
        '<div class="outillage" role="search">'
        '<input type="search" class="outil-recherche" placeholder="Rechercher…" '
        'aria-label="Rechercher dans ce tableau (insensible aux accents)">'
        '<button type="button" class="outil-reinit">Réinitialiser les filtres</button>'
        # Le compteur EXISTANT devient le compteur nommé de sa table : un bloc outillé ne porte
        # qu une table, l agrégat et le compte par table y sont le même nombre. L attribut est
        # un MARQUEUR de rattachement — l écriture reste celle de `recompter`.
        f'<span class="outil-compte" data-tf-count-for="{identifiant}" aria-live="polite">'
        f"{len(lignes)} / {len(lignes)} ligne(s) affichée(s)</span></div>"
    )
    return f'<div class="bloc-tableau">{outillage}{table}</div>'


# --- Synthèse par pan (R2) ----------------------------------------------------------------------
def _synthese_par_pan(chapitres: list[dict], identifiant: str = "table-par-pan") -> str:
    """Un bloc par chapitre (pan) : x/y passés, %, et une phrase de lecture — dérivés des
    éléments que la page rend déjà dans les onglets. Un pan non mesuré le DIT, avec sa raison.

    `identifiant` : la même table sert la Synthèse ET l'en-tête de chaque onglet de famille
    (retour humain du 14/08) — deux rendus, deux ids, jamais deux dérivations.
    """
    lignes = []
    for chapitre in chapitres:
        elements = [e for s in chapitre["sous_chapitres"] for e in s["elements"]]
        total = len(elements)
        cible = "fonctionnels" if chapitre["famille"] == "fonctionnel" else "techniques"
        lien = (
            f'<button type="button" class="lien-chapitre" data-cible="{cible}" '
            f'data-ancre="chap-{_e(chapitre["code"])}">'
            f"{_e(chapitre['code'])} — {_e(chapitre['titre'])}</button>"
        )
        if total == 0:
            motifs = [
                f"{_e(m.get('pan'))} : {_e(m.get('motif'))}"
                for m in (chapitre.get("pans_non_couverts") or [])
            ]
            lecture = (
                "non testé — " + " · ".join(motifs)
                if motifs
                else "non testé — aucun élément inventorié pour ce chapitre"
            )
            lignes.append(
                [
                    lien,
                    _e(chapitre["famille"]),
                    "0", "—", "—", "—", "—",
                    '<span class="badge b-part" title="aucun élément inventorié : rien n a pu '
                    'être mesuré sur ce pan — la lecture donne le motif">non testé</span>',
                    f'<span class="discret">{lecture}</span>',
                ]
            )
            continue
        passes = sum(1 for e in elements if e["etat"] == "exerce")
        ko = sum(1 for e in elements if e["etat"] == "defaut")
        bloquants = sum(
            1 for e in elements if e["etat"] == "defaut" and e.get("severite") == "bloquant"
        )
        # Retour humain n°3 : les NON-PASSÉS ont leurs colonnes explicites — la vue est
        # complète sans lire la prose.
        non_joues = sum(1 for e in elements if e["etat"] == "non_exerce")
        non_testables = sum(1 for e in elements if e["etat"] == "non_testable")
        pct = round(100 * passes / total)
        badge = (
            "b-pass" if ko == 0 and non_joues == 0 and non_testables == 0
            else ("b-fail" if bloquants else "b-part")
        )
        # Retour humain n°2 : la lecture apporte un FAIT ABSENT des autres colonnes (H4) —
        # le constat au plus fort risque, nommé ; ou l'angle mort le plus parlant ; jamais
        # une redite des compteurs.
        # Le libellé cité porte SON garde L11 au plus près (data-litteral-ok sur le span du
        # libellé, pas sur la phrase) : il peut citer le vocabulaire du domaine (« NOT NULL »).
        def _cite(brut: str) -> str:
            return f'<span data-litteral-ok>« {_e(brut)} »</span>'

        en_defaut = [e for e in elements if e["etat"] == "defaut" and e.get("risque") is not None]
        if en_defaut:
            pire = max(en_defaut, key=lambda e: e["risque"])
            lib = _libelle_element(pire["id"]) or pire["id"]
            lecture = (
                f"plus fort risque : {_e(pire.get('classe') or 'constat')} — "
                f"{_cite(lib)} (risque {pire['risque']})"
            )
        elif ko:
            pire = next(e for e in elements if e["etat"] == "defaut")
            lib = _libelle_element(pire["id"]) or pire["id"]
            lecture = (
                f"constat sans score : {_e(pire.get('classe') or 'défaut')} — {_cite(lib)}"
            )
        elif non_joues or non_testables:
            angle_mort = next(
                e for e in elements if e["etat"] in ("non_exerce", "non_testable")
            )
            lib = _libelle_element(angle_mort["id"]) or angle_mort["id"]
            lecture = (
                f"aucun échec mesuré ; l'angle mort demeure — ex. {_cite(lib)} "
                + ("jamais exercé" if angle_mort["etat"] == "non_exerce" else "non testable ici")
            )
        else:
            lecture = "pan sain — tous les éléments exercés, aucun constat"
        lignes.append(
            [
                lien,
                _e(chapitre["famille"]),
                str(total),
                f"{passes} ({pct} %)",
                str(ko)
                + (f' <span class="discret">dont {bloquants} bloq.</span>' if bloquants else ""),
                str(non_joues) if non_joues else "0",
                str(non_testables) if non_testables else "0",
                f'<span class="badge {badge}" title="passés = éléments exercés sans constat, '
                f'rapportés aux {total} éléments du chapitre">{_e(f"{pct} % passés")}</span>',
                # la lecture est déjà de l'HTML sûr : parties échappées, libellés gardés
                f'<span class="discret">{lecture}</span>',
            ]
        )
    return _tableau(
        ["chapitre (pan)", "famille", "éléments", "passés", "KO", "non joués",
         "non testables", "résultat", "lecture"],
        lignes,
        identifiant=identifiant,
    )


def _etat_des_seuils(rapport: dict) -> tuple[list[list[str]], list[str], int]:
    """Seuil par seuil : valeur, sévérité, et état DÉRIVÉ des findings qui citent sa valeur.

    Renvoie (lignes, libellés des seuils non tenus, nombre de seuils) pour que la synthèse
    au-dessus du tableau soit dérivée des mêmes données que le tableau.
    """
    constats = [
        f for f in (rapport.get("findings") or []) if f.get("classe") == "seuil-non-tenu"
    ]
    lignes, non_tenus, total = [], [], 0
    for nom, detail in sorted((rapport.get("seuils") or {}).items()):
        total += 1
        valeur = float(detail.get("valeur") or 0)
        libelle = _glossaire.seuil(nom)
        cite = [f for f in constats if f"seuil {valeur:.0%}" in str(f.get("message") or "")]
        if cite:
            etat = (
                f'<span class="badge b-fail" title="{len(cite)} finding(s) seuil-non-tenu '
                f'citent la valeur de ce seuil">✕ non tenu — {len(cite)} constat(s)</span>'
            )
            non_tenus.append(libelle)
        else:
            etat = (
                '<span class="badge b-pass" title="aucun finding seuil-non-tenu ne cite '
                "la valeur de ce seuil — au rapprochement près, le seuil est tenu\">"
                "✓ tenu (aucun constat contraire)</span>"
            )
        lignes.append(
            [
                f"{_e(libelle)}<br><code class=\"discret\">{_e(nom)}</code>",
                f"{valeur:.0%}",
                _e(detail.get("severite")),
                etat,
                f'<span class="discret">{_e(detail.get("porte_sur"))}</span>',
            ]
        )
    return lignes, non_tenus, total


def _tendance(rapport: dict, precedent: dict | list[dict] | None) -> str:
    if not precedent:
        return (
            '<p class="discret">Aucun rapport précédent fourni — pas de tendance. '
            "Passer <code>--precedent &lt;rapport.json&gt;</code> pour l obtenir "
            "(répétable : plusieurs rapports, du plus ancien au plus récent, donnent "
            "l historique multi-runs — TF-0159).</p>"
        )
    precedents = precedent if isinstance(precedent, list) else [precedent]
    if len(precedents) > 1:
        return _tendance_multi(rapport, precedents)
    avant, apres = totaux(precedents[0]), totaux(rapport)
    cibles = {
        "elements": ("synthese", "table-par-pan", ""),
        "passes": ("synthese", "table-par-pan", ""),
        "echecs": ("echecs", "table-echecs", ""),
        "echecs_bloquants": ("echecs", "table-echecs", "bloquant"),
        "non_joues": ("non-joues", "", ""),
        "actions": ("actions", "table-actions", ""),
    }
    lignes = []
    for cle in ("elements", "passes", "echecs", "echecs_bloquants", "non_joues", "actions"):
        ecart = apres[cle] - avant[cle]
        # Un écart n est « bon » ou « mauvais » que selon ce qu il compte : plus d éléments
        # exercés est un progrès, plus d échecs ne l est pas. Le sens est déclaré, pas deviné.
        favorable = ecart > 0 if cle in ("elements", "passes") else ecart < 0
        classe = "b-info" if ecart == 0 else ("b-pass" if favorable else "b-fail")
        signe = f"{ecart:+d}" if ecart else "="
        pct = f" ({ecart / avant[cle]:+.0%})" if ecart and avant[cle] else ""
        libelle, descriptif = _glossaire.compteur(cle)
        sens = (
            "écart nul entre les deux rapports"
            if ecart == 0
            else f"{'amélioration' if favorable else 'dégradation'} : "
            f"{avant[cle]} → {apres[cle]} — le sens est déclaré par ce que le compteur "
            "compte, pas deviné"
        )
        cible, ancre, severite = cibles[cle]
        voir = (
            f'<button type="button" class="lien-chapitre tuile-lien" data-cible="{cible}"'
            + (f' data-ancre="{ancre}"' if ancre else "")
            + (f' data-filtre-severite="{severite}"' if severite else "")
            + ">voir</button>"
        )
        lignes.append(
            [
                f"{_e(libelle)}<br><span class=\"discret\">{_e(descriptif)}</span>",
                str(avant[cle]),
                str(apres[cle]),
                f'<span class="badge {classe}" title="{_e(sens)}">{signe}{_e(pct)}</span>',
                voir,
            ]
        )
    note = (
        '<p class="discret">Tendance limitée au rapport précédent fourni '
        "(<code>--precedent</code>) — deux points, pas un historique. Chaque écart compare "
        "les TOTAUX : il ne dit pas si ce sont les mêmes éléments qui ont bougé.</p>"
    )
    return (
        _tableau(
            ["compteur", "rapport précédent", "ce rapport", "écart", "aller voir"], lignes
        )
        + note
    )


def _tendance_multi(rapport: dict, precedents: list[dict]) -> str:
    """TF-0159 (barre Allure B3) : tendance MULTI-RUNS — une colonne par rapport fourni
    (du plus ancien au plus récent), l écart jugé entre les deux derniers points. Chaque
    ligne garde son « aller voir » : l agrégat mène à sa liste (B4).
    """
    series = [totaux(p) for p in precedents] + [totaux(rapport)]
    entetes = (
        ["compteur"]
        + [f"R-{len(precedents) - i}" for i in range(len(precedents))]
        + ["ce rapport", "écart (dernier pas)", "aller voir"]
    )
    cibles = {
        "elements": ("synthese", "table-par-pan", ""),
        "passes": ("synthese", "table-par-pan", ""),
        "echecs": ("echecs", "table-echecs", ""),
        "echecs_bloquants": ("echecs", "table-echecs", "bloquant"),
        "non_joues": ("non-joues", "", ""),
        "actions": ("actions", "table-actions", ""),
    }
    lignes = []
    for cle in ("elements", "passes", "echecs", "echecs_bloquants", "non_joues", "actions"):
        valeurs_serie = [s[cle] for s in series]
        ecart = valeurs_serie[-1] - valeurs_serie[-2]
        favorable = ecart > 0 if cle in ("elements", "passes") else ecart < 0
        classe = "b-info" if ecart == 0 else ("b-pass" if favorable else "b-fail")
        signe = f"{ecart:+d}" if ecart else "="
        libelle, descriptif = _glossaire.compteur(cle)
        sens = (
            "écart nul entre les deux derniers rapports"
            if ecart == 0
            else f"{'amélioration' if favorable else 'dégradation'} sur le dernier pas : "
            f"{valeurs_serie[-2]} → {valeurs_serie[-1]}"
        )
        cible, ancre, severite = cibles[cle]
        voir = (
            f'<button type="button" class="lien-chapitre" data-cible="{cible}"'
            + (f' data-ancre="{ancre}"' if ancre else "")
            + (f' data-filtre-severite="{severite}"' if severite else "")
            + ">voir</button>"
        )
        lignes.append(
            [f"{_e(libelle)}<br><span class=\"discret\">{_e(descriptif)}</span>"]
            + [str(v) for v in valeurs_serie]
            + [f'<span class="badge {classe}" title="{_e(sens)}">{signe}</span>', voir]
        )
    note = (
        f'<p class="discret">Historique : {len(precedents)} rapport(s) antérieur(s) fournis '
        "(<code>--precedent</code> répétable, du plus ancien au plus récent). Chaque colonne "
        "compare des TOTAUX : elle ne dit pas si ce sont les mêmes éléments qui ont bougé.</p>"
    )
    return _tableau(entetes, lignes) + note


# --- Détail d un cas (R11 — barre B1 : le détail à ≤ 2 clics, déplié sur place) -----------------
def _rendre_exigences_liens(liens: list[dict] | None) -> str:
    if not liens:
        return "aucune exigence rattachée (ni clé technique, ni rapprochement lexical)"
    return " · ".join(
        f"<code>{_e(lien.get('id'))}</code> ({_e(lien.get('provenance') or 'déclaré')})"
        for lien in liens
        if isinstance(lien, dict)
    )


def _detail_element(detail: dict | None) -> tuple[str, str]:
    """(bouton de dépliage, contenu pleine largeur) — TF-0175, retour humain n°6 : le détail
    ne vit plus dans une cellule étroite. Le bouton annonce le volume (« 4 cas ▸ ») ; le
    contenu se déplie sous la ligne, cas côte à côte en cartes lisibles.
    """
    if not detail:
        return '<span class="discret">—</span>', ""
    if detail.get("raison"):
        contenu = (
            '<div class="cas-grille"><div class="cas-carte">'
            f"<p><strong>Non couvert</strong> — {_e(detail['raison'])}</p>"
            f"<p><strong>Exigences</strong> — {_rendre_exigences_liens(detail.get('exigences'))}"
            "</p></div></div>"
        )
        return (
            '<button type="button" class="btn-detail" aria-expanded="false">raison ▸</button>',
            contenu,
        )
    cartes = []
    adoptes = 0
    for cas in detail.get("cas") or []:
        etapes = "".join(f"<li>{_e(geste)}</li>" for geste in (cas.get("etapes") or []))
        adoption = cas.get("adoption") or {"statut": "proposition"}
        adoptes += adoption.get("statut") == "adopte"
        cartes.append(
            '<div class="cas-carte">'
            f'<p class="cas-ref"><code>{_e(cas.get("ref"))}</code> · '
            f'{_e(cas.get("titre") or "")}</p>'
            + _badge_adoption(adoption)
            + f"<p><strong>Préconditions</strong> — {_e(cas.get('preconditions'))}</p>"
            f"<p><strong>Jeu de données</strong> — <code>{_e(cas.get('jeu'))}</code></p>"
            f"<ol>{etapes}</ol>"
            f"<p><strong>Résultat attendu</strong> — {_texte_libre(cas.get('attendu'))}</p>"
            f"<p><strong>Exigences</strong> — {_rendre_exigences_liens(cas.get('exigences'))}</p>"
            "</div>"
        )
    if not cartes:
        return '<span class="discret">—</span>', ""
    n = len(cartes)
    # RT-12 : le bouton ne dit plus « 4 cas » (que le lecteur lisait comme « 4 tests non
    # joués ») mais ce que ces cas SONT — des propositions, dont x adoptées par le projet.
    libelle = f"{n} cas proposé{'s' if n > 1 else ''}"
    if adoptes:
        libelle += f", {adoptes} adopté{'s' if adoptes > 1 else ''}"
    bouton = (
        f'<button type="button" class="btn-detail" aria-expanded="false" '
        f'title="cas DÉRIVÉS de la surface, déposés hors du projet (G-1) : des propositions '
        f'à adopter, pas des tests que l audit aurait sautés">{_e(libelle)} ▸</button>'
    )
    return bouton, f'<div class="cas-grille">{"".join(cartes)}</div>'


def _badge_adoption(adoption: dict) -> str:
    """Statut d'un cas dérivé (RT-13) — « Proposition » n'est pas « Non joué ».

    Retour humain du 14/08 : le lecteur a lu « Non joué » sur un cas dérivé et a demandé
    « pourquoi ce type de tests n'est pas joué ? ». Un cas dérivé n'est pas joué par
    construction — il n'appartient pas encore à la suite du projet.
    """
    statut = adoption.get("statut")
    if statut == "adopte":
        return (
            '<p><span class="badge b-pass" title="le projet a déclaré ce cas adopté et le '
            'test cité existe">✓ Adopté par le projet</span> '
            f'<code>{_e(adoption.get("test"))}</code></p>'
        )
    if statut == "refuse":
        return (
            '<p><span class="badge b-fail" title="adoption déclarée mais non vérifiable">'
            f'✕ Adoption refusée</span> <span class="discret">{_e(adoption.get("motif"))}'
            "</span></p>"
        )
    return (
        '<p><span class="badge b-part" title="cas dérivé de la surface : il n appartient pas '
        "encore à la suite du projet — ce n est pas un test que l audit aurait sauté\">"
        "○ Proposition (non adoptée)</span></p>"
    )


def _badge_declaration(declaration: dict | None) -> str:
    """État d un constat DÉCLARÉ par le projet (RT-18) — jamais un masquage, un état de plus.

    Trois rendus, tous visibles : la déclaration retenue (le constat sort du décompte, sa
    contre-preuve est citée en regard, avec qui l a signée et quand), la déclaration REFUSÉE
    (le constat reste au décompte, et le motif du refus est dit — sans quoi le mécanisme
    deviendrait un bouton « faire taire ») et la déclaration PÉRIMÉE.
    """
    if not declaration:
        return ""
    statut = declaration.get("statut")
    signature = (
        f'<span class="discret"> — déclaré par {_e(declaration.get("par"))} le '
        f'{_e(declaration.get("date"))}'
        + (f", terme {_e(declaration.get('expire_le'))}" if declaration.get("expire_le") else "")
        + "</span>"
    )
    if statut == _declarations.RETENUE:
        libelle = _e(declaration.get("libelle_motif") or declaration.get("motif"))
        explication = (
            f'<span class="discret"> {_e(declaration.get("explication"))}</span>'
            if declaration.get("explication")
            else ""
        )
        return (
            '<p><span class="badge b-info" title="le projet a DÉCLARÉ ce constat et la preuve '
            'citée existe : il reste mesuré et affiché, hors du décompte principal">'
            f"⚖ Déclaré par le projet — {libelle}</span> "
            f'contre-preuve <code>{_e(declaration.get("preuve"))}</code>'
            f"{signature}{explication}</p>"
        )
    if statut == _declarations.PERIMEE:
        return (
            '<p><span class="badge b-part" title="déclaration expirée : le constat revient au '
            'décompte principal tant qu elle n est pas renouvelée">⏳ Déclaration périmée</span> '
            f'<span class="discret">{_e(declaration.get("motif_du_refus"))}</span>{signature}</p>'
        )
    return (
        '<p><span class="badge b-fail" title="déclaration non vérifiable : le constat reste au '
        'décompte principal">✕ Déclaration refusée</span> '
        f'<span class="discret">{_e(declaration.get("motif_du_refus"))}</span>{signature}</p>'
    )


def _constat_cellule(element: dict) -> str:
    """La colonne « constat mesuré — pourquoi » ne se tait JAMAIS (retour humain du 13/08 :
    une cellule vide est indistinguable d un bug d affichage), et pour un élément NON JOUÉ
    elle explique POURQUOI il ne l a pas été (retour humain du 14/08) — la raison est dérivée
    de l état et des champs du rapport, jamais inventée.
    """
    message = element.get("message")
    etat = element.get("etat")
    if etat == "non_testable":
        champs = ", ".join(element.get("champs_requis") or [])
        motif = _e(message) if message else "la configuration requise est absente"
        return (
            f'<span data-litteral-ok><strong>Pourquoi non testable ici :</strong> {motif}'
            + (
                f" — fournir (noms seuls, jamais les valeurs) : <code>{_e(champs)}</code>"
                if champs
                else ""
            )
            + ", puis <code>--reprendre</code> le rapport</span>"
        ) + _contexte_porteur(element)
    if etat == "non_exerce":
        constat = f"{_e(message)} — " if message else ""
        return (
            f"<span data-litteral-ok>{constat}<strong>Pourquoi non exercé :</strong> aucun test "
            "de la suite du projet n atteint cet élément — l audit mesure la suite existante, "
            "il ne joue pas de cas à sa place (garde-fou G-1) ; le cas à ajouter est dépliable "
            "dans la colonne « détail »</span>"
        ) + _contexte_porteur(element)
    if message:
        return _texte_libre(message) + _contexte_porteur(element)
    if etat == "exerce":
        return '<span class="discret">✓ Passé — aucun constat</span>'
    return '<span class="discret">sans objet</span>'


def _contexte_porteur(element: dict) -> str:
    """RT-12 : le constat de la ROUTE qui porte l'élément, quand il existe et qu'il diffère.

    Sans lui, la cellule affichait « formulaire sans action ni écouteur » sans le `401` de
    l'écran qui l'explique — celui-ci vivant deux sous-chapitres plus loin.
    """
    porteur = element.get("porteur")
    if not porteur or not porteur.get("message"):
        return ""
    return (
        f'<br><span class="porteur" data-litteral-ok><strong>Contexte de l\'écran '
        f'{_e(porteur.get("route"))}</strong> ({_e(porteur.get("classe") or "constat")}) : '
        f'{_e(porteur.get("message"))}</span>'
    )


def _kpis_chapitre(chapitre: dict) -> str:
    """KPIs cliquables du CHAPITRE (retour humain du 14/08) : un compteur par état mesuré,
    qui FILTRE les tables du chapitre au clic. Dérivés des mêmes éléments que les tables —
    jamais deux vérités. Un état absent du chapitre n affiche pas de bouton mort."""
    elements = [e for s in chapitre["sous_chapitres"] for e in s["elements"]]
    if not elements:
        return ""
    comptes: dict[str, int] = {}
    for element in elements:
        comptes[element["etat"]] = comptes.get(element["etat"], 0) + 1
    boutons = []
    for etat in ("exerce", "defaut", "non_exerce", "non_testable", "exclu"):
        n = comptes.get(etat, 0)
        if not n:
            continue
        picto, libelle, classe, descriptif = _glossaire.etat(etat)
        boutons.append(
            f'<button type="button" class="kpi-etat {classe}" data-etat="{_e(etat)}" '
            f'aria-pressed="false" title="{_e(descriptif)} — cliquer : ne montrer que ces '
            f'éléments dans ce chapitre (re-cliquer : tout montrer)">'
            f"{_e(picto)} {_e(libelle)} · {n}</button>"
        )
    return f'<div class="kpis-chapitre">{"".join(boutons)}</div>'


def _panneau_chapitres(
    chapitres: list[dict],
    famille: str,
    details: dict[tuple[str, str], dict] | None = None,
    declarations: dict[tuple[str, str], dict] | None = None,
) -> str:
    """`declarations` (RT-18) : (pan, id élément) -> déclaration du projet portée par le
    finding. L état de l élément reste celui que le rapport mesure ; la déclaration s affiche
    EN REGARD du constat, elle ne le remplace pas."""
    details = details or {}
    declarations = declarations or {}
    retenus = [c for c in chapitres if c["famille"] == famille]
    # Retour humain du 14/08 : l'onglet ouvre sur SA synthèse (mêmes colonnes que l'onglet
    # Synthèse, restreinte à la famille) + les commandes de repli global des chapitres.
    morceaux: list[str] = [
        '<section class="card">',
        f"<h3>Synthèse des chapitres "
        f"{('fonctionnels' if famille == 'fonctionnel' else 'techniques')}</h3>",
        '<p class="discret">La même dérivation que l\'onglet Synthèse, restreinte à cette '
        "famille — le lien ouvre le chapitre détaillé ci-dessous.</p>",
        _synthese_par_pan(retenus, identifiant=f"table-par-pan-{famille}"),
        '<div class="outillage pli-commandes">'
        '<button type="button" class="outil-reinit pli-tout" data-sens="ouvrir">'
        "Ouvrir tous les chapitres</button>"
        '<button type="button" class="outil-reinit pli-tout" data-sens="fermer">'
        "Fermer tous les chapitres</button></div>",
        "</section>",
    ]
    for chapitre in retenus:
        classe = "card grise" if chapitre["grise"] else "card"
        outillage_chapitre = "" if chapitre["grise"] else (
            # TF-0175 (retour n°4) : l'outillage vit au CHAPITRE — une barre pour toutes les
            # tables du chapitre, quel que soit le découpage en sous-chapitres.
            '<div class="outillage outil-chapitre" role="search">'
            '<input type="search" class="outil-recherche" placeholder="Rechercher dans ce '
            'chapitre…" aria-label="Rechercher dans les éléments du chapitre (insensible '
            'aux accents)">'
            '<button type="button" class="outil-reinit">Réinitialiser les filtres</button>'
            f'<span class="outil-compte" aria-live="polite">{chapitre["elements"]} / '
            f'{chapitre["elements"]} élément(s) affiché(s)</span></div>'
        )
        morceaux.append(
            f'<section class="{classe}" id="chap-{_e(chapitre["code"])}"'
            f'{" data-outille" if outillage_chapitre else ""}>'
        )
        # Chapitre REPLIABLE (retour humain du 14/08) : chevron natif <details>, ouvert par
        # défaut — replier est un choix du lecteur, jamais un masquage par défaut.
        morceaux.append('<details class="pli" open><summary>')
        morceaux.append(
            f'<h3>{_e(chapitre["code"])} — {_e(chapitre["titre"])}'
            '<span class="chevron" aria-hidden="true">▾</span></h3>'
        )
        morceaux.append("</summary>")
        morceaux.append(
            f'<p class="discret">pan(s) <code>{_e(", ".join(chapitre["pans"]))}</code> · '
            f"découpe par {_e(chapitre['decoupe'])} · {chapitre['elements']} élément(s) "
            f"inventorié(s), dont {chapitre['rattaches']} rattaché(s) par dérivation.</p>"
        )
        morceaux.append(_kpis_chapitre(chapitre))
        morceaux.append(outillage_chapitre)
        for manquant in chapitre.get("pans_non_couverts") or []:
            morceaux.append(
                '<p><span class="badge b-part" title="aucun banc d essai n existe pour ce pan '
                'dans cet environnement — le motif suit, le chemin de couverture aussi">'
                "pan non couvert</span> "
                f"<strong>{_e(manquant.get('pan'))}</strong> — {_e(manquant.get('motif'))}<br>"
                '<span class="note" aria-describedby="note-pour-couvrir" title="le geste qui '
                'rendrait ce pan mesurable au prochain audit">'
                f'Pour couvrir : {_e(manquant.get("pour_couvrir"))}</span></p>'
            )
        if chapitre["grise"]:
            morceaux.append(
                '<p class="discret">Chapitre <strong>non mesuré</strong> : aucun élément '
                "inventorié. Il reste affiché — un chapitre absent laisserait croire que "
                "le sujet n existe pas dans le produit.</p>"
            )
        for rang, sous in enumerate(chapitre["sous_chapitres"]):
            morceaux.append(f"<h4>{_e(sous['libelle'])} — {len(sous['elements'])} élément(s)</h4>")
            # Retour humain du 13/08 : cette section existait sans définition — 51 éléments
            # que le lecteur ne savait pas lire. Le chapeau est désormais obligatoire.
            if sous["libelle"].startswith("éléments non rattachés"):
                axe = chapitre["decoupe"]
                morceaux.append(
                    f'<p class="discret">Éléments réels de l inventaire que les règles de '
                    f"rattachement n associent à aucun {_e(axe)} (identifiant sans forme "
                    f"reconnue). Ils sont testés comme les autres — leur résultat est dans la "
                    f"colonne « Résultat » — mais rendus ici plutôt que sous un {_e(axe)} : un "
                    "élément rangé nulle part serait un élément qu on cesse de lire.</p>"
                )
            lignes, details_lignes, attributs = [], [], []
            for element in sous["elements"]:
                bouton, contenu = _detail_element(details.get((chapitre["code"], element["id"])))
                lignes.append(
                    [
                        _cellule_element(element["id"]),
                        _cellule_objectif(element["id"]),
                        _badge_etat(element["etat"]),
                        _e(element.get("classe") or "")
                        or '<span class="discret" title="élément passé : aucun constat, '
                        'donc pas de type">—</span>',
                        _constat_cellule(element)
                        + _badge_declaration(
                            declarations.get((str(element.get("pan") or ""), element["id"]))
                        ),
                        _e(element.get("risque"))
                        if element.get("risque") is not None
                        else '<span class="discret" title="pas de constat, donc pas de score '
                        'de risque">—</span>',
                        bouton,
                    ]
                )
                details_lignes.append(contenu)
                # data-etat : la donnée que les KPIs de chapitre filtrent au clic.
                attributs.append(f' data-etat="{_e(element["etat"])}"')
            colonnes = [
                "élément", "objectif", "état", "classe", "constat mesuré", "risque",
                "détail du cas",
            ]
            morceaux.append(
                _tableau(
                    colonnes, lignes, attributs=attributs, chapitre=True,
                    details_lignes=details_lignes,
                    # Identifiant PARLANT et stable : c'est lui que le compte par table nomme
                    # (G5), et le rang du sous-chapitre suffit à le rendre unique dans la page.
                    identifiant=f"table-chap-{_e(chapitre['code'])}-{rang}",
                )
            )
        morceaux.append("</details></section>")
    return "\n".join(morceaux) or '<p class="discret">Aucun chapitre de cette famille.</p>'


# --- Constats déclarés par le projet (RT-18) ----------------------------------------------------
def _section_declarations(rapport: dict, valeurs: dict[str, int]) -> str:
    """Le canal de réponse du projet, rendu en clair — retenues ET refusées.

    Rendre les seules déclarations RETENUES ferait de ce canal un bouton « faire taire » : ce
    qui rend la mesure opposable, c est que le refus se lise autant que l acceptation, avec le
    motif de l un comme la contre-preuve de l autre.
    """
    section = rapport.get("declarations") or {}
    entrees = section.get("entrees") or []
    compte = section.get("compte") or {}
    titre = '<h3 id="constats-declares">Constats déclarés par le projet</h3>'
    vocabulaire = (
        '<p class="discret">Motifs typés admis : '
        + " · ".join(
            f"<code>{_e(cle)}</code> ({_e(libelle)})"
            for cle, libelle in sorted((section.get("motifs") or {}).items())
        )
        + ".</p>"
        if section.get("motifs")
        else ""
    )
    if not section:
        return (
            titre
            + '<p class="discret">Ce rapport n a pas traversé le point d application des '
            "déclarations : aucune section <code>declarations</code>. Le canal existe "
            "néanmoins — voir <code>forge_tests/declarations.py</code>.</p>"
        )
    if not entrees:
        return (
            titre
            + '<p class="discret">Aucune déclaration : le projet n a écarté aucun constat. '
            f"Le canal existe et reste ouvert — {_e(section.get('pour_declarer'))}.</p>"
            + vocabulaire
        )
    lignes = []
    for entree in entrees:
        statut = str(entree.get("statut") or "")
        badge = {
            _declarations.RETENUE: (
                "b-info",
                "⚖ Retenue",
                "la preuve citée existe : le constat sort du décompte principal",
            ),
            _declarations.PERIMEE: (
                "b-part",
                "⏳ Périmée",
                "le terme est passé : le constat est revenu au décompte principal",
            ),
        }.get(
            statut,
            (
                "b-fail",
                "✕ Refusée",
                "déclaration non vérifiable : le constat reste au décompte principal",
            ),
        )
        lignes.append(
            [
                f"<code>{_e(entree.get('constat') or '—')}</code>",
                f'<span class="badge {badge[0]}" title="{_e(badge[2])}">{_e(badge[1])}</span>',
                _e(
                    (section.get("motifs") or {}).get(entree.get("motif"), entree.get("motif"))
                    or "—"
                ),
                f"<code>{_e(entree.get('preuve') or '—')}</code>",
                f"{_e(entree.get('par') or '—')}<br>"
                f'<span class="discret">{_e(entree.get("date") or "sans date")}'
                + (f" → {_e(entree.get('expire_le'))}" if entree.get("expire_le") else "")
                + "</span>",
                _texte_libre(entree.get("motif_du_refus") or entree.get("explication") or "—"),
            ]
        )
    inconnues = section.get("inconnues") or []
    note_inconnues = (
        '<p class="discret">Déclarations qui ne visent aucun constat de CE rapport : '
        + " · ".join(f"<code>{_e(cle)}</code>" for cle in inconnues)
        + ". Le constat a pu disparaître (bonne nouvelle) ou l identifiant changer — "
        "elles sont dites, jamais silencieuses.</p>"
        if inconnues
        else ""
    )
    return (
        titre
        + '<p class="discret">Le projet répond ici aux constats de l audit : contestation avec '
        "contre-preuve, élément bloqué par une configuration absente, ou code supplanté par le "
        "point d entrée réellement déployé. Chaque déclaration est vérifiée — la preuve citée "
        "doit exister —, datée et signée. Un constat déclaré reste mesuré et affiché ; il sort "
        f"du seul décompte principal ({valeurs['declares']} sur "
        f"{valeurs['declares'] + valeurs['echecs']} constats mesurés).</p>"
        + f'<p><strong>{compte.get(_declarations.RETENUE, 0)} retenue(s)</strong> · '
        f"{compte.get(_declarations.REFUSEE, 0)} refusée(s) · "
        f"{compte.get(_declarations.PERIMEE, 0)} périmée(s) · "
        f"{compte.get('inconnues', 0)} sans constat correspondant — source "
        f"<code>{_e(section.get('fichier'))}</code>, lue en LECTURE SEULE dans le projet.</p>"
        + vocabulaire
        + _tableau(
            ["constat", "état", "motif typé", "preuve citée", "déclaré par", "explication"],
            lignes,
            identifiant="table-declarations",
            outille_force=True,
        )
        + note_inconnues
    )


# --- Actions (R8) -------------------------------------------------------------------------------
def _action_structuree(quoi: str, pourquoi: str, obtenu: str, badge: str = "") -> str:
    """Une action lisible (retour humain du 14/08) : QUOI faire, POURQUOI, ce qu'on OBTIENT.
    Trois lignes nommées — jamais une phrase-fleuve où tout se mélange."""
    return (
        "<li>" + badge
        + f'<span class="a-quoi" data-litteral-ok><strong>Quoi :</strong> {quoi}</span>'
        + f'<span class="a-pourquoi" data-litteral-ok><strong>Pourquoi :</strong> '
        f"{pourquoi}</span>"
        + f'<span class="a-obtenu" data-litteral-ok><strong>Vous obtiendrez :</strong> '
        f"{obtenu}</span></li>"
    )


def _synthese_actions(rapport: dict, valeurs: dict[str, int]) -> str:
    """Synthèse des suites à donner : plan de rejeu pour l IA, priorités pour l humain.

    Tout est dérivé du rapport (actions[], findings[].risque, non_testables[],
    pans_non_couverts[]) — la page n invente aucun ordre : la priorité EST le risque calculé
    au rapport, et la configuration passe d abord parce qu elle DÉBLOQUE la mesure.
    """
    risques = {
        str(f.get("id")): f.get("risque")
        for f in (rapport.get("findings") or [])
        if f.get("risque") is not None
    }
    actions = rapport.get("actions") or []
    morceaux = ['<section class="card" id="synthese-actions"><h3>Que faire de cet audit ?</h3>']
    # 1. auto_ia — le plan de rejeu, borné (G-3 amendé sur mandat humain du 14/08 : 5 cycles,
    #    extensibles à 7 si chaque cycle réduit strictement le reste — jamais de boucle sans fin).
    auto = [a for a in actions if a.get("categorie") == "auto_ia"]
    if auto:
        par_etape: dict[str, int] = {}
        for action in auto:
            etape = str(action.get("etape_cible") or "")
            par_etape[etape] = par_etape.get(etape, 0) + 1
        repartition_txt = " · ".join(
            f"{n} en {_glossaire.etape_action(etape)}"
            for etape, n in sorted(par_etape.items(), key=lambda kv: -kv[1])
        )
        boucle = rapport.get("boucle_fermeture") or {}
        if boucle:
            etat_boucle = (
                f"<p><strong>Boucle jouée sur cet audit :</strong> "
                f"{_e(boucle.get('cycles'))} cycle(s) sur une borne de "
                f"{_e(boucle.get('borne', 5))} — il reste {len(auto)} action(s) "
                "automatisables, listées ci-dessous avec leur motif.</p>"
            )
        else:
            etat_boucle = (
                '<p class="discret">La boucle n a PAS tourné sur cet audit : ce rapport est '
                "une mesure one-shot — les actions ci-dessous sont le PLAN du premier cycle. "
                "Ces correctifs s écrivent dans la SUITE DU PROJET, que l audit ne modifie "
                "jamais (garde-fou G-1) : c est l agent du run qui les applique, pas la "
                "forge.</p>"
            )
        morceaux.append(
            f"<p><strong>{len(auto)} action(s) automatisables par l IA</strong> "
            f"({repartition_txt}) — à traiter en <strong>boucle bornée</strong> jusqu à "
            "épuisement : 5 cycles maximum, 7 si chaque cycle réduit strictement le reste "
            "(garde-fou G-3, amendé le 14/08) :</p>"
            "<ol>"
            "<li>appliquer les correctifs <code>auto_ia</code> par lot (la source qui fait foi "
            "dit quoi écrire — chaque cas généré reste une proposition relue) ;</li>"
            "<li>re-mesurer : <code>--reprendre &lt;rapport.json&gt;</code> rejoue l audit sur "
            "l état corrigé ;</li>"
            "<li>répéter tant qu il reste des actions <code>auto_ia</code> ET que la borne n "
            "est pas atteinte ; au-delà, livrer avec la liste des écarts résiduels — jamais "
            "assouplir une assertion pour « faire passer » (interdit G-2).</li>"
            "</ol>" + etat_boucle
        )
    # 2. manuelle_utilisateur — VOS actions, structurées (Quoi / Pourquoi / Vous obtiendrez).
    #    La configuration d abord (elle débloque la mesure), puis les arbitrages par risque.
    votres = [a for a in actions if a.get("categorie") == "manuelle_utilisateur"]
    if votres:
        elements: list[str] = []
        # 2a. Configuration absente — UN bloc par jeu de champs, pans regroupés (le rapport
        #     porte le détail par pan ; l afficher quatre fois était le retour n°1 du 14/08).
        groupes: dict[tuple[str, ...], dict[str, int]] = {}
        for entree in rapport.get("non_testables") or []:
            champs = tuple(entree.get("champs_requis") or [])
            pan = str(entree.get("pan") or "")
            groupes.setdefault(champs, {})
            groupes[champs][pan] = groupes[champs].get(pan, 0) + 1
        for champs, pans in sorted(groupes.items()):
            detail_pans = " · ".join(f"{n} du pan « {p} »" for p, n in sorted(pans.items()))
            total = sum(pans.values())
            elements.append(
                _action_structuree(
                    "renseigner la configuration d audit dans "
                    "<code>&lt;projet&gt;/.env.forge-tests</code> — "
                    f"{len(champs)} champ(s), noms seuls (les valeurs ne transitent jamais) : "
                    f"<code>{_e(', '.join(champs))}</code> — puis relancer avec "
                    "<code>--reprendre &lt;rapport.json&gt;</code>",
                    f"{total} élément(s) inventorié(s) sont injouables ici ({detail_pans}) : "
                    "personne ne POUVAIT les exercer sans cette configuration — manque d "
                    "environnement, pas trou de couverture du projet",
                    "ces éléments mesurés au prochain audit ; les pans concernés sortent de "
                    "« non joués » et le verdict PARTIEL peut se prononcer",
                )
            )
        # 2b. Pans non couverts : motif et chemin de couverture, tels que le rapport les
        #     porte. TOUS rendus — même quand le pan attend aussi la configuration du 2a,
        #     son `pour_couvrir` est un geste DISTINCT (déclarer l'app, exposer un module…)
        #     qui serait perdu s'il était absorbé par le regroupement.
        for entree in rapport.get("pans_non_couverts") or []:
            if not isinstance(entree, dict):
                continue
            elements.append(
                _action_structuree(
                    _e(entree.get("pour_couvrir") or "chemin de couverture non déclaré"),
                    f"le pan « {_e(entree.get('pan'))} » est entièrement NON MESURÉ — "
                    f"{_e(entree.get('motif') or 'sans motif')}",
                    "le pan mesuré au prochain audit, avec ses éléments dans les chapitres",
                )
            )
        # 2c. Les autres actions à vous (arbitrages, sondes) — par risque décroissant.
        deja = {PREFIXE_NON_TESTABLE, PREFIXE_PAN_NON_COUVERT}
        restantes = [
            a for a in votres
            if not any(str(a.get("finding_ref") or "").startswith(p) for p in deja)
        ]
        restantes.sort(key=lambda a: -(risques.get(str(a.get("finding_ref")), 0) or 0))
        for action in restantes:
            badge = (
                f'<span class="badge b-fail" title="risque du constat source '
                f'(criticité × probabilité × coût)">risque '
                f'{risques[str(action.get("finding_ref"))]}</span> '
                if str(action.get("finding_ref")) in risques
                else ""
            )
            elements.append(
                "<li>" + badge + f"{_texte_libre(action.get('attendu'))} "
                f"<span class=\"discret\">(étape : "
                f"{_e(_glossaire.etape_action(str(action.get('etape_cible') or '')))})"
                "</span></li>"
            )
        regroupement = (
            f", regroupées en {len(elements)} point(s) — la configuration compte pour un seul "
            "geste, quel que soit le nombre de pans qu'elle débloque"
            if len(elements) != len(votres)
            else ""
        )
        morceaux.append(
            f"<p><strong>Vos {len(votres)} action(s)</strong>{regroupement} — personne "
            "d'autre ne peut les faire. La configuration d'abord (elle débloque la mesure), "
            "puis les arbitrages par risque décroissant :</p>"
            f'<ol class="actions-vous">{"".join(elements)}</ol>'
        )
    # 3. manuelle_dev — le reste du travail humain, pointé vers la liste filtrable.
    dev = valeurs.get("actions_manuelle_dev", 0)
    if dev:
        morceaux.append(
            f'<p class="discret">{dev} action(s) « développeur » restent à arbitrer — la liste '
            "ci-dessous se filtre par catégorie et par étape.</p>"
        )
    morceaux.append("</section>")
    return "".join(morceaux)


def _composant_filtres() -> str:
    """Composant filtres du socle : asset du skill installé, sinon la copie D-12 du dépôt."""
    skill = (
        Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "assets" / "table-filters.js"
    )
    source = skill if skill.exists() else Path(__file__).with_name("table-filters.js")
    return source.read_text(encoding="utf-8")


def _composant_filtres_css() -> str:
    """CSS JUMEAU du composant (TF-0176/H5) : un composant sans son habillage sort en rendu
    brut navigateur — c'est le retour humain n°1 du 13/08 soir. Même règle de chargement."""
    skill = (
        Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "assets" / "table-filters.css"
    )
    source = skill if skill.exists() else Path(__file__).with_name("table-filters.css")
    return source.read_text(encoding="utf-8")


# --- Libellés d'éléments (TF-0175) --------------------------------------------------------------
# « qualif:effet:/:0:form » n'explique rien à un lecteur (retour humain n°5). Le libellé et
# l'OBJECTIF du test sont DÉRIVÉS de la forme de l'identifiant — jamais inventés : le module
# partagé `libelles.py` (dashboard + cahiers, retour humain du 14/08) porte les deux tables ;
# forme inconnue → pas de libellé, l'id technique reste toujours affiché.


def _cellule_objectif(identifiant: str) -> str:
    """Colonne « objectif du test » (retour humain du 14/08) : le périmètre précis de la
    ligne, dérivé de la forme de l'élément. Forme inconnue → un tiret QUI LE DIT."""
    objectif = _objectif_element(identifiant)
    if objectif:
        return f'<span class="objectif">{_e(objectif)}</span>'
    return (
        '<span class="discret" title="forme d identifiant inconnue du glossaire des '
        'objectifs — l objectif reste celui du chapitre">—</span>'
    )


def _cellule_element(identifiant: str) -> str:
    lib = _libelle_element(identifiant)
    code = f'<code class="discret">{_e(identifiant)}</code>'
    # data-litteral-ok : un libellé dérivé peut CITER le vocabulaire du domaine audité
    # (« NOT NULL ») — c'est le fait nommé, pas une valeur non traitée qui fuit (L11).
    return (f'<span class="lib" data-litteral-ok>{_e(lib)}</span><br>{code}') if lib else code


def construire(
    rapport: dict,
    contexte: dict,
    chapitres: list[dict],
    precedent: dict | None = None,
    chapitres_cas: list[dict] | None = None,
) -> str:
    """Page complète. `chapitres` vient de `surface.repartir` — dérivé, jamais écrit en dur.

    `chapitres_cas` (facultatif, TF-0153) : la sortie de `cahiers.cas_du_chapitre` — la même
    dérivation qui écrit les cahiers. Quand elle est fournie, chaque élément déplie son cas
    (préconditions, jeu, étapes, attendu, exigences) SOUS LES MÊMES RÉFÉRENCES que le cahier.
    """
    valeurs = totaux(rapport)
    titre = f"{contexte['produit']} — Dashboard tests — {contexte['date']}"
    # TF-0159 : `precedent` accepte un rapport OU une liste (multi-runs) — les deltas des
    # tuiles se jugent toujours contre le PLUS RÉCENT des précédents.
    dernier_precedent = precedent[-1] if isinstance(precedent, list) and precedent else precedent
    deltas = (
        {
            cle: valeurs[cle] - avant
            for cle, avant in totaux(dernier_precedent).items()
            if cle in valeurs
        }
        if dernier_precedent
        else {}
    )

    # Index (code chapitre, id élément) -> détail (cas dérivés OU raison de non-couverture).
    details: dict[tuple[str, str], dict] = {}
    for chapitre in chapitres_cas or []:
        for sous in chapitre.get("sous_chapitres") or []:
            for entree in sous.get("entrees") or []:
                details[(chapitre["code"], entree["element"]["id"])] = {"cas": entree["cas"]}
        for element in chapitre.get("non_couverts") or []:
            details[(chapitre["code"], element["id"])] = {
                "raison": element.get("raison"),
                "exigences": element.get("exigences"),
            }

    # RT-18 : index (pan, id élément) -> déclaration du projet, lue sur les findings eux-mêmes.
    # La page ne relit pas `forge/constats-contestes.jsonl` : c est le rapport qui porte le
    # verdict de vérification, sans quoi deux lecteurs du même audit auraient deux vérités.
    declarations_par_element: dict[tuple[str, str], dict] = {}
    for finding in rapport.get("findings") or []:
        if finding.get("declaration"):
            declarations_par_element[
                (str(finding.get("pan") or ""), str(finding.get("id") or ""))
            ] = finding["declaration"]

    def pct(part: int, tout: int) -> str:
        return f"{round(100 * part / tout)} % " if tout else ""

    # RL-3 (TF-0235) — le repère de lecture d un compteur de SUIVI, c est d abord son point
    # précédent. Absent, il se dit : « pas mesurable ici » est une information, pas un blanc.
    avant_totaux = totaux(dernier_precedent) if dernier_precedent else {}

    def derive(cle: str) -> str:
        if cle not in avant_totaux:
            return (
                " Aucun rapport précédent n a été fourni : la dérive de ce compteur n est "
                "pas mesurable sur ce run."
            )
        avant = avant_totaux[cle]
        ecart = valeurs[cle] - avant
        if ecart == 0:
            return f" Le rapport précédent en comptait {avant}, soit un écart nul."
        return f" Le rapport précédent en comptait {avant}, soit un écart de {ecart:+d}."

    lignes_seuils, seuils_non_tenus, nb_seuils = _etat_des_seuils(rapport)
    if nb_seuils and seuils_non_tenus:
        synthese_seuils = (
            f"<p><strong>{len(seuils_non_tenus)} seuil(s) non tenu(s) sur {nb_seuils}</strong> — "
            + " · ".join(_e(s) for s in seuils_non_tenus)
            + ".</p>"
        )
    elif nb_seuils:
        synthese_seuils = f"<p><strong>{nb_seuils}/{nb_seuils} seuils tenus.</strong></p>"
    else:
        synthese_seuils = '<p class="discret">Aucun seuil opposable au rapport.</p>'

    synthese = [
        "<h2>1 · Synthèse</h2>",
        '<p id="note-severite" class="discret">« sévérité » = classe déclarée par la règle qui a '
        "produit le constat (bloquant · majeur · mineur) — barème porté par le rapport, "
        "jamais recalculé par la page.</p>",
        '<p id="note-risque" class="discret">« risque » = score du rapport '
        "(criticité × probabilité × coût tardif, notes 1-5) — calcul de "
        "<code>forge_tests.noyau.score_risque</code>, la page ne fait que le rendre.</p>",
        '<p id="note-pour-couvrir" class="discret">« Pour couvrir » = le geste qui rendrait un '
        "pan non couvert mesurable au prochain audit — champ <code>pour_couvrir</code> du "
        "rapport, jamais inventé par la page.</p>",
        _verdict_bloc(rapport, contexte, valeurs, seuils_non_tenus, nb_seuils),
        '<div class="grille">',
        _tuile(
            "elements",
            valeurs["elements"],
            delta=deltas.get("elements"),
            cible="synthese",
            ancre="table-par-pan",
            repere="Base de tous les pourcentages de cette page : ce que l audit a trouvé "
            "à tester dans le produit." + derive("elements"),
        ),
        _tuile(
            "passes",
            valeurs["passes"],
            delta=deltas.get("passes"),
            part=pct(valeurs["passes"], valeurs["elements"]) + "des éléments",
            cible="synthese",
            ancre="table-par-pan",
            repere=f"{valeurs['passes']} sur {valeurs['elements']} élément(s) inventoriés. "
            f"Le complément, soit {valeurs['elements'] - valeurs['passes']} élément(s), se "
            "répartit entre constats mesurés, non joués et non testables."
            + derive("passes"),
        ),
        _tuile(
            "echecs",
            valeurs["echecs"],
            delta=deltas.get("echecs"),
            cible="echecs",
            ancre="table-echecs",
            repere=f"{valeurs['echecs']} constat(s) au décompte opposable, quand "
            f"{valeurs['declares']} autre(s) sont déclarés par le projet. Un seul constat "
            "bloquant suffit à faire basculer le verdict en FAIL." + derive("echecs"),
        ),
        _tuile(
            "echecs_bloquants",
            valeurs["echecs_bloquants"],
            delta=deltas.get("echecs_bloquants"),
            part=pct(valeurs["echecs_bloquants"], valeurs["echecs"]) + "des constats",
            cible="echecs",
            ancre="table-echecs",
            filtre_severite="bloquant",
            repere=f"{valeurs['echecs_bloquants']} sur {valeurs['echecs']} constat(s) au "
            "décompte : ce sont ceux qui se traitent avant toute mise en production."
            + derive("echecs_bloquants"),
        ),
        _tuile(
            "declares",
            valeurs["declares"],
            delta=deltas.get("declares"),
            part=pct(valeurs["declares"], valeurs["declares"] + valeurs["echecs"])
            + "des constats mesurés",
            cible="echecs",
            ancre="constats-declares",
            libelle="Constats déclarés par le projet",
            descriptif="constats mesurés que le projet a déclarés — contestés avec "
            "contre-preuve, ou bloqués par une configuration absente ou du code supplanté. "
            "Hors du décompte principal, jamais retirés du rapport",
            repere=f"{valeurs['declares']} sur "
            f"{valeurs['declares'] + valeurs['echecs']} constat(s) mesurés sortent du "
            "décompte opposable. Ils restent affichés avec leur contre-preuve, leur "
            "signataire et leur date." + derive("declares"),
        ),
        _tuile(
            "non_joues",
            valeurs["non_joues"],
            delta=deltas.get("non_joues"),
            cible="non-joues",
            repere=f"{valeurs['non_testables']} élément(s) attendent une configuration "
            f"absente et {valeurs['pans_non_couverts']} pan(s) n ont pas de banc d essai "
            "ici. Personne ne POUVAIT les exercer dans cet environnement : ce n est pas un "
            "trou de couverture du projet." + derive("non_joues"),
        ),
        _tuile(
            "actions",
            valeurs["actions"],
            delta=deltas.get("actions"),
            cible="actions",
            ancre="synthese-actions",
            repere=f"{valeurs['actions']} suite(s) à donner portées par le rapport, "
            "réparties entre l IA, le développeur et vous. C est la file de travail de "
            "l opérateur, filtrable par catégorie et par étape." + derive("actions"),
        ),
        "</div>",
        '<div class="grille">',
        _tuile(
            "non_testables",
            valeurs["non_testables"],
            cible="non-joues",
            ancre="non-testables-ici",
            repere=f"{valeurs['non_testables']} sur {valeurs['non_joues']} élément(s) non "
            "joués tiennent à une configuration absente de cet environnement. Fournir les "
            "champs, puis reprendre le rapport, les rend mesurables au prochain audit."
            + derive("non_testables"),
        ),
        _tuile(
            "pans_non_couverts",
            valeurs["pans_non_couverts"],
            cible="non-joues",
            ancre="pans-non-couverts",
            repere=f"{valeurs['pans_non_couverts']} domaine(s) entiers sans banc d essai. "
            "Chacun porte son motif et le geste qui le rendrait mesurable au prochain audit."
            + derive("pans_non_couverts"),
        ),
        "</div>",
        _figure_etats(chapitres),
        _figure_pans(chapitres),
        _chemins(),
        "<h3>Résultats par pan testé</h3>",
        '<p class="discret">Un chapitre = un domaine testé (pan). Chaque ligne dit combien '
        "d éléments sont passés, combien sont KO et pourquoi lire plus loin — le lien ouvre le "
        "chapitre détaillé. Un pan non testé le dit explicitement, avec sa raison.</p>",
        _synthese_par_pan(chapitres),
        "<h3>Seuils opposables et leur état</h3>",
        '<p class="discret">Un seuil opposable est un ENGAGEMENT chiffré du contrat de tests '
        "(ex. « 100 % des affordances câblées ») : il est déclaré avant l audit, avec sa "
        "sévérité, et le verdict global en dépend — c est ce qui le rend opposable. "
        "« ✓ tenu » = aucun constat ne le contredit ; « ✕ non tenu » = des constats citent sa "
        "valeur, la colonne « aller voir » des tuiles et l onglet Échecs les détaillent.</p>",
        synthese_seuils,
        _tableau(
            ["seuil", "valeur", "sévérité", "état constaté", "porte sur"],
            lignes_seuils,
        ),
        '<p class="discret">L état est dérivé des findings <code>seuil-non-tenu</code> qui '
        "citent la valeur du seuil. Deux seuils de même valeur ne sont pas discernables par ce "
        "rapprochement : ils seraient alors marqués « non tenu » tous les deux.</p>",
        '<h3 id="tendance">Tendance</h3>',
        _figure_tendance(rapport, precedent),
        _tendance(rapport, precedent),
    ]

    echecs = [
        "<h2>4 · Échecs — raisons mesurées</h2>",
        '<p class="discret">Chaque ligne est un constat RATTACHÉ à un élément nommé, trié '
        "par risque décroissant. Un défaut sans élément n existe pas dans ce framework. "
        "Un constat que le projet a DÉCLARÉ (contesté, ou bloqué par configuration ou code "
        "supplanté) reste dans cette table, avec sa contre-preuve : il sort du décompte, "
        "jamais du rapport.</p>",
        _tableau(
            ["risque", "sévérité", "pan", "élément", "classe", "raison mesurée", "localisation"],
            [
                [
                    _e(f.get("risque") if f.get("risque") is not None else "—"),
                    _e(f.get("severite")),
                    _e(f.get("pan")),
                    f"<code>{_e(f.get('id'))}</code>",
                    _e(f.get("classe")),
                    _texte_libre(f.get("message")) + _badge_declaration(f.get("declaration")),
                    f'<span class="discret">{_e(f.get("localisation"))}</span>',
                ]
                for f in (rapport.get("findings") or [])
            ],
            attributs=[
                f' data-severite="{_e(f.get("severite"))}"'
                + (
                    f' data-declaration="{_e((f.get("declaration") or {}).get("statut"))}"'
                    if f.get("declaration")
                    else ""
                )
                for f in (rapport.get("findings") or [])
            ],
            identifiant="table-echecs",
        ),
        _section_declarations(rapport, valeurs),
    ]

    non_joues = [
        "<h2>5 · Non joués</h2>",
        '<h3 id="non-testables-ici">Non testables ici — configuration absente</h3>',
        '<p class="discret">Ce n est pas un trou de couverture du projet : personne ne POUVAIT '
        "l exercer dans cet environnement. Fournir les champs, puis <code>--reprendre</code> le "
        "rapport. Seuls les NOMS des champs figurent ici : jamais leurs valeurs.</p>",
        _tableau(
            ["pan", "élément", "champs requis", "motif"],
            [
                [
                    _e(n.get("pan")),
                    f"<code>{_e(n.get('element'))}</code>",
                    f"<code>{_e(', '.join(n.get('champs_requis') or []))}</code>",
                    _e(n.get("motif")),
                ]
                for n in (rapport.get("non_testables") or [])
            ],
            identifiant="table-non-testables",
            # Retour humain du 14/08 : recherche, tri et filtres sur CET onglet aussi,
            # quel que soit le volume — on y cherche un pan ou un champ précis.
            outille_force=True,
        ),
        '<h3 id="pans-non-couverts">Pans non couverts — motif ET chemin de couverture</h3>',
        _tableau(
            ["pan", "motif", "pour couvrir"],
            [
                [_e(p.get("pan")), _e(p.get("motif")), _e(p.get("pour_couvrir"))]
                for p in (rapport.get("pans_non_couverts") or [])
                if isinstance(p, dict)
            ],
            identifiant="table-pans-non-couverts",
            outille_force=True,
        ),
    ]

    boutons = []
    for axe, source in (("categorie", CATEGORIES), ("etape", ETAPES)):
        for valeur in source:
            libelle = (
                _glossaire.categorie_action(valeur)[0]
                if axe == "categorie"
                else _glossaire.etape_action(valeur)
            )
            boutons.append(
                f'<button type="button" data-axe="{axe}" data-valeur="{_e(valeur)}" '
                f'aria-pressed="false" title="identifiant : {_e(valeur)}">{_e(libelle)}</button>'
            )
    lignes_actions, attributs_actions = [], []
    for action in rapport.get("actions") or []:
        categorie = str(action.get("categorie") or "")
        libelle, legende = _glossaire.categorie_action(categorie)
        lignes_actions.append(
            [
                f"<code>{_e(action.get('finding_ref'))}</code>",
                f'<span class="badge b-info" title="{_e(legende)} — identifiant : '
                f'{_e(categorie)}">{_e(libelle)}</span>',
                _e(_glossaire.etape_action(str(action.get("etape_cible") or ""))),
                _texte_libre(action.get("attendu")),
            ]
        )
        attributs_actions.append(
            f' data-categorie="{_e(action.get("categorie"))}"'
            f' data-etape="{_e(action.get("etape_cible"))}"'
        )
    actions_html = [
        "<h2>6 · Actions</h2>",
        '<p class="discret">Classification TERNAIRE portée par le rapport JSON — la page ne '
        "fait que la rendre. Filtre attendu par le dossier de MEP : "
        "<code>jq &#39;.actions[] | "
        "select(.categorie==&quot;manuelle_utilisateur&quot;)&#39;</code>."
        "</p>",
        _synthese_actions(rapport, valeurs),
        '<div class="grille">',
        *[
            _tuile(
                f"actions_{c}",
                valeurs[f"actions_{c}"],
                part=pct(valeurs[f"actions_{c}"], valeurs["actions"]) + "des actions",
                cible="actions",
                ancre="table-actions",
                filtre_axe="categorie",
                filtre_valeur=c,
                libelle=_glossaire.categorie_action(c)[0],
                descriptif=_glossaire.categorie_action(c)[1],
                repere=f"{valeurs[f'actions_{c}']} action(s) de cette catégorie sur les "
                f"{valeurs['actions']} que porte le rapport. La classification est portée "
                "par le rapport JSON, la page ne fait que la rendre.",
            )
            for c in CATEGORIES
        ],
        "</div>",
        '<div class="grille">',
        *[
            _tuile(
                f"etape_{etape.replace('-', '_')}",
                valeurs[f"etape_{etape.replace('-', '_')}"],
                cible="actions",
                ancre="table-actions",
                filtre_axe="etape",
                filtre_valeur=etape,
                libelle=f"Étape : {_glossaire.etape_action(etape)}",
                descriptif="actions à jouer à cette étape du cycle",
                repere=f"{valeurs['etape_' + etape.replace('-', '_')]} action(s) se jouent "
                f"à cette étape, sur les {valeurs['actions']} que porte le rapport. "
                "L étape cible est déclarée par le rapport, jamais devinée par la page.",
            )
            for etape in ETAPES
        ],
        "</div>",
        '<div class="filtres">' + "".join(boutons) + "</div>",
        _tableau(
            ["référence", "catégorie", "étape cible", "attendu"],
            lignes_actions,
            attributs=attributs_actions,
            identifiant="table-actions",
        ),
    ]

    panneaux = [
        ("synthese", "Synthèse", synthese),
        (
            "fonctionnels",
            "Fonctionnels",
            [
                "<h2>2 · Fonctionnels</h2>",
                _panneau_chapitres(
                    chapitres, "fonctionnel", details, declarations_par_element
                ),
            ],
        ),
        (
            "techniques",
            "Techniques",
            [
                "<h2>3 · Techniques</h2>",
                _panneau_chapitres(chapitres, "technique", details, declarations_par_element),
            ],
        ),
        ("echecs", "Échecs", echecs),
        ("non-joues", "Non joués", non_joues),
        ("actions", "Actions", actions_html),
    ]
    # Sommaire réel (L6 du socle) : chaque entrée ANNONCE ce qu on va y trouver (.toc-d) et
    # chaque panneau ouvre par un chapeau (.ch-apprend, L7). Le clic bascule l onglet — une
    # ancre vers un panneau masqué serait une affordance morte.
    annonces = {
        "synthese": "verdict, résultats par pan, état des seuils opposables et tendance",
        "fonctionnels": "synthèse des pans fonctionnels, puis chapitres repliables — "
        "objectif, résultat, constat expliqué et cas dépliable par élément",
        "techniques": "synthèse des pans techniques, puis chapitres repliables — "
        "objectif, résultat, constat expliqué et cas dépliable par élément",
        "echecs": "chaque constat rattaché à un élément nommé, trié par risque décroissant, "
        "puis les constats déclarés par le projet avec leur contre-preuve",
        "non-joues": "non testables (configuration absente) et pans non couverts, motivés — "
        "tables outillées",
        "actions": "suites à donner structurées (quoi, pourquoi, résultat), plan de boucle "
        "IA, puis liste filtrable par catégorie et étape",
    }
    # TF-0235 : `data-vue` sur CHAQUE entrée de navigation — c est le marqueur que le
    # référentiel de restitution lit pour vérifier qu une page s organise en vues naviguées
    # (RL-1). Les deux barres en portent : le sommaire annoté (L6 du socle) et les onglets.
    toc = "".join(
        f'<a href="#{identifiant}" data-vue="{identifiant}">'
        f"<strong>{rang + 1} · {_e(libelle)}</strong> "
        f'<span class="toc-d">{_e(annonces[identifiant])}</span></a>'
        for rang, (identifiant, libelle, _) in enumerate(panneaux)
    )
    nav = "".join(
        f'<button type="button" role="tab" data-cible="{identifiant}" '
        f'data-vue="{identifiant}" '
        f'aria-selected="{"true" if rang == 0 else "false"}" '
        f'aria-controls="{identifiant}">{rang + 1} · {_e(libelle)}</button>'
        for rang, (identifiant, libelle, _) in enumerate(panneaux)
    )
    # L10 du socle : un chapitre porteur d une table de ≥ 8 lignes publie un EXEMPLE DE
    # LECTURE — la première ligne déchiffrée en français, pour amorcer le parcours.
    exemples = {
        "synthese": "un pan testé, ses passés/KO en chiffres et en %, puis un seuil opposable, "
        "sa valeur, sa sévérité déclarée et l'état constaté",
        "fonctionnels": "un élément nommé de l'inventaire, l'objectif précis de son test, son "
        "résultat (✓ ✕ ○), le type et la preuve de son constat — ou le pourquoi de son "
        "non-joué —, son risque, et son cas dépliable",
        "techniques": "un élément nommé de l'inventaire, l'objectif précis de son test, son "
        "résultat (✓ ✕ ○), le type et la preuve de son constat — ou le pourquoi de son "
        "non-joué —, son risque, et son cas dépliable",
        "echecs": "le constat au risque le plus élevé d'abord : sa sévérité, son pan, "
        "l'élément auquel il est rattaché, la raison mesurée et sa localisation",
        "non-joues": "un élément injouable ICI, les noms des champs de configuration requis "
        "(jamais leurs valeurs) et le motif",
        "actions": "une action, sa catégorie ternaire, l'étape cible où la jouer et le "
        "résultat attendu",
    }
    corps = "".join(
        f'<section class="panneau" id="{identifiant}" role="tabpanel"'
        f'{"" if rang == 0 else " hidden"}>'
        + contenu[0]
        + f'<p class="discret ch-apprend">Ce panneau présente : {_e(annonces[identifiant])}.</p>'
        + f'<p class="discret exemple-lecture">Exemple de lecture — une ligne type : '
        f"{_e(exemples[identifiant])}.</p>"
        + "\n".join(contenu[1:])
        + "</section>"
        for rang, (identifiant, _, contenu) in enumerate(panneaux)
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(titre)}</title>
<meta name="description" content="Dashboard d exécution des tests — dérivé du seul
 rapport JSON produit par Forge Tests.">
<meta name="theme-color" content="#2563EB">
<meta name="color-scheme" content="light dark">
<!-- Favicon-lettre (13/08, loi transverse n°3) : première lettre du produit audité. -->
<link rel="icon" type="image/svg+xml"
 href="{_FAVICON_AVANT}{_e(str(contexte["produit"] or "D").strip()[:1].upper())}{_FAVICON_APRES}">
<style>{_STYLE}
/* Habillage du composant filtres — CSS jumeau (TF-0176/H5), chargé avec le JS. */
{_composant_filtres_css()}</style>
</head>
<!-- TF-0235 — famille de restitution DÉCLARÉE : « suivi ». Ce dashboard est revisité d un
     audit à l autre ; ses lecteurs sont le pilote (« est-ce que ça dérive ? ») et l opérateur
     (« que traiter d abord ? »). C est ce marqueur que l oracle de restitution consomme. -->
<body data-restitution="suivi">
<div class="wrap">
<header class="doc">
  <p class="eyebrow">Digit-AI · Forge Tests · Dashboard d'exécution</p>
  <h1>{_e(contexte['produit'])} — Dashboard tests</h1>
  <p class="discret">Audit du {_e(contexte['date'])} · source unique : le rapport
     <code>{_e(contexte['rapport_nom'])}</code> · page autonome, aucun appel réseau.
     <button type="button" id="bascule-theme" class="theme-toggle"
             aria-pressed="false">Thème sombre</button></p>
</header>
<nav class="toc" aria-label="Sommaire">{toc}</nav>
<nav class="onglets" role="tablist">{nav}</nav>
<main>{corps}</main>
<footer class="doc">
  Digit-AI — Forge Tests · {_e(contexte['produit'])} · dashboard dérivé du rapport, sans
  recalcul : tout chiffre se conteste sur le rapport JSON. Aucune valeur d environnement
  n entre dans cette page. À l impression, tout est déplié et le thème est toujours clair.
</footer>
{_manifeste_ecarts(_ecarts_declares(rapport, valeurs, chapitres, precedent, nb_seuils))}
</div>
<script>{_SCRIPT}</script>
<script>/* Composant filtres du socle — asset du skill installé ou copie D-12 du dépôt. */
{_composant_filtres()}</script>
<script>/* Initialisation D-12 : l API n auto-démarre pas — sans cet appel, les filtres de
   colonne n existent pas (affordance morte constatée sur le dashboard BAV2 du 13/08).

   `data-tf-count-for` rattache chaque table à son compte : c est le contrat que l oracle
   G5 vérifie, et le composant s en sert pour annoncer les lignes masquées. Mais il ne
   connaît QUE ses filtres de colonne : dès qu une recherche ou un KPI d état filtre aussi,
   son compte serait faux, et il écraserait le nôtre. Le composant capture sa référence au
   compteur à l INITIALISATION : l attribut lui est donc retiré le temps de cet appel, et
   remis aussitôt. La page garde son marquage, le script maison garde la plume. */
(function () {{
  var marques = Array.prototype.slice.call(document.querySelectorAll('[data-tf-count-for]'));
  marques.forEach(function (c) {{
    c.setAttribute('data-tf-compte-de', c.getAttribute('data-tf-count-for'));
    c.removeAttribute('data-tf-count-for');
  }});
  if (window.DigitAITableFilters) {{ DigitAITableFilters.initAll(); }}
  marques.forEach(function (c) {{
    c.setAttribute('data-tf-count-for', c.getAttribute('data-tf-compte-de'));
    c.removeAttribute('data-tf-compte-de');
  }});
}})();</script>
</body>
</html>
"""


# --- Contrôle pré-génération (contrat pilot §2 bis, TF-0153) ------------------------------------
# La forge est responsable de son gabarit : AVANT de livrer, la page rendue est confrontée aux
# règles courantes du socle HTML. Une dérive ne bloque pas la génération (le run reste borné) :
# elle est imprimée pour le ledger et remonte au pilot en candidature TODO (sidecar déposé par
# `livrables.produire` à côté des livrables — donc HORS du projet audité, comme eux).
_REGLES_PREGENERATION: tuple[tuple[str, str], ...] = (
    (
        "E4-largeur",
        r"max-width:\s*clamp\(75vw",
    ),
    (
        "R-30-clair-par-defaut",
        r'data-theme="sombre"',
    ),
    (
        "G1-bascule-cablee",
        r"bascule-theme",
    ),
    (
        "G1-persistance",
        r"localStorage",
    ),
    (
        "H2-recherche",
        r"outil-recherche",
    ),
    (
        "H2-reinitialisation",
        r"outil-reinit",
    ),
    (
        "H3-kpi-cliquable",
        r'<button type="button" class="tuile',
    ),
    # Retours humains du 14/08 : chapitres repliables, KPIs d'état par chapitre, colonne
    # « objectif du test », actions structurées — un gabarit qui les perdrait dériverait.
    (
        "H-chapitres-repliables",
        r'<details class="pli"',
    ),
    (
        "H3-kpi-chapitre",
        r'class="kpi-etat',
    ),
    (
        "H4-objectif-du-test",
        r"Objectif du test",
    ),
    (
        "print-clair-force",
        r"@media print",
    ),
    # TF-0235 — contrat de marquage du référentiel de restitution (famille « suivi »). Chaque
    # motif est le SEUL crochet que l oracle `oracle-restitution` sait lire : le perdre ne
    # dégraderait pas l apparence de la page, il la sortirait du périmètre contrôlé en silence.
    (
        "RL-famille-declaree",
        r'<body data-restitution="suivi">',
    ),
    (
        "RL-1-verdict",
        r'<div class="verdict" data-verdict=',
    ),
    (
        "RL-1-vues-naviguees",
        r"data-vue=",
    ),
    (
        "RL-3-kpi-complet",
        r'class="k-repere" id="repere-',
    ),
    (
        "RL-9-chemins-de-lecteur",
        r'<ul class="chemins">',
    ),
    (
        "RL-10-manifeste-ecarts",
        r'<footer class="ecarts">',
    ),
)

# Règles CONDITIONNELLES : (nom, motif attendu, motif de déclenchement). Une règle qui exige un
# marqueur que la page n'a aucune raison de porter est un faux positif — et le contrôle §2 bis,
# qui écrit une candidature TODO à chaque écart, se met à crier au loup. Constaté en recette le
# 14/08 : « H4-actions-structurees » sortait DÉRIVE sur les bancs d'essai, dont le rapport ne
# porte aucune action « à vous » — donc aucun bloc Quoi/Pourquoi à rendre.
_REGLES_CONDITIONNELLES: tuple[tuple[str, str, str], ...] = (
    (
        "H4-actions-structurees",
        r'class="a-quoi"',
        r"<strong>Vos \d+ action",
    ),
    # TF-0235 / RL-4 : une figure n existe que si la donnée existe. La règle ne se prononce
    # donc QUE sur un rapport qui a inventorié au moins un élément — sur un rapport vide,
    # exiger un graphique reviendrait à demander une courbe inventée.
    (
        "RL-4-figure-a-question",
        r'<figure class="graphe"><figcaption>[^<]+\?</figcaption>',
        r'data-total="elements"[^>]*>[1-9]',
    ),
)


def controle_pregeneration(page: str) -> list[str]:
    """Écarts du gabarit rendu vis-à-vis des règles courantes. Liste vide = conforme.

    Contrôle de PRÉSENCE (le gabarit a-t-il régressé ?), pas un oracle de rendu : les oracles
    exécutés du socle (`check_html.py`, `render_page.py`) restent la preuve de campagne. Celui-ci
    tourne à CHAQUE génération, chez l utilisateur de la forge, sans dépendance au skill.
    """
    ecarts = []
    for nom, motif in _REGLES_PREGENERATION:
        if not re.search(motif, page):
            ecarts.append(
                f"règle « {nom} » : motif attendu absent de la page rendue — le gabarit a "
                "probablement dérivé des règles du socle (BEST-PRACTICES E4/G1/H du pilot)"
            )
    for nom, motif, declencheur in _REGLES_CONDITIONNELLES:
        # La règle ne se prononce QUE si la page avait de quoi porter le marqueur.
        if re.search(declencheur, page) and not re.search(motif, page):
            ecarts.append(
                f"règle « {nom} » : la page porte le bloc attendu mais pas sa forme structurée "
                "— le gabarit a dérivé des règles du socle (BEST-PRACTICES §H du pilot)"
            )
    if re.search(r"\.wrap\s*\{[^}]*max-width:\s*\d+px", page):
        ecarts.append(
            "règle « E4-largeur » : plafond px nu sur le conteneur — interdit (75-100 % de la "
            "fenêtre, token clamp(75vw,1680px,92vw))"
        )
    ecarts.extend(_ecarts_comptes_de_table(page))
    return ecarts


def _ecarts_comptes_de_table(page: str) -> list[str]:
    """G4/G5 du composant D-12 : toute table filtrable a un `id`, et ce `id` a son compteur.

    La règle ne se déduit pas d un motif de présence : elle CROISE deux marquages, et c est
    précisément ce croisement qui manquait. Trois tables du dashboard portaient `data-filterable`
    sans qu aucun élément ne porte leur `data-tf-count-for` : le composant masquait des lignes
    sans que rien ne dise combien, et un lecteur d écran n en était pas averti du tout. Le
    contrôle vit ici pour que la forge le constate à CHAQUE génération, sans dépendre d un
    oracle externe installé sur le poste.
    """
    ecarts: list[str] = []
    for balise in re.findall(r"<table\b[^>]*\bdata-filterable(?![-=])[^>]*>", page):
        identifiant = re.search(r'\bid="([^"]+)"', balise)
        if not identifiant:
            ecarts.append(
                "règle « G4-table-identifiee » : une table `data-filterable` est rendue sans "
                "`id` — le composant ne peut ni l initialiser ni la relier à son compteur"
            )
            continue
        compteur = re.search(
            rf'<[^>]+data-tf-count-for="{re.escape(identifiant.group(1))}"[^>]*>', page
        )
        if not compteur:
            ecarts.append(
                f"règle « G5-compteur-nomme » : la table « {identifiant.group(1)} » est "
                "filtrable mais aucun élément ne porte son `data-tf-count-for` — le lecteur ne "
                "peut pas savoir combien de lignes un filtre vient de masquer"
            )
        elif 'aria-live="polite"' not in compteur.group(0):
            ecarts.append(
                f"règle « G5-compteur-nomme » : le compteur de « {identifiant.group(1)} » n est "
                'pas `aria-live="polite"` — le changement n est pas annoncé aux lecteurs d écran'
            )
    return ecarts


def ecrire(chemin: Path, page: str, cible: Path | None) -> Path:
    """Écrit la page APRÈS le garde-fou. L ordre n est pas indifférent : une page posée circule."""
    verifier_absence_de_secrets(page, cible)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(page, encoding="utf-8", newline="\n")
    return chemin
