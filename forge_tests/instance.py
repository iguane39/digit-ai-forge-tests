"""Cycle de vie et PROVENANCE de l instance servie — TF-0340 (cycle) / TF-0341 (provenance).

Six pans exigent une instance SERVIE : `front`, `qualif`, `accessibilite`, `visuel`,
`contraste` et `plancher`. Les deux derniers ont ete ajoutes le 23/08 (TF-0480) : `contraste`
mesurait deja les styles RENDUS depuis TF-0409 sans figurer ici — un pan qui exige une instance
servie et que le cycle de vie ignore, c est une instance qu on ne monte pas pour lui et qu on ne
demonte pas apres lui. Le
MONTAGE est délégué au projet, et c est le bon partage — lui seul sait ce que « peuplée » veut
dire chez lui. Mais jusqu au 18/08 le DÉMONTAGE n était délégué à personne, et aucune ligne du
rapport ne disait ce qui restait en service après l audit.

**Ce que ça a coûté, mesuré le 17/08 sur Produit-11.** `node e2e/preparer.mjs` monte 3 conteneurs et
un réseau (~4 min à froid) ; l audit se termine à 11:30 ; les conteneurs tiennent les ports
8091, 8092 et 5544 jusqu à 13:55 — 2 h 25 sans le moindre usage, jusqu à ce qu un humain s en
étonne. Au-delà de l encombrement, les ports sont pris : un second projet audité sur le même
poste, ou un second run du même projet, se heurte à une instance qu il n a pas montée sans
aucun moyen de savoir si elle est la sienne.

**Et la moitié grave (TF-0341).** La topologie auditée avait été bâtie à 10:47 depuis l arbre
de travail d alors ; le correctif D-14 (`src/02_get_advert.py`) a été écrit APRÈS. Entre 11:30
et 13:55, l instance servait donc un code ANTÉRIEUR au correctif, et rien ne l aurait signalé —
ni l instance, ni le rapport. Un audit relancé dans cette fenêtre aurait mesuré l ancien code et
publié ses chiffres comme l état courant du produit. Le risque n est pas la mémoire du poste,
c est de MESURER AUTRE CHOSE QUE CE QU ON CROIT, sans aucun signal.

La forge sait déjà nommer cette classe : `interface/ecart-servi` (TF-0288) confronte le SERVI au
VERSIONNÉ sur les liens d un `<nav>`. Ce module ne fait qu en généraliser le terme de
comparaison — de la page à L INSTANCE ENTIÈRE — et en reprend les trois issues, toutes
DÉCLARÉES au rapport, jamais devinées.

**Le format de provenance n est PAS inventé ici.** Le scellement d empreinte existe côté
forge-ops depuis TF-0288/TF-0298 : `ops.mjs deployer|canary` scelle `empreintes/<release>.json`
au format `forge-ops/empreinte@1` (`{format, release, ts, fichiers: {chemin: sha256}}`), et
`oracle-ops.mjs --empreinte` (O-7) le compare au servi. Ce module LIT ce format tel quel. Un
projet qui monte son instance localement, sans passer par forge-ops, déclare la forme légère
`forge-tests/instance@1` (`commit`, `construit_le`, `images[]`). Deux formes, toutes deux
DÉCLARÉES par le projet — aucune devinée.

**La règle, en une phrase** — celle que `REGLE` porte et que le rapport publie :

    la forge démonte ce qu elle a monté, et publie ce qu elle laisse debout quand elle ne l a
    pas monté.

C est la doctrine déjà tenue partout ailleurs ici : un SKIP muet est pire qu un SKIP déclaré ;
une instance laissée en service sans le dire est de la même famille.

**G-1 tenue** : rien n est jamais écrit chez l audité. Ce module lit des fichiers et interroge
git en lecture seule. Il n exécute AUCUNE commande de montage ou de démontage : la forge ne
monte pas aujourd hui, donc elle n a rien à démonter — elle PUBLIE ce qu elle trouve debout et
nomme la commande que le projet a déclarée pour le démonter. Le jour où la forge montera
elle-même, `contrat()` porte déjà les deux commandes qu il lui faudra.
"""

from __future__ import annotations

import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

# Les pans qui ne peuvent RIEN mesurer sans une instance servie. Liste tenue ici parce que
# c est ici qu on parle du cycle de vie de cette instance ; les adaptateurs, eux, revendiquent
# leurs champs (`CHAMPS_REQUIS`) et ne savent rien du montage.
PANS_SERVIS = ("front", "qualif", "accessibilite", "visuel", "contraste", "plancher")

