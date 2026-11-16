"""Déclarations du projet sur les CONSTATS d audit — le canal de réponse qui manquait.

RT-18 (majeur, 14/08) : « un constat réfuté par le projet revient à chaque audit,
indéfiniment ». Fait mesuré par le produit : RT-1 et RT-2 remis le 13/08, les 13 findings
correspondants revenus identiques le 14/08, sur six audits successifs. Rien ne permettait au
projet de dire une fois « ce constat est contesté, voici la contre-preuve », et rien ne
permettait à l auditeur d en tenir compte. Le projet tenait donc sa déclaration à côté
(`forge/constats-contestes.jsonl`, 14 lignes), invisible au rapport.

C est le TROISIÈME retour du même manque, et un seul mécanisme les couvre tous les trois :

  - **RT-13** — un cas dérivé écrit par le projet doit pouvoir être ADOPTÉ. Déjà livré :
    `forge_tests.adoption` (`forge/cas-adoptes.jsonl`). Ce module ne le refait pas — il le
    CITE : le motif `adopte` est du vocabulaire connu ici, mais sa déclaration vit là-bas, et
    une ligne `adopte` déposée dans ce fichier-ci est refusée en le disant ;
  - **RT-15** — un mutant d un module que le point d entrée déployé SUPPLANTE
    (`azure/standalone_backend.py` redéfinit trois routes), ou un élément qu une configuration
    laisse `disabled` : le tuer demanderait d exercer du code que le produit livré n atteint
    jamais. Motifs `bloque-code-supplante` et `bloque-configuration` ;
  - **RT-18** — le constat CONTESTÉ, avec le test qui établit le contraire. Motif `conteste`.

**Le contrat, tenu par ce module :**

    <projet>/forge/constats-contestes.jsonl   — une ligne JSON par constat déclaré :
    {"constat": "qualif/qualif:effet:/:0:form", "motif": "conteste",
     "preuve": "frontend/tests/e2e/10-formulaire.spec.ts", "par": "equipe-front",
     "date": "2026-08-14", "expire_le": "2026-11-14", "explication": "…"}

`constat` est la clé de jointure du rapport : `<pan>/<id du finding>` — la MÊME que
`actions[].finding_ref`. La forme courte `<id>` est acceptée (elle vise alors le constat quel
que soit son pan) ; `classe` restreint la déclaration à une classe de finding précise quand un
même élément en porte plusieurs. C est le PROJET qui déclare, jamais la forge, et le fichier
est lu en LECTURE SEULE (G-1) : rien n est jamais écrit chez l audité.

**Ancrage stable (TF-1672).** Un identifiant qui porte un numéro de ligne
(`interface:…/coquille.tsx:203:a`) change dès que le code se décale : chez Produit-80, le
constat contesté le 30/09 est revenu non déclaré sous `:205:a` après l ajout de deux entrées
de menu. Le champ facultatif `texte` ancre la déclaration sur le MESSAGE du constat : elle vise
alors le constat de même forme sans numéro de ligne (même pan, même fichier, même balise) et de
même texte, où qu il soit passé, et ne vise plus l ancienne ligne si un autre constat l occupe.
Une déclaration sans `texte`, écrite avant ce champ, garde la jointure exacte ; orpheline, elle
est rapprochée du seul constat libre de même forme, et le rapprochement est publié au rapport
(`declarations.rapprochees`). Plusieurs candidats : rien n est deviné, la déclaration reste
inconnue et ses candidats sont nommés (`declarations.ambigues`).

**Ancrage par empreinte de ligne (TF-2664).** Quand plusieurs constats partagent le MÊME message
(cinq constats SAST de même règle dans un fichier), `texte` ne distingue plus rien : après trois
commits qui décalent des lignes, les cinq déclarations rendaient chacune cinq candidats, et les
cinq constats contestés le matin revenaient comme nouveaux. Le champ facultatif `empreinte` porte
l empreinte de la LIGNE VISÉE (`empreinte_de_ligne` : son texte, blancs normalisés, seize
caractères hexadécimaux) ; le rapport publie celle des constats qu un même message ne distingue
pas (`declarations.empreintes`). La déclaration vise alors le constat dont la ligne a cette
empreinte, quel que soit son numéro, et ne vise plus une ancienne ligne qu occupe un autre
constat. Une ligne réécrite ne se suit pas : la déclaration reste sans constat, et le rapport la
nomme (`declarations.inconnues`).

**Deux constats, un identifiant (TF-2658).** Deux constats SAST distincts sur la même ligne
partagent un identifiant et ne diffèrent que par leur message : le doublon se juge sur le couple
`constat` + `texte` quand `texte` est fourni, et leurs deux déclarations sont retenues.

**Quatre règles, toutes vérifiées, sans lesquelles ce canal deviendrait un bouton « faire
taire » :**

  1. **contre-preuve obligatoire** — la déclaration cite un chemin (`preuve`) qui doit
     EXISTER dans le projet : le test qui établit le contraire pour `conteste`, le point
     d entrée qui supplante ou le fichier de configuration qui désactive pour les motifs
     bloqués. Introuvable → déclaration REFUSÉE avec son motif, exactement comme
     `adoption.charger` refuse une adoption dont le test n existe pas, et le constat reste au
     décompte principal ;
  2. **motif TYPÉ** — hors du vocabulaire `MOTIFS`, la déclaration est refusée. Une prose
     libre ne se relit pas et ne se compte pas ;
  3. **datée et signée** — `par` (qui déclare) et `date` (quand) sont obligatoires. Sans date,
     une déclaration se périmerait sans que personne le sache : elle est donc bornée, par
     `expire_le` si le projet le fixe, sinon à `PEREMPTION_JOURS` jours. Passé ce terme la
     déclaration est PÉRIMÉE — le constat revient au décompte principal, en le disant ;
  4. **comptabilisé à part, jamais supprimé** — un constat déclaré RESTE dans `findings`
     (donc dans l inventaire de surface, donc au dashboard) : il porte un champ `declaration`
     et sort du décompte principal (`bandes_de_risque`, tuile « Constats d échec », liste des
     actions). La mesure reste opposable, et la contestation aussi : un relecteur la lit, avec
     sa contre-preuve, et peut l attaquer.

Ce module ne juge pas si la contre-preuve DIT ce qu elle prétend — il constate une déclaration
et l existence de son support. Vérifier qu un test affirme ce qu il annonce est le rôle de la
mutation, pas d une déclaration.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path

from forge_tests import adoption as _adoption

FICHIER = "forge/constats-contestes.jsonl"

# Terme par défaut d une déclaration qui n en fixe pas. Une contestation sans fin serait un
# effacement : au bout de ce délai, le constat revient au décompte et la déclaration se renouvelle.
PEREMPTION_JOURS = 180

RETENUE, REFUSEE, PERIMEE, AUCUNE = "retenue", "refusee", "perimee", "aucune"

# Vocabulaire des motifs. Une déclaration hors de cette table est refusée : c est ce qui rend
# les trois familles de RT comptables séparément au lieu de se fondre en « ignoré ».
MOTIFS: dict[str, dict[str, str]] = {
    "conteste": {
        "libelle": "constat contesté",
        "retour": "RT-18",
        "preuve_attendue": "le chemin du test qui établit le CONTRAIRE du constat",
    },
    "bloque-configuration": {
        "libelle": "bloqué par une configuration absente ou désactivée",
        "retour": "RT-15",
        "preuve_attendue": "le chemin du fichier de configuration qui montre l élément "
        "désactivé ou non déployé",
    },
    "bloque-code-supplante": {
        "libelle": "bloqué par du code supplanté au déploiement",
        "retour": "RT-15",
        "preuve_attendue": "le chemin du point d entrée déployé qui redéfinit ou supplante le "
        "code visé — le produit livré ne l atteint jamais",
    },
    "adopte": {
        "libelle": "cas dérivé adopté par le projet",
        "retour": "RT-13",
        "preuve_attendue": "le chemin du test qui joue le cas",
        # Déjà livré : ce module ne le refait pas, il y renvoie.
        "delegue": _adoption.FICHIER,
    },
}

NON_JUGE = [
    "declarations : le fichier `forge/constats-contestes.jsonl` est une DECLARATION du projet — "
    "ce module verifie que la preuve citee EXISTE, jamais qu elle etablit ce qu elle pretend "
    "(c est le role de la mutation et de l execution)",
    "declarations : un constat ecarte reste MESURE et reste au rapport ; il sort du decompte "
    "principal, il ne sort pas de l inventaire — la mesure demeure opposable, la declaration aussi",
    "declarations : la peremption se juge sur la DATE DECLAREE par le projet, jamais sur une "
    "horloge externe — une date postee en avant differe le terme d autant, et cela se lit",
    "declarations : une declaration qui ne vise aucun constat du rapport courant sort en "
    "INCONNUE, declaree telle quelle — le constat a pu disparaitre, ou l identifiant changer ; "
    "seul le numero de ligne qui suit un nom de fichier est rapproche (TF-1672), tout autre "
    "changement d identifiant reste INCONNU",
    "declarations : une declaration SANS `texte` rapprochee par la seule forme sans numero de "
    "ligne (fichier, balise, classe) vise le seul constat libre de cette forme ; si le constat "
    "conteste a disparu et qu un AUTRE de meme forme est apparu, c est lui qui est ecarte — le "
    "rapprochement est donc publie au rapport, jamais tu, et `texte` le rend exact",
]


# --- Lecture de la déclaration ------------------------------------------------------------------
def _date(valeur: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(valeur)
    except ValueError:
        return None


def _refus(entree: dict, pourquoi: str, statut: str = REFUSEE) -> dict:
    return {**entree, "statut": statut, "motif_du_refus": pourquoi}


def charger(cible: Path, aujourdhui: _dt.date | None = None) -> dict[str, dict]:
    """Déclarations du projet, chacune avec son verdict de vérification.

    Renvoie `{constat: entrée}` où l entrée porte toujours `statut` (`retenue`, `refusee`,
    `perimee`) et, pour les deux derniers, `motif_du_refus`. Fichier absent = aucune
    déclaration : ce n est pas une faute, c est l état initial — et c est aussi le cas de tous
    les projets qui ignorent que ce canal existe.
    """
    source = Path(cible) / FICHIER
    if not source.is_file():
        return {}
    jour = aujourdhui or _dt.date.today()
    declarations: dict[str, dict] = {}
    for rang, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        base = {"ligne": rang, "constat": "", "motif": "", "preuve": "", "par": "", "date": "",
                "expire_le": "", "explication": "", "classe": "", "texte": "", "empreinte": ""}
        try:
            brut = json.loads(ligne)
        except json.JSONDecodeError:
            declarations[f"(ligne {rang})"] = _refus(
                base, f"ligne {rang} de {FICHIER} : JSON invalide — declaration ignoree"
            )
            continue
        if not isinstance(brut, dict):
            declarations[f"(ligne {rang})"] = _refus(
                base, f"ligne {rang} de {FICHIER} : objet JSON attendu — declaration ignoree"
            )
            continue
        entree = {
            **base,
            **{
                cle: str(brut.get(cle) or "").strip()
                for cle in ("constat", "motif", "preuve", "par", "date", "expire_le",
                            "explication", "classe", "texte", "empreinte")
            },
        }
        cle = entree["constat"] or f"(ligne {rang})"
        # TF-2658 : le doublon se juge sur le COUPLE `constat` + `texte` quand `texte` est fourni.
        # Deux constats SAST distincts sur la même ligne partagent un identifiant et ne se
        # distinguent que par leur message : leurs deux déclarations, de `texte` différents, sont
        # deux déclarations, pas un doublon. Sans `texte` d'un côté ou de l'autre, la déclaration
        # vise tout message du constat : la seconde la recoupe, et reste refusée.
        voisines = [
            e for k, e in declarations.items()
            if entree["constat"] and e.get("constat") == entree["constat"]
            and not k.startswith("(ligne ")
        ]
        if voisines:
            texte = _texte(entree["texte"])
            if not texte or any(_texte(v.get("texte")) in ("", texte) for v in voisines):
                # Le doublon ne remplace pas silencieusement : deux déclarations sur un même
                # constat sont un désaccord interne au projet, et il se lit.
                declarations[f"(ligne {rang})"] = _refus(
                    entree,
                    f"doublon : « {entree['constat']} » est deja declare"
                    + (" avec le meme texte" if texte else "")
                    + f" ligne {voisines[0].get('ligne')} — la premiere declaration fait foi",
                )
                continue
            # Le constat est déjà une clé : la déclaration à `texte` distinct prend la clé composée.
            cle = f"{entree['constat']} · {texte}"
        declarations[cle] = _verifier(entree, Path(cible), jour)
    return declarations


def _verifier(entree: dict, cible: Path, jour: _dt.date) -> dict:
    """Verdict d UNE déclaration : les quatre règles, dans l ordre où elles se lisent."""
    if not entree["constat"]:
        return _refus(entree, "aucun constat vise — une declaration sans cible ne s applique pas")

    motif = entree["motif"]
    if not motif:
        return _refus(
            entree,
            "aucun motif type — motifs admis : " + ", ".join(sorted(MOTIFS)),
        )
    if motif not in MOTIFS:
        return _refus(
            entree,
            f"motif « {motif} » hors vocabulaire — motifs admis : " + ", ".join(sorted(MOTIFS)),
        )
    delegue = MOTIFS[motif].get("delegue")
    if delegue:
        return _refus(
            entree,
            f"le motif « {motif} » se declare dans `{delegue}` (RT-13), pas ici — "
            "un cas adopte est verifie par `forge_tests.adoption`, ce fichier porte les "
            "constats ecartes",
        )

    if not entree["par"]:
        return _refus(
            entree, "declaration non signee (`par` absent) — qui declare fait partie de la preuve"
        )
    if not entree["date"]:
        return _refus(
            entree,
            "declaration non datee (`date` absente, format AAAA-MM-JJ) — sans date, elle se "
            "perimerait sans que personne le sache",
        )
    posee = _date(entree["date"])
    if posee is None:
        return _refus(
            entree, f"date « {entree['date']} » illisible — format attendu AAAA-MM-JJ"
        )

    if not entree["preuve"]:
        return _refus(
            entree,
            "aucune preuve citee — "
            + MOTIFS[motif]["preuve_attendue"]
            + " ; un constat conteste sans preuve a l appui reste au rapport",
        )
    if not (Path(cible) / entree["preuve"]).exists():
        return _refus(
            entree,
            f"la preuve citee est introuvable ({entree['preuve']}) — declaration refusee, le "
            "constat reste au decompte",
        )

    if entree["expire_le"]:
        terme = _date(entree["expire_le"])
        if terme is None:
            return _refus(
                entree,
                f"date de peremption « {entree['expire_le']} » illisible — format attendu "
                "AAAA-MM-JJ",
            )
    else:
        terme = posee + _dt.timedelta(days=PEREMPTION_JOURS)
    if terme < jour:
        return _refus(
            entree,
            f"declaration perimee le {terme.isoformat()} (posee le {entree['date']}"
            + (
                f", terme declare {entree['expire_le']}"
                if entree["expire_le"]
                else f", terme par defaut a {PEREMPTION_JOURS} jours"
            )
            + ") — a renouveler ou a retirer ; le constat revient au decompte",
            statut=PERIMEE,
        )
    return {**entree, "statut": RETENUE, "motif_du_refus": "", "terme": terme.isoformat()}


# --- Rapprochement avec les constats du rapport --------------------------------------------------
def cles_du_finding(finding: dict) -> tuple[str, str]:
    """Les deux clés sous lesquelles un constat est citable : `<pan>/<id>` et `<id>` seul."""
    pan = str(finding.get("pan") or "")
    identifiant = str(finding.get("id") or "")
    return (f"{pan}/{identifiant}" if pan else identifiant, identifiant)


#: Le numéro de ligne qui suit un nom de fichier dans un identifiant : `coquille.tsx:203:a`.
_LIGNE_APRES_FICHIER = re.compile(r"(\.[A-Za-z0-9]{1,8}):\d+(?=[:#]|$)")


def forme_stable(cle: str) -> str:
    """La clé SANS le numéro de ligne qui suit un nom de fichier — TF-1672.

    `interface/interface:src/coquille.tsx:203:a` → `interface/interface:src/coquille.tsx:*:a`.
    Seul ce numéro-là est masqué : un rang ou un index qui ne suit pas un fichier fait partie de
    l identité du constat, le masquer rapprocherait deux constats différents.
    """
    return _LIGNE_APRES_FICHIER.sub(r"\1:*", cle)


def _texte(valeur: object) -> str:
    return " ".join(str(valeur or "").split())


def empreinte_de_ligne(texte: str) -> str:
    """L empreinte d une LIGNE de source — TF-2664 : son texte, blancs et fin de ligne normalisés.

    Seize caractères hexadécimaux. Le champ `empreinte` d une déclaration porte celle de la ligne
    visée ; le rapport publie celle des constats que leur message seul ne distingue pas
    (`declarations.empreintes`).
    """
    return hashlib.sha256(" ".join(str(texte).split()).encode("utf-8")).hexdigest()[:16]


#: La position d un constat : `<chemin>:<ligne>`, éventuellement suivie d un détail.
_POSITION = re.compile(r"^(?P<chemin>.+?):(?P<ligne>\d+)(?=$|[:\s·])")


def lecteur_de_lignes(cible: Path):
    """Un lecteur `constat -> empreinte de sa ligne`, ou `None` quand la ligne n est pas lisible.

    La ligne se lit à la `localisation` du constat (`app/requetes.py:12`, relative à la racine
    auditée ou absolue), et seulement SOUS cette racine : une localisation qui en sort n est pas
    lue. Lecture seule (G-1), un fichier lu une fois.
    """
    racine = Path(cible).resolve()
    cache: dict[Path, list[str] | None] = {}

    def lire(finding: dict) -> str | None:
        trouve = _POSITION.match(str(finding.get("localisation") or ""))
        if trouve is None:
            return None
        chemin = Path(trouve["chemin"])
        chemin = (chemin if chemin.is_absolute() else racine / chemin).resolve()
        try:
            chemin.relative_to(racine)
        except ValueError:
            return None
        if chemin not in cache:
            try:
                cache[chemin] = chemin.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                cache[chemin] = None
        lignes = cache[chemin]
        rang = int(trouve["ligne"])
        if lignes is None or not 1 <= rang <= len(lignes):
            return None
        return empreinte_de_ligne(lignes[rang - 1])

    return lire


def _convient(entree: dict, finding: dict, lecteur=None) -> bool:
    """La déclaration s applique-t-elle à CE constat ? Classe, `texte` et `empreinte` déclarés.

    `empreinte` (TF-2664) : la ligne que le constat occupe AUJOURD HUI doit avoir l empreinte de
    celle que la déclaration a visée. Une ligne illisible ne confirme rien : rien n est deviné.
    """
    classe = entree.get("classe") or ""
    if classe and classe != str(finding.get("classe") or ""):
        return False
    texte = _texte(entree.get("texte"))
    if texte and texte != _texte(finding.get("message")):
        return False
    empreinte = entree.get("empreinte") or ""
    return not empreinte or (lecteur is not None and lecteur(finding) == empreinte)


def _entrees_du_constat(declarations: dict[str, dict], cle: str):
    """Les déclarations qui visent `cle` : la première (clé du constat), puis celles de `texte`
    distinct (TF-2658), sous une clé composée. Les refus de doublon (`(ligne n)`) n en font pas
    partie."""
    premiere = declarations.get(cle)
    if premiere is not None:
        yield premiere
    for autre, entree in declarations.items():
        if autre != cle and not autre.startswith("(ligne ") and entree.get("constat") == cle:
            yield entree


def statut(declarations: dict[str, dict], finding: dict, lecteur=None) -> dict:
    """Déclaration qui vise ce constat, ou `{"statut": "aucune"}`. La clé longue prime."""
    for cle in cles_du_finding(finding):
        for entree in _entrees_du_constat(declarations, cle):
            if _convient(entree, finding, lecteur):
                return entree
    return {"statut": AUCUNE, "motif": "", "preuve": "", "par": "", "date": "",
            "motif_du_refus": ""}


def rapprocher(
    declarations: dict[str, dict], orphelines: list[str], libres: list[dict], lecteur=None
) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Rapproche les déclarations ORPHELINES d un constat dont seule la ligne a changé — TF-1672.

    Rend `({clé déclarée: constat retenu}, {clé déclarée: candidats})`. Trois ancrages :

      - **`empreinte`** déclarée (TF-2664) : parmi les constats libres de même forme stable (et de
        même message si `texte`), celui dont la ligne a l empreinte déclarée. C est ce qui suit
        cinq constats de même message dont les lignes se décalent ; deux lignes identiques
        restent ambiguës ;
      - **`texte`** déclaré : le constat libre de même forme stable et de même message. Un seul
        candidat est retenu ; plusieurs (deux liens identiques dans le même fichier) restent
        ambigus ;
      - **sans `texte`** (déclarations antérieures à ce champ) : la forme stable seule, et
        seulement quand elle désigne UNE déclaration orpheline et UN constat libre. Toute autre
        configuration est ambiguë : rien n est deviné.
    """
    retenus: dict[str, dict] = {}
    ambigues: dict[str, list[str]] = {}
    pris: set[int] = set()

    def _candidats(cle: str, entree: dict) -> list[dict]:
        forme = forme_stable(entree["constat"])
        return [
            f for f in libres
            if id(f) not in pris
            and forme in {forme_stable(k) for k in cles_du_finding(f)}
            and _convient(entree, f, lecteur)
        ]

    def _ancre(entree: dict) -> bool:
        return bool(entree.get("texte") or entree.get("empreinte"))

    # Les déclarations ancrées (`empreinte`, puis `texte`) d abord : elles sont exactes, les
    # autres prennent ce qui reste.
    rangees = sorted(
        orphelines,
        key=lambda c: (
            0 if declarations[c].get("empreinte") else 1 if declarations[c].get("texte") else 2, c
        ),
    )
    formes_sans_texte: dict[str, int] = {}
    for cle in rangees:
        if not _ancre(declarations[cle]):
            forme = forme_stable(declarations[cle]["constat"])
            formes_sans_texte[forme] = formes_sans_texte.get(forme, 0) + 1
    for cle in rangees:
        entree = declarations[cle]
        constat = entree["constat"]
        if forme_stable(constat) == constat:
            continue  # aucun numéro de ligne dans la clé : rien à rapprocher
        candidats = _candidats(cle, entree)
        unique = len(candidats) == 1 and (
            _ancre(entree) or formes_sans_texte[forme_stable(constat)] == 1
        )
        if unique:
            retenus[cle] = candidats[0]
            pris.add(id(candidats[0]))
        elif candidats:
            ambigues[cle] = sorted(cles_du_finding(f)[0] for f in candidats)
    return retenus, ambigues


