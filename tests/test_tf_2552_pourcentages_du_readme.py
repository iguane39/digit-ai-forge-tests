"""TF-2552 — un pourcentage du README se recalcule contre le tableau qui le suit.

Le fait, relevé le 14/11/2026 par la factory (site vitrine) : la section « Une campagne se
termine » écrivait « 69 % des anomalies n'existaient pas au tour 1 », alors que le tableau juste
au-dessus donne 4, 9, 1, 0 anomalies par tour — 10 sur 14, soit 71 %. Le chiffre allait être publié
sur le site. Aucune relecture ne le rattrapait : un nombre écrit à la main à côté d'un tableau
dérive de lui sans rien casser.

Le contrôle (`ecarts_de_pourcentage`) lit chaque tableau du README dont la deuxième colonne est un
décompte, puis le texte qui le suit jusqu'au titre suivant, et recalcule contre lui :

  - « X anomalies sur Y (N %) » — Y est le total du tableau, X le compte du premier tour ou le reste
    de la campagne, et N est X rapporté à Y ;
  - « N % des anomalies n'existaient pas au tour 1 » — N est la part des anomalies hors du premier
    tour ;
  - tout autre pourcentage du voisinage est refusé : un chiffre qu'aucun tableau ne permet de
    recalculer n'est pas un chiffre vérifié.

Sens prouvés : ROUGE sur la phrase d'avant (69 %), VERT sur celle d'après, et le README réel.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

_LIGNE_TABLEAU = re.compile(r"^\|.*\|\s*$")
_RATIO_AVEC_POURCENT = re.compile(r"(\d+)\s+anomalies?\s+sur\s+(\d+)\s+\((\d+)\s*%\)")
_PART_HORS_TOUR_1 = re.compile(
    r"(\d+)\s*%\s+des\s+anomalies\s+n[’']existaient\s+pas\s+au\s+tour\s+1"
)
_POURCENT = re.compile(r"(\d+)\s*%")


def _arrondi(numerateur: int, denominateur: int) -> int:
    return int(100 * numerateur / denominateur + 0.5)


def _tableaux_de_decomptes(lignes: list[str]) -> list[tuple[list[int], int]]:
    """(décomptes de la 2e colonne, index de la ligne qui suit le tableau), pour chaque tableau
    dont toutes les lignes de données portent un entier (gras toléré) en 2e colonne."""
    trouves: list[tuple[list[int], int]] = []
    i = 0
    while i < len(lignes):
        if not _LIGNE_TABLEAU.match(lignes[i]):
            i += 1
            continue
        debut = i
        while i < len(lignes) and _LIGNE_TABLEAU.match(lignes[i]):
            i += 1
        donnees = []
        for ligne in lignes[debut + 2 : i]:  # l'en-tête et le filet ne sont pas des données
            cellules = [c.strip().strip("*").strip() for c in ligne.strip().strip("|").split("|")]
            if len(cellules) < 2 or not cellules[1].isdigit():
                donnees = []
                break
            donnees.append(int(cellules[1]))
        if len(donnees) >= 2:
            trouves.append((donnees, i))
    return trouves


def ecarts_de_pourcentage(readme: str) -> list[str]:
    """Les pourcentages du voisinage d'un tableau de décomptes que ce tableau ne confirme pas."""
    lignes = readme.splitlines()
    ecarts: list[str] = []
    for decomptes, suite in _tableaux_de_decomptes(lignes):
        voisinage = []
        for ligne in lignes[suite:]:
            if ligne.startswith("#"):
                break
            voisinage.append(ligne)
        texte = " ".join(voisinage)
        total, premier = sum(decomptes), decomptes[0]
        verifies: set[int] = set()
        for x, y, n in _RATIO_AVEC_POURCENT.findall(texte):
            x, y, n = int(x), int(y), int(n)
            verifies.add(n)
            if y != total or x not in (premier, total - premier):
                ecarts.append(
                    f"« {x} anomalies sur {y} » : le tableau compte {total} anomalies, "
                    f"{premier} au tour 1 et {total - premier} ensuite"
                )
            elif n != _arrondi(x, y):
                ecarts.append(f"« {x} sur {y} ({n} %) » : {x} sur {y} fait {_arrondi(x, y)} %")
        for n in (int(m) for m in _PART_HORS_TOUR_1.findall(texte)):
            verifies.add(n)
            attendu = _arrondi(total - premier, total)
            if n != attendu:
                ecarts.append(
                    f"« {n} % des anomalies n'existaient pas au tour 1 » : le tableau donne "
                    f"{total - premier} sur {total}, soit {attendu} %"
                )
        for n in (int(m) for m in _POURCENT.findall(texte)):
            if n not in verifies:
                ecarts.append(f"« {n} % » : aucun tableau voisin ne permet de le recalculer")
    return ecarts


