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


_STYLE = """
    :root {
      --blue:#2563EB; --bg:#FAFBFF; --surface:#FFFFFF; --card:#FFFFFF;
      --ink:#0F172A; --muted:#64748B; --faint:#94A3B8; --line:#E6EAF2;
      --amber:#D97706; --amber-fill:#FFFBEB; --amber-line:#FDE9C8;
      --teal:#0E9488; --teal-fill:#EFFDFB; --teal-line:#C7F0EA;
      --green:#15803D; --green-fill:#F2FCF5; --green-line:#CFEEDD;
      --red:#B91C1C; --red-fill:#FEF2F2; --red-line:#FBD5D5;
      /* Encres des pastilles. Le ton d accent de la charte sert aux FILETS ; posé en TEXTE sur
         son propre fond pâle, l ambre tombe à 3,07:1 — sous les 4,5:1 de WCAG AA, mesuré par
         `render_page.py`. Un statut illisible est un statut qu on ne lit pas : la pastille a
         donc son encre propre, foncée, et le ton d accent reste à la bordure. */
      --amber-ink:#92400E; --teal-ink:#115E59; --green-ink:#14532D; --red-ink:#991B1B;
      --r:12px; --r-sm:8px;
      --head:"Roboto", system-ui, -apple-system, "Segoe UI", sans-serif;
      --sans:"DM Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
      --mono:"JetBrains Mono", ui-monospace, "Consolas", monospace;
    }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="clair"]) {
        --bg:#0B1120; --surface:#131C2E; --card:#131C2E; --ink:#E8EDF7; --muted:#9BA9C0;
        --faint:#6B7A93; --line:#25324A; --amber-fill:#2A2113; --amber-line:#4A3A1A;
        --teal-fill:#0E2A28; --teal-line:#1C4A46; --green-fill:#0F2A1B; --green-line:#1D4A2F;
        --red-fill:#2C1414; --red-line:#5A2222; --blue:#7CA6FF; --green:#4ADE80;
        --amber:#FBBF24; --red:#F87171; --teal:#5EEAD4;
        --amber-ink:#FBBF24; --teal-ink:#5EEAD4; --green-ink:#4ADE80; --red-ink:#F87171;
      }
    }
    :root[data-theme="sombre"] {
      --bg:#0B1120; --surface:#131C2E; --card:#131C2E; --ink:#E8EDF7; --muted:#9BA9C0;
      --faint:#6B7A93; --line:#25324A; --amber-fill:#2A2113; --amber-line:#4A3A1A;
      --teal-fill:#0E2A28; --teal-line:#1C4A46; --green-fill:#0F2A1B; --green-line:#1D4A2F;
      --red-fill:#2C1414; --red-line:#5A2222; --blue:#7CA6FF; --green:#4ADE80;
      --amber:#FBBF24; --red:#F87171; --teal:#5EEAD4;
    }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
           line-height:1.55; font-size:16px; }
    .wrap { max-width:1180px; margin:0 auto; padding:32px 24px 64px; }
    h1,h2,h3,h4 { font-family:var(--head); font-weight:800; color:var(--ink); line-height:1.2; }
    h1 { font-size:2rem; margin:0 0 .25em; }
    h2 { font-size:1.4rem; font-weight:700; margin:0 0 .6em; }
    h3 { font-size:1.1rem; font-weight:700; margin:1.6em 0 .4em; }
    h4 { font-size:1rem; font-weight:700; margin:1.2em 0 .3em; color:var(--muted); }
    p { margin:0 0 1em; }
    a { color:var(--blue); }
    code, pre { font-family:var(--mono); font-size:.86em; }
    header.doc { border-bottom:2px solid var(--blue); padding-bottom:16px; margin-bottom:20px; }
    .eyebrow { color:var(--muted); font-size:.85rem; letter-spacing:.04em;
               text-transform:uppercase; margin:0 0 .3em; }
    .card { background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
            padding:18px 22px; margin:16px 0; }
    .grille { display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }
    .tuile { flex:1 1 150px; background:var(--surface); border:1px solid var(--line);
             border-radius:var(--r); padding:14px 16px; }
    .tuile .chiffre { font-family:var(--head); font-size:1.9rem; font-weight:900;
                      display:block; line-height:1.1; }
    .tuile .quoi { color:var(--muted); font-size:.82rem; text-transform:uppercase;
                   letter-spacing:.03em; }
    .badge { display:inline-block; border-radius:999px; padding:2px 11px; font-size:.8rem;
             font-weight:700; border:1px solid var(--line); }
    .b-pass { background:var(--green-fill); border-color:var(--green-line);
              color:var(--green-ink); }
    .b-fail { background:var(--red-fill); border-color:var(--red-line); color:var(--red-ink); }
    .b-part { background:var(--amber-fill); border-color:var(--amber-line);
              color:var(--amber-ink); }
    .b-info { background:var(--teal-fill); border-color:var(--teal-line);
              color:var(--teal-ink); }
    nav.toc { display:flex; flex-wrap:wrap; gap:4px 18px; margin:0 0 12px; font-size:.85rem; }
    nav.toc a { color:var(--blue); text-decoration:none; }
    nav.toc a:hover { text-decoration:underline; }
    nav.toc .toc-d { color:var(--muted); }
    nav.onglets { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 20px;
                  border-bottom:1px solid var(--line); }
    nav.onglets button { font-family:var(--sans); font-size:.95rem; font-weight:600;
      background:transparent; color:var(--muted); border:1px solid transparent;
      border-bottom:none; border-radius:var(--r-sm) var(--r-sm) 0 0; padding:9px 15px;
      cursor:pointer; }
    nav.onglets button[aria-selected="true"] { background:var(--surface); color:var(--ink);
      border-color:var(--line); }
    .zone-tableau { overflow-x:auto; }
    table { border-collapse:collapse; width:100%; font-size:.88rem; table-layout:fixed; }
    th, td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line);
             vertical-align:top; overflow-wrap:anywhere; }
    th { font-family:var(--head); font-size:.78rem; text-transform:uppercase;
         letter-spacing:.03em; color:var(--muted); }
    .grise { opacity:.72; border-style:dashed; }
    .filtres { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px; }
    .filtres button { font-family:var(--sans); font-size:.85rem; border:1px solid var(--line);
      background:var(--surface); color:var(--ink); border-radius:999px; padding:5px 13px;
      cursor:pointer; }
    .filtres button[aria-pressed="true"] { background:var(--blue); color:#fff;
      border-color:var(--blue); }
    .discret { color:var(--muted); font-size:.86rem; }
    footer.doc { margin-top:44px; padding-top:14px; border-top:1px solid var(--line);
                 color:var(--muted); font-size:.85rem; }
    /* Sur mobile, un tableau à sept colonnes ne « défile » pas : il sort de l écran et le
       lecteur ne sait pas qu il manque quelque chose. Les lignes se replient donc en blocs,
       chaque cellule reprenant son intitulé de colonne (`data-label`). Rien n est masqué —
       c est la seule mise en page qui tienne la promesse « aucune absence silencieuse »
       jusque dans le rendu. Mesuré : sans cela, V1 sort douze débordements à 390 px. */
    @media (max-width:640px) {
      .wrap { padding:22px 14px 44px; }
      h1 { font-size:1.5rem; }
      table, thead, tbody, tr, th, td { display:block; width:auto; }
      thead { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }
      tr { border:1px solid var(--line); border-radius:var(--r-sm); margin:0 0 10px;
           padding:6px 8px; }
      td { border:none; padding:3px 0; }
      td::before { content:attr(data-label) " · "; color:var(--muted); font-size:.76rem;
                   text-transform:uppercase; letter-spacing:.03em; }
      td:empty { display:none; }
    }
    @page { size:A4 landscape; margin:14mm; }
    @media print {
      body { background:#FFFFFF; }
      .wrap { max-width:none; padding:0; }
      nav.onglets, .filtres, #bascule-theme { display:none; }
      .panneau { display:block !important; page-break-before:always; }
      .card, .tuile, tr { break-inside:avoid; page-break-inside:avoid; }
    }
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

  var filtres = document.querySelectorAll('.filtres button');
  filtres.forEach(function (b) {
    b.addEventListener('click', function () {
      var actif = b.getAttribute('aria-pressed') === 'true';
      filtres.forEach(function (a) {
        if (a.dataset.axe === b.dataset.axe) { a.setAttribute('aria-pressed', 'false'); }
      });
      b.setAttribute('aria-pressed', actif ? 'false' : 'true');
      var choix = {};
      document.querySelectorAll('.filtres button[aria-pressed="true"]').forEach(function (a) {
        choix[a.dataset.axe] = a.dataset.valeur;
      });
      document.querySelectorAll('#table-actions tbody tr').forEach(function (tr) {
        var visible = Object.keys(choix).every(function (axe) {
          return tr.dataset[axe] === choix[axe];
        });
        tr.hidden = !visible;
      });
    });
  });

  // Sommaire → onglets : une ancre vers un panneau masqué serait morte ; le clic bascule.
  document.querySelectorAll('nav.toc a').forEach(function (a) {
    a.addEventListener('click', function () { montrer(a.getAttribute('href').slice(1)); });
  });

  var bascule = document.getElementById('bascule-theme');
  if (bascule) {
    bascule.addEventListener('click', function () {
      var racine = document.documentElement;
      var sombre = racine.getAttribute('data-theme') === 'sombre';
      racine.setAttribute('data-theme', sombre ? 'clair' : 'sombre');
      bascule.textContent = sombre ? 'Thème sombre' : 'Thème clair';
    });
  }
})();
"""


