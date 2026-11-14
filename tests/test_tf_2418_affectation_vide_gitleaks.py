"""TF-2418 — gitleaks accuse les lignes VIDES du gabarit `.env.forge-tests.exemple` de la forge.

Fait (Produit-84, rapport du 10/11/2026) : 2 des 7 bloquants du pan `securite` étaient des
`generic-api-key` aux lignes `FORGE_TESTS_PASSWORD=` et `FORGE_TESTS_QUALIF_PASSWORD=` — des clés
SANS valeur, dans le gabarit que la forge dépose elle-même chez le produit (TF-0539). Cause : la
règle de gitleaks laisse `\\s` après le `=`, donc une affectation vide « emprunte » la ligne
suivante comme valeur (ici le nom de la clé d'après, 28 caractères). Deux gestes, parce que le
gabarit n'est pas le seul fichier à porter des clés vides (`.env.example` de tout produit) :

  1. le gabarit déposé par la forge sort du scan, quand il est INTACT (aucune valeur renseignée) ;
     renseigné, il redevient un fichier du produit et reste scanné ;
  2. un `generic-api-key` dont la ligne est une affectation vide, suivie d'une autre affectation
     vide ou d'un commentaire, est écarté et DIT au rapport ; la ligne suivante qui porte une
     valeur reste un constat, parce que c'est elle que gitleaks a prise pour la valeur.

`_lancer` est doublé par un mini-gitleaks qui rejoue la règle générique sur les fichiers de la
copie : la paire de fixtures ne dépend pas de gitleaks installé.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from forge_tests import gabarit_env
from forge_tests.adaptateurs import securite

# La règle `generic-api-key` de gitleaks, réduite à ce qui compte ici : un mot-clé, `=`, des
# séparateurs qui comprennent `\s` (donc le saut de ligne), puis une « valeur » de 10 caractères.
_GENERIQUE = re.compile(
    r"(?i)[\w.-]{0,50}?(?:key|passw(?:or)?d|secret|token)[ \t\w.-]{0,20}[\s'\"]{0,3}=[`'\"\s=]{0,5}"
    r"([\w.=-]{10,150})(?:[`'\"\s;]|$)"
)


def _mini_gitleaks(script: Path, cible: Path) -> dict:
    """Ce que `oracle-secrets` publie d'un gitleaks : `fichier:ligne · 4 premiers caractères`."""
    if Path(str(script)).name != "oracle-secrets.mjs":
        return {"verdict": "PASS", "findings": [], "non_juge": []}
    findings = []
    for fichier in sorted(Path(cible).rglob("*")):
        if not fichier.is_file():
            continue
        texte = fichier.read_text(encoding="utf-8")
        for trouve in _GENERIQUE.finditer(texte):
            ligne = texte.count("\n", 0, trouve.start()) + 1
            findings.append(
                {
                    "sev": "bloquant",
                    "msg": "gitleaks generic-api-key : secret probable",
                    "where": f"{fichier}:{ligne} · {trouve.group(1)[:4]}…",
                }
            )
    return {
        "verdict": "FAIL" if findings else "PASS",
        "findings": findings,
        "non_juge": [],
    }


@pytest.fixture(autouse=True)
def _oracles_doubles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Un dossier d'oracles qui contient les trois scripts (vides) : seul `_lancer` répond."""
    scripts = tmp_path / "oracles"
    scripts.mkdir()
    for nom in securite.ORACLES:
        (scripts / f"oracle-{nom}.mjs").write_text("// double\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_ORACLES", str(scripts))
    monkeypatch.setattr(securite, "_lancer", _mini_gitleaks)


