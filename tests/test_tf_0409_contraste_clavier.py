"""TF-0409 (option O3) — les deux familles que le parc DÉCLARAIT non couvertes.

Le `non_juge` du pan accessibilité disait, mot pour mot depuis le 20/08, que le CONTRASTE
avait « une mesure existante mais NON CÂBLÉE à cet audit » et que la NAVIGATION CLAVIER
n'était « couverte par AUCUN oracle du parc ». Un écart déclaré est honnête ; il ne mesure
rien. Ces tests verrouillent les deux pans qui le mesurent, dans les DEUX sens : une page
conforme passe, une page fautive est refusée avec le motif nommé.

Le parcours réel (serveur, navigateur, tabulations) est remplacé par des relevés canoniques :
ce qui est prouvé ici est la DÉRIVATION du verdict, seule partie déterministe. Le parcours
lui-même a ses propres gardes, hérités de TF-0122 et testés là-bas.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import clavier, contraste

CIBLE = Path("projet-factice")
ROUTES = (["/", "/demandes"], "routes déclarées pour la recette")


def _brancher(monkeypatch, module, resultats, motifs=None):
    """Remplace le parcours servi par un relevé canonique, et les routes par les nôtres."""
    monkeypatch.setattr(module.accessibilite, "routes_a_auditer", lambda _c: ROUTES)
    monkeypatch.setattr(module, "parcourir", lambda *a, **k: (resultats, motifs or []))


# ── Contraste ───────────────────────────────────────────────────────────────


def test_contraste_page_conforme_passe(monkeypatch) -> None:
    _brancher(monkeypatch, contraste, {"/": {"v2_contrast": [], "unmeasured": []}})
    monkeypatch.setattr(contraste, "_mesure_js", lambda: "() => ({})")
    sortie = contraste.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert sortie.findings == []
    assert any("routes mesurees" in ligne for ligne in sortie.non_juge)


def test_contraste_texte_sous_seuil_est_bloquant(monkeypatch) -> None:
    _brancher(monkeypatch, contraste, {
        "/": {"v2_contrast": [
            {"what": "p.mention", "detail": "2.11:1 < 4.5:1 (#9aa0a6 sur #ffffff)"},
        ], "unmeasured": []},
    })
    monkeypatch.setattr(contraste, "_mesure_js", lambda: "() => ({})")
    sortie = contraste.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    assert len(sortie.findings) == 1
    unique = sortie.findings[0]
    assert unique.severite == "bloquant"
    # Le constat doit porter la ROUTE et la MESURE : un « contraste insuffisant » sans chiffre
    # ni localisation se discute au lieu de se corriger.
    assert "/" in unique.localisation
    assert "2.11:1" in unique.message
    assert "p.mention" in unique.message


def test_contraste_non_mesurable_ne_passe_pas_en_silence(monkeypatch) -> None:
    """Un texte sur image de fond n'est pas mesurable par calcul : il se DÉCLARE."""
    _brancher(monkeypatch, contraste, {
        "/": {"v2_contrast": [], "unmeasured": [
            {"what": "h1.heros", "detail": "texte sur background-image — non mesurable"},
        ]},
    })
    monkeypatch.setattr(contraste, "_mesure_js", lambda: "() => ({})")
    sortie = contraste.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert any("h1.heros" in ligne for ligne in sortie.non_juge), (
        "le non mesurable a disparu du rapport — le PASS se lirait « tout est conforme »"
    )


def test_contraste_sans_socle_est_un_skip_motive(monkeypatch) -> None:
    """Le pan ne RECOPIE pas la formule de luminance : sans le socle, il se déclare non mesuré."""
    monkeypatch.setattr(contraste, "_mesure_js", lambda: None)
    sortie = contraste.analyser(CIBLE)
    assert sortie.verdict == "SKIP"
    assert any("mesure V2 introuvable" in ligne for ligne in sortie.non_juge)


def test_contraste_charge_la_mesure_du_socle_sans_la_dupliquer() -> None:
    """Si le socle est installé, la mesure vient de LUI — une copie divergerait en silence."""
    mesure = contraste._mesure_js()
    if mesure is None:
        return  # socle absent de ce poste : le SKIP motivé est déjà prouvé ci-dessus
    assert "v2_contrast" in mesure, "la mesure chargée n'est pas celle de render_page.py V2"
    source = contraste._SOCLE.read_text(encoding="utf-8")
    assert mesure.strip() in source, "la mesure jouée ne vient pas du fichier du socle"


# ── Clavier ─────────────────────────────────────────────────────────────────

