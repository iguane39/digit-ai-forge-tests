"""TF-0470 (23/08/2026) — LES ROUTES ATTENDUES PAR LOCALE SE DÉCLARENT.

Le fait fondateur, et il est particulièrement coûteux : la parité de routes se mesurait contre
l UNION des routes SERVIES, donc contre une ARBORESCENCE. Un produit rendu côté serveur
(`output: 'standalone'`) n en émet aucune — le pan sortait en SKIP sur la parité de routes, et
c était le constat FONDATEUR du pan qui devenait invisible : une route sur 201 existait en FR et
pas en EN, sur le produit même où le pan avait été conçu. La forge ne voyait plus le défaut qui
l avait fait naître.

Le remède suit le patron déjà éprouvé des chaînes littérales (TF-0465) : RIEN DE DÉCLARÉ, RIEN DE
JUGÉ. Le produit déclare ses routes attendues par locale dans un fichier versionné, et le pan les
confronte — entre locales d abord, ce qui ne demande aucun build, puis au servi quand il existe.

Ce que ces tests figent, dans les deux sens : une déclaration symétrique passe, une déclaration
asymétrique est refusée, une absence de déclaration est DÉCLARÉE non jugée (jamais un vert), et
une déclaration illisible n emporte pas l audit.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests.adaptateurs import i18n


def _declarer(tmp_path: Path, monkeypatch, contenu) -> Path:
    fichier = tmp_path / "routes-attendues.json"
    fichier.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_ROUTES", str(fichier))
    return fichier


def test_rien_de_declare_rien_de_lu(monkeypatch) -> None:
    monkeypatch.delenv("FORGE_TESTS_I18N_ROUTES", raising=False)
    assert i18n.routes_de_reference() == {}


def test_une_declaration_illisible_ne_casse_rien(tmp_path, monkeypatch) -> None:
    fichier = tmp_path / "casse.json"
    fichier.write_text("{ceci n est pas du JSON", encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_I18N_ROUTES", str(fichier))
    # Une déclaration illisible se DÉCLARE (le pan le dit à son non_juge) et n emporte pas
    # l audit : elle ne vaut ni un constat, ni un vert.
    assert i18n.routes_de_reference() == {}


def test_les_chemins_sont_normalises(tmp_path, monkeypatch) -> None:
    _declarer(tmp_path, monkeypatch, {"fr": ["a-propos", "/contact/", "/"], "en": ["/about"]})
    lues = i18n.routes_de_reference()
    assert lues["fr"] == ["/", "/a-propos", "/contact"]
    assert lues["en"] == ["/about"]


def test_une_declaration_SYMETRIQUE_ne_produit_aucun_constat() -> None:
    constats, motifs = i18n.constats_routes_declarees(
        {"fr": ["/", "/a-propos", "/contact"], "en": ["/en", "/en/about", "/en/contact"]}
    )
    assert constats == []
    # Le motif DIT ce qui a été confronté : un PASS muet ne se distingue pas d un pan qui n a
    # rien fait.
    assert any("fr (3)" in m and "en (3)" in m for m in motifs)
    assert any("prouve une INTENTION" in m for m in motifs)


def test_LE_DEFAUT_FONDATEUR_une_route_promise_en_FR_et_pas_en_EN() -> None:
    constats, _ = i18n.constats_routes_declarees(
        {"fr": ["/", "/a-propos", "/contact"], "en": ["/en", "/en/about"]}
    )
    assert len(constats) == 1
    identifiant, message = constats[0]
    assert identifiant.endswith(":en")
    # Le constat porte LES DEUX comptes et le nombre manquant : « parité de routes en défaut »
    # sans chiffre se discute, « en déclare 2 quand fr en déclare 3 » se corrige.
    assert "« en »" in message and "2 route(s)" in message and "3" in message
    assert "1 route(s) promise(s) ailleurs" in message
    assert "FORGE_TESTS_I18N_ROUTES" in message


def test_une_seule_locale_declaree_ne_produit_pas_de_constat_mais_le_DIT() -> None:
    constats, motifs = i18n.constats_routes_declarees({"fr": ["/", "/a-propos"]})
    assert constats == []
    assert any("UNE SEULE locale" in m for m in motifs)


def test_le_DECLARE_est_confronte_au_SERVI_quand_le_build_existe() -> None:
    constats, _ = i18n.constats_routes_declarees(
        {"fr": ["/", "/a-propos"], "en": ["/en", "/en/about"]},
        servies={"fr": {"/": object()}, "en": {"/en": object(), "/en/about": object()}},
    )
    # `/a-propos` est PROMISE et pas servie : le produit annonce une page qu il ne sert pas.
    absentes = [m for _i, m in constats if "ABSENTE du build" in m]
    assert len(absentes) == 1
    assert "/a-propos" in absentes[0]
    assert "404" in absentes[0]


def test_une_locale_declaree_mais_absente_du_build_est_DECLAREE_non_jugee() -> None:
    _constats, motifs = i18n.constats_routes_declarees(
        {"fr": ["/", "/a-propos"], "de": ["/de", "/de/ueber-uns"]},
        servies={"fr": {"/": object(), "/a-propos": object()}},
    )
    assert any("« de » declaree et ABSENTE du build servi" in m for m in motifs)


def test_sans_declaration_le_pan_DIT_ce_qu_il_ne_juge_pas(tmp_path, monkeypatch) -> None:
    # C est le point qui manquait : sur un produit sans arborescence, le pan sortait en SKIP et
    # rien ne disait POURQUOI ni COMMENT lever la borne. Un contrôle qui se tait sans le dire est
    # un contrôle absent.
    monkeypatch.delenv("FORGE_TESTS_I18N_ROUTES", raising=False)
    monkeypatch.delenv("FORGE_TESTS_I18N_BUILD", raising=False)
    sortie = i18n.analyser(tmp_path)
    assert any("AUCUNE route declaree" in msg for msg in sortie.non_juge)
    assert any("FORGE_TESTS_I18N_ROUTES" in msg for msg in sortie.non_juge)
    assert any("standalone" in msg for msg in sortie.non_juge)
