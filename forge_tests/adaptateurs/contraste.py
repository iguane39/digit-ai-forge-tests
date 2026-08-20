"""Adaptateur Contraste (Q4) — cablage de la mesure V2 de `render_page.py`, sur le RENDU servi.

Pourquoi ce pan existe (TF-0409, option O3). La mesure existait et n etait jouee par personne.
`render_page.py` du socle digit-ai-page-html porte V2 — contraste WCAG calcule sur les styles
REELLEMENT rendus, texte large distingue du texte courant — et elle avait deja tourne contre
des ecrans produits le 11/08/2026. Elle n etait cablee comme pan de forge-tests NULLE PART :
elle ne tournait que si quelqu un y pensait. Le `non_juge` du pan accessibilite le declarait
mot pour mot depuis le 20/08 (« une mesure existante mais NON CABLEE a cet audit »).
Un controle qui existe sans etre joue n existe pas.

Ce que ce pan ne fait PAS, et qui explique sa forme. Il ne recopie pas la mesure : il charge
`MEASURE_JS` depuis le script du socle et l evalue dans la page vivante. La formule de
luminance reste a UN seul endroit du parc ; si le socle la corrige, ce pan en herite sans une
ligne. Et il ne mesure pas un fichier : un DOM capture puis relu depuis le disque perd ses
feuilles de style (les `<link>` pointent vers le serveur), et un contraste mesure sur une page
non stylee est un faux vert — noir sur blanc, toujours conforme, jamais reel.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from forge_tests import classes
from forge_tests.adaptateurs import accessibilite
from forge_tests.adaptateurs._parcours import parcourir
from forge_tests.noyau import Element, Finding, SortieAdaptateur
from forge_tests.risque import coter

NOM, PAN = "contraste-wcag", "contraste"

# A-5 : ce qu il FAUDRAIT pour couvrir ce pan — publie tel quel au rapport.
POUR_COUVRIR = (
    "servir le front (build présent et `npm`/navigateur disponibles) ou déclarer l'instance "
    "SERVIE dans FORGE_TESTS_BASE_URL, ET disposer du socle digit-ai-page-html installé "
    "(`scripts/render_page.py`, dont la mesure V2 est chargée ici) : le pan juge les styles "
    "RENDUS, il n'a rien à mesurer sur un fichier dont les feuilles de style ne se chargent pas"
)

CHAPITRES = (
    {"code": "F4", "famille": "fonctionnel", "titre": "Accessibilité",
     "decoupe": "ecran", "axe_cas": "contraste"},
)

CHAMPS_REQUIS = (
    "FORGE_TESTS_BASE_URL",
    "FORGE_TESTS_LOGIN",
    "FORGE_TESTS_PASSWORD",
)

_SOCLE = Path.home() / ".claude" / "skills" / "digit-ai-page-html" / "scripts" / "render_page.py"

NON_JUGE = [
    "contraste : mesure a l etat INITIAL de chaque route — les etats atteints apres "
    "interaction (menu ouvert, modale, message d erreur) ne sont pas mesures",
    "contraste : un texte pose sur une IMAGE de fond n est pas mesurable par calcul — la "
    "mesure le declare `non mesure` au lieu de l approuver, et il reste a verifier a l oeil",
    "contraste : le seuil applique est WCAG AA (4.5:1, ou 3:1 pour le texte large tel que le "
    "socle le qualifie). AAA (7:1) n est pas jugé ici",
    "contraste : la NAVIGATION CLAVIER et les pieges de focus relevent du pan `clavier` ; "
    "l ARIA avance (roles, ordre de focus) n est couvert par aucun oracle du parc a ce jour",
    "contraste : l audit RGAA complet reste un livrable HUMAIN — un tiers des criteres n est "
    "pas mecanisable, la machine prepare l audit, elle ne rend pas la declaration",
]


def _mesure_js() -> str | None:
    """Charge `MEASURE_JS` depuis le script du socle. None si le socle n est pas installe.

    Import par chemin plutot que copie : la formule de luminance reste a UN endroit du parc.
    Le module s importe sans effet de bord (son `main()` n est appele que sous `__main__`).
    """
    if not _SOCLE.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_socle_render_page", _SOCLE)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mesure = getattr(module, "MEASURE_JS", None)
        return mesure if isinstance(mesure, str) and mesure.strip() else None
    except Exception:  # noqa: BLE001 — socle illisible : le pan se declare non mesure
        return None


def sans_objet(cible: Path) -> str | None:
    """Meme frontiere que le pan accessibilite : pas d interface, pas de contraste."""
    return accessibilite.sans_objet(cible)


def inventaire(cible: Path) -> list[Element]:
    routes, _ = accessibilite.routes_a_auditer(cible)
    return [
        Element(id=f"contraste:{route}", pan=PAN, libelle=f"contraste de {route}",
                source=str(cible / "frontend"))
        for route in routes
    ]


def analyser(cible: Path) -> SortieAdaptateur:
    mesure = _mesure_js()
    if mesure is None:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[
                *NON_JUGE,
                f"contraste : mesure V2 introuvable — {_SOCLE} absent ou illisible. Le pan ne "
                "recopie pas la formule : sans le socle, il se declare non mesure",
            ],
        )
    routes, provenance = accessibilite.routes_a_auditer(cible)
    if not routes:
        return accessibilite.verdict_sans_route(NOM, PAN, cible, NON_JUGE)

    def action(page: Any, _route: str) -> tuple[Any, str | None]:
        page.wait_for_timeout(150)  # styles et polices posees avant de mesurer
        return page.evaluate(mesure), None

    resultats, motifs = parcourir(cible, routes, action, prefixe="contraste")
    socle = [
        *NON_JUGE,
        f"contraste : {len(routes)} route(s) a mesurer — provenance : "
        + (provenance or "inventaire fourni a l adaptateur"),
    ]
    if not resultats and not motifs:
        return SortieAdaptateur(
            NOM, PAN, str(cible), "SKIP",
            non_juge=[*socle, "front non servi : build absent, npm ou navigateur manquant"],
        )

    findings: list[Finding] = []
    non_juge = [*socle, *motifs]
    mesurees: list[str] = []
    for route, issues in resultats.items():
        if not isinstance(issues, dict):
            non_juge.append(f"contraste : route {route} — mesure illisible, page non jugee")
            continue
        mesurees.append(route)
        for ecart in issues.get("v2_contrast", []):
            quoi = str(ecart.get("what", "element"))
            detail = str(ecart.get("detail", ""))
            identifiant = f"contraste:{route}:{quoi[:40]}"
            findings.append(
                Finding(
                    id=identifiant,
                    classe=classes.ACCESSIBILITE,
                    localisation=route,
                    # Le seuil WCAG AA n est pas un gout : un texte sous 4.5:1 est illisible
                    # pour une partie des utilisateurs, et pour un site public francais
                    # l ecart se declare au dossier MEP.
                    message=f"[{route}] contraste WCAG AA — {quoi} : {detail}",
                    severite="bloquant",
                    risque=coter(PAN, identifiant, str(cible / "frontend")),
                )
            )
        # `unmeasured` est la part HONNETE de la mesure : ce que le calcul ne peut pas trancher
        # (texte sur image de fond). La taire ferait lire le PASS comme « tout est conforme ».
        for inconnu in issues.get("unmeasured", []):
            non_juge.append(
                f"contraste : [{route}] {inconnu.get('what', 'element')} — "
                f"{inconnu.get('detail', 'non mesurable par calcul')}"
            )

    if not mesurees:
        return SortieAdaptateur(NOM, PAN, str(cible), "SKIP", non_juge=sorted(set(non_juge)))
    non_juge.append(f"contraste : routes mesurees — {', '.join(mesurees)}")
    return SortieAdaptateur(
        adaptateur=NOM, pan=PAN, cible=str(cible),
        verdict="FAIL" if findings else "PASS",
        findings=findings, non_juge=sorted(set(non_juge)),
    )
