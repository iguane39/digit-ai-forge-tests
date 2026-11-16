"""TF-2670 — le pan i18n ne mesurait ni un site rendu côté serveur ni la péremption.

Fait remonté par le site public (lot factory-digit-ai-fr 20261116e, hors run, ledger seq 431) : un
site FastAPI rendu côté serveur, aux contenus en Markdown, faisait passer le pan i18n en SKIP
(« aucun build servi lu ») sans dire comment le mesurer, et aucun contrôle ne signalait une
traduction périmée quand sa source change.

Deux volets :
  1. la RECETTE d'export statique d'un site rendu côté serveur est écrite au pan (consigne du pan,
     motif du SKIP, README) : un lecteur sait quoi faire pour que le pan le mesure ;
  2. un contrôle de PÉREMPTION par empreinte de la source : le projet déclare, pour chaque
     traduction, sa source et l'empreinte qu'elle avait quand la traduction a été faite
     (`FORGE_TESTS_I18N_PEREMPTION`) ; une source modifiée depuis rend un constat.

Sens prouvés :
  - ROUGE : une source modifiée après sa traduction rend un constat de péremption ; une source ou
    une traduction introuvable aussi (une déclaration cassée ne se lit pas « à jour ») ;
  - VERT : une source inchangée (fins de ligne CRLF ou LF) ne rend rien, et le pan PASSE sans
    build servi, puisqu'il a mesuré ;
  - CONTRE-ÉPREUVES : rien de déclaré, rien de jugé, et le rapport le dit ; une déclaration
    illisible n'emporte pas l'audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests import peremption_i18n
from forge_tests.adaptateurs import i18n

README = Path(__file__).resolve().parents[1] / "README.md"
SOURCE = "# Tarifs\n\nLe forfait démarre à 40 euros par mois.\n"
TRADUCTION = "# Pricing\n\nThe plan starts at 40 euros a month.\n"


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for nom in ("FORGE_TESTS_I18N_PEREMPTION", "FORGE_TESTS_I18N_BUILD",
                "FORGE_TESTS_I18N_ROUTES", "FORGE_TESTS_I18N_CHAINES"):
        monkeypatch.delenv(nom, raising=False)


def _site(tmp_path: Path, source: str = SOURCE) -> Path:
    """Un site rendu côté serveur : des contenus Markdown par langue, aucun build."""
    for langue, texte in (("fr", source), ("en", TRADUCTION)):
        page = tmp_path / "contenu" / langue / "tarifs.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(texte, encoding="utf-8", newline="")
    return tmp_path


def _declarer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empreinte: str, **surcharge: str
) -> Path:
    entree = {
        "traduction": "contenu/en/tarifs.md",
        "source": "contenu/fr/tarifs.md",
        "empreinte": empreinte,
    }
    entree.update(surcharge)
    fichier = tmp_path / "forge" / "peremption-i18n.json"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps({"traductions": [entree]}), encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_PEREMPTION", str(fichier))
    return fichier


def _constats_de_peremption(sortie) -> list:
    return [f for f in sortie.findings if f.id.startswith("i18n:peremption:")]


# --- ROUGE : la source a changé depuis la traduction ---------------------------------------------
def test_une_source_modifiee_apres_sa_traduction_rend_un_constat_de_peremption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _site(tmp_path)
    scellee = peremption_i18n.empreinte(site / "contenu" / "fr" / "tarifs.md")
    _declarer(site, monkeypatch, scellee)
    (site / "contenu" / "fr" / "tarifs.md").write_text(
        SOURCE.replace("40 euros", "50 euros"), encoding="utf-8"
    )

    sortie = i18n.analyser(site)

    constats = _constats_de_peremption(sortie)
    assert [f.id for f in constats] == ["i18n:peremption:contenu/en/tarifs.md"]
    message = constats[0].message
    assert "contenu/fr/tarifs.md" in message and "périmée" in message
    assert scellee[:12] in message
    assert sortie.verdict == "FAIL"


@pytest.mark.parametrize("manquant", ["traduction", "source"])
def test_une_declaration_dont_un_fichier_manque_rend_un_constat_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manquant: str
) -> None:
    site = _site(tmp_path)
    _declarer(site, monkeypatch, peremption_i18n.empreinte(site / "contenu" / "fr" / "tarifs.md"))
    chemin = {"traduction": "contenu/en/tarifs.md", "source": "contenu/fr/tarifs.md"}[manquant]
    (site / chemin).unlink()

    sortie = i18n.analyser(site)

    constats = _constats_de_peremption(sortie)
    assert len(constats) == 1 and manquant in constats[0].message
    assert "introuvable" in constats[0].message


# --- VERT : la source n'a pas bougé --------------------------------------------------------------
def test_une_source_inchangee_ne_rend_rien_et_le_pan_passe_sans_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _site(tmp_path)
    _declarer(site, monkeypatch, peremption_i18n.empreinte(site / "contenu" / "fr" / "tarifs.md"))

    sortie = i18n.analyser(site)

    assert _constats_de_peremption(sortie) == []
    assert sortie.verdict == "PASS"
    assert any("péremption" in ligne and "1 traduction" in ligne for ligne in sortie.non_juge)


def test_l_empreinte_ne_depend_pas_des_fins_de_ligne(tmp_path: Path) -> None:
    """Un dépôt extrait sous Windows (CRLF) ne périme pas ses traductions d'un coup."""
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(SOURCE.encode("utf-8"))
    crlf.write_bytes(SOURCE.replace("\n", "\r\n").encode("utf-8"))

    assert peremption_i18n.empreinte(lf) == peremption_i18n.empreinte(crlf)


