"""TF-1791 — la délégation d événements posée sur le conteneur racine échappait au pan qualif.

Fait remonté par Produit-83 (lot 20261015b, RE-3, ledger seq 122) : le pan ne cherchait la
délégation que sur `document` et `document.body`. React 17+ (React 19 chez le produit) la pose
sur le conteneur passé à `createRoot`, `<div id="root">`. Effet : 64 faux constats « formulaire
sans action ni écouteur », et le seuil qualif bloquant.

Joué contre un vrai navigateur (protocole DevTools, comme en audit) :
  - le cas fautif d hier : un écouteur `click`/`submit` sur `#root`, aucun sur document ou
    body, doit être vu comme une délégation ;
  - le cas conforme : sans aucun écouteur ancêtre, pas de délégation, et l affordance inerte
    reste jugeable (donc accusable).
"""

from __future__ import annotations

import pytest

from forge_tests.adaptateurs import qualif

_RACINE_REACT = """<!doctype html><html lang="fr"><head><meta charset="utf-8"></head><body>
<div id="root"><form><input name="q"><button type="submit">Chercher</button></form></div>
<script>
  const racine = document.getElementById('root');
  racine.addEventListener('click', () => {});
  racine.addEventListener('submit', (e) => e.preventDefault());
</script></body></html>"""

_SANS_DELEGATION = """<!doctype html><html lang="fr"><head><meta charset="utf-8"></head><body>
<div id="root"><form><input name="q"><button type="submit">Chercher</button></form></div>
</body></html>"""


def _delegation(html: str) -> bool:
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pilote:
        navigateur = pilote.chromium.launch()
        try:
            page = navigateur.new_page()
            page.set_content(html)
            types, delegation, motif = qualif._ecouteurs(page)
        finally:
            navigateur.close()
    assert motif is None, motif
    assert types is not None
    return delegation


def test_delegation_sur_le_conteneur_racine_est_vue() -> None:
    assert _delegation(_RACINE_REACT) is True


def test_sans_ecouteur_ancetre_pas_de_delegation() -> None:
    assert _delegation(_SANS_DELEGATION) is False
