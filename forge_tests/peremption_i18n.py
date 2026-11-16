"""Péremption d'une traduction : sa source a changé depuis qu'elle a été faite — TF-2670.

**Le fait (site public, lot factory-digit-ai-fr 20261116e).** Un site rendu côté serveur, aux
contenus en Markdown, a deux sortes de pages en défaut que le pan i18n ne voit pas : celles qui
manquent dans une langue (parité de routes, jugée sur un build) et celles qui existent mais disent
l'ancien texte, parce que la source a changé après la traduction. Les secondes ne laissent aucune
trace dans une arborescence : la page anglaise est là, bien formée, et fausse.

**Le contrôle.** Le projet déclare, pour chaque traduction, sa source et l'EMPREINTE qu'avait cette
source quand la traduction a été faite, dans un fichier JSON versionné désigné par
`FORGE_TESTS_I18N_PEREMPTION` :

    {"traductions": [
      {"traduction": "contenu/en/tarifs.md", "source": "contenu/fr/tarifs.md",
       "empreinte": "<sha256 de la source au moment de la traduction>"}
    ]}

Les chemins sont relatifs à la racine auditée. Le pan recalcule l'empreinte de chaque source :
différente, la traduction est PÉRIMÉE — un constat, qui nomme la source, l'empreinte attendue et
l'empreinte lue. On re-scelle en retraduisant, puis en recopiant l'empreinte que donne
`python -m forge_tests.peremption_i18n <source>`.

L'empreinte est celle du texte avec ses fins de ligne normalisées (CRLF lu comme LF) : un dépôt
extrait sous Windows ne périme pas toutes ses traductions d'un coup. Elle ne dit rien du SENS : une
virgule corrigée dans la source périme sa traduction, et le projet la re-scelle d'un geste, après
avoir jugé qu'elle dit toujours la même chose — c'est l'écart que le contrôle rend visible, pas un
jugement sur la traduction.

**Rien de déclaré, rien de jugé** (patron de `FORGE_TESTS_I18N_ROUTES`) : le pan ne devine pas
quelle page traduit laquelle. Un chemin qui sort de la racine auditée n'est pas lu.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

CHAMP = "FORGE_TESTS_I18N_PEREMPTION"


def empreinte(chemin: Path | str) -> str:
    """SHA-256 du contenu, fins de ligne normalisées."""
    contenu = Path(chemin).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(contenu).hexdigest()


def declarees() -> tuple[list[dict] | None, str | None]:
    """Les traductions déclarées, ou `(None, motif)` quand la déclaration manque ou est illisible.

    `(None, None)` : rien n'est déclaré — ce n'est pas une faute, c'est l'état initial.
    """
    chemin = (os.environ.get(CHAMP) or "").strip()
    if not chemin:
        return None, None
    try:
        brut = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except OSError:
        return None, f"{CHAMP} désigne un fichier illisible ou absent : {chemin}"
    except json.JSONDecodeError as erreur:
        return None, f"{CHAMP} : fichier illisible, JSON invalide ({erreur.msg}) : {chemin}"
    entrees = brut.get("traductions") if isinstance(brut, dict) else None
    if not isinstance(entrees, list) or not entrees:
        return None, (
            f'{CHAMP} : fichier illisible, {{"traductions": [{{"traduction", "source", '
            f'"empreinte"}}]}} attendu : {chemin}'
        )
    retenues = [e for e in entrees if isinstance(e, dict)]
    manquantes = len(entrees) - len(retenues)
    if manquantes or any(
        not all(isinstance(e.get(cle), str) and e.get(cle) for cle in
                ("traduction", "source", "empreinte"))
        for e in retenues
    ):
        return None, (
            f"{CHAMP} : fichier illisible, chaque entrée porte `traduction`, `source` et "
            f"`empreinte` en texte : {chemin}"
        )
    return retenues, None


def _dans_le_projet(cible: Path, relatif: str) -> Path | None:
    chemin = (cible / relatif).resolve()
    try:
        chemin.relative_to(cible.resolve())
    except ValueError:
        return None
    return chemin


def constats(cible: Path) -> tuple[list[tuple[str, str, str]], list[str], bool]:
    """`([(id, localisation, message)], motifs de non-jugé, déclaration présente)`."""
    entrees, motif = declarees()
    if entrees is None:
        if motif:
            return [], [f"i18n : péremption NON jugée — {motif}"], False
        return [], [
            f"i18n : AUCUNE péremption déclarée ({CHAMP}) — une traduction dont la source a changé "
            "n'est signalée nulle part. Déclarer, pour chaque traduction, sa source et l'empreinte "
            "que celle-ci avait quand elle a été faite (`python -m forge_tests.peremption_i18n "
            "<source>` la donne) : rien de déclaré, rien de jugé"
        ], False

    sortie: list[tuple[str, str, str]] = []
    for entree in entrees:
        traduction, source, attendue = entree["traduction"], entree["source"], entree["empreinte"]
        identifiant = f"i18n:peremption:{traduction}"
        fichiers: dict[str, Path | None] = {
            nom: _dans_le_projet(cible, chemin)
            for nom, chemin in (("traduction", traduction), ("source", source))
        }
        hors = [nom for nom, chemin in fichiers.items() if chemin is None]
        if hors:
            sortie.append((identifiant, traduction, (
                f"péremption de « {traduction} » NON jugée : le chemin déclaré pour sa "
                f"{' et sa '.join(hors)} est hors du projet audité, il n'est pas lu"
            )))
            continue
        absents = [nom for nom, chemin in fichiers.items() if not chemin.is_file()]  # type: ignore[union-attr]
        if absents:
            sortie.append((identifiant, traduction, (
                f"péremption de « {traduction} » non jugeable : "
                + " et ".join(f"{nom} introuvable ({entree[nom]})" for nom in absents)
                + " — une déclaration cassée ne se lit pas « à jour »"
            )))
            continue
        lue = empreinte(fichiers["source"])  # type: ignore[arg-type]
        if lue != attendue:
            sortie.append((identifiant, traduction, (
                f"traduction « {traduction} » périmée : sa source « {source} » a changé depuis la "
                f"traduction (empreinte déclarée {attendue[:12]}…, lue {lue[:12]}…). La retraduire "
                "ou juger qu'elle dit toujours la même chose, puis re-sceller l'empreinte"
            )))
    motifs = [
        f"i18n : péremption jugée sur {len(entrees)} traduction(s) déclarée(s) ({CHAMP}) — par "
        "empreinte de la source : elle dit que la source a changé, jamais que la traduction est "
        "fausse"
    ]
    return sortie, motifs, True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage : python -m forge_tests.peremption_i18n <fichier source>\n"
              "  Imprime l'empreinte à recopier dans `empreinte` (sha256, fins de ligne "
              "normalisées).")
        sys.exit(0)
    cible_ = Path(sys.argv[1])
    if not cible_.is_file():
        print(f"fichier introuvable : {cible_}", file=sys.stderr)
        sys.exit(2)
    print(empreinte(cible_))