# Le contrat que le PROJET déclare — deux commandes, comme l item l exige. Même canal que
# l URL de l instance (`FORGE_TESTS_BASE_URL`) : ce sont des champs de configuration, et
# `qualification.py` sait déjà nommer un champ manquant au rapport.
CHAMP_MONTER = "FORGE_TESTS_INSTANCE_MONTER"
CHAMP_DEMONTER = "FORGE_TESTS_INSTANCE_DEMONTER"
CHAMP_PROVENANCE = "FORGE_TESTS_INSTANCE_PROVENANCE"
CHAMPS_REQUIS = (CHAMP_MONTER, CHAMP_DEMONTER, CHAMP_PROVENANCE)

REGLE = (
    "la forge démonte ce qu elle a monté, et publie ce qu elle laisse debout quand elle ne l a "
    "pas monté"
)

# Les trois issues de la confrontation, reprises de TF-0288 — vocabulaire FERMÉ.
CONCORDANT = "concordant"
DIVERGENT = "divergent"
NON_DETERMINABLE = "non_determinable"

# La phrase qui compte, celle que l item réclame mot pour mot : sans elle, un lecteur corrige
# le code alors que c est l instance qui est en retard — exactement le développement inutile
# qu INS-0001 a failli déclencher.
PHRASE_DIVERGENT = "ce n est pas le code qui est en retard, c est l instance"

FORMATS_PROVENANCE = ("forge-ops/empreinte@1", "forge-tests/instance@1")

NON_JUGE = (
    "instance/cycle-de-vie : la forge ne MONTE pas l instance aujourd hui — le montage reste "
    "délégué au projet, qui seul sait ce que « peuplée » veut dire chez lui. Elle ne démonte "
    "donc rien : elle publie ce qu elle laisse debout et nomme la commande de démontage que le "
    "projet a déclarée. Le jour où elle montera, la règle s appliquera dans son premier sens",
    "instance/cycle-de-vie : ce qui est publié « debout » est ce que la CONFIGURATION déclare "
    "servi (URL, champs revendiqués par les pans), pas un balayage de ports ni un inventaire "
    "de conteneurs — sonder le poste dirait ce qui tourne, jamais ce qui appartient à cet "
    "audit, et accuserait l instance d un voisin",
    # TF-0842 : l exception, bornée, à la ligne ci-dessus — et pourquoi elle n en est pas une.
    "instance/cycle-de-vie (TF-0842) : `verifier_demontage` sonde LE port de L URL que cet "
    "audit a lui-même déclarée servie, jamais le poste. Il dit qu un port est TENU, pas QUI le "
    "tient : un socket ouvert ne nomme pas son propriétaire sans un droit et un outil que la "
    "forge n a pas. Un port repris entre-temps par un autre processus se lirait donc « encore "
    "tenu » — le doute va vers la vérification, jamais vers le silence",
    "instance/cycle-de-vie (TF-0842) : la forge ne vérifie pas ce que la commande de MONTAGE "
    "transmet à l instance. Une instance remontée sans les secrets de session que "
    "l application attend démarre, prend le port, et rend 500 au premier appel — indiscernable "
    "d une instance saine tant qu on ne l interroge pas. C est au projet de faire porter à "
    "FORGE_TESTS_INSTANCE_MONTER l environnement complet de son instance",
    "instance/provenance : le terme SERVI est le document de provenance DÉCLARÉ par le projet, "
    "jamais une introspection de l instance en service — interroger un conteneur supposerait un "
    "runtime, un droit et une topologie que la forge ne connaît pas, et ferait dépendre le "
    "verdict de l outil d inspection au lieu du produit",
    "instance/provenance : le terme VERSIONNÉ est le WORKING TREE de la cible, comme pour "
    "`interface/ecart-servi` (TF-0288) — un produit hors git n a donc pas de commit opposable, "
    "seulement des fichiers ; la comparaison par empreintes de fichiers reste jouable et le dit",
    "instance/provenance : la comparaison n est pas symétrique. Un fichier PRÉSENT dans "
    "l empreinte scellée et modifié depuis est un écart ; un fichier neuf dans l arbre de "
    "travail, que l empreinte ne connaît pas, n en est PAS un — il peut n avoir jamais eu à "
    "être déployé. Seul ce que le SERVI prétend porter est confronté",
)


