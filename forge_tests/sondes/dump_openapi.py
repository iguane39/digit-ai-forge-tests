"""Extrait le schéma OpenAPI que l application produit ELLE-MÊME.

Règle R3 — on s appuie sur la source qui fait foi. Les regex sur les décorateurs devinaient
la surface ; le schéma la déclare : chemins, méthodes, codes, paramètres, corps de requête.
C est aussi ce dont le générateur a besoin pour fabriquer un appel valide.

Exécuté dans l interpréteur du projet analysé, en lecture seule, sans rien écrire chez lui.

Même convention d application que `sonde_api` : `app.main:app` par défaut, sinon la désignation
`FORGE_TESTS_APP="module:attribut"`. L attribut peut être une FABRIQUE — elle est alors appelée
sans argument pour obtenir l application dont on lit le schéma.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

DESIGNATION_PAR_DEFAUT = "app.main:app"


def _application(destination: Path):  # noqa: ANN202
    """Application désignée, ou None après avoir écrit le motif dans `destination`."""
    designation = (os.environ.get("FORGE_TESTS_APP") or "").strip() or DESIGNATION_PAR_DEFAUT
    nom_module, _, attribut = designation.partition(":")
    try:
        module = importlib.import_module(nom_module)
    except Exception as exc:  # noqa: BLE001
        destination.write_text(json.dumps({"erreur": str(exc)}), encoding="utf-8")
        return None
    cible = getattr(module, attribut or "app", None)
    if cible is not None and not hasattr(cible, "openapi") and callable(cible):
        try:
            cible = cible()
        except Exception as exc:  # noqa: BLE001
            destination.write_text(
                json.dumps({"erreur": f"fabrique {designation} : {exc}"}), encoding="utf-8"
            )
            return None
    if cible is None or not hasattr(cible, "openapi"):
        destination.write_text(
            json.dumps({"erreur": f"pas d application OpenAPI en {designation}"}), encoding="utf-8"
        )
        return None
    return cible


def main() -> int:
    destination = Path(sys.argv[1])
    application = _application(destination)
    if application is None:
        return 2
    destination.write_text(
        json.dumps(application.openapi(), ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
