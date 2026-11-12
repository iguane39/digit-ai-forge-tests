"""TF-2449 — un oracle délégué qui rend SKIP n'est plus compté « réellement joué » par le pan
`securite`, qui rendait alors PASS.

Fait remonté par le lot ft de la campagne du 12/11/2026 : avec un `oracle-sca` factice qui rend
SKIP (« OSV injoignable »), le pan écrivait « oracles réellement joués — sca » et rendait PASS.
Même famille de faux négatif que TF-2403 : un audit de sécurité vert sur une vérification qui n'a
pas eu lieu. Cause : `analyser` ajoutait l'oracle à `joues` dès qu'il rendait un JSON, sans lire son
verdict ; seul `FAIL` était distingué.

Correction : un verdict `SKIP` range l'oracle au `non_juge` (« a rendu SKIP — non joue », motif
repris de l'oracle) et ne le compte pas parmi les joués. Si plus aucun oracle n'est joué, le pan
rend SKIP, comme pour un oracle absent du registre.

Sens prouvés :
  - ROUGE  — un oracle factice qui rend SKIP ne doit plus donner PASS ni figurer aux « réellement
             joués » (le seul oracle SKIP : le pan rend SKIP) ;
  - VERT   — les oracles qui rendent PASS restent comptés et le pan reste PASS ; un SKIP à côté
             de deux PASS est NOMMÉ non joué, le PASS repose sur les deux joués ;
  - CONTRE-ÉPREUVES — un oracle qui rend FAIL reste compté joué et fait échouer le pan ; un SKIP
             ne masque pas le FAIL d'un autre oracle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite


def _oracle(verdict: str, *, sev: str = "info", msg: str = "", motif: str | None = None) -> str:
    """Un oracle factice : un verdict, un finding (ou aucun), et le champ `motif` des SKIP."""
    findings = f"[{{ sev: '{sev}', msg: '{msg}', where: 'app/m.py' }}]" if msg else "[]"
    champ_motif = f", motif: '{motif}'" if motif else ""
    return (
        "process.stdout.write(JSON.stringify({ oracle: 'factice', "
        f"verdict: '{verdict}', findings: {findings}, non_juge: []{champ_motif} }}));\n"
    )


@pytest.fixture
def produit(tmp_path: Path, monkeypatch) -> Path:
    """Un produit à racine plate : une source Python lisible, aucun manifeste hors `.py`."""
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


def test_rouge_un_oracle_sca_qui_rend_skip_n_est_pas_un_oracle_joue(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    """Le défaut mesuré : sca rend SKIP, le pan rendait PASS et écrivait « joues — sca »."""
    _registre(
        tmp_path, monkeypatch,
        sca=_oracle("SKIP", msg="SCA non verifiable — OSV injoignable", motif="OSV injoignable"),
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "SKIP", "aucun oracle joué : le pan ne peut pas rendre PASS"
    assert not _ligne_joues(sortie), "un oracle SKIP ne se déclare pas « réellement joué »"
    assert any("oracle-sca a rendu SKIP" in n and "OSV injoignable" in n for n in sortie.non_juge)
    assert any("aucun oracle de securite n a pu etre joue" in n for n in sortie.non_juge)


def test_rouge_trois_oracles_skip_le_pan_rend_skip(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    skip = _oracle("SKIP", msg="rien de verifiable")
    _registre(tmp_path, monkeypatch, sast=skip, secrets=skip, sca=skip)

    sortie = securite.analyser(produit)

    assert sortie.verdict == "SKIP"
    assert not _ligne_joues(sortie)
    for nom in ("sast", "secrets", "sca"):
        assert any(f"oracle-{nom} a rendu SKIP" in n for n in sortie.non_juge)


def test_vert_un_skip_a_cote_de_deux_pass_est_nomme_non_joue_et_le_pan_reste_pass(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    """Le PASS repose sur les deux oracles joués ; le SKIP se lit au rapport."""
    _registre(
        tmp_path, monkeypatch,
        sast=_oracle("PASS"),
        secrets=_oracle("PASS"),
        sca=_oracle("SKIP", msg="SCA non verifiable — OSV injoignable", motif="OSV injoignable"),
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "PASS"
    ligne = _ligne_joues(sortie)
    assert len(ligne) == 1
    assert "sast, secrets" in ligne[0]
    assert "sca" not in ligne[0]
    assert any("oracle-sca a rendu SKIP" in n and "OSV injoignable" in n for n in sortie.non_juge)


def test_contre_epreuve_les_oracles_qui_rendent_pass_restent_comptes_joues(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    _registre(
        tmp_path, monkeypatch, sast=_oracle("PASS"), secrets=_oracle("PASS"), sca=_oracle("PASS")
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "PASS"
    assert "sast, secrets, sca" in _ligne_joues(sortie)[0]
    assert not any("a rendu SKIP" in n for n in sortie.non_juge)


def test_contre_epreuve_un_fail_reste_joue_et_un_skip_ne_le_masque_pas(
    tmp_path: Path, produit: Path, monkeypatch
) -> None:
    _registre(
        tmp_path, monkeypatch,
        sast=_oracle("FAIL", sev="bloquant", msg="injection SQL"),
        sca=_oracle("SKIP", msg="OSV injoignable"),
    )

    sortie = securite.analyser(produit)

    assert sortie.verdict == "FAIL"
    assert "sast" in _ligne_joues(sortie)[0]
    assert "sca" not in _ligne_joues(sortie)[0]
    assert any(f.id.startswith("securite:sast:") for f in sortie.findings)
