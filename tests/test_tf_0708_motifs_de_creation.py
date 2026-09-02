"""TF-0708 — deux motifs légitimes d'écran de création, plutôt qu'un seul imposé partout.

LE FAIT (lot Produit-12, 16/08/2026). Une exigence d'interface imposait à TOUS les écrans le
motif « formulaire replié toujours présent » : un `<details>` et le `data-cible` qui le vise. Le
motif est bon quand le formulaire est court et unique. Il devient **nuisible** dès qu'il porte
des **branches exclusives** : le repli masque alors la contradiction au lieu de la résoudre.
**Le test a dû être ASSOUPLI** pour laisser passer la refonte de l'écran des connexions — une
règle affaiblie pour livrer une correction d'ergonomie réelle.

Un test qu'on assouplit pour laisser passer une amélioration vise le mauvais invariant. Ce qui
doit tenir n'est pas « ce motif-ci partout » mais « la création a une forme déclarée » :

  * **(a) formulaire replié** — `<details>` + `data-cible`, pour une création simple ;
  * **(b) panneau adressable** — `?nouveau=…`, pour une tâche à branches exclusives.

FIXTURE À DOUBLE SENS : un écran à panneau adressable **n'est plus un écart** ; un écran sans
aucun des deux motifs **le reste**.

LE BRUIT EST MESURÉ, PAS SUPPOSÉ. Version naïve du déclencheur (le mot n'importe où, libellé de
n'importe quelle longueur) sur le corpus réel d'un produit servi, 220 gabarits : **7
accusations, les 7 fausses** — toutes sur « Open the booking engine in a **new** tab ». Bornes
retenues : libellé de 4 mots au plus, annonce dans les 2 premiers. Même corpus : **0
accusation**. Les deux bornes sont tenues ci-dessous par leurs propres cas.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import classes
from forge_tests.adaptateurs.interface import (
    MOTIF_FORMULAIRE_REPLIE,
    MOTIF_PANNEAU_ADRESSABLE,
    _findings_ecrans_de_creation,
    annonce_une_creation,
    juger_ecran_de_creation,
    motifs_de_creation,
)

_REPLIE = """<!doctype html><html><body>
<h1>Lots</h1>
<details><summary>Nouveau lot</summary>
  <form action="/lots" method="post" data-cible="lot"><input name="nom"></form>
</details>
</body></html>"""

_ADRESSABLE = """<!doctype html><html><body>
<h1>Connexions</h1>
<a href="/connexions?nouveau=sql">Nouvelle connexion SQL</a>
<a href="/connexions?nouveau=api">Nouvelle connexion API</a>
</body></html>"""

_SANS_MOTIF = """<!doctype html><html><body>
<h1>Lots</h1>
<button onclick="ouvrir()">Nouveau lot</button>
</body></html>"""

#: Le faux positif MESURÉ sur le corpus réel : `new` y qualifie un onglet, pas une création.
_ONGLET = """<!doctype html><html><body>
<a href="https://exemple.test/moteur" target="_blank">Open the booking engine in a new tab</a>
</body></html>"""


def test_vert_le_panneau_adressable_n_est_plus_un_ecart() -> None:
    """Le cas qui avait forcé l'assouplissement : une tâche à branches, à son adresse."""
    assert annonce_une_creation(_ADRESSABLE)
    assert motifs_de_creation(_ADRESSABLE) == {MOTIF_PANNEAU_ADRESSABLE}
    assert juger_ecran_de_creation(_ADRESSABLE) is None


def test_vert_le_formulaire_replie_reste_legitime() -> None:
    """La correction n'affaiblit pas le motif d'origine : elle cesse de l'imposer seul."""
    assert motifs_de_creation(_REPLIE) == {MOTIF_FORMULAIRE_REPLIE}
    assert juger_ecran_de_creation(_REPLIE) is None