def _tuile(cle: str, valeur: int, quoi: str) -> str:
    return (
        f'<div class="tuile"><span class="chiffre" data-total="{cle}">{valeur}</span>'
        f'<span class="quoi">{_e(quoi)}</span></div>'
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
    """
    if not lignes:
        return '<p class="discret">Aucune entrée.</p>'
    tete = ""
    for t in entetes:
        attribut = f' aria-describedby="{_DESCRIBEDBY[t]}"' if t in _DESCRIBEDBY else ""
        tete += f"<th{attribut}>{_e(t)}</th>"
    corps = ""
    for rang, ligne in enumerate(lignes):
        ouverture = f"<tr{(attributs or [''] * len(lignes))[rang]}>"
        cellules = "".join(
            f'<td data-label="{_e(entetes[i]) if i < len(entetes) else ""}">{c}</td>'
            for i, c in enumerate(ligne)
        )
        corps += ouverture + cellules + "</tr>"
    marque = f' id="{identifiant}"' if identifiant else ""
    filtrable = " data-filterable" if len(lignes) >= _SEUIL_FILTRE else ""
    return (
        f'<div class="zone-tableau"><table{marque}{filtrable}><thead><tr>{tete}</tr></thead>'
        f"<tbody>{corps}</tbody></table></div>"
    )


def _etat_des_seuils(rapport: dict) -> list[list[str]]:
    """Seuil par seuil : valeur, sévérité, et état DÉRIVÉ des findings qui citent sa valeur."""
    constats = [
        f for f in (rapport.get("findings") or []) if f.get("classe") == "seuil-non-tenu"
    ]
    lignes = []
    for nom, detail in sorted((rapport.get("seuils") or {}).items()):
        valeur = float(detail.get("valeur") or 0)
        cite = [f for f in constats if f"seuil {valeur:.0%}" in str(f.get("message") or "")]
        if cite:
            etat = (
                f'<span class="badge b-fail" title="{len(cite)} finding(s) seuil-non-tenu '
                f'citent la valeur de ce seuil">non tenu — {len(cite)} constat(s)</span>'
            )
        else:
            etat = (
                '<span class="badge b-pass" title="aucun finding seuil-non-tenu ne cite '
                'la valeur de ce seuil">aucun constat contraire</span>'
            )
        lignes.append(
            [
                f"<code>{_e(nom)}</code>",
                f"{valeur:.0%}",
                _e(detail.get("severite")),
                etat,
                f'<span class="discret">{_e(detail.get("porte_sur"))}</span>',
            ]
        )
    return lignes


def _tendance(rapport: dict, precedent: dict | None) -> str:
    if precedent is None:
        return (
            '<p class="discret">Aucun rapport précédent fourni — pas de tendance. '
            "Passer <code>--precedent &lt;rapport.json&gt;</code> pour l obtenir.</p>"
        )
    avant, apres = totaux(precedent), totaux(rapport)
    lignes = []
    for cle in ("elements", "passes", "echecs", "echecs_bloquants", "non_joues", "actions"):
        ecart = apres[cle] - avant[cle]
        # Un écart n est « bon » ou « mauvais » que selon ce qu il compte : plus d éléments
        # exercés est un progrès, plus d échecs ne l est pas. Le sens est déclaré, pas deviné.
        favorable = ecart > 0 if cle in ("elements", "passes") else ecart < 0
        classe = "b-info" if ecart == 0 else ("b-pass" if favorable else "b-fail")
        signe = f"{ecart:+d}" if ecart else "="
        lignes.append(
            [
                _e(cle),
                str(avant[cle]),
                str(apres[cle]),
                f'<span class="badge {classe}">{signe}</span>',
            ]
        )
    return _tableau(["compteur", "rapport précédent", "ce rapport", "écart"], lignes)


def _panneau_chapitres(chapitres: list[dict], famille: str) -> str:
    morceaux: list[str] = []
    for chapitre in [c for c in chapitres if c["famille"] == famille]:
        classe = "card grise" if chapitre["grise"] else "card"
        morceaux.append(f'<section class="{classe}">')
        morceaux.append(f"<h3>{_e(chapitre['code'])} — {_e(chapitre['titre'])}</h3>")
        morceaux.append(
            f'<p class="discret">pan(s) <code>{_e(", ".join(chapitre["pans"]))}</code> · '
            f"découpe par {_e(chapitre['decoupe'])} · {chapitre['elements']} élément(s) "
            f"inventorié(s), dont {chapitre['rattaches']} rattaché(s) par dérivation.</p>"
        )
        for manquant in chapitre.get("pans_non_couverts") or []:
            morceaux.append(
                f'<p><span class="badge b-part">pan non couvert</span> '
                f"<strong>{_e(manquant.get('pan'))}</strong> — {_e(manquant.get('motif'))}<br>"
                f"<span class=\"note\">Pour couvrir : {_e(manquant.get('pour_couvrir'))}</span></p>"
            )
        if chapitre["grise"]:
            morceaux.append(
                '<p class="discret">Chapitre <strong>non mesuré</strong> : aucun élément '
                "inventorié. Il reste affiché — un chapitre absent laisserait croire que "
                "le sujet n existe pas dans le produit.</p>"
            )
        for sous in chapitre["sous_chapitres"]:
            morceaux.append(f"<h4>{_e(sous['libelle'])} — {len(sous['elements'])} élément(s)</h4>")
            lignes = [
                [
                    f"<code>{_e(element['id'])}</code>",
                    _e(element["etat"]),
                    _e(element.get("classe") or ""),
                    _texte_libre(element.get("message") or ""),
                    _e(element.get("risque") if element.get("risque") is not None else "—"),
                ]
                for element in sous["elements"]
            ]
            colonnes = ["élément", "état", "classe", "constat mesuré", "risque"]
            morceaux.append(_tableau(colonnes, lignes))
        morceaux.append("</section>")
    return "\n".join(morceaux) or '<p class="discret">Aucun chapitre de cette famille.</p>'


def _composant_filtres() -> str:
    """Composant filtres du socle : asset du skill installé, sinon la copie D-12 du dépôt."""
    skill = (
        Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "assets" / "table-filters.js"
    )
    source = skill if skill.exists() else Path(__file__).with_name("table-filters.js")
    return source.read_text(encoding="utf-8")


def construire(
    rapport: dict, contexte: dict, chapitres: list[dict], precedent: dict | None = None
) -> str:
    """Page complète. `chapitres` vient de `surface.repartir` — dérivé, jamais écrit en dur."""
    valeurs = totaux(rapport)
    titre = f"{contexte['produit']} — Dashboard tests — {contexte['date']}"

    synthese = [
        "<h2>1 · Synthèse</h2>",
        '<p id="note-severite" class="discret">« sévérité » = classe déclarée par la règle qui a '
        "produit le constat (bloquant · majeur · mineur) — barème porté par le rapport, "
        "jamais recalculé par la page.</p>",
        '<p id="note-risque" class="discret">« risque » = score du rapport '
        "(criticité × probabilité × coût tardif, notes 1-5) — calcul de "
        "<code>forge_tests.noyau.score_risque</code>, la page ne fait que le rendre.</p>",
        f"<p>Verdict du rapport : {_badge_verdict(str(rapport.get('verdict')))} · "
        f"rapport source <code>{_e(contexte['rapport_nom'])}</code> "
        f"(sha256, 16 premiers hex : <code>{_e(contexte['rapport_sha'][:16])}</code>).</p>",
        '<div class="grille">',
        _tuile("elements", valeurs["elements"], "éléments inventoriés"),
        _tuile("passes", valeurs["passes"], "passés (exercés)"),
        _tuile("echecs", valeurs["echecs"], "échecs (constats)"),
        _tuile("echecs_bloquants", valeurs["echecs_bloquants"], "dont bloquants"),
        _tuile("non_joues", valeurs["non_joues"], "non joués"),
        _tuile("actions", valeurs["actions"], "actions"),
        "</div>",
        '<div class="grille">',
        _tuile("non_testables", valeurs["non_testables"], "non testables ici"),
        _tuile("pans_non_couverts", valeurs["pans_non_couverts"], "pans non couverts"),
        "</div>",
        "<h3>Seuils opposables et leur état</h3>",
        _tableau(
            ["seuil", "valeur", "sévérité", "état constaté", "porte sur"],
            _etat_des_seuils(rapport),
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
        ),
    ]

    non_joues = [
        "<h2>5 · Non joués</h2>",
        "<h3>Non testables ici — configuration absente</h3>",
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
        "<h3>Pans non couverts — motif ET chemin de couverture</h3>",
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
            boutons.append(
                f'<button type="button" data-axe="{axe}" data-valeur="{_e(valeur)}" '
                f'aria-pressed="false">{_e(valeur)}</button>'
            )
    descriptions_categories = {
        "ia": "corrigeable par l IA dans la boucle de fermeture",
        "manuelle_dev": "geste manuel côté développement",
        "manuelle_utilisateur": "décision ou geste attendu de l utilisateur",
    }
    lignes_actions, attributs_actions = [], []
    for action in rapport.get("actions") or []:
        categorie = str(action.get("categorie") or "")
        legende = descriptions_categories.get(categorie, f"catégorie {categorie}")
        lignes_actions.append(
            [
                f"<code>{_e(action.get('finding_ref'))}</code>",
                f'<span class="badge b-info" title="{_e(legende)}">{_e(categorie)}</span>',
                _e(action.get("etape_cible")),
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
        '<div class="grille">',
        *[
            _tuile(f"actions_{c}", valeurs[f"actions_{c}"], c.replace("_", " "))
            for c in CATEGORIES
        ],
        "</div>",
        '<div class="grille">',
        *[
            _tuile(
                f"etape_{etape.replace('-', '_')}",
                valeurs[f"etape_{etape.replace('-', '_')}"],
                f"étape {etape}",
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
            ["<h2>2 · Fonctionnels</h2>", _panneau_chapitres(chapitres, "fonctionnel")],
        ),
        (
            "techniques",
            "Techniques",
            ["<h2>3 · Techniques</h2>", _panneau_chapitres(chapitres, "technique")],
        ),
        ("echecs", "Échecs", echecs),
        ("non-joues", "Non joués", non_joues),
        ("actions", "Actions", actions_html),
    ]
    # Sommaire réel (L6 du socle) : chaque entrée ANNONCE ce qu on va y trouver (.toc-d) et
    # chaque panneau ouvre par un chapeau (.ch-apprend, L7). Le clic bascule l onglet — une
    # ancre vers un panneau masqué serait une affordance morte.
    annonces = {
        "synthese": "verdict, totaux republiés, état des seuils opposables et tendance",
        "fonctionnels": "chapitres fonctionnels dérivés de la surface, élément par élément",
        "techniques": "chapitres techniques dérivés de la surface, élément par élément",
        "echecs": "chaque constat rattaché à un élément nommé, trié par risque décroissant",
        "non-joues": "non testables (configuration absente) et pans non couverts, motivés",
        "actions": "classification ternaire des actions, filtrable par catégorie et étape",
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
        "synthese": "un seuil opposable, sa valeur, sa sévérité déclarée et l état constaté "
        "dérivé des findings qui le citent",
        "fonctionnels": "un élément nommé de l inventaire, son état mesuré, la classe de son "
        "constat éventuel et son risque",
        "techniques": "un élément nommé de l inventaire, son état mesuré, la classe de son "
        "constat éventuel et son risque",
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
     <button type="button" id="bascule-theme">Thème sombre</button></p>
</header>
<nav class="toc" aria-label="Sommaire">{toc}</nav>
<nav class="onglets" role="tablist">{nav}</nav>
<main>{corps}</main>
<footer class="doc">
  Digit-AI — Forge Tests · {_e(contexte['produit'])} · dashboard dérivé du rapport, sans
  recalcul : tout chiffre se conteste sur le rapport JSON. Aucune valeur d environnement
  n entre dans cette page.
</footer>
</div>
<script>{_SCRIPT}</script>
<script>/* Composant filtres du socle — asset du skill installé ou copie D-12 du dépôt. */
{_composant_filtres()}</script>
</body>
</html>
"""


def ecrire(chemin: Path, page: str, cible: Path | None) -> Path:
    """Écrit la page APRÈS le garde-fou. L ordre n est pas indifférent : une page posée circule."""
    verifier_absence_de_secrets(page, cible)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(page, encoding="utf-8", newline="\n")
    return chemin
