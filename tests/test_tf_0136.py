"""TF-0136 — payé en réel sur ce poste le 12/08.

`recette/verifier_corpus.py --section corpus` échouait sur D-01 (pan front) : la suite e2e de
`fixtures/banc-rouge` n'atteignait jamais `getByTestId('lien-connexion')`, alors que ce testid
existe bel et bien dans la source, dans `frontend/dist/` et dans `.visuel/racine.html`.
Reproduit à l'identique avant ET après les correctifs TF-0132/0135 (git stash) : défaut
préexistant, sans lien avec eux.

Cause racine PROUVÉE par observation : un serveur `vite preview` d'un projet totalement
étranger (`C:\\dev\\_Client-A\\Approval2\\frontend`) écoutait déjà sur le port 4173 — le port que
`fixtures/banc-rouge/frontend/playwright.config.js` et `fixtures/banc-vert/...` codent en dur,
avec `webServer.reuseExistingServer: true`. Playwright constate que quelque chose répond déjà
sur l URL configurée et s'abstient de démarrer SON PROPRE serveur : la suite e2e du banc
s'exécute alors, en silence, contre la page d'accueil d'un produit sans le moindre rapport avec
elle (`curl http://127.0.0.1:4173/` renvoyait `<title>Approval</title>`) — d'où l'absence de
`lien-connexion`, qui n'a jamais existé sur cette page.

Deux volets, comme pour TF-0132 :
  (a) DÉFAUT CORRIGEABLE du banc : `reuseExistingServer: true` → `false` dans les deux fixtures
      — Playwright démarre alors TOUJOURS son propre serveur, et échoue fort (au lieu de tester
      la mauvaise page en silence) si le port est déjà pris par un tiers ;
  (b) DURCISSEMENT du harnais : `execution.front_execute` reconnaît maintenant le message exact
      que Playwright émet dans ce cas (« ... is already used, make sure that nothing is running
      on the port/url ... ») et le nomme AVANT toute autre cause — sans ce garde, ce cas se
      confondait avec « trace indisponible » (TF-0132, aucun trace.zip produit puisqu'aucun
      test n'a tourné) ou avec une suite e2e réellement rouge.

Ce dernier point reste un fait d'ENVIRONNEMENT sur ce poste (le port ne se libère pas depuis le
code de ce dépôt) : D-01 ne repassera au vert qu'une fois le port 4173 libéré côté poste. Ce que
ce correctif garantit, c'est que le rapport ne mente plus sur la raison.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from forge_tests import execution


def _projet_front(tmp_path: Path) -> Path:
    front = tmp_path / "frontend"
    (front / "node_modules").mkdir(parents=True)
    (front / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    return front


def _front_execute_avec(tmp_path: Path, monkeypatch, resultat) -> dict | None:
    _projet_front(tmp_path)
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: "npx-factice")
    monkeypatch.setattr(execution, "_run", lambda *_a, **_k: resultat)
    execution.front_execute.cache_clear()
    return execution.front_execute(str(tmp_path))


# --- ROUGE implicite : le message Playwright EXACT observé sur ce poste ------------------------
def test_port_deja_occupe_est_nomme_jamais_confondu_avec_la_trace(
    tmp_path: Path, monkeypatch
) -> None:
    """Le cas RÉEL constaté : le webServer ne démarre pas (port pris par un AUTRE processus),
    donc aucun test ne tourne et aucun trace.zip n'est produit — mode `on` par défaut.

    AVANT le correctif, ce cas retombait sur « trace Playwright indisponible » (TF-0132) :
    un diagnostic faux, puisque la trace n'y est pour rien — aucun test n'a même démarré.
    """
    resultat = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="Error: http://localhost:4173 is already used, make sure that nothing is "
        "running on the port/url or set reuseExistingServer:true in config.webServer.",
        stderr="",
    )

    mesure = _front_execute_avec(tmp_path, monkeypatch, resultat)

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "port" in motif.lower() and "occup" in motif.lower()
    assert "http://localhost:4173" in motif
    # Le motif TF-0132 (« trace Playwright indisponible (code ... malgre --trace on) ») ne doit
    # PAS être celui publié ici — seule sa mention explicite pour écarter la confusion est
    # tolérée (« ni une trace indisponible »).
    assert "trace playwright indisponible" not in motif.lower()
    assert "la suite e2e s est terminée en échec" not in motif.lower()


def test_port_deja_occupe_prime_meme_avec_trace_desactivee(tmp_path: Path, monkeypatch) -> None:
    """La priorité du motif « port occupé » ne dépend pas du mode de trace choisi."""
    monkeypatch.setenv("FORGE_TESTS_PLAYWRIGHT_TRACE", "off")
    resultat = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="Error: http://localhost:4173 is already used, make sure that nothing is "
        "running on the port/url or set reuseExistingServer:true in config.webServer.",
        stderr="",
    )

    mesure = _front_execute_avec(tmp_path, monkeypatch, resultat)

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "port" in motif.lower() and "occup" in motif.lower()


# --- Témoin discriminant : une suite réellement rouge n'est PAS reclassée en « port occupé » ----
def test_une_suite_reellement_rouge_nest_pas_confondue_avec_un_port_occupe(
    tmp_path: Path, monkeypatch
) -> None:
    """ROUGE implicite inverse : un texte de suite ordinairement rouge ne doit JAMAIS matcher
    le motif « port occupé » sous prétexte qu'il contient le mot « port » ou « already »."""
    resultat = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="1 failed\n  Error: expect(received).toBeVisible()\n  already visible: false",
        stderr="",
    )
    monkeypatch.setenv("FORGE_TESTS_PLAYWRIGHT_TRACE", "off")

    mesure = _front_execute_avec(tmp_path, monkeypatch, resultat)

    assert mesure is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "port" not in motif.lower() or "occup" not in motif.lower()
    assert "suite e2e" in motif.lower() and "échec" in motif.lower()
