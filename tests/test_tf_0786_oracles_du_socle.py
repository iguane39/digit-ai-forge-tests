"""TF-0786 — un verdict rendu par des ORACLES non épinglés n'est pas reproductible.

Constat du 02/09/2026, section `dashboard` de la recette. Elle joue `check_html.py` et
`render_page.py` depuis `~/.claude/skills/digit-ai-page-html/scripts/` — la copie INSTALLÉE,
qu'un autre chantier a mise à jour PENDANT la session : empreinte des règles `4b9b6179fb57` →
`c16177d42a88`, 31 → 36 règles, 14 → 18 familles de rendu. La section est passée de verte à
rouge sans qu'un octet du dépôt ne bouge. Même classe que la dérive de `ruff` (TF-0785).

Ce que ces tests câblent, en trois temps :

  1. l'identité des oracles joués est LUE aux oracles et CONSIGNÉE au rapport ;
  2. deux rapports d'empreintes différentes se DÉCLARENT non comparables — le taire ferait lire
     une régression du dépôt là où il n'y a qu'une montée de version du socle ;
  3. les deux constats restants sont corrigés À LA BONNE PLACE, dans le générateur de la page,
     et la forge les garde elle-même sans dépendre du skill installé (contrôle §2 bis) : L17
     (196 lignes de détail sans `id` ni bouton qui les vise) et l'écart d'alignement mesuré par
     `render_page` (22 px entre les commandes de deux chemins de lecteur à 768 px).

Chaque contrôle porte sa FIXTURE À DOUBLE SENS : le cas rouge est refusé, le cas vert accepté.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from forge_tests.livrables import dashboard as dash

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from recette import verifier_corpus as vc  # noqa: E402


# --- TF-0786 : l'identité des oracles du socle, consignée puis comparée -----------------------
def _faux_socle(dossier: Path, regles: int, familles: int, empreinte: str) -> Path:
    """Un socle de test : deux scripts qui publient la MÊME interface que les vrais.

    On ne teste pas les oracles du skill (ils ont leur propre banc) — on teste que la recette
    LIT leur identité et la rend. Des stubs suffisent, et rendent le test jouable sur un poste
    où le skill n'est pas installé.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "check_html.py").write_text(
        "import json\n"
        + f"print(json.dumps({{'regles': {list(range(regles))!r}, 'nombre': {regles}, "
        + f"'empreinte': {empreinte!r}}}))\n",
        encoding="utf-8",
    )
    table = {f"f{n}": {"libelle": f"famille {n}", "severite": "bloquant"} for n in range(familles)}
    (dossier / "render_page.py").write_text(
        "import json\n"
        + f"print(json.dumps({{'schema': 'digit-ai/familles-mesure@1', 'familles': {table!r}}}))\n",
        encoding="utf-8",
    )
    return dossier


def test_l_identite_des_oracles_est_LUE_a_l_oracle_jamais_recopiee(tmp_path: Path) -> None:
    """CAS VERT — l'empreinte publiée par `check_html.py` est reprise telle quelle, et celle de
    `render_page.py` est DÉRIVÉE de sa table de familles (il n'en publie pas)."""
    identite = vc.empreinte_oracles_socle(_faux_socle(tmp_path / "s", 36, 18, "c16177d42a88"))

    assert identite["check_html"] == {"empreinte": "c16177d42a88", "regles": 36}
    assert identite["render_page"]["familles"] == 18
    assert re.fullmatch(r"[0-9a-f]{12}", identite["render_page"]["empreinte"])
    assert re.fullmatch(r"[0-9a-f]{12}", identite["empreinte"])


def test_une_regle_qui_bouge_change_l_empreinte_c_est_tout_l_objet(tmp_path: Path) -> None:
    """CAS ROUGE du même contrôle : le fait du 02/09, rejoué. 31 règles / 14 familles puis
    36 / 18 — l'empreinte d'ensemble DOIT changer, sinon la comparaison ne verrait rien."""
    avant = vc.empreinte_oracles_socle(_faux_socle(tmp_path / "a", 31, 14, "4b9b6179fb57"))
    apres = vc.empreinte_oracles_socle(_faux_socle(tmp_path / "b", 36, 18, "c16177d42a88"))

    assert avant["empreinte"] != apres["empreinte"]
    # ... et une table de familles qui bouge SEULE suffit : le nombre de règles n'est pas
    # le seul discriminant, sinon une famille renommée passerait au travers.
    familles_seules = vc.empreinte_oracles_socle(
        _faux_socle(tmp_path / "c", 31, 18, "4b9b6179fb57"))
    assert familles_seules["empreinte"] != avant["empreinte"]


def test_un_oracle_ABSENT_est_dit_absent_jamais_confondu_avec_une_version(tmp_path: Path) -> None:
    """L'absence n'est pas un vert, et ce n'est pas non plus « une autre version » : le rapport
    doit pouvoir dire lequel des deux cas il a rencontré."""
    identite = vc.empreinte_oracles_socle(tmp_path / "nulle-part")

    assert "absent" in identite["check_html"] and "absent" in identite["render_page"]
    lignes = "\n".join(vc.lignes_empreinte_oracles(identite))
    assert "ABSENT" in lignes and "check_html" in lignes


