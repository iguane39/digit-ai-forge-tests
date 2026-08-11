"""Générateur de cas — P4, capacité 2 du contrat d adaptateur.

Dérive des cas depuis les éléments de surface NON EXERCÉS, par risque décroissant, en
s appuyant sur le schéma OpenAPI que l application déclare (règle R3 : la source qui fait foi,
pas des regex sur les décorateurs).

Loi du générateur : **il ne produit que ce qu il sait construire honnêtement.**
Un cas dont la précondition n est pas dérivable du schéma (valeur métier invalide, état
conflictuel, type de média attendu) n est PAS émis — il est déclaré non générable. Émettre un
cas qui échoue pour la mauvaise raison est pire que ne rien émettre : cela invite à assouplir
l assertion pour le faire passer, c est-à-dire le test-fitting que le garde-fou G-2 interdit.

Garde-fou G-1 : rien n est écrit dans le projet analysé. Les cas sont déposés dans un dossier
de PROPOSITION désigné par l opérateur.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Pan que ce générateur sait produire. Lu par `forge_tests.actions` pour décider qu un élément
# non exercé de ce pan relève d `auto_ia` : la source qui fait foi dit comment l atteindre.
# Déclaré ICI plutôt que recopié là-bas — une liste de pans générables tenue à la main aurait
# divergé au premier générateur ajouté.
PAN = "api"

NON_JUGE = [
    "generateur : les codes exigeant une valeur METIER invalide (400), un etat conflictuel "
    "(409) ou un type de media particulier (415) ne sont pas generables depuis le seul schema "
    "— ils sont declares NON GENERABLES, jamais emis a l aveugle",
    "generateur : pans API et Data generes ; Front, Batch et Fichiers ne le sont pas — "
    "leurs cas exigent un scenario, pas une seule requete",
    "generateur : le corps synthetise ne porte que les champs REQUIS ; un endpoint dont le "
    "comportement depend d un champ optionnel ne sera pas exerce sur ce chemin",
]

_CODE = re.compile(r"^code:(?P<methode>[A-Z]+) (?P<chemin>\S+)=(?P<code>\d{3})$")
# Codes dont la precondition n est pas derivable du schema OpenAPI.
NON_GENERABLES = {400, 403, 409, 415, 429, 500}

ENTETE = '''"""Cas générés par Forge Tests — À RELIRE AVANT USAGE.

Chaque cas cible un élément de surface INVENTORIÉ ET NON EXERCÉ, cité avec son score de risque.
Le corps de requête est synthétisé depuis le schéma OpenAPI déclaré par l application.
Un cas généré est une PROPOSITION : il porte le comportement que la source DÉCLARE.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import JETON, app

AUTH = {"Authorization": f"Bearer {JETON}"}
INEXISTANT = 999999


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
'''

_CAS = '''

