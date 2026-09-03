"""TF-0537 — UN ARTEFACT DE SAUVEGARDE NAVIGATEUR N'EST PAS DU CODE DU PROJET (24/08/2026).

LE FAIT (lot Produit-02 du 23/08). Le pan `securite` sortait FAIL sur NEUF « secrets », tous
situes dans une page aspiree : les cles Google Maps et Weglot embarquees dans
`weglot.min.js.telechargement` et `saved_resource`, du JavaScript minifie DE TIERS capture par
« Enregistrer la page sous… ». Aucun n'appartient au projet, aucun n'est revocable par lui, aucun ne
peut fuiter par son fait — ils sont PUBLICS dans le HTML du site d'origine.

L'oracle savait pourtant deja discriminer : trois des neuf etaient classes « valeur non reelle
(placeholder/env) — OK ». *Il savait distinguer, il ne savait pas s'abstenir.*

DEUX CAUSES, ET LA PREMIERE EST HUMILIANTE :
  1. le motif de nom etait ecrit SANS ACCENT (« .telechargement ») alors que le navigateur francais
     nomme le fichier « .telechargement » avec les siens. Le motif ne correspondait a rien ;
  2. `est_page_aspiree`, le helper qui reconnait le marqueur « saved from url » ecrit par les
     navigateurs, existait depuis TF-0536 et N'ETAIT APPELE PAR PERSONNE — une regle morte.

CE QUE CE TEST VERROUILLE : les deux voies. Le nom accentue, et le marqueur pour ce que le nom ne
trahit pas. Sans lui, le meme rapport reviendrait avec neuf constats a ecarter a la main avant
d'apercevoir le produit — et un lecteur qui ecarte neuf lignes apprend a survoler la dixieme.
"""
import tempfile
from pathlib import Path

from forge_tests import exclusions
from forge_tests.adaptateurs import securite

CLE = "AIzaSyA0000000000000000000000000000000000"


def _projet(racine: Path) -> None:
    """Un projet plat : un fichier a lui, et deux artefacts venus d'un navigateur."""
    (racine / "app.js").write_text("// code du projet\nconst x = 1;\n", encoding="utf-8")
    # (1) le nom ACCENTUE, tel que le navigateur francais l'ecrit
    (racine / "weglot.min.js.téléchargement").write_text(f"var k='{CLE}';\n", encoding="utf-8")
    # (2) un nom qui ne trahit RIEN : seul le marqueur en tete le denonce
    (racine / "ressource-sauvee.js").write_text(
        f"<!-- saved from url=(0044)https://exemple.fr/ -->\nvar k='{CLE}';\n", encoding="utf-8"
    )


def test_le_nom_accentue_et_le_marqueur_sortent_du_perimetre():
    with tempfile.TemporaryDirectory() as brut:
        racine = Path(brut) / "projet"
        racine.mkdir()
        _projet(racine)
        with tempfile.TemporaryDirectory() as tmp:
            aspires: list[str] = []
            scan = securite._sources_du_produit(racine, Path(tmp), [], [], aspires)
            copies = {p.name for p in scan.rglob("*") if p.is_file()}

        assert "app.js" in copies, "le code du projet doit rester dans le perimetre"
        assert "weglot.min.js.téléchargement" not in copies, (
            "TF-0537 : le motif de nom ACCENTUE ne filtre pas — c'est exactement le defaut "
            "d'origine"
        )
        assert "ressource-sauvee.js" not in copies, (
            "TF-0537 : le marqueur « saved from url » ne filtre pas ; un artefact renomme "
            "a la main revient donc dans le scan"
        )
        assert any("ressource-sauvee" in x for x in aspires), (
            "une exclusion se DIT au rapport : sans la liste, un lecteur ne distingue pas « aucun "
            "secret dans la page aspiree » de « la page aspiree n'a pas ete lue »"
        )


def test_les_deux_graphies_du_motif_sont_declarees():
    """BORNE : la graphie sans accent reste, parce qu'un navigateur anglais l'ecrit ainsi."""
    assert "weglot.min.js.téléchargement".endswith(exclusions.MOTIFS_ASPIRES)
    assert "part.js.telechargement".endswith(exclusions.MOTIFS_ASPIRES)
    assert "x.crdownload".endswith(exclusions.MOTIFS_ASPIRES)


def test_un_fichier_du_projet_nest_jamais_ecarte_par_ces_motifs():
    """SENS INVERSE, sans lequel la regle pourrait tout exclure et paraitre juste."""
    with tempfile.TemporaryDirectory() as brut:
        racine = Path(brut) / "projet"
        racine.mkdir()
        (racine / "telechargement.js").write_text("// vrai module du projet\n", encoding="utf-8")
        (racine / "downloads.py").write_text("# vrai module du projet\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            scan = securite._sources_du_produit(racine, Path(tmp), [], [], [])
            copies = {p.name for p in scan.rglob("*") if p.is_file()}
        assert copies == {"telechargement.js", "downloads.py"}, (
            "un fichier du projet qui PARLE de telechargement n'est pas un artefact de navigateur "
            ": "
            f"copies = {sorted(copies)}"
        )
