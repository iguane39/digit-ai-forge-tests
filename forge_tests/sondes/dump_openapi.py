"""Extrait le schéma OpenAPI que l application produit ELLE-MÊME.

Règle R3 — on s appuie sur la source qui fait foi. Les regex sur les décorateurs devinaient
la surface ; le schéma la déclare : chemins, méthodes, codes, paramètres, corps de requête.
C est aussi ce dont le générateur a besoin pour fabriquer un appel valide.

Exécuté dans l interpréteur du projet analysé, en lecture seule, sans rien écrire chez lui.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    destination = Path(sys.argv[1])
    try:
        import app.main as principal
    except Exception as exc:  # noqa: BLE001
        destination.write_text(json.dumps({"erreur": str(exc)}), encoding="utf-8")
        return 2
    application = getattr(principal, "app", None)
    if application is None or not hasattr(application, "openapi"):
        destination.write_text(json.dumps({"erreur": "pas d application OpenAPI"}), encoding="utf-8")
        return 2
    destination.write_text(
        json.dumps(application.openapi(), ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