def test_deux_empreintes_DIFFERENTES_refusent_la_comparaison_et_le_DISENT() -> None:
    """CAS ROUGE — le cœur de TF-0786. Sans cette déclaration, une section passée de verte à
    rouge se lit comme une régression du dépôt ; c'était une montée de version du socle."""
    avant = {"empreinte": "4b9b6179fb57", "check_html": {"empreinte": "4b9b6179fb57"}}
    apres = {"empreinte": "c16177d42a88", "check_html": {"empreinte": "c16177d42a88"}}

    comparable, dit = vc.comparabilite(avant, apres)
    texte = "\n".join(dit)

    assert comparable is False
    assert "NON COMPARABLES" in texte
    assert "4b9b6179fb57" in texte and "c16177d42a88" in texte, "les deux empreintes sont NOMMÉES"
    assert "check_html" in texte, "le rapport dit LEQUEL des oracles a bougé"


def test_deux_empreintes_EGALES_laissent_la_comparaison_ouverte() -> None:
    """CAS VERT — un contrôle qui refuserait toujours ne dirait rien de plus qu'un silence."""
    identique = {"empreinte": "c16177d42a88"}

    comparable, dit = vc.comparabilite(dict(identique), dict(identique))

    assert comparable is True
    assert "comparables" in "\n".join(dit)


def test_sans_rapport_anterieur_l_absence_de_comparaison_est_DITE() -> None:
    """Le troisième état, celui qu'on oublie : rien à comparer n'est pas « comparable »."""
    comparable, dit = vc.comparabilite(None, {"empreinte": "abc123abc123"})

    assert comparable is True
    assert "aucun rapport anterieur" in "\n".join(dit)


def test_le_journal_fait_le_pont_d_une_execution_a_l_autre(tmp_path: Path) -> None:
    """Le mécanisme complet : consigné, relu, comparé. Un journal illisible ne casse rien —
    il rend `None`, et la recette dit « rien à comparer » plutôt que d'inventer."""
    journal = tmp_path / ".empreintes-oracles.json"
    identite = vc.empreinte_oracles_socle(_faux_socle(tmp_path / "s", 36, 18, "c16177d42a88"))

    assert vc.lire_journal_oracles(journal) is None
    vc.ecrire_journal_oracles(identite, journal)
    assert vc.lire_journal_oracles(journal) == identite
    assert json.loads(journal.read_text(encoding="utf-8"))["empreinte"] == identite["empreinte"]

    journal.write_text("ceci n est pas du JSON", encoding="utf-8")
    assert vc.lire_journal_oracles(journal) is None


def test_le_journal_du_poste_n_entre_PAS_dans_l_arbre_versionne() -> None:
    """TF-0294 : ce que la recette écrit pendant qu'elle tourne rend l'arbre instable et lui
    fait REFUSER son propre verdict. Le journal décrit le poste — il est ignoré, comme le
    gabarit de TF-0601."""
    gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")

    assert "recette/.empreintes-oracles.json" in gitignore


# --- TF-0786 (2) : les constats du tableau de bord, corrigés à la bonne place -----------------
_DETAIL_SANS_ID = (
    '<table><tbody><tr><td><button type="button" class="btn-detail" '
    'aria-expanded="false">raison ▸</button></td></tr>'
    '<tr data-detail hidden><td colspan="1">…</td></tr></tbody></table>'
)
_DETAIL_ORPHELIN = (
    '<table><tbody><tr><td><button type="button" class="btn-detail" '
    'aria-expanded="false">raison ▸</button></td></tr>'
    '<tr data-detail id="t-detail-0" hidden><td colspan="1">…</td></tr></tbody></table>'
)
_DETAIL_CIBLE = (
    '<table><tbody><tr><td><button type="button" class="btn-detail" '
    'aria-controls="t-detail-0" aria-expanded="false">raison ▸</button></td></tr>'
    '<tr data-detail id="t-detail-0" hidden><td colspan="1">…</td></tr></tbody></table>'
)


def test_L17_une_ligne_de_detail_SANS_id_est_refusee() -> None:
    """CAS ROUGE — l'état du 02/09 : 196 constats L17 sur le tableau de bord de la forge. Le
    dépliage se faisait par voisinage DOM : vrai pour la souris, muet pour l'assistance."""
    ecarts = dash._ecarts_lignes_de_detail(_DETAIL_SANS_ID)

    assert ecarts and "L17-detail-identifie" in ecarts[0]
    assert "1 ligne(s)" in ecarts[0]


def test_L17_une_ligne_de_detail_qu_AUCUN_bouton_ne_vise_est_refusee() -> None:
    """CAS ROUGE n°2 : l'`id` seul ne suffit pas. Un identifiant que rien ne cite est un
    identifiant décoratif — exactement le défaut G4/G5 déjà payé sur les tables filtrables."""
    ecarts = dash._ecarts_lignes_de_detail(_DETAIL_ORPHELIN)

    assert ecarts and "L17-detail-cible" in ecarts[0]
    assert "t-detail-0" in ecarts[0], (
        "le constat NOMME la ligne : un total anonyme ne se corrige pas")


