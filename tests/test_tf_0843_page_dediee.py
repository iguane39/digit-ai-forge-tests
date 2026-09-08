"""TF-0843 — deux contrôles justes qui s'excluaient, et l'action qu'aucun geste ne pouvait solder.

LE FAIT (lot Produit-61, retour du 05/09/2026). Une **page dédiée** — `inscription.html`, dont le
formulaire EST la page — recevait « création sans motif » du pan `interface` : elle ne porte ni
`<details>` + `data-cible` (il n'y a rien à replier, on est déjà sur le formulaire), ni
`?nouveau=` (il n'y a rien à adresser, la page a sa propre URL). Et quand le projet déclarait le
panneau adressable pour satisfaire ce contrôle, l'oracle de panneau adressable de forge-design
(PA6) le **refusait** à son tour, faute de déclencheur dans le document — puisque le déclencheur,
sur une page dédiée, est le lien qui a amené l'utilisateur ici, et il vit sur une **autre** page.

Deux contrôles justes, et leur conjonction sans issue : **une action `manuelle_dev` qu'aucune
modification du gabarit ne pouvait fermer**. Un écart qu'aucun geste ne peut solder n'est pas une
exigence, c'est une impasse — et c'est exactement le défaut que TF-0708 avait déjà payé une fois,
sous une autre forme (une règle affaiblie pour laisser passer une correction réelle).

La forme manquait à l'énumération, pas au produit. La page dédiée est le **troisième** motif, et
le plus ancien des trois. Le critère est mécanique : l'affordance qui ANNONCE la création est-elle
le contrôle qui SOUMET un formulaire de la page ?

  * page dédiée → « Créer mon compte » est un `<button>` DANS le `<form>` : il l'envoie ;
  * écran de liste → « Nouveau lot » est HORS du formulaire : il ouvre un panneau, et l'écran
    doit alors porter (a) ou (b).
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import classes
from forge_tests.adaptateurs.interface import (
    MOTIF_FORMULAIRE_REPLIE,
    MOTIF_PAGE_DEDIEE,
    MOTIF_PANNEAU_ADRESSABLE,
    _findings_ecrans_de_creation,
    annonce_une_creation,
    juger_ecran_de_creation,
    motifs_de_creation,
    porte_une_page_dediee,
)

#: Le gabarit du retour : la page EST le formulaire d'inscription.
_PAGE_DEDIEE = """<!doctype html><html lang="fr"><body>
<h1>Inscription</h1>
<form action="/inscription" method="post">
  <label for="courriel">Courriel</label><input id="courriel" name="courriel" type="email">
  <label for="mdp">Mot de passe</label><input id="mdp" name="mdp" type="password">
  <button type="submit">Creer mon compte</button>
</form>
</body></html>"""

#: La même page, dont le bouton d'envoi est un `<input type=submit>`.
_PAGE_DEDIEE_INPUT = """<!doctype html><html lang="fr"><body>
<h1>Inscription</h1>
<form action="/inscription" method="post">
  <input name="courriel" type="email">
  <input type="submit" value="Creer mon compte">
</form>
</body></html>"""

#: L'écran de liste, inchangé : le « Nouveau lot » est HORS du formulaire — il ouvre un panneau.
#: La barre de recherche est là exprès : une page de liste porte souvent un `<form>`, et ce n'est
#: pas ce qui en ferait une page de création.
_LISTE_SANS_MOTIF = """<!doctype html><html><body>
<h1>Lots</h1>
<form action="/lots" method="get"><input name="q"><button type="submit">Rechercher</button></form>
<button onclick="ouvrir()">Nouveau lot</button>
</body></html>"""

#: Le formulaire replié de TF-0708 : l'annonce est portée par le `<summary>`, hors du `<form>`.
_REPLIE = """<!doctype html><html><body>
<h1>Lots</h1>
<details><summary>Nouveau lot</summary>
  <form action="/lots" method="post" data-cible="lot"><input name="nom"></form>
</details>
</body></html>"""


# --- Le troisième motif, dans les deux sens -----------------------------------------------------


def test_vert_la_page_dediee_n_est_plus_un_ecart() -> None:
    """Le cas du 05/09 : l'action ne pouvait être soldée par aucune modification du gabarit."""
    assert annonce_une_creation(_PAGE_DEDIEE), "le declencheur de TF-0708 s allume bien ici"
    assert porte_une_page_dediee(_PAGE_DEDIEE)
    assert motifs_de_creation(_PAGE_DEDIEE) == {MOTIF_PAGE_DEDIEE}
    assert juger_ecran_de_creation(_PAGE_DEDIEE) is None


