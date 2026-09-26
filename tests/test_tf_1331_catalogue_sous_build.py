"""TF-1331 — un catalogue de traductions placé sous `build/` était invisible, et le pan ne le
déclarait même pas « non lu ».

Le fait, mesuré le 23/09/2026 : un catalogue `build/i18n/{fr,en}.mjs` rend `({}, [])` au pan
i18n (`forge_tests/adaptateurs/i18n.py`) — la forme du produit du lot 20260823a. Sur lui, les
contrôles (d) à (k) du catalogue, dont (g) qui porte l'étape B5 de la chaîne d'audit des
traductions, se taisaient SANS que le rapport le dise.

La cause : `catalogue_i18n._EXCLUS` coupait la marche de `_dossiers_candidats` AVANT même
d'atteindre `build/i18n` — `build`, `dist` et `out` y vivaient via `exclusions.OUTILLAGE`, le
socle commun à tous les pans. Le dossier `i18n` sous `build/` n'était donc jamais visité : ni lu,
ni nommé comme non lu. Un silence, pas un SKIP — la pire des deux défaillances (loi 3 du pilot).

Le correctif retire `build`, `dist`, `out` du socle POUR CETTE recherche seulement : ces trois
noms sont déjà ceux que le pan i18n reconnaît comme racines de BUILD SERVI (`DOSSIERS_BUILD`).
Ce que ce fichier tient, dans les deux sens de l'item (« que le pan LISE ces catalogues, OU
déclare NON LU ») :

  · un catalogue LISIBLE (JSON par locale) sous `build/`, `dist/` ou `out/` est désormais LU
    normalement, comme s'il vivait à la racine ;
  · un catalogue ILLISIBLE (toute autre extension, ici `.mjs`) sous ces mêmes racines est NOMMÉ
    « non lu » avec son CHEMIN, jamais confondu avec une absence de catalogue ;
  · la déclaration survit jusqu'au RAPPORT DU PAN — y compris quand le verdict final reste NA,
    faute d'un autre signe d'internationalisation ;
  · un dossier de build qui ne porte AUCUN nom conventionnel de catalogue (chunks compilés,
    assets…) ne produit toujours RIEN — le correctif n'élargit pas le bruit, il répare un trou.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests import catalogue_i18n as catalogue
from forge_tests.adaptateurs import i18n


def _fichiers(racine: Path, dossier: str, noms_et_contenus: dict[str, str]) -> Path:
    """Dépose des fichiers QUELCONQUES (pas nécessairement du JSON) sous `dossier`."""
    cible = racine / dossier
    cible.mkdir(parents=True, exist_ok=True)
    for nom, contenu in noms_et_contenus.items():
        (cible / nom).write_text(contenu, encoding="utf-8")
    return cible


def _catalogue_json(racine: Path, dossier: str, contenus: dict[str, dict]) -> Path:
    cible = racine / dossier
    cible.mkdir(parents=True, exist_ok=True)
    for locale, objet in contenus.items():
        (cible / f"{locale}.json").write_text(
            json.dumps(objet, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return cible


# --- Le cas MESURÉ : `build/i18n/{fr,en}.mjs` ----------------------------------------------------
def test_un_catalogue_MJS_sous_build_est_NOMME_NON_LU_avec_son_CHEMIN(tmp_path: Path) -> None:
    """La forme réelle du lot 20260823a. Avant le correctif : `({}, [])`, silence total — ni
    `lus` ni `non_lus` ne portaient la moindre trace de ces deux fichiers."""
    _fichiers(
        tmp_path, "build/i18n", {"fr.mjs": "export default {}", "en.mjs": "export default {}"}
    )

    lus, non_lus = catalogue.catalogues(tmp_path)

    assert lus == {}, "un .mjs n est pas du JSON par locale : rien de comparable comme catalogue"
    assert len(non_lus) == 1
    assert "build/i18n" in non_lus[0], f"le CHEMIN doit être nommé : {non_lus!r}"
    assert "NON LU" in non_lus[0]
    assert "fr.mjs" in non_lus[0] and "en.mjs" in non_lus[0]


def test_le_pan_i18n_DECLARE_le_catalogue_non_lu_MEME_QUAND_le_verdict_final_est_NA(
    tmp_path: Path,
) -> None:
    """Le cœur de l'item : « le pan ne le déclare même pas non lu ». Ce produit minimal n a
    NUL AUTRE signe d internationalisation (pas de package.json i18n, pas de build avec
    index.html) — le verdict tombe donc NA (sans objet), et c'est PRÉCISÉMENT ce cas qui doit
    encore porter la déclaration : un verdict NA n est pas un droit au silence.
    """
    _fichiers(
        tmp_path, "build/i18n", {"fr.mjs": "export default {}", "en.mjs": "export default {}"}
    )

    sortie = i18n.analyser(tmp_path)

    declare = " ".join(sortie.non_juge)
    assert "build/i18n" in declare, (
        f"le rapport du pan doit nommer le chemin non lu quel que soit le verdict "
        f"({sortie.verdict}) : {sortie.non_juge!r}"
    )
    assert "NON LU" in declare


# --- L'AUTRE moitié de l'« OU » : un catalogue LISIBLE sous build/ est LU -----------------------
def test_un_catalogue_JSON_sous_build_est_LU_normalement(tmp_path: Path) -> None:
    """Avant le correctif, un catalogue JSON parfaitement lisible sous `build/` était TOUT AUSSI
    invisible qu un `.mjs` — la coupe se faisait au niveau du DOSSIER, avant même de regarder les
    fichiers qu il contient."""
    _catalogue_json(tmp_path, "build/locales", {
        "fr": {"accueil": "Bonjour", "nav": {"aide": "Aide"}},
        "en": {"accueil": "Hello"},
    })

    lus, non_lus = catalogue.catalogues(tmp_path)

    assert "build/locales" in lus, f"catalogue JSON sous build/ non lu : {non_lus!r}"
    verdict = catalogue.juger(lus["build/locales"])
    assert verdict["union"] == 2
    assert verdict["manquantes"] == {"en": ["nav.aide"]}


def test_un_catalogue_JSON_sous_dist_et_sous_out_est_LU_aussi(tmp_path: Path) -> None:
    """Le correctif porte sur les TROIS noms que le pan reconnaît comme racines de build servi
    (`DOSSIERS_BUILD`) — pas seulement celui mesuré. Une correction qui n en couvrirait qu un
    laisserait le même trou, motif identique, sous un autre nom."""
    _catalogue_json(tmp_path, "dist/i18n", {"fr": {"a": "A"}, "en": {"a": "A", "b": "B"}})
    _catalogue_json(tmp_path, "out/i18n", {"fr": {"a": "A"}, "en": {"a": "A", "b": "B"}})

    lus, _ = catalogue.catalogues(tmp_path)

    assert "dist/i18n" in lus
    assert "out/i18n" in lus


# --- Non-régression : le bruit ne s élargit pas -------------------------------------------------
def test_un_dossier_de_build_SANS_nom_conventionnel_ne_produit_toujours_RIEN(
    tmp_path: Path,
) -> None:
    """`build/` reste par ailleurs plein de chunks compilés, jamais des catalogues : le
    correctif ne cherche que les SIX noms conventionnels (`DOSSIERS`), il ne se met pas à
    parcourir tout `build/` en quête de JSON à deux lettres."""
    _fichiers(tmp_path, "build/static/chunks", {
        "fr.json": '{"pas": "un catalogue de locale"}',
        "main.abc123.js": "console.log('build')",
    })

    lus, non_lus = catalogue.catalogues(tmp_path)

    assert lus == {}, "aucun dossier au nom conventionnel : rien à comparer"
    assert non_lus == [], "un chunk compilé n est pas un fichier de catalogue NON LU"


def test_node_modules_reste_coupe_MEME_a_l_interieur_d_un_dossier_de_build(
    tmp_path: Path,
) -> None:
    """Le retrait de `build`/`dist`/`out` du socle ne retire PAS `node_modules` : une dépendance
    empaquetée sous `build/` (cas réel d un bundle qui copie ses deps) reste hors périmètre."""
    _catalogue_json(
        tmp_path, "build/node_modules/une-dep/locales", {"fr": {"a": "A"}, "en": {"a": "A"}}
    )

    lus, non_lus = catalogue.catalogues(tmp_path)

    assert lus == {} and non_lus == [], "node_modules reste coupé, même sous build/"
