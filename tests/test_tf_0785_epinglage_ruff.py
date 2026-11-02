"""TF-0785 — un verdict rendu par un linter NON ÉPINGLÉ n'est pas un verdict.

Constat du 02/09/2026, section `lint` de la recette. La dépendance était déclarée `ruff>=0.5`,
la version installée `0.16.1`. Mesuré sur le MÊME arbre : **115 constats sous 0.5.7, 100 sous
0.16.1** — 17 `UP038` disparus (règle retirée en amont), 2 `UP031` apparus. Aucun octet du dépôt
n'avait bougé. Le pas « armé après avoir soldé les 21 » (TF-0226) était donc rouge depuis une
date que personne ne pouvait situer, pour des constats qu'aucun commit n'avait introduits.

Ce que ces tests câblent : la version jouée ENTRE AU RAPPORT, et une déclaration qui n'épingle
pas est un ÉCHEC de la section — pas un avertissement. Un garde-fou dont la référence dérive ne
mesure plus le dépôt : il mesure le poste.

Chaque contrôle porte sa FIXTURE À DOUBLE SENS : le cas rouge est refusé, le cas vert accepté —
un contrôle qui n'accepte rien ne prouve pas plus qu'un contrôle qui accepte tout.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from recette import verifier_corpus as vc  # noqa: E402


# --- TF-0785 : la version de ruff est épinglée, et la recette la dit --------------------------
def test_un_plancher_de_version_n_est_PAS_un_epinglage() -> None:
    """CAS ROUGE — la déclaration d'origine, mot pour mot. Elle laisse la version au poste."""
    epinglee, declaration = vc.epinglage_ruff('dev = [\n    "ruff>=0.5",\n]\n')

    assert epinglee is None, "un plancher laisse 0.5.7 et 0.16.1 également valides"
    assert declaration == "ruff>=0.5", "la déclaration lue est RENDUE, pas paraphrasée"


def test_une_version_exacte_EST_un_epinglage() -> None:
    """CAS VERT — le contrôle doit ACCEPTER l'épinglage, sinon il n'a rien discriminé."""
    epinglee, declaration = vc.epinglage_ruff('    "ruff==0.16.1",\n')

    assert epinglee == "0.16.1"
    assert declaration == "ruff==0.16.1"


@pytest.mark.parametrize(
    "declaration",
    ['    "ruff~=0.16",', '    "ruff",', '    "ruff>=0.5,<1.0",'],
)
def test_les_autres_contraintes_ne_sont_pas_des_epinglages(declaration: str) -> None:
    """Contre-épreuve : `~=` et une fourchette laissent DEUX versions possibles, donc deux
    verdicts possibles. Les accepter rouvrirait le trou par la porte d'à côté."""
    assert vc.epinglage_ruff(declaration)[0] is None


def test_une_declaration_ABSENTE_est_dite_absente_jamais_supposee_juste() -> None:
    """Loi 3 : l'oubli n'existe pas. Un `pyproject` sans ruff n'est pas un `pyproject` épinglé
    — c'est un `pyproject` qui a perdu la dépendance que la recette joue."""
    epinglee, declaration = vc.epinglage_ruff("[project]\nname = 'x'\n")

    assert epinglee is None
    assert "aucune déclaration" in declaration


def test_CE_depot_epingle_effectivement_son_linter() -> None:
    """Le garde-fou de non-régression : la doctrine ci-dessus est vraie ICI, pas seulement sur
    des chaînes de test. Un retour à `ruff>=…` rend ce test rouge."""
    pyproject = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
    epinglee, declaration = vc.epinglage_ruff(pyproject)

    assert epinglee, f"le linter du dépôt n'est plus épinglé : {declaration}"
    assert re.fullmatch(r"\d+\.\d+\.\d+", epinglee), declaration


# --- TF-2060 : un ruff d'une autre version dit d'où il vient et quelle commande jouer ----------
def test_un_ruff_de_poste_reste_refuse_et_le_dit_avec_sa_commande(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CAS ROUGE — ruff 0.15.21 du poste pour 0.16.1 épinglé : le refus reste ENTIER (S-01 n'est
    pas assoupli), mais le message nomme le lanceur et donne la commande qui corrige."""
    monkeypatch.setattr(vc, "_version_ruff", lambda commande: "0.15.21")
    epinglee, _ = vc.epinglage_ruff((vc.RACINE / "pyproject.toml").read_text(encoding="utf-8"))

    echecs = vc.verifier_lint()
    sortie = capsys.readouterr().out

    assert echecs >= 1, "un autre ruff que l'épinglé est un ÉCHEC, jamais un avertissement"
    assert f"ruff joue 0.15.21 alors que le depot epingle {epinglee}" in sortie
    assert "vient du LANCEUR" in sortie
    assert "`uv run python recette/verifier_corpus.py`" in sortie
    assert f"ruff=={epinglee}" in sortie


def test_le_ruff_epingle_ne_declenche_pas_le_message_du_lanceur(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CAS VERT — la version jouée est l'épinglée : aucun écart, aucun message de lanceur."""
    epinglee, _ = vc.epinglage_ruff((vc.RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    monkeypatch.setattr(vc, "_version_ruff", lambda commande: epinglee)

    vc.verifier_lint()
    sortie = capsys.readouterr().out

    assert "LANCEUR" not in sortie
    assert "alors que le depot epingle" not in sortie
