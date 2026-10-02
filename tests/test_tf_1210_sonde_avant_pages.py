"""TF-1210 — la forge ne sondait pas l'adresse de l'instance SERVIE A DISTANCE avant de lancer
les pages, et son motif d'echec ne le disait pas.

Mesure du 02/10/2026, confirmee en lisant `forge_tests/adaptateurs/_parcours.py` et
`forge_tests/instance.py` : `_parcourir_distant` navigue directement vers chaque route des que
FORGE_TESTS_BASE_URL est declaree, sans sonder l'adresse au prealable. Une instance non
demarree avant le controle fait donc echouer CHAQUE route avec le meme motif generique
(« navigation impossible : Error ») qui ne dit ni qu'il fallait demarrer l'instance, ni quelle
commande jouer — un audit complet perdu (quatre domaines mesures a zero sur une instance par
ailleurs saine, cout mesure au TODO de l'item).

Correction : sonder le port de l'adresse de base AVANT la premiere route ; si le port est
confirme LIBRE (et seulement dans ce cas — un port INDETERMINABLE ne bloque pas, meme doctrine
que `precondition_absente` du pan `qualif` : la garde ne se deduit jamais d'une ignorance),
refuser tot en citant la commande declaree dans FORGE_TESTS_INSTANCE_MONTER.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from forge_tests.adaptateurs._parcours import _motif_instance_injoignable, _parcourir_distant
from forge_tests.instance import CHAMP_MONTER


def _port_libre() -> int:
    """Un port garanti LIBRE : lie puis immediatement refermee."""
    with socket.socket() as prise:
        prise.bind(("127.0.0.1", 0))
        return int(prise.getsockname()[1])


def test_motif_cite_la_commande_de_montage_declaree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CHAMP_MONTER, "node e2e/preparer.mjs")
    motif = _motif_instance_injoignable("http://127.0.0.1:9", "pan")
    assert "node e2e/preparer.mjs" in motif
    assert CHAMP_MONTER in motif


def test_motif_sans_commande_declaree_le_dit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CHAMP_MONTER, raising=False)
    motif = _motif_instance_injoignable("http://127.0.0.1:9", "pan")
    assert "aucune commande de demarrage declaree" in motif
    assert CHAMP_MONTER in motif


def test_instance_non_demarree_refuse_tot_sans_naviguer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Le cas mesure : une instance non demarree est detectee AVANT la premiere route, et
    `action` (donc le navigateur) n'est jamais sollicite — plus de quatre routes perdues pour un
    motif illisible, un seul motif exploitable pour l'instance entiere."""
    monkeypatch.setenv(CHAMP_MONTER, "node e2e/preparer.mjs")
    port = _port_libre()
    appels: list[str] = []

    def action(page: object, route: str) -> tuple[object, str | None]:
        appels.append(route)
        return {}, None

    resultats, motifs = _parcourir_distant(
        f"http://127.0.0.1:{port}", ["/", "/a", "/b", "/c"], action, tmp_path, "pan"
    )

    assert resultats == {}
    assert not appels, "action ne doit jamais etre invoquee : le port est sonde AVANT toute route"
    assert len(motifs) == 1, "un seul motif pour l'instance entiere, pas un par route perdue"
    assert "node e2e/preparer.mjs" in motifs[0]
    assert CHAMP_MONTER in motifs[0]
