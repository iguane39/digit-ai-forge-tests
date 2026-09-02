"""TF-0340 / TF-0341 — le cycle de vie de l instance servie, et de quoi elle a été bâtie.

Faits mesurés le 17/08/2026 sur Produit-11, sur pièces :

  - **TF-0340** — `node e2e/preparer.mjs` monte 3 conteneurs et un réseau ; l audit se termine
    à 11:30 ; les conteneurs tiennent les ports 8091, 8092 et 5544 jusqu à 13:55, soit 2 h 25
    sans le moindre usage, jusqu à ce qu un humain s en étonne. Aucune ligne du rapport ne
    mentionnait ce qui restait en service. Au-delà de l encombrement : les ports sont pris, donc
    un second audit sur le même poste se heurte à une instance qu il n a pas montée sans pouvoir
    savoir si elle est la sienne.
  - **TF-0341** — la topologie auditée avait été bâtie à 10:47 ; le correctif D-14
    (`src/02_get_advert.py`) a été écrit APRÈS. Entre 11:30 et 13:55 l instance servait un code
    antérieur au correctif et rien ne l aurait signalé. Un audit relancé dans cette fenêtre
    aurait publié ses chiffres comme l état courant du produit.

Ce que ces tests tiennent, DANS LES DEUX SENS — sans quoi les deux contrôles seraient
décoratifs :

  - la section `instance` est TOUJOURS présente au rapport, y compris sans instance déclarée :
    une section qui disparaîtrait serait indiscernable d une section qui a mesuré et n a rien
    trouvé, exactement le silence que ce framework interdit ailleurs ;
  - une instance laissée debout est DITE, avec la commande qui la démonte quand le projet l a
    déclarée — et l absence de cette commande est dite aussi, puisque c est elle qui a coûté les
    2 h 25 ;
  - la provenance rend les TROIS issues de TF-0288, jamais un verdict deviné : `concordant`,
    `divergent` (l écart nommé, plus la phrase qui compte), `non_determinable` en disant LEQUEL
    des deux termes manque ;
  - le cas fondateur est rejoué tel quel : un fichier scellé au montage puis corrigé dans
    l arbre de travail rend `divergent` et NOMME le fichier ;
  - contre-épreuve indispensable : un fichier NEUF, que l empreinte scellée ne connaît pas, ne
    déclenche RIEN. Sans elle, `divergent` pourrait être rendu par simple asymétrie de lecture
    et le contrôle accuserait le produit d un défaut de son lecteur (la limite que
    `interface/ecart-servi` déclare déjà pour la même raison).
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from forge_tests.instance import (
    CHAMP_DEMONTER,
    CHAMP_PROVENANCE,
    CONCORDANT,
    DIVERGENT,
    NON_DETERMINABLE,
    PHRASE_DIVERGENT,
    au_rapport,
    provenance,
)


def _sceller(projet: Path, relatifs: list[str]) -> Path:
    """Écrit un scellé au format forge-ops/empreinte@1 — le format n est PAS réinventé ici."""
    fichiers = {
        rel: sha256((projet / rel).read_bytes()).hexdigest() for rel in relatifs
    }
    chemin = projet / "empreinte-instance.json"
    chemin.write_text(
        json.dumps(
            {
                "format": "forge-ops/empreinte@1",
                "release": "r42",
                "ts": "2026-08-17T10:47:00+02:00",
                "fichiers": fichiers,
            }
        ),
        encoding="utf-8",
    )
    return chemin


def _projet(tmp_path: Path) -> Path:
    projet = tmp_path / "produit-11"
    (projet / "src").mkdir(parents=True)
    (projet / "src" / "02_get_advert.py").write_text("def get(): return 1\n", encoding="utf-8")
    return projet


# ── TF-0340 · le cycle de vie ────────────────────────────────────────────────────────────────


def test_section_toujours_presente_sans_instance(tmp_path: Path) -> None:
    """Sans instance déclarée, la section existe et le DIT — elle ne disparaît pas."""
    r = au_rapport(_projet(tmp_path), env={})
    assert set(r) == {"cycle_de_vie", "provenance", "non_juge"}
    assert r["cycle_de_vie"]["etat"] == "aucune_instance_declaree"
    assert r["non_juge"], "une section sans limites déclarées ne juge rien"


def test_instance_laissee_debout_est_dite_avec_sa_commande(tmp_path: Path) -> None:
    """Le cas réel : l audit ne monte pas, laisse debout, et publie comment démonter."""
    env = {
        "FORGE_TESTS_BASE_URL": "http://localhost:8091",
        "FORGE_TESTS_QUALIF_URL": "http://localhost:8092",
        CHAMP_DEMONTER: "node e2e/demonter.mjs",
    }
    c = au_rapport(_projet(tmp_path), env=env)["cycle_de_vie"]
    assert c["etat"] == "laissee_debout"
    assert "node e2e/demonter.mjs" in c["consigne"]
    urls = [u["url"] for u in c["laisse_en_service"]]
    assert urls == ["http://localhost:8091", "http://localhost:8092"]
    assert "démonte ce qu elle a monté" in c["regle"]


def test_absence_de_commande_de_demontage_est_dite(tmp_path: Path) -> None:
    """C est l absence de cette commande qui a coûté 2 h 25 : elle ne peut pas être tue."""
    env = {"FORGE_TESTS_BASE_URL": "http://localhost:8091"}
    c = au_rapport(_projet(tmp_path), env=env)["cycle_de_vie"]
    assert c["etat"] == "laissee_debout_sans_commande"
    assert CHAMP_DEMONTER in c["consigne"]
    assert c["demonter"] is None


def test_la_forge_demonte_ce_qu_elle_a_monte(tmp_path: Path) -> None:
    """Premier sens de la règle — inatteignable aujourd hui, écrit pour ne pas être un ajout."""
    env = {"FORGE_TESTS_BASE_URL": "http://localhost:8091"}
    c = au_rapport(_projet(tmp_path), env=env, monte_par_la_forge=True)["cycle_de_vie"]
    assert c["etat"] == "montee_par_la_forge"
    assert "sans rien demander" in c["consigne"]


# ── TF-0341 · la provenance ──────────────────────────────────────────────────────────────────


def test_provenance_non_declaree_dit_quel_terme_manque(tmp_path: Path) -> None:
    r = provenance(_projet(tmp_path), env={})
    assert r["issue"] == NON_DETERMINABLE
    assert r["terme_manquant"] == "servi"
    assert CHAMP_PROVENANCE in r["motif"]


def test_provenance_concordante(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    emp = _sceller(projet, ["src/02_get_advert.py"])
    r = provenance(projet, env={CHAMP_PROVENANCE: str(emp)})
    assert r["issue"] == CONCORDANT
    assert r["servi"]["format"] == "forge-ops/empreinte@1"
    assert r["servi"]["fichiers_scelles"] == 1


def test_cas_fondateur_correctif_ecrit_apres_le_montage(tmp_path: Path) -> None:
    """Le cas réel du 17/08 : D-14 écrit après le scellement → divergent, fichier NOMMÉ."""
    projet = _projet(tmp_path)
    emp = _sceller(projet, ["src/02_get_advert.py"])
    (projet / "src" / "02_get_advert.py").write_text(
        "def get(): return 2  # D-14\n", encoding="utf-8")
    r = provenance(projet, env={CHAMP_PROVENANCE: str(emp)})
    assert r["issue"] == DIVERGENT
    assert r["ecarts_total"] == 1
    assert any("src/02_get_advert.py" in e for e in r["ecarts"])
    assert PHRASE_DIVERGENT in r["motif"], "la phrase qui compte doit être au rapport"


def test_fichier_neuf_ne_declenche_rien(tmp_path: Path) -> None:
    """Contre-épreuve : la comparaison n est PAS symétrique (limite déclarée au non_juge)."""
    projet = _projet(tmp_path)
    emp = _sceller(projet, ["src/02_get_advert.py"])
    (projet / "src" / "03_neuf.py").write_text("X = 1\n", encoding="utf-8")
    r = provenance(projet, env={CHAMP_PROVENANCE: str(emp)})
    assert r["issue"] == CONCORDANT, "un fichier neuf n a jamais eu à être déployé"


def test_fichier_scelle_disparu_est_un_ecart(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    emp = _sceller(projet, ["src/02_get_advert.py"])
    (projet / "src" / "02_get_advert.py").unlink()
    r = provenance(projet, env={CHAMP_PROVENANCE: str(emp)})
    assert r["issue"] == DIVERGENT
    assert any("absent de l arbre" in e for e in r["ecarts"])


def test_format_de_provenance_inconnu_est_refuse_en_le_disant(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    mauvais = projet / "provenance.json"
    mauvais.write_text('{"format": "maison@9"}', encoding="utf-8")
    r = provenance(projet, env={CHAMP_PROVENANCE: str(mauvais)})
    assert r["issue"] == NON_DETERMINABLE
    assert "format de provenance inconnu" in r["motif"]
    assert "forge-ops/empreinte@1" in r["motif"], "les formats lus doivent être nommés"


def test_forme_legere_sans_terme_comparable(tmp_path: Path) -> None:
    """Un document qui existe mais ne porte aucun terme opposable est NON DÉTERMINABLE."""
    projet = _projet(tmp_path)
    leger = projet / "instance.json"
    leger.write_text(
        '{"format": "forge-tests/instance@1", "construit_le": "2026-08-17"}', encoding="utf-8")
    r = provenance(projet, env={CHAMP_PROVENANCE: str(leger)})
    assert r["issue"] == NON_DETERMINABLE
    assert r["terme_manquant"] == "servi"


def test_provenance_illisible_ne_ment_pas(tmp_path: Path) -> None:
    projet = _projet(tmp_path)
    r = provenance(projet, env={CHAMP_PROVENANCE: str(projet / "jamais-ecrit.json")})
    assert r["issue"] == NON_DETERMINABLE
    assert "introuvable" in r["motif"]
