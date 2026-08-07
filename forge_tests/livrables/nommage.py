"""Nommage et scellement des livrables — convention Digit-AI et preuve d intégrité.

Deux règles, et une seule raison derrière les deux : **un livrable dérivé doit être
reconnaissable comme dérivé.**

  - le NOM porte le produit, la nature du document et la date suivie d un indice de rang
    (`ASD Mail Manager 2 - Cahier de tests fonctionnels - 20260807a.md`). Deux audits du même
    jour ne s écrasent pas : le second prend l indice `b` ;
  - le SCEAU porte l empreinte des sources ET celle du corps. Le cahier est régénéré à chaque
    audit ; une édition manuelle entre deux audits serait donc écrasée sans bruit. Le sceau
    la trahit avant : `verifier_sceau` recalcule l empreinte du corps et la compare.

Le sceau n interdit rien — il rend l édition manuelle CONSTATABLE. C est la seule chose
qu un fichier posé dans un dossier puisse honnêtement garantir.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path

DEBUT_SCEAU = "<!-- SCEAU FORGE-TESTS"
FIN_SCEAU = "-->"
_LIGNE_CORPS = re.compile(r"^\s*sceau_corps\s*:\s*([0-9a-f]{64})\s*$", re.MULTILINE)

# Caractères qu un système de fichiers Windows refuse dans un nom. Le produit vient d un
# référentiel externe : il n est pas garanti d en être exempt.
_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def empreinte(contenu: str | bytes) -> str:
    """SHA-256 — la seule preuve recevable qu un texte n a pas bougé."""
    octets = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
    return hashlib.sha256(octets).hexdigest()


def empreinte_fichier(chemin: Path) -> str | None:
    return empreinte(chemin.read_bytes()) if chemin and chemin.is_file() else None


def serialiser_rapport(rapport: dict) -> str:
    """Forme CANONIQUE d un rapport — celle dont on prend l empreinte.

    Clés triées et indentation fixe : sans cela, deux rapports au contenu identique mais
    sérialisés dans un autre ordre donneraient deux sceaux différents, et le cahier accuserait
    une édition manuelle qui n a jamais eu lieu.
    """
    return json.dumps(rapport, ensure_ascii=False, sort_keys=True, indent=2)


def _indice(rang: int) -> str:
    """`a`, `b`, … puis `z1`, `z2` — l alphabet ne suffit pas toujours, et il doit le dire."""
    return chr(ord("a") + rang) if rang < 26 else f"z{rang - 25}"


def nommer(
    produit: str, nature: str, extension: str, dossier: Path, jour: _dt.date | None = None
) -> Path:
    """Chemin libre suivant la convention. L indice s incrémente tant que le fichier existe."""
    date = (jour or _dt.date.today()).strftime("%Y%m%d")
    propre = _INTERDITS.sub("-", produit).strip() or "Produit"
    for rang in range(400):
        chemin = dossier / f"{propre} - {nature} - {date}{_indice(rang)}{extension}"
        if not chemin.exists():
            return chemin
    raise RuntimeError(
        f"plus d indice libre pour « {propre} - {nature} » au {date} dans {dossier} : "
        "400 livrables du même jour, c est une boucle, pas un audit"
    )


def sceller(entetes: dict[str, str], corps: str) -> str:
    """Préfixe le corps d un bloc de sceau : sources scellées + empreinte du corps."""
    lignes = [DEBUT_SCEAU]
    for cle, valeur in entetes.items():
        lignes.append(f"  {cle}: {valeur}")
    lignes.append(f"  sceau_corps: {empreinte(corps)}")
    lignes.append(FIN_SCEAU)
    return "\n".join(lignes) + "\n\n" + corps


def verifier_sceau(texte: str) -> tuple[bool, str]:
    """(intact, motif). Sans sceau, un document n est pas réputé intact : il est NON SCELLÉ."""
    if not texte.startswith(DEBUT_SCEAU):
        return False, "aucun sceau en tête : ce document n a pas été produit par la forge"
    fin = texte.find(FIN_SCEAU)
    if fin < 0:
        return False, "bloc de sceau non refermé"
    bloc, corps = texte[: fin + len(FIN_SCEAU)], texte[fin + len(FIN_SCEAU) :].lstrip("\n")
    trouve = _LIGNE_CORPS.search(bloc)
    if not trouve:
        return False, "sceau sans empreinte de corps (`sceau_corps`)"
    attendu, obtenu = trouve.group(1), empreinte(corps)
    if attendu != obtenu:
        return False, (
            f"corps modifié après scellement — attendu {attendu[:16]}…, obtenu {obtenu[:16]}… ; "
            "une édition manuelle d un livrable dérivé est un défaut : corriger la SOURCE et "
            "régénérer"
        )
    return True, "sceau valide : le corps est celui qui a été produit"
