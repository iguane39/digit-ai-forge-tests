"""Adoption des cas dérivés — le contrat qui SOLDE les cas à adopter.

RT-13 (lot bourse-aux-vacants 20260814a) : les cahiers dérivés sont déposés hors du projet
(G-1), et rien ne permettait au projet de dire « ce cas-là, je l'ai écrit, il vit ici ».
Conséquence mesurée par le produit : après avoir écrit 11 tests couvrant exactement les axes
proposés, le cahier suivant régénérait les mêmes cent cas en « non joué ».
Un indicateur qui ne bouge pas quand le travail est fait cesse d'être lu.

**R-40 (17/08, TF-0349) — la voie « proposition de tests » est fermée.** Un cas dérivé n'est
pas un livrable, et « proposition » n'est plus un état terminal : le cas NAÎT `a_adopter`,
état transitoire, et ne se solde que de trois façons — jamais par le silence :

  - **adopté et exécuté** : le projet cite le test qui le porte, et le test existe ;
  - **`non_testable` motivé** : idiome RT-6, `champs_requis[]` nommés — il se répare en
    FOURNISSANT ce qui manque, pas en écrivant un test de complaisance ;
  - **écarté par une décision humaine nommée** : qui, quand, pourquoi.

Le solde `dérivés − adoptés − non_testables − écartés` est compté ET publié par ce module
(`solde`, `cumuler`, `libelle_solde`). Un cahier dont ce solde n'est pas nul porte un
reste-à-faire, pas un livrable clos. Le coût du statu quo est mesuré : 971 cas dérivés pour
0 adopté (bourse-aux-vacants, 20260817b), 680 pour 0 (COMPTA, 20260814b).

**TF-0355 (18/08) — le solde des CAS ne solde pas la SURFACE.** Un élément déclaré
`non_testable` ou `exclu` PAR LE RAPPORT ne produit aucun cas : il sort « non couvert », et
n entre donc dans aucun terme du solde. Un cahier pouvait afficher « solde 0 — SOLDÉ » avec
huit éléments de sa surface ne portant aucun cas. Les deux chiffres sont désormais OPPOSÉS :
`libelle_solde` reçoit le compte des non-couverts et refuse de prononcer « SOLDÉ » tant qu il
n est pas nul. Les deux dettes restent DISTINCTES — l une se solde par une déclaration du
projet, l autre en fournissant ce qui manque puis en rejouant.

**Antériorité assumée, déclarée ici.** Les `cas-adoptes.jsonl` déjà écrits par les produits,
et les rapports déjà rendus, portent l'ancien vocabulaire (`"statut": "proposition"`). Le
LECTEUR l'accepte et le normalise en `a_adopter` (`est_a_adopter`) : aucun produit n'est
rattrapé en masse, chacun l'est au prochain run. Le PRODUCTEUR, lui, n'émet plus jamais
« proposition ».

**Le nom de dossier `propositions/` : requalification SÉQUENCÉE, pas oubliée (TF-0354).** Le
mot est mort en doctrine, au catalogue, au cahier et à l'oracle ; il survit dans un seul
endroit, et pour une raison qui n'est pas de la négligence : `<projet>/propositions/` est une
convention de CHEMIN en service chez les produits, citée par leurs commandes et leurs scripts.
La renommer d'un geste casserait des appels réels — et la loi 1 vaut aussi pour les chemins :
une convention est câblée ou n'existe pas. La séquence déclarée est donc : (1) le vocabulaire
est requalifié partout ailleurs — fait ; (2) le placeholder documenté devient
`<dossier-cas-derives>`, ce qui ne casse rien puisque c'est le lecteur qui choisit le nom —
fait ; (3) le renommage du dossier de convention se fait produit par produit, à leur prochain
run, jamais en masse depuis ici (garde-fou « le pilot n'intervient pas hors run demandé »).
Tant que (3) n'est pas achevé, `propositions/` reste LU et accepté sans avertissement.

**Condition technique déjà remplie**, vérifiée par le produit : les références de cas sont
DÉTERMINISTES (74 éléments communs entre deux audits, 0 identifiant changé) — elles sont donc
citables depuis du code.

**Le contrat, tenu par ce module :**

    <projet>/forge/cas-adoptes.jsonl   — une ligne JSON par cas SOLDÉ, trois formes :
    {"cas": "F1-3025-3", "test": "frontend/tests/e2e/10-navigation.spec.ts"}
    {"cas": "T2-0481-1", "non_testable": true, "champs_requis": ["FORGE_TESTS_QUALIF_URL"]}
    {"cas": "F1-3025-2", "ecarte_par": "<nom>", "date": "2026-08-17", "motif": "<pourquoi>"}

C'est le PROJET qui déclare, jamais la forge : elle ne saurait pas dire à sa place qu'un cas
est couvert. Le fichier est lu en LECTURE SEULE (G-1) et la déclaration est **vérifiée** :

  - le chemin de test cité doit EXISTER, sinon l'adoption est REFUSÉE avec son motif. Sans ce
    contrôle, un fichier d'adoptions survivrait à la suppression des tests qu'il cite, et le
    solde descendrait sur du vide — exactement le contraire de ce que RT-13 demande ;
  - une référence inconnue du cahier courant est déclarée, jamais silencieuse : elle signale
    un cas renommé ou un fichier périmé ;
  - un `non_testable` sans `champs_requis`, un écart sans nom ou sans motif sont REFUSÉS avec
    leur raison : ils resteraient sinon deux portes de sortie muettes, exactement ce que R-40
    ferme. Une adoption refusée reste AU SOLDE — sinon le solde descendrait sur du vide.

Ce module ne juge pas la QUALITÉ du test adopté : il constate une déclaration et l'existence
de son support. Vérifier qu'un test affirme ce qu'il prétend est le rôle de la mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

FICHIER = "forge/cas-adoptes.jsonl"

#: TF-0354 — le SECOND fichier, et la contradiction qu'il révélait.
#: R-40 (`REGLES-PROJET.md` §T du pilot) prescrit `forge/cas-ecartes.jsonl` pour les DEUX
#: autres issues, et `oracles/oracle-adoption-tests.mjs` (A2) renvoie vers ce sidecar tout
#: écartement trouvé dans `cas-adoptes.jsonl`. Ce module, lui, acceptait les trois formes dans
#: le premier fichier et ne lisait pas le second. Résultat mesuré en confrontant les deux
#: outils le 18/08 : **un produit qui suit la doctrine était puni par la forge** — ses
#: `non_testable` et ses écarts partaient dans `cas-ecartes.jsonl`, invisibles ici, et son
#: solde ne descendait jamais. Le cahier lui répondait « reste-à-faire » pour avoir bien fait.
#:
#: Les deux fichiers sont donc lus, et la répartition prescrite est celle du pilot :
#: l'adoption ici, les deux autres issues là-bas. L'ancienne tolérance (les trois formes dans
#: `cas-adoptes.jsonl`) reste ACCEPTÉE comme antériorité — des produits ont écrit ainsi avant
#: le 18/08 et aucun n'est rattrapé en masse — mais elle n'est plus ce que le cahier enseigne.
FICHIER_ECARTES = "forge/cas-ecartes.jsonl"

# Les quatre états d'un cas dérivé, plus le refus. `A_ADOPTER` est l'état de NAISSANCE : il est
# transitoire par construction (R-40), et c'est lui que le solde compte comme reste-à-faire.
A_ADOPTER = "a_adopter"
ADOPTE = "adopte"
NON_TESTABLE = "non_testable"
ECARTE = "ecarte"
REFUSE = "refuse"
# Vocabulaire d'AVANT R-40, encore présent dans les fichiers et les rapports déjà écrits : le
# lecteur l'accepte (antériorité), le producteur ne l'émet plus. Le retirer d'ici ferait passer
# des cas déjà déclarés pour des états inconnus, sans qu'aucun produit ait rien changé.
ETATS_ANTERIEURS_A_ADOPTER = ("proposition",)

NON_JUGE = [
    "adoption : le fichier `forge/cas-adoptes.jsonl` est une DECLARATION du projet — ce module "
    "verifie que le test cite existe, jamais qu il couvre reellement le cas ni qu il affirme "
    "quoi que ce soit (c est le role de la mutation)",
    "adoption : un cas adopte puis renomme cote cahier ressort en reference INCONNUE, declaree "
    "telle quelle — la reference de cas est stable par construction, pas eternelle",
    "adoption : un cas `non_testable` ou `ecarte` (R-40) est pris au mot — ce module exige que "
    "le motif soit NOMME (champs_requis, ou qui/quand/pourquoi) et jamais que la raison soit "
    "bonne ; le solde compte des etats declares, il ne juge pas un arbitrage humain",
]


def _solder_non_testable(entree: dict) -> dict:
    """Cas déclaré injouable ICI — idiome RT-6 : il se répare en FOURNISSANT les champs."""
    champs = [str(c).strip() for c in (entree.get("champs_requis") or []) if str(c).strip()]
    if not champs:
        return {
            "test": "",
            "statut": REFUSE,
            "motif": "non_testable sans `champs_requis` — RT-6 : un cas injouable se repare en "
            "nommant ce qu il faut fournir, sinon la sortie est muette",
            "champs_requis": [],
        }
    return {
        "test": "",
        "statut": NON_TESTABLE,
        "motif": "aucune execution ne peut l atteindre ici : fournir " + ", ".join(champs),
        "champs_requis": champs,
    }


def _solder_ecarte(entree: dict) -> dict:
    """Cas écarté par une décision HUMAINE nommée — qui, quand, pourquoi. Sans nom, refusé."""
    par = str(entree.get("ecarte_par") or "").strip()
    motif = str(entree.get("motif") or "").strip()
    date = str(entree.get("date") or "").strip()
    if not par or not motif:
        return {
            "test": "",
            "statut": REFUSE,
            "motif": "ecart sans decision nommee — R-40 exige `ecarte_par` et `motif` (la date "
            "est recommandee) : un ecart anonyme est un silence deguise",
        }
    quand = f" le {date}" if date else " (date non declaree)"
    return {"test": "", "statut": ECARTE, "motif": f"ecarte par {par}{quand} — {motif}"}


def _solder_ecarte_du_sidecar(entree: dict) -> dict:
    """Un écart au vocabulaire du SIDECAR : `qui` / `quand` / `pourquoi` (R-40 du pilot).

    Le même objet porte deux vocabulaires selon le fichier où il vit — `ecarte_par`/`date`/
    `motif` ici (antériorité RT-13), `qui`/`quand`/`pourquoi` là-bas (R-40). Les traduire à la
    lecture est moins coûteux que d'imposer un renommage aux produits qui ont déjà déclaré, et
    surtout : refuser un écart parce qu'il emploie le mot de l'AUTRE outil serait exactement la
    double vérité que ce module vient de fermer.
    """
    return _solder_ecarte({
        "ecarte_par": entree.get("ecarte_par") or entree.get("qui"),
        "date": entree.get("date") or entree.get("quand"),
        "motif": entree.get("motif") or entree.get("pourquoi"),
    })


def _lire_sidecar(cible: Path) -> dict[str, dict]:
    """Les deux autres issues de R-40, là où la doctrine du pilot les range."""
    source = Path(cible) / FICHIER_ECARTES
    if not source.is_file():
        return {}
    soldes: dict[str, dict] = {}
    for rang, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            entree = json.loads(ligne)
        except json.JSONDecodeError:
            soldes[f"({FICHIER_ECARTES} ligne {rang})"] = {
                "test": "",
                "statut": REFUSE,
                "motif": f"ligne {rang} de {FICHIER_ECARTES} : JSON invalide — ignoree",
            }
            continue
        ref = str(entree.get("cas") or "").strip()
        if not ref:
            continue
        declare = str(entree.get("statut") or "").strip()
        if entree.get("non_testable") or declare == NON_TESTABLE:
            soldes[ref] = _solder_non_testable(entree)
        elif declare == ECARTE or "ecarte_par" in entree or "qui" in entree:
            soldes[ref] = _solder_ecarte_du_sidecar(entree)
        else:
            soldes[ref] = {
                "test": "",
                "statut": REFUSE,
                "motif": f"{FICHIER_ECARTES} ne porte que `non_testable` et `ecarte` (R-40) — "
                "une adoption se declare dans " + FICHIER,
            }
    return soldes


def charger(cible: Path) -> dict[str, dict]:
    """Déclarations du projet sur ses cas dérivés, chacune avec son verdict de vérification.

    Renvoie `{ref_cas: {"test": chemin, "statut": "adopte"|"non_testable"|"ecarte"|"refuse",
    "motif": …}}`. Fichier absent = aucune déclaration : ce n'est pas une faute, c'est l'état
    initial — mais tous les cas du cahier restent alors `a_adopter`, donc le cahier n'est PAS
    soldé (R-40).
    """
    source = Path(cible) / FICHIER
    adoptions: dict[str, dict] = {}
    if not source.is_file():
        # TF-0354 : le sidecar de la doctrine se lit MÊME sans `cas-adoptes.jsonl`. Un produit
        # dont tous les cas sont non testables ou écartés n'a aucune adoption à déclarer — le
        # retour anticipé d'ici rendait ses déclarations invisibles, c'est-à-dire punissait
        # exactement le cas où il a le plus soigneusement suivi R-40.
        return _lire_sidecar(cible)
    for rang, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            entree = json.loads(ligne)
        except json.JSONDecodeError:
            adoptions[f"(ligne {rang})"] = {
                "test": "",
                "statut": REFUSE,
                "motif": f"ligne {rang} de {FICHIER} : JSON invalide — declaration ignoree",
            }
            continue
        ref = str(entree.get("cas") or "").strip()
        test = str(entree.get("test") or "").strip()
        declare = str(entree.get("statut") or "").strip()
        if not ref:
            continue
        # R-40 : les deux autres soldes se lisent AVANT le test cité — ils n'en portent aucun,
        # et le contrôle « le test existe » les aurait tous refusés pour absence de support.
        if entree.get("non_testable") or declare == NON_TESTABLE:
            adoptions[ref] = _solder_non_testable(entree)
            continue
        # `ecarte_par` se lit par PRÉSENCE de la clé, pas par sa valeur : un écart déclaré avec
        # un nom vide doit sortir « écart sans décision nommée », pas « aucun test cité » — le
        # motif du refus dit alors ce qu il faut corriger.
        if "ecarte_par" in entree or declare == ECARTE:
            adoptions[ref] = _solder_ecarte(entree)
            continue
        if not test:
            adoptions[ref] = {
                "test": "",
                "statut": REFUSE,
                "motif": "aucun test cite — une adoption sans support ne se verifie pas",
            }
            continue
        chemin = Path(cible) / test
        if not chemin.exists():
            adoptions[ref] = {
                "test": test,
                "statut": REFUSE,
                "motif": f"le test cite est introuvable ({test}) — adoption refusee",
            }
            continue
        adoptions[ref] = {"test": test, "statut": ADOPTE, "motif": ""}
    # Le sidecar est lu APRÈS : sur un cas déclaré des deux côtés, la déclaration qui suit la
    # doctrine l'emporte sur l'antériorité tolérée. Un produit en cours de migration n'a donc
    # pas à nettoyer l'ancien fichier avant que le nouveau compte.
    adoptions.update(_lire_sidecar(cible))
    return adoptions


def statut(adoptions: dict[str, dict], ref: str) -> dict:
    """État d'un cas : adopté (avec son test), non testable (motivé), écarté (nommé), adoption
    refusée (avec son motif) — ou `a_adopter` s'il n'est déclaré nulle part.

    `a_adopter` n'est pas un aboutissement : c'est l'état de naissance, et R-40 en fait un
    reste-à-faire tant qu'il n'est pas soldé. Le mot « proposition » n'est plus PRODUIT ici.
    """
    entree = adoptions.get(ref)
    if entree is None:
        return {"statut": A_ADOPTER, "test": "", "motif": ""}
    return entree


def est_a_adopter(valeur: object) -> bool:
    """Vrai si cet état est l'état de naissance — antériorité comprise.

    Les cahiers, dashboards et fichiers d'adoption écrits avant le 17/08 portent
    « proposition » : le lecteur les accepte tels quels plutôt que de les afficher en état
    inconnu, ce qui reviendrait à faire mentir un artefact que personne n'a modifié.
    """
    lu = str(valeur or A_ADOPTER)
    return lu == A_ADOPTER or lu in ETATS_ANTERIEURS_A_ADOPTER


def solde(etats: list[dict]) -> dict:
    """Solde R-40 d'un ensemble de cas dérivés : `dérivés − adoptés − non_testables − écartés`.

    Un solde non nul n'est pas une statistique : c'est le NOMBRE de cas dont personne n'a dit
    ce qu'ils devenaient. Les adoptions REFUSÉES y restent comptées — une déclaration
    invérifiable ne solde rien (RT-13 : sans quoi le solde descendrait sur du vide).
    """
    compte = {A_ADOPTER: 0, ADOPTE: 0, NON_TESTABLE: 0, ECARTE: 0, REFUSE: 0}
    for etat in etats:
        lu = (etat or {}).get("statut")
        cle = A_ADOPTER if est_a_adopter(lu) else str(lu)
        compte[cle] = compte.get(cle, 0) + 1
    derives = len(etats)
    return {
        "derives": derives,
        "adoptes": compte[ADOPTE],
        "non_testables": compte[NON_TESTABLE],
        "ecartes": compte[ECARTE],
        "refuses": compte[REFUSE],
        "a_adopter": compte[A_ADOPTER],
        "solde": derives - compte[ADOPTE] - compte[NON_TESTABLE] - compte[ECARTE],
    }


def cumuler(soldes: list[dict]) -> dict:
    """Somme de soldes (chapitre par chapitre, cahier par cahier) — le solde reste RECALCULÉ.

    Additionner les restes serait équivalent aujourd'hui, mais un état ajouté demain rendrait
    les deux valeurs divergentes sans qu'aucun test ne le voie.
    """
    total = {c: 0 for c in ("derives", "adoptes", "non_testables", "ecartes", "refuses",
                            "a_adopter")}
    for partiel in soldes:
        for cle in total:
            total[cle] += int((partiel or {}).get(cle) or 0)
    total["solde"] = total["derives"] - total["adoptes"] - total["non_testables"] - total["ecartes"]
    return total


def libelle_solde(compte: dict, non_couverts: int = 0) -> str:
    """Le solde en une ligne, PUBLIÉE telle quelle par les cahiers et le dashboard.

    Sans texte neutre ici, chaque livrable aurait reformulé le calcul à sa façon et deux
    livrables du même audit auraient pu se contredire sur le même chiffre.

    **TF-0355 — les deux chiffres sont OPPOSÉS, plus seulement voisins.** Un élément que le
    RAPPORT déclare `non_testable` (ou `exclu`) ne produit aucun cas dérivé : il sort en « non
    couvert », donc hors du solde, qui ne compte que des cas. Les deux colonnes coexistaient au
    tableau de tête sans que rien n oppose la seconde — « solde 0 » et « 8 éléments sans aucun
    cas » s écrivaient côte à côte, et seul le premier portait un verdict. C est exactement le
    faux confort que R-40 venait de tuer pour les cas, renaissant un cran plus haut, à l étage
    de la SURFACE. Un cahier n est donc SOLDÉ que si les deux valent zéro ; sinon la phrase
    nomme le reste et refuse la clôture, en distinguant la cause pour ne pas confondre deux
    dettes différentes.
    """
    reste = int(compte.get("solde") or 0)
    surface = max(0, int(non_couverts or 0))
    if not int(compte.get("derives") or 0):
        # Un périmètre sans aucun cas dérivé n a rien soldé : le déclarer « SOLDÉ » offrirait un
        # vert gratuit au chapitre le plus vide du cahier.
        vide = "solde R-40 : aucun cas dérivé sur ce périmètre — rien à solder"
        return vide + _rappel_surface(surface)
    detail = (
        f"{compte.get('derives', 0)} dérivés − {compte.get('adoptes', 0)} adoptés "
        f"− {compte.get('non_testables', 0)} non testables (motivés) "
        f"− {compte.get('ecartes', 0)} écartés"
    )
    if reste == 0:
        if not surface:
            return f"solde R-40 : {detail} = 0 — cahier SOLDÉ"
        return (
            f"solde R-40 : {detail} = 0 pour les cas, MAIS {surface} élément(s) inventorié(s) "
            "ne portent aucun cas dérivé — cahier NON CLOS : un solde de cas nul ne solde pas "
            "la surface"
        )
    refuses = int(compte.get("refuses") or 0)
    rappel = f", dont {refuses} adoption(s) refusée(s)" if refuses else ""
    return (
        f"solde R-40 : {detail} = {reste} cas NON SOLDÉ(S){rappel} — "
        "ce cahier porte un reste-à-faire, ce n'est pas un livrable clos"
    ) + _rappel_surface(surface)


def _rappel_surface(non_couverts: int) -> str:
    """La seconde dette, jamais fondue dans la première : elle se répare autrement."""
    if not non_couverts:
        return ""
    return (
        f" ; s y ajoutent {non_couverts} élément(s) inventorié(s) SANS AUCUN cas dérivé "
        "(déclarés `non_testable` ou `exclu` par le rapport) — ils se réparent en fournissant "
        "ce qui manque puis en rejouant, jamais en les déclarant au fichier d adoption"
    )


def references_inconnues(adoptions: dict[str, dict], refs_du_cahier: set[str]) -> list[str]:
    """Références déclarées adoptées qu'aucun cas du cahier courant ne porte."""
    return sorted(r for r in adoptions if not r.startswith("(ligne ") and r not in refs_du_cahier)
