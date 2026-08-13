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
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

from forge_tests.actions import CATEGORIES, ETAPES, repartition
from forge_tests.livrables import glossaire as _glossaire
from forge_tests.livrables import surface as _surface
from forge_tests.livrables.jeux import _valeurs_de_configuration

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
]


class SecretDansLeDashboard(RuntimeError):
    """Une valeur de configuration a été retrouvée dans la page. Rien n est écrit."""


# --- Totaux -----------------------------------------------------------------------------------
def totaux(rapport: dict) -> dict[str, int]:
    """Compteurs publiés par la page. Une seule définition, pour le rendu ET pour le contrôle."""
    inventaire = _surface.inventaire(rapport)
    elements = [e for liste in inventaire.values() for e in liste]
    findings = rapport.get("findings") or []
    actions = rapport.get("actions") or []
    compte = repartition(actions)
    valeurs = {
        "elements": len(elements),
        "passes": sum(1 for e in elements if e["etat"] == "exerce"),
        "echecs": len(findings),
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
    details.cas {{ margin:2px 0; }}
    details.cas summary {{ color:var(--blue); cursor:pointer; font-size:.84rem; }}
    details.cas > div {{ background:var(--bg); border:1px solid var(--line);
      border-radius:var(--r-sm); padding:10px 12px; margin-top:6px; font-size:.86rem; }}
    details.cas p {{ margin:0 0 .5em; }}
    details.cas ol {{ margin:.2em 0 .6em; padding-left:1.4em; }}
    .discret {{ color:var(--muted); font-size:.86rem; }}
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
      nav.onglets, .filtres, .theme-toggle, .outillage, .tuile-va {{ display:none; }}
      .panneau {{ display:block !important; page-break-before:always; }}
      .card, .tuile, tr {{ break-inside:avoid; page-break-inside:avoid; }}
      /* Le papier montre tout : aucun filtre écran ne masque une ligne à l impression. */
      tr[data-tf-hidden], tr[hidden] {{ display:table-row !important; }}
      @media (max-width:640px) {{ tr[data-tf-hidden], tr[hidden] {{ display:block !important; }} }}
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
      || tr.hasAttribute('data-axe-cache');
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
      if (ok) { tr.removeAttribute('data-axe-cache'); } else { tr.setAttribute('data-axe-cache', ''); }
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
  function lignesDe(bloc) {
    var tb = bloc.querySelector('table tbody');
    return tb ? Array.prototype.slice.call(tb.rows) : [];
  }
  function visible(tr) {
    return !tr.hidden && tr.style.display !== 'none' && !tr.hasAttribute('data-rech-cache');
  }
  function recompter(bloc) {
    var compte = bloc.querySelector('.outil-compte');
    if (!compte) return;
    var lignes = lignesDe(bloc), vues = 0;
    lignes.forEach(function (tr) { if (visible(tr)) vues++; });
    compte.textContent = vues + ' / ' + lignes.length + ' ligne(s) affichée(s)';
  }
  function recompterTout() {
    document.querySelectorAll('.bloc-tableau').forEach(recompter);
  }
  document.querySelectorAll('.bloc-tableau').forEach(function (bloc) {
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
          majVisibilite(tr);
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

  // À l impression navigateur, tout détail se déplie : le papier ne cache rien.
  var etatDetails = [];
  window.addEventListener('beforeprint', function () {
    etatDetails = [];
    document.querySelectorAll('details.cas').forEach(function (d) {
      etatDetails.push(d.open); d.open = true;
    });
  });
  window.addEventListener('afterprint', function () {
    document.querySelectorAll('details.cas').forEach(function (d, i) {
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
) -> str:
    """Tuile-KPI. Cliquable (bouton) dès qu une cible existe — H3 : jamais un nombre seul.

    `hors_page` : un KPI dont les éléments ne sont PAS affichés dans la page ne se rend pas
    cliquable ; il dit où ils vivent (c est son descriptif de repli).
    """
    if not libelle or not descriptif:
        libelle_g, descriptif_g = _glossaire.compteur(cle)
        libelle = libelle or libelle_g
        descriptif = descriptif or descriptif_g
    interieur = [
        f'<span class="chiffre" data-total="{cle}">{valeur}</span>',
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
    interieur.append(f'<span class="tuile-d">{_e(descriptif)}</span>')
    if hors_page:
        interieur.append(f'<span class="tuile-d">{_e(hors_page)}</span>')
        return f'<div class="tuile">{"".join(interieur)}</div>'
    if not cible and not ancre:
        return f'<div class="tuile">{"".join(interieur)}</div>'
    interieur.append('<span class="tuile-va" aria-hidden="true">→ voir la liste</span>')
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
        f'<button type="button" class="tuile"{attributs} '
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
    outille = len(lignes) >= _SEUIL_FILTRE
    tete = ""
    affiches = []
    for t in entetes:
        affiche, info = _glossaire.entete(t)
        affiches.append(affiche)
        attribut = f' aria-describedby="{_DESCRIBEDBY[t]}"' if t in _DESCRIBEDBY else ""
        attribut += f' title="{_e(info)}"' if info else ""
        attribut += ' data-tri=""' if outille else ""
        tete += f"<th{attribut}>{_e(affiche)}</th>"
    corps = ""
    for rang, ligne in enumerate(lignes):
        ouverture = f"<tr{(attributs or [''] * len(lignes))[rang]}>"
        cellules = "".join(
            f'<td data-label="{_e(affiches[i]) if i < len(affiches) else ""}">{c}</td>'
            for i, c in enumerate(ligne)
        )
        corps += ouverture + cellules + "</tr>"
    marque = f' id="{identifiant}"' if identifiant else ""
    filtrable = " data-filterable" if outille else ""
    table = (
        f'<div class="zone-tableau"><table{marque}{filtrable}><thead><tr>{tete}</tr></thead>'
        f"<tbody>{corps}</tbody></table></div>"
    )
    if not outille:
        return table
    outillage = (
        '<div class="outillage" role="search">'
        '<input type="search" class="outil-recherche" placeholder="Rechercher…" '
        'aria-label="Rechercher dans ce tableau (insensible aux accents)">'
        '<button type="button" class="outil-reinit">Réinitialiser les filtres</button>'
        f'<span class="outil-compte" aria-live="polite">{len(lignes)} / {len(lignes)} '
        "ligne(s) affichée(s)</span></div>"
    )
    return f'<div class="bloc-tableau">{outillage}{table}</div>'


# --- Synthèse par pan (R2) ----------------------------------------------------------------------
def _synthese_par_pan(chapitres: list[dict]) -> str:
    """Un bloc par chapitre (pan) : x/y passés, %, et une phrase de lecture — dérivés des
    éléments que la page rend déjà dans les onglets. Un pan non mesuré le DIT, avec sa raison.
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
                    "0",
                    "—",
                    "—",
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
        non_joues = sum(1 for e in elements if e["etat"] in ("non_exerce", "non_testable"))
        pct = round(100 * passes / total)
        badge = "b-pass" if ko == 0 and non_joues == 0 else ("b-fail" if bloquants else "b-part")
        lecture = (
            f"{passes}/{total} passés ({pct} %) — {ko} KO"
            + (f" dont {bloquants} bloquant(s)" if bloquants else "")
            + (f", {non_joues} non joué(s)" if non_joues else "")
        )
        lignes.append(
            [
                lien,
                _e(chapitre["famille"]),
                str(total),
                f"{passes} ({pct} %)",
                str(ko),
                f'<span class="badge {badge}" title="passés = éléments exercés sans constat, '
                f'rapportés aux {total} éléments du chapitre">{_e(f"{pct} % passés")}</span>',
                f'<span class="discret">{_e(lecture)}</span>',
            ]
        )
    return _tableau(
        ["chapitre (pan)", "famille", "éléments", "passés", "KO", "état", "lecture"],
        lignes,
        identifiant="table-par-pan",
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


def _tendance(rapport: dict, precedent: dict | None) -> str:
    if precedent is None:
        return (
            '<p class="discret">Aucun rapport précédent fourni — pas de tendance. '
            "Passer <code>--precedent &lt;rapport.json&gt;</code> pour l obtenir.</p>"
        )
    avant, apres = totaux(precedent), totaux(rapport)
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


# --- Détail d un cas (R11 — barre B1 : le détail à ≤ 2 clics, déplié sur place) -----------------
def _rendre_exigences_liens(liens: list[dict] | None) -> str:
    if not liens:
        return "aucune exigence rattachée (ni clé technique, ni rapprochement lexical)"
    return " · ".join(
        f"<code>{_e(lien.get('id'))}</code> ({_e(lien.get('provenance') or 'déclaré')})"
        for lien in liens
        if isinstance(lien, dict)
    )


def _detail_element(detail: dict | None) -> str:
    """Détail dépliable d un élément : ses cas dérivés (cahiers, MÊMES références stables),
    ou sa raison de non-couverture. Sans détail connu, la cellule le dit — jamais muette.
    """
    if not detail:
        return '<span class="discret">—</span>'
    if detail.get("raison"):
        return (
            '<details class="cas"><summary>non couvert — voir la raison</summary><div>'
            f"<p>{_e(detail['raison'])}</p>"
            f"<p><strong>Exigences</strong> — {_rendre_exigences_liens(detail.get('exigences'))}"
            "</p></div></details>"
        )
    morceaux = []
    for cas in detail.get("cas") or []:
        etapes = "".join(f"<li>{_e(geste)}</li>" for geste in (cas.get("etapes") or []))
        morceaux.append(
            f'<details class="cas"><summary>cas <code>{_e(cas.get("ref"))}</code> — '
            "préconditions, étapes, attendu</summary><div>"
            f"<p><strong>Préconditions</strong> — {_e(cas.get('preconditions'))}</p>"
            f"<p><strong>Jeu de données</strong> — <code>{_e(cas.get('jeu'))}</code></p>"
            f"<ol>{etapes}</ol>"
            f"<p><strong>Résultat attendu</strong> — {_texte_libre(cas.get('attendu'))}</p>"
            f"<p><strong>Exigences</strong> — {_rendre_exigences_liens(cas.get('exigences'))}"
            "</p></div></details>"
        )
    return "".join(morceaux) or '<span class="discret">—</span>'


def _constat_cellule(element: dict) -> str:
    """La colonne « constat mesuré — pourquoi » ne se tait JAMAIS (retour humain du 13/08 :
    une cellule vide est indistinguable d un bug d affichage).
    """
    message = element.get("message")
    if message:
        return _texte_libre(message)
    etat = element.get("etat")
    if etat == "exerce":
        return '<span class="discret">✓ Passé — aucun constat</span>'
    if etat == "non_exerce":
        return (
            '<span class="discret">inventorié mais jamais atteint par la suite — '
            "aucune mesure</span>"
        )
    return '<span class="discret">sans objet</span>'


def _panneau_chapitres(
    chapitres: list[dict], famille: str, details: dict[tuple[str, str], dict] | None = None
) -> str:
    details = details or {}
    morceaux: list[str] = []
    for chapitre in [c for c in chapitres if c["famille"] == famille]:
        classe = "card grise" if chapitre["grise"] else "card"
        morceaux.append(f'<section class="{classe}" id="chap-{_e(chapitre["code"])}">')
        morceaux.append(f"<h3>{_e(chapitre['code'])} — {_e(chapitre['titre'])}</h3>")
        morceaux.append(
            f'<p class="discret">pan(s) <code>{_e(", ".join(chapitre["pans"]))}</code> · '
            f"découpe par {_e(chapitre['decoupe'])} · {chapitre['elements']} élément(s) "
            f"inventorié(s), dont {chapitre['rattaches']} rattaché(s) par dérivation.</p>"
        )
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
        for sous in chapitre["sous_chapitres"]:
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
            lignes = [
                [
                    f"<code>{_e(element['id'])}</code>",
                    _badge_etat(element["etat"]),
                    _e(element.get("classe") or "")
                    or '<span class="discret" title="élément passé : aucun constat, '
                    'donc pas de type">—</span>',
                    _constat_cellule(element),
                    _e(element.get("risque"))
                    if element.get("risque") is not None
                    else '<span class="discret" title="pas de constat, donc pas de score '
                    'de risque">—</span>',
                    _detail_element(details.get((chapitre["code"], element["id"]))),
                ]
                for element in sous["elements"]
            ]
            colonnes = ["élément", "état", "classe", "constat mesuré", "risque", "détail du cas"]
            morceaux.append(_tableau(colonnes, lignes))
        morceaux.append("</section>")
    return "\n".join(morceaux) or '<p class="discret">Aucun chapitre de cette famille.</p>'


# --- Actions (R8) -------------------------------------------------------------------------------
def _synthese_actions(rapport: dict, valeurs: dict[str, int]) -> str:
    """Synthèse des suites à donner : plan de rejeu pour l IA, priorités pour l humain.

    Tout est dérivé du rapport (actions[], findings[].risque) — la page n invente aucun
    ordre : la priorité EST le risque calculé au rapport.
    """
    risques = {
        str(f.get("id")): f.get("risque")
        for f in (rapport.get("findings") or [])
        if f.get("risque") is not None
    }
    actions = rapport.get("actions") or []
    morceaux = ['<section class="card" id="synthese-actions"><h3>Que faire de cet audit ?</h3>']
    # 1. auto_ia — le plan de rejeu, borné (G-3 : jamais de boucle sans fin).
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
        morceaux.append(
            f"<p><strong>{len(auto)} action(s) automatisables par l IA</strong> "
            f"({repartition_txt}) — plan de rejeu, en <strong>boucle bornée</strong> "
            "(3 cycles maximum, garde-fou G-3) :</p>"
            "<ol>"
            "<li>appliquer les correctifs <code>auto_ia</code> par lot (la source qui fait foi "
            "dit quoi écrire — chaque cas généré reste une proposition relue) ;</li>"
            "<li>re-mesurer : <code>--reprendre &lt;rapport.json&gt;</code> rejoue l audit sur "
            "l état corrigé ;</li>"
            "<li>si des actions <code>auto_ia</code> subsistent après 3 cycles, livrer avec la "
            "liste des écarts résiduels — jamais assouplir une assertion pour « faire passer » "
            "(interdit G-2).</li>"
            "</ol>"
        )
    # 2. manuelle_utilisateur — VOS actions, triées par risque décroissant du finding source.
    votres = [a for a in actions if a.get("categorie") == "manuelle_utilisateur"]
    if votres:
        votres = sorted(
            votres,
            key=lambda a: -(risques.get(str(a.get("finding_ref")), 0) or 0),
        )
        elements = "".join(
            "<li>"
            + (
                f'<span class="badge b-fail" title="risque du constat source '
                f'(criticité × probabilité × coût)">risque {risques[str(a.get("finding_ref"))]}'
                "</span> "
                if str(a.get("finding_ref")) in risques
                else ""
            )
            + f"{_texte_libre(a.get('attendu'))} "
            f"<span class=\"discret\">(étape : {_e(_glossaire.etape_action(str(a.get('etape_cible') or '')))})</span></li>"
            for a in votres
        )
        morceaux.append(
            f"<p><strong>Vos {len(votres)} action(s)</strong> — personne d autre ne peut les "
            "faire, par priorité (risque décroissant) :</p>"
            f"<ol>{elements}</ol>"
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
    deltas = (
        {cle: valeurs[cle] - avant for cle, avant in totaux(precedent).items() if cle in valeurs}
        if precedent
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

    def pct(part: int, tout: int) -> str:
        return f"{round(100 * part / tout)} % " if tout else ""

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
        f"<p>Verdict du rapport : {_badge_verdict(str(rapport.get('verdict')))} · "
        f"rapport source <code>{_e(contexte['rapport_nom'])}</code> "
        f"(sha256, 16 premiers hex : <code>{_e(contexte['rapport_sha'][:16])}</code>).</p>",
        '<div class="grille">',
        _tuile(
            "elements",
            valeurs["elements"],
            delta=deltas.get("elements"),
            cible="synthese",
            ancre="table-par-pan",
        ),
        _tuile(
            "passes",
            valeurs["passes"],
            delta=deltas.get("passes"),
            part=pct(valeurs["passes"], valeurs["elements"]) + "des éléments",
            cible="synthese",
            ancre="table-par-pan",
        ),
        _tuile(
            "echecs",
            valeurs["echecs"],
            delta=deltas.get("echecs"),
            cible="echecs",
            ancre="table-echecs",
        ),
        _tuile(
            "echecs_bloquants",
            valeurs["echecs_bloquants"],
            delta=deltas.get("echecs_bloquants"),
            part=pct(valeurs["echecs_bloquants"], valeurs["echecs"]) + "des constats",
            cible="echecs",
            ancre="table-echecs",
            filtre_severite="bloquant",
        ),
        _tuile("non_joues", valeurs["non_joues"], delta=deltas.get("non_joues"), cible="non-joues"),
        _tuile(
            "actions",
            valeurs["actions"],
            delta=deltas.get("actions"),
            cible="actions",
            ancre="synthese-actions",
        ),
        "</div>",
        '<div class="grille">',
        _tuile(
            "non_testables",
            valeurs["non_testables"],
            cible="non-joues",
            ancre="non-testables-ici",
        ),
        _tuile(
            "pans_non_couverts",
            valeurs["pans_non_couverts"],
            cible="non-joues",
            ancre="pans-non-couverts",
        ),
        "</div>",
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
        "<h3>Tendance</h3>",
        _tendance(rapport, precedent),
    ]

    echecs = [
        "<h2>4 · Échecs — raisons mesurées</h2>",
        '<p class="discret">Chaque ligne est un constat RATTACHÉ à un élément nommé, trié '
        "par risque décroissant. Un défaut sans élément n existe pas dans ce framework.</p>",
        _tableau(
            ["risque", "sévérité", "pan", "élément", "classe", "raison mesurée", "localisation"],
            [
                [
                    _e(f.get("risque") if f.get("risque") is not None else "—"),
                    _e(f.get("severite")),
                    _e(f.get("pan")),
                    f"<code>{_e(f.get('id'))}</code>",
                    _e(f.get("classe")),
                    _texte_libre(f.get("message")),
                    f'<span class="discret">{_e(f.get("localisation"))}</span>',
                ]
                for f in (rapport.get("findings") or [])
            ],
            attributs=[
                f' data-severite="{_e(f.get("severite"))}"'
                for f in (rapport.get("findings") or [])
            ],
            identifiant="table-echecs",
        ),
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
        ),
        '<h3 id="pans-non-couverts">Pans non couverts — motif ET chemin de couverture</h3>',
        _tableau(
            ["pan", "motif", "pour couvrir"],
            [
                [_e(p.get("pan")), _e(p.get("motif")), _e(p.get("pour_couvrir"))]
                for p in (rapport.get("pans_non_couverts") or [])
                if isinstance(p, dict)
            ],
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
                _panneau_chapitres(chapitres, "fonctionnel", details),
            ],
        ),
        (
            "techniques",
            "Techniques",
            ["<h2>3 · Techniques</h2>", _panneau_chapitres(chapitres, "technique", details)],
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
        "fonctionnels": "chapitres fonctionnels dérivés de la surface, élément par élément, "
        "cas dépliables",
        "techniques": "chapitres techniques dérivés de la surface, élément par élément, "
        "cas dépliables",
        "echecs": "chaque constat rattaché à un élément nommé, trié par risque décroissant",
        "non-joues": "non testables (configuration absente) et pans non couverts, motivés",
        "actions": "synthèse des suites à donner, puis liste filtrable par catégorie et étape",
    }
    toc = "".join(
        f'<a href="#{identifiant}"><strong>{rang + 1} · {_e(libelle)}</strong> '
        f'<span class="toc-d">{_e(annonces[identifiant])}</span></a>'
        for rang, (identifiant, libelle, _) in enumerate(panneaux)
    )
    nav = "".join(
        f'<button type="button" role="tab" data-cible="{identifiant}" '
        f'aria-selected="{"true" if rang == 0 else "false"}" '
        f'aria-controls="{identifiant}">{rang + 1} · {_e(libelle)}</button>'
        for rang, (identifiant, libelle, _) in enumerate(panneaux)
    )
    # L10 du socle : un chapitre porteur d une table de ≥ 8 lignes publie un EXEMPLE DE
    # LECTURE — la première ligne déchiffrée en français, pour amorcer le parcours.
    exemples = {
        "synthese": "un pan testé, ses passés/KO en chiffres et en %, puis un seuil opposable, "
        "sa valeur, sa sévérité déclarée et l état constaté",
        "fonctionnels": "un élément nommé de l inventaire, son résultat (✓ ✕ ○), le type et la "
        "preuve de son constat éventuel, son risque, et son cas dépliable",
        "techniques": "un élément nommé de l inventaire, son résultat (✓ ✕ ○), le type et la "
        "preuve de son constat éventuel, son risque, et son cas dépliable",
        "echecs": "le constat au risque le plus élevé d abord : sa sévérité, son pan, "
        "l élément auquel il est rattaché, la raison mesurée et sa localisation",
        "non-joues": "un élément injouable ICI, les noms des champs de configuration requis "
        "(jamais leurs valeurs) et le motif",
        "actions": "une action, sa catégorie ternaire, l étape cible où la jouer et le "
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
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
<header class="doc">
  <p class="eyebrow">Digit-AI · Forge Tests · Dashboard d exécution</p>
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
</div>
<script>{_SCRIPT}</script>
<script>/* Composant filtres du socle — asset du skill installé ou copie D-12 du dépôt. */
{_composant_filtres()}</script>
<script>/* Initialisation D-12 : l API n auto-démarre pas — sans cet appel, les filtres de
   colonne n existent pas (affordance morte constatée sur le dashboard BAV2 du 13/08). */
if (window.DigitAITableFilters) {{ DigitAITableFilters.initAll(); }}</script>
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
        r'<button type="button" class="tuile"',
    ),
    (
        "print-clair-force",
        r"@media print",
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
    if re.search(r"\.wrap\s*\{[^}]*max-width:\s*\d+px", page):
        ecarts.append(
            "règle « E4-largeur » : plafond px nu sur le conteneur — interdit (75-100 % de la "
            "fenêtre, token clamp(75vw,1680px,92vw))"
        )
    return ecarts


def ecrire(chemin: Path, page: str, cible: Path | None) -> Path:
    """Écrit la page APRÈS le garde-fou. L ordre n est pas indifférent : une page posée circule."""
    verifier_absence_de_secrets(page, cible)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(page, encoding="utf-8", newline="\n")
    return chemin
