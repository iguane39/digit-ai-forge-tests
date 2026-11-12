"""TF-2402 — arbre de travail neuf : un préalable absent se lit « NON MESURABLE », pas « MANQUE ».

Fait remonté par l'agent du lot FT le 10/11/2026 et rejoué le 12/11/2026 sur `955454a` : dans un
arbre de travail sans `.venv` des bancs, sans `node_modules` ni `dist` du front, la section
`corpus` de la recette rendait 13 défauts « MANQUE » sur 23 (10 détectés) — des régressions
annoncées là où la mesure n'avait simplement pas eu lieu. Le mécanisme de TF-0299 (marqueur
`PREALABLE_ABSENT` dans le motif d'un pan, lu par `prealables_absents`) existait pour le démon de
conteneurs seulement ; les trois autres préalables le disaient en d'autres mots, que la recette ne
reconnaît pas.

Correction : le marqueur est porté par les motifs de `.venv` absent (pans api, data, migrations,
batch, fichiers, back), de `node_modules` absent (pan front) et de `dist` / `node_modules` / `npx`
absents (pans accessibilité, contraste, clavier, plancher, visuel). Il ne l'est PAS quand le front
a tous ses préalables et ne répond pas, ni pour une instance distante : absoudre un front qui ne
démarre pas serait le défaut symétrique.

Sens prouvés :
  - ROUGE  — sur l'état de départ, aucun de ces motifs ne porte le marqueur, `prealables_absents`
             rend `{}` et la recette écrit « MANQUE » ;
  - VERT   — chaque motif le porte et nomme ce qui manque et la commande qui le crée ;
  - CONTRE-ÉPREUVES — préalables présents, ou instance distante désignée : motif générique, sans
             marqueur ; un défaut d'un pan NON touché reste « MANQUE ».
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import execution
from forge_tests.adaptateurs import mutation
from recette import verifier_corpus as vc


@pytest.fixture(autouse=True)
def _caches_vides(monkeypatch: pytest.MonkeyPatch):
    for fonction in (execution.mesurer, execution.front_execute):
        fonction.cache_clear()
    monkeypatch.delenv("FORGE_TESTS_BASE_URL", raising=False)
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    monkeypatch.delenv("FORGE_TESTS_PYTHON", raising=False)
    yield
    for fonction in (execution.mesurer, execution.front_execute):
        fonction.cache_clear()


def _produit(racine: Path) -> Path:
    """Un produit comme un arbre de travail neuf le livre : sources et suite, aucun préalable."""
    (racine / "backend" / "app").mkdir(parents=True)
    (racine / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (racine / "backend" / "app" / "calcul.py").write_text(
        "def somme(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (racine / "backend" / "tests").mkdir()
    (racine / "backend" / "tests" / "test_calcul.py").write_text(
        "from app.calcul import somme\n\n\ndef test_somme():\n    assert somme(1, 2) == 3\n",
        encoding="utf-8",
    )
    (racine / "backend" / "pyproject.toml").write_text("[project]\nname='p'\n", encoding="utf-8")
    (racine / "frontend").mkdir()
    (racine / "frontend" / "package.json").write_text('{"name":"f"}', encoding="utf-8")
    return racine


# --- .venv absent -------------------------------------------------------------------------------
def test_rouge_sans_venv_le_motif_du_backend_porte_le_prealable(tmp_path: Path) -> None:
    produit = _produit(tmp_path)

    assert execution.mesurer(str(produit)) is None
    motif = execution.motif_indisponibilite(produit, "backend", "")

    assert execution.PREALABLE_ABSENT in motif
    assert "aucun environnement Python" in motif
    assert "uv sync" in motif


def test_rouge_sans_venv_le_pan_mutation_porte_le_prealable_en_dernier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le motif publié au rapport est le DERNIER `non_juge` : c'est lui que la recette lit."""
    monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
    produit = _produit(tmp_path)

    sortie = mutation.analyser(produit)

    assert sortie.verdict == "SKIP"
    assert execution.PREALABLE_ABSENT in sortie.non_juge[-1]
    assert "aucun muté" in sortie.non_juge[-1]


