"""TF-0842 — une commande de démontage qui rend 0 sans démonter est indiscernable d'un succès.

LE FAIT (lot Produit-61, retour du 05/09/2026). L'instance remontée pour l'audit n'avait pas la
clé de session que l'application attend, et la commande de démontage déclarée — `taskkill /IM
uvicorn.exe` — ne tuait rien : un `uvicorn` lancé par `uv run` ne s'appelle pas `uvicorn.exe`,
c'est un `python.exe` **enfant** de `uv`. La commande rendait la main sans erreur. Une instance
**sans clé** occupait donc le port après l'audit, le smoke M-3 rendait 500, et il a fallu
**une demi-heure et trois relances** pour comprendre que rien n'avait été démonté.

Seul le PORT dit la vérité. Ces cas vérifient qu'on le sonde, ce qu'on en conclut, et — tout
aussi important — ce qu'on **refuse** de conclure : le module dit qu'un port est TENU, jamais
QUI le tient.

La frontière du `NON_JUGE` d'origine tient : on ne balaie pas le poste, on sonde le port de
l'URL que cet audit a lui-même déclarée servie.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from forge_tests import instance

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture()
def port_tenu():
    """Un port réellement TENU par une socket d'écoute — l'instance qui n'a pas été démontée."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as ecoute:
        ecoute.bind(("127.0.0.1", 0))
        ecoute.listen(1)
        yield ecoute.getsockname()[1]


@pytest.fixture()
def port_libre() -> int:
    """Un port qui vient d'être relâché — l'instance correctement démontée."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


# --- La sonde elle-même -------------------------------------------------------------------------


def test_un_port_tenu_est_vu_TENU(port_tenu: int) -> None:
    """FIXTURE ROUGE — le cas du 05/09 : l'instance est toujours là après le démontage."""
    lu = instance.sonder_port(f"http://127.0.0.1:{port_tenu}")

    assert lu["etat"] == instance.PORT_OCCUPE
    assert lu["hote"] == "127.0.0.1"
    assert lu["port"] == port_tenu


def test_un_port_libre_est_vu_LIBRE(port_libre: int) -> None:
    """FIXTURE VERTE — le démontage a fait ce qu'il annonçait."""
    assert instance.sonder_port(f"http://127.0.0.1:{port_libre}")["etat"] == instance.PORT_LIBRE


def test_le_port_implicite_du_schema_est_deduit() -> None:
    """Une URL sans port n'est pas une URL sans port : `https` en porte un."""
    assert instance._hote_port("https://produit.exemple.test")[1] == 443
    assert instance._hote_port("http://produit.exemple.test")[1] == 80
    assert instance._hote_port("http://produit.exemple.test:8091")[1] == 8091


def test_une_URL_inexploitable_est_INDETERMINABLE_avec_son_motif() -> None:
    """BORNE : ce qu'on ne peut pas sonder se déclare, il ne se devine pas."""
    lu = instance.sonder_port("pas une url")

    assert lu["etat"] == instance.PORT_INDETERMINABLE
    assert lu["motif"]


# --- Le verdict après démontage -------------------------------------------------------------


def test_le_verdict_dit_ENCORE_TENU_et_nomme_le_remede_MESURE(port_tenu: int) -> None:
    """Le cœur de l'item : la consigne doit porter la cause réelle, pas un conseil générique."""
    verdict = instance.verifier_demontage(
        {"FORGE_TESTS_BASE_URL": f"http://127.0.0.1:{port_tenu}"}
    )

    assert verdict["verdict"] == "encore_tenu"
    assert f"127.0.0.1:{port_tenu}" in verdict["motif"]
    consigne = verdict["consigne"] or ""
    assert "uv run" in consigne, "la cause mesuree doit etre nommee, sinon on la recherche"
    assert "kill-port" in consigne or "taskkill /PID" in consigne, (
        "le remede doit passer PAR LE PORT, puisque c est le nom du processus qui trompait")


def test_le_verdict_dit_LIBERE_quand_le_port_l_est(port_libre: int) -> None:
    verdict = instance.verifier_demontage(
        {"FORGE_TESTS_QUALIF_URL": f"http://127.0.0.1:{port_libre}"}
    )

    assert verdict["verdict"] == "libere"
    assert verdict["consigne"] is None


