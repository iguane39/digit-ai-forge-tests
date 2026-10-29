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

**TF-1407 (02/10/2026)** — la liste `--pans` n'était pas le seul endroit à périmer : la section
« Autres pans » du guide (son tableau « Conventions appliquées / Seuil ») omettait `contraste`,
`clavier` et `plancher` dans AUCUNE section ni ligne de tableau, alors que `--pans` les proposait
déjà depuis TF-1332. Un utilisateur pouvait demander ces trois pans sans savoir ce qu'ils
exigent de son projet. Les trois lignes ont été ajoutées au tableau ; le contrôle ci-dessous
étend le même principe (DÉRIVER de `PANS_ATTENDUS`, jamais recopier) à toute la documentation du
README : chaque pan attendu doit être nommé soit dans une ligne du tableau « Autres pans », soit
dans un en-tête de section dédiée (« pan `api` », « pans `data` et `migrations` »…) — les deux
formes réellement utilisées par ce README.
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
    # Fixture relue le 29/10/2026 (TF-1998, TF-2008) : `workers` et `supabase` n'existaient pas le
    # 23/09 ; la liste périmée les manque donc aussi, en plus des quatre pans de l'époque.
    assert manquants == ["clavier", "contraste", "i18n", "plancher", "supabase", "workers"], (
        "la liste périmée du 23/09 manquait exactement ces quatre pans — si ce n'est plus le "
        "cas, PANS_ATTENDUS a changé et cette fixture historique doit être relue, pas supprimée"
    )


def test_le_motif_ne_confond_pas_un_SOUS_ENSEMBLE_de_pans_avec_la_liste_CLI() -> None:
    """Garde anti-faux-positif : une phrase qui nomme quelques pans pour une autre raison (par
    exemple les pans qui exigent une instance servie) ne doit pas être lue comme LA liste de
    `--pans`, sous peine de faire échouer ce verrou sur une phrase qu'il n'a pas à juger."""
    sans_rapport = "Six pans exigent une instance servie (`front`, `qualif`, `accessibilite`)."

    assert _LIGNE_PANS_CLI.search(sans_rapport) is None


# ── TF-1407 · chaque pan attendu est documenté QUELQUE PART, pas seulement dans `--pans` ───────
#
# Deux formes, et seulement deux, sont réellement employées par ce README pour documenter un
# pan : une ligne du tableau « Autres pans » (colonne `Pan`, un ou plusieurs noms séparés par une
# virgule), ou un en-tête de section dédiée qui nomme le ou les pans qu'elle couvre (« pan
# `api` », « pans `data` et `migrations` »). Les deux formes sont DÉRIVÉES ici, jamais recopiées.

_SECTION_AUTRES_PANS = re.compile(
    r"### Autres pans\n\n\| Pan \| Conventions appliquées \| Seuil \|\n\|---\|---\|---\|\n"
    r"(.*?)\n\n",
    re.DOTALL,
)
_TOKEN_PAN = re.compile(r"`([a-zA-Z0-9éèàâîôûï_-]+)`")
# « pan `api` », « pans `data` et `migrations` », « pans `front`, `qualif`, ... » — une suite de
# jetons entre backticks séparés par une virgule ou le mot « et », immédiatement après « pan(s) ».
# TF-1407 : `i18n` porte un chiffre — le jeton l'accepte, sans quoi ce pan resterait indétectable
# partout dans le README, y compris après correction.
_PANS_EN_PROSE = re.compile(r"\bpans?\s+((?:`[a-zA-Z0-9éèàâîôûï_-]+`(?:\s*,\s*|\s+et\s+)?)+)")


