"""Matrice des droits — une action × un profil = une cellule = une assertion.

TF-0343 / TF-0342 (campagnes des 12 et 17/08/2026, produit Produit-01).

**Le trou.** Le cahier d'Produit-01 porte une matrice de 10 actions × 4 profils. La suite
existante en couvrait les règles, mais **dispersées dans 13 fichiers, sous l'angle de chaque
service** — donc sans jamais dire quelles CASES n'étaient pas couvertes. Deux ne l'étaient pas :

  - le profil « en copie » n'apparaissait que comme destinataire servant à faire échouer un
    envoi (`can_view` testé pour tiers / demandeur / approbateur, jamais pour une copie) ;
  - aucun test n'instanciait d'admin sur une décision — la règle « l'admin ne peut pas décider
    à la place d'un approbateur » était donc vraie **par construction** et prouvée par rien.

Deux autres cases du cahier ne sont carrément **pas tenues** par le produit (relance manuelle
sans aucune route ; export des demandes ouvert à tout authentifié au lieu d'être réservé aux
admins) sans qu'aucun test ne le signale.

**Le patron.** Une action × un profil = une cellule = une assertion, dans UN fichier dédié qui
parcourt tous les profils par action et compare le code HTTP au contrat du cahier. Une suite
organisée par service ne peut PAS dire ce qu'elle ne couvre pas ; une suite organisée par
cellule ne peut pas se taire.

**Les cellules non tenues s'écrivent en `xfail(strict=True)`** — jamais omises, jamais
commentées. Le test échoue pour la bonne raison, et le jour du correctif il passe en XPASS,
que `strict` transforme en échec : on est forcé de retirer le marqueur. Un écart commenté, lui,
survit à son correctif.

**Objet neuf par cellule mutante (TF-0344, piège 3).** L'approbation réussie du profil N faisait
avancer le circuit et ouvrait le tour du profil N+1, qui rendait 201 au lieu de 409 — faux
échec. Le patron le rend STRUCTUREL : une cellule déclarée `mute: true` reçoit un objet frais.
C'est le seul des trois pièges qu'aucune revue statique ne sait voir (`forge_tests.revue`).

**Coût mesuré sur Produit-01** : 15 tests, ~340 lignes, 2 écarts rendus exécutables,
13 cellules vertes.

**TF-0342 — la recette MULTI-PROFILS devient une exigence de socle.** Produit-01 a passé un audit
12 pans le 12/08 avec « pan qualif 8/8, ratio 1,00, ZÉRO finding » et « suite e2e 10/10 verte »,
le tout sous UNE identité qui se désignait elle-même approbateur. Le cas NOMINAL du cahier — un
approbateur décide, le suivant est sollicité — n'avait donc jamais été exécuté. Le trou n'a pas
été trouvé par l'outillage mais par une question humaine, cinq jours plus tard. La première
recette inter-profils a révélé un défaut produit réel (`canDecide` ne vérifie pas le tour :
l'IHM invite à une action vouée au 409) plus deux défauts d'ergonomie. Tous invisibles à une
suite mono-identité **par construction**.

Donc : dès qu'un produit déclare des rôles, il faut autant d'identités outillées que de rôles,
et au moins un test où deux identités COEXISTENT — observer ce qu'un profil voit pendant qu'un
autre agit. Ces deux exigences sont contrôlées ici.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from forge_tests import classes
from forge_tests.noyau import Finding
from forge_tests.risque import coter

PAN = "qualif"

#: La matrice est une DÉCLARATION du projet, pas une déduction de la forge : elle seule sait
#: quel code son contrat promet à quel profil. Même canal que `cas-adoptes.jsonl` (RT-13).
FICHIER = "forge/matrice-droits.json"

#: Le fichier généré. Un seul, dédié : c'est tout le patron — 13 fichiers par service ne
#: peuvent pas dire quelle CASE manque.
NOM_FICHIER_GENERE = "test_matrice_droits.py"


def lire(cible: Path | str) -> dict:
    """La matrice déclarée par le projet, ou `{}`. Une déclaration illisible est DITE.

    Forme attendue :

        {
          "profils": ["demandeur", "approbateur", "en copie", "admin"],
          "actions": [
            {"nom": "decider", "methode": "POST", "route": "/api/demandes/{id}/decision",
             "mute": true,
             "attendu": {"approbateur": 200, "demandeur": 403, "en copie": 403, "admin": 403}},
            {"nom": "relancer", "methode": "POST", "route": "/api/demandes/{id}/relance",
             "attendu": {"demandeur": 200, "approbateur": 403, "en copie": 403, "admin": 200},
             "non_tenues": ["demandeur", "admin"]}
          ]
        }

    `non_tenues` : les cases que le PRODUIT ne tient pas aujourd'hui. Elles ne disparaissent pas
    de la matrice — elles deviennent des `xfail(strict=True)`.
    """
    source = Path(cible) / FICHIER
    if not source.exists():
        return {}
    try:
        matrice = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erreur:
        return {"_illisible": f"{FICHIER} : JSON invalide ({erreur})"}
    return matrice if isinstance(matrice, dict) else {"_illisible": f"{FICHIER} : objet attendu"}


def cellules(matrice: dict) -> list[dict]:
    """Le produit cartésien actions × profils, aplati. Une case absente du contrat est NOMMÉE.

    C'est l'inversion qui fait tout : on énumère d'abord la grille, on regarde ensuite ce que le
    contrat en dit. L'inverse — parcourir ce que le contrat déclare — reproduirait exactement le
    biais de disponibilité que ce framework existe pour supprimer.
    """
    profils = [str(p) for p in matrice.get("profils") or []]
    grille: list[dict] = []
    for action in matrice.get("actions") or []:
        attendu = action.get("attendu") or {}
        non_tenues = {str(p) for p in action.get("non_tenues") or []}
        for profil in profils:
            grille.append(
                {
                    "action": str(action.get("nom") or ""),
                    "profil": profil,
                    "methode": str(action.get("methode") or "GET").upper(),
                    "route": str(action.get("route") or ""),
                    "mute": bool(action.get("mute")),
                    "code": attendu.get(profil),
                    "tenue": profil not in non_tenues,
                    "au_contrat": profil in attendu,
                }
            )
    return grille


def _identifiant_python(texte: str) -> str:
    nettoye = re.sub(r"[^0-9a-zA-Z]+", "_", texte.strip().lower()).strip("_")
    return nettoye or "cellule"


def generer_matrice(matrice: dict) -> str:
    """Le fichier exécutable : une cellule = un test, les non tenues en `xfail(strict=True)`.

    Généré, donc régénérable : la grille suit le contrat sans qu'on doive se souvenir d'ajouter
    un test au douzième profil.
    """
    grille = cellules(matrice)
    if not grille:
        return ""
    lignes = [
        '"""Matrice des droits — DÉRIVÉE de forge/matrice-droits.json (TF-0343).',
        "",
        "Une action × un profil = une cellule = une assertion. Ce fichier est le SEUL endroit où",
        "la grille se lit d'un coup d'œil : une suite organisée par service ne peut pas dire",
        "quelle CASE elle ne couvre pas.",
        "",
        "Les cellules que le produit ne tient pas sont en `xfail(strict=True)` : jamais omises,",
        "jamais commentées. Le jour du correctif, XPASS fait échouer le test et force à retirer",
        "le marqueur — un écart commenté, lui, survit à son correctif.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import pytest",
        "",
        "",
        "def _appeler(client, methode: str, route: str, profil: str):",
        '    """À CÂBLER par le projet : lui seul sait comment il ouvre une session par profil."""',
        "    raise NotImplementedError(",
        '        "cabler _appeler(client, methode, route, profil) sur les identites du projet"',
        "    )",
        "",
        "",
        "def _objet_neuf(client, profil: str):",
        '    """Objet frais pour une cellule MUTANTE (TF-0344, piège 3).',
        "",
        "    L'approbation réussie du profil N faisait avancer le circuit et ouvrait le tour du",
        "    profil N+1, qui rendait 201 au lieu de 409 — faux échec. Une cellule dont le succès",
        "    mute l'état exige un objet neuf : ici c'est structurel, pas une vigilance.",
        '    """',
        "    raise NotImplementedError(",
        '        "cabler _objet_neuf(client, profil) sur la fabrique du projet"',
        "    )",
        "",
    ]
    for cellule in grille:
        nom = (
            f"test_{_identifiant_python(cellule['action'])}"
            f"_{_identifiant_python(cellule['profil'])}"
        )
        lignes.append("")
        if not cellule["au_contrat"]:
            lignes += [
                "@pytest.mark.xfail(",
                "    strict=True,",
                f"    reason=\"cellule ABSENTE du contrat : le cahier ne dit pas ce que "
                f"« {cellule['profil']} » doit obtenir sur « {cellule['action']} » — "
                "le trou est au contrat, pas au test\",",
                ")",
            ]
        elif not cellule["tenue"]:
            lignes += [
                "@pytest.mark.xfail(",
                "    strict=True,",
                f"    reason=\"cellule NON TENUE par le produit aujourd hui "
                f"(attendu {cellule['code']}) — le jour du correctif, XPASS fait echouer ce "
                "test et force a retirer ce marqueur\",",
                ")",
            ]
        lignes += [
            f"def {nom}(client) -> None:",
            f'    """{cellule["action"]} × {cellule["profil"]} → '
            f'{cellule["code"] if cellule["au_contrat"] else "NON CONTRACTUALISÉ"}."""',
            (
                f"    identifiant = _objet_neuf(client, {cellule['profil']!r})"
                if cellule["mute"]
                else "    identifiant = None"
            ),
            f"    route = {cellule['route']!r}.replace('{{id}}', str(identifiant))",
            f"    reponse = _appeler(client, {cellule['methode']!r}, route, "
            f"{cellule['profil']!r})",
            "",
            f"    assert reponse.status_code == {cellule['code'] or 0}, (",
            f"        f\"{cellule['action']} × {cellule['profil']} : \"",
            f'        f"attendu {cellule["code"]}, obtenu {{reponse.status_code}}"',
            "    )",
        ]
    return "\n".join(lignes) + "\n"