# {id}  (risque {risque}){prealable_note}
def test_genere_{nom}(client: TestClient) -> None:
{corps}
'''


def _exemple(schema: dict, composants: dict, profondeur: int = 0) -> object:
    """Instance minimale satisfaisant le schéma (types et champs requis seulement)."""
    if profondeur > 4:
        return None
    if "$ref" in schema:
        nom = schema["$ref"].rsplit("/", 1)[1]
        return _exemple(composants.get(nom, {}), composants, profondeur + 1)
    type_ = schema.get("type")
    if type_ == "object" or "properties" in schema:
        # Champs REQUIS seulement : un optionnel rempli au hasard viole souvent un invariant
        # metier que le schema ne declare pas (liste fermee, format), et produit un faux positif.
        requis = schema.get("required", [])
        return {
            cle: _exemple(schema["properties"][cle], composants, profondeur + 1)
            for cle in requis
            if cle in schema.get("properties", {})
        }
    if type_ == "array":
        return []
    if type_ == "integer":
        return 1
    if type_ == "number":
        return 1.0
    if type_ == "boolean":
        return True
    if type_ == "string":
        return "x"
    for cle in ("anyOf", "oneOf", "allOf"):
        if cle in schema and schema[cle]:
            return _exemple(schema[cle][0], composants, profondeur + 1)
    return "x"


def _corps_json(operation: dict, composants: dict) -> dict | None:
    contenu = (operation.get("requestBody") or {}).get("content") or {}
    schema = (contenu.get("application/json") or {}).get("schema")
    if schema is None:
        return None
    exemple = _exemple(schema, composants)
    return exemple if isinstance(exemple, dict) else None


def _champs_requis(operation: dict, composants: dict) -> list[str]:
    contenu = (operation.get("requestBody") or {}).get("content") or {}
    schema = (contenu.get("application/json") or {}).get("schema") or {}
    if "$ref" in schema:
        schema = composants.get(schema["$ref"].rsplit("/", 1)[1], {})
    return list(schema.get("required", []))


def _exige_authentification(operation: dict, schema: dict) -> bool:
    """Vrai si l operation declare une exigence de securite. Sans declaration, on ne devine pas."""
    return bool(operation.get("security") or schema.get("security"))


def _parent(chemin: str) -> str | None:
    """Chemin de la collection parente d une ressource paramétrée."""
    if not chemin.endswith("}"):
        return None
    return chemin.rsplit("/", 1)[0] or None


def _appel(methode: str, chemin: str, corps: dict | None, auth: bool, variable: str) -> str:
    morceaux = [variable]
    if corps is not None:
        morceaux.append(f"json={json.dumps(corps, ensure_ascii=False)}")
    if auth:
        morceaux.append("headers=AUTH")
    arguments = ", ".join(morceaux)
    return f"client.{methode}({arguments})"


def _nom(methode: str, chemin: str, code: int) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{methode} {chemin} {code}".lower()).strip("_")


def construire(rapport: dict, schema: dict, limite: int = 30) -> tuple[str, list[dict]]:
    """Renvoie (contenu du fichier, liste des elements declares NON GENERABLES)."""
    chemins = schema.get("paths", {})
    composants = (schema.get("components") or {}).get("schemas", {})
    cas: list[str] = []
    refuses: list[dict] = []
    vus: set[str] = set()

    for finding in rapport["findings"]:
        if finding["classe"] != "element-non-exerce":
            continue
        trouve = _CODE.match(finding["id"])
        if not trouve:
            continue
        methode = trouve["methode"].lower()
        code = int(trouve["code"])
        # Retrouver le gabarit reel du schema (l identifiant porte {} normalise).
        gabarit = next(
            (
                c
                for c in chemins
                if re.sub(r"\{[^}]*\}", "{}", c) == trouve["chemin"] and methode in chemins[c]
            ),
            None,
        )
        if gabarit is None:
            continue
        if code in NON_GENERABLES:
            refuses.append({"id": finding["id"], "motif": f"code {code} non derivable du schema"})
            continue

        operation = chemins[gabarit][methode]
        if "415" in (operation.get("responses") or {}):
            refuses.append(
                {
                    "id": finding["id"],
                    "motif": "endpoint a type de media contraint (415 declare) : non derivable",
                }
            )
            continue
        contenu = (operation.get("requestBody") or {}).get("content") or {}
        if contenu and "application/json" not in contenu:
            refuses.append(
                {"id": finding["id"],
                 "motif": "corps non JSON : type de media a fournir, non derivable"}
            )
            continue
        corps, requis = _corps_json(operation, composants), _champs_requis(operation, composants)
        if code == 422 and not requis:
            refuses.append(
                {"id": finding["id"], "motif": "422 non derivable : aucun champ requis a omettre"}
            )
            continue
        if code == 401 and not _exige_authentification(operation, schema):
            refuses.append(
                {"id": finding["id"],
                 "motif": "401 non derivable : aucune exigence de securite declaree"}
            )
            continue
        auth = code != 401
        parametre = "{" in gabarit
        nom = _nom(methode, gabarit, code)
        if nom in vus:
            continue
        vus.add(nom)

        lignes: list[str] = []
        note = ""
        if parametre and 200 <= code < 300:
            parent = _parent(gabarit)
            operation_parent = (chemins.get(parent) or {}).get("post") if parent else None
            if operation_parent is None:
                refuses.append(
                    {"id": finding["id"],
                     "motif": "ressource prealable non creable (pas de POST parent)"}
                )
                vus.discard(nom)
                continue
            corps_parent = _corps_json(operation_parent, composants)
            lignes.append(
                f"    prealable = {_appel('post', parent, corps_parent, True, json.dumps(parent))}"
            )
            lignes.append("    assert prealable.status_code < 300")
            lignes.append('    cible = f"' + parent + '/{prealable.json()[\'id\']}"')
            variable = "cible"
            note = "  [etat prealable cree]"
        elif parametre:
            lignes.append('    cible = f"' + gabarit.rsplit("/", 1)[0] + '/{INEXISTANT}"')
            variable = "cible"
        else:
            variable = json.dumps(gabarit)

        if code == 422 and corps is not None and corps:
            corps = {}  # champ requis manquant : 422 par validation de schema
        lignes.append(f"    reponse = {_appel(methode, gabarit, corps, auth, variable)}")
        lignes.append(f"    assert reponse.status_code == {code}")
        cas.append(
            _CAS.format(
                id=finding["id"],
                risque=finding["risque"],
                prealable_note=note,
                nom=nom,
                corps="\n".join(lignes),
            )
        )
        if len(cas) >= limite:
            break
    return (ENTETE + "".join(cas) if cas else ""), refuses


def ecrire(rapport: dict, destination: Path, schema: dict | None = None, limite: int = 30):
    """Dépose les cas générés dans un dossier de proposition. Jamais dans le projet analysé."""
    if schema is None:
        return None
    contenu, refuses = construire(rapport, schema, limite=limite)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "non-generables.json").write_text(
        json.dumps(refuses, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not contenu:
        return None
    cible = destination / "test_genere_api.py"
    cible.write_text(contenu, encoding="utf-8")
    return cible
