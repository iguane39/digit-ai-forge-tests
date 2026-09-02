"""TF-0728 — un couple opération × code exercé par la suite n'est pas une divergence statique.

LE FAIT, mesuré sur une campagne v0.4.0 du 31/08/2026 (lot Produit-12). Le contrôle statique
des codes déclarés publiait **quatre divergences**, toutes sur des codes 400 neufs — et les
quatre couples opération × code étaient **exercés dynamiquement par le pan `api` de la MÊME
campagne**, qui rendait par ailleurs 483/483. Le rapport se contredisait donc lui-même d'une
section à l'autre : la lecture statique disait « aucune garde ne lève ce code », la mesure
dynamique disait « l'application vient de l'émettre ». Coût : **4 faux écarts à analyser à la
main par campagne**.

QUI PLIE, ET CE N'EST PAS SYMÉTRIQUE. La mesure dynamique est un FAIT constaté — la sonde a vu
la réponse partir. L'analyse statique est une LECTURE, dont les limites sont déjà déclarées
(RT-9). Quand les deux se contredisent, c'est la lecture qui plie.

FIXTURE À DOUBLE SENS, aux chiffres exacts du lot :

  * VERT — 4 divergences statiques dont 4 exercées → **0 écart publié, 4 confirmations** ;
  * ROUGE — une divergence NON exercée **reste un écart**.

Le silence aurait été le mauvais remède : il aurait fait disparaître du rapport quatre codes
dont on sait désormais quelque chose de plus, pas de moins. Ils se publient en « confirmé
dynamiquement », nommés couple par couple.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import classes
from forge_tests.adaptateurs.api import _divergences_gardes
from forge_tests.noyau import Element

#: Les quatre codes 400 neufs des lots A/B, tels que le rapport du 31/08 les portait.
_QUATRE = (
    ("POST", "/api/v1/lots", 400),
    ("PATCH", "/api/v1/lots/{lot_id}", 400),
    ("POST", "/api/v1/lots/{lot_id}/valider", 400),
    ("POST", "/api/v1/lots/{lot_id}/lignes", 400),
)


def _inventaire() -> list[Element]:
    return [
        Element(
            id=f"code:{methode} {chemin}={code}",
            pan="api",
            libelle=f"{methode} {chemin} -> {code}",
            source="app/api/routes_lots.py",
        )
        for methode, chemin, code in _QUATRE
    ]


def _table() -> dict[tuple[str, str], str]:
    """Chaque route a bien un handler RÉSOLU — sinon le cas dégraderait en `non_juge` (TF-0135)
    et ne testerait plus le croisement, mais la résolution."""
    return {(m, c): f"handler_{i}" for i, (m, c, _) in enumerate(_QUATRE)}


#: Aucune garde statique ne lève ces codes : c'est exactement l'état qui produisait 4 écarts.
_SANS_GARDE: dict[str, set[int]] = {f"handler_{i}": set() for i in range(len(_QUATRE))}

_SOURCE = Path("app/main.py")


def test_vert_quatre_divergences_dont_quatre_exercees_ne_publient_aucun_ecart() -> None:
    """Le chiffre du lot, tenu à l'identique : 4 statiques × 4 exercées = 0 écart, 4 confirmés."""
    exerces = {e.id for e in _inventaire()}  # le pan api les a toutes vues passer (483/483)
    findings, non_juge, confirmes = _divergences_gardes(
        _inventaire(), _table(), _SANS_GARDE, _SOURCE, exerces
    )

    assert findings == [], "un couple exercé dynamiquement n'est pas une divergence"
    assert len(confirmes) == 4
    # La confirmation se DIT, couple par couple : un silence aurait retiré du rapport quatre
    # codes dont on sait désormais quelque chose de plus.
    ligne = next(m for m in non_juge if "CONFIRME" in m)
    for methode, chemin, code in _QUATRE:
        assert f"{methode} {chemin} -> {code}" in ligne
    assert "TF-0728" in ligne


def test_sans_croisement_les_quatre_ecarts_reapparaissent() -> None:
    """La mesure du coût : sans la couverture dynamique, ce sont bien 4 faux écarts par campagne."""
    findings, _non_juge, confirmes = _divergences_gardes(
        _inventaire(), _table(), _SANS_GARDE, _SOURCE, set()
    )
    assert len(findings) == 4
    assert confirmes == []
    assert all(f.classe == classes.DIVERGENCE for f in findings)


def test_rouge_une_divergence_non_exercee_reste_un_ecart() -> None:
    """La contradiction disparaît, la divergence non : un code que RIEN n'a produit reste nommé."""
    inv = _inventaire()
    exerces = {e.id for e in inv[:3]}  # la quatrième n'a jamais été émise
    findings, non_juge, confirmes = _divergences_gardes(
        inv, _table(), _SANS_GARDE, _SOURCE, exerces
    )

    assert len(confirmes) == 3
    assert len(findings) == 1
    (seul,) = findings
    assert seul.id == f"divergence:{inv[3].id}"
    assert seul.classe == classes.DIVERGENCE
    assert "aucune garde" in seul.message
    # Les trois confirmations restent publiées à côté de l'écart : les deux verdicts coexistent.
    assert any("CONFIRME" in m for m in non_juge)


def test_un_code_leve_par_une_garde_n_a_jamais_ete_un_ecart() -> None:
    """Garde-fou de non-régression : le chemin nominal du contrôle ne bouge pas."""
    gardes = {f"handler_{i}": {400} for i in range(len(_QUATRE))}
    findings, _non_juge, confirmes = _divergences_gardes(
        _inventaire(), _table(), gardes, _SOURCE, set()
    )
    assert findings == [] and confirmes == []


def test_un_handler_non_resolu_reste_non_juge_meme_exerce() -> None:
    """TF-0135 prime : ce que l'analyseur n'a pas su lire ne devient pas une confirmation."""
    inv = _inventaire()
    findings, non_juge, confirmes = _divergences_gardes(
        inv, {}, {}, _SOURCE, {e.id for e in inv}
    )
    assert findings == [] and confirmes == []
    assert len(non_juge) == 4
    assert all("aucun handler n a pu etre resolu" in m for m in non_juge)