def ecrire(cible: Path, destination: Path) -> Path | None:
    """Dépose la matrice exécutable dans le dossier de cas dérivés. Jamais chez l'audité (G-1)."""
    matrice = lire(cible)
    contenu = generer_matrice(matrice)
    if not contenu:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    chemin = destination / NOM_FICHIER_GENERE
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# --- TF-0342 : la recette multi-profils, exigence de socle -------------------------------------
_COEXISTENCE = re.compile(
    r"(?:newContext|browser\.newContext|request\.newContext)\([^;]{0,400}?storageState",
    re.DOTALL,
)


def controles(cible: Path, sessions: list[dict], specs: list[Path]) -> list[Finding]:
    """Les deux exigences de socle dès qu'un produit DÉCLARE des rôles.

    Un produit à rôles n'est pas vérifiable sous une identité unique : ce n'est pas une
    faiblesse de couverture, c'est une impossibilité de construction. Le cas nominal (« un
    approbateur décide, le suivant est sollicité ») n'existe pas dans une suite mono-identité.
    """
    matrice = lire(cible)
    findings: list[Finding] = []
    if matrice.get("_illisible"):
        identifiant = "qualif:matrice-droits:illisible"
        return [
            Finding(
                id=identifiant,
                classe=classes.MATRICE_DES_DROITS,
                localisation=FICHIER,
                message=(
                    f"{matrice['_illisible']} — la matrice des droits declaree est illisible : "
                    "aucune cellule n est opposable, et l audit ne peut pas dire ce qu il ne "
                    "couvre pas"
                ),
                risque=coter(PAN, identifiant, FICHIER),
            )
        ]
    profils = [str(p) for p in matrice.get("profils") or []]
    if not profils:
        return []

    outillees = {str(s.get("role") or "") for s in sessions if s.get("role")}
    manquantes = sorted(set(profils) - outillees)
    if manquantes:
        identifiant = "qualif:multi-profils:identites-manquantes"
        findings.append(
            Finding(
                id=identifiant,
                classe=classes.MATRICE_DES_DROITS,
                localisation=FICHIER,
                message=(
                    f"le produit declare {len(profils)} role(s) et l audit n en outille que "
                    f"{len(outillees)} : "
                    + ", ".join(f"« {profil} »" for profil in manquantes)
                    + " sans identite. Un produit a roles n est PAS verifiable sous une identite "
                    "unique — mesure le 12/08 : « ratio 1,00, ZERO finding » sous un compte "
                    "unique, un defaut produit et deux defauts d ergonomie decouverts a la "
                    "premiere recette inter-profils. Declarer "
                    "FORGE_TESTS_QUALIF_STORAGE_STATES = « role=chemin » pour chaque role"
                ),
                risque=coter(PAN, identifiant, FICHIER),
            )
        )

    if len(profils) > 1 and not _un_test_fait_COEXISTER_deux_identites(specs):
        identifiant = "qualif:multi-profils:aucune-coexistence"
        findings.append(
            Finding(
                id=identifiant,
                classe=classes.MATRICE_DES_DROITS,
                localisation=FICHIER,
                message=(
                    "aucun test ne fait COEXISTER deux identites : rejouer le meme parcours sous "
                    "N profils, l un apres l autre, ne montre jamais ce qu un profil VOIT "
                    "pendant qu un autre AGIT. C est exactement le cas nominal du cahier — un "
                    "approbateur decide, le suivant est sollicite — et c est ainsi qu a ete "
                    "trouve le defaut produit du 17/08 (l IHM invite un approbateur hors tour a "
                    "une action vouee au 409)"
                ),
                risque=coter(PAN, identifiant, FICHIER),
            )
        )
    return findings


def _un_test_fait_COEXISTER_deux_identites(specs: list[Path]) -> bool:
    """Deux contextes porteurs d'un `storageState` dans le MÊME test : la coexistence."""
    for fichier in specs:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for _nom, corps in _blocs(texte):
            if len(_COEXISTENCE.findall(corps)) >= 2:
                return True
    return False


def _blocs(texte: str) -> list[tuple[str, str]]:
    from forge_tests.revue import _blocs_de_test

    return _blocs_de_test(texte)
