"""TF-2197 (volet a) — une garde se prouve des DEUX côtés.

Fait remonté (Produit-86, lot du 05/11/2026, RP-17) : la garde E-097 n'était tenue que par son cas
positif. Une garde qui laisse passer tout le monde, ou qui refuse tout le monde, a le même test vert
qu'une garde juste. Décision du 06/11/2026 : contre-épreuve des gardes.

La matrice des droits (`forge/matrice-droits.json`, TF-0343) est l'endroit où le contrat de chaque
action se lit. Une action qui n'y affirme que des succès n'a pas de contre-épreuve ; celle qui n'y
affirme que des refus n'a pas de cas positif.

Trois sens :
  - ROUGE  — que des succès : FAIL nommé ; que des refus : FAIL nommé ;
  - VERT   — un succès et un refus ; une action déclarée ouverte à tous avec son motif ;
  - REMÈDE — le remède que le message propose (ajouter la cellule refusée) est joué et passe.
"""

from __future__ import annotations

from forge_tests import classes, droits


def _matrice(attendu: dict, **action: object) -> dict:
    return {
        "profils": ["operateur", "approbateur", "anonyme"],
        "actions": [{"nom": "decider", "methode": "POST", "route": "/api/x", "attendu": attendu,
                     **action}],
    }


def _ids(matrice: dict) -> list[str]:
    return [f.id for f in droits.gardes_sans_contre_epreuve(matrice)]


# --- ROUGE ---------------------------------------------------------------------------------------
def test_rouge_une_action_qui_n_affirme_que_des_succes_n_a_pas_de_contre_epreuve() -> None:
    matrice = _matrice({"approbateur": 200, "operateur": 200})
    constats = droits.gardes_sans_contre_epreuve(matrice)
    assert [c.id for c in constats] == [
        "qualif:matrice-droits:garde-sans-contre-epreuve:decider"
    ]
    assert constats[0].classe == classes.MATRICE_DES_DROITS
    assert constats[0].severite == "bloquant"
    assert "SUCCÈS" in constats[0].message


def test_rouge_une_action_qui_n_affirme_que_des_refus_n_a_pas_de_cas_positif() -> None:
    assert _ids(_matrice({"approbateur": 403, "anonyme": 401})) == [
        "qualif:matrice-droits:garde-sans-cas-positif:decider"
    ]


def test_rouge_un_409_n_est_pas_un_refus_de_droit() -> None:
    """Le 409 dit « état en conflit », pas « pas le droit » : il ne prouve pas la garde."""
    assert _ids(_matrice({"approbateur": 200, "operateur": 409})) == [
        "qualif:matrice-droits:garde-sans-contre-epreuve:decider"
    ]


def test_rouge_le_constat_remonte_par_les_controles_du_pan_qualif(tmp_path) -> None:
    (tmp_path / "forge").mkdir()
    import json

    (tmp_path / droits.FICHIER).write_text(
        json.dumps(_matrice({"approbateur": 200})), encoding="utf-8"
    )
    sessions = [{"role": r, "storage_state": f"{r}.json", "etat": None}
                for r in ("operateur", "approbateur", "anonyme")]
    ids = [f.id for f in droits.controles(tmp_path, sessions, [])]
    assert "qualif:matrice-droits:garde-sans-contre-epreuve:decider" in ids


# --- VERT ----------------------------------------------------------------------------------------
def test_vert_un_succes_et_un_refus() -> None:
    assert _ids(_matrice({"approbateur": 200, "operateur": 403})) == []
    assert _ids(_matrice({"approbateur": 201, "anonyme": 401})) == []
    assert _ids(_matrice({"approbateur": 200, "operateur": 404})) == []


def test_vert_une_action_ouverte_a_tous_se_declare_avec_son_motif() -> None:
    ouverte = _matrice({"approbateur": 200, "operateur": 200}, sans_garde="lecture publique")
    assert _ids(ouverte) == []


def test_remede_joue_ajouter_la_cellule_refusee_fait_passer() -> None:
    """Le remède du message : la cellule d'un profil refusé. Il doit PASSER."""
    avant = _matrice({"approbateur": 200, "operateur": 200})
    assert _ids(avant) != []
    apres = _matrice({"approbateur": 200, "operateur": 200, "anonyme": 401})
    assert _ids(apres) == []


def test_une_action_sans_aucun_code_n_est_pas_accusee() -> None:
    """Rien n'est affirmé : c'est la grille (cellules absentes du contrat) qui le dit déjà."""
    assert _ids(_matrice({})) == []