def contrat(env: dict[str, str] | None = None) -> dict:
    """Les deux commandes de cycle de vie déclarées par le projet (TF-0340).

    Rend toujours les deux clés, à `None` quand elles manquent : une clé absente serait
    indiscernable d une commande vide, et c est précisément le silence qu on ferme ici.
    """
    e = os.environ if env is None else env
    monter = (e.get(CHAMP_MONTER) or "").strip() or None
    demonter = (e.get(CHAMP_DEMONTER) or "").strip() or None
    return {
        "monter": monter,
        "demonter": demonter,
        "declare": bool(monter and demonter),
        "champs": list(CHAMPS_REQUIS[:2]),
    }


def _url_servie(env: dict[str, str] | None = None) -> list[str]:
    """Ce que la configuration déclare SERVI — jamais un balayage de ports (cf. `NON_JUGE`)."""
    e = os.environ if env is None else env
    vues, urls = set(), []
    for champ in ("FORGE_TESTS_BASE_URL", "FORGE_TESTS_QUALIF_URL", "FORGE_TESTS_API_URL"):
        val = (e.get(champ) or "").strip()
        if val and val not in vues:
            vues.add(val)
            urls.append({"champ": champ, "url": val})
    return urls


def cycle_de_vie(env: dict[str, str] | None = None, monte_par_la_forge: bool = False) -> dict:
    """Ce que l audit laisse en service, et par quelle commande le démonter (TF-0340)."""
    c = contrat(env)
    servies = _url_servie(env)
    if monte_par_la_forge:
        # Premier sens de la règle. Inatteignable aujourd hui (la forge ne monte pas), écrit
        # pour que le jour où elle montera, le contrat soit déjà celui-ci et non un ajout.
        etat = "montee_par_la_forge"
        consigne = ("la forge a monté cette instance : elle la démonte, sans rien demander"
                    " à personne")
    elif not servies:
        etat = "aucune_instance_declaree"
        consigne = "aucune URL servie déclarée — rien n est laissé debout par cet audit"
    elif c["demonter"]:
        etat = "laissee_debout"
        # TF-0842 : la commande ne suffit plus à clore la consigne. Une commande de démontage
        # qui rend 0 sans rien démonter est indiscernable d un démontage réussi — seul le port
        # le dit, et la vérification est nommée ICI parce que c est ici qu on lit la consigne.
        consigne = (
            "instance NON montée par la forge, laissée en service : la démonter avec "
            f"`{c['demonter']}`, PUIS vérifier que le port est libre — "
            "`python -m forge_tests.instance --verifier-demontage`"
        )
    else:
        etat = "laissee_debout_sans_commande"
        consigne = (
            "instance NON montée par la forge, laissée en service, et AUCUNE commande de "
            f"démontage déclarée : la déclarer dans `{CHAMP_DEMONTER}` — sans elle, le prochain "
            "audit du même poste se heurtera à des ports pris sans savoir à qui ils sont"
        )
    return {
        "regle": REGLE,
        "etat": etat,
        "consigne": consigne,
        "contrat_declare": c["declare"],
        "monter": c["monter"],
        "demonter": c["demonter"],
        "laisse_en_service": servies,
        "pans_concernes": list(PANS_SERVIS),
    }


# --- Ce que le DÉMONTAGE a réellement libéré (TF-0842) -------------------------------------------
# LE FAIT (lot Produit-61, 05/09/2026). L instance remontée pour l audit n avait pas la clé de
# session que l application attend, et la commande de démontage déclarée — `taskkill /IM
# uvicorn.exe` — ne tuait rien : un `uvicorn` lancé par `uv run` ne s appelle pas `uvicorn.exe`,
# c est un `python.exe` enfant de `uv`. Résultat : une instance SANS CLÉ occupait le port après
# l audit, le smoke M-3 rendait 500, et il a fallu une demi-heure et trois relances pour
# comprendre que la commande de démontage avait rendu la main sans rien démonter.
#
# Une commande de démontage qui rend 0 sans démonter est indiscernable d un démontage réussi.
# Seul le PORT le dit. C est la seule chose que ce module sonde, et la frontière tient :
#
#   - on ne BALAIE pas le poste — le `NON_JUGE` de ce module l interdit et la raison n a pas
#     bougé : un balayage accuserait l instance d un voisin. On sonde LE port de L URL que cet
#     audit a lui-même déclarée servie, et rien d autre ;
#   - on ne dit pas QUI tient le port : un socket ouvert ne nomme pas son propriétaire sans un
#     droit et un outil que la forge n a pas. On dit qu il est TENU, ce qui suffit à démentir
#     « démonté ».
_DELAI_SONDE_S = 1.0