def _pans_du_tableau_autres_pans(texte: str) -> set[str]:
    """Les pans nommés dans la colonne `Pan` du tableau « Autres pans »."""
    trouve = _SECTION_AUTRES_PANS.search(texte)
    assert trouve is not None, (
        "la section « Autres pans » (son tableau à 3 colonnes) a changé de forme : ce motif ne "
        "la trouve plus — l'adapter, pas le supprimer"
    )
    pans: set[str] = set()
    for ligne in trouve.group(1).splitlines():
        if not ligne.startswith("|"):
            continue
        colonne_pan = ligne.split("|")[1]
        pans.update(_TOKEN_PAN.findall(colonne_pan))
    return pans


def _pans_nommes_en_section_dediee(texte: str) -> set[str]:
    """Les pans nommés par une phrase « pan(s) `...` » — en-têtes de section dédiée comprises."""
    pans: set[str] = set()
    for bloc in _PANS_EN_PROSE.findall(texte):
        pans.update(_TOKEN_PAN.findall(bloc))
    return pans


def _pans_documentes_quelque_part(texte: str) -> set[str]:
    return _pans_du_tableau_autres_pans(texte) | _pans_nommes_en_section_dediee(texte)


def test_tous_les_pans_de_PANS_ATTENDUS_sont_documentes_quelque_part() -> None:
    """Le défaut du 24/09, confirmé encore présent le 02/10 : `contraste`, `clavier` et
    `plancher` n'apparaissaient dans AUCUNE section ni ligne de tableau du guide, alors que
    `--pans` les propose depuis TF-1332. Chaque pan de `PANS_ATTENDUS` doit être nommé au moins
    une fois, tableau « Autres pans » ou section dédiée confondus."""
    documentes = _pans_documentes_quelque_part(README.read_text(encoding="utf-8"))
    manquants = [pan for pan in PANS_ATTENDUS if pan not in documentes]
    assert not manquants, (
        f"pan(s) de PANS_ATTENDUS absent(s) de toute documentation du README : {manquants} — "
        "ajouter une ligne au tableau « Autres pans » ou une section dédiée les nommant"
    )


def test_le_verrou_ATTRAPE_l_absence_de_contraste_clavier_plancher_du_02_10_2026() -> None:
    """Second sens, indispensable (même discipline que TF-1332) : rejoue le README tel qu'il
    était avant la correction TF-1407 — tableau « Autres pans » SANS les trois lignes ajoutées,
    en-têtes de section dédiée inchangés (`api`, `data`/`migrations`, `front`/`qualif`/
    `accessibilite`/`visuel`), pour isoler exactement ce que la correction a ajouté."""
    readme_perime = (
        "### Application ASGI — pan `api`\n\n"
        "### Couche SQL observable — pans `data` et `migrations`\n\n"
        "### Cycle de vie et provenance de l'instance servie — pans `front`, `qualif`, "
        "`accessibilite`, `visuel` (TF-0340 / TF-0341)\n\n"
        "### Autres pans\n\n"
        "| Pan | Conventions appliquées | Seuil |\n"
        "|---|---|---|\n"
        "| `front` | ... | 90 % |\n"
        "| `interface` | ... | 100 % |\n"
        "| `batch` | ... | 90 % |\n"
        "| `fichiers` | ... | 100 % |\n"
        "| `back` | ... | 70 % global |\n"
        "| `qualif` | ... | 100 % |\n"
        "| `securite` | ... | — |\n"
        "| `prompts` | ... | 100 % |\n"
        "| `accessibilite`, `visuel` | ... | — |\n"
        "| `i18n` | ... | 100 % |\n"
        "\n"
    )
    documentes = _pans_documentes_quelque_part(readme_perime)
    manquants = sorted(set(PANS_ATTENDUS) - documentes)
    # Fixture relue le 29/10/2026 (TF-1998, TF-2008) : `workers` et `supabase`, nés ce jour-là,
    # manquent aussi au README du 24/09, en plus des trois pans que TF-1407 a documentés.
    assert manquants == ["clavier", "contraste", "plancher", "supabase", "workers"], (
        "la fixture historique du README périmé du 24/09 ne manque plus exactement ces trois "
        "pans — si PANS_ATTENDUS a changé, relire cette fixture plutôt que la supprimer"
    )