_CONFORME = {
    "total": 4, "examines": 4, "sans_indicateur": [], "evitement": "present",
    "premier": "a « Aller au contenu »", "k2": {"piege": None, "pas": 8, "distincts": 5},
}


def test_clavier_page_conforme_passe(monkeypatch) -> None:
    _brancher(monkeypatch, clavier, {"/": dict(_CONFORME)})
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert sortie.findings == []


def test_clavier_focus_invisible_est_bloquant(monkeypatch) -> None:
    _brancher(monkeypatch, clavier, {
        "/": {**_CONFORME, "sans_indicateur": ["button.valider « Valider »"]},
    })
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    k1 = [f for f in sortie.findings if ":K1:" in f.id]
    assert len(k1) == 1
    assert k1[0].severite == "bloquant"
    assert "button.valider" in k1[0].message
    assert "10.7" in k1[0].message, "le critère RGAA opposable n'est pas cité"


def test_clavier_piege_de_focus_est_bloquant(monkeypatch) -> None:
    _brancher(monkeypatch, clavier, {
        "/": {**_CONFORME, "k2": {"piege": "input#recherche", "pas": 3, "distincts": 1}},
    })
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    k2 = [f for f in sortie.findings if ":K2:" in f.id]
    assert len(k2) == 1
    assert k2[0].severite == "bloquant"
    assert "input#recherche" in k2[0].message
    assert "2.1.2" in k2[0].message


def test_clavier_lien_evitement_absent_est_signale_pas_bloquant(monkeypatch) -> None:
    """Un lien d'évitement manquant est un défaut d'usage, pas une impasse : il se SIGNALE."""
    _brancher(monkeypatch, clavier, {"/": {**_CONFORME, "evitement": "absent"}})
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "PASS", "un K3 absent ne doit pas emporter le verdict"
    k3 = [f for f in sortie.findings if ":K3:" in f.id]
    assert len(k3) == 1
    assert k3[0].severite == "signale"


def test_clavier_lien_evitement_inerte_est_bloquant(monkeypatch) -> None:
    """Une affordance inerte est pire qu'absente : elle se compte conforme et ne mène nulle part."""
    _brancher(monkeypatch, clavier, {"/": {**_CONFORME, "evitement": "cible-absente"}})
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    k3 = [f for f in sortie.findings if ":K3:" in f.id]
    assert len(k3) == 1
    assert k3[0].severite == "bloquant"


def test_clavier_troncature_est_declaree(monkeypatch) -> None:
    """TF-0382 : une borne muette se lit comme une couverture complète."""
    _brancher(monkeypatch, clavier, {
        "/": {**_CONFORME, "total": 137, "examines": clavier.MAX_ELEMENTS},
    })
    sortie = clavier.analyser(CIBLE)
    reste = 137 - clavier.MAX_ELEMENTS
    assert any(f"{reste} restants ne sont PAS juges" in ligne for ligne in sortie.non_juge)


def test_clavier_k2_non_mesure_se_declare(monkeypatch) -> None:
    """Une mesure ratée nomme sa route — elle ne se confond pas avec une absence de piège."""
    _brancher(monkeypatch, clavier, {
        "/": {**_CONFORME, "k2": None, "k2_motif": "TimeoutError"},
    })
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert any("K2 non mesure (TimeoutError)" in ligne for ligne in sortie.non_juge)


def test_clavier_front_non_servi_est_un_skip(monkeypatch) -> None:
    _brancher(monkeypatch, clavier, {}, [])
    sortie = clavier.analyser(CIBLE)
    assert sortie.verdict == "SKIP"
    assert any("front non servi" in ligne for ligne in sortie.non_juge)


# ── Contrat commun ──────────────────────────────────────────────────────────


def test_les_deux_pans_sont_au_registre() -> None:
    from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE

    assert REGISTRE["contraste-wcag"] is contraste
    assert REGISTRE["clavier-focus"] is clavier
    # Un pan absent de PANS_ATTENDUS n'est jamais réclamé au rapport : il serait vert par
    # absence, exactement le faux vert que ce chantier corrige.
    assert "contraste" in PANS_ATTENDUS
    assert "clavier" in PANS_ATTENDUS


def test_les_deux_pans_declarent_ce_qu_ils_ne_jugent_pas() -> None:
    for module in (contraste, clavier):
        assert module.NON_JUGE, f"{module.PAN} sans non_juge — un périmètre muet se lit total"
        assert module.POUR_COUVRIR, f"{module.PAN} sans POUR_COUVRIR (A-5)"
        assert module.CHAPITRES, f"{module.PAN} sans chapitre de cahier"