# --- node_modules absent ------------------------------------------------------------------------
def test_rouge_sans_node_modules_le_motif_du_front_porte_le_prealable(tmp_path: Path) -> None:
    produit = _produit(tmp_path)

    assert execution.front_execute(str(produit)) is None
    motif = execution.motif_indisponibilite(produit, "front", "")

    assert execution.PREALABLE_ABSENT in motif
    assert "node_modules" in motif and "npm ci" in motif


# --- dist / node_modules / npx absents : les cinq pans du front servi ---------------------------
def test_rouge_sans_dist_le_motif_du_front_non_servi_porte_le_prealable(tmp_path: Path) -> None:
    produit = _produit(tmp_path)
    (produit / "frontend" / "node_modules").mkdir()

    motif = execution.motif_front_non_servi(produit)

    assert execution.PREALABLE_ABSENT in motif
    assert "build absent" in motif and "npm run build" in motif
    assert "node_modules" not in motif, "ce qui est présent ne se reproche pas"
    assert "front non servi" in motif


def test_le_motif_nomme_chacun_des_preambles_manquants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    produit = _produit(tmp_path)
    monkeypatch.setattr(execution.shutil, "which", lambda _nom: None)

    motif = execution.motif_front_non_servi(produit)

    assert execution.PREALABLE_ABSENT in motif
    for attendu in ("node_modules", "build absent", "npx introuvable"):
        assert attendu in motif


def test_vert_prealables_presents_le_motif_reste_generique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contre-épreuve : le front a tout et ne répond pas — ce n'est pas un préalable, et le dire
    absoudrait un front qui ne démarre pas."""
    produit = _produit(tmp_path)
    (produit / "frontend" / "node_modules").mkdir()
    (produit / "frontend" / "dist").mkdir()
    monkeypatch.setattr(execution.shutil, "which", lambda nom: f"/bin/{nom}")

    motif = execution.motif_front_non_servi(produit)

    assert motif == execution.MOTIF_FRONT_NON_SERVI
    assert execution.PREALABLE_ABSENT not in motif


def test_vert_instance_distante_le_build_local_n_y_est_pour_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contre-épreuve : `FORGE_TESTS_BASE_URL` désigne une instance déjà servie ; son silence n'est
    pas un `dist` absent."""
    produit = _produit(tmp_path)
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "http://127.0.0.1:9")

    assert execution.motif_front_non_servi(produit) == execution.MOTIF_FRONT_NON_SERVI


def _brancher_pan(monkeypatch: pytest.MonkeyPatch, pan: str):
    """Une route à auditer, et un rendu qui ne capture rien : le cas « front non servi »."""
    import importlib

    module = importlib.import_module(f"forge_tests.adaptateurs.{pan}")
    if pan == "accessibilite":
        monkeypatch.setattr(module, "_routes", lambda _cible: ["/"])
        monkeypatch.setattr(module, "_capturer", lambda *_a, **_k: ({}, []))
    elif pan == "visuel":
        monkeypatch.setattr(module, "_routes", lambda _cible: ["/"])
        monkeypatch.setattr(module, "capturer", lambda _cible: {})
    else:
        monkeypatch.setattr(module.accessibilite, "routes_a_auditer", lambda _c: (["/"], "essai"))
        monkeypatch.setattr(module, "parcourir", lambda *_a, **_k: ({}, []))
        if pan in ("contraste", "plancher"):
            monkeypatch.setattr(
                module.contraste if pan == "plancher" else module, "_mesure_js",
                lambda: "() => ({})",
            )
    return module


@pytest.mark.parametrize("pan", ["accessibilite", "contraste", "clavier", "plancher", "visuel"])
def test_chaque_pan_du_front_servi_publie_le_motif_a_prealable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pan: str
) -> None:
    """Les cinq adaptateurs lisent le MÊME motif : un sixième copierait-il l'ancien texte ?"""
    module = _brancher_pan(monkeypatch, pan)
    produit = _produit(tmp_path)

    sortie = module.analyser(produit)

    assert sortie.verdict == "SKIP", (pan, sortie.verdict)
    assert execution.PREALABLE_ABSENT in sortie.non_juge[-1], (pan, sortie.non_juge[-1])
    assert "front non servi" in sortie.non_juge[-1]


