"""TF-2222 — la pile se reconnaît à ses manifestes, pas au nom de son dossier.

Fait remonté (Produit-81, lot du 05/11/2026, RP-1) : forge-tests a rendu PARTIEL (sortie 3) sur un
produit dont le front React vit dans `FRONT/` et le back .NET dans `BACK/` : il cherchait
`frontend/node_modules` et un `.venv`, et il a émis 46 constats « destination absente » sur des
routes React qu'il n'avait pas inventoriées.

Décision du 06/11/2026 : reconnaître le front par son `package.json` et le back par ses manifestes
(`*.csproj`), et ne pas émettre de constat « destination absente » quand l'inventaire des routes est
vide. Ce que cette campagne livre, et ce qu'elle ne livre pas :

  - LIVRÉ    — le front est reconnu à son `package.json` (cascade : manifeste projet, `frontend`,
               découverte) ; le back .NET est reconnu à ses `*.csproj` et son motif le dit au
               lieu de chercher un `.venv` ; « destination absente » est suspendu, et dit, quand
               un front
               JavaScript n'a aucune route inventoriée ;
  - PAS LIVRÉ — l'adaptateur qui joue `dotnet test` : aucun pan .NET n'existe dans cette forge.
               Le rapport le dit (`motif_pile_non_python`).

Sens prouvés : ROUGE (le défaut du lot, rejoué) et VERT (corrigé), avec contre-épreuve (un lien faux
d'un site sans front JavaScript reste accusé).
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import disposition, execution
from forge_tests.adaptateurs import front, interface


def _ecrire(racine: Path, relatif: str, texte: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


def _package(racine: Path, dossier: str, dependances: dict[str, str]) -> None:
    contenu = json.dumps({"name": "x", "dependencies": dependances})
    _ecrire(racine, f"{dossier}/package.json", contenu)


ROUTES_REACT_ROUTER = (
    "import { Route, Routes } from 'react-router-dom';\n"
    "export const App = () => (<Routes>\n"
    "  <Route path=\"/tableau\" element={<Tableau />} />\n"
    "  <Route path=\"/demandes\" element={<Demandes />} />\n"
    "</Routes>);\n"
)
LIEN_VERS_TABLEAU = (
    "export const Menu = () => (<nav><a href=\"/tableau\">Tableau</a>"
    "<a href=\"/introuvable\">Fantôme</a></nav>);\n"
)


# --- Le front se reconnaît à son package.json ----------------------------------------------------
def test_rouge_avant_le_nom_d_un_dossier_etait_la_seule_reconnaissance(tmp_path: Path) -> None:
    """Le défaut du lot, rejoué : sans `frontend/`, le pan front n'inventoriait aucune route."""
    _package(tmp_path, "FRONT", {"react": "^18", "react-router-dom": "^6"})
    _ecrire(tmp_path, "FRONT/src/App.tsx", ROUTES_REACT_ROUTER)
    assert front.inventaire(tmp_path) != [], "le front de FRONT/ doit être inventorié"
    ids = {e.id for e in front.inventaire(tmp_path)}
    assert {"route:/tableau", "route:/demandes"} <= ids


def test_la_racine_du_front_suit_la_cascade(tmp_path: Path) -> None:
    # 1. repli historique rendu même absent
    assert disposition.racine_front(tmp_path) == tmp_path / "frontend"
    assert disposition.front_decouvert(tmp_path) is False
    # 2. découverte par manifeste, jusqu'à la profondeur 2
    _package(tmp_path, "FRONT", {"react": "^18"})
    assert disposition.racine_front(tmp_path) == tmp_path / "FRONT"
    assert disposition.front_decouvert(tmp_path) is True
    # 3. `frontend` prime quand il existe (convention historique, rien ne change pour l'existant)
    (tmp_path / "frontend").mkdir()
    assert disposition.racine_front(tmp_path) == tmp_path / "frontend"
    assert disposition.front_decouvert(tmp_path) is False


def test_le_manifeste_du_projet_prime_sur_la_decouverte(tmp_path: Path) -> None:
    _package(tmp_path, "FRONT", {"react": "^18"})
    _ecrire(tmp_path, ".forge/profile.toml", '[racines]\nfront = "web"\n')
    assert disposition.racine_front(tmp_path) == tmp_path / "web"


def test_un_package_json_sans_dependance_de_front_n_est_pas_un_front(tmp_path: Path) -> None:
    """Contre-épreuve : un outillage Node (lint, scripts) n'est pas un front."""
    _package(tmp_path, "outils", {"eslint": "^9", "prettier": "^3"})
    assert disposition.a_un_front_javascript(tmp_path) is False
    assert disposition.racine_front(tmp_path) == tmp_path / "frontend"


def test_les_dependances_ne_sont_pas_des_candidats(tmp_path: Path) -> None:
    _package(tmp_path, "node_modules/react", {"react": "^18"})
    assert disposition.a_un_front_javascript(tmp_path) is False


