"""TF-1347 — le pan `front` composait mal les routes react-router IMBRIQUÉES.

Fait mesuré (retour Produit-72 du 23/09/2026, confirmé à la lecture le 02/10/2026) : 3 findings
lien-casse bloquants sur `/admin/keys` et `/admin/requests`, vérifiés faux. Cause, dans
`forge_tests/adaptateurs/front.py` : `_routes_react_router` relevait chaque `<Route path="…">`
isolément — un enfant `<Route path="keys">` sous un parent `<Route path="admin">` sortait comme
la route `/keys` toute seule, jamais composée en `/admin/keys`. L URL réellement visitée
(`/admin/keys`) n appariait alors aucun des deux fragments relevés séparément, et le lien
semblait cassé — alors qu il ne l était pas.

Chaque test ci-dessous ÉCHOUAIT avant le correctif.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import front


def _projet_react_router(tmp_path: Path, jsx: str) -> Path:
    projet = tmp_path / "spa"
    (projet / "frontend" / "src").mkdir(parents=True)
    (projet / "frontend" / "src" / "App.tsx").write_text(jsx, encoding="utf-8")
    return projet


# --- 1. Le cas réel du retour Produit-72 : deux enfants sous un même parent ---------------------------
def test_routes_imbriquees_composees_avec_leur_parent(tmp_path: Path) -> None:
    jsx = """
    <Routes>
      <Route path="/admin" element={<AdminLayout />}>
        <Route path="keys" element={<AdminKeys />} />
        <Route path="requests" element={<AdminRequests />} />
      </Route>
      <Route path="/login" element={<Login />} />
    </Routes>
    """
    projet = _projet_react_router(tmp_path, jsx)
    chemins = {chemin for chemin, _fichier in front._routes_react_router(projet / "frontend")}
    assert chemins == {"/admin", "/admin/keys", "/admin/requests", "/login"}
    # Les deux fragments isolés que l ancienne lecture produisait ne doivent plus apparaître seuls.
    assert "/keys" not in chemins
    assert "/requests" not in chemins


# --- 2. Bout en bout : l inventaire du pan porte la route COMPOSÉE, jamais le fragment ---------
def test_inventaire_porte_la_route_composee(tmp_path: Path) -> None:
    jsx = """
    <Routes>
      <Route path="/admin" element={<AdminLayout />}>
        <Route path="keys" element={<AdminKeys />} />
      </Route>
    </Routes>
    """
    projet = _projet_react_router(tmp_path, jsx)
    ids = {e.id for e in front.inventaire(projet)}
    assert "route:/admin/keys" in ids
    assert "route:/keys" not in ids


# --- 3. Fermeture de la boucle : l URL réellement visitée appariait désormais la route composée -
def test_url_visitee_apparie_desormais_la_route_composee_jamais_le_fragment() -> None:
    """C est exactement ce qui manquait pour que `/admin/keys` ne sorte plus « lien cassé » :
    l URL visitée doit apparier la route DÉCLARÉE par son motif (RT-11, `motif_de_route`)."""
    from forge_tests.noyau import Element

    inventaire_compose = [Element("route:/admin/keys", "front", "route", "src")]
    couvert = front._routes_appariees(inventaire_compose, ["/admin/keys"])
    assert couvert == {"route:/admin/keys"}
    # Le fragment isolé que l ancienne lecture produisait n aurait jamais apparié cette URL.
    inventaire_fragment = [Element("route:/keys", "front", "route", "src")]
    assert front._routes_appariees(inventaire_fragment, ["/admin/keys"]) == set()


# --- 4. Trois niveaux d imbrication, et un enfant ABSOLU qui ignore ses parents (react-router) --
def test_trois_niveaux_et_enfant_absolu_ignore_ses_parents(tmp_path: Path) -> None:
    jsx = """
    <Routes>
      <Route path="/admin" element={<AdminLayout />}>
        <Route path="users" element={<Users />}>
          <Route path=":id" element={<UserDetail />} />
        </Route>
        <Route path="/hors-admin" element={<HorsAdmin />} />
      </Route>
    </Routes>
    """
    projet = _projet_react_router(tmp_path, jsx)
    chemins = {chemin for chemin, _fichier in front._routes_react_router(projet / "frontend")}
    assert "/admin/users" in chemins
    assert "/admin/users/:id" in chemins
    # Un chemin enfant qui COMMENCE par "/" est absolu : il ignore ses ancêtres, comme
    # react-router lui-même — il ne doit jamais devenir "/admin/hors-admin".
    assert "/hors-admin" in chemins
    assert "/admin/hors-admin" not in chemins


# --- 5. Non-régression : une balise auto-fermée SANS element imbriqué reste auto-fermée ---------
def test_route_auto_fermee_simple_sans_enfant(tmp_path: Path) -> None:
    jsx = '<Routes><Route path="/solo" /></Routes>'
    projet = _projet_react_router(tmp_path, jsx)
    chemins = {chemin for chemin, _fichier in front._routes_react_router(projet / "frontend")}
    assert chemins == {"/solo"}


# --- 6. Non-régression : le catch-all RACINE garde sa convention react-router ("*", pas "/*") ---
def test_catch_all_racine_reste_etoile_sans_slash(tmp_path: Path) -> None:
    """Couvert aussi par `test_correctifs_20260811.py::test_front_reconnait_les_routes_react_router`
    (8 routes Produit-01) : la composition TF-1347 ne doit pas transformer `path="*"` racine en
    `/*` — seul un `*` IMBRIQUÉ sous un parent se compose normalement."""
    jsx = '<Routes><Route path="*" element={<NotFound />} /></Routes>'
    projet = _projet_react_router(tmp_path, jsx)
    chemins = {chemin for chemin, _fichier in front._routes_react_router(projet / "frontend")}
    assert chemins == {"*"}

    jsx_imbrique = """
    <Routes>
      <Route path="/admin" element={<AdminLayout />}>
        <Route path="*" element={<AdminNotFound />} />
      </Route>
    </Routes>
    """
    projet2 = _projet_react_router(tmp_path / "autre", jsx_imbrique)
    chemins2 = {chemin for chemin, _fichier in front._routes_react_router(projet2 / "frontend")}
    assert "/admin/*" in chemins2