def est_ecarte(finding: dict) -> bool:
    """Ce constat sort-il du décompte principal ? Vrai pour la SEULE déclaration retenue."""
    declaration = finding.get("declaration")
    return bool(declaration) and declaration.get("statut") == RETENUE


# --- Application au rapport ----------------------------------------------------------------------
def reintegrer(rapport: dict) -> dict:
    """Défait `appliquer` : les constats écartés redeviennent des constats comme les autres.

    Sans elle, `--reprendre` sur un rapport déjà traité repartirait d un décompte amputé, et
    une déclaration retirée du projet ne rendrait jamais son constat au rapport.
    """
    for finding in rapport.get("findings") or []:
        finding.pop("declaration", None)
    reprises = rapport.pop("actions_declarees", None) or []
    if reprises:
        actions = list(rapport.get("actions") or [])
        connues = {a.get("finding_ref") for a in actions}
        actions.extend(a for a in reprises if a.get("finding_ref") not in connues)
        rapport["actions"] = actions
    rapport.pop("declarations", None)
    rapport.pop("bandes_de_risque_declares", None)
    _recompter_bandes(rapport)
    return rapport


def _bandes(findings: list[dict]) -> dict[str, int]:
    from forge_tests.noyau import bande

    comptes = {"critique": 0, "standard": 0, "differe": 0, "non_cote": 0}
    for finding in findings:
        risque = finding.get("risque")
        comptes["non_cote" if risque is None else bande(int(risque))] += 1
    return comptes