PORT_LIBRE = "libre"
PORT_OCCUPE = "occupe"
PORT_INDETERMINABLE = "indeterminable"

#: Ce que la mesure du 05/09 a nommé, et qu une consigne doit porter pour être utile.
CONSIGNE_PORT_TENU = (
    "le port est ENCORE TENU après la commande de démontage : elle a rendu la main sans "
    "démonter. Cas mesuré : `taskkill /IM uvicorn.exe` ne tue pas un uvicorn lancé par "
    "`uv run` — le processus s appelle `python.exe` et il est ENFANT de `uv`. Démonter PAR LE "
    "PORT (`npx kill-port <port>`, `fuser -k <port>/tcp`, ou l identifiant rendu par "
    "`netstat -ano | findstr :<port>` puis `taskkill /PID <pid> /F`), puis revérifier"
)


def _hote_port(url: str) -> tuple[str | None, int | None]:
    """Hôte et port d une URL servie — le port par défaut du schéma quand il est implicite."""
    from urllib.parse import urlparse

    lu = urlparse(url if "://" in url else f"http://{url}")
    if not lu.hostname:
        return None, None
    port = lu.port or {"http": 80, "https": 443}.get(lu.scheme)
    return lu.hostname, port


def sonder_port(url: str, delai: float = _DELAI_SONDE_S) -> dict:
    """L état du port de cette URL : `libre`, `occupe`, ou `indeterminable` AVEC son motif."""
    import socket

    hote, port = _hote_port(url)
    if hote is None or port is None:
        return {
            "url": url,
            "hote": hote,
            "port": port,
            "etat": PORT_INDETERMINABLE,
            "motif": f"URL sans hôte ni port exploitable : {url!r}",
        }
    socle = {"url": url, "hote": hote, "port": port}
    try:
        with socket.create_connection((hote, port), timeout=delai):
            return {**socle, "etat": PORT_OCCUPE, "motif": None}
    except (TimeoutError, ConnectionRefusedError):
        return {**socle, "etat": PORT_LIBRE, "motif": None}
    except OSError as erreur:
        return {
            **socle,
            "etat": PORT_INDETERMINABLE,
            "motif": f"sonde impossible ({type(erreur).__name__}: {erreur})",
        }


def verifier_demontage(env: dict[str, str] | None = None, delai: float = _DELAI_SONDE_S) -> dict:
    """Ce que la commande de démontage a RÉELLEMENT libéré (TF-0842).

    À jouer APRÈS `FORGE_TESTS_INSTANCE_DEMONTER`. Rend un verdict fermé :

      - `libere` — aucun port déclaré n est plus tenu ;
      - `encore_tenu` — au moins un l est, avec la consigne qui nomme le remède mesuré ;
      - `non_verifiable` — aucune URL déclarée, ou aucun port sondable, et on le DIT.
    """
    servies = _url_servie(env)
    if not servies:
        return {
            "verdict": "non_verifiable",
            "motif": "aucune URL servie déclarée : il n y a pas de port dont vérifier la "
            "libération",
            "ports": [],
            "consigne": None,
        }
    ports = [sonder_port(entree["url"], delai) for entree in servies]
    tenus = [p for p in ports if p["etat"] == PORT_OCCUPE]
    if tenus:
        return {
            "verdict": "encore_tenu",
            "motif": "port(s) encore tenu(s) après démontage : "
            + ", ".join(f"{p['hote']}:{p['port']}" for p in tenus),
            "ports": ports,
            "consigne": CONSIGNE_PORT_TENU,
        }
    if all(p["etat"] == PORT_INDETERMINABLE for p in ports):
        return {
            "verdict": "non_verifiable",
            "motif": "aucun port sondable — "
            + " · ".join(str(p["motif"]) for p in ports if p["motif"]),
            "ports": ports,
            "consigne": None,
        }
    return {
        "verdict": "libere",
        "motif": "aucun port déclaré n est plus tenu",
        "ports": ports,
        "consigne": None,
    }


