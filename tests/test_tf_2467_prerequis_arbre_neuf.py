"""TF-2467 — un arbre de travail neuf : une commande unique, hors ligne, prépare les bancs, et la
recette rend « prérequis absent » au lieu d'un faux rouge.

Fait remonté par l'agent du lot ft le 12/11/2026, rejoué le 13/11/2026 par l'agent du lot fu sur un
`git worktree add` neuf (`2c1a45b`) : sans `.venv` des bancs, sans `node_modules` ni `dist` des
fronts, 13 défauts du corpus sur 23 étaient NON MESURABLES (TF-2402) et la section `dashboard`
échouait — `check_html.py` rend code 1 (règle L12, cinq constats bloquants) sur les textes de
préalable que le dashboard cite. La recette écrivait « S-01 NON TENU », code 1, pour un arbre
simplement pas préparé.

Décision (R-58 du 12/11/2026) : forge-tests publie une commande unique, hors ligne, qui prépare un
arbre neuf ; la recette rend « prérequis absent » au lieu d'un faux rouge.

Sens prouvés :
  - ROUGE  — sur un arbre neuf, `prerequis_absents` nomme les six dossiers manquants (trois par
             banc) et `--verifier` rend 3 ; un jugement de forme en échec sur un rapport à
             préalable absent n'est plus un FAIL ;
  - VERT   — la préparation joue les étapes dans l'ordre (back, dépendances du front, build),
             toutes hors ligne, puis l'arbre est prêt ; le verdict S-01 nomme la commande ;
  - CONTRE-ÉPREUVES — un arbre prêt ne rejoue rien ; un échec d'étape s'arrête et se dit (code 1) ;
             un outil absent est un prérequis absent (code 3) ; un échec de forme SANS préalable
             absent reste un FAIL, et un PASS reste un PASS.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from recette import preparer_arbre as pa
from recette import verifier_corpus as vc


def _arbre_neuf(racine: Path) -> Path:
    """Ce que git livre : les dossiers suivis des deux bancs, aucun préalable."""
    for banc in pa.BANCS:
        (racine / "fixtures" / banc / "backend").mkdir(parents=True)
        (racine / "fixtures" / banc / "frontend").mkdir(parents=True)
    return racine


def _preparer_tout(racine: Path) -> None:
    for etape in pa.etapes(racine):
        etape.produit.mkdir(parents=True, exist_ok=True)


class _Executeur:
    """Un exécuteur factice : note chaque appel et crée le produit de l'étape, comme l'outil."""

    def __init__(self, racine: Path, *, echoue_a: int | None = None) -> None:
        self.racine = racine
        self.appels: list[tuple[list[str], Path]] = []
        self.echoue_a = echoue_a

    def __call__(self, argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        cwd = Path(str(options["cwd"]))
        self.appels.append((argv, cwd))
        if self.echoue_a is not None and len(self.appels) == self.echoue_a:
            return subprocess.CompletedProcess(argv, 1, "", "cache incomplet")
        for etape in pa.etapes(self.racine):
            if etape.dossier == cwd and tuple(argv[1:]) == etape.argv[1:]:
                etape.produit.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(argv, 0, "ok", "")


def _chercher(nom: str) -> str:
    return f"/outils/{nom}"


# --- ROUGE : l'état de départ ---------------------------------------------------------------------
def test_rouge_un_arbre_neuf_nomme_ses_six_prerequis_absents(tmp_path: Path) -> None:
    racine = _arbre_neuf(tmp_path)

    absents = [e.produit.relative_to(racine).as_posix() for e in pa.prerequis_absents(racine)]

    assert absents == [
        f"fixtures/{banc}/{chemin}"
        for banc in pa.BANCS
        for chemin in ("backend/.venv", "frontend/node_modules", "frontend/dist")
    ]


def test_rouge_verifier_rend_3_et_nomme_la_commande(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    racine = _arbre_neuf(tmp_path)

    assert pa.main(["--verifier"], racine) == 3

    sortie = capsys.readouterr().out
    assert "PRÉREQUIS ABSENT" in sortie and "6 élément(s)" in sortie
    assert pa.COMMANDE in sortie


def test_rouge_un_jugement_de_forme_en_echec_sur_prealable_absent_n_est_pas_un_fail() -> None:
    """Le défaut mesuré : check_html rend 1 sur le dashboard d'un rapport à 12 pans non mesurés."""
    prealables = {"api": "PRÉALABLE D ENVIRONNEMENT ABSENT — aucun environnement Python"}

    assert vc.jugement_de_forme(1, prealables) == "PREREQUIS_ABSENT"


