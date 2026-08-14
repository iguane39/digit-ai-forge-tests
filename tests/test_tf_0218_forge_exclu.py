"""TF-0218 (RT-4, lot COMPTA 20260814a) — le pan `interface` scannait `forge\\` du produit.

Fait mesure : la convention ETAPES-RUN du pilot archive les livrables du cycle N-1 sous
`forge\\etapes\\tests\\livrables\\` (dashboards HTML, cahiers de tests). Ce pan les inventoriait
au cycle N comme s ils etaient la surface du PRODUIT — 344 elements au cycle 2 dont 262 issus
des dashboards et cahiers archives, contre 82 elements produit au cycle 1.

Aucun faux echec, mais deux defauts : la mesure est POLLUEE, et elle est CROISSANTE a chaque
cycle — un produit dont pas une ligne de gabarit ne change voit sa surface grossir du seul fait
d avoir ete audite. C est le meme defaut que RT-9/RT-10 (`output\\`, `old\\`, `.oracles\\`,
ajoutes le matin meme), et le meme remede : `forge\\` est le dossier de RUN DU PILOT, jamais du
produit.

ROUGE implicite : avant le correctif, `test_les_livrables_archives_n_entrent_pas_a_l_inventaire`
comptait 1 + N elements au lieu de 1, et le second cycle en comptait davantage que le premier.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import interface

_GABARIT_PRODUIT = """<html><body>
  <form action="/ventiler"><button type="submit">Ventiler la facture</button></form>
</body></html>
"""

# Un dashboard de forge-tests : beaucoup d affordances, aucune ne relevant du produit.
_DASHBOARD_ARCHIVE = """<html><body>
  <a href="#pan-api">API</a>
  <a href="#pan-data">Data</a>
  <button onclick="trier()">Trier</button>
  <form action="/filtre"><button type="submit">Filtrer</button></form>
</body></html>
"""


def _produit(racine: Path) -> Path:
    """Un produit a racine plate avec UN seul gabarit : sa surface d interface vaut 2."""
    (racine / "app" / "templates").mkdir(parents=True)
    (racine / "app" / "templates" / "facture.html").write_text(
        _GABARIT_PRODUIT, encoding="utf-8"
    )
    return racine


def _archiver_un_cycle(racine: Path, cycle: int) -> None:
    """Ce que le PILOT depose apres un run — convention `references\\ETAPES-RUN.md`."""
    livrables = racine / "forge" / "etapes" / "tests" / "livrables"
    livrables.mkdir(parents=True, exist_ok=True)
    (livrables / f"dashboard-cycle-{cycle}.html").write_text(
        _DASHBOARD_ARCHIVE, encoding="utf-8"
    )
    (livrables / f"cahier-de-tests-cycle-{cycle}.html").write_text(
        _DASHBOARD_ARCHIVE, encoding="utf-8"
    )


def test_forge_est_exclu_au_meme_titre_que_les_autres_dossiers_de_run():
    """`forge\\` rejoint `output`, `old`, `.oracles` — memes causes, meme remede."""
    for dossier in ("forge", "output", "old", "Old", ".oracles", "node_modules", ".venv"):
        assert dossier in interface._EXCLUS, f"{dossier} devrait etre exclu du perimetre"


def test_les_livrables_archives_n_entrent_pas_a_l_inventaire(tmp_path):
    cible = _produit(tmp_path)
    _archiver_un_cycle(cible, cycle=1)

    elements = interface.inventaire(cible)

    # ROUGE implicite : 12 elements — 2 du produit et 10 des deux archives (mesure sur ce
    # meme montage, `forge` retire de `_EXCLUS`).
    assert len(elements) == 2, [e.id for e in elements]
    assert not any("forge/" in e.id for e in elements), [e.id for e in elements]


def test_la_mesure_ne_croit_plus_a_chaque_cycle(tmp_path):
    """Le defaut le plus couteux de RT-4 : la pollution GRANDIT a chaque audit."""
    cible = _produit(tmp_path)

    _archiver_un_cycle(cible, cycle=1)
    cycle_1 = interface.analyser(cible)
    _archiver_un_cycle(cible, cycle=2)
    cycle_2 = interface.analyser(cible)

    # ROUGE implicite : 12 -> 22 sur ce montage, 82 -> 344 sur le produit reel — sans qu une
    # ligne de gabarit change dans un cas comme dans l autre.
    assert cycle_1.surface["inventorie"] == cycle_2.surface["inventorie"]
    assert cycle_1.surface["ratio"] == cycle_2.surface["ratio"]


def test_un_dossier_forge_ne_fabrique_pas_de_faux_defaut(tmp_path):
    """Les archives portent des `<a href="#…">` : autant de faux « affordances inertes »."""
    cible = _produit(tmp_path)
    _archiver_un_cycle(cible, cycle=1)

    sortie = interface.analyser(cible)

    assert sortie.verdict == "PASS"
    assert not sortie.findings, [f.id for f in sortie.findings]


def test_le_produit_reste_mesure_lui(tmp_path):
    """Garde-fou du remede : exclure `forge\\` ne doit rien retirer au produit."""
    cible = _produit(tmp_path)
    _archiver_un_cycle(cible, cycle=1)

    sortie = interface.analyser(cible)

    assert sortie.surface["inventorie"] == 2
    assert all("facture.html" in e for e in sortie.surface["elements_exerces"])
