"""Adaptateur Navigation clavier (Q4) — le pan que AUCUN oracle du parc ne couvrait.

Pourquoi ce pan existe (TF-0409, option O3). Le `non_juge` du pan accessibilite le disait mot
pour mot depuis le 20/08 : « la NAVIGATION CLAVIER, les pieges de focus et l ARIA avance ne
sont couverts par AUCUN oracle du parc a ce jour — pour un site public francais, RGAA 4.1 est
une obligation legale et cet ecart se declare au dossier MEP, il ne se tait pas ». Un ecart
declare est honnete ; il n est pas une couverture. Ce pan en mesure la part mecanisable.

Trois mesures, sur l instance SERVIE, a l etat initial de chaque route :
  K1  focus VISIBLE — chaque element atteignable au clavier change d apparence quand il prend
      le focus (RGAA 10.7, WCAG 2.4.7 AA). Mesure : styles calcules avant/apres `focus()`.
  K2  aucun PIEGE de focus — la tabulation ne reste pas prisonniere d un element (WCAG 2.1.2,
      niveau A). Mesure : tabulations REELLES, et l element actif releve a chaque pas.
  K3  lien d EVITEMENT — la premiere tabulation mene au contenu (RGAA 12.7). Mesure :
      le premier element tabulable est-il une ancre interne vers une cible existante.

Ce que ce pan ne pretend pas etre : un audit RGAA. Un tiers des criteres n est pas
mecanisable — la machine prepare l audit, elle ne rend pas la declaration. Ce qu il refuse
d etre, en revanche : un silence. Une famille sans mesure se lit « conforme » par defaut.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forge_tests import classes
from forge_tests.adaptateurs import accessibilite
from forge_tests.adaptateurs._parcours import parcourir
from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "clavier-focus", "clavier"

POUR_COUVRIR = (
    "servir le front (build présent et `npm`/navigateur disponibles) ou déclarer l'instance "
    "SERVIE dans FORGE_TESTS_BASE_URL : la navigation clavier se mesure sur une page vivante, "
    "en tabulant réellement — un DOM relu depuis un fichier ne prend pas le focus"
)

CHAPITRES = (
    {"code": "F4", "famille": "fonctionnel", "titre": "Accessibilité",
     "decoupe": "ecran", "axe_cas": "clavier"},
)

CHAMPS_REQUIS = (
    "FORGE_TESTS_BASE_URL",
    "FORGE_TESTS_LOGIN",
    "FORGE_TESTS_PASSWORD",
)

#: Bornes de mesure. Elles sont DECLAREES au rapport : une troncature muette se lit comme une
#: couverture complete — c est le defaut que TF-0382 a paye sur la liste des debordements.
MAX_ELEMENTS = 60
MAX_TABULATIONS = 80

_TABULABLES = (
    "a[href], button, input, select, textarea, summary, [tabindex], "
    "audio[controls], video[controls], [contenteditable]"
)

# Releve des tabulables et de leur apparence AU FOCUS. Tout se passe dans la page : c est la
# seule facon d obtenir les styles CALCULES, ceux que l utilisateur voit, et non ceux que la
# feuille declare.
_JS_FOCUS = """
(args) => {
  const [selecteur, maxElements] = args;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const etiquette = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
    const txt = (el.textContent || '').trim().slice(0, 30);
    return el.tagName.toLowerCase() + id + cls + (txt ? ' « ' + txt + ' »' : '');
  };
  // Empreinte d apparence : ce qui, changeant, rend un focus PERCEPTIBLE. Le contour, son
  // epaisseur, l ombre portee, la bordure, le fond et la couleur du texte — un design peut
  // signaler le focus par n importe lequel, et refuser les autres serait imposer un gout.
  const apparence = (el) => {
    const s = getComputedStyle(el);
    return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset,
            s.boxShadow, s.borderColor, s.borderWidth, s.backgroundColor,
            s.color, s.textDecorationLine].join('|');
  };
  const candidats = [...document.querySelectorAll(selecteur)]
    .filter(el => el.tabIndex >= 0 && !el.disabled && visible(el));
  const total = candidats.length;
  const examines = candidats.slice(0, maxElements);
  const sans_indicateur = [];
  const actifAvant = document.activeElement;
  for (const el of examines) {
    const avant = apparence(el);
    try { el.focus({ preventScroll: true }); } catch (e) { continue; }
    if (document.activeElement !== el) continue;   // non focusable en pratique : pas un ecart
    const apres = apparence(el);
    if (avant === apres) sans_indicateur.push(etiquette(el));
    try { el.blur(); } catch (e) { /* sans effet : l element suivant reprendra le focus */ }
  }
  try {
    if (actifAvant && actifAvant.focus) actifAvant.focus({ preventScroll: true });
  } catch (e) { /* l element d origine a disparu : sans consequence sur la mesure */ }

  // K3 — lien d evitement : la premiere tabulation mene-t-elle au contenu ?
  let evitement = null;
  if (examines.length) {
    const premier = examines[0];
    const href = premier.getAttribute && premier.getAttribute('href');
    if (premier.tagName === 'A' && href && href.startsWith('#') && href.length > 1) {
      evitement = document.querySelector(href) ? 'present' : 'cible-absente';
    } else {
      evitement = 'absent';
    }
  }
  return { total, examines: examines.length, sans_indicateur, evitement,
           premier: examines.length ? etiquette(examines[0]) : null };
}
"""

# Element actif courant, releve entre deux tabulations REELLES.
_JS_ACTIF = """
() => {
  const el = document.activeElement;
  if (!el || el === document.body) return 'body';
  const id = el.id ? '#' + el.id : '';
  const cls = (el.className && typeof el.className === 'string')
    ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
  return el.tagName.toLowerCase() + id + cls;
}
"""

NON_JUGE = [
    "clavier : mesure a l etat INITIAL de chaque route — un piege de focus qui n apparait "
    "qu apres ouverture d une modale ou d un menu n est pas atteint",
    "clavier : K1 juge qu une apparence CHANGE au focus, pas que le changement soit "
    "SUFFISAMMENT visible — le contraste de l anneau se juge en amont, au contrat de tokens "
    "(oracle-tokens T8 de forge-design) ; ici, un changement imperceptible passerait",
    "clavier : l ORDRE de tabulation (coherence avec l ordre de lecture) n est pas juge — il "
    "demande de comprendre l intention de la page, ce qu aucune mesure ne fait",
    "clavier : les raccourcis, la gestion du focus au changement de route et les regions "
    "ARIA live ne sont pas mesures",
    "clavier : l audit RGAA complet reste un livrable HUMAIN — la machine prepare l audit, "
    "elle ne rend pas la declaration",
]


def sans_objet(cible: Path) -> str | None:
    """Meme frontiere que le pan accessibilite : pas d interface, pas de clavier."""
    return accessibilite.sans_objet(cible)


def inventaire(cible: Path) -> list[Element]:
    routes, _ = accessibilite.routes_a_auditer(cible)
    return [
        Element(id=f"clavier:{route}", pan=PAN, libelle=f"navigation clavier de {route}",
                source=str(cible / "frontend"))
        for route in routes
    ]


def _mesurer(page: Any, _route: str) -> tuple[Any, str | None]:
    page.wait_for_timeout(150)
    releve = page.evaluate(_JS_FOCUS, [_TABULABLES, MAX_ELEMENTS])

    # K2 — piege de focus, mesure par tabulations REELLES : `el.focus()` en JS contourne
    # justement ce qui pourrait pieger l utilisateur (gestionnaire de touche, focus force).
    parcours: list[str] = []
    piege: str | None = None
    try:
        page.evaluate("() => document.body.focus()")
        for _ in range(min(MAX_TABULATIONS, max(4, int(releve.get("examines", 0)) * 2 + 4))):
            page.keyboard.press("Tab")
            parcours.append(str(page.evaluate(_JS_ACTIF)))
            # Trois pas d affilee sur le meme element : la tabulation n avance plus.
            if len(parcours) >= 3 and parcours[-1] == parcours[-2] == parcours[-3]:
                piege = parcours[-1]
                break
    except Exception as erreur:  # noqa: BLE001 — la route porte son motif, l audit continue
        return {**releve, "k2": None, "k2_motif": type(erreur).__name__}, None

    return {**releve, "k2": {"piege": piege, "pas": len(parcours),
                             "distincts": len(set(parcours))}}, None


def analyser(cible: Path) -> SortieAdaptateur:
    routes, provenance = accessibilite.routes_a_auditer(cible)
    if not routes:
        return accessibilite.verdict_sans_route(NOM, PAN, cible, NON_JUGE)

    resultats, motifs = parcourir(cible, routes, _mesurer, prefixe="clavier")
    socle = [
        *NON_JUGE,
        f"clavier : {len(routes)} route(s) a mesurer — provenance : "
        + (provenance or "inventaire fourni a l adaptateur"),
        f"clavier : bornes de mesure DECLAREES — {MAX_ELEMENTS} elements tabulables examines "
        f"au plus par route, {MAX_TABULATIONS} tabulations au plus (une troncature muette se "
        "lirait comme une couverture complete)",
    ]
    if not resultats and not motifs:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*socle, "front non servi : build absent, npm ou navigateur manquant"],
        )

    findings: list[Finding] = []
    non_juge = [*socle, *motifs]
    mesurees: list[str] = []
    for route, releve in resultats.items():
        if not isinstance(releve, dict):
            non_juge.append(f"clavier : route {route} — releve illisible, page non jugee")
            continue
        mesurees.append(route)
        total, examines = int(releve.get("total", 0)), int(releve.get("examines", 0))
        if total > examines:
            non_juge.append(
                f"clavier : [{route}] {total} elements tabulables, {examines} examines "
                f"(borne {MAX_ELEMENTS}) — les {total - examines} restants ne sont PAS juges"
            )
        if total == 0:
            non_juge.append(
                f"clavier : [{route}] aucun element tabulable — page sans interaction clavier, "
                "ou interface construite d elements non focusables (ce second cas est un ecart "
                "que cette mesure ne sait pas distinguer du premier)"
            )

        for quoi in releve.get("sans_indicateur", []):
            identifiant = f"clavier:K1:{route}:{str(quoi)[:40]}"
            findings.append(Finding(
                id=identifiant, classe=classes.ACCESSIBILITE, localisation=route,
                message=(f"[{route}] K1 focus INVISIBLE — {quoi} ne change pas d apparence "
                         "quand il prend le focus : un utilisateur au clavier ne sait pas ou "
                         "il est (RGAA 10.7, WCAG 2.4.7 AA)"),
                severite="bloquant",
                risque=coter(PAN, identifiant, str(cible / "frontend")),
            ))

        k2 = releve.get("k2")
        if k2 is None:
            motif_k2 = releve.get("k2_motif") or "tabulation impossible"
            non_juge.append(
                f"clavier : [{route}] K2 non mesure ({motif_k2}) — piege de focus NON juge "
                "sur cette route")
        elif k2.get("piege"):
            identifiant = f"clavier:K2:{route}"
            findings.append(Finding(
                id=identifiant, classe=classes.ACCESSIBILITE, localisation=route,
                message=(f"[{route}] K2 PIEGE de focus — la tabulation reste sur "
                         f"{k2['piege']} : l utilisateur au clavier ne peut plus sortir "
                         "(WCAG 2.1.2, niveau A)"),
                severite="bloquant",
                risque=coter(PAN, identifiant, str(cible / "frontend")),
            ))

        evitement = releve.get("evitement")
        if evitement == "absent" and total > 0:
            identifiant = f"clavier:K3:{route}"
            findings.append(Finding(
                id=identifiant, classe=classes.ACCESSIBILITE, localisation=route,
                message=(f"[{route}] K3 aucun lien d evitement — la premiere tabulation mene a "
                         f"{releve.get('premier') or 'un element quelconque'} et non au contenu ; "
                         "sur une page a navigation repetee, l utilisateur au clavier la "
                         "retraverse a chaque page (RGAA 12.7)"),
                severite="signale",
                risque=coter(PAN, identifiant, str(cible / "frontend")),
            ))
        elif evitement == "cible-absente":
            identifiant = f"clavier:K3:{route}:cible"
            findings.append(Finding(
                id=identifiant, classe=classes.ACCESSIBILITE, localisation=route,
                message=(f"[{route}] K3 lien d evitement PRESENT mais sa cible n existe pas — "
                         "une affordance inerte est pire qu absente : elle se compte conforme "
                         "et ne mene nulle part (RGAA 12.7)"),
                severite="bloquant",
                risque=coter(PAN, identifiant, str(cible / "frontend")),
            ))

    if not mesurees:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=sorted(set(non_juge)))
    non_juge.append(f"clavier : routes mesurees — {', '.join(mesurees)}")
    bloquants = [f for f in findings if f.severite == "bloquant"]
    return SortieAdaptateur(
        adaptateur=NOM, pan=PAN, cible=str(cible),
        verdict="FAIL" if bloquants else "PASS",
        findings=findings, non_juge=sorted(set(non_juge)),
    )