# --- La recette lit ces motifs et dit « NON MESURABLE » ----------------------------------------
def _rapport(motifs: dict[str, str]) -> dict:
    return {
        "findings": [],
        "motifs_non_couverture": motifs,
        "non_testables": [],
        "modules": [{"module": "app/x.py", "exerce": True}],
        "seuils": {"couverture_surface_api": {"valeur": 1.0}},
        "pans_non_couverts": [],
        "verdict": "PARTIEL",
    }


def test_la_recette_ecrit_non_mesurable_pour_les_trois_preambles_d_un_arbre_neuf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """De bout en bout : les motifs RÉELS d'un arbre neuf, lus par la recette."""
    produit = _produit(tmp_path)
    execution.mesurer(str(produit))
    execution.front_execute(str(produit))
    motifs = {
        "api": "api : 33 elements INVENTORIES mais couverture non mesurable — "
        + execution.motif_indisponibilite(produit, "backend", ""),
        "front": "front : 25 elements INVENTORIES mais couverture non mesurable — "
        + execution.motif_indisponibilite(produit, "front", ""),
        "accessibilite": execution.motif_front_non_servi(produit),
    }
    rapport = _rapport(motifs)

    assert set(vc.prealables_absents({"rouge": rapport})["rouge"]) == set(motifs)
    attendus = [code for code, pan, *_reste in vc.CORPUS if pan in motifs]
    assert attendus
    echecs = vc.verifier_corpus_des_bancs(
        rapport, _rapport({}), [], {}, vc.prealables_absents({"rouge": rapport})
    )
    sortie = capsys.readouterr().out

    for code in attendus:
        assert f"[NON MESURABLE] {code}" in sortie, sortie
        assert f"[MANQUE ] {code}" not in sortie
    # Contre-épreuve : un défaut d'un pan non touché reste un MANQUE.
    assert "[MANQUE ] H-14" in sortie
    assert echecs == len(vc.CORPUS) - len(attendus)


# --- Un pan qui rend FAIL sur un constat statique, sa couverture n'ayant pas pu être mesurée -----
_LIGNE_BATCH = (
    f"batch : 9 branches/rejets INVENTORIES mais couverture non mesurable — "
    f"{execution.PREALABLE_ABSENT} — aucun environnement Python dans le projet analysé"
)


def test_un_pan_fail_dont_la_couverture_manque_faute_de_preambule_est_non_mesurable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le pan `batch` rend FAIL sur un déclencheur cassé (constat statique) : son verdict n'est pas
    SKIP, il n'entre pas dans `motifs_non_couverture`, et H-06 s'écrivait « MANQUE » dans un arbre
    neuf. Le marqueur de sa ligne de `non_juge`, préfixée par son nom, suffit à la recette."""
    rapport = {**_rapport({}), "non_juge": [_LIGNE_BATCH, "securite : autre chose"]}

    releve = vc.prealables_absents({"rouge": rapport})

    assert set(releve["rouge"]) == {"batch"}
    vc.verifier_corpus_des_bancs(rapport, _rapport({}), [], {}, releve)
    sortie = capsys.readouterr().out
    assert "[NON MESURABLE] H-06" in sortie and "[MANQUE ] H-06" not in sortie
    # Contre-épreuve : le défaut d'un autre pan, lui, reste un MANQUE.
    assert "[MANQUE ] H-14" in sortie


@pytest.mark.parametrize(
    "ligne",
    [
        # pas de marqueur : une couverture non mesurée pour une autre raison reste un MANQUE
        "batch : 9 branches/rejets INVENTORIES mais couverture non mesurable — suite rouge",
        # marqueur, mais le préfixe n'est pas un pan du corpus
        f"mutation : {execution.PREALABLE_ABSENT} — aucun muté",
        f"securite/sast : {execution.PREALABLE_ABSENT}",
    ],
)
def test_contre_epreuve_seule_une_ligne_de_pan_a_marqueur_vaut_preambule(ligne: str) -> None:
    rapport = {**_rapport({}), "non_juge": [ligne]}

    assert vc.prealables_absents({"rouge": rapport}) == {}
