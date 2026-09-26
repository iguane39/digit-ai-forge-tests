"""TF-1332 (part forge-tests) — le README omettait i18n, contraste, clavier et plancher de la
liste de `--pans`.

Constat du 23/09/2026 : le README (vers la ligne 79) listait les pans de `--pans` sans i18n,
contraste, clavier ni plancher — une liste écrite À LA MAIN qui a divergé du registre au fil des
quatre pans ajoutés depuis (`PANS_ATTENDUS`, dans `forge_tests/adaptateurs/__init__.py`), sans
qu'aucun contrôle ne le remarque. Le `--help` du CLI, lui, ne périmait JAMAIS : il compose déjà
son aide par `", ".join(PANS_ATTENDUS)` (`forge_tests/__main__.py`) — seule la copie à la main du
README pouvait diverger.

Ce fichier ne se contente pas de corriger la liste : il la DÉRIVE de la mesure (loi n° 4 du
pilot — une donnée périssable vit éditable, pas recopiée en dur dans un contrôle qui la croit).
Le test confronte la liste écrite au README à `PANS_ATTENDUS`, rouge à la moindre divergence —
qu'un pan futur s'ajoute au registre sans toucher au README, ou qu'il soit retiré du registre
sans qu'on pense à l'enlever du README.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from forge_tests.adaptateurs import PANS_ATTENDUS  # noqa: E402

README = RACINE / "README.md"

# La ligne cible, telle qu'écrite au README : « ... restreint l'audit à ces pans (`a b c`) ... ».
# Motif étroit et non un simple `pans\s*\(` : ce tableau contient d'autres phrases qui nomment un
# SOUS-ENSEMBLE de pans (« six pans exigent une instance servie », par exemple) — ce n'est pas la
# même prétention, et les confondre ferait échouer ce verrou sur des phrases qu'il n'a pas à juger.
_LIGNE_PANS_CLI = re.compile(r"restreint l'audit à ces pans \(`([^`]+)`\)")


def _pans_declares_au_readme(texte: str) -> list[str]:
    """Les pans que le README PRÉTEND accepter pour `--pans`, dans leur ordre d'écriture."""
    trouve = _LIGNE_PANS_CLI.search(texte)
    assert trouve is not None, (
        "la ligne décrivant `--pans` au README a changé de forme : ce motif ne la trouve plus — "
        "l'adapter, pas le supprimer (une liste non vérifiée est une liste qui périme à nouveau)"
    )
    return trouve.group(1).split()


def test_la_liste_pans_du_readme_est_DERIVEE_de_PANS_ATTENDUS() -> None:
    """Le sens qui manquait le 23/09 : ni un pan absent (i18n, contraste, clavier, plancher
    l'étaient), ni un pan en trop (une entrée retirée du registre mais oubliée au README)."""
    declares = _pans_declares_au_readme(README.read_text(encoding="utf-8"))

    manquants = [pan for pan in PANS_ATTENDUS if pan not in declares]
    en_trop = [pan for pan in declares if pan not in PANS_ATTENDUS]
    assert not manquants and not en_trop, (
        f"README --pans diverge de PANS_ATTENDUS — manquants : {manquants or 'aucun'}, "
        f"en trop : {en_trop or 'aucun'}. Recopier depuis forge_tests.adaptateurs.PANS_ATTENDUS "
        "(loi 4 : une donnée dérivable ne se réécrit pas à la main)."
    )
    # Même ORDRE : c'est celui que `--help` compose déjà (`", ".join(PANS_ATTENDUS)`), et un
    # README qui le respecte peut s'y copier-coller mot pour mot sans jamais avoir à réordonner.
    assert declares == PANS_ATTENDUS, (
        f"README --pans ({declares}) dans un ORDRE différent de PANS_ATTENDUS ({PANS_ATTENDUS})"
    )


def test_le_verrou_ATTRAPE_la_liste_PERIMEE_du_23_09_2026() -> None:
    """Second sens, indispensable (même discipline que TF-0334) : sans lui, ce fichier passerait
    vert sur le README fautif qui a motivé l'item. La phrase est celle trouvée périmée, mot pour
    mot, avant correction."""
    fautif = (
        "| `--pans <pan> [...]` | restreint l'audit à ces pans (`front interface api data "
        "migrations batch fichiers back securite accessibilite visuel qualif prompts`) |"
    )

    declares = _pans_declares_au_readme(fautif)

    assert declares != PANS_ATTENDUS
    manquants = sorted(set(PANS_ATTENDUS) - set(declares))
    assert manquants == ["clavier", "contraste", "i18n", "plancher"], (
        "la liste périmée du 23/09 manquait exactement ces quatre pans — si ce n'est plus le "
        "cas, PANS_ATTENDUS a changé et cette fixture historique doit être relue, pas supprimée"
    )


def test_le_motif_ne_confond_pas_un_SOUS_ENSEMBLE_de_pans_avec_la_liste_CLI() -> None:
    """Garde anti-faux-positif : une phrase qui nomme quelques pans pour une autre raison (par
    exemple les pans qui exigent une instance servie) ne doit pas être lue comme LA liste de
    `--pans`, sous peine de faire échouer ce verrou sur une phrase qu'il n'a pas à juger."""
    sans_rapport = "Six pans exigent une instance servie (`front`, `qualif`, `accessibilite`)."

    assert _LIGNE_PANS_CLI.search(sans_rapport) is None