def test_la_suite_e2e_du_front_cherche_node_modules_dans_le_front_reconnu(tmp_path: Path) -> None:
    """Le motif publié nomme le dossier RECONNU (FRONT/), pas un `frontend/` inexistant."""
    _package(tmp_path, "FRONT", {"react": "^18"})
    execution.front_execute.cache_clear()
    assert execution.front_execute(str(tmp_path)) is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "FRONT" in motif and "node_modules" in motif
    assert "frontend" not in motif.replace("FRONT", "")


# --- Le back .NET se reconnaît à ses manifestes --------------------------------------------------
def test_le_back_dotnet_est_nomme_au_lieu_de_chercher_un_venv(tmp_path: Path) -> None:
    _ecrire(tmp_path, "BACK/Api/Api.csproj", "<Project Sdk=\"Microsoft.NET.Sdk.Web\" />")
    _ecrire(tmp_path, "BACK/Api.Tests/Api.Tests.csproj", "<Project Sdk=\"Microsoft.NET.Sdk\" />")
    projets = [p.name for p in disposition.manifestes_dotnet(tmp_path)]
    assert projets == ["Api.csproj", "Api.Tests.csproj"]
    motif = disposition.motif_pile_non_python(tmp_path)
    assert "back .NET reconnu" in motif and "2 projet(s)" in motif
    assert "PAS d'adaptateur .NET" in motif and "dotnet test" in motif


def test_la_mesure_du_back_dit_dotnet_et_plus_aucun_venv_absent(tmp_path: Path) -> None:
    _ecrire(tmp_path, "BACK/Api/Api.csproj", "<Project />")
    execution.mesurer.cache_clear() if hasattr(execution.mesurer, "cache_clear") else None
    assert execution.mesurer(str(tmp_path)) is None
    motif = execution.motif_indisponibilite(tmp_path, "backend", "")
    assert "back .NET reconnu" in motif
    assert "aucun environnement Python" not in motif


def test_sans_manifeste_dotnet_le_motif_historique_reste(tmp_path: Path) -> None:
    """Contre-épreuve : un projet sans `.csproj` garde son motif d'environnement Python absent."""
    assert disposition.motif_pile_non_python(tmp_path) == ""
    (tmp_path / "x").mkdir()
    execution.mesurer.cache_clear() if hasattr(execution.mesurer, "cache_clear") else None
    assert execution.mesurer(str(tmp_path)) is None
    assert "aucun environnement Python" in execution.motif_indisponibilite(tmp_path, "backend", "")


# --- « destination absente » sur un inventaire vide ----------------------------------------------
def _liens_faux(racine: Path) -> list[str]:
    releve, _exprimee, _declarations = interface._relever_composants(racine)
    return [r["motif"] for r in releve if r["motif"] and "absente" in r["motif"]]


def test_rouge_un_front_dont_les_routes_ne_sont_pas_inventoriees_n_accuse_aucun_lien(
    tmp_path: Path,
) -> None:
    """46 liens accusés sur un front React non inventorié : le contrôle est suspendu, et le dit."""
    _package(tmp_path, "FRONT", {"react": "^18"})
    # Routeur par objet : aucune des grammaires lues ne le reconnaît.
    _ecrire(tmp_path, "FRONT/src/router.tsx",
            "export const r = createBrowserRouter([{ path: '/tableau', element: <T/> }]);\n")
    _ecrire(tmp_path, "FRONT/src/Menu.tsx", LIEN_VERS_TABLEAU)
    _ecrire(tmp_path, "FRONT/public/index.html", "<html><body>x</body></html>")
    assert _liens_faux(tmp_path) == []
    _releve, _exprimee, declarations = interface._relever_composants(tmp_path)
    assert any("SUSPENDU" in d and "AUCUNE de ses routes" in d for d in declarations)


def test_contre_epreuve_un_site_sans_front_javascript_garde_son_controle(tmp_path: Path) -> None:
    """Sans `package.json` de front, l'arborescence statique est complète : un lien faux reste
    accusé. Le correctif ne désarme pas le contrôle partout."""
    _ecrire(tmp_path, "index.html", "<html><body>x</body></html>")
    _ecrire(tmp_path, "tableau/index.html", "<html><body>t</body></html>")
    _ecrire(tmp_path, "src/Menu.tsx", LIEN_VERS_TABLEAU)
    faux = _liens_faux(tmp_path)
    assert len(faux) == 1 and "/introuvable" in faux[0]


def test_vert_un_front_inventorie_garde_le_controle_et_accuse_le_vrai_lien_faux(
    tmp_path: Path,
) -> None:
    """Le remède joué : dès que les routes sont inventoriées (react-router), le contrôle reprend
    et ne garde que le lien réellement faux."""
    _package(tmp_path, "FRONT", {"react": "^18", "react-router-dom": "^6"})
    _ecrire(tmp_path, "FRONT/src/App.tsx", ROUTES_REACT_ROUTER)
    _ecrire(tmp_path, "FRONT/src/Menu.tsx", LIEN_VERS_TABLEAU)
    faux = _liens_faux(tmp_path)
    assert len(faux) == 1 and "/introuvable" in faux[0]