def _sha256_fichier(p: Path) -> str | None:
    try:
        return sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _commit_arbre(cible: Path) -> tuple[str | None, str | None]:
    """HEAD du working tree audité, et le motif quand il n y en a pas. Lecture seule."""
    try:
        r = subprocess.run(
            ["git", "-C", str(cible), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as err:
        return None, f"git injouable sur la cible ({type(err).__name__})"
    if r.returncode != 0:
        return None, ("la cible n est pas un dépôt git — aucun commit opposable (seulement"
                      " des fichiers)")
    return r.stdout.strip() or None, None


def _lire_provenance(chemin: Path) -> tuple[dict | None, str | None]:
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
    except OSError:
        return None, f"document de provenance introuvable ou illisible : {chemin}"
    except json.JSONDecodeError as err:
        return None, f"document de provenance non JSON ({chemin}) : {err.msg}"
    if not isinstance(doc, dict):
        return None, f"document de provenance non conforme ({chemin}) : objet JSON attendu"
    fmt = doc.get("format")
    if fmt not in FORMATS_PROVENANCE:
        connus = ", ".join(FORMATS_PROVENANCE)
        return None, f"format de provenance inconnu « {fmt} » ({chemin}) — formats lus : {connus}"
    return doc, None


def provenance(cible: Path, env: dict[str, str] | None = None) -> dict:
    """Confronte de quoi l instance a été bâtie à l arbre de travail audité (TF-0341).

    Trois issues, toutes déclarées : `concordant`, `divergent` (l écart NOMMÉ, plus la phrase
    qui compte), `non_determinable` (en disant LEQUEL des deux termes manque).
    """
    e = os.environ if env is None else env
    declare = (e.get(CHAMP_PROVENANCE) or "").strip()
    commit_arbre, motif_git = _commit_arbre(cible)

    if not declare:
        return {
            "issue": NON_DETERMINABLE,
            "terme_manquant": "servi",
            "motif": (
                "aucun document de provenance déclaré : le terme SERVI manque — de quoi "
                "l instance a été bâtie n est écrit nulle part, donc rien ne distingue une "
                f"instance fraîche d une instance périmée. Le déclarer dans `{CHAMP_PROVENANCE}` "
                "(scellé `forge-ops/empreinte@1` produit par `ops.mjs deployer|canary`, ou "
                "`forge-tests/instance@1` pour un montage local)"
            ),
            "versionne": {"commit": commit_arbre, "motif": motif_git},
            "servi": None,
        }

    doc, motif = _lire_provenance(Path(declare))
    if doc is None:
        return {
            "issue": NON_DETERMINABLE,
            "terme_manquant": "servi",
            "motif": (f"{motif} — le terme SERVI est déclaré mais pas lisible, donc l écart"
                      " n est pas mesurable"),
            "versionne": {"commit": commit_arbre, "motif": motif_git},
            "servi": {"chemin": declare},
        }

    fmt = doc["format"]
    servi = {
        "chemin": declare,
        "format": fmt,
        "construit_le": doc.get("ts") or doc.get("construit_le"),
        "release": doc.get("release"),
        "commit": doc.get("commit"),
        "images": doc.get("images"),
    }

    # Forme forge-ops : la comparaison porte sur les EMPREINTES DE FICHIERS scellées — c est le
    # terme le plus précis des deux, et c est celui que O-7 utilise déjà.
    fichiers = doc.get("fichiers")
    if fmt == "forge-ops/empreinte@1" and isinstance(fichiers, dict) and fichiers:
        modifies, disparus = [], []
        for rel, sha_scelle in sorted(fichiers.items()):
            actuel = _sha256_fichier(cible / rel)
            if actuel is None:
                disparus.append(rel)
            elif actuel != sha_scelle:
                modifies.append(rel)
        servi["fichiers_scelles"] = len(fichiers)
        if not modifies and not disparus:
            return {
                "issue": CONCORDANT,
                "motif": (
                    f"{len(fichiers)} fichier(s) scellé(s) au montage, tous identiques dans "
                    "l arbre de travail audité : l instance sert bien le code mesuré"
                ),
                "versionne": {"commit": commit_arbre, "motif": motif_git},
                "servi": servi,
            }
        ecarts = [f"{r} (modifié depuis le scellement)" for r in modifies]
        ecarts += [f"{r} (absent de l arbre de travail)" for r in disparus]
        return {
            "issue": DIVERGENT,
            "motif": (
                f"{len(modifies) + len(disparus)} écart(s) entre le code scellé au montage de "
                f"l instance et l arbre de travail audité — {PHRASE_DIVERGENT} : les chiffres de "
                "cet audit portent sur un code qui n est plus celui du dépôt. Remonter "
                "l instance avant de conclure"
            ),
            "ecarts": ecarts[:20],
            "ecarts_total": len(modifies) + len(disparus),
            "versionne": {"commit": commit_arbre, "motif": motif_git},
            "servi": servi,
        }

    # Forme légère : la comparaison porte sur le COMMIT. Moins précise, et elle le dit.
    commit_servi = doc.get("commit")
    if not commit_servi:
        return {
            "issue": NON_DETERMINABLE,
            "terme_manquant": "servi",
            "motif": (
                f"provenance `{fmt}` sans `commit` ni `fichiers` : le document existe mais ne "
                "porte aucun terme comparable — de quoi l instance a été bâtie reste inconnu"
            ),
            "versionne": {"commit": commit_arbre, "motif": motif_git},
            "servi": servi,
        }
    if commit_arbre is None:
        return {
            "issue": NON_DETERMINABLE,
            "terme_manquant": "versionne",
            "motif": (
                f"le terme VERSIONNÉ manque : {motif_git}. La provenance déclare le commit "
                f"{commit_servi[:12]}, mais il n y a rien à quoi l opposer"
            ),
            "versionne": {"commit": None, "motif": motif_git},
            "servi": servi,
        }
    if commit_servi == commit_arbre:
        return {
            "issue": CONCORDANT,
            "motif": (
                f"l instance a été bâtie depuis le commit {commit_servi[:12]}, celui de l arbre "
                "de travail audité"
            ),
            "versionne": {"commit": commit_arbre, "motif": None},
            "servi": servi,
        }
    return {
        "issue": DIVERGENT,
        "motif": (
            f"l instance a été bâtie depuis {commit_servi[:12]}, l arbre de travail audité est "
            f"en {commit_arbre[:12]} — {PHRASE_DIVERGENT} : les chiffres de cet audit portent "
            "sur un code qui n est plus celui du dépôt. Remonter l instance avant de conclure"
        ),
        "ecarts": [f"commit servi {commit_servi[:12]} ≠ commit audité {commit_arbre[:12]}"],
        "ecarts_total": 1,
        "versionne": {"commit": commit_arbre, "motif": None},
        "servi": servi,
    }


def au_rapport(
    cible: Path,
    env: dict[str, str] | None = None,
    monte_par_la_forge: bool = False,
) -> dict:
    """La section `instance` du rapport JSON — TOUJOURS présente, même sans instance.

    Une section qui disparaîtrait quand aucune instance n est déclarée serait indiscernable
    d une section qui a mesuré et n a rien trouvé : c est le silence que ce framework interdit
    partout ailleurs.
    """
    return {
        "cycle_de_vie": cycle_de_vie(env, monte_par_la_forge=monte_par_la_forge),
        "provenance": provenance(cible, env),
        "non_juge": list(NON_JUGE),
    }


if __name__ == "__main__":
    # TF-0842 — le geste qui manquait, et qui ne peut pas vivre dans l audit : la vérification
    # se joue APRÈS la commande de démontage, donc après la fin de l audit. Même forme d appel
    # que `python -m forge_tests.dette` : un module, une intention, aucun argument à retenir.
    import sys

    if "--verifier-demontage" not in sys.argv[1:]:
        print(
            "usage : python -m forge_tests.instance --verifier-demontage\n"
            "\n"
            "  À jouer APRÈS la commande déclarée dans FORGE_TESTS_INSTANCE_DEMONTER. Sonde le\n"
            "  port de chaque URL que cet audit a déclarée servie (FORGE_TESTS_BASE_URL,\n"
            "  _QUALIF_URL, _API_URL) et dit s il est encore tenu.\n"
            "\n"
            "  Codes : 0 libéré · 1 encore tenu · 3 non vérifiable (motif imprimé)."
        )
        sys.exit(0)

    _verdict = verifier_demontage()
    print(f"démontage : {_verdict['verdict']} — {_verdict['motif']}")
    for _port in _verdict["ports"]:
        _detail = f" ({_port['motif']})" if _port["motif"] else ""
        print(f"  {_port['hote']}:{_port['port']} — {_port['etat']}{_detail}")
    if _verdict["consigne"]:
        print(f"  → {_verdict['consigne']}")
    sys.exit(
        {"libere": 0, "encore_tenu": 1, "non_verifiable": 3}[str(_verdict["verdict"])]
    )
