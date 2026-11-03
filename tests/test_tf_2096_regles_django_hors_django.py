"""TF-2096 — les regles semgrep `python.django.*` ne doivent pas accuser un projet sans Django.

Fait : la regle `django-no-csrf-token` se declenche sur des gabarits a champ cache meme hors
Django. Sur un backend FastAPI + Jinja2, chaque formulaire porte deja son jeton CSRF verifie
cote serveur ; la regle le prend pour une absence et rend un bloquant FAUX. `oracle-sast` ne
publie que le DERNIER segment du check_id (`django-no-csrf-token`), le namespace `python.django.*`
est perdu en amont : le pan `securite` reconnait donc la famille Django a ce segment et n ecarte
ces constats QUE si le projet ne declare aucune dependance Django.

Le `_lancer` est doublé : la paire de fixtures ne depend ni de semgrep installe ni du reseau.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite


def _projet(tmp_path: Path, deps: str) -> Path:
    projet = tmp_path / "produit"
    projet.mkdir()
    (projet / "pyproject.toml").write_text(
        f'[project]\nname = "p"\ndependencies = [{deps}]\n', encoding="utf-8"
    )
    (projet / "main.py").write_text("x = 1\n", encoding="utf-8")
    (projet / "login.html").write_text(
        '<form><input type="hidden" name="csrf_token" value="xxx"><button>Entrer</button></form>\n',
        encoding="utf-8",
    )
    return projet


def _sast_rend_django(monkeypatch: pytest.MonkeyPatch) -> None:
    """oracle-sast remonte un bloquant `django-no-csrf-token` ; les autres oracles sont verts."""

    def _double(script: Path, cible: Path) -> dict:
        if Path(str(script)).name == "oracle-sast.mjs":
            return {
                "verdict": "FAIL",
                "findings": [
                    {"sev": "bloquant", "msg": "semgrep django-no-csrf-token",
                     "where": str(Path(cible) / "login.html") + ":1"},
                ],
                "non_juge": [],
            }
        return {"verdict": "PASS", "findings": [], "non_juge": []}

    monkeypatch.setattr(securite, "_lancer", _double)


def test_regle_django_ecartee_sur_fastapi_sans_django(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sast_rend_django(monkeypatch)
    sortie = securite.analyser(_projet(tmp_path, '"fastapi>=0.110", "jinja2"'))
    django = [f for f in sortie.findings if "django" in f.message.lower()]
    assert django == [], [f.message for f in django]
    # L exclusion se DIT au rapport, jamais en silence (TF-0280).
    dit = [n for n in sortie.non_juge if "django" in n.lower() and "ecart" in n.lower()]
    assert dit, sortie.non_juge


def test_regle_django_conservee_sur_un_vrai_projet_django(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sens rouge du bornage : un projet qui DECLARE Django garde ses constats Django."""
    _sast_rend_django(monkeypatch)
    sortie = securite.analyser(_projet(tmp_path, '"django>=4.2"'))
    django = [f for f in sortie.findings if "django" in f.message.lower()]
    assert django, "un projet Django doit conserver ses constats de regle Django"
