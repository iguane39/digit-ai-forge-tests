"""TF-0334 — les deux comptes que le verrou de TF-0311 laissait passer, et la classe littérale.

TF-0311 a posé le verrou des comptes du corpus. Il était aveugle sur deux points, et les deux
ont été payés : (a) son motif ne lisait que des CHIFFRES — « treize adaptateurs » pour 14 et
« les onze autres » pans pour 14 sont restés faux au README pendant que le verrou passait vert ;
(b) il ne portait que sur le corpus, alors que la maladie est celle de tout compte recopié.

Ce fichier ferme les deux, plus le second volet de l item : la CLASSE de finding, littéral des
deux côtés du contrat de corpus, se lit désormais dans `forge_tests.classes`. Le verrou tient
les deux sens — aucune classe du corpus hors du module, aucun littéral de classe hors du module.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from forge_tests import classes  # noqa: E402
from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE  # noqa: E402

README = RACINE / "README.md"

# Les nombres écrits en toutes lettres jusqu'à vingt : le compte périmé du README s'écrivait
# « treize », pas « 13 » — c'est précisément pour ça qu'il a survécu au verrou de TF-0311.
_EN_LETTRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19, "vingt": 20,
}
_NOMBRE = r"(\d+|" + "|".join(sorted(_EN_LETTRES, key=len, reverse=True)) + r")"


def _charger_recette():
    os.environ["FORGE_TESTS_BASE_URL"] = ""
    spec = importlib.util.spec_from_file_location("vc", RACINE / "recette" / "verifier_corpus.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _comptes(texte: str, motif: str) -> list[int]:
    trouves = re.findall(motif, texte, re.IGNORECASE)
    plats = [n for t in trouves for n in ((t,) if isinstance(t, str) else t) if n]
    return [int(n) if n.isdigit() else _EN_LETTRES[n.lower()] for n in plats]


# Un mot compté = un motif. Le motif reste étroit, pour la raison écrite en TF-0311 : un verrou
# qui gêne se contourne. D'où trois règles, chacune adossée à un cas RÉEL et pas à une intuition.
_MOTIFS = {
    # A — « treize adaptateurs » (réel, 18/08). Aucun sous-ensemble d adaptateurs ne se compte
    # dans cette page : un « N adaptateurs » est toujours une prétention au total.
    "adaptateurs": _NOMBRE + r"\s+adaptateurs",
    # B — « comme les onze autres » (réel, 18/08) et « un silence sur les huit autres » (trouvé
    # par ce verrou en l écrivant). Un compte du COMPLÉMENT d un total périme par construction :
    # il est interdit, quelle que soit sa valeur. On écrit « les autres », ou on les nomme.
    "complement": r"les\s+" + _NOMBRE + r"\s+autres",
    # C — « en treize sections », juste aujourd hui : le verrou est là pour qu il le reste.
    "sections": r"en\s+" + _NOMBRE + r"\s+sections",
}

# D — les pans, eux, se comptent LÉGITIMEMENT par sous-ensembles (« les deux pans » = les deux
# nommés juste avant ; « Quatre pans exigent une instance servie » = PANS_SERVIS). Un verrou
# qui refuserait ces phrases serait une gêne. Il n admet donc un compte de pans que s il vaut
# un total DÉCLARÉ par le code, ou le nombre de pans NOMMÉS dans la même phrase.
_MOTIF_PANS = _NOMBRE + r"\s+(?:autres\s+)?pans"


def _phrases(texte: str) -> list[str]:
    return re.split(r"(?<=[.;:!?])\s+", texte)


def test_aucun_compte_d_adaptateurs_perime_au_README() -> None:
    faux = [n for n in _comptes(README.read_text(encoding="utf-8"), _MOTIFS["adaptateurs"])
            if n != len(REGISTRE)]
    assert not faux, (
        f"comptes d adaptateurs périmés au README : {faux} — le registre en déclare "
        f"{len(REGISTRE)}. Renvoyer au REGISTRE plutôt que recopier le nombre (loi 4)."
    )


def test_aucun_compte_du_COMPLEMENT_d_un_total_au_README() -> None:
    trouves = _comptes(README.read_text(encoding="utf-8"), _MOTIFS["complement"])
    assert not trouves, (
        f"comptes du complément d un total au README : « les {trouves} autres » — cette forme "
        "périme dès qu une entrée s ajoute. Écrire « les autres », ou les nommer."
    )


def test_aucun_compte_de_sections_de_recette_perime_au_README() -> None:
    recette = _charger_recette()
    faux = [n for n in _comptes(README.read_text(encoding="utf-8"), _MOTIFS["sections"])
            if n != len(recette.SECTIONS)]
    assert not faux, (
        f"comptes de sections périmés au README : {faux} — la recette en porte "
        f"{len(recette.SECTIONS)}."
    )


def test_tout_compte_de_pans_vaut_un_total_declare_ou_les_pans_nommes_a_cote() -> None:
    from forge_tests.instance import PANS_SERVIS

    totaux = {len(PANS_ATTENDUS), len(PANS_SERVIS)}
    faux: list[str] = []
    for phrase in _phrases(README.read_text(encoding="utf-8")):
        comptes = _comptes(phrase, _MOTIF_PANS)
        if not comptes:
            continue
        nommes = sum(1 for pan in PANS_ATTENDUS if f"`{pan}`" in phrase)
        for n in comptes:
            if n not in totaux and n != nommes:
                faux.append(f"{n} dans « {phrase.strip()[:90]} »")
    assert not faux, (
        f"comptes de pans ni total déclaré ({sorted(totaux)}) ni pans nommés dans la phrase : "
        + " | ".join(faux)
    )


def test_le_verrou_ATTRAPE_les_deux_formes_EN_LETTRES_qui_ont_survecu_a_TF_0311() -> None:
    """Second sens, indispensable : sans lui, ce fichier passerait vert sur le README fautif.

    Les deux phrases sont celles trouvées périmées le 18/08, mot pour mot.
    """
    fautif = (
        "Le noyau, treize adaptateurs, le générateur de cas, le registre de dette.\n"
        "il ne pourrait donc pas être exercé par un banc de fichiers, comme les onze autres.\n"
    )
    assert _comptes(fautif, _MOTIFS["adaptateurs"]) == [13]
    assert _comptes(fautif, _MOTIFS["complement"]) == [11]
    assert len(REGISTRE) != 13


def test_toute_classe_du_corpus_est_declaree_dans_forge_tests_classes() -> None:
    """Le contrat de corpus (TF-0310) ne cite plus une chaîne : il cite une constante."""
    recette = _charger_recette()
    citees = {classe for entree in recette.CORPUS for classe in entree[4]}
    inconnues = sorted(citees - classes.CLASSES)
    assert not inconnues, (
        f"classes citées par le corpus et déclarées nulle part : {inconnues} — "
        "les ajouter à forge_tests/classes.py, seule source des noms de classes."
    )


def test_aucun_litteral_de_classe_ne_subsiste_hors_du_module_des_classes() -> None:
    """La récidive : réécrire `classe=\"…\"` en dur rouvrirait exactement le trou refermé ici."""
    coupables: list[str] = []
    for fichier in sorted((RACINE / "forge_tests").rglob("*.py")):
        if fichier.name == "classes.py":
            continue
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'classe=(?!classes\.)"[a-z0-9-]+"|"classe":\s*"[a-z0-9-]+"', ligne):
                coupables.append(f"{fichier.relative_to(RACINE)}:{numero}")
    assert not coupables, (
        "littéraux de classe hors de forge_tests/classes.py : " + ", ".join(coupables)
    )
