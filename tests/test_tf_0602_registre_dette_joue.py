"""TF-0602 — le registre de dette est vérifié par la suite unitaire, pas seulement par la recette.

LE FAIT. Le `registre-dette.json` commité manquait de QUINZE entrées que le code déclarait :
`clavier-focus-001` à `-005`, `contraste-wcag-001` à `-005`, `plancher-rendu-001` à `-004` et
`accessibilite-a11y-006` — les limites de trois modules livrés les 22 et 23/08. C'est mot pour
mot le défaut fondateur de TF-0384 (« une dette qui n'entre pas au registre est de la prose »),
réapparu deux jours après sa correction, par une autre cause.

CE QUI MANQUAIT N'ÉTAIT PAS LE CONTRÔLE. `dette.verifier()` fonctionne, son code de sortie est
juste, et son message donne la commande qui répare. Il manquait son DÉCLENCHEUR : son seul
appelant était `recette/verifier_corpus.py`, qui dure plus de deux minutes et dont le verdict
était de toute façon refusé (TF-0601). La porte la plus fine du dépôt vivait derrière la plus
lourde et la plus cassée.

Ce test le fait descendre là où il coûte une seconde et se joue à chaque `pytest`. C'est la même
famille que TF-0545 — « rien ne joue l'ensemble des contrôles » — sur un objet différent : ici le
contrôle était bien DANS un ensemble, mais cet ensemble ne se jouait pas.

L'écart a été trouvé par un appel ACCIDENTEL à `--help`, qui régénérait le fichier au lieu
d'afficher une aide. Cette seconde moitié est corrigée dans le module lui-même et tenue ci-dessous.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from forge_tests import dette


def test_le_registre_commite_ne_derive_pas_de_ce_que_le_code_declare() -> None:
    """Le contrôle qui manquait de déclencheur, joué ici à chaque `pytest`.

    Une limite déclarée dans un `NON_JUGE` et absente du registre est une dette invisible : elle
    ne se compte pas, ne se priorise pas, et ne se comble jamais.
    """
    ecarts = dette.verifier()

    assert not ecarts, (
        f"{len(ecarts)} limite(s) déclarée(s) par le code et absente(s) du registre — "
        "régénérer avec `python -m forge_tests.dette` puis committer le fichier :\n  "
        + "\n  ".join(ecarts[:15])
    )


def test_une_dette_dont_le_code_a_disparu_est_FERMEE_ou_RETIREE_jamais_orpheline() -> None:
    """Deuxième sens, et il a fallu se corriger pour l'écrire juste.

    Le premier jet de ce test exigeait que toute entrée du registre soit encore déclarée par un
    module. C'était FAUX, et le registre avait raison contre lui : une dette COMBLÉE (`ok`, avec
    sa preuve nommée) voit son `NON_JUGE` disparaître du code — c'est le but — et elle reste au
    registre comme histoire. Trois entrées étaient dans ce cas.

    Ce qui doit vraiment être impossible, c'est l'orpheline SILENCIEUSE : une limite `todo` ou
    `assume` dont le code a disparu sans que personne ne le déclare. Elle gonfle le compte de la
    dette avec quelque chose que plus rien ne porte, et une mesure fausse dans ce sens-là est la
    plus difficile à repérer — elle ne casse rien.
    """
    collectes = {(e["domaine"], e["enonce"]) for e in dette.collecter()}
    orphelines = [
        e for e in dette.charger()
        if e["statut"] in ("todo", "assume")
        and (e["domaine"], e["enonce"]) not in collectes
    ]

    assert not orphelines, (
        f"{len(orphelines)} limite(s) `todo`/`assume` que plus aucun module ne déclare — "
        "elles se ferment avec une preuve (`ok`) ou se déclarent `retiree`, jamais orphelines : "
        + ", ".join(e["id"] for e in orphelines[:5])
    )


def test_aide_n_ecrit_rien_et_un_argument_inconnu_est_refuse() -> None:
    """`--help` RÉGÉNÉRAIT le registre — c'est ainsi que l'écart a été découvert.

    Un outil dont l'appel le plus inoffensif écrit est un outil qu'on déclenche par accident. Le
    contrôle porte sur les deux formes : l'aide qui doit se contenter d'afficher, et l'argument
    inconnu qui doit être refusé plutôt qu'interprété comme « fais quelque chose ».
    """
    avant = dette.REGISTRE.read_bytes()

    aide = subprocess.run(
        [sys.executable, "-m", "forge_tests.dette", "--help"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert aide.returncode == 0, f"`--help` sort en {aide.returncode}"
    assert "usage" in aide.stdout, "`--help` n'affiche pas de mode d'emploi"
    assert dette.REGISTRE.read_bytes() == avant, "`--help` a ÉCRIT dans le registre"

    inconnu = subprocess.run(
        [sys.executable, "-m", "forge_tests.dette", "--nimporte-quoi"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert inconnu.returncode == 2, (
        f"un argument inconnu sort en {inconnu.returncode} — il doit être REFUSÉ (2), "
        "jamais tomber dans la branche qui régénère"
    )
    assert dette.REGISTRE.read_bytes() == avant, "un argument inconnu a ÉCRIT dans le registre"


def test_le_verificateur_sait_ECHOUER_et_pas_seulement_passer() -> None:
    """Une porte neuve se valide en la faisant échouer une fois.

    C'est la règle que le lot Approval2 du 24/08 a formulée, et elle vaut ici : sans ce cas, on
    saurait que le contrôle rend vert, jamais qu'il sait rougir. Le registre réel n'est pas touché
    — la vérification travaille sur une copie amputée d'une entrée.
    """
    reel = dette.charger()
    assert reel, "registre vide : le cas rouge ne prouverait rien"

    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "registre-ampute.json"
        copie.write_text(
            json.dumps({"version": 2, "note": "copie de travail", "dette": reel[1:]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ecarts = dette.verifier(copie)

    assert ecarts, (
        "un registre amputé d'une entrée n'est PAS dénoncé — le contrôle ne sait pas rougir"
    )
    # Le constat LOCALISE, au domaine près. Il ne nomme pas forcément l'entrée retirée, et c'est
    # une propriété du format et non un défaut : les identifiants sont POSITIONNELS dans leur
    # domaine (`<domaine>-NNN`), donc amputer la première décale les suivantes et le manque se
    # présente comme une entrée de plus attendue en fin de domaine. Asserter l'id retiré aurait
    # été asserter faux — le premier jet de ce test le faisait.
    domaine = reel[0]["domaine"]
    assert any(domaine in e for e in ecarts), (
        f"le contrôle rougit sans localiser le domaine touché ({domaine}) — un refus qui ne "
        "localise pas se subit"
    )
    assert any("regenerer" in e for e in ecarts), (
        "le constat ne donne pas la commande qui répare — un refus sans remède se contourne"
    )
