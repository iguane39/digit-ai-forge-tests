"""TF-0620 — la forge livre la LIGNE qui protège le fichier qu'elle prescrit.

Le fait, mesuré par le pilot le 25/08/2026. `forge_tests` prescrit `<projet>/.env.forge-tests`,
en dépose le gabarit, et son propre docstring écrivait « gitignore que l'opérateur remplit » : la
protection était SUPPOSÉE, jamais livrée — le mot `gitignore` n'apparaissait nulle part ailleurs
dans le paquet. Sur les trois projets du parc portant le fichier réel, **un seul l'ignorait**. Le
deuxième n'avait aucune ligne ; le troisième portait `!.env.forge-tests`, une négation écrite
exprès, ce qui interdit de conclure à l'étourderie. Les deux étaient versionnés, l'un publié sur
`origin/main`.

Les quatre issues sont jouées, et les deux sens avec elles : ce qui doit changer change, et ce qui
ne doit pas être touché ne l'est pas. Une branche jamais jouée est une branche morte qui se croit
vivante.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import gabarit_env


def test_la_ligne_manquante_est_ajoutee(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    r = gabarit_env.proteger(tmp_path)

    assert r["etat"] == "ajoutee"
    contenu = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env.forge-tests" in contenu.splitlines()
    # Ce qui existait n'est pas perdu : le geste est ADDITIF.
    assert "node_modules/" in contenu
    # La ligne porte son motif, pour que le lecteur sache pourquoi elle est là.
    assert "TF-0620" in contenu


def test_sans_gitignore_le_fichier_est_cree_avec_la_ligne(tmp_path: Path) -> None:
    r = gabarit_env.proteger(tmp_path)

    assert r["etat"] == "ajoutee"
    assert ".env.forge-tests" in (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_une_ligne_deja_presente_n_est_pas_dupliquee(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".env.forge-tests\n", encoding="utf-8")

    r = gabarit_env.proteger(tmp_path)

    assert r["etat"] == "deja"
    assert r["ligne"] == 1
    lignes = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lignes.count(".env.forge-tests") == 1


def test_la_forme_ancree_a_la_racine_compte_aussi(tmp_path: Path) -> None:
    """`/.env.forge-tests` protège le même fichier : l'accuser ferait ajouter un doublon."""
    (tmp_path / ".gitignore").write_text("/.env.forge-tests\n", encoding="utf-8")

    assert gabarit_env.proteger(tmp_path)["etat"] == "deja"


def test_une_negation_est_denoncee_et_JAMAIS_retiree(tmp_path: Path) -> None:
    """Le cas du parc : quelqu'un a écrit la négation exprès. On la dit, on ne décide pas pour lui.
    """
    avant = "*.log\n!.env.forge-tests\n"
    (tmp_path / ".gitignore").write_text(avant, encoding="utf-8")

    r = gabarit_env.proteger(tmp_path)

    assert r["etat"] == "negation"
    assert r["ligne"] == 2
    assert "rotation" in r["motif"]
    # LE SENS QUI COMPTE : le fichier du projet est INCHANGÉ, octet pour octet.
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == avant


def test_la_negation_ne_se_confond_pas_avec_un_autre_fichier(tmp_path: Path) -> None:
    """`!.env.example` n'est pas notre sujet : l'accuser ferait dénoncer la bonne pratique."""
    (tmp_path / ".gitignore").write_text("!.env.example\n", encoding="utf-8")

    assert gabarit_env.proteger(tmp_path)["etat"] == "ajoutee"


def test_un_commentaire_qui_cite_le_nom_ne_compte_pas_pour_une_protection(tmp_path: Path) -> None:
    """Un contrôle qui accepte un COMMENTAIRE comme preuve rend un vert sur rien."""
    (tmp_path / ".gitignore").write_text("# .env.forge-tests reste local\n", encoding="utf-8")

    assert gabarit_env.proteger(tmp_path)["etat"] == "ajoutee"