def test_l_empreinte_change_avec_le_contenu(tmp_path: Path) -> None:
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text(SOURCE, encoding="utf-8")
    b.write_text(SOURCE.replace("40", "41"), encoding="utf-8")

    assert peremption_i18n.empreinte(a) != peremption_i18n.empreinte(b)


# --- Contre-épreuves -----------------------------------------------------------------------------
def test_rien_de_declare_rien_de_juge_et_le_rapport_le_dit(tmp_path: Path) -> None:
    site = _site(tmp_path)

    sortie = i18n.analyser(site)

    assert _constats_de_peremption(sortie) == []
    assert any("FORGE_TESTS_I18N_PEREMPTION" in ligne for ligne in sortie.non_juge)


def test_une_declaration_illisible_n_emporte_pas_l_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _site(tmp_path)
    cassee = site / "casse.json"
    cassee.write_text("{ceci n'est pas du JSON", encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_PEREMPTION", str(cassee))

    sortie = i18n.analyser(site)

    assert _constats_de_peremption(sortie) == []
    assert any("FORGE_TESTS_I18N_PEREMPTION" in ligne and "illisible" in ligne
               for ligne in sortie.non_juge)


def test_un_chemin_declare_hors_du_projet_n_est_pas_lu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G-1 et périmètre : une déclaration ne fait pas lire un fichier hors de la racine auditée."""
    site = _site(tmp_path / "projet")
    (tmp_path / "secret.md").write_text("hors du projet", encoding="utf-8")
    _declarer(site, monkeypatch, "0" * 64, source="../secret.md")

    sortie = i18n.analyser(site)

    constats = _constats_de_peremption(sortie)
    assert len(constats) == 1 and "hors du projet" in constats[0].message


# --- La recette d'export statique ----------------------------------------------------------------
def test_le_motif_du_skip_nomme_la_recette_d_export_statique(tmp_path: Path) -> None:
    """Un site rendu côté serveur, multilingue par ses sources (dossier de traductions), sans
    build : le pan ne mesure rien, et dit comment le faire mesurer."""
    (tmp_path / "i18n").mkdir()
    (tmp_path / "i18n" / "fr.json").write_text("{}", encoding="utf-8")
    (tmp_path / "app").mkdir()

    sortie = i18n.analyser(tmp_path)

    assert sortie.verdict == "SKIP"
    motif = sortie.non_juge[-1]
    assert "rendu côté serveur" in motif and "export statique" in motif
    assert "FORGE_TESTS_I18N_BUILD" in motif and "README" in motif


def test_la_consigne_du_pan_porte_la_recette() -> None:
    assert "export statique" in i18n.POUR_COUVRIR


def test_le_readme_documente_la_recette_et_la_peremption() -> None:
    texte = README.read_text(encoding="utf-8")
    assert "Site rendu côté serveur" in texte
    assert "FORGE_TESTS_I18N_PEREMPTION" in texte
    assert "python -m forge_tests.peremption_i18n" in texte
