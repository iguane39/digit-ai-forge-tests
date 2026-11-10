"""Attendre la stabilité des animations FINIES avant de juger un rendu (TF-2313).

Le fait (Produit-84, 09/11/2026, chaîne de dev 42686921354, onglet dashboard) : axe-core a rendu un
contraste de 1,53 sur un toast de 12 px, mesuré au milieu de son fondu de 0,25 s ; affiché, il tient
7,16:1 (calculé). Le même banc passait sur le poste. En attendant la fin des animations finies
(`document.getAnimations()`, `iterations` infini ignoré), les 24 contrôles passaient sur le poste et
sur la chaîne 42688833213.

Une couleur calculée pendant une transition CSS est un état intermédiaire : le contraste mesuré dit
l'image prise, pas la page. Ce module attend que toutes les animations et transitions FINIES soient
terminées, 5 s au plus, avant que le pan lise le rendu ; il rend ce qu'il a vu, pour que le pan
DISE quand le plafond a été atteint (une animation de 8 s jugée à 5 s n'est pas une page stable).

Ce que le module ne fait pas : attendre une animation sans fin (spinner, marquee, pulsation), qui
n'a pas d'état final à attendre ; elle est comptée et nommée, jamais attendue. Une animation en
pause (`paused`) n'est pas attendue non plus : elle ne finira pas d'elle-même.
"""

from __future__ import annotations

from typing import Any

#: Plafond d'attente, en millisecondes : au-delà, le pan juge ce qu'il voit et le dit.
PLAFOND_MS = 5000

#: Exécuté dans la page. Boucle tant qu'une animation FINIE est en cours : une animation qui se
#: termine peut en déclencher une autre (chaîne de transitions), un seul `await` ne suffit pas. Une
#: fois la page calme, deux images de plus laissent naître la transition que la FIN de la précédente
#: déclenche (`transitionend` puis recalcul de style) avant de conclure.
_SCRIPT = """
async (plafond) => {
  const debut = performance.now();
  const finie = (a) => {
    const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : null;
    return t !== null && t.iterations !== Infinity && Number.isFinite(t.endTime);
  };
  const en_cours = () => document.getAnimations().filter(
    (a) => finie(a) && (a.playState === 'running' || a.pending)
  );
  const images = () => new Promise((resolve) => {
    const garde = setTimeout(resolve, 150);
    requestAnimationFrame(() => requestAnimationFrame(() => { clearTimeout(garde); resolve(); }));
  });
  while (performance.now() - debut < plafond) {
    if (en_cours().length === 0) {
      await images();
      if (en_cours().length === 0) break;
      continue;
    }
    const reste = plafond - (performance.now() - debut);
    await Promise.race([
      Promise.allSettled(en_cours().map((a) => a.finished)),
      new Promise((resolve) => setTimeout(resolve, reste)),
    ]);
  }
  const infinies = document.getAnimations().filter(
    (a) => !finie(a) && a.playState === 'running'
  ).length;
  return {
    restantes: en_cours().length,
    infinies: infinies,
    ms: Math.round(performance.now() - debut),
  };
}
"""


def attendre_animations_finies(page: Any, plafond_ms: int | None = None) -> dict:
    """Attend la fin des animations finies de `page`, `plafond_ms` au plus, et rend le constat.

    `{"stable": bool, "restantes": int, "infinies": int, "ms": int, "plafond": int}` : `stable` est
    faux quand le plafond est atteint avec des animations finies encore en cours. Ne lève JAMAIS :
    une page qui ne répond pas à l'évaluation rend `{"stable": None, ...}` et le pan juge sans
    cette garantie.
    """
    plafond = PLAFOND_MS if plafond_ms is None else plafond_ms
    try:
        brut = page.evaluate(_SCRIPT, plafond)
        return {
            "stable": int(brut["restantes"]) == 0, "restantes": int(brut["restantes"]),
            "infinies": int(brut["infinies"]), "ms": int(brut["ms"]), "plafond": plafond,
        }
    except Exception as erreur:  # noqa: BLE001 — l'attente ne doit jamais emporter la mesure
        return {"stable": None, "restantes": 0, "infinies": 0, "ms": 0, "plafond": plafond,
                "erreur": type(erreur).__name__}


def note_si_instable(constat: dict, pan: str, route: str) -> str | None:
    """La ligne de non-jugé quand la page n'a PAS été vue stable, ou None si elle l'était."""
    if constat.get("stable") is False:
        return (
            f"{pan} : route {route} jugée alors que {constat['restantes']} animation(s) finie(s) "
            f"duraient encore après {constat['ms']} ms d'attente (plafond {constat['plafond']} "
            "ms) — le rendu lu peut être un état intermédiaire"
        )
    if constat.get("stable") is None:
        return (
            f"{pan} : route {route} — la stabilité des animations n'a pas pu être vérifiée "
            f"({constat.get('erreur', 'évaluation impossible')})"
        )
    return None
