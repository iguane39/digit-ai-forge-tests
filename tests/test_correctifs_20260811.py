"""Quatre défauts payés en réel sur Produit-01 le 11/08 (TF-0097 à TF-0100).

Chaque défaut avait la même forme : l adaptateur suppose une arborescence ou une cause au lieu
de lire ce que le projet déclare ou de constater les faits — d où un FAUX NÉGATIF (surface non
mesurée à tort) ou un motif qui accuse la mauvaise cause. Aucun banc existant ne peut les
exercer (le corpus des bancs porte déjà des conventions reconnues) : les cas sont donc vérifiés
ici, sur des arborescences minimales reproduisant chaque défaut constaté sur pièces.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import execution
from forge_tests.adaptateurs import data, front, migrations, securite, visuel


# --- TF-0097 — migrations : lire alembic.ini plutôt que supposer trois chemins -----------------
def test_script_location_lu_dans_alembic_ini(tmp_path: Path) -> None:
    """Alembic déclare son dossier via `script_location` — la forge doit le LIRE, pas le deviner.

    Reproduit le cas Produit-01 : `backend/alembic.ini` déclare `script_location = migrations`,
    ce qui pointe vers `backend/migrations/versions/` — un chemin qu AUCUN des trois motifs
    codés en dur (backend/app/alembic/versions, backend/alembic/versions, alembic/versions) ne
    couvre. Sans la lecture de la configuration, ces 9 migrations restaient invisibles.
    """
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "alembic.ini").write_text(
        "[alembic]\nscript_location = migrations\n", encoding="utf-8"
    )
    versions = backend / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "__init__.py").write_text("", encoding="utf-8")
    (versions / "0001_init.py").write_text(
        "def upgrade(): pass\ndef downgrade(): pass\n", encoding="utf-8"
    )
    (versions / "0002_suite.py").write_text(
        "def upgrade(): pass\ndef downgrade(): pass\n", encoding="utf-8"
    )

    trouve = migrations._versions_alembic(tmp_path)

    # ROUGE implicite : aucun des trois chemins codés en dur ne correspond à `migrations/` —
    # sans la lecture de `script_location`, cette liste serait vide (c est le défaut constaté).
    assert [p.name for p in trouve] == ["0001_init.py", "0002_suite.py"]


def test_conventions_codees_en_dur_restent_un_repli(tmp_path: Path) -> None:
    """Sans alembic.ini, les trois chemins conventionnels fonctionnent (non-régression)."""
    dossier = tmp_path / "backend" / "alembic" / "versions"
    dossier.mkdir(parents=True)
    (dossier / "0001_x.py").write_text("def upgrade(): pass\n", encoding="utf-8")

    trouve = migrations._versions_alembic(tmp_path)

    assert [p.name for p in trouve] == ["0001_x.py"]


def test_motif_distingue_surface_non_localisee_de_surface_absente(
    tmp_path: Path, monkeypatch
) -> None:
    """script_location déclaré mais dossier introuvable : « non localisée », pas « absente »."""
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "alembic.ini").write_text(
        "[alembic]\nscript_location = chemin/qui/n/existe/pas\n", encoding="utf-8"
    )
    monkeypatch.setattr(migrations, "instructions_sql", lambda cible: [])
    monkeypatch.setattr(migrations, "sources_sql", lambda cible: [])

    motif = migrations._motif_sans_migration(tmp_path)

    assert "NON LOCALISEE" in motif
    assert "chemin" in motif and "existe" in motif and "pas" in motif


def test_motif_surface_reellement_absente_reste_le_motif_generique(
    tmp_path: Path, monkeypatch
) -> None:
    """Sans aucune déclaration Alembic, le motif reste celui d une surface réellement absente."""
    monkeypatch.setattr(migrations, "instructions_sql", lambda cible: [])
    monkeypatch.setattr(migrations, "sources_sql", lambda cible: [])

    motif = migrations._motif_sans_migration(tmp_path)

    assert "NON LOCALISEE" not in motif
    assert "sans couche SQL observable" in motif


# --- TF-0097 — data : découverte récursive des modèles ORM ------------------------------------
def test_fichiers_modeles_trouve_db_models(tmp_path: Path) -> None:
    """`backend/app/db/models.py` doit être vu — pas seulement `backend/app/models.py`."""
    modeles = tmp_path / "backend" / "app" / "db" / "models.py"
    modeles.parent.mkdir(parents=True)
    modeles.write_text(
        'class Compte(Base):\n'
        '    id = Column(Integer, primary_key=True)\n'
        '    nom = Column(String, nullable=False)\n',
        encoding="utf-8",
    )

    trouves = data._fichiers_modeles(tmp_path)

    # ROUGE implicite : le seul chemin conventionnel `backend/app/models.py` n existe pas ici —
    # avant le correctif, cette liste aurait été vide (le défaut constaté sur Produit-01).
    assert trouves == [modeles]


def test_fichiers_modeles_priorite_aux_chemins_conventionnels(tmp_path: Path) -> None:
    """Les deux chemins conventionnels priment sur la recherche récursive."""
    direct = tmp_path / "backend" / "app" / "models.py"
    direct.parent.mkdir(parents=True)
    direct.write_text("class A(Base): pass\n", encoding="utf-8")
    imbrique = tmp_path / "backend" / "app" / "profond" / "models.py"
    imbrique.parent.mkdir(parents=True)
    imbrique.write_text("class B(Base): pass\n", encoding="utf-8")

    trouves = data._fichiers_modeles(tmp_path)

    assert trouves == [direct]


def test_fichiers_modeles_recursif_exclut_les_dependances(tmp_path: Path) -> None:
    """La recherche récursive ignore les dossiers de dépendances et de tests."""
    reel = tmp_path / "backend" / "app" / "domaine" / "models.py"
    reel.parent.mkdir(parents=True)
    reel.write_text("class C(Base): pass\n", encoding="utf-8")
    faux = tmp_path / "backend" / "app" / "tests" / "models.py"
    faux.parent.mkdir(parents=True)
    faux.write_text("class Faux(Base): pass\n", encoding="utf-8")

    trouves = data._fichiers_modeles(tmp_path)

    assert trouves == [reel]


# --- TF-0098 — front : ne pas lancer `npx playwright test` sans config déclarée ----------------
def test_front_execute_sans_config_playwright_le_dit(tmp_path: Path) -> None:
    """Sans playwright.config, la cause publiée est « aucune suite e2e », jamais un échec."""
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    execution.front_execute.cache_clear()

    resultat = execution.front_execute(str(tmp_path))

    assert resultat is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    # ROUGE implicite : avant le correctif, le code passait ce garde et lançait
    # `npx playwright test`, qui ramasse les *.test.tsx de vitest et échoue — le motif publié
    # aurait été « la suite e2e s est terminée en échec », pas « aucune suite e2e déclarée ».
    assert "aucune suite e2e" in motif.lower()
    assert "playwright.config" in motif


def test_front_execute_avec_config_ne_confond_plus_les_deux_causes(
    tmp_path: Path, monkeypatch
) -> None:
    """Une config PRÉSENTE ne doit plus jamais produire le motif « aucune suite e2e »."""
    front_dir = tmp_path / "frontend"
    (front_dir / "node_modules").mkdir(parents=True)
    (front_dir / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    # npx forcé absent : arrête le chemin avant tout lancement réel de process, tout en
    # restant sur une cause DIFFÉRENTE de « aucune suite e2e » — c est ce qui prouve que le
    # contrôle discrimine les deux causes au lieu de les confondre.
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: None)
    execution.front_execute.cache_clear()

    resultat = execution.front_execute(str(tmp_path))

    assert resultat is None
    motif = execution.motif_indisponibilite(tmp_path, "front", "")
    assert "aucune suite e2e" not in motif.lower()
    assert "npx introuvable" in motif.lower()


# --- TF-0100 — front : reconnaître les routes react-router -------------------------------------
def test_front_reconnait_les_routes_react_router(tmp_path: Path) -> None:
    """8 routes déclarées en `<Route path="...">` (react-router) — comme sur Produit-01."""
    app_tsx = tmp_path / "frontend" / "src" / "App.tsx"
    app_tsx.parent.mkdir(parents=True)
    app_tsx.write_text(
        """
