"""La forge dépose le gabarit de configuration qu'elle réclame (TF-0539).

Fait fondateur (lot Produit-02 20260823a) : le rapport énumérait, pan par pan, les clés
attendues ET le chemin exact du fichier — jusqu'à préciser quelles clés seraient inutiles sur la
stack détectée. Le projet devait pourtant reconstituer le fichier à la main depuis un rapport de
1,1 Mo. Coût forge du dépôt : nul.

Ce que ces cas verrouillent : que les clés soient DÉRIVÉES du code (une liste recopiée se périme
en silence), et surtout que le dépôt n'écrase JAMAIS ce qui appartient au projet.
"""

from __future__ import annotations

from forge_tests import gabarit_env


def test_les_cles_sont_derivees_du_code_pas_recopiees():
    """Une liste recopiée se périme au premier ajout ; une liste dérivée, jamais."""
    cles = gabarit_env.cles_connues()
    assert len(cles) > 30, f"{len(cles)} clés dérivées — le balayage ne trouve plus le code"
    assert "FORGE_TESTS_APP" in cles
    assert "FORGE_TESTS_INCLURE" in cles, (
        "la clé posée par TF-0536 doit apparaître sans qu'on l'ajoute ici")
    assert cles == sorted(cles), "l'ordre doit être stable, sinon le fichier bouge à chaque dépôt"


def test_depot_sur_un_projet_nu(tmp_path):
    """Le cas de l'item : rien n'est configuré, la forge dépose."""
    resultat = gabarit_env.deposer(tmp_path)
    assert resultat["depose"] is True
    depose = tmp_path / gabarit_env.FICHIER
    assert depose.exists()
    contenu = depose.read_text(encoding="utf-8")
    assert "FORGE_TESTS_APP=" in contenu
    assert "JAMAIS de secret réel" in contenu, "le gabarit doit porter la garde des secrets"


def test_un_projet_deja_configure_n_est_pas_touche(tmp_path):
    """BORNE : `.env.forge-tests` appartient au projet — on n'y touche jamais."""
    (tmp_path / ".env.forge-tests").write_text("FORGE_TESTS_APP=app:api\n", encoding="utf-8")
    resultat = gabarit_env.deposer(tmp_path)
    assert resultat["depose"] is False
    assert not (tmp_path / gabarit_env.FICHIER).exists()
    ecrit = (tmp_path / ".env.forge-tests").read_text(encoding="utf-8")
    assert ecrit == "FORGE_TESTS_APP=app:api\n"


def test_un_gabarit_deja_depose_n_est_jamais_reecrit(tmp_path):
    """BORNE : le projet a pu l'annoter — le réécrire effacerait son travail."""
    depose = tmp_path / gabarit_env.FICHIER
    depose.write_text("# annoté par le projet\nFORGE_TESTS_APP=\n", encoding="utf-8")
    resultat = gabarit_env.deposer(tmp_path)
    assert resultat["depose"] is False
    assert "annoté par le projet" in depose.read_text(encoding="utf-8")


def test_le_depot_se_dit_toujours(tmp_path):
    """Un dépôt silencieux ne se distingue pas d'un oubli : les trois cas portent un motif."""
    assert gabarit_env.deposer(tmp_path)["motif"]
    assert gabarit_env.deposer(tmp_path)["motif"], (
        "le second passage doit dire pourquoi il ne fait rien")


def test_une_cible_illisible_ne_fait_pas_echouer_l_audit(tmp_path):
    """BORNE : un dépôt impossible se déclare, il n'interrompt pas l'audit qui l'entoure."""
    resultat = gabarit_env.deposer(tmp_path / "inexistant" / "profond")
    assert resultat["depose"] is False
    assert "impossible" in resultat["motif"]
