"""TF-0291 — le pan securite s auto-accusait sur ses PROPRES bancs d essai.

Fait mesure le 15/08/2026, pan securite joue sur forge-tests elle-meme : 5 constats, TOUS sur de
la matiere de test plantee expres.

  - 2 SAST — `fixtures/banc-rouge/backend/app/recherche.py:13` (l execution dynamique QUE LE BANC
    ROUGE EXISTE POUR FAIRE DETECTER) et `tests/test_tf_0279_id_sast_stable.py:47` (la chaine de
    montage qui prouve la stabilite de l identifiant SAST d une passe a l autre) ;
  - 3 secrets — des `AKIA…` de fixture dans `test_correctifs_20260811.py`,
    `test_tf_0216_racine_plate.py` et `test_tf_0280_vendored_exclu.py`.

C est le cousin exact du Larsen du pan `prompts` (TF-0257) : l auditeur mesure ses propres
artefacts. Le remede est le meme — reconnaitre l auditeur sur SIGNATURE, n ecarter que ce qu il
DECLARE comme matiere de test, et publier l exclusion.

Double sens sur chaque regle, et la contrepartie non negociable en tete de liste : un VRAI secret
dans le code de la forge (`forge_tests\\`) reste detecte. Sans elle, on aurait achete du silence
et non de la lisibilite.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from forge_tests.adaptateurs import securite

# La forme exacte des trois secrets de fixture qui s auto-accusaient (cle d acces AWS).
_SECRET = "AKIAIOSFODNN7EXAMPLE"


@pytest.fixture(autouse=True)
def sans_declaration(monkeypatch):
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)


def _registre(racine: Path) -> Path:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "oracle-secrets.mjs").write_text("", encoding="utf-8")
    return racine


def _oracle_secrets(script: Path, scan: Path) -> dict:
    """Rejoue le contrat d `oracle-secrets` sur CE QU IL RECOIT — sans node, sans reseau.

    Le defaut ne vit pas dans l oracle mais dans ce qu on lui tend : ce faux oracle lit donc
    reellement l arborescence copiee, il ne recite pas une reponse ecrite d avance.
    """
    findings = [
        {"sev": "bloquant", "msg": "secret probable : cle d'acces AWS", "where": str(fichier)}
        for fichier in sorted(Path(scan).rglob("*"))
        if fichier.is_file() and _SECRET in fichier.read_text(encoding="utf-8", errors="ignore")
    ]
    return {"verdict": "FAIL" if findings else "PASS", "findings": findings, "non_juge": []}


def _analyser(cible: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))
    monkeypatch.setattr(securite, "_lancer", _oracle_secrets)
    return securite.analyser(cible)


def _forge(racine: Path, *, signature: bool = True, secret_dans_la_forge: bool = False) -> Path:
    """Une reproduction de forge-tests, avec ou sans sa signature.

    Les trois emplacements du constat reel y vivent : le banc rouge sous `fixtures\\`, une chaine
    de montage sous `tests\\`, et le code de la forge sous `forge_tests\\`.
    """
    (racine / "forge_tests" / "adaptateurs").mkdir(parents=True)
    (racine / "recette").mkdir(parents=True)
    if signature:
        (racine / "forge_tests" / "adaptateurs" / "__init__.py").write_text(
            "REGISTRE = {}\n", encoding="utf-8"
        )
        (racine / "recette" / "verifier_corpus.py").write_text("CORPUS = []\n", encoding="utf-8")
        (racine / "registre-dette.json").write_text('{"dette": []}\n', encoding="utf-8")

    ligne = f'CLE = "{_SECRET}"\n' if secret_dans_la_forge else "CLE = os.environ['CLE']\n"
    (racine / "forge_tests" / "adaptateurs" / "securite.py").write_text(ligne, encoding="utf-8")

    # Le banc rouge : un produit factice FIGE dont le defaut est l attendu du corpus.
    (racine / "fixtures" / "banc-rouge" / "backend" / "app").mkdir(parents=True)
    (racine / "fixtures" / "banc-rouge" / "backend" / "app" / "recherche.py").write_text(
        f'CLE_DE_BANC = "{_SECRET}"\n', encoding="utf-8"
    )
    # Une chaine de montage : elle PLANTE le secret dont elle prouve la detection.
    (racine / "tests").mkdir(parents=True)
    (racine / "tests" / "test_tf_0216_racine_plate.py").write_text(
        f'_SECRET = "{_SECRET}"\n', encoding="utf-8"
    )
    return racine


# --- La reconnaissance : sur signature, jamais sur le nom -------------------------------------
def test_la_forge_est_reconnue_a_sa_signature(tmp_path):
    assert securite.est_la_forge_elle_meme(_forge(tmp_path / "peu-importe-le-nom"))


def test_un_produit_qui_s_appellerait_forge_tests_sans_en_etre_un_n_est_PAS_reconnu(tmp_path):
    """TEMOIN de la reconnaissance : le nom ne prouve rien, les trois marqueurs si."""
    assert not securite.est_la_forge_elle_meme(
        _forge(tmp_path / "digit-ai-forge-tests", signature=False)
    )


def test_les_trois_marqueurs_sont_TOUS_exiges(tmp_path):
    """Un seul marqueur suffirait a excuser n importe quel projet portant un `tests\\`."""
    racine = _forge(tmp_path / "presque", signature=True)
    (racine / "registre-dette.json").unlink()
    assert not securite.est_la_forge_elle_meme(racine)


# --- L exclusion : ancree a la racine, et rien de plus ----------------------------------------
def test_les_bancs_et_les_montages_de_la_forge_n_atteignent_jamais_les_oracles(tmp_path):
    """La copie filtree est le seul levier qui ne reecrit pas l outil delegue (R3)."""
    application = _forge(tmp_path / "forge")

    with tempfile.TemporaryDirectory() as brouillon:
        scan = securite._sources_du_produit(application, Path(brouillon))
        copies = {chemin.name for chemin in scan.rglob("*") if chemin.is_file()}

    assert "recherche.py" not in copies, copies
    assert "test_tf_0216_racine_plate.py" not in copies, copies
    # Le code de la forge, lui, est bien tendu aux oracles.
    assert "securite.py" in copies, copies


def test_sur_un_AUTRE_projet_fixtures_et_tests_restent_scannes(tmp_path):
    """TEMOIN de l exclusion : elle ne vaut que pour la forge. Le `tests\\` d un produit
    client porte du code de ce produit, et un secret y est un secret."""
    application = _forge(tmp_path / "produit", signature=False)

    with tempfile.TemporaryDirectory() as brouillon:
        scan = securite._sources_du_produit(application, Path(brouillon))
        copies = {chemin.name for chemin in scan.rglob("*") if chemin.is_file()}

    assert "recherche.py" in copies, copies
    assert "test_tf_0216_racine_plate.py" in copies, copies


def test_l_exclusion_est_ANCREE_a_la_racine_de_l_application(tmp_path):
    """Un `tests\\` niche DANS le paquet de la forge n est pas la matiere de test declaree :
    l exclusion porte sur deux emplacements nommes, pas sur deux noms de dossier."""
    application = _forge(tmp_path / "forge")
    (application / "forge_tests" / "tests").mkdir(parents=True)
    (application / "forge_tests" / "tests" / "interne.py").write_text(
        f'CLE = "{_SECRET}"\n', encoding="utf-8"
    )

    with tempfile.TemporaryDirectory() as brouillon:
        scan = securite._sources_du_produit(application, Path(brouillon))
        copies = {chemin.name for chemin in scan.rglob("*") if chemin.is_file()}

    assert "interne.py" in copies, copies


# --- Le verdict : plus de Larsen, mais pas de silence -----------------------------------------
def test_les_cinq_constats_du_15_08_ne_sortent_plus(tmp_path, monkeypatch):
    """ROUGE avant correctif : 5 constats sur la forge elle-meme, tous sur de la matiere de
    test. Ici les deux emplacements fautifs portent un `AKIA…` et le verdict doit etre PASS."""
    sortie = _analyser(_forge(tmp_path / "forge"), tmp_path, monkeypatch)

    assert not sortie.findings, [f.localisation for f in sortie.findings]
    assert sortie.verdict == "PASS", sortie.verdict


def test_un_VRAI_secret_dans_le_code_de_la_forge_reste_detecte(tmp_path, monkeypatch):
    """La contrepartie non negociable : on a achete de la lisibilite, jamais du silence."""
    cible = _forge(tmp_path / "forge", secret_dans_la_forge=True)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert sortie.verdict == "FAIL", sortie.verdict
    assert len(sortie.findings) == 1, [f.localisation for f in sortie.findings]
    assert "securite.py" in sortie.findings[0].localisation, sortie.findings[0].localisation


def test_sur_un_autre_projet_le_secret_de_ses_tests_reste_detecte(tmp_path, monkeypatch):
    """Second temoin du verdict : sans la signature, les deux secrets sortent — c est bien
    l exclusion qui les taisait, et non le faux oracle qui ne les voyait pas."""
    cible = _forge(tmp_path / "produit", signature=False)

    sortie = _analyser(cible, tmp_path, monkeypatch)

    assert sortie.verdict == "FAIL", sortie.verdict
    assert len(sortie.findings) == 2, [f.localisation for f in sortie.findings]


# --- La declaration : une exclusion muette est un angle mort ----------------------------------
def test_l_exclusion_est_declaree_et_NOMME_ce_qu_elle_ecarte(tmp_path, monkeypatch):
    sortie = _analyser(_forge(tmp_path / "forge"), tmp_path, monkeypatch)

    mesures = [ligne for ligne in sortie.non_juge if "ECARTEE de ce scan" in ligne]
    assert mesures, sortie.non_juge
    assert "fixtures" in mesures[0] and "tests" in mesures[0], mesures[0]


def test_la_REGLE_est_au_NON_JUGE_du_module_donc_au_registre_de_dette(tmp_path, monkeypatch):
    """TF-0292 a posé l idiome : la regle se compte au registre, la mesure appartient au run."""
    regles = [ligne for ligne in securite.NON_JUGE if "banc" in ligne and "forge-tests" in ligne]
    assert regles, securite.NON_JUGE

    sortie = _analyser(_forge(tmp_path / "forge"), tmp_path, monkeypatch)
    assert all(regle in sortie.non_juge for regle in regles)


def test_aucune_MESURE_quand_le_projet_n_est_pas_la_forge(tmp_path, monkeypatch):
    """Declarer qu on a ecarte ce qu on n a pas ecarte serait du bruit — et un rapport se lit."""
    sortie = _analyser(_forge(tmp_path / "produit", signature=False), tmp_path, monkeypatch)

    assert not [ligne for ligne in sortie.non_juge if "ECARTEE de ce scan" in ligne]
