"""TF-2229 (D-178) — la campagne lit chaque réglage de plateforme exigé et le compare à l'attendu.

Pièce 5 de l'étude « Sécurité par défaut de bout en bout » du 06/11/2026. Le principe « réglage
admissible appliqué à la création, vérifié à chaque livraison, exception décidée » devient une loi
transverse (décision D-178 (a)) ; le point d'injection des tests est une lecture, en campagne, de
chaque réglage que le produit exige, reliée à l'exigence.

Le registre lu est une COPIE de fixture (`fixtures/reglages-plateforme/`), jamais le fichier réel du
pilot. La commande de lecture est remplacée par un relevé canonique : ce qui est prouvé ici est la
dérivation du verdict, seule partie déterministe ; le réseau n'est jamais touché.

Sens prouvés :
  - ROUGE  — réglage `defaut` hors de l'attendu ; réglage `decision` sans décision consignée (écart
             nu) ; écart accepté NON tenu tel que décidé ; réglage inconnu du registre ;
  - VERT   — réglage conforme à l'attendu ; écart accepté tenu tel que décidé ;
  - SANS OBJET / NON LU — aucune exigence de réglage ; secret absent ; commande qui écrit refusée ;
             attendu non mécanisable : jamais un succès.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_tests import classes
from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, reglages

REGISTRE_COPIE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "reglages-plateforme"
    / "REGLAGES-SURS-PAR-DEFAUT.json"
)
SECRET = "sbp_valeur_secrete_de_test_0123456789"
TLS = "TLS imposé"
MFA = "Double vérification imposée"
SECRETS_GITHUB = "Protection des secrets à la poussée"


@pytest.fixture(autouse=True)
def _environnement(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("FORGE_TESTS_EXIGENCES", "FORGE_ROOT"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.setenv("FORGE_TESTS_REGISTRE_REGLAGES", str(REGISTRE_COPIE))
    monkeypatch.setenv("PROJECT_REF", "abcdefgh")
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", SECRET)
    monkeypatch.setenv("OWNER", "acme")
    monkeypatch.setenv("REPO", "produit")
    monkeypatch.setenv("ORG_SLUG", "acme-org")


def _produit(tmp_path: Path, exigences: list[dict]) -> Path:
    racine = tmp_path / "produit"
    (racine / "forge").mkdir(parents=True)
    (racine / "forge" / "EXIGENCES.json").write_text(
        json.dumps({"projet": "p", "exigences": exigences}, ensure_ascii=False), encoding="utf-8"
    )
    return racine


def _lecture(monkeypatch: pytest.MonkeyPatch, rendu: str, code: int = 0) -> list[str]:
    jouees: list[str] = []

    def faux(commande: str, env: dict[str, str]) -> tuple[int, str, str]:
        jouees.append(commande)
        return code, rendu, "" if code == 0 else "401 Unauthorized"

    monkeypatch.setattr(reglages, "_executer", faux)
    return jouees


def _constats(sortie) -> list:  # noqa: ANN001
    """Les constats de réglage ; le pan y ajoute un constat de seuil qui ne nous regarde pas."""
    return [f for f in sortie.findings if f.id.startswith("reglage:")]


def _exigence(identifiant: str, reglage: str, **plus: object) -> dict:
    return {"id": identifiant, "enonce": "x", "reglage_plateforme": {"reglage": reglage, **plus}}


# --- Le registre copié en fixture -----------------------------------------------------------------
def test_la_copie_de_fixture_est_un_registre_valide_de_neuf_reglages() -> None:
    registre = reglages.lire_registre(REGISTRE_COPIE)
    assert len(registre) == 9
    assert {e["classement"] for e in registre} == {"defaut", "decision"}
    assert sum(e["classement"] == "defaut" for e in registre) == 5


def test_le_pan_est_inscrit_au_registre_et_attendu() -> None:
    assert REGISTRE["reglages-plateforme"] is reglages
    assert reglages.PAN in PANS_ATTENDUS
    assert reglages.CHAPITRES


# --- Sans objet -----------------------------------------------------------------------------------
def test_sans_exigence_de_reglage_le_pan_est_sans_objet(tmp_path: Path) -> None:
    racine = _produit(tmp_path, [{"id": "E-001", "enonce": "une page d'accueil"}])
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "NA"
    assert any("aucune exigence de réglage" in ligne for ligne in sortie.non_juge)


# --- Branche défaut -------------------------------------------------------------------------------
def test_vert_un_reglage_defaut_conforme_a_l_attendu_passe_et_la_lecture_est_celle_du_registre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, [_exigence("E-012", TLS)])
    jouees = _lecture(monkeypatch, "true\n")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "PASS", sortie.non_juge
    assert sortie.findings == []
    assert len(jouees) == 1 and "ssl-enforcement" in jouees[0]  # cmd_lire du registre, rien d'autre


def test_rouge_un_reglage_defaut_hors_de_l_attendu_est_un_constat_relie_a_l_exigence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, [_exigence("E-012", TLS)])
    _lecture(monkeypatch, "false\n")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert len(_constats(sortie)) == 1
    constat = _constats(sortie)[0]
    assert constat.classe == classes.REGLAGE_PLATEFORME_HORS_ATTENDU
    assert constat.id.startswith("reglage:E-012:")  # la traçabilité exigence vers test
    assert "attendu « true »" in constat.message and "lu « false" in constat.message
    assert "cmd_appliquer" in constat.message


def test_un_reglage_inconnu_du_registre_est_un_constat_pas_un_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, [_exigence("E-020", "Pare-feu applicatif magique")])
    _lecture(monkeypatch, "true")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert "ne porte pas" in _constats(sortie)[0].message


# --- Branche décision -----------------------------------------------------------------------------
def test_rouge_un_reglage_decision_sans_decision_consignee_est_un_ecart_nu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, [_exigence("E-030", MFA)])
    jouees = _lecture(monkeypatch, "true")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert _constats(sortie)[0].classe == classes.REGLAGE_DECIDE_NON_TENU
    assert "écart nu" in _constats(sortie)[0].message
    assert jouees == []  # rien à lire tant que la décision n'est pas posée


def test_vert_un_ecart_accepte_est_verifie_tel_que_decide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision = {"choix": "ecart-accepte", "valeur_decidee": "disabled",
                "motif": "dépôt privé sans secret", "decide_par": "porteur, 29/10/2026"}
    racine = _produit(tmp_path, [_exigence("E-040", SECRETS_GITHUB, decision=decision)])
    _lecture(monkeypatch, "disabled\n")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "PASS", sortie.non_juge
    assert sortie.findings == []


def test_rouge_un_ecart_accepte_qui_n_est_plus_tel_que_decide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le réglage a bougé depuis la décision (activé alors qu'il était accepté désactivé)."""
    decision = {"choix": "ecart-accepte", "valeur_decidee": "disabled", "motif": "m"}
    racine = _produit(tmp_path, [_exigence("E-040", SECRETS_GITHUB, decision=decision)])
    _lecture(monkeypatch, "enabled\n")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert _constats(sortie)[0].classe == classes.REGLAGE_DECIDE_NON_TENU
    assert "non tenu tel que décidé" in _constats(sortie)[0].message


