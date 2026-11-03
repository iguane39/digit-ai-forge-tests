"""TF-2098 — une preprod LOCALE en TLS auto-signe est joignable, sous variable BORNEE.

Le pan qualif creait son contexte Playwright sans `ignore_https_errors` : impossible de joindre
une preproduction locale a certificat auto-signe (le navigateur refuse, parcours reste anonyme).
Une variable DECLAREE, `FORGE_TESTS_QUALIF_TLS_NON_VERIFIE=1`, accepte le certificat — mais
BORNEE aux hotes de boucle locale (localhost, 127.0.0.1, ::1). Lever la verification TLS contre
un hote DISTANT ferait de l auditeur le complice d un homme-du-milieu : la borne est le fond.
"""

from __future__ import annotations

import pytest

from forge_tests.adaptateurs import qualif


def test_tls_option_posee_quand_variable_et_hote_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_TESTS_QUALIF_TLS_NON_VERIFIE", "1")
    options, alertes = qualif._options_contexte({"base": "https://localhost:8443"})
    assert options.get("ignore_https_errors") is True
    assert any("TLS" in a for a in alertes), alertes


def test_tls_option_absente_sans_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_TESTS_QUALIF_TLS_NON_VERIFIE", raising=False)
    options, _ = qualif._options_contexte({"base": "https://localhost:8443"})
    assert "ignore_https_errors" not in options


def test_tls_option_refusee_sur_hote_distant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sens rouge du bornage : la variable posee NE leve PAS le TLS contre un hote distant."""
    monkeypatch.setenv("FORGE_TESTS_QUALIF_TLS_NON_VERIFIE", "1")
    options, _ = qualif._options_contexte({"base": "https://preprod.exemple.test"})
    assert "ignore_https_errors" not in options


def test_tls_borne_sur_127_0_0_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_TESTS_QUALIF_TLS_NON_VERIFIE", "1")
    options, _ = qualif._options_contexte({"base": "https://127.0.0.1:8443"})
    assert options.get("ignore_https_errors") is True
