"""TF-2862 (1/2) — `incomplete-sanitization` n'accuse pas un `replace` dont le résultat part à une
conversion numérique.

Fait (Produit-12, RS-56, 23/11/2026) : deux constats « bloquants » semgrep `incomplete-sanitization`
sur `table-filters.js` l. 126-127. La ligne visée est
`parseFloat(String(va).replace(',', '.').replace('%', ''))` : le résultat part à `parseFloat` pour
trier une colonne, ce n'est pas un assainissement. Un faux bloquant entraîne à ignorer la classe des
bloquants.

Le `_lancer` est doublé : la recette ne dépend ni de semgrep installé ni du réseau. Chaque cas vert
(le `replace` converti n'est plus bloquant) a son cas rouge (un vrai assainissement incomplet reste
bloquant) : la règle ne se lève pas pour tout le monde.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite

LIGNE_MESUREE = "          var na = parseFloat(String(va).replace(',', '.').replace('%', ''));\n"


def _projet(tmp_path: Path, source: str, nom: str = "table-filters.js") -> Path:
    projet = tmp_path / "produit"
    (projet / "app").mkdir(parents=True)
    (projet / "app" / nom).write_text(source, encoding="utf-8")
    (projet / "main.py").write_text("x = 1\n", encoding="utf-8")
    (projet / "pyproject.toml").write_text(
        '[project]\nname = "p"\ndependencies = ["fastapi>=0.110"]\n', encoding="utf-8"
    )
    return projet


def _sast_rend(
    monkeypatch: pytest.MonkeyPatch, lignes: list[int], regle: str = "incomplete-sanitization",
    relatif: bool = False, nom: str = "table-filters.js",
) -> None:
    """oracle-sast remonte un bloquant par ligne donnée ; les autres oracles sont verts."""

    def _double(script: Path, cible: Path) -> dict:
        if Path(str(script)).name != "oracle-sast.mjs":
            return {"verdict": "PASS", "findings": [], "non_juge": []}
        fichier = Path(cible) / "app" / nom
        lieu = (
            os.path.relpath(fichier, start=Path(cible).parent.parent) if relatif else str(fichier)
        )
        return {
            "verdict": "FAIL",
            "findings": [
                {"sev": "bloquant", "msg": f"semgrep {regle}", "where": f"{lieu}:{ligne}"}
                for ligne in lignes
            ],
            "non_juge": [],
        }

    monkeypatch.setattr(securite, "_lancer", _double)


def _jouer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, lignes: list[int],
           **options: object) -> securite.SortieAdaptateur:
    _sast_rend(monkeypatch, lignes, **options)  # type: ignore[arg-type]
    return securite.analyser(_projet(tmp_path, source))


def _severites(sortie: securite.SortieAdaptateur) -> list[str]:
    return [f.severite for f in sortie.findings if "incomplete-sanitization" in f.message]


# --- Sens vert : un `replace` converti n'accuse personne --------------------------------------


def test_la_ligne_mesuree_chez_produit_12_n_est_plus_bloquante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        "function trier(a, b, va, vb) {\n"
        f"{LIGNE_MESUREE}"
        "          var nb = parseFloat(String(vb).replace(',', '.').replace('%', ''));\n"
        "}\n"
    )

    sortie = _jouer(tmp_path, monkeypatch, source, [2, 3])

    assert _severites(sortie) == ["signale", "signale"], [f.message for f in sortie.findings]
    assert sortie.verdict == "PASS", "plus aucun bloquant : le pan ne rend plus FAIL"
    message = next(f.message for f in sortie.findings if "incomplete-sanitization" in f.message)
    assert "non bloquant" in message and "conversion numérique" in message
    assert "TF-2862" in message


def test_le_reclassement_se_dit_au_non_juge_avec_les_lieux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sortie = _jouer(tmp_path, monkeypatch, "x\n" + LIGNE_MESUREE, [2])

    dit = [n for n in sortie.non_juge if "TF-2862" in n]
    assert len(dit) == 1, sortie.non_juge
    assert "incomplete-sanitization" in dit[0] and "NON BLOQUANT" in dit[0]
    assert "table-filters.js:2" in dit[0], "le lieu reclassé est nommé"


@pytest.mark.parametrize(
    "source",
    [
        "var n = Number(valeur.replace(',', '.'));\n",
        "var n = parseInt(texte.replace(' ', ''), 10);\n",
        "var n = parseFloat(texte.replace('(', '').replace(')', ''));\n",
        "var n = parseFloat(\n  String(va).replace(',', '.')\n);\n",
        "var t = texte.replace(',', '.');\nvar n = Number(t);\n",
        "const t = texte.replace(',', '.')\n// converti plus bas\nconst n = parseFloat(t)\n",
    ],
    ids=["Number", "parseInt", "parentheses-dans-le-replace", "sur-deux-lignes",
         "variable-puis-Number", "variable-puis-parseFloat"],
)
def test_chaque_forme_de_replace_converti_est_signalee_sans_bloquer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    lignes = [i + 1 for i, ligne in enumerate(source.splitlines()) if ".replace(" in ligne]
    assert lignes, "la source de test porte un replace"

    sortie = _jouer(tmp_path, monkeypatch, source, lignes)

    assert set(_severites(sortie)) == {"signale"}, [f.message for f in sortie.findings]


def test_le_lieu_relatif_de_oracle_sast_se_resout_aussi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`oracle-sast` publie un chemin RELATIF où la copie filtrée n'apparaît que par son suffixe."""
    sortie = _jouer(tmp_path, monkeypatch, "x\n" + LIGNE_MESUREE, [2], relatif=True)

    assert _severites(sortie) == ["signale"]


