"""TF-2097 — une page-liste dont « Creer » mene a une page dediee n est plus accusee.

Le controle interface/creation accusait « creation sans AUCUN motif » un ecran de LISTE dont
le lien « Creer » mene a une page dediee (`/lots/nouvelle`) que le MEME controle reconnait par
ailleurs (motif page-dediee, TF-0843). Sur une liste, le declencheur de creation est un
`<a href>` HORS formulaire : il ne soumet rien (pas (c)), ne porte ni `<details>`+`data-cible`
(a) ni `?nouveau=` (b) — il MENE a la page ou la creation a lieu. Accuser la liste alors que
sa page de creation EXISTE etait une impasse de la meme famille que TF-0843.
"""

from __future__ import annotations

from forge_tests.adaptateurs import interface

_LISTE_AVEC_LIEN = """<!doctype html><html lang="fr"><body>
  <h1>Lots</h1>
  <a href="/lots/nouvelle">Creer</a>
  <table><tbody><tr><td>Lot A</td></tr></tbody></table>
</body></html>"""

_LISTE_SANS_ISSUE = """<!doctype html><html lang="fr"><body>
  <h1>Lots</h1>
  <button type="button">Nouveau lot</button>
  <table><tbody><tr><td>Lot A</td></tr></tbody></table>
</body></html>"""


def test_liste_avec_lien_vers_page_dediee_n_est_pas_accusee() -> None:
    # AVANT le correctif : « ecran annoncant une creation sans AUCUN des trois motifs ».
    assert interface.juger_ecran_de_creation(_LISTE_AVEC_LIEN) is None


def test_liste_sans_issue_reste_accusee() -> None:
    """Sens rouge du bornage : un « Nouveau lot » qui n ouvre ni page dediee ni panneau est
    toujours accuse — le controle protege toujours contre une creation sans issue."""
    motif = interface.juger_ecran_de_creation(_LISTE_SANS_ISSUE)
    assert motif is not None and "sans AUCUN" in motif


def test_le_lien_de_creation_est_reconnu_par_sa_cible() -> None:
    # Le lien de liste est reconnu comme la SECONDE forme de la page dediee (motif (c), TF-2097).
    assert interface.porte_un_lien_vers_page_dediee(_LISTE_AVEC_LIEN)
    assert interface.MOTIF_PAGE_DEDIEE in interface.motifs_de_creation(_LISTE_AVEC_LIEN)
    # Un lien de navigation ordinaire vers la liste elle-meme ne declenche pas.
    assert not interface.porte_un_lien_vers_page_dediee('<a href="/lots">Voir</a>')
    # Un panneau adressable (?nouveau=) reste le motif (b), jamais confondu avec la page dediee.
    assert not interface.porte_un_lien_vers_page_dediee('<a href="/x?nouveau=1">Creer</a>')
