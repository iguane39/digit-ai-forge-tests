"""TF-2392 — la recette du corpus ne change pas de couleur avec le calendrier ni le poste.

Fait remonté par la campagne du 09/11/2026 (reproduit sur 1a6d47a) :

  1. la section `corpus` rendait ECHEC : le banc vert sortait 5 bloquants du pan `securite`
     (certifi 2026.7.22 PYSEC-2026-4320, urllib3 2.7.0 PYSEC-2026-4175 à 4177), avis publiés
     entre le 01/10 et le 20/10/2026 sur un verrou qui n'avait pas bougé depuis le 12/08 ;
  2. la section `unitaire` n'était pas prononcée : `pytest` y était lancé en un seul processus avec
     un délai de 600 s, dépassé sur ce poste ; l'échec se lisait « pytest non lancable :
     TimeoutExpired », indiscernable d'une panne de lancement.

Décision du 10/11/2026 : le banc vert se juge contre une base d'avis figée et datée, ou son verrou
se met à jour ; le délai de la section unitaire se relève ou se parallélise.

Choix : le verrou du banc vert est remonté (`certifi 2026.10.23`, `urllib3 2.8.0`, 12 lignes de
`uv.lock`), et la section unitaire se PARALLÉLISE par fichier de test avec un délai réglable. La
base d'avis figée (`oracle-sca --osv-fige`) a été essayée et écartée : en mode figé l'oracle
demande la version de la plage du `package.json` (`vite ^5.4.8`) et juge tout avis sans filtre de
sévérité ; même répondu sur les versions du `package-lock.json`, il restait 4 avis publiés avant le
gel (`vite` 5.4.21 ×3, `react-router-dom` 6.30.4 ×1), donc 4 bloquants npm que le pan ne rend pas en
mode vif.

Sens prouvés :
  - ROUGE  — sur l'ancien code, la suite unitaire est lancée en UN processus, un délai dépassé se
             lit « non lançable », et rien ne dit que des avis publiés depuis le verrou sont la
             cause d'un vert rouge ;
  - VERT   — un processus par fichier, comptes agrégés, délai dépassé nommé `DELAI_DEPASSE` avec
             son réglage, indice de calendrier qui nomme les paquets et la commande de remontée ;
  - CONTRE-ÉPREUVES — un fichier rouge fait échouer la section et montre sa queue, un bloquant du
             banc vert qui n'est pas un avis de dépendance ne reçoit aucun indice de calendrier.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path

import pytest

from recette import verifier_corpus as recette

RACINE = Path(__file__).resolve().parent.parent
REGLAGE_DELAI = "RECETTE_DELAI_UNITAIRE_S"
REGLAGE_PROCESSUS = "RECETTE_PROCESSUS_UNITAIRE"


class _FauxPytest:
    """Remplace `subprocess.run` : enregistre chaque lancement, rend un bilan par fichier."""

    def __init__(self, *, rouges: tuple[str, ...] = (), lent: str | None = None) -> None:
        self.appels: list[dict] = []
        self.simultanes = 0
        self.max_simultanes = 0
        self._verrou = threading.Lock()
        self.rouges = rouges
        self.lent = lent

    def __call__(self, commande, **kwargs):
        fichier = next((c for c in commande if str(c).endswith(".py")), "")
        with self._verrou:
            self.appels.append({"commande": list(commande), "timeout": kwargs.get("timeout")})
            self.simultanes += 1
            self.max_simultanes = max(self.max_simultanes, self.simultanes)
        try:
            time.sleep(0.02)  # laisse aux autres fils le temps de se recouvrir
            if self.lent and self.lent in str(fichier):
                raise subprocess.TimeoutExpired(commande, kwargs.get("timeout") or 0)
            rouge = any(nom in str(fichier) for nom in self.rouges)
            sortie = (
                f"FAILED {fichier}::test_x - assert 1 == 2\n1 failed, 2 passed in 0.10s\n"
                if rouge else "3 passed, 1 skipped in 0.10s\n"
            )
            return subprocess.CompletedProcess(
                commande, 1 if rouge else 0, stdout=sortie, stderr=""
            )
        finally:
            with self._verrou:
                self.simultanes -= 1


@pytest.fixture()
def faux(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(REGLAGE_DELAI, raising=False)
    monkeypatch.setenv(REGLAGE_PROCESSUS, "4")

    def poser(**kwargs):
        faux_run = _FauxPytest(**kwargs)
        monkeypatch.setattr(subprocess, "run", faux_run)
        return faux_run

    return poser


def _fichiers_de_test() -> list[Path]:
    return sorted((RACINE / "tests").glob("test_*.py"))


def test_rouge_la_suite_unitaire_est_lancee_en_un_processus_par_fichier(
    faux, capsys: pytest.CaptureFixture[str]
) -> None:
    """ROUGE avant le correctif : un seul `pytest` pour tout le dépôt, jamais deux en même temps."""
    pytest_simule = faux()
    assert recette.verifier_suite_unitaire() == 0
    fichiers = _fichiers_de_test()
    lances = [c["commande"][-1] for c in pytest_simule.appels]
    assert len(lances) == len(fichiers) > 100  # un lancement par fichier, aucun oublié
    assert sorted(Path(c).name for c in lances) == sorted(f.name for f in fichiers)
    assert pytest_simule.max_simultanes >= 2  # recouvrement réel : la section est parallèle
    sortie = capsys.readouterr().out
    assert "[OK     ] pytest :" in sortie
    assert f"{3 * len(fichiers)} passed" in sortie and f"{len(fichiers)} skipped" in sortie


def test_le_nombre_de_processus_se_regle_et_se_dit(
    faux, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(REGLAGE_PROCESSUS, "1")
    pytest_simule = faux()
    assert recette.verifier_suite_unitaire() == 0
    assert pytest_simule.max_simultanes == 1
    assert "1 processus" in capsys.readouterr().out


def test_un_fichier_rouge_fait_echouer_la_section_et_montre_sa_queue(
    faux, capsys: pytest.CaptureFixture[str]
) -> None:
    """CONTRE-ÉPREUVE : le parallélisme ne dilue pas un échec dans les comptes des autres."""
    faux(rouges=("test_tf_0311",))
    assert recette.verifier_suite_unitaire() == 1
    sortie = capsys.readouterr().out
    assert "[ECHEC  ] pytest :" in sortie
    assert "test_tf_0311_comptes_du_corpus.py" in sortie
    assert "FAILED" in sortie and "assert 1 == 2" in sortie


def test_rouge_un_delai_depasse_ne_se_lit_plus_pytest_non_lancable(
    faux, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ROUGE avant : « pytest non lancable : TimeoutExpired ». Vert : le verdict est nommé, le
    réglage qui lève le délai est donné, et la section échoue (G-2 : un délai n'est pas un vert)."""
    faux(lent="test_tf_0311")
    monkeypatch.setenv(REGLAGE_DELAI, "900")
    assert recette.verifier_suite_unitaire() == 1
    sortie = capsys.readouterr().out
    assert "non lancable" not in sortie
    assert "DELAI_DEPASSE" in sortie
    assert REGLAGE_DELAI in sortie and "900 s" in sortie
    assert "test_tf_0311_comptes_du_corpus.py" in sortie  # le fichier interrompu est nommé