import { Routes, Route } from "react-router-dom";

export default function App() {
  return (
    <Routes>
      <Route path="/callback" element={<Callback />} />
      <Route path="/" element={<Home />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="/demandes" element={<Demandes />} />
      <Route path="/demandes/new" element={<New />} />
      <Route path="/demandes/:id" element={<Detail />} />
      <Route path="/demandes/:id/review" element={<Review />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
""",
        encoding="utf-8",
    )

    elements = front.inventaire(tmp_path)
    routes = {e.id for e in elements if e.id.startswith("route:")}

    # ROUGE implicite : ni `routes.jsx` ni la convention TanStack n existent ici — avant le
    # correctif, `routes` aurait été un ensemble VIDE (le défaut constaté : 0 route inventoriée
    # pour 8 routes réellement déclarées).
    assert routes == {
        "route:/callback", "route:/", "route:/admin", "route:/demandes",
        "route:/demandes/new", "route:/demandes/:id", "route:/demandes/:id/review", "route:*",
    }


def test_front_react_router_ne_double_compte_pas_avec_routes_jsx(tmp_path: Path) -> None:
    """Une route déjà déclarée par `routes.jsx` n est pas répétée par la lecture react-router."""
    src = tmp_path / "frontend" / "src"
    src.mkdir(parents=True)
    (src / "routes.jsx").write_text('const routes = [{ path: "/x" }];\n', encoding="utf-8")
    (src / "App.tsx").write_text('<Route path="/x" element={<X />} />\n', encoding="utf-8")

    elements = front.inventaire(tmp_path)
    routes = [e.id for e in elements if e.id == "route:/x"]

    assert routes == ["route:/x"]


# --- TF-0100 — visuel : le SKIP porte la cause CONSTATÉE, jamais une cause supposée ------------
def test_visuel_aucune_route_nest_pas_confondu_avec_front_non_servi(
    tmp_path: Path, monkeypatch
) -> None:
    """0 route inventoriée : le motif dit « aucune route », pas « build absent / npm »."""
    monkeypatch.setattr(visuel, "_routes", lambda cible: [])

    sortie = visuel.analyser(tmp_path)

    assert sortie.verdict == "SKIP"
    assert any("aucune route" in m for m in sortie.non_juge)
    # ROUGE implicite : avant le correctif, ce cas tombait dans la même branche que le front
    # réellement non servi et publiait ce motif — accusant à tort build/npm/navigateur alors
    # que les trois étaient présents (vérifié sur pièces le 11/08).
    assert not any("front non servi" in m for m in sortie.non_juge)


def test_visuel_front_non_servi_reste_signale_distinctement(tmp_path: Path, monkeypatch) -> None:
    """Un front réellement non servi (routes présentes, capture vide) garde SON motif propre."""
    monkeypatch.setattr(visuel, "_routes", lambda cible: ["/accueil"])
    monkeypatch.setattr(visuel, "capturer", lambda cible: {})

    sortie = visuel.analyser(tmp_path)

    assert sortie.verdict == "SKIP"
    assert any("front non servi" in m for m in sortie.non_juge)
    assert not any(m == "aucune route a capturer" for m in sortie.non_juge)


# --- TF-0099 — sécurité : borner le scan aux sources du produit --------------------------------
def test_sources_du_produit_exclut_les_dependances(tmp_path: Path) -> None:
    """La copie filtrée ne contient jamais `.venv` — seulement les sources du produit."""
    application = tmp_path / "backend"
    (application / "app").mkdir(parents=True)
    (application / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    venv = application / ".venv" / "lib" / "site-packages" / "cryptography"
    venv.mkdir(parents=True)
    (venv / "__init__.py").write_text("AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8")

    scan = securite._sources_du_produit(application, tmp_path / "brouillon")

    # ROUGE implicite : sans bornage, `.venv` (et son faux « secret ») aurait été copié tel quel
    # et resterait visible à l outil délégué — c est exactement le cas constaté (219 hits, 100 %
    # sous .venv/, zéro dans le produit).
    assert not (scan / ".venv").exists()
    assert (scan / "app" / "main.py").is_file()


def test_analyser_ne_transmet_jamais_venv_a_loracle(tmp_path: Path, monkeypatch) -> None:
    """Bout en bout : l oracle délégué ne reçoit JAMAIS un dossier contenant `.venv`."""
    application = tmp_path / "backend"
    (application / "app").mkdir(parents=True)
    (application / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (application / ".venv" / "lib").mkdir(parents=True)
    (application / ".venv" / "lib" / "secret.py").write_text(
        "AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8"
    )
    racine = tmp_path / "oracles"
    racine.mkdir()
    (racine / "oracle-secrets.mjs").write_text("", encoding="utf-8")

    recus: list[Path] = []

    def _lancer_espion(script: Path, cible: Path) -> dict:
        recus.append(cible)
        return {"verdict": "PASS", "non_juge": [], "findings": []}

    monkeypatch.setattr(securite, "_racine_oracles", lambda: racine)
    monkeypatch.setattr(securite, "_lancer", _lancer_espion)

    sortie = securite.analyser(tmp_path)

    assert recus, "l oracle-secrets aurait du etre invoque"
    # ROUGE implicite : avant le correctif, `_lancer` recevait `application` TEL QUEL — un
    # dossier qui CONTIENT `.venv`. C est cette transmission non bornée que gitleaks parcourait
    # sans exclusion, produisant les 219 « fuites » toutes situées dans des dépendances.
    for cible_recue in recus:
        assert not (cible_recue / ".venv").exists()
    assert sortie.verdict == "PASS"