_TABLEAU = (
    "| tour | anomalies | d'où elles viennent |\n"
    "|---|---|---|\n"
    "| 1 | 4 | l'audit |\n"
    "| 2 | **9** | des correctifs du tour 1 |\n"
    "| 3 | 1 | une course |\n"
    "| 4 | 0 | trois passages verts |\n"
)


def _readme(phrase: str) -> str:
    return f"## Une campagne se termine\n\n{_TABLEAU}\n{phrase}\n\n## Suite\n\nUn autre 50 % ici.\n"


def test_rouge_le_69_pour_cent_du_readme_d_avant_est_refuse() -> None:
    ecarts = ecarts_de_pourcentage(
        _readme("**69 % des anomalies n'existaient pas au tour 1.** Un mandat en laisse 10 sur 14.")
    )

    assert ecarts == [
        "« 69 % des anomalies n'existaient pas au tour 1 » : le tableau donne 10 sur 14, "
        "soit 71 %"
    ]


def test_vert_la_phrase_corrigee_passe() -> None:
    phrase = "**10 anomalies sur 14 (71 %) n'existaient pas au tour 1.** Il en manque 4 sur 4"
    assert ecarts_de_pourcentage(_readme(phrase)) == []


def test_rouge_un_pourcentage_faux_sur_un_ratio_juste_est_refuse() -> None:
    ecarts = ecarts_de_pourcentage(_readme("**10 anomalies sur 14 (69 %) n'existaient pas.**"))

    assert ecarts == ["« 10 sur 14 (69 %) » : 10 sur 14 fait 71 %"]


def test_rouge_un_ratio_qui_ne_vient_pas_du_tableau_est_refuse() -> None:
    ecarts = ecarts_de_pourcentage(_readme("**9 anomalies sur 13 (69 %) n'existaient pas.**"))

    assert len(ecarts) == 1 and "le tableau compte 14 anomalies" in ecarts[0]


def test_rouge_un_pourcentage_sans_ratio_ni_tableau_est_refuse() -> None:
    ecarts = ecarts_de_pourcentage(_readme("Une réduction de 40 % de la durée."))

    assert ecarts == ["« 40 % » : aucun tableau voisin ne permet de le recalculer"]


def test_vert_un_pourcentage_hors_du_voisinage_d_un_tableau_n_est_pas_juge() -> None:
    """Le contrôle ne lit que le texte qui suit un tableau de décomptes, jusqu'au titre suivant :
    le « 50 % » de la section suivante (fixture) ne lui appartient pas."""
    assert ecarts_de_pourcentage(_readme("**10 anomalies sur 14 (71 %).**")) == []


def test_le_readme_du_depot_est_coherent_avec_ses_tableaux() -> None:
    readme = (RACINE / "README.md").read_text(encoding="utf-8")

    assert ecarts_de_pourcentage(readme) == []
    assert "10 anomalies sur 14 (71 %)" in readme
    assert "69 %" not in readme
