"""TF-2468 — un verdict d'oracle autre que PASS ou FAIL (champ absent, inconnu, forme inattendue)
n'est plus compté « réellement joué » par le pan `securite`.

Fait remonté par l'agent du lot ft le 12/11/2026, en traitant TF-2449 : seul `SKIP` était écarté
des joués. Un oracle qui rendait un JSON sans champ `verdict`, ou un verdict hors du vocabulaire
(`WARN`, `ERROR`, `pass` en minuscules), restait compté joué : le pan écrivait « oracles
réellement joués — sca » et rendait PASS sur une vérification dont rien ne dit qu'elle a eu lieu.
Même famille que TF-2449 et TF-2403 : un audit de sécurité vert sur une mesure non prononcée.

Décision (R-58 du 12/11/2026) : le pan ne compte joués que les oracles qui rendent PASS ou FAIL ;
tout autre verdict, champ absent compris, va au `non_juge` avec son motif.

Sens prouvés :
  - ROUGE  — un oracle sans `verdict`, ou à verdict inconnu, ne donne plus PASS et ne figure pas
             aux « réellement joués » (seul oracle de ce cas : le pan rend SKIP) ;
  - VERT   — un oracle à verdict non prononçable à côté de deux PASS est NOMMÉ non joué avec son
             motif, et le PASS repose sur les deux joués ;
  - CONTRE-ÉPREUVES — PASS et FAIL restent comptés joués ; un verdict non prononçable ne masque
             pas le FAIL d'un autre oracle ; le message du SKIP (TF-2449) est inchangé.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite


def _oracle_brut(sortie: object) -> str:
    """Un oracle factice qui écrit tel quel le JSON donné (verdict absent compris)."""
    return f"process.stdout.write({json.dumps(json.dumps(sortie))});\n"


def _oracle(verdict: str | None, *, msg: str = "", sev: str = "info") -> str:
    corps: dict = {"oracle": "factice", "findings": [], "non_juge": []}
    if verdict is not None:
        corps["verdict"] = verdict
    if msg:
        corps["findings"] = [{"sev": sev, "msg": msg, "where": "app/m.py"}]
    return _oracle_brut(corps)


@pytest.fixture
def produit(tmp_path: Path, monkeypatch) -> Path:
    racine = tmp_path / "produit"
    (racine / "app").mkdir(parents=True)
    (racine / "app" / "__init__.py").write_text("", encoding="utf-8")
    (racine / "app" / "m.py").write_text("X = 1\n", encoding="utf-8")
    (racine / "tests").mkdir()
    (racine / "pyproject.toml").write_text("[project]\nname='p'\n", encoding="utf-8")
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    return racine


def _registre(tmp_path: Path, monkeypatch, **oracles: str) -> Path:
    registre = tmp_path / "oracles"
    registre.mkdir()
    for nom, source in oracles.items():
        (registre / f"oracle-{nom}.mjs").write_text(source, encoding="utf-8")
    monkeypatch.setattr(securite, "_racine_oracles", lambda: registre)
    return registre


def _ligne_joues(sortie) -> list[str]:
    return [n for n in sortie.non_juge if "oracles reellement joues" in n]


def test_rouge_un_oracle_sans_champ_verdict_n_est_pas_un_oracle_joue(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    """Le défaut mesuré : sca rend un JSON sans `verdict`, le pan écrivait « joues — sca »."""
    _registre(tmp_path, monkeypatch, sca=_oracle(None))

    sortie = securite.analyser(produit)

    assert sortie.verdict == "SKIP", "aucun oracle joué : le pan ne peut pas rendre PASS"
    assert not _ligne_joues(sortie), "un oracle sans verdict ne se déclare pas « réellement joué »"
    assert any("oracle-sca" in n and "aucun verdict" in n for n in sortie.non_juge)
    assert any("aucun oracle de securite n a pu etre joue" in n for n in sortie.non_juge)


@pytest.mark.parametrize("inconnu", ["WARN", "ERROR", "pass", "OK", ""])
def test_rouge_un_verdict_hors_vocabulaire_n_est_pas_un_oracle_joue(
    tmp_path: Path, produit: Path, monkeypatch, inconnu: str
) -> None:
    _registre(tmp_path, monkeypatch, sast=_oracle(inconnu, msg="a verifier"))

    sortie = securite.analyser(produit)

    assert sortie.verdict == "SKIP"
    assert not _ligne_joues(sortie)
    ligne = next(n for n in sortie.non_juge if "oracle-sast" in n and "non joue" in n)
    assert f"« {inconnu} »" in ligne, "le verdict reçu est cité tel quel"
    assert "a verifier" in ligne, "le motif de l'oracle est repris"


@pytest.mark.parametrize("brut", [[], "PASS", 3])
def test_rouge_une_sortie_qui_n_est_pas_un_objet_n_est_pas_un_oracle_joue(
    tmp_path: Path, produit: Path, monkeypatch, brut: object
) -> None:
    """Un JSON valide mais d'une autre forme ne doit ni lever ni compter joué."""
    _registre(tmp_path, monkeypatch, secrets=_oracle_brut(brut))

    sortie = securite.analyser(produit)

    assert sortie.verdict == "SKIP"
    assert not _ligne_joues(sortie)
    assert any("oracle-secrets" in n and "non joue" in n for n in sortie.non_juge)


def test_vert_un_verdict_non_prononce_a_cote_de_deux_pass_est_nomme_non_joue(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    _registre(
        tmp_path, monkeypatch,
        sast=_oracle("PASS"), secrets=_oracle("PASS"), sca=_oracle("WARN", msg="avis partiel"),
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "PASS"
    ligne = _ligne_joues(sortie)
    assert len(ligne) == 1
    assert "sast, secrets" in ligne[0]
    assert "sca" not in ligne[0]
    assert any("oracle-sca" in n and "« WARN »" in n and "avis partiel" in n
               for n in sortie.non_juge)


def test_contre_epreuve_pass_et_fail_restent_comptes_joues(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    _registre(
        tmp_path, monkeypatch,
        sast=_oracle("FAIL", sev="bloquant", msg="injection SQL"),
        secrets=_oracle("PASS"),
        sca=_oracle("PASS"),
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "FAIL"
    assert "sast, secrets, sca" in _ligne_joues(sortie)[0]
    assert any(f.id.startswith("securite:sast:") for f in sortie.findings)


def test_contre_epreuve_un_verdict_non_prononcable_ne_masque_pas_un_fail(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    _registre(
        tmp_path, monkeypatch,
        sast=_oracle("FAIL", sev="bloquant", msg="injection SQL"),
        sca=_oracle(None),
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "FAIL"
    assert "sast" in _ligne_joues(sortie)[0]
    assert "sca" not in _ligne_joues(sortie)[0]


def test_contre_epreuve_le_message_du_skip_reste_celui_de_tf_2449(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    _registre(tmp_path, monkeypatch, sca=_oracle("SKIP", msg="OSV injoignable"))

    sortie = securite.analyser(produit)

    assert sortie.verdict == "SKIP"
    assert any("oracle-sca a rendu SKIP — non joue : OSV injoignable" in n
               for n in sortie.non_juge)