def test_le_delai_regle_borne_chaque_lancement(
    faux, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest_simule = faux()
    monkeypatch.setenv(REGLAGE_DELAI, "120")
    assert recette.verifier_suite_unitaire() == 0
    assert all(0 < c["timeout"] <= 120 for c in pytest_simule.appels)


def test_un_delai_illisible_laisse_le_defaut_et_le_dit(
    faux, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest_simule = faux()
    monkeypatch.setenv(REGLAGE_DELAI, "bientot")
    assert recette.verifier_suite_unitaire() == 0
    assert all(c["timeout"] <= recette.DELAI_UNITAIRE_DEFAUT_S for c in pytest_simule.appels)
    sortie = capsys.readouterr().out
    assert REGLAGE_DELAI in sortie and "illisible" in sortie


# --- Avis de dépendances publiés depuis le verrou du banc vert ---------------------------------
def _avis(paquet: str, version: str, identifiant: str) -> dict:
    return {
        "id": "securite:sca:uv.lock", "pan": "securite", "classe": "dependance-vulnerable",
        "severite": "bloquant", "message": f"[sca] PyPI {paquet}@{version} : {identifiant}",
    }


def test_rouge_le_calendrier_derriere_un_vert_rouge_se_nomme() -> None:
    """Les cinq bloquants du 09/11/2026 : l'indice nomme les deux paquets et la remontée."""
    bloquants = [
        _avis("certifi", "2026.7.22", "PYSEC-2026-4320"),
        _avis("urllib3", "2.7.0", "PYSEC-2026-4175"),
        _avis("urllib3", "2.7.0", "PYSEC-2026-4176"),
        _avis("urllib3", "2.7.0", "PYSEC-2026-4177"),
    ]
    indice = " ".join(recette.indice_avis_depuis_le_verrou(bloquants))
    assert "certifi" in indice and "urllib3" in indice
    assert "uv lock --upgrade-package certifi --upgrade-package urllib3" in indice
    assert "fixtures/banc-vert/backend" in indice
    assert indice.count("urllib3") == 2  # nommé une fois, et dans la commande : pas trois fois


def test_l_indice_cite_une_commande_qui_vise_un_verrou_existant() -> None:
    """Jouer le remède recommandé (TF-1013) : le dossier de la commande porte bien un uv.lock."""
    indice = " ".join(recette.indice_avis_depuis_le_verrou([_avis("certifi", "1", "X")]))
    dossier = re.search(r"cd (\S+) &&", indice)
    assert dossier is not None
    assert (RACINE / dossier.group(1) / "uv.lock").is_file()


def test_contre_epreuve_un_autre_bloquant_ne_recoit_aucun_indice_de_calendrier() -> None:
    autre = {
        "id": "api:route-non-couverte:/x", "pan": "api", "classe": "route-non-exercee",
        "severite": "bloquant", "message": "route non couverte",
    }
    assert recette.indice_avis_depuis_le_verrou([autre]) == []
    assert recette.indice_avis_depuis_le_verrou([]) == []


def test_le_verrou_du_banc_vert_ne_porte_plus_les_versions_du_09_11() -> None:
    """Le correctif lui-même : les deux paquets nommés par la campagne sont remontés."""
    verrou = (RACINE / "fixtures/banc-vert/backend/uv.lock").read_text(encoding="utf-8")
    assert 'name = "certifi"\nversion = "2026.7.22"' not in verrou.replace("\r\n", "\n")
    assert 'name = "urllib3"\nversion = "2.7.0"' not in verrou.replace("\r\n", "\n")