def test_vert_la_soumission_par_input_compte_aussi() -> None:
    """Le motif porte sur la SOUMISSION, pas sur le choix de la balise."""
    assert motifs_de_creation(_PAGE_DEDIEE_INPUT) == {MOTIF_PAGE_DEDIEE}
    assert juger_ecran_de_creation(_PAGE_DEDIEE_INPUT) is None


def test_rouge_un_ecran_de_liste_sans_motif_le_RESTE() -> None:
    """FIXTURE ROUGE — admettre une troisième forme n'est pas n'en exiger aucune.

    Ce cas porte le piège qui rendrait la règle inutile : la page de liste a un `<form>` (sa
    barre de recherche), et son affordance de création est DEHORS.
    """
    assert annonce_une_creation(_LISTE_SANS_MOTIF)
    assert not porte_une_page_dediee(_LISTE_SANS_MOTIF)
    assert motifs_de_creation(_LISTE_SANS_MOTIF) == set()

    motif = juger_ecran_de_creation(_LISTE_SANS_MOTIF)
    assert motif is not None
    assert "trois motifs" in motif and "page dediee" in motif and "TF-0843" in motif


def test_le_formulaire_replie_n_est_PAS_requalifie_en_page_dediee() -> None:
    """Non-régression de TF-0708 : l'annonce y est portée par le `<summary>`, hors du `<form>`."""
    assert not porte_une_page_dediee(_REPLIE)
    assert motifs_de_creation(_REPLIE) == {MOTIF_FORMULAIRE_REPLIE}


def test_un_bouton_d_envoi_NEUTRE_ne_fabrique_pas_le_motif() -> None:
    """BORNE : le motif se lit sur le libellé, aux mêmes deux bornes mesurées que TF-0708.

    Et la conséquence est saine : sans annonce, le contrôle ne se déclenche pas du tout — la
    page n'est pas jugée plutôt qu'accusée à côté.
    """
    neutre = _PAGE_DEDIEE.replace("Creer mon compte", "Valider")

    assert not porte_une_page_dediee(neutre)
    assert not annonce_une_creation(neutre)
    assert juger_ecran_de_creation(neutre) is None


def test_un_libelle_long_dans_un_formulaire_ne_fabrique_pas_le_motif() -> None:
    """La borne des 4 mots vaut ici comme ailleurs : sans elle, les 7 faux positifs reviennent."""
    long = _PAGE_DEDIEE.replace(
        "Creer mon compte", "Je souhaite creer un compte sur ce service"
    )

    assert not porte_une_page_dediee(long)


# --- Ce que le rapport dit ----------------------------------------------------------------------


def test_le_gabarit_du_retour_ne_produit_plus_de_finding(tmp_path: Path) -> None:
    """De bout en bout, sur le disque, comme l'audit le fait."""
    (tmp_path / "inscription.html").write_text(_PAGE_DEDIEE, encoding="utf-8")

    findings, non_juge = _findings_ecrans_de_creation(tmp_path)

    assert findings == []
    assert any("en page dediee" in ligne for ligne in non_juge), (
        "le rapport doit COMPTER ce motif, sinon on ne sait pas qu il a joue")


def test_le_compte_par_motif_distingue_les_trois_formes(tmp_path: Path) -> None:
    (tmp_path / "inscription.html").write_text(_PAGE_DEDIEE, encoding="utf-8")
    (tmp_path / "lots.html").write_text(_REPLIE, encoding="utf-8")
    (tmp_path / "liste.html").write_text(_LISTE_SANS_MOTIF, encoding="utf-8")

    findings, non_juge = _findings_ecrans_de_creation(tmp_path)

    assert [f.classe for f in findings] == [classes.ECRAN_DE_CREATION_SANS_MOTIF]
    resume = " ".join(non_juge)
    assert "3 gabarit(s) annoncant une creation" in resume
    assert "1 en formulaire replie" in resume
    assert "1 en page dediee" in resume
    assert "1 sans aucun des trois" in resume


def test_la_limite_du_motif_est_declaree(tmp_path: Path) -> None:
    """Une règle dont la borne n'est pas dite se relit comme une règle sans borne."""
    (tmp_path / "inscription.html").write_text(_PAGE_DEDIEE, encoding="utf-8")

    _findings, non_juge = _findings_ecrans_de_creation(tmp_path)

    declare = " ".join(non_juge)
    assert "TF-0843" in declare
    assert "libelle neutre" in declare and "Valider" in declare


def test_le_panneau_adressable_reste_reconnu() -> None:
    """Non-régression : la forme (b) n'a pas bougé."""
    adressable = """<!doctype html><html><body>
<h1>Connexions</h1>
<a href="/connexions?nouveau=sql">Nouvelle connexion SQL</a>
</body></html>"""

    assert motifs_de_creation(adressable) == {MOTIF_PANNEAU_ADRESSABLE}
