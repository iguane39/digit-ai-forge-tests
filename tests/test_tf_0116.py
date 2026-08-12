"""TF-0116 — bug G-1 (mutant non restauré) situé dans `mutation.py` en cours d édition ailleurs.

Le vrai bug — un mutant qui survit à la restauration parce que la découverte dynamique du
paquet de sources (`forge_tests.disposition.paquet_sources`) est interrogée en cours
d écriture — vit dans `forge_tests/adaptateurs/mutation.py`, propriété d une session tierce
pendant cette campagne : intouchable ici. Le `try`/`finally` qui garantirait la restauration
CÔTÉ MUTATION reste donc un reste explicite.

Ce qui est livrable SANS ce fichier, c est le filet de la RECETTE elle-même : un contrôle
d intégrité du banc, indépendant de ce que `mutation.py` fait ou ne fait pas, qui NOMME toute
altération résiduelle au lieu de la laisser invisible. Ce filet existait déjà
(`recette/verifier_corpus.py::main`, section « corpus ») mais restait couplé en dur à
`backend/app` — alors que le paquet réellement muté est désormais DÉCOUVERT et peut vivre
ailleurs (`backend/src`, etc., cf. `forge_tests/disposition.py`). Sans suivre cette
découverte, le filet peut regarder au mauvais endroit dès qu un projet ne range pas son
paquet sous `app`. Corrigé ici, avec sa preuve : une empreinte AVANT/APRÈS altération est
NOMMÉE (rouge), une empreinte inchangée ne l est pas (vert).
"""

from __future__ import annotations

from pathlib import Path

from recette import verifier_corpus as vc


def _poser_banc(racine: Path, paquet: str = "app") -> Path:
    module = racine / "backend" / paquet / "calcul.py"
    module.parent.mkdir(parents=True)
    module.write_text("TAUX_TAXE = 1.20\n", encoding="utf-8")
    return module


# --- `_empreintes` suit le paquet DÉCOUVERT, pas `backend/app` en dur -------------------------
def test_empreintes_couvre_backend_app_quand_cest_la_convention(tmp_path: Path) -> None:
    module = _poser_banc(tmp_path, "app")
    empreintes = vc._empreintes(tmp_path)
    assert module.as_posix() in empreintes


def test_empreintes_suit_la_decouverte_quand_le_paquet_sappelle_autrement(tmp_path: Path) -> None:
    """ROUGE implicite : une empreinte figée sur `backend/app` aurait rendu {} ici — un banc
    dont le paquet s appelle `src` (cas Produit-11 2, cf. `disposition.py`) resterait
    hors de portée du contrôle G-1, muet sur exactement les fichiers que la mutation altère."""
    module = _poser_banc(tmp_path, "src")
    empreintes = vc._empreintes(tmp_path)
    assert module.as_posix() in empreintes


# --- `alterations` — le cœur du contrôle G-1, vérifiable sans payer un audit complet -----------
def test_alterations_nomme_un_fichier_reellement_altere_apres_lempreinte(tmp_path: Path) -> None:
    """ROUGE : un mutant non restauré (le bug constaté le 12/08, TAUX_TAXE resté à 1.20 sur
    UNE valeur alors qu il aurait dû être défait) doit sortir NOMMÉ, jamais silencieux."""
    module = _poser_banc(tmp_path)
    avant = vc._empreintes(tmp_path)

    module.write_text("TAUX_TAXE = 1.19  # mutant non restaure\n", encoding="utf-8")

    trouve = vc.alterations({tmp_path: avant})
    assert trouve == [f"{tmp_path.name}/{module.as_posix()}"]


def test_alterations_vide_quand_le_banc_est_rendu_intact(tmp_path: Path) -> None:
    """VERT — le même banc, restauré à l identique, ne doit produire AUCUNE altération : un
    contrôle qui nomme un fichier intact ne prouverait rien de plus qu un vert de complaisance
    inversé."""
    module = _poser_banc(tmp_path)
    avant = vc._empreintes(tmp_path)

    contenu_origine = module.read_bytes()
    module.write_text("TAUX_TAXE = 1.19  # mutant pose puis defait\n", encoding="utf-8")
    module.write_bytes(contenu_origine)

    assert vc.alterations({tmp_path: avant}) == []


def test_alterations_porte_sur_plusieurs_bancs_independamment(tmp_path: Path) -> None:
    sain = tmp_path / "banc-vert"
    altere = tmp_path / "banc-rouge"
    module_sain = _poser_banc(sain)
    module_altere = _poser_banc(altere)
    avant = {sain: vc._empreintes(sain), altere: vc._empreintes(altere)}

    module_altere.write_text("TAUX_TAXE = 1.19\n", encoding="utf-8")

    trouve = vc.alterations(avant)
    assert trouve == [f"{altere.name}/{module_altere.as_posix()}"]
    assert not any(module_sain.as_posix() in ligne for ligne in trouve)
