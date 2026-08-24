"""Une copie vendorisée qui a divergé de sa source sert des valeurs périmées en silence (TF-0580).

Fait fondateur (lot Produit-02 20260824) : un `Dockerfile` posait `ENV FORGE_ROOT=/app/vendor`,
donc en production la copie vendorisée ÉTAIT la source alimentant la base et les chiffres affichés.
Rien ne la rafraîchissait, rien ne la comparait à l'amont. Le site annonçait v1.6.2 et 80 services
quand le catalogue amont en portait v1.8.0 et 83 — deux versions de retard, sur un site dont
l'argument entier est la preuve datée.

Ce que ces cas verrouillent, et la troisième borne est la plus importante : « je ne peux pas
comparer » et « c'est à jour » ne doivent JAMAIS s'écrire pareil. Les confondre, c'est reproduire
le défaut d'origine dans l'outil censé le détecter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import vendorisation


def _depot(base: Path, nom: str, fichiers: dict[str, str]) -> Path:
    """Un dépôt source : ce qui le distingue d'un dossier quelconque est son `.git`."""
    d = base / nom
    (d / ".git").mkdir(parents=True, exist_ok=True)
    for rel, contenu in fichiers.items():
        cible = d / rel
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")
    return d


def _projet_avec_copie(base: Path, nom: str, fichiers: dict[str, str]) -> Path:
    p = base / "produit"
    for rel, contenu in fichiers.items():
        cible = p / "vendor" / nom / rel
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")
    return p


def test_copie_a_jour_ne_produit_aucun_ecart(tmp_path):
    _depot(tmp_path, "digit-ai-factory", {"catalogues/catalogue.jsonl": '{"version":"1.8.0"}\n'})
    projet = _projet_avec_copie(tmp_path, "digit-ai-factory", {"catalogues/catalogue.jsonl": '{"version":"1.8.0"}\n'})
    r = vendorisation.constats(projet, tmp_path)
    assert len(r) == 1 and r[0]["statut"] == "a_jour", r


def test_le_fait_fondateur_deux_versions_de_retard(tmp_path):
    """Le cas exact du 24/08 : la copie porte une version antérieure, et rien ne le disait."""
    _depot(tmp_path, "digit-ai-factory", {"catalogues/catalogue.jsonl": '{"version":"1.8.0","services":83}\n'})
    projet = _projet_avec_copie(tmp_path, "digit-ai-factory", {"catalogues/catalogue.jsonl": '{"version":"1.6.2","services":80}\n'})
    r = vendorisation.constats(projet, tmp_path)
    assert r[0]["statut"] == "diverge"
    assert "catalogues/catalogue.jsonl" in r[0]["divergents"]


def test_un_fichier_ajoute_en_amont_manque_a_la_copie(tmp_path):
    _depot(tmp_path, "amont", {"a.txt": "x\n", "b.txt": "neuf\n"})
    projet = _projet_avec_copie(tmp_path, "amont", {"a.txt": "x\n"})
    r = vendorisation.constats(projet, tmp_path)
    assert r[0]["statut"] == "diverge" and "b.txt" in r[0]["absents"]


def test_BORNE_source_absente_du_poste_non_comparable_jamais_a_jour(tmp_path):
    """LA borne qui compte : ne pas confondre « pas comparé » et « à jour ».

    Les confondre reproduirait, dans l'outil censé détecter le défaut, exactement le défaut
    d'origine — un silence qui se lit comme un feu vert.
    """
    projet = _projet_avec_copie(tmp_path, "une-lib-tierce", {"lib.js": "…\n"})
    r = vendorisation.constats(projet, tmp_path)
    assert r[0]["statut"] == "non_comparable"
    assert r[0]["statut"] != "a_jour"
    assert "non comparé" in r[0]["motif"]


def test_BORNE_fins_de_ligne_ne_font_pas_diverger(tmp_path):
    """Un CRLF n'est pas une dérive de contenu (TF-0072, rencontré trois fois cette semaine)."""
    _depot(tmp_path, "amont", {"a.txt": "une ligne\nune autre\n"})
    projet = _projet_avec_copie(tmp_path, "amont", {"a.txt": "a remplacer"})
    # Ecrit en BINAIRE : write_text retraduit \n en \r\n sur Windows, ce qui produirait
    # \r\r\n et testerait autre chose que ce qu'on croit tester.
    (projet / "vendor" / "amont" / "a.txt").write_bytes(b"une ligne\r\nune autre\r\n")
    r = vendorisation.constats(projet, tmp_path)
    assert r[0]["statut"] == "a_jour", r


def test_BORNE_projet_sans_vendor_ne_rend_rien(tmp_path):
    """Un projet qui ne vendorise pas n'a rien à déclarer — et n'est pas accusé de se taire."""
    (tmp_path / "produit").mkdir()
    assert vendorisation.constats(tmp_path / "produit", tmp_path) == []


def test_le_constat_dit_CE_QUI_A_ETE_COMPARE(tmp_path):
    """Un constat qui ne dit pas ce qu'il a regardé n'est pas actionnable."""
    _depot(tmp_path, "amont", {"a.txt": "x\n", "b.txt": "y\n"})
    projet = _projet_avec_copie(tmp_path, "amont", {"a.txt": "x\n", "b.txt": "AUTRE\n"})
    r = vendorisation.constats(projet, tmp_path)
    assert r[0]["compares"] == 2
    assert "2 comparé(s)" in r[0]["motif"]


@pytest.mark.parametrize("racine", ["vendor", "third_party", "externes"])
def test_les_conventions_de_dossier_reconnues(tmp_path, racine):
    _depot(tmp_path, "amont", {"a.txt": "x\n"})
    p = tmp_path / "produit"
    (p / racine / "amont").mkdir(parents=True)
    (p / racine / "amont" / "a.txt").write_text("DIVERGE\n", encoding="utf-8")
    r = vendorisation.constats(p, tmp_path)
    assert r and r[0]["statut"] == "diverge"
