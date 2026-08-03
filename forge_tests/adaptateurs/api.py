"""Adaptateur API (FastAPI) — endpoints x methodes x codes de retour depuis le code source."""

from __future__ import annotations

import re
from pathlib import Path

from forge_tests.execution import codes_emis, schema_openapi
from forge_tests.invariants import NON_JUGE as NON_JUGE_INV
from forge_tests.invariants import codes_par_fonction, handlers
from forge_tests.noyau import Element, Finding, SortieAdaptateur, evaluer_surface
from forge_tests.risque import coter

NOM, PAN, SEUIL = "api-fastapi", "api", 1.0
_ROUTE = re.compile(r'@app\.(get|post|patch|put|delete)\(\s*"([^"]+)"(.*?)\)\s*\n', re.DOTALL)
_CODE = re.compile(r"(\d{3})\s*:")
_APPEL = re.compile(r'client\.(get|post|patch|put|delete)\(\s*f?"([^"]+)"')
_STATUT = re.compile(r"status_code\s*==\s*(\d{3})")

NON_JUGE = [
    "api : un code emis pendant la suite est repute couvert ; la sonde ne verifie pas qu une "
    "ASSERTION porte sur lui — c est le role du second contre-oracle",
]


def _norm(chemin: str) -> str:
    chemin = chemin.split("?")[0]
    chemin = re.sub(r"\{[^}]*\}", "{}", chemin)
    return re.sub(r"/\d+", "/{}", chemin)


def _codes_declares(cible: Path) -> set[str]:
    """Codes ecrits A LA MAIN dans `responses=`, par opposition a ceux ajoutes par le cadre."""
    src = cible / "backend" / "app" / "main.py"
    if not src.exists():
        return set()
    declares: set[str] = set()
    for methode, chemin, reste in _ROUTE.findall(src.read_text(encoding="utf-8")):
        for code in _CODE.findall(reste):
            declares.add(f"{methode.upper()} {_norm(chemin)}={code}")
    return declares


def _inventaire_openapi(cible: Path) -> list[Element]:
    """Surface lue dans le schema que l application DECLARE — source primaire du CDC."""
    schema = schema_openapi(str(cible))
    if not schema:
        return []
    elements: list[Element] = []
    source = str(cible / "backend" / "app" / "main.py")
    for chemin, operations in schema.get("paths", {}).items():
        c = _norm(chemin)
        for methode, operation in operations.items():
            if methode not in ("get", "post", "put", "patch", "delete"):
                continue
            m = methode.upper()
            elements.append(Element(f"endpoint:{m} {c}", PAN, f"{m} {c}", source))
            declares_source = _codes_declares(cible)
            for code in operation.get("responses", {}):
                # FastAPI ajoute un 422 a toute route validee, sans que personne l ait declare.
                # Sur un GET sans corps il est inatteignable : l exiger accuse la suite d un
                # trou qui n existe pas. Retenu SEULEMENT s il est declare a la main.
                if code == "422" and f"{m} {c}=422" not in declares_source:
                    continue
                elements.append(
                    Element(f"code:{m} {c}={code}", PAN, f"{m} {c} -> {code}", source)
                )
    return elements


def inventaire(cible: Path) -> list[Element]:
    par_schema = _inventaire_openapi(cible)
    if par_schema:
        return par_schema
    src = cible / "backend" / "app" / "main.py"
    if not src.exists():
        return []
    texte = src.read_text(encoding="utf-8")
    elements: list[Element] = []
    for methode, chemin, reste in _ROUTE.findall(texte):
        m, c = methode.upper(), _norm(chemin)
        elements.append(Element(f"endpoint:{m} {c}", PAN, f"{m} {c}", str(src)))
        for code in dict.fromkeys(_CODE.findall(reste)):
            elements.append(Element(f"code:{m} {c}={code}", PAN, f"{m} {c} -> {code}", str(src)))
    return elements


def exerces(cible: Path) -> set[str] | None:
    """Couples et codes REELLEMENT emis pendant la suite (sonde ASGI), jamais deduits du texte.

    None = couverture NON MESURABLE (suite non executee). A ne pas confondre avec un ensemble
    vide, qui signifierait « rien n est couvert » — deux verdicts opposes.
    """
    releve = codes_emis(cible)
    if releve is None:
        return None
    couvert: set[str] = set()
    for entree in releve:
        methode = entree["methode"].upper()
        gabarit = _norm(entree["gabarit"])
        couvert.add(f"endpoint:{methode} {gabarit}")
        couvert.add(f"code:{methode} {gabarit}={entree['code']}")
    return couvert


def analyser(cible: Path) -> SortieAdaptateur:
    inv = inventaire(cible)
    if exerces(cible) is None:
        # « 0 % couvert » et « couverture non mesurable » sont deux verdicts OPPOSES. Les
        # confondre accuse a tort une suite qu on n a simplement pas pu executer.
        endpoints = sum(1 for e in inv if e.id.startswith("endpoint:"))
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"api : {len(inv)} elements INVENTORIES ({endpoints} operations, "
                f"{len(inv) - endpoints} codes) mais couverture non mesurable — "
                "suite non executee sous sonde",
            ],
        )
    couvert = exerces(cible)
    if couvert is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"api : {len(inv)} elements INVENTORIES (OpenAPI) mais couverture non mesurable — "
                "la suite du projet n a pas pu etre executee sous sonde",
            ],
        )
    sortie = evaluer_surface(NOM, PAN, str(cible), inv, couvert, SEUIL, NON_JUGE)
    # Un code EMIS pendant la suite mais absent de `responses=` est une divergence entre ce que
    # la source declare et ce que le code fait. Ni un trou de couverture, ni un silence : un ecart.
    # Un code d invariant metier DECLARE mais qu aucune garde du code ne peut produire est une
    # divergence : la source promet une erreur que le comportement ne sait plus lever.
    source = cible / "backend" / "app" / "main.py"
    par_fonction = codes_par_fonction(source)
    table = handlers(source)
    for element in inv:
        if not element.id.startswith("code:"):
            continue
        signature, code = element.id[len("code:") :].rsplit("=", 1)
        methode, chemin = signature.split(" ", 1)
        code = int(code)
        fonction = table.get((methode, chemin))
        gardes = par_fonction.get(fonction or "", set())
        if code in (400, 409) and code not in gardes:
            sortie.findings.append(
                Finding(
                    id=f"divergence:{element.id}",
                    classe="divergence",
                    localisation=str(source),
                    message=(
                        f"code {code} declare pour {signature} mais aucune garde de "
                        f"{fonction or '?'}() ne le leve"
                    ),
                    risque=coter(PAN, element.id, str(source)),
                )
            )
            sortie.verdict = "FAIL"

    declares = {e.id for e in inv if e.id.startswith("code:")}
    for identifiant in sorted(couvert - declares):
        if not identifiant.startswith("code:"):
            continue
        sortie.findings.append(
            Finding(
                id=identifiant,
                classe="divergence",
                localisation=str(cible / "backend" / "app" / "main.py"),
                message="code emis par l application mais absent de sa declaration responses=",
                severite="signale",
                risque=coter(PAN, identifiant, str(cible / "backend" / "app" / "main.py")),
            )
        )
    return sortie