def test_sans_URL_declaree_le_verdict_est_NON_VERIFIABLE_et_le_dit() -> None:
    """Le silence est interdit ici comme partout : « rien à vérifier » se déclare."""
    verdict = instance.verifier_demontage({})

    assert verdict["verdict"] == "non_verifiable"
    assert "aucune URL servie déclarée" in verdict["motif"]
    assert verdict["ports"] == []


def test_toutes_les_URL_declarees_sont_sondees(port_tenu: int, port_libre: int) -> None:
    """Un audit déclare parfois trois URL : une seule tenue suffit à démentir le démontage."""
    verdict = instance.verifier_demontage(
        {
            "FORGE_TESTS_BASE_URL": f"http://127.0.0.1:{port_libre}",
            "FORGE_TESTS_API_URL": f"http://127.0.0.1:{port_tenu}",
        }
    )

    assert verdict["verdict"] == "encore_tenu"
    assert len(verdict["ports"]) == 2


# --- Ce que le rapport dit, et ce que la commande rend ------------------------------------------


def test_la_consigne_de_l_audit_NOMME_la_verification() -> None:
    """Une vérification que la consigne ne nomme pas est une vérification que personne ne joue."""
    cycle = instance.cycle_de_vie(
        {
            "FORGE_TESTS_BASE_URL": "http://127.0.0.1:8091",
            "FORGE_TESTS_INSTANCE_MONTER": "uv run uvicorn app:api",
            "FORGE_TESTS_INSTANCE_DEMONTER": "taskkill /IM uvicorn.exe",
        }
    )

    assert cycle["etat"] == "laissee_debout"
    assert "--verifier-demontage" in cycle["consigne"]


def test_la_limite_du_MONTAGE_est_declaree() -> None:
    """L'autre moitié de l'item : la forge ne vérifie pas ce que MONTER transmet à l'instance."""
    declare = " ".join(instance.NON_JUGE)

    assert "FORGE_TESTS_INSTANCE_MONTER" in declare
    assert "secrets de session" in declare
    assert "500" in declare


def test_les_limites_de_ce_module_entrent_AU_REGISTRE_de_dette() -> None:
    """Constaté en livrant cet item : `instance.NON_JUGE` est un TUPLE, et le collecteur du
    registre ne lisait que les LISTES. Les limites de ce module n'entraient donc au registre
    d'aucun domaine — huitième occurrence du patron « un contrôle qui itère sur une liste ne
    voit jamais ce qui n'y est pas », et « une dette qui n'entre pas au registre est de la
    prose » est le commentaire du collecteur lui-même.
    """
    from forge_tests.dette import collecter

    enonces = {entree["enonce"] for entree in collecter()}

    assert any("verifier_demontage" in e for e in enonces), (
        "la limite de la sonde de port doit etre opposable, pas seulement ecrite")
    assert any("FORGE_TESTS_INSTANCE_MONTER" in e for e in enonces)


@pytest.mark.parametrize(
    ("env", "code_attendu"),
    [({"FORGE_TESTS_BASE_URL": None}, 1), ({}, 3)],
)
def test_la_commande_rend_un_code_qui_DISTINGUE_les_trois_issues(
    env: dict, code_attendu: int, port_tenu: int
) -> None:
    """Un code unique ferait d'un « rien à vérifier » un « tout va bien »."""
    import os

    environnement = {
        k: v for k, v in os.environ.items() if not k.startswith("FORGE_TESTS_")
    }
    if "FORGE_TESTS_BASE_URL" in env:
        environnement["FORGE_TESTS_BASE_URL"] = f"http://127.0.0.1:{port_tenu}"
    environnement["PYTHONUTF8"] = "1"

    joue = subprocess.run(
        [sys.executable, "-m", "forge_tests.instance", "--verifier-demontage"],
        cwd=RACINE, env=environnement, capture_output=True, text=True, timeout=120,
    )

    assert joue.returncode == code_attendu, f"{joue.stdout}\n{joue.stderr}"


def test_la_commande_sans_argument_explique_et_ne_fait_RIEN() -> None:
    """Un outil dont l'appel nu agit est un outil qu'on appelle par accident (leçon TF-0602)."""
    import os

    joue = subprocess.run(
        [sys.executable, "-m", "forge_tests.instance"],
        cwd=RACINE, env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True, text=True, timeout=120,
    )

    assert joue.returncode == 0
    assert "--verifier-demontage" in joue.stdout
