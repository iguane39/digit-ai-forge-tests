"""G5 — unification du compteur maison et du contrat du composant D-12 (dette du 15/08/2026).

Le dashboard outille ses tables depuis TF-0175 : recherche, réinitialisation, tri, et un
compteur `.outil-compte` que son propre script tient à jour. Le composant de filtres de colonne
D-12, lui, attend un élément portant `data-tf-count-for="<id-table>"` pour savoir OÙ annoncer
les lignes qu il masque — marquage qu aucune table du dashboard ne portait. Résultat mesuré par
`oracle-filtres-tableau.mjs` : un bloquant G4 (table filtrable sans `id`) et trois bloquants G5
(aucun compteur nommé), sur une page qui affichait pourtant un compte juste. Deux mécaniques qui
faisaient le même travail sans se connaître.

L unification ne duplique pas le compteur : elle POSE le marqueur sur celui qui existe. Le
script maison reste l unique écrivain — et cette exclusivité est elle-même vérifiée ici, parce
que le composant, lui, ne compte QUE ses filtres de colonne : son chiffre serait faux dès qu une
recherche ou un KPI d état filtre aussi.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from forge_tests.livrables import dashboard as dash

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def page() -> str:
    """La page de la recette de socle : le seul rapport qui arme toutes les règles en cause
    (≥ 8 constats, colonnes catégorielles, chapitre à sous-chapitres)."""
    import importlib.util

    chemin = RACINE / "recette" / "preuve_dashboard_socle.py"
    spec = importlib.util.spec_from_file_location("preuve_socle", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dash.construire(module.RAPPORT, module.CONTEXTE, module.CHAPITRES)


def _tables_filtrables(page: str) -> list[str]:
    return re.findall(r"<table\b[^>]*\bdata-filterable(?![-=])[^>]*>", page)


# --- 1. Le contrat, sur la page réellement produite ---------------------------------------------
def test_toute_table_filtrable_porte_un_identifiant(page: str) -> None:
    """G4 — le défaut d origine : une table du chapitre était filtrable sans `id`, donc ni
    initialisable ni rattachable. L identifiant est PARLANT (`table-chap-F1-0`), pas tiré au
    hasard : deux rendus du même rapport doivent rester identiques."""
    balises = _tables_filtrables(page)

    assert balises, "sans table filtrable, la page de recette ne prouverait rien"
    assert all(re.search(r'\bid="[^"]+"', b) for b in balises)
    assert 'id="table-chap-F1-0"' in page


def test_chaque_table_filtrable_a_SON_compteur_nomme(page: str) -> None:
    """G5 — le marquage attendu par le composant, table par table. Un compteur pour deux tables
    ne dirait pas laquelle un filtre vient de vider."""
    for balise in _tables_filtrables(page):
        identifiant = re.search(r'\bid="([^"]+)"', balise).group(1)
        compteur = re.search(rf'<[^>]+data-tf-count-for="{identifiant}"[^>]*>', page)
        assert compteur, f"table « {identifiant} » filtrable sans compteur nommé"
        assert 'aria-live="polite"' in compteur.group(0)


def test_le_marqueur_est_pose_sur_le_compteur_EXISTANT_pas_sur_un_doublon(page: str) -> None:
    """La contrainte de la dette : unifier, pas empiler. Un bloc outillé garde son unique
    `.outil-compte` — le marqueur s y ajoute, il n amène pas un second compte à côté."""
    blocs = re.findall(r'<div class="bloc-tableau">.*?</table></div></div>', page, re.DOTALL)

    assert blocs
    for bloc in blocs:
        assert bloc.count("outil-compte") == 1
        assert bloc.count("data-tf-count-for") == 1
        # ... et c est bien le même élément qui porte les deux.
        assert re.search(r'<span class="outil-compte" data-tf-count-for="[^"]+"', bloc)


def test_le_compte_par_table_du_CHAPITRE_s_ajoute_sans_toucher_a_l_agregat(page: str) -> None:
    """Le compteur du chapitre AGRÈGE ses sous-listes (TF-0175) : il ne peut pas nommer une
    table en particulier. Chaque table filtrable du chapitre porte donc son propre compte, et
    l agrégat garde son libellé « élément(s) », intact."""
    assert 'class="compte-table" data-tf-count-for="table-chap-F1-0"' in page
    assert "élément(s) affiché(s)</span></div>" in page  # la barre de chapitre, inchangée


# --- 2. Le script maison reste l UNIQUE écrivain ------------------------------------------------
def test_le_composant_ne_capture_JAMAIS_les_compteurs_a_l_initialisation(page: str) -> None:
    """Le composant lit `data-tf-count-for` une fois, à l init, et écrirait ensuite un chiffre
    calculé sur ses SEULS filtres de colonne — faux dès qu une recherche filtre aussi. L attribut
    lui est donc retiré le temps de `initAll()`, et remis aussitôt : la page garde son marquage,
    le script maison garde la plume."""
    init = page[page.index("DigitAITableFilters.initAll()") - 700 :]

    assert "data-tf-compte-de" in init
    assert init.index("removeAttribute('data-tf-count-for')") < init.index(
        "DigitAITableFilters.initAll()"
    )
    assert init.index("DigitAITableFilters.initAll()") < init.index(
        "setAttribute('data-tf-count-for'"
    )


def test_le_script_maison_tient_les_compteurs_nommes(page: str) -> None:
    """Et il les tient depuis SA notion de visibilité (`visible`), celle qui compose recherche,
    filtres de colonne et KPI d état — pas depuis un sous-ensemble."""
    assert "function majComptesMarques(bloc)" in page
    assert "'[data-tf-count-for]:not(.outil-compte)'" in page
    assert re.search(r"function recompter\(bloc\) \{\s*majComptesMarques\(bloc\);", page)


# --- 3. Le contrôle de pré-génération : la règle est ARMÉE, pas seulement tenue -----------------
def test_le_controle_de_pregeneration_est_VERT_sur_la_page_produite(page: str) -> None:
    assert dash._ecarts_comptes_de_table(page) == []
    assert dash.controle_pregeneration(page) == []


def test_une_table_filtrable_SANS_identifiant_est_un_ecart() -> None:
    """Fixture rouge : sans elle, la règle serait une déclaration d intention."""
    ecarts = dash._ecarts_comptes_de_table("<table data-filterable><tbody></tbody></table>")

    assert len(ecarts) == 1
    assert "G4-table-identifiee" in ecarts[0]


def test_une_table_identifiee_SANS_compteur_est_un_ecart() -> None:
    ecarts = dash._ecarts_comptes_de_table('<table id="t1" data-filterable></table>')

    assert len(ecarts) == 1
    assert "G5-compteur-nomme" in ecarts[0]
    assert "t1" in ecarts[0]


def test_un_compteur_MUET_pour_les_lecteurs_d_ecran_est_un_ecart() -> None:
    """`aria-live` absent = le chiffre change sans que personne ne l entende. C est le point que
    l oracle G5 traite en bloquant, et il a raison : un compte qu on ne perçoit pas ne remplit
    pas la fonction pour laquelle il existe."""
    ecarts = dash._ecarts_comptes_de_table(
        '<table id="t1" data-filterable></table><span data-tf-count-for="t1">3 / 3</span>'
    )

    assert len(ecarts) == 1
    assert "aria-live" in ecarts[0]


def test_une_table_exemptee_ou_nue_ne_declenche_rien() -> None:
    """Sens inverse : la règle ne se prononce que sur ce que le composant gouverne."""
    assert dash._ecarts_comptes_de_table("<table id=\"t\"><tbody></tbody></table>") == []
    assert dash._ecarts_comptes_de_table('<table id="t" data-filterable="off"></table>') == []


# --- 3 bis. TF-2279 : la colonne « Élément testé » quitte la facette, motivée -------------------
def test_la_colonne_element_du_chapitre_quitte_la_facette_avec_son_motif(page: str) -> None:
    """Fixture verte : chaque cellule de la colonne est une clé composite (libellé + identifiant),
    la facette aurait une valeur par ligne (G12 bloquant d'oracle-filtres-tableau). L'en-tête
    porte `data-filter-col="off"` ET `data-filter-reason` : la sortie est motivée, pas muette."""
    entetes = re.findall(r"<th\b[^>]*>Élément testé</th>", page)

    assert entetes
    chapitre = [e for e in entetes if 'data-filter-col="off"' in e]
    assert chapitre, "la colonne composite du chapitre doit sortir de la facette"
    assert all(re.search(r'data-filter-reason="[^"]{10,}"', e) for e in chapitre)


def test_une_colonne_sortie_de_la_facette_sans_demande_reste_dans_la_facette() -> None:
    """Fixture rouge : sans le paramètre, `_tableau` ne pose rien — la sortie n'est pas un défaut
    appliqué à toute colonne, elle se demande colonne par colonne, avec son motif."""
    lignes = [["a", "x"], ["b", "y"]]

    sans = dash._tableau(["élément", "état"], lignes)
    avec = dash._tableau(["élément", "état"], lignes, colonnes_hors_facette={"élément": "clé"})

    assert "data-filter-col" not in sans
    assert avec.count('data-filter-col="off" data-filter-reason="clé"') == 1


# --- 4. L oracle externe, quand le poste l a ----------------------------------------------------
ORACLE = (
    Path.home() / ".claude" / "skills" / "quality-oracles" / "scripts"
    / "oracle-filtres-tableau.mjs"
)


@pytest.mark.skipif(not ORACLE.exists(), reason="quality-oracles absent du poste")
def test_l_oracle_de_la_grille_G1_G6_rend_PASS(page: str, tmp_path: Path) -> None:
    """La preuve de campagne : le juge externe, exécuté, sur la page réellement produite."""
    import shutil

    node = shutil.which("node")
    if node is None:  # pragma: no cover — dépend du poste
        pytest.skip("node absent du poste")
    fichier = tmp_path / "dashboard.html"
    fichier.write_text(page, encoding="utf-8")

    resultat = subprocess.run(
        [node, str(ORACLE), str(fichier)], capture_output=True, text=True, encoding="utf-8"
    )

    assert resultat.returncode == 0, (resultat.stdout or "") + (resultat.stderr or "")


# --- 4 bis. TF-2292 : aucune colonne du tableau de bord ne rend G13 -----------------------------
def _regles_de_l_oracle(html: str, tmp_path: Path) -> list[str]:
    """Les règles qu'`oracle-filtres-tableau` lève sur `html` (avertissements compris)."""
    import json
    import shutil

    node = shutil.which("node")
    if node is None:  # pragma: no cover — dépend du poste
        pytest.skip("node absent du poste")
    fichier = tmp_path / "page.html"
    fichier.write_text(html, encoding="utf-8")
    resultat = subprocess.run(
        [node, str(ORACLE), str(fichier)], capture_output=True, text=True, encoding="utf-8"
    )
    return [f["regle"] for f in json.loads(resultat.stdout)["findings"]]


_CLES_DU_TABLEAU_DE_BORD = {
    "table-chap-F1-0": ["Constat mesuré — pourquoi", "Action — remède", "Risque"],
    "table-echecs": ["Risque", "Élément testé", "raison mesurée", "localisation"],
    "table-non-testables": ["Élément testé"],
    "table-actions": ["référence", "attendu"],
}


@pytest.mark.parametrize("table", sorted(_CLES_DU_TABLEAU_DE_BORD))
def test_les_colonnes_sans_regroupement_du_dashboard_quittent_la_facette_avec_leur_motif(
    page: str, table: str
) -> None:
    """Fixture verte, sans l'oracle du poste : chaque colonne qui rendait G13 (une valeur par
    ligne) porte `data-filter-col="off"` ET un motif, dans la table nommée."""
    corps = re.search(rf'<table id="{table}"[^>]*>(.*?)</thead>', page, re.S)
    assert corps, f"la table {table} manque à la page de recette"
    entetes = re.findall(r"<th\b([^>]*)>([^<]*)</th>", corps.group(1))

    for libelle in _CLES_DU_TABLEAU_DE_BORD[table]:
        attributs = [a for a, texte in entetes if texte == libelle]
        assert attributs, f"colonne « {libelle} » absente de {table}"
        assert 'data-filter-col="off"' in attributs[0], (table, libelle)
        assert re.search(r'data-filter-reason="[^"]{10,}"', attributs[0]), (table, libelle)


@pytest.mark.skipif(not ORACLE.exists(), reason="quality-oracles absent du poste")
def test_oracle_filtres_tableau_ne_rend_aucun_G13_sur_le_dashboard(
    page: str, tmp_path: Path
) -> None:
    """Fixture verte : le juge externe, sur la page de recette, ne lève plus d'avertissement.
    La page portait 10 G13 (constat, action, risque, élément, raison, localisation, référence,
    attendu) avant TF-2292."""
    assert "G13" not in _regles_de_l_oracle(page, tmp_path)


@pytest.mark.skipif(not ORACLE.exists(), reason="quality-oracles absent du poste")
def test_une_colonne_a_une_valeur_par_ligne_rend_G13_tant_qu_elle_reste_dans_la_facette(
    tmp_path: Path,
) -> None:
    """Fixture rouge, puis remède joué : sans déclaration, la colonne « référence » (une valeur
    par ligne, 10 lignes) lève G13 ; avec `colonnes_hors_facette`, la même table n'en lève plus.
    Prouve que le test précédent n'est pas vide."""
    lignes = [[f"réf-{i}", "ok" if i % 2 else "ko"] for i in range(10)]

    sans = dash._tableau(["référence", "état"], lignes, outille_force=True, identifiant="t")
    avec = dash._tableau(
        ["référence", "état"], lignes, outille_force=True, identifiant="t",
        colonnes_hors_facette={"référence": "clé unique par ligne : la recherche suffit"},
    )

    assert "G13" in _regles_de_l_oracle(sans, tmp_path)
    assert "G13" not in _regles_de_l_oracle(avec, tmp_path)


def test_le_dashboard_reste_DETERMINISTE(page: str) -> None:
    """Les identifiants dérivés du contenu ne doivent pas faire diverger deux rendus du même
    rapport : le sceau des livrables en dépend."""
    import importlib.util

    chemin = RACINE / "recette" / "preuve_dashboard_socle.py"
    spec = importlib.util.spec_from_file_location("preuve_socle_bis", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert dash.construire(module.RAPPORT, module.CONTEXTE, module.CHAPITRES) == page