def _projet(tmp_path: Path) -> Path:
    projet = tmp_path / "produit"
    projet.mkdir()
    # Un projet plat : la racine d'exécution est lue sur son manifeste Python.
    (projet / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    (projet / "main.py").write_text("x = 1\n", encoding="utf-8")
    return projet


def _secrets(sortie) -> list[str]:
    return [f.localisation for f in sortie.findings if "generic-api-key" in f.message]


# --- 1. Le gabarit déposé par la forge ---------------------------------------------------------
def test_le_double_reproduit_le_faux_positif_d_origine(tmp_path: Path) -> None:
    """Fixture rouge de la fixture : sur le gabarit tel que la forge le dépose, la règle
    générique lève bien les deux constats du rapport. Sans cela, les tests verts qui suivent ne
    prouveraient rien."""
    texte = gabarit_env.rendre(["FORGE_TESTS_PASSWORD", "FORGE_TESTS_QUALIF_PASSWORD"])
    ou = [m.group(1) for m in _GENERIQUE.finditer(texte)]

    assert ou, "le double doit accuser les lignes vides du gabarit, comme gitleaks"


def test_le_gabarit_intact_sort_du_scan_et_la_sortie_le_dit(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    (projet / gabarit_env.FICHIER).write_text(
        gabarit_env.rendre(["FORGE_TESTS_PASSWORD", "FORGE_TESTS_QUALIF_PASSWORD"]),
        encoding="utf-8",
    )

    sortie = securite.analyser(projet)

    assert _secrets(sortie) == []
    assert sortie.verdict == "PASS"
    # Une exclusion se DIT : sans la ligne, « rien à signaler » ne se distingue pas de « pas lu ».
    dit = [n for n in sortie.non_juge if gabarit_env.FICHIER in n and "ECART" in n]
    assert dit, sortie.non_juge


def test_le_gabarit_renseigne_reste_scanne(tmp_path: Path) -> None:
    """Sens inverse : un projet qui a rempli le gabarit sur place y a mis un mot de passe réel.
    Le fichier n'est plus le gabarit de la forge, il est au produit, et il reste jugé."""
    projet = _projet(tmp_path)
    (projet / gabarit_env.FICHIER).write_text(
        gabarit_env.rendre(["FORGE_TESTS_PASSWORD"]).replace(
            "FORGE_TESTS_PASSWORD=", "FORGE_TESTS_PASSWORD=Sup3rS3cretDeVrai"
        ),
        encoding="utf-8",
    )

    sortie = securite.analyser(projet)

    assert _secrets(sortie), "un gabarit renseigné doit rester scanné"
    assert sortie.verdict == "FAIL"


def test_le_gabarit_n_est_ecarte_que_sous_son_nom(tmp_path: Path) -> None:
    """Un autre fichier d'affectations vides n'est pas le gabarit de la forge : le premier geste
    ne l'exclut pas (le second le traite, par sa règle propre)."""
    projet = _projet(tmp_path)
    (projet / "exemple.cfg").write_text("API_KEY=\nDB_PASSWORD=\n", encoding="utf-8")

    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    copie = securite._sources_du_produit(projet, scan_dir, [], [], [], [])

    assert (copie / "exemple.cfg").is_file()


# --- 2. L'affectation vide, dans n'importe quel fichier ----------------------------------------
def test_une_affectation_vide_suivie_d_une_autre_est_ecartee_et_dite(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    (projet / ".env.example").write_text(
        "API_TOKEN=\nSERVICE_PASSWORD=\nDEBUG=true\n", encoding="utf-8"
    )

    sortie = securite.analyser(projet)

    assert _secrets(sortie) == [], [f.message for f in sortie.findings]
    assert any("affectation" in n and "vide" in n for n in sortie.non_juge), sortie.non_juge


def test_une_valeur_reelle_sur_la_ligne_suivante_reste_un_constat(tmp_path: Path) -> None:
    """Sens rouge du bornage : la règle emprunte la ligne d'après comme valeur. Si cette ligne
    porte elle-même une valeur, c'est elle que gitleaks a vue — l'écarter masquerait un secret."""
    projet = _projet(tmp_path)
    (projet / ".env.local").write_text(
        "API_TOKEN=\nAUTRE_SECRET=hunter2hunter2\n", encoding="utf-8"
    )

    sortie = securite.analyser(projet)

    assert _secrets(sortie), "la valeur réelle de la ligne suivante doit rester signalée"
    assert sortie.verdict == "FAIL"


def test_une_affectation_renseignee_reste_un_constat(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    (projet / "config.py").write_text('API_KEY = "abcd1234efgh5678ijkl"\n', encoding="utf-8")
    (projet / "app.env").write_text("DB_PASSWORD=abcd1234efgh5678ijkl\n", encoding="utf-8")

    sortie = securite.analyser(projet)

    assert len(_secrets(sortie)) >= 1
    assert sortie.verdict == "FAIL"
