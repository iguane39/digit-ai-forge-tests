"""TF-0138 — payé en réel sur ce poste le 12/08, découvert en instruisant TF-0137.

Depuis que `fixtures/banc-rouge` et `fixtures/banc-vert` servent chacun sur leur port dédié
(41733/41743, TF-0137) au lieu du 4173 partagé, `recette --section corpus` faisait apparaître
26 findings BLOQUANTS sur le banc VERT — le témoin PROPRE, censé n'en produire aucun.

Cause racine PROUVÉE par observation (`FORGE_TESTS_PLAYWRIGHT_TRACE=on` forcé en ligne de
commande sur `fixtures/banc-vert`) : la suite e2e est VERTE de bout en bout et exerce 25/25
éléments (100 %) — ce n'est pas la suite qui manque de couverture. Le vrai coupable est
`front.playwright.config.js` des DEUX bancs, qui porte `use: { trace: "off" }` depuis leur
création (avant même TF-0132) : `_mode_trace` (TF-0132) respecte désormais ce choix EXPLICITE
du projet et ne passe plus `--trace on` en CLI — ce qui est le comportement VOULU pour un vrai
client. Mais `front_execute`, côté SUCCÈS (code 0), ne vérifiait pas si la trace avait
seulement été SOLLICITÉE avant de scanner les archives : sans trace, la boucle sur les
`trace.zip` ne trouve jamais rien et renvoie `{"routes": [], "testids": []}` — un ensemble VIDE,
indiscernable pour l appelant d une suite qui n exerce RÉELLEMENT rien. `evaluer_surface`
transforme alors cette absence de mesure en un vrai FAIL « 0 % sous le seuil 90 % ».

Deux volets, comme pour TF-0132/0136 :
  (a) DÉFAUT DU PAN corrigé : `front_execute` déclare désormais explicitement la couverture
      NON MESURABLE (comme il le fait déjà côté échec, TF-0132b) dès que `mode_effectif != "on"`
      sur le chemin SUCCÈS — jamais une couverture nulle sur une suite verte ;
  (b) DÉFAUT DE LA RECETTE corrigé : `recette/verifier_corpus.py::analyser_servi` force
      `FORGE_TESTS_PLAYWRIGHT_TRACE=on` (scopé au temps de l analyse, `finally` comme
      `FORGE_TESTS_QUALIF_URL`) — sans quoi la recette elle-même perdrait la capacité de
      CONSTATER D-01 (parcours front tronqué du banc rouge) ET de prouver que le banc vert est
      exercé à 100 %, se contentant d un silence non mesurable des deux côtés. Portée
      volontairement scopée à la fonction (pas un réglage au niveau du module) : un réglage
      global aurait fui vers tout autre test import ant `recette.verifier_corpus`
      (`tests/test_tf_0116.py`, `tests/test_tf_0136.py`) et cassé silencieusement les tests de
      TF-0132 qui vérifient précisément l ABSENCE de cette variable.

Témoin discriminant conservé : `test_code_non_nul_en_mode_off_reste_une_suite_rouge_sans_ambiguite`
(TF-0132) prouve que ce garde ne s applique qu au chemin SUCCÈS — un code non nul reste jugé par
la logique TF-0132b existante, jamais requalifié en NON MESURABLE par ce correctif.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from forge_tests import execution


def _projet_front(tmp_path: Path, config_trace: str | None = None) -> Path:
    front = tmp_path / "frontend"
    (front / "node_modules").mkdir(parents=True)
    contenu = "export default {};\n"
    if config_trace is not None:
        contenu = f'export default {{ use: {{ trace: "{config_trace}" }} }};\n'
    (front / "playwright.config.ts").write_text(contenu, encoding="utf-8")
    return front


def test_succes_avec_trace_desactivee_par_le_projet_est_non_mesurable_pas_nulle(
    tmp_path: Path, monkeypatch
) -> None:
    """Le cas RÉEL constaté sur `fixtures/banc-vert` : mode `off` choisi par le PROJET, code de
    sortie 0 (suite entièrement verte) — la couverture ne doit être ni PASS à tort, ni FAIL à
    tort, mais explicitement déclarée NON MESURABLE.

    ROUGE implicite : avant le correctif, ce cas renvoyait `{"routes": [], "testids": []}`,
    qu `evaluer_surface` traduisait en « couverture de surface 0 % sous le seuil 90 % » —
    26 findings bloquants sur un banc dont la suite passe 100 %.
    """
    _projet_front(tmp_path, config_trace="off")
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(
        execution,
        "_run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="25 passed", stderr=""
        ),
    )
    execution.front_execute.cache_clear()

    mesure = execution.front_execute(str(tmp_path))

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "non mesurable" in motif.lower()
    assert "verte" in motif.lower() or "code 0" in motif.lower()
    assert "0 %" not in motif


def test_succes_avec_trace_on_reste_mesure_normalement(
    tmp_path: Path, monkeypatch
) -> None:
    """Témoin discriminant : le garde ne s active QUE quand la trace n a pas été sollicitée —
    en mode `on` (défaut de la forge), un succès sans `trace.zip` reste ce qu il a toujours été
    (aucun test n a réellement manipulé d élément avec `data-testid`, ensemble vide légitime),
    ce correctif ne doit rien y changer."""
    _projet_front(tmp_path)  # pas de config_trace -> mode par défaut "on"
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(
        execution,
        "_run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="3 passed", stderr=""
        ),
    )
    execution.front_execute.cache_clear()

    mesure = execution.front_execute(str(tmp_path))

    # Mode "on" : le garde TF-0138 ne se déclenche pas, la mesure (vide ici, aucun trace.zip
    # écrit par le stub) reste un résultat MESURÉ, pas une non-mesure déclarée.
    assert mesure == {"routes": [], "testids": []}