def test_l_identifiant_du_constat_ne_change_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une contestation déjà écrite contre l'identifiant du constat reste appariable."""
    sortie = _jouer(tmp_path, monkeypatch, "x\n" + LIGNE_MESUREE, [2])

    identifiants = [f.id for f in sortie.findings if "incomplete-sanitization" in f.message]
    assert len(identifiants) == 1
    assert identifiants[0].startswith("securite:sast:") and identifiants[0].endswith(":2")


# --- Sens rouge : un vrai assainissement incomplet reste bloquant -----------------------------


@pytest.mark.parametrize(
    "source",
    [
        "const propre = nom.replace('..', '');\nfs.readFile(propre);\n",
        "var total = parseFloat(a) + nom.replace('..', '');\n",
        "var t = nom.replace('..', '');\nvar n = Number(autre);\n",
        "html = html.replace('<script>', '');\n",
        "var t = nom.replace('..', '');\n\n\n\nvar n = Number(t);\n",
    ],
    ids=["chemin-assaini", "conversion-a-cote", "autre-variable-convertie", "html-assaini",
         "conversion-trop-loin"],
)
def test_un_vrai_assainissement_incomplet_reste_bloquant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    sortie = _jouer(tmp_path, monkeypatch, source, [1])

    assert _severites(sortie) == ["bloquant"], [f.message for f in sortie.findings]
    assert sortie.verdict == "FAIL"
    assert not [n for n in sortie.non_juge if "TF-2862" in n], "rien n'a été reclassé, rien à dire"


def test_une_autre_regle_sur_la_meme_ligne_reste_bloquante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sortie = _jouer(tmp_path, monkeypatch, "x\n" + LIGNE_MESUREE, [2], regle="detect-eval")

    assert [f.severite for f in sortie.findings if "detect-eval" in f.message] == ["bloquant"]


def test_une_ligne_illisible_reste_bloquante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conservateur : sans lire la ligne, on ne masque rien."""
    sortie = _jouer(tmp_path, monkeypatch, "x\n", [999])

    assert _severites(sortie) == ["bloquant"]


def test_le_fichier_absent_reste_bloquant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sast_rend(monkeypatch, [1], nom="fantome.js")

    sortie = securite.analyser(_projet(tmp_path, LIGNE_MESUREE))

    assert _severites(sortie) == ["bloquant"]
