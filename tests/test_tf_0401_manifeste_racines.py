"""TF-0401 (RF-3, lot Produit-09) — le manifeste opposable était lu par AUCUN code de la forge.

Le fait, relevé au code le 20/08 sur HEAD 7d3ca37 : `profile.toml` = 0 occurrence dans le code
(`--include=*.py`), alors que la doctrine de la forge DÉCRIT la cascade « manifeste → profil
curé → inférence » et que le pilot présente P-18 comme primant sur toute détection. Ce qui
décidait réellement : `_ORDRE_CANDIDATS = ("backend", ".")` et `banc / "frontend"`, en dur.
L'arborescence de SCC.FR est `back/` + `front/` : non vue, quel que soit le manifeste livré —
un audit pouvait mesurer un dossier vide et rendre un verdict d'apparence normale.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.disposition import (
    MANIFESTE_RELATIF,
    _decider_racine,
    racine_execution,
    racines_declarees,
)


def _manifeste(racine: Path, contenu: str) -> None:
    chemin = racine / MANIFESTE_RELATIF
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


def test_le_cas_SCC_FR_une_arborescence_back_front_est_VUE_par_manifeste(tmp_path: Path) -> None:
    """Le cas fondateur : back/ + front/, fixés au dossier, invisibles à la détection."""
    (tmp_path / "back" / "tests").mkdir(parents=True)
    (tmp_path / "front").mkdir()
    _manifeste(tmp_path, '[racines]\nexecution = "back"\nfront = "front"\n')

    racine, regle, _ = _decider_racine(tmp_path)

    assert racine == tmp_path / "back"
    assert "manifeste" in regle and "profile.toml" in regle, "la provenance est PUBLIÉE"


def test_sans_manifeste_rien_ne_change(tmp_path: Path) -> None:
    """Garde anti-régression : aucun projet déjà mesuré ne change de racine."""
    (tmp_path / "backend" / "tests").mkdir(parents=True)

    assert racine_execution(tmp_path) == tmp_path / "backend"


def test_l_operateur_prime_le_manifeste(tmp_path: Path, monkeypatch) -> None:
    """FORGE_TESTS_SOURCES est un geste explicite au run : il passe avant la déclaration du
    projet — l'opérateur qui désigne une base sait quelque chose que le manifeste ignore."""
    (tmp_path / "back").mkdir()
    (tmp_path / "ailleurs" / "paquet").mkdir(parents=True)
    _manifeste(tmp_path, '[racines]\nexecution = "back"\n')
    monkeypatch.setenv("FORGE_TESTS_SOURCES", str(tmp_path / "ailleurs" / "paquet"))

    racine, regle, _ = _decider_racine(tmp_path)

    assert racine == tmp_path / "ailleurs"
    assert "FORGE_TESTS_SOURCES" in regle


def test_une_racine_declaree_ABSENTE_est_rendue_avec_son_avertissement(tmp_path: Path) -> None:
    """Retomber en silence sur la détection referait le défaut mesuré (un manifeste livré et
    ignoré). La racine déclarée est rendue, et le motif DIT la contradiction."""
    _manifeste(tmp_path, '[racines]\nexecution = "back"\n')

    racine, regle, _ = _decider_racine(tmp_path)

    assert racine == tmp_path / "back"
    assert "N EXISTE PAS" in regle


def test_un_manifeste_ILLISIBLE_est_dit_jamais_tu(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    _manifeste(tmp_path, "ceci n'est pas [du toml")

    declarees, motif = racines_declarees(tmp_path)

    assert declarees == {}
    assert motif is not None and "ILLISIBLE" in motif


def test_un_manifeste_sans_section_racines_ne_declare_rien(tmp_path: Path) -> None:
    """Le manifeste du conducteur porte d'autres sections (profil, has_ui) : leur présence ne
    vaut pas déclaration de racines."""
    _manifeste(tmp_path, 'has_ui = false\n[profil]\nnom = "outil"\n')

    declarees, motif = racines_declarees(tmp_path)

    assert declarees == {} and motif is None