def test_une_decision_appliquer_se_compare_a_l_attendu_du_registre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision = {"choix": "applique", "motif": "choix du porteur"}
    racine = _produit(tmp_path, [_exigence("E-040", SECRETS_GITHUB, decision=decision)])
    _lecture(monkeypatch, "enabled\n")
    assert reglages.analyser(racine).verdict == "PASS"


# --- Ce qui n'a pas pu être lu : jamais un succès -------------------------------------------------
def test_un_secret_absent_est_nomme_et_sa_valeur_ne_fuit_jamais(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN")
    racine = _produit(tmp_path, [_exigence("E-012", TLS)])
    jouees = _lecture(monkeypatch, "true")
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "SKIP" and jouees == []
    assert any("SUPABASE_ACCESS_TOKEN" in ligne and "NON LU" in ligne for ligne in sortie.non_juge)


def test_la_valeur_d_un_secret_n_entre_jamais_dans_la_sortie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, [_exigence("E-012", TLS)])
    _lecture(monkeypatch, "", code=22)
    sortie = reglages.analyser(racine)
    assert SECRET not in sortie.json()
    assert any("lecture en échec" in ligne for ligne in sortie.non_juge)


def test_une_commande_de_lecture_qui_ecrit_est_refusee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registre = json.loads(REGISTRE_COPIE.read_text(encoding="utf-8"))
    registre[0]["cmd_lire"] = registre[0]["cmd_appliquer"]  # un PUT, pas une lecture
    copie = tmp_path / "registre.json"
    copie.write_text(json.dumps(registre, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("FORGE_TESTS_REGISTRE_REGLAGES", str(copie))
    racine = _produit(tmp_path, [_exigence("E-012", TLS)])
    jouees = _lecture(monkeypatch, "true")
    sortie = reglages.analyser(racine)
    assert jouees == [], "une commande qui écrit a été jouée"
    assert any("ÉCRIT" in ligne for ligne in sortie.non_juge)


def test_un_attendu_non_mecanisable_est_lu_mais_non_compare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    racine = _produit(tmp_path, [_exigence("E-050", "Restriction des adresses admises")])
    _lecture(monkeypatch, '{"v4": ["203.0.113.0/24"], "v6": [], "status": "applied"}')
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "SKIP"  # rien n'a été comparé : ce n'est pas un PASS
    assert any("forme non mécanisable" in ligne for ligne in sortie.non_juge)


def test_un_registre_introuvable_est_un_skip_qui_nomme_les_chemins_cherches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORGE_TESTS_REGISTRE_REGLAGES", str(tmp_path / "absent.json"))
    monkeypatch.setattr(reglages, "chemins_du_registre", lambda _c: [tmp_path / "absent.json"])
    racine = _produit(tmp_path, [_exigence("E-012", TLS)])
    sortie = reglages.analyser(racine)
    assert sortie.verdict == "SKIP"
    assert any("INTROUVABLE" in ligne and "absent.json" in ligne for ligne in sortie.non_juge)


def test_un_registre_aux_cles_inexactes_est_refuse(tmp_path: Path) -> None:
    registre = json.loads(REGISTRE_COPIE.read_text(encoding="utf-8"))
    registre[0]["intrus"] = 1
    copie = tmp_path / "registre.json"
    copie.write_text(json.dumps(registre, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(reglages.RegistreIllisible, match="clés"):
        reglages.lire_registre(copie)


# --- La comparaison -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "attendu,lu,verdict",
    [
        ("true", "true", "PASS"), ("true", "false", "FAIL"), ("on", '"on"', "PASS"),
        ("enabled", "disabled", "FAIL"), ("0 (réponse 204)", "0", "PASS"),
        ("0 (réponse 204)", "22", "FAIL"),
        ("true pour chaque membre (l'obligation n'est pas lisible)", "true", "PASS"),
        ("contient deletion, non_fast_forward et pull_request",
         '["deletion","non_fast_forward","pull_request"]', "PASS"),
        ("contient deletion, non_fast_forward et pull_request", '["deletion"]', "FAIL"),
        ("enabled = true, max_age >= 31536000", "{}", "NON_COMPARABLE"),
    ],
)
def test_evaluer(attendu: str, lu: str, verdict: str) -> None:
    assert reglages.evaluer(attendu, lu)[0] == verdict


def test_les_classes_sont_declarees_et_classees() -> None:
    from forge_tests import actions

    for classe in (classes.REGLAGE_PLATEFORME_HORS_ATTENDU, classes.REGLAGE_DECIDE_NON_TENU):
        assert classe in classes.CLASSES and classe in actions._REGLES