def test_rouge_un_ecran_sans_aucun_des_deux_motifs_reste_un_ecart() -> None:
    """Admettre deux formes n'est pas n'en exiger aucune."""
    motif = juger_ecran_de_creation(_SANS_MOTIF)
    assert motif is not None
    # Le constat porte le CRITÈRE DE CHOIX : sans lui, le lecteur sait qu'il manque quelque
    # chose mais pas lequel des deux motifs poser.
    assert "branche exclusive" in motif and "TF-0708" in motif
    assert "`<details>` + `data-cible`" in motif and "?nouveau=" in motif


def test_un_details_sans_data_cible_n_est_pas_le_motif() -> None:
    """Un accordéon de contenu n'est pas un formulaire replié visé par une affordance."""
    accordeon = _SANS_MOTIF.replace(
        "<button onclick=\"ouvrir()\">Nouveau lot</button>",
        "<details><summary>Nouveau lot</summary><p>texte</p></details>",
    )
    assert motifs_de_creation(accordeon) == set()
    assert juger_ecran_de_creation(accordeon) is not None


def test_le_parametre_adressable_est_declarable_par_le_projet() -> None:
    """`nouveau` est la convention du produit qui a payé le défaut, pas une loi universelle."""
    autre = _ADRESSABLE.replace("nouveau=", "creation=")
    assert juger_ecran_de_creation(autre) is not None
    assert juger_ecran_de_creation(autre, param="creation") is None


def test_le_bruit_mesure_le_libelle_long_n_est_pas_une_annonce_de_creation() -> None:
    """Les 7 faux positifs du corpus réel, tenus par leur cas : « … in a new tab »."""
    assert not annonce_une_creation(_ONGLET)
    assert juger_ecran_de_creation(_ONGLET) is None


def test_le_bruit_mesure_l_annonce_hors_des_deux_premiers_mots_ne_declenche_pas() -> None:
    """Seconde borne : un libellé court dont le verbe n'est pas en tête n'est pas un bouton."""
    tardif = '<html><body><a href="/x">Voir le tableau nouveau</a></body></html>'
    assert not annonce_une_creation(tardif)


def test_un_paragraphe_n_est_pas_un_ecran_de_creation() -> None:
    """L'annonce se lit sur les AFFORDANCES, jamais sur le document entier."""
    prose = "<html><body><p>Vous pouvez creer un compte depuis votre espace.</p></body></html>"
    assert not annonce_une_creation(prose)
    assert juger_ecran_de_creation(prose) is None


def test_le_controle_sur_projet_publie_ce_qu_il_a_regarde(tmp_path: Path) -> None:
    """Trois écrans, un seul écart — et le compte par motif est publié, pas seulement le total."""
    (tmp_path / "replie.html").write_text(_REPLIE, encoding="utf-8")
    (tmp_path / "adressable.html").write_text(_ADRESSABLE, encoding="utf-8")
    (tmp_path / "sans.html").write_text(_SANS_MOTIF, encoding="utf-8")

    findings, non_juge = _findings_ecrans_de_creation(tmp_path)

    assert len(findings) == 1
    (seul,) = findings
    assert seul.id == "creation:sans.html"
    assert seul.classe == classes.ECRAN_DE_CREATION_SANS_MOTIF
    assert seul.severite == "signale"

    resume = non_juge[0]
    assert "3 gabarit(s) annoncant une creation" in resume
    assert "1 en formulaire replie" in resume and "1 en panneau adressable" in resume
    assert "1 sans aucun des deux" in resume
    # Les deux bornes du déclencheur sont DITES avec leur mesure : un contrôle qui tait sa
    # précision demande qu'on lui fasse confiance.
    assert "7 accusations" in non_juge[1] and "220 gabarits" in non_juge[1]


def test_un_projet_sans_ecran_de_creation_le_dit_au_lieu_de_rendre_vert(tmp_path: Path) -> None:
    """« Le contrôle ne s'applique à rien » et « le contrôle a rendu vert » ne sont pas pareils."""
    (tmp_path / "page.html").write_text(_ONGLET, encoding="utf-8")
    findings, non_juge = _findings_ecrans_de_creation(tmp_path)
    assert findings == []
    assert "ne s applique a rien" in non_juge[0]