def _recompter_bandes(rapport: dict) -> None:
    """`bandes_de_risque` ne compte QUE les constats opposables ; les écartés ont la leur.

    Les deux sections existent toujours : un lecteur `jq` qui n additionnerait que la première
    doit pouvoir constater que la somme ne fait pas le total des findings, et trouver l autre.
    """
    if "findings" not in rapport:
        return
    findings = rapport.get("findings") or []
    ecartes = [f for f in findings if est_ecarte(f)]
    rapport["bandes_de_risque"] = _bandes([f for f in findings if not est_ecarte(f)])
    if ecartes:
        rapport["bandes_de_risque_declares"] = _bandes(ecartes)


def appliquer(rapport: dict, cible: Path, aujourdhui: _dt.date | None = None) -> dict:
    """Applique au rapport les déclarations du projet. Idempotent, et LECTURE SEULE (G-1).

    Le rapport gagne une section `declarations` — toujours présente une fois ce point
    d application franchi, y compris quand le projet n a rien déclaré : un canal que le projet
    ignore est un canal qui n existe pas.
    """
    reintegrer(rapport)
    source = Path(cible) / FICHIER
    declarations = charger(cible, aujourdhui)
    findings = rapport.get("findings") or []

    def _poser(finding: dict, entree: dict) -> None:
        finding["declaration"] = {
            cle: entree.get(cle, "")
            for cle in ("statut", "motif", "preuve", "par", "date", "expire_le", "explication",
                        "motif_du_refus")
        }
        finding["declaration"]["libelle_motif"] = MOTIFS.get(entree.get("motif", ""), {}).get(
            "libelle", entree.get("motif", "")
        )

    # TF-2664 — la ligne que chaque constat occupe aujourd hui, pour les déclarations ancrées par
    # `empreinte` : lue chez l audité, en lecture seule.
    lecteur = lecteur_de_lignes(cible)
    ecartes = 0
    servies: set[int] = set()
    for finding in findings:
        entree = statut(declarations, finding, lecteur)
        if entree["statut"] == AUCUNE:
            continue
        _poser(finding, entree)
        servies.add(id(entree))
        ecartes += entree["statut"] == RETENUE

    # TF-1672 — une déclaration qui ne vise plus aucun constat est d abord RAPPROCHÉE, si seul le
    # numéro de ligne a changé ; le rapprochement est publié, avec la clé à recopier.
    orphelines = [
        cle for cle, entree in declarations.items()
        if not cle.startswith("(ligne ") and entree.get("constat") and id(entree) not in servies
    ]
    retenus, ambigues = rapprocher(
        declarations, orphelines, [f for f in findings if "declaration" not in f], lecteur
    )
    rapprochees = []
    for cle, finding in sorted(retenus.items()):
        entree = declarations[cle]
        _poser(finding, entree)
        retrouve = cles_du_finding(finding)[0]
        ancrage = (
            "empreinte" if entree.get("empreinte")
            else "texte" if entree.get("texte") else "forme-sans-ligne"
        )
        finding["declaration"]["rapprochee_de"] = entree["constat"]
        finding["declaration"]["ancrage"] = ancrage
        entree["rapprochee_vers"] = retrouve
        rapprochees.append(
            {
                "declare": entree["constat"],
                "retrouve": retrouve,
                "ancrage": ancrage,
                "a_faire": f"remplacer `{entree['constat']}` par `{retrouve}` dans `{FICHIER}`"
                + (
                    ""
                    if ancrage != "forme-sans-ligne"
                    else " et y ajouter `texte` (le message du constat) pour un ancrage exact"
                ),
            }
        )
        ecartes += entree["statut"] == RETENUE

    # TF-2664 — de quoi écrire `empreinte` sans la calculer à la main : l empreinte de la ligne
    # des constats qu un même message ne distingue pas (même forme sans numéro de ligne).
    groupes: dict[tuple[str, str], list[dict]] = {}
    for finding in findings:
        groupes.setdefault(
            (forme_stable(cles_du_finding(finding)[0]), _texte(finding.get("message"))), []
        ).append(finding)
    empreintes: dict[str, str] = {}
    for membres in groupes.values():
        if len(membres) < 2:
            continue
        for finding in membres:
            lue = lecteur(finding)
            if lue is not None:
                empreintes[cles_du_finding(finding)[0]] = lue

    # L action d un constat écarté n a plus de destinataire : elle est MISE À PART, jamais
    # perdue. Un constat non déclaré qui partagerait la même référence garde la sienne.
    refs_ecartees = {
        cles_du_finding(f)[0] for f in findings if est_ecarte(f)
    } - {cles_du_finding(f)[0] for f in findings if not est_ecarte(f)}
    actions, mises_a_part = [], []
    for action in rapport.get("actions") or []:
        (mises_a_part if action.get("finding_ref") in refs_ecartees else actions).append(action)
    if mises_a_part:
        rapport["actions"] = actions
        rapport["actions_declarees"] = mises_a_part

    _recompter_bandes(rapport)
    comptes = {
        statut_: sum(1 for e in declarations.values() if e.get("statut") == statut_)
        for statut_ in (RETENUE, REFUSEE, PERIMEE)
    }
    inconnus = sorted(cle for cle in orphelines if cle not in retenus)
    rapport["declarations"] = {
        "fichier": FICHIER,
        "present": source.is_file(),
        "motifs": {cle: valeur["libelle"] for cle, valeur in MOTIFS.items()},
        "compte": {
            **comptes,
            "constats_ecartes": ecartes,
            "inconnues": len(inconnus),
            "rapprochees": len(rapprochees),
        },
        "inconnues": inconnus,
        "rapprochees": rapprochees,
        "ambigues": ambigues,
        "empreintes": empreintes,
        "entrees": sorted(declarations.values(), key=lambda e: (e.get("ligne") or 0)),
        # Ce que le projet doit écrire pour se servir du canal — au rapport, pas dans une doc
        # qu il faudrait connaître d avance.
        "pour_declarer": (
            f"deposer une ligne JSON par constat dans `{FICHIER}` : "
            '{"constat": "<pan>/<id du finding>", "motif": "<'
            + "|".join(sorted(MOTIFS))
            + '>", "preuve": "<chemin qui existe>", "par": "<qui declare>", '
            '"date": "AAAA-MM-JJ", "texte": "<message du constat, facultatif>", '
            '"empreinte": "<empreinte de la ligne visee, facultatif>"}. La preuve '
            "est verifiee ; sans elle le constat reste au decompte. `texte` ancre la "
            "declaration sur le message : elle suit le constat quand sa ligne change ; deux "
            "constats de meme identifiant et de textes differents portent chacun leur "
            "declaration. Quand plusieurs constats partagent le meme message, `empreinte` (celle "
            "de la ligne visee, publiee dans `declarations.empreintes`) ancre la declaration sur "
            "SA ligne : elle la suit quand les lignes se decalent"
        ),
    }
    return rapport
