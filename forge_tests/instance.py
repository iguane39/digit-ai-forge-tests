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
        consigne = ("instance NON montée par la forge, laissée en service : la démonter avec"
                    f" `{c['demonter']}`")
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
