r"""Une copie VENDORISÉE a-t-elle divergé de sa source ? (TF-0580, lot Produit-02 20260824)

Le fait fondateur, mesuré : un `Dockerfile` posait `ENV FORGE_ROOT=/app/vendor`. En production,
`vendor/digit-ai-factory/catalogues/catalogue.jsonl` ÉTAIT donc la source qui alimentait la base
et, de là, les chiffres affichés au visiteur. Aucun mécanisme ne la rafraîchissait, aucun
contrôle ne la comparait à l'amont. Résultat : **le site annonçait v1.6.2 et 80 services quand
le catalogue amont en portait v1.8.0 et 83** — deux versions de retard, sur un site dont
l'argument entier est la preuve datée.

Le retard était masqué par un second effet, et il mérite d'être noté parce qu'il inverse
l'intuition : l'amont avait renommé une forge, ce qui faisait échouer la régénération par un
refus NET (« forges hors regroupement connu »). **Le refus était bon** — il ne devinait pas — mais
personne ne le lisait. Un refus juste que personne ne lit produit exactement le même silence
qu'une absence de contrôle.

Ce que ce module fait : pour chaque copie vendorisée dont la SOURCE est présente sur le poste, il
compare les fichiers communs et nomme ceux qui divergent. Ni plus, ni moins.

Ce qu'il NE fait PAS, et c'est délibéré :
  · il ne rafraîchit rien — mettre à jour une copie est un geste de projet, pas d'auditeur ;
  · il ne juge PAS une copie dont la source est absente du poste : « je ne peux pas comparer » et
    « c'est à jour » ne doivent jamais s'écrire pareil, sinon on retombe dans le défaut d'origine ;
  · il ne compare pas les dépendances tierces vendorisées classiques (`node_modules` recopié,
    paquets épinglés) : leur amont n'est pas sur le poste, et les accuser ferait crier le pan sur
    tout projet qui épingle ses dépendances — ce que TF-0280 avait justement écarté.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Les dossiers qui abritent une copie vendorisée, par convention.
RACINES_VENDOR: tuple[str, ...] = ("vendor", "vendors", "third_party", "externes")

#: Ce qu'on ne compare jamais : bruit d'outillage, journaux, artefacts de build.
IGNORES: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", "site-packages", ".oracles", "_oracles",
})

#: Taille au-delà de laquelle on ne compare pas octet à octet — un binaire lourd coûterait plus
#: que le constat ne rapporte, et sa divergence se voit à sa taille.
TAILLE_MAX = 2 * 1024 * 1024


def _sources_disponibles(racine_forges: Path) -> dict[str, Path]:
    """Les dépôts présents sur le poste, indexés par nom — l'amont potentiel d'une copie."""
    try:
        return {d.name: d for d in racine_forges.iterdir() if d.is_dir() and (d / ".git").exists()}
    except OSError:
        return {}


def _fichiers(base: Path) -> dict[str, Path]:
    """Les fichiers comparables sous `base`, indexés par chemin relatif POSIX."""
    trouves: dict[str, Path] = {}
    for chemin in base.rglob("*"):
        if not chemin.is_file():
            continue
        if any(p in IGNORES for p in chemin.relative_to(base).parts):
            continue
        try:
            if chemin.stat().st_size > TAILLE_MAX:
                continue
        except OSError:
            continue
        trouves[chemin.relative_to(base).as_posix()] = chemin
    return trouves


def _identiques(a: Path, b: Path) -> bool:
    """Comparaison NORMALISÉE en fins de ligne : un CRLF ne fait pas diverger une copie (TF-0072)."""
    try:
        ca, cb = a.read_bytes(), b.read_bytes()
    except OSError:
        return False
    if ca == cb:
        return True
    return ca.replace(b"\r\n", b"\n") == cb.replace(b"\r\n", b"\n")


def constats(cible: Path | str, racine_forges: Path | str | None = None) -> list[dict]:
    """Les copies vendorisées qui ont divergé de leur source, une entrée par copie.

    Chaque entrée dit ce qui a été comparé et ce qui manque — un constat qui ne dit pas ce qu'il
    a regardé n'est pas actionnable.
    """
    cible = Path(cible)
    racine = Path(racine_forges) if racine_forges else Path(os.environ.get("FORGE_ROOT", cible.parent))
    sources = _sources_disponibles(racine)
    resultats: list[dict] = []

    for nom_racine in RACINES_VENDOR:
        dossier = cible / nom_racine
        if not dossier.is_dir():
            continue
        for copie in sorted(p for p in dossier.iterdir() if p.is_dir()):
            source = sources.get(copie.name)
            if source is None:
                # « Je ne peux pas comparer » et « c'est à jour » ne s'écrivent JAMAIS pareil.
                resultats.append({
                    "copie": copie.relative_to(cible).as_posix(),
                    "statut": "non_comparable",
                    "motif": f"aucune source « {copie.name} » sur le poste (cherchée sous {racine}) — "
                             "non comparé, ce qui n'est pas la même chose qu'à jour",
                    "divergents": [], "absents": [],
                })
                continue

            fic_copie, fic_source = _fichiers(copie), _fichiers(source)
            communs = sorted(set(fic_copie) & set(fic_source))
            divergents = [r for r in communs if not _identiques(fic_copie[r], fic_source[r])]
            absents = sorted(set(fic_source) - set(fic_copie))
            resultats.append({
                "copie": copie.relative_to(cible).as_posix(),
                "source": str(source),
                "statut": "diverge" if (divergents or absents) else "a_jour",
                "compares": len(communs),
                "divergents": divergents[:20],
                "absents": absents[:20],
                "motif": (
                    f"{len(divergents)} fichier(s) divergent et {len(absents)} manquent sur "
                    f"{len(communs)} comparé(s) — une copie vendorisée qui a divergé sert des "
                    "valeurs périmées SANS que rien ne le dise (TF-0580)"
                ) if (divergents or absents) else f"{len(communs)} fichier(s) comparé(s), aucun écart",
            })
    return resultats
