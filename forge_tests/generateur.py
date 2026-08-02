"""Générateur de cas — P4, capacité 2 du contrat d adaptateur.

Dérive des cas de test depuis les éléments de surface NON EXERCÉS, par risque décroissant.
Le sens de la génération est inversé par rapport au biais de disponibilité : on ne part pas
de ce que l agent a sous les yeux, on part de l inventaire mécanique de ce qui n est pas
couvert.

Garde-fou G-1 : rien n est écrit dans le projet analysé. Les cas sont déposés dans un dossier
de PROPOSITION désigné par l opérateur, à relire puis à porter sur une branche dédiée.
"""

from __future__ import annotations

import re
from pathlib import Path

NON_JUGE = [
    "generateur : precision MESUREE a 0 % sur le banc (recette/precision_generateur.py) — les "
    "cas produits echouent aussi sur du code correct. NON UTILISABLE en l etat",
    "generateur : ne synthetise pas les preconditions (ressource existante, corps valide, "
    "en-tete de type de media) ni les parametres qui declenchent un code d erreur",
    "generateur : couvre le seul pan API ; les autres pans ne sont pas generes",
]

_CODE = re.compile(r"^code:(?P<methode>[A-Z]+) (?P<chemin>\S+)=(?P<code>\d{3})$")
_ENDPOINT = re.compile(r"^endpoint:(?P<methode>[A-Z]+) (?P<chemin>\S+)$")

ENTETE = '''"""Cas générés par Forge Tests — À RELIRE AVANT USAGE.

Chaque cas cible un élément de surface INVENTORIÉ ET NON EXERCÉ, cité en commentaire avec son
score de risque. Un cas généré est une PROPOSITION : il porte le comportement attendu tel que
la source le déclare, pas tel que le code se comporte. Un cas qui échoue dès sa première
exécution signale un écart entre la déclaration et le code — c est son intérêt principal.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import JETON, app

AUTH = {"Authorization": f"Bearer {JETON}"}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
'''

_CORPS = '''

# {id}  (risque {risque})
def test_genere_{nom}(client: TestClient) -> None:
    reponse = client.{methode}({appel})
    assert reponse.status_code == {code}
'''


def _nom_de_test(methode: str, chemin: str, code: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", f"{methode} {chemin} {code}".lower()).strip("_")
    return base


def _appel(methode: str, chemin: str, code: int) -> str:
    """Construit l appel client. Un chemin paramétré reçoit une valeur inexistante pour 404."""
    concret = chemin.replace("{}", "999999")
    entetes = "headers=AUTH" if code != 401 else ""
    corps = ""
    if methode in ("post", "patch", "put"):
        corps = "json={}"
    morceaux = [f'"{concret}"']
    if corps:
        morceaux.append(corps)
    if entetes:
        morceaux.append(entetes)
    return ", ".join(morceaux)


def generer_api(rapport: dict, limite: int = 20) -> str:
    """Produit le contenu d un fichier de tests pour les codes API non exercés, par risque."""
    cas: list[str] = []
    vus: set[str] = set()
    for finding in rapport["findings"]:
        if finding["classe"] != "element-non-exerce":
            continue
        trouve = _CODE.match(finding["id"]) or _ENDPOINT.match(finding["id"])
        if not trouve:
            continue
        donnees = trouve.groupdict()
        code = int(donnees.get("code") or 200)
        methode = donnees["methode"].lower()
        nom = _nom_de_test(methode, donnees["chemin"], str(code))
        if nom in vus:
            continue
        vus.add(nom)
        cas.append(
            _CORPS.format(
                id=finding["id"],
                risque=finding["risque"],
                nom=nom,
                methode=methode,
                appel=_appel(methode, donnees["chemin"], code),
                code=code,
            )
        )
        if len(cas) >= limite:
            break
    return ENTETE + "".join(cas) if cas else ""


def ecrire(rapport: dict, destination: Path, limite: int = 20) -> Path | None:
    """Dépose les cas générés dans un dossier de proposition. Jamais dans le projet analysé."""
    contenu = generer_api(rapport, limite=limite)
    if not contenu:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    cible = destination / "test_genere_api.py"
    cible.write_text(contenu, encoding="utf-8")
    return cible
