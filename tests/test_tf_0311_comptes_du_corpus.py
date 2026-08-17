"""TF-0311 — aucun compte du corpus recopié en dur dans la prose du README.

Le README annonçait « 19/19 des défauts » et « chacun des 16 défauts plantés » quand la recette
en mesurait 23 : un lecteur croyait à un corpus de 19 là où l'outil en éprouve 23 — la doc
démentait l'outil. C'est la loi 4 appliquée à la documentation : une donnée volatile (le compte
d'un registre qui grossit à chaque campagne) dupliquée en prose périme sans que rien ne le dise.

Le remède est le compte DÉRIVÉ : la prose renvoie à `CORPUS`, qui est la seule source. Ce test
est le verrou — il ne vérifie pas une formulation, il interdit la RÉCIDIVE : si un compte en dur
revient au README, il doit valoir `len(CORPUS)`. Fixture rouge du dossier : le témoin ci-dessous
prouve que le motif de détection attrape bien les deux formes historiquement fautives.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recette.verifier_corpus import CORPUS  # noqa: E402

README = Path(__file__).resolve().parent.parent / "README.md"

# Les deux formes RÉELLEMENT trouvées périmées le 17/08, généralisées : « 19/19 des défauts » et
# « chacun des 16 défauts plantés ». Le motif reste volontairement étroit — attraper tout nombre
# voisin du mot « défaut » ferait de ce verrou une gêne, et un verrou qui gêne se contourne.
_COMPTES_EN_DUR = re.compile(
    r"(\d+)\s*/\s*\d+\s*(?:\*\*)?\s*(?:des\s+)?d[ée]fauts"
    r"|des\s+(?:\*\*)?(\d+)(?:\*\*)?\s+d[ée]fauts\s+plant[ée]s"
    r"|corpus\s+de\s+(?:\*\*)?(\d+)(?:\*\*)?\s+d[ée]fauts",
    re.IGNORECASE,
)


def _comptes(texte: str) -> list[int]:
    return [
        int(groupe)
        for trouve in _COMPTES_EN_DUR.finditer(texte)
        for groupe in trouve.groups()
        if groupe
    ]


def test_le_README_ne_recopie_AUCUN_compte_du_corpus_ou_alors_le_bon() -> None:
    """Le verrou : soit la prose dérive (aucun compte), soit elle dit la vérité mesurée."""
    faux = [n for n in _comptes(README.read_text(encoding="utf-8")) if n != len(CORPUS)]

    assert not faux, (
        f"comptes du corpus périmés au README : {faux} — le corpus en mesure {len(CORPUS)}. "
        "Renvoyer à CORPUS plutôt que recopier le nombre (loi 4)."
    )


def test_le_verrou_ATTRAPE_bien_les_deux_formes_historiquement_fausses() -> None:
    """Second sens, et il est indispensable : un verrou dont le motif n attrape rien passerait
    vert sur le README fautif d hier. On lui redonne donc les deux phrases exactes."""
    fautif = (
        "La recette officielle détecte **19/19** des défauts plantés au banc rouge.\n"
        "chacun des **16** défauts plantés du banc rouge doit produire un finding nommé.\n"
    )

    assert sorted(_comptes(fautif)) == [16, 19]
    assert [n for n in _comptes(fautif) if n != len(CORPUS)] == [19, 16]


def test_un_compte_en_dur_JUSTE_reste_admis() -> None:
    """Le troisième sens : le verrou interdit le compte FAUX, pas le compte. Un rédacteur qui
    tient à écrire le nombre reste libre — c est ce test qui le tiendra à jour."""
    juste = f"la recette détecte **{len(CORPUS)}/{len(CORPUS)}** des défauts plantés"

    assert [n for n in _comptes(juste) if n != len(CORPUS)] == []