def test_L17_une_ligne_de_detail_identifiee_ET_visee_passe() -> None:
    """CAS VERT — le contrôle DISCRIMINE : sans ce test, `return [ecart]` passerait les deux
    cas rouges ci-dessus et ne prouverait rien."""
    assert dash._ecarts_lignes_de_detail(_DETAIL_CIBLE) == []


def test_une_page_SANS_ligne_de_detail_ne_declenche_rien() -> None:
    """La règle ne se prononce que si la page avait de quoi porter le marqueur — un chapitre
    sans cas dérivé ne doit pas accuser."""
    assert dash._ecarts_lignes_de_detail("<table><tbody><tr><td>x</td></tr></tbody></table>") == []


def test_le_generateur_CABLE_le_rattachement_il_ne_le_documente_pas() -> None:
    """Loi transverse n°1 : l'affordance est câblée ou elle n'existe pas. C'est le générateur
    de tables qui pose l'`id` et l'`aria-controls`, pas une consigne dans un docstring."""
    bouton = '<button type="button" class="btn-detail" aria-expanded="false">raison ▸</button>'
    rendu = dash._tableau(
        ["élément", "détail du cas"],
        [["E-1", bouton], ["E-2", bouton]],
        identifiant="table-preuve",
        chapitre=True,
        details_lignes=["<p>premier</p>", "<p>second</p>"],
    )

    assert 'id="table-preuve-detail-0"' in rendu and 'id="table-preuve-detail-1"' in rendu
    assert 'aria-controls="table-preuve-detail-0"' in rendu
    assert 'aria-controls="table-preuve-detail-1"' in rendu
    assert dash._ecarts_lignes_de_detail(rendu) == []
    # Deux rendus du même contenu restent identiques : le déterminisme des livrables est
    # vérifié en recette, et un identifiant tiré au hasard le romprait.
    assert rendu == dash._tableau(
        ["élément", "détail du cas"],
        [["E-1", bouton], ["E-2", bouton]],
        identifiant="table-preuve",
        chapitre=True,
        details_lignes=["<p>premier</p>", "<p>second</p>"],
    )


def test_une_table_SANS_detail_garde_exactement_le_rendu_d_avant() -> None:
    """Non-régression : le rattachement ne doit rien changer là où il n'y a pas de détail —
    ni identifiant surnuméraire, ni attribut posé sur un bouton de filtre ou de tri."""
    rendu = dash._tableau(["a", "b"], [["1", "2"]], identifiant="t", chapitre=True)

    assert "data-detail" not in rendu and "aria-controls" not in rendu


# --- TF-0786 (3) : les commandes de deux chemins voisins s'alignent ---------------------------
@pytest.fixture(scope="module")
def page_socle() -> str:
    """La page de la recette de socle — le rapport qui arme toutes les règles du gabarit."""
    chemin = RACINE / "recette" / "preuve_dashboard_socle.py"
    spec = importlib.util.spec_from_file_location("preuve_socle_alignement", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dash.construire(module.RAPPORT, module.CONTEXTE, module.CHAPITRES)


def test_les_boutons_des_chemins_de_lecteur_sont_colles_au_bas_de_leur_carte(
    page_socle: str,
) -> None:
    """CAS VERT — `render_page.py` mesurait 22 px d'écart entre les commandes de deux cartes
    voisines à 768 px (tolérance 2 px) : deux textes d'introduction de longueurs différentes
    décalaient les boutons. Le bloc d'actions est désormais poussé au bas de sa carte."""
    assert '<span class="c-actions">' in page_socle
    assert ".chemin .c-actions { margin-top:auto" in page_socle
    assert ".chemin { " in page_socle.replace("\n", " ") or "flex-direction:column" in page_socle
    assert dash.controle_pregeneration(page_socle) == []


def test_un_gabarit_qui_perd_l_alignement_des_actions_est_DENONCE(page_socle: str) -> None:
    """CAS ROUGE — la contre-épreuve du contrôle de pré-génération : on retire la règle CSS de
    la page rendue, et la dérive doit être nommée. Sans cela, la règle ne garderait rien."""
    ampute = page_socle.replace(".chemin .c-actions { margin-top:auto; }", "")

    ecarts = dash.controle_pregeneration(ampute)

    assert any("L26bis-actions-alignees" in e for e in ecarts)


def test_un_gabarit_SANS_chemins_de_lecteur_ne_declenche_pas_la_regle() -> None:
    """La règle est CONDITIONNELLE : elle ne se prononce que si la page porte des chemins de
    lecteur. Accuser une page qui n'en a pas serait du bruit pur."""
    ecarts = dash.controle_pregeneration("<html><body><p>rien de tel ici</p></body></html>")

    assert not any("L26bis" in e for e in ecarts)
