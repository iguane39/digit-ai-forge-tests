"""TF-2661 — une campagne sur une instance hébergée y laissait ses données de test.

Fait remonté par Produit-82 (lot 20261113h, RT-43, ledger seq 277 et 283) : la suite du produit,
rejouée à chaque déploiement sur la base réelle de la recette, créait des organisations et des
identités sans les effacer : 315 organisations et 465 identités non marquées au 13/11/2026. Aucune
règle ni contrôle ne comparait l'état de l'instance avant et après une campagne.

La règle : la campagne inscrit le décompte des objets métier de l'instance AVANT et APRÈS ses pans,
et un écart rend FAIL. Le décompte lui-même est celui du PRODUIT, seul à savoir ce que sont ses
objets : il déclare une commande (`FORGE_TESTS_INSTANCE_DECOMPTE`) qui imprime un objet JSON
`{"organisations": 315, "identites": 465}`. La forge fournit le contrôle, pas le décompte.

Sens prouvés :
  - ROUGE : une campagne qui crée un objet sans le retirer rend FAIL, l'écart est nommé ;
  - VERT : une campagne qui nettoie après elle laisse PASS, et ses deux décomptes sont au rapport ;
  - CONTRE-ÉPREUVES : sans commande déclarée, la section le DIT (instance hébergée : non mesuré ;
    instance locale ou aucune : sans objet) ; un décompte illisible rend « non mesuré », jamais un
    FAIL inventé ; un objet qui disparaît est un écart comme un objet qui apparaît.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from forge_tests import __main__ as cli
from forge_tests import residus_instance
from forge_tests.noyau import SortieAdaptateur, rapport

SCRIPT_DECOMPTE = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "etat = Path(sys.argv[1])\n"
    "print(json.dumps(json.loads(etat.read_text(encoding='utf-8'))))\n"
)
SCRIPT_EN_ECHEC = "import sys\nsys.stderr.write('base injoignable')\nsys.exit(3)\n"


def _commande(*arguments: object) -> str:
    return subprocess.list2cmdline([sys.executable, *map(str, arguments)])


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for nom in (
        "FORGE_TESTS_INSTANCE_DECOMPTE", "FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL",
        "FORGE_TESTS_API_URL",
    ):
        monkeypatch.delenv(nom, raising=False)


def _instance(tmp_path: Path, objets: dict[str, int]) -> tuple[Path, Path]:
    """L'état de l'instance (un fichier) et le décompte que le produit déclare."""
    dossier = tmp_path / "instance"
    dossier.mkdir()
    etat = dossier / "etat.json"
    etat.write_text(json.dumps(objets), encoding="utf-8")
    script = dossier / "decompte.py"
    script.write_text(SCRIPT_DECOMPTE, encoding="utf-8")
    return etat, script


def _produit(tmp_path: Path) -> Path:
    produit = tmp_path / "produit"
    (produit / "app").mkdir(parents=True)
    (produit / "app" / "__init__.py").write_text("", encoding="utf-8")
    return produit


def _campagne(monkeypatch: pytest.MonkeyPatch, effet) -> None:
    """Une campagne d'un pan : il joue `effet()` sur l'instance, puis rend PASS."""
    faux = types.SimpleNamespace(
        PAN="faux",
        analyser=lambda cible: (effet(), SortieAdaptateur("faux", "faux", str(cible), "PASS"))[1],
    )
    monkeypatch.setattr(cli, "REGISTRE", {"faux": faux})
    monkeypatch.setattr(cli, "PANS_ATTENDUS", ["faux"])


def _ajouter(etat: Path, objet: str, combien: int) -> None:
    objets = json.loads(etat.read_text(encoding="utf-8"))
    objets[objet] = objets.get(objet, 0) + combien
    etat.write_text(json.dumps(objets), encoding="utf-8")


# --- ROUGE : une campagne qui laisse un objet derrière elle --------------------------------------
def test_une_campagne_qui_cree_un_objet_sans_le_retirer_rend_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    etat, script = _instance(tmp_path, {"organisations": 315, "identites": 465})
    monkeypatch.setenv("FORGE_TESTS_INSTANCE_DECOMPTE", _commande(script, etat))
    _campagne(monkeypatch, lambda: _ajouter(etat, "organisations", 1))

    rap = cli.analyser(_produit(tmp_path))

    residus = rap["residus_instance"]
    assert rap["verdict"] == "FAIL"
    assert residus["statut"] == "residus" and residus["verdict"] == "FAIL"
    assert residus["avant"] == {"organisations": 315, "identites": 465}
    assert residus["apres"] == {"organisations": 316, "identites": 465}
    assert residus["ecarts"] == [
        {"objet": "organisations", "avant": 315, "apres": 316, "ecart": 1}
    ]
    assert "organisations" in residus["motif"] and "+1" in residus["motif"]


# --- VERT : une campagne qui nettoie après elle --------------------------------------------------
def test_une_campagne_qui_nettoie_laisse_le_verdict_et_inscrit_ses_deux_decomptes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    etat, script = _instance(tmp_path, {"organisations": 315})
    monkeypatch.setenv("FORGE_TESTS_INSTANCE_DECOMPTE", _commande(script, etat))

    def creer_puis_retirer() -> None:
        _ajouter(etat, "organisations", 1)
        _ajouter(etat, "organisations", -1)

    _campagne(monkeypatch, creer_puis_retirer)

    rap = cli.analyser(_produit(tmp_path))

    residus = rap["residus_instance"]
    assert rap["verdict"] == "PASS"
    assert residus["statut"] == "conforme" and residus["verdict"] == "PASS"
    assert residus["avant"] == residus["apres"] == {"organisations": 315}
    assert residus["ecarts"] == []


# --- Contre-épreuves : ce que la section dit quand elle ne mesure pas ----------------------------
def test_sans_commande_sur_une_instance_hebergee_la_section_le_dit_sans_changer_le_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORGE_TESTS_BASE_URL", "https://recette.exemple.org")
    _campagne(monkeypatch, lambda: None)

    rap = cli.analyser(_produit(tmp_path))

    residus = rap["residus_instance"]
    assert residus["statut"] == "non_mesure" and residus["verdict"] is None
    assert "FORGE_TESTS_INSTANCE_DECOMPTE" in residus["motif"]
    assert rap["verdict"] == "PASS"
    assert any("FORGE_TESTS_INSTANCE_DECOMPTE" in ligne for ligne in rap["non_juge"])


@pytest.mark.parametrize("url", [None, "http://localhost:8000", "http://127.0.0.1:5173"])
def test_sans_instance_hebergee_ni_commande_la_section_est_sans_objet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str | None
) -> None:
    if url:
        monkeypatch.setenv("FORGE_TESTS_BASE_URL", url)
    _campagne(monkeypatch, lambda: None)

    rap = cli.analyser(_produit(tmp_path))

    assert rap["residus_instance"]["statut"] == "sans_objet"
    assert rap["residus_instance"]["verdict"] is None
    assert not any("FORGE_TESTS_INSTANCE_DECOMPTE" in ligne for ligne in rap["non_juge"])


def test_un_decompte_qui_echoue_avant_est_non_mesure_jamais_un_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    echec = tmp_path / "echec.py"
    echec.write_text(SCRIPT_EN_ECHEC, encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_INSTANCE_DECOMPTE", _commande(echec))
    _campagne(monkeypatch, lambda: None)

    rap = cli.analyser(_produit(tmp_path))

    residus = rap["residus_instance"]
    assert residus["statut"] == "non_mesure" and rap["verdict"] == "PASS"
    assert "avant" in residus["motif"] and "base injoignable" in residus["motif"]


def test_un_decompte_qui_echoue_apres_est_non_mesure_jamais_un_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    etat, script = _instance(tmp_path, {"organisations": 5})
    monkeypatch.setenv("FORGE_TESTS_INSTANCE_DECOMPTE", _commande(script, etat))
    _campagne(monkeypatch, lambda: etat.unlink())

    rap = cli.analyser(_produit(tmp_path))

    residus = rap["residus_instance"]
    assert residus["statut"] == "non_mesure" and rap["verdict"] == "PASS"
    assert "après" in residus["motif"]
    assert residus["avant"] == {"organisations": 5}


@pytest.mark.parametrize(
    "sortie",
    ["pas du json", "[1, 2]", '{"organisations": "beaucoup"}', '{"organisations": -3}',
     '{"organisations": 2.5}', '{"organisations": true}', "{}"],
)
def test_un_decompte_illisible_est_refuse_avec_son_motif(
    tmp_path: Path, sortie: str
) -> None:
    script = tmp_path / "decompte.py"
    script.write_text(f"print({sortie!r})\n", encoding="utf-8")

    mesure = residus_instance.mesurer(
        tmp_path, {"FORGE_TESTS_INSTANCE_DECOMPTE": _commande(script)}
    )

    assert mesure["decompte"] is None
    assert mesure["motif"]


# --- La comparaison ------------------------------------------------------------------------------
def test_comparer_nomme_chaque_objet_dont_le_compte_a_change() -> None:
    ecarts = residus_instance.comparer(
        {"organisations": 315, "identites": 465, "missions": 7},
        {"organisations": 316, "identites": 465, "missions": 5},
    )
    assert ecarts == [
        {"objet": "missions", "avant": 7, "apres": 5, "ecart": -2},
        {"objet": "organisations", "avant": 315, "apres": 316, "ecart": 1},
    ]


def test_comparer_traite_un_objet_apparu_ou_disparu_comme_un_ecart() -> None:
    assert residus_instance.comparer({"a": 1}, {"a": 1, "b": 2}) == [
        {"objet": "b", "avant": 0, "apres": 2, "ecart": 2}
    ]
    assert residus_instance.comparer({"a": 1, "b": 2}, {"a": 1}) == [
        {"objet": "b", "avant": 2, "apres": 0, "ecart": -2}
    ]


def test_comparer_ne_rend_rien_quand_rien_n_a_change() -> None:
    assert residus_instance.comparer({"a": 1, "b": 0}, {"b": 0, "a": 1}) == []


# --- Le verdict du rapport -----------------------------------------------------------------------
def test_le_verdict_du_rapport_pese_un_ecart_comme_un_fail() -> None:
    sortie = SortieAdaptateur("a", "api", "cible", "PASS")
    section = {"statut": "residus", "verdict": "FAIL", "ecarts": [], "motif": "x"}

    assert rapport([sortie], ["api"], residus_instance=section)["verdict"] == "FAIL"
    assert rapport([sortie], ["api"])["verdict"] == "PASS"
    assert rapport([sortie], ["api"])["residus_instance"]["statut"] == "non_mesure"


def test_un_pan_manquant_garde_la_precedence_sur_un_ecart() -> None:
    """La précédence existante ne bouge pas : PARTIEL > FAIL > PASS."""
    section = {"statut": "residus", "verdict": "FAIL", "ecarts": [], "motif": "x"}
    assert rapport([], ["api"], residus_instance=section)["verdict"] == "PARTIEL"