# --- VERT : la commande ---------------------------------------------------------------------------
def test_vert_la_commande_est_unique_et_hors_ligne() -> None:
    assert pa.COMMANDE == "uv run --frozen --offline python recette/preparer_arbre.py"
    assert "--offline" in pa.COMMANDE and "--frozen" in pa.COMMANDE


def test_vert_la_preparation_joue_les_etapes_dans_l_ordre_et_hors_ligne(tmp_path: Path) -> None:
    racine = _arbre_neuf(tmp_path)
    executeur = _Executeur(racine)

    code = pa.preparer(racine, executeur, _chercher)

    assert code == 0
    assert [(a[0].rsplit("/", 1)[-1], *a[1:], c.parent.name, c.name)
            for a, c in executeur.appels][:3] == [
        ("uv", "sync", "--frozen", "--offline", "banc-rouge", "backend"),
        ("npm", "ci", "--offline", "banc-rouge", "frontend"),
        ("npm", "run", "build", "banc-rouge", "frontend"),
    ]
    assert len(executeur.appels) == 6
    for argv, _ in executeur.appels:
        if argv[1] in ("sync", "ci"):
            assert "--offline" in argv, f"{argv} lirait le réseau"
    assert pa.prerequis_absents(racine) == []


def test_vert_apres_la_preparation_verifier_rend_0(tmp_path: Path) -> None:
    racine = _arbre_neuf(tmp_path)
    pa.preparer(racine, _Executeur(racine), _chercher)

    assert pa.main(["--verifier"], racine) == 0


def test_vert_le_verdict_s01_nomme_la_commande_quand_un_prealable_manque() -> None:
    lignes, code = vc.verdict_s01(
        True, False, {"rouge": {"api": "PRÉALABLE D ENVIRONNEMENT ABSENT"}}, commande=pa.COMMANDE
    )

    assert code == 3
    assert any(pa.COMMANDE in ligne for ligne in lignes)
    assert any("S-01 NON PRONONCÉ" in ligne for ligne in lignes)


# --- CONTRE-ÉPREUVES ------------------------------------------------------------------------------
def test_contre_epreuve_un_arbre_pret_ne_rejoue_rien(tmp_path: Path) -> None:
    racine = _arbre_neuf(tmp_path)
    _preparer_tout(racine)
    executeur = _Executeur(racine)

    assert pa.preparer(racine, executeur, _chercher) == 0
    assert executeur.appels == []


def test_contre_epreuve_seul_ce_qui_manque_est_rejoue(tmp_path: Path) -> None:
    racine = _arbre_neuf(tmp_path)
    _preparer_tout(racine)
    (racine / "fixtures" / "banc-vert" / "frontend" / "dist").rmdir()
    executeur = _Executeur(racine)

    assert pa.preparer(racine, executeur, _chercher) == 0
    assert [a[1:] for a, _ in executeur.appels] == [["run", "build"]]


def test_contre_epreuve_une_etape_en_echec_arrete_la_preparation_et_se_dit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    racine = _arbre_neuf(tmp_path)
    executeur = _Executeur(racine, echoue_a=2)

    assert pa.preparer(racine, executeur, _chercher) == 1

    assert len(executeur.appels) == 2, "aucune étape après l'échec"
    sortie = capsys.readouterr().out
    assert "ÉCHEC" in sortie and "cache incomplet" in sortie


def test_contre_epreuve_un_outil_absent_est_un_prerequis_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    racine = _arbre_neuf(tmp_path)
    executeur = _Executeur(racine)

    assert pa.preparer(racine, executeur, lambda _nom: None) == 3
    assert executeur.appels == []
    assert "outil « uv » introuvable" in capsys.readouterr().out


def test_contre_epreuve_un_echec_de_forme_sans_prealable_absent_reste_un_fail() -> None:
    """Le jugement de forme garde toute sa force dès que l'arbre est prêt."""
    assert vc.jugement_de_forme(1, {}) == "FAIL"
    assert vc.jugement_de_forme(2, {}) == "FAIL"


def test_contre_epreuve_un_pass_reste_un_pass_meme_avec_un_prealable_absent() -> None:
    assert vc.jugement_de_forme(0, {"api": "PRÉALABLE D ENVIRONNEMENT ABSENT"}) == "PASS"
    assert vc.jugement_de_forme(0, {}) == "PASS"


def test_contre_epreuve_verdict_s01_sans_commande_est_inchange() -> None:
    """Sans arbre à préparer (démon de conteneurs absent), aucune commande n'est citée."""
    prealables = {"rouge": {"api": "PRÉALABLE D ENVIRONNEMENT ABSENT"}}
    lignes, code = vc.verdict_s01(True, False, prealables)

    assert code == 3
    assert not any("preparer_arbre" in ligne for ligne in lignes)
