"""TF-1792 — le parcours qualif multiplié par 4 états dérivait 10 728 cas, F1 et F2 en doublon.

Fait remonté par Produit-83 (lot 20261015b, RE-4, ledger seq 123), sur une instance peuplée de
13 000 établissements. Mesuré le 15/10/2026 sur le cahier fonctionnel livré au produit : un
sous-chapitre par fiche (« parcours /fiche/11111111100011 », « parcours /fiche/22222222200022 »…),
chacun avec ses 4 états ; et chaque élément du pan qualif dérivé DEUX fois, une fois en F1
(parcours) et une fois en F2 (écrans), sous le même numéro stable : 5 324 références F1 et
5 472 références F2 pour la même surface.

Deux corrections :
  1. une adresse d instance (`/fiche/<identifiant>`) se range sous son GABARIT
     (`/fiche/{id}`) ; ses cas se dérivent une fois, portés par le premier élément ;
  2. le pan qualif PARTAGE ses éléments entre ses deux chapitres : la route et la porte
     d entrée font le parcours (F1), les effets, la console et les marqueurs font l écran (F2).
"""

from __future__ import annotations

from forge_tests.adaptateurs import REGISTRE
from forge_tests.livrables import cahiers, surface


def _rapport(elements: list[str]) -> dict:
    return {
        "couverture_par_pan": {
            "qualif": {"elements_exerces": elements, "elements_non_exerces": []},
        },
        "findings": [],
    }


ELEMENTS = [
    "qualif:route:/carte",
    "qualif:effet:/carte:0:button",
    "qualif:route:/fiche/11111111100011",
    "qualif:route:/fiche/22222222200022",
    "qualif:route:/fiche/33333333300033",
    "qualif:effet:/fiche/11111111100011:0:a",
    "qualif:effet:/fiche/22222222200022:0:a",
]


def _chapitres() -> dict[str, dict]:
    return {
        c["code"]: cahiers.cas_du_chapitre(c, None)
        for c in surface.repartir(_rapport(ELEMENTS), REGISTRE)
        if c["code"] in ("F1", "F2")
    }


def _elements_avec_cas(chapitre: dict) -> set[str]:
    return {
        e["element"]["id"] for s in chapitre["sous_chapitres"] for e in s["entrees"] if e["cas"]
    }


def test_un_element_qualif_ne_releve_que_d_un_chapitre() -> None:
    chapitres = _chapitres()
    f1 = _elements_avec_cas(chapitres["F1"])
    f2 = _elements_avec_cas(chapitres["F2"])
    assert not (f1 & f2)
    assert all(":route:" in e for e in f1)
    assert all(":effet:" in e for e in f2)
    refs_f1 = {u["ref"].split("-", 1)[1] for s in chapitres["F1"]["sous_chapitres"]
               for e in s["entrees"] for u in e["cas"]}
    refs_f2 = {u["ref"].split("-", 1)[1] for s in chapitres["F2"]["sous_chapitres"]
               for e in s["entrees"] for u in e["cas"]}
    assert not (refs_f1 & refs_f2)


def test_les_fiches_d_instance_se_rangent_sous_leur_gabarit_et_derivent_une_fois() -> None:
    chapitres = _chapitres()
    libelles = {s["libelle"] for s in chapitres["F1"]["sous_chapitres"]}
    assert "parcours /fiche/{id}" in libelles
    assert not [lib for lib in libelles if "11111111100011" in lib]
    # 2 gabarits de route (/carte, /fiche/{id}) × 4 états, jamais 4 routes × 4 états.
    assert chapitres["F1"]["total_cas"] == 2 * 4
    assert chapitres["F2"]["total_cas"] == 2 * 4
    fiche = next(s for s in chapitres["F1"]["sous_chapitres"]
                 if s["libelle"] == "parcours /fiche/{id}")
    portees = [e for e in fiche["entrees"] if not e["cas"]]
    assert len(portees) == 2
    assert all(e.get("porte_par") == "qualif:route:/fiche/11111111100011" for e in portees)


def test_une_adresse_sans_identifiant_garde_son_nom() -> None:
    assert surface.gabarit_adresse("/aide/carte") == "/aide/carte"
    assert surface.gabarit_adresse("/donnees-personnelles") == "/donnees-personnelles"
    assert surface.gabarit_adresse("/fiche/11111111100011") == "/fiche/{id}"
    assert (
        surface.gabarit_adresse("/compte/3f2b9c1e-8a4d-4f6b-9c2e-1a2b3c4d5e6f/profil")
        == "/compte/{id}/profil"
    )
