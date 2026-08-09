"""Qualification — ce qu aucune exécution ne POUVAIT atteindre ici (RT-6a, RT-13).

Le module décide ce qu on demande à un humain de fournir. Une erreur y coûte cher dans les deux
sens : taire un manque, c est accuser le projet d un trou de couverture qui n est pas le sien ;
en inventer un, c est réclamer une configuration inutile — 16 actions fausses au rapport ASD du
07/08. La recette en vérifie la détection ; ces tests portent sur le registre lui-même, ses
frontières et son point d application.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import qualification
from forge_tests.noyau import NonTestable, SortieAdaptateur

CIBLE = "/projet-de-test-unitaire"


class _Adaptateur:
    """Adaptateur minimal : un pan, ses champs revendiqués, aucun inventaire."""

    def __init__(self, pan: str, champs: tuple[str, ...] = ()) -> None:
        self.PAN = pan
        self.CHAMPS_REQUIS = champs


@pytest.fixture(autouse=True)
def _registre_propre():
    qualification.oublier(CIBLE)
    yield
    qualification.oublier(CIBLE)


def _skip(pan: str) -> SortieAdaptateur:
    return SortieAdaptateur(f"{pan}-test", pan, CIBLE, "SKIP")


# --- Registre : ce qui entre, ce qui n entre pas ----------------------------------------------
def test_une_variable_fournie_n_est_jamais_un_manque(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZZ_FOURNIE", "valeur")
    qualification.declarer(CIBLE, "backend", ("ZZ_FOURNIE", "ZZ_ABSENTE"))
    assert qualification.requis(CIBLE, "backend") == {"ZZ_ABSENTE": "constate"}


def test_une_variable_vide_compte_comme_absente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une variable posée à la chaîne vide n est pas fournie : elle est déclarée et inutile."""
    monkeypatch.setenv("ZZ_VIDE", "   ")
    qualification.declarer(CIBLE, "backend", ("ZZ_VIDE",))
    assert "ZZ_VIDE" in qualification.requis(CIBLE, "backend")


def test_la_premiere_provenance_gagne() -> None:
    """Un champ constaté ne doit pas être rétrogradé en présumé par une déclaration tardive."""
    qualification.declarer(CIBLE, "backend", ("ZZ_JETON",), provenance="constate")
    qualification.declarer(CIBLE, "backend", ("ZZ_JETON",), provenance="presume")
    assert qualification.requis(CIBLE, "backend")["ZZ_JETON"] == "constate"


def test_chemin_et_chaine_designent_le_meme_projet() -> None:
    """`Path` et `str` doivent se rejoindre : sinon un manque détecté est perdu en silence."""
    qualification.declarer(Path(CIBLE), "backend", ("ZZ_JETON",))
    assert "ZZ_JETON" in qualification.requis(CIBLE, "backend")


def test_les_faux_amis_d_une_trace_python_ne_sont_pas_des_secrets() -> None:
    assert qualification.detecter(CIBLE, "backend", "KeyError: 'PATH'") == set()


def test_champs_presumes_lit_les_cles_declarees_par_le_projet(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        "# commentaire\nZZ_CLE_TIERCE=\nligne sans egal\nZZ_AUTRE=valeur\n", encoding="utf-8"
    )
    assert qualification.champs_presumes(tmp_path) == ["ZZ_CLE_TIERCE", "ZZ_AUTRE"]


# --- Point d application : qui reçoit quoi ----------------------------------------------------
def test_seul_un_pan_en_SKIP_est_qualifie() -> None:
    qualification.declarer(CIBLE, "backend", ("ZZ_JETON",))
    passant = SortieAdaptateur("api-test", "api", CIBLE, "PASS")
    qualification.qualifier([passant], Path(CIBLE), {})
    assert passant.non_testables == []


def test_ce_qu_un_adaptateur_a_deja_declare_n_est_pas_ecrase() -> None:
    qualification.declarer(CIBLE, "backend", ("ZZ_JETON",))
    sortie = _skip("api")
    sortie.non_testables.append(NonTestable("endpoint:GET /x", ["ZZ_PROPRE"], "api", "motif"))
    qualification.qualifier([sortie], Path(CIBLE), {})
    assert [n.champs_requis for n in sortie.non_testables] == [["ZZ_PROPRE"]]


def test_un_pan_sans_domaine_de_configuration_est_laisse_tranquille() -> None:
    """Le pan `interface` est un contrôle STATIQUE : aucune configuration ne le débloque."""
    qualification.declarer(CIBLE, "backend", ("ZZ_JETON",))
    qualification.declarer(CIBLE, "acces", ("ZZ_URL",))
    sortie = _skip("interface")
    qualification.qualifier([sortie], Path(CIBLE), {})
    assert sortie.non_testables == []


def test_un_pan_sans_inventaire_reste_NOMME() -> None:
    """Un pan dont rien n est énumérable garde une entrée : le silence ressemblerait à « RAS »."""
    qualification.declarer(CIBLE, "backend", ("ZZ_JETON",))
    sortie = _skip("api")
    qualification.qualifier([sortie], Path(CIBLE), {})
    assert [n.element for n in sortie.non_testables] == ["pan:api"]
    assert "ZZ_JETON" in sortie.non_testables[0].motif


# --- RT-13 : chaque champ appartient au pan qui le réclame -------------------------------------
def test_proprietaires_recense_les_revendications() -> None:
    registre = {
        "a": _Adaptateur("qualif", ("ZZ_URL_QUALIF",)),
        "b": _Adaptateur("front", ("ZZ_BASE_URL",)),
        "c": _Adaptateur("visuel", ("ZZ_BASE_URL",)),
        "d": _Adaptateur("data"),
    }
    assert qualification.proprietaires(registre) == {
        "ZZ_URL_QUALIF": {"qualif"},
        "ZZ_BASE_URL": {"front", "visuel"},
    }


def test_un_champ_revendique_ne_va_qu_a_ses_revendicateurs() -> None:
    registre = {"a": _Adaptateur("qualif", ("ZZ_URL_QUALIF",)), "b": _Adaptateur("data")}
    qualification.declarer(CIBLE, "acces", ("ZZ_URL_QUALIF",))
    qualif, data = _skip("qualif"), _skip("data")
    qualification.qualifier([qualif, data], Path(CIBLE), registre)
    assert qualif.non_testables[0].champs_requis == ["ZZ_URL_QUALIF"]
    assert data.non_testables == []


def test_un_champ_sans_proprietaire_reste_partage() -> None:
    """Les variables PROPRES AU PROJET, citées par une trace, n ont aucun revendicateur."""
    registre = {"a": _Adaptateur("qualif", ("ZZ_URL_QUALIF",)), "b": _Adaptateur("data")}
    qualification.declarer(CIBLE, "acces", ("ZZ_URL_QUALIF",))
    qualification.detecter(CIBLE, "backend", "KeyError: 'ZZ_JETON_CLIENT'")
    data = _skip("data")
    qualification.qualifier([data], Path(CIBLE), registre)
    assert data.non_testables[0].champs_requis == ["ZZ_JETON_CLIENT"]


def test_le_repli_presume_ne_sert_que_faute_de_constat(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("ZZ_CLE_TIERCE=\n", encoding="utf-8")
    qualification.oublier(tmp_path)
    sortie = _skip("api")
    sortie.cible = str(tmp_path)
    qualification.qualifier([sortie], tmp_path, {})
    assert sortie.non_testables[0].champs_requis == ["ZZ_CLE_TIERCE"]
    assert "presume" in sortie.non_testables[0].motif
    qualification.oublier(tmp_path)
