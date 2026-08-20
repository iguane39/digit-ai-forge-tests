"""Registre de dette — P5.

Les `non_juge` étaient des chaînes en dur dans chaque module : de la prose, donc du silence
à retardement. Ici ils deviennent des entrées VERSIONNÉES à statut, sur le patron du registre
d oracles de quality-oracles (règle §4 : un domaine non couvert reçoit une entrée, pas une
phrase). Le registre est REGÉNÉRÉ depuis le code — impossible de le laisser diverger — et les
statuts déjà posés à la main sont PRÉSERVÉS.

Deux règles de sémantique, posées après le constat du 08/08 (89 entrées, **zéro** fermeture) :

  - **l identifiant est stable et découplé de l énoncé.** Il valait `<domaine>-<sha8(enonce)>` :
    reformuler une phrase fabriquait une entrée neuve en `todo` et faisait passer l ancienne
    pour comblée. L identité vit désormais dans le registre (`<domaine>-<rang>`), attribuée une
    fois, et un énoncé reformulé la CONSERVE — le rapprochement se fait sur la ressemblance et
    il est DÉCLARÉ à la régénération, jamais silencieux ;
  - **`ok` exige une preuve.** Une dette ne se ferme pas parce qu on a retiré sa phrase du
    code : elle se ferme parce qu un test ou un contrôle de recette la tient. Le champ `preuve`
    nomme ce contrôle, et `verifier()` refuse un `ok` qui n en porte pas. Une entrée dont
    l énoncé a disparu du code sans preuve sort en `retiree` — un retrait, pas une fermeture.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

REGISTRE = Path(__file__).resolve().parent.parent / "registre-dette.json"
# Statuts VIVANTS, posés à la main. `ok` est le seul qui prétende à une fermeture, et il exige
# une `preuve` nommée — sans quoi il ne serait qu un `assume` qui n ose pas dire son nom.
STATUTS = ("todo", "assume", "ok")
# Statut posé par la MACHINE : l énoncé a disparu du code. Ce n est pas une fermeture.
STATUT_RETIRE = "retiree"
# Au-dessus de ce taux de ressemblance, deux énoncés du même domaine sont la MÊME dette
# reformulée. En dessous, c est une dette nouvelle et l ancienne est retirée.
SEUIL_RESSEMBLANCE = 0.70


def _identifiant(domaine: str, rang: int) -> str:
    """Identifiant stable — un rang d attribution, jamais une empreinte de l énoncé."""
    return f"{domaine}-{rang:03d}"


def _canonique(identifiant: str, domaine: str) -> bool:
    """Un identifiant de la forme `<domaine>-<rang a 3 chiffres>` — et rien d autre.

    Les identifiants d origine valaient `<domaine>-<sha8(enonce)>`. Ils sont RENUMÉROTÉS à la
    première régénération : laisser vivre une empreinte d énoncé inviterait à la recalculer,
    c est-à-dire à refaire exactement l erreur que le découplage existe pour ôter.
    """
    prefixe, _, suffixe = identifiant.rpartition("-")
    return prefixe == domaine and len(suffixe) == 3 and suffixe.isdigit()


def _rang(identifiant: str) -> int:
    suffixe = identifiant.rpartition("-")[2]
    return int(suffixe) if suffixe.isdigit() else 0


def collecter() -> list[dict]:
    """Rassemble les non_juge déclarés par le noyau, le risque, l exécution et les adaptateurs."""
    from forge_tests import (
        actions,
        adoption,
        catalogue_i18n,
        declarations,
        declencheurs,
        execution,
        generateur,
        generateur_data,
        invariants,
        qualification,
        reprise,
        risque,
        sql,
    )
    from forge_tests.adaptateurs import REGISTRE as ADAPTATEURS
    from forge_tests.livrables import cahiers, dashboard, exigences, jeux

    sources: list[tuple[str, list[str]]] = [
        ("risque", list(risque.NON_JUGE)),
        ("execution", list(execution.NON_JUGE)),
        # Les limites de l analyse STATIQUE des gardes (RT-9 : un seul niveau d appel resolu)
        # etaient declarees dans `invariants` et collectees nulle part : elles ne figuraient au
        # registre d aucun domaine. Une dette qui n entre pas au registre est de la prose.
        ("invariants", list(invariants.NON_JUGE)),
        ("generateur", list(generateur.NON_JUGE)),
        ("generateur-data", list(generateur_data.NON_JUGE)),
        ("sql", list(sql.NON_JUGE)),
        ("qualification", list(qualification.NON_JUGE)),
        ("reprise", list(reprise.NON_JUGE)),
        ("actions", list(actions.NON_JUGE)),
        # TF-0383 — les limites du CATALOGUE de chaines. Elles sont fusionnees a celles du
        # pan i18n a l EXECUTION (`analyser`), or ce collecteur lit les modules
        # STATIQUEMENT : sans cette ligne, sept limites declarees n entraient au registre
        # d aucun domaine. « Une dette qui n entre pas au registre est de la prose », et
        # c est le commentaire de cette fonction meme qui le dit.
        ("catalogue-i18n", list(catalogue_i18n.NON_JUGE)),
        ("adoption", list(adoption.NON_JUGE)),
        ("declarations", list(declarations.NON_JUGE)),
        ("declencheurs", list(declencheurs.NON_JUGE)),
        ("cahiers", list(cahiers.NON_JUGE)),
        ("jeux-de-donnees", list(jeux.NON_JUGE)),
        ("exigences", list(exigences.NON_JUGE)),
        ("dashboard", list(dashboard.NON_JUGE)),
    ]
    for nom, module in ADAPTATEURS.items():
        sources.append((nom, list(getattr(module, "NON_JUGE", []))))

    # TF-0384 (19/08, constaté en livrant TF-0383) — la liste ci-dessus est ÉCRITE À LA MAIN :
    # un module neuf n'y entrait que si quelqu'un y pensait, et les 8 limites de
    # `catalogue_i18n` n'entraient au registre d'AUCUN domaine sans que rien ne le signale.
    # « Une dette qui n'entre pas au registre est de la prose » — le commentaire de cette
    # fonction le disait en étant lui-même une liste, un cran plus haut. Septième occurrence du
    # patron « un contrôle qui itère sur une liste ne voit jamais ce qui n'y est pas ».
    #
    # La DÉCOUVERTE se fait sur le DISQUE : tout module de `forge_tests/` et
    # `forge_tests/livrables/` portant un `NON_JUGE` de niveau module est collecté. La liste à
    # la main ne sert plus qu'à NOMMER les domaines historiques (« jeux-de-donnees » pour
    # `jeux`…) — un module absent d'elle ET des adaptateurs entre quand même, sous le nom de
    # son fichier. Les énoncés lus par AST : la déduplication de `collecter` absorbe le
    # recouvrement avec les modules déjà importés ci-dessus.
    import ast as _ast

    racine_pkg = Path(__file__).resolve().parent
    couverts = {module.__name__.rsplit(".", 1)[-1] for module in ADAPTATEURS.values()}
    couverts |= {
        "risque", "execution", "invariants", "generateur", "generateur_data", "sql",
        "qualification", "reprise", "actions", "adoption", "declarations", "declencheurs",
        "catalogue_i18n", "cahiers", "dashboard", "exigences", "jeux",
    }
    for dossier, prefixe in ((racine_pkg, ""), (racine_pkg / "livrables", "livrables.")):
        for fichier in sorted(dossier.glob("*.py")):
            stem = fichier.stem
            if stem.startswith("_") or (prefixe + stem).replace("livrables.", "") in couverts:
                continue
            try:
                arbre = _ast.parse(fichier.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            enonces: list[str] = []
            for noeud in arbre.body:
                if isinstance(noeud, _ast.Assign) and any(
                    isinstance(c, _ast.Name) and c.id == "NON_JUGE" for c in noeud.targets
                ):
                    try:
                        valeur = _ast.literal_eval(noeud.value)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(valeur, list):
                        enonces.extend(str(x) for x in valeur)
            if enonces:
                sources.append((stem.replace("_", "-"), enonces))

    entrees: list[dict] = []
    vus: set[tuple[str, str]] = set()
    for domaine, enonces in sources:
        for enonce in enonces:
            cle = (domaine, enonce.strip())
            if cle in vus:
                continue
            vus.add(cle)
            entrees.append({"domaine": domaine, "enonce": enonce.strip()})
    return entrees


def _apparier(
    courant: list[dict], ancien: dict[str, dict], reformulees: list[str] | None = None
) -> dict[int, dict]:
    """Rapproche chaque énoncé du code d une entrée du registre — indice courant -> entrée.

    Deux passes, dans cet ordre : l énoncé IDENTIQUE d abord (un fait), puis la RESSEMBLANCE
    dans le même domaine (une reformulation). Sans la seconde, réécrire une phrase perdait
    l identité de la dette, son statut et sa note : c est exactement ce qui produisait 27
    « résolues » sans qu une seule ait été comblée.
    """
    libres = dict(ancien)
    apparie: dict[int, dict] = {}

    par_enonce: dict[tuple[str, str], str] = {}
    for identifiant, entree in ancien.items():
        par_enonce.setdefault((entree.get("domaine", ""), entree.get("enonce", "")), identifiant)
    for indice, neuf in enumerate(courant):
        identifiant = par_enonce.get((neuf["domaine"], neuf["enonce"]))
        if identifiant and identifiant in libres:
            apparie[indice] = libres.pop(identifiant)

    for indice, neuf in enumerate(courant):
        if indice in apparie:
            continue
        candidats = [
            (
                difflib.SequenceMatcher(None, entree.get("enonce", ""), neuf["enonce"]).ratio(),
                identifiant,
            )
            for identifiant, entree in libres.items()
            if entree.get("domaine") == neuf["domaine"]
        ]
        if not candidats:
            continue
        taux, identifiant = max(candidats, key=lambda couple: (couple[0], couple[1]))
        if taux >= SEUIL_RESSEMBLANCE:
            apparie[indice] = libres.pop(identifiant)
            if reformulees is not None:
                reformulees.append(f"{identifiant} (ressemblance {taux:.0%}) : enonce reformule")
    return apparie


def projeter(ancien: dict[str, dict], reformulees: list[str] | None = None) -> dict:
    """Ce que le registre DOIT contenir au vu du code — sans rien écrire.

    Fonction pure : `regenerer` l écrit, `verifier` la compare au fichier committé. Les deux
    lisent donc la même vérité, ce qui est la seule façon qu un contrôle de synchronisation
    ne mente pas.
    """
    courant = collecter()
    apparie = _apparier(courant, ancien, reformulees)
    conserves = {precedent["id"] for precedent in apparie.values()}

    # Rangs déjà attribués, pour ne jamais réutiliser un numéro : un identifiant recyclé
    # désignerait deux dettes différentes dans deux versions du registre.
    prochain: dict[str, int] = {}
    for identifiant, entree in ancien.items():
        domaine = entree.get("domaine", "")
        if _canonique(identifiant, domaine):
            prochain[domaine] = max(prochain.get(domaine, 0), _rang(identifiant))

    # Ordre d émission : le code d abord (ordre de déclaration), puis les entrées retirées,
    # triées par leur ancien identifiant. Deux projections du même état donnent la même sortie.
    a_emettre: list[tuple[dict | None, dict, str]] = [
        (apparie.get(indice), neuf, "code") for indice, neuf in enumerate(courant)
    ]
    for identifiant in sorted(ancien):
        if identifiant in conserves:
            continue
        entree = ancien[identifiant]
        a_emettre.append((entree, {"domaine": entree.get("domaine", ""),
                                   "enonce": entree.get("enonce", "")}, "retire"))

    entrees: list[dict] = []
    for precedent, neuf, origine in a_emettre:
        domaine = neuf["domaine"]
        if precedent is not None and _canonique(str(precedent.get("id", "")), domaine):
            identifiant = str(precedent["id"])
        else:
            prochain[domaine] = prochain.get(domaine, 0) + 1
            identifiant = _identifiant(domaine, prochain[domaine])
        if origine == "code":
            statut = (precedent or {}).get("statut", "todo")
            # Un `retiree` dont l énoncé revient au code redevient une dette vivante.
            statut = "todo" if statut == STATUT_RETIRE else statut
        else:
            # Une entrée dont l énoncé a disparu du code n est PAS comblée : elle est retirée.
            # Seule une entrée déjà fermée SUR PREUVE garde son `ok`.
            ferme = (precedent or {}).get("statut") == "ok" and str(
                (precedent or {}).get("preuve") or ""
            ).strip()
            statut = "ok" if ferme else STATUT_RETIRE
        entree = {
            "id": identifiant,
            "domaine": domaine,
            "enonce": neuf["enonce"],
            "statut": statut,
        }
        for champ in ("preuve", "note"):
            if (precedent or {}).get(champ):
                entree[champ] = (precedent or {})[champ]
        entrees.append(entree)

    return {
        "version": 2,
        "note": (
            "Dette de jugement du framework. `todo` = à outiller · `assume` = limite acceptée "
            "et déclarée pour toujours · `ok` = comblée, et le champ `preuve` NOMME le test ou "
            "le contrôle de recette qui la tient · `retiree` = énoncé disparu du code sans "
            "preuve, ce qui n est PAS une fermeture. L identifiant est stable et découplé de "
            "l énoncé : reformuler une phrase conserve l entrée. Régénéré depuis le code "
            "(`python -m forge_tests.dette`) et vérifié en recette (`--verifier`) : ne pas "
            "éditer les énoncés à la main, seulement les statuts, les preuves et les notes."
        ),
        "dette": sorted(entrees, key=lambda e: (e["statut"], e["domaine"], _rang(e["id"]))),
    }


def _lire(cible: Path) -> dict[str, dict]:
    if not cible.exists():
        return {}
    return {e["id"]: e for e in json.loads(cible.read_text(encoding="utf-8"))["dette"]}


def _rendu(donnees: dict) -> str:
    return json.dumps(donnees, ensure_ascii=False, indent=2) + "\n"


def regenerer(chemin: Path | None = None, reformulees: list[str] | None = None) -> dict:
    """Régénère le registre depuis le code, en préservant identités, statuts, preuves et notes."""
    cible = chemin or REGISTRE
    donnees = projeter(_lire(cible), reformulees)
    cible.write_text(_rendu(donnees), encoding="utf-8")
    return donnees


def verifier(chemin: Path | None = None) -> list[str]:
    """Divergences entre le registre COMMITTÉ et le code. Liste vide = registre à jour.

    Un registre régénéré à la main est un registre qu on oublie de régénérer : la dette du
    jour se lit alors dans un fichier qui décrit le code d avant-hier. Le contrôle est donc
    joué en recette, et il échoue — il ne signale pas.
    """
    cible = chemin or REGISTRE
    if not cible.exists():
        return [f"registre absent : {cible}"]

    ecarts: list[str] = []
    ancien = _lire(cible)
    attendu = projeter(ancien)

    # 1. Sémantique : ce que le fichier committé déclare doit être recevable en soi.
    vocabulaire = (*STATUTS, STATUT_RETIRE)
    for entree in ancien.values():
        statut = entree.get("statut")
        if statut not in vocabulaire:
            ecarts.append(f"{entree.get('id')} : statut « {statut} » hors vocabulaire")
        if statut == "ok" and not str(entree.get("preuve") or "").strip():
            ecarts.append(
                f"{entree.get('id')} : statut `ok` SANS preuve — une dette ne se ferme que sur "
                "un test ou un controle de recette NOMME dans le champ `preuve`"
            )

    # 2. Synchronisation : le fichier doit être exactement ce que le code produirait.
    ancien_par_id = {e["id"]: e for e in json.loads(cible.read_text(encoding="utf-8"))["dette"]}
    attendu_par_id = {e["id"]: e for e in attendu["dette"]}
    for identifiant, entree in attendu_par_id.items():
        precedent = ancien_par_id.get(identifiant)
        if precedent is None:
            ecarts.append(
                f"{identifiant} ({entree['domaine']}) : declaree par le code, absente du "
                f"registre — regenerer (`python -m forge_tests.dette`)"
            )
        elif precedent.get("enonce") != entree["enonce"]:
            ecarts.append(
                f"{identifiant} : enonce du registre different de celui du code "
                f"(reformulation non regeneree)"
            )
        elif precedent.get("statut") != entree["statut"]:
            ecarts.append(
                f"{identifiant} : statut « {precedent.get('statut')} » au registre, "
                f"« {entree['statut']} » au vu du code"
            )
    for identifiant in ancien_par_id:
        if identifiant not in attendu_par_id:
            ecarts.append(f"{identifiant} : au registre, inconnue de la projection du code")

    if not ecarts and _rendu(attendu) != cible.read_text(encoding="utf-8"):
        ecarts.append(
            "le registre differe de sa projection (ordre, en-tete ou champ) — regenerer"
        )
    return ecarts


def charger(chemin: Path | None = None) -> list[dict]:
    cible = chemin or REGISTRE
    if not cible.exists():
        return []
    return json.loads(cible.read_text(encoding="utf-8"))["dette"]


def resume() -> dict[str, int]:
    compte = dict.fromkeys((*STATUTS, STATUT_RETIRE), 0)
    for entree in charger():
        compte[entree["statut"]] = compte.get(entree["statut"], 0) + 1
    return compte


if __name__ == "__main__":
    import sys

    if "--verifier" in sys.argv[1:]:
        ecarts = verifier()
        if ecarts:
            print(f"registre de dette DESYNCHRONISE : {len(ecarts)} ecart(s)")
            for ecart in ecarts:
                print(f"  - {ecart}")
            sys.exit(1)
        print(f"registre de dette a jour : {len(charger())} entrees, aucun ecart")
        sys.exit(0)

    reformulees: list[str] = []
    donnees = regenerer(reformulees=reformulees)
    par_statut: dict[str, int] = {}
    for entree in donnees["dette"]:
        par_statut[entree["statut"]] = par_statut.get(entree["statut"], 0) + 1
    print(f"registre de dette regenere : {len(donnees['dette'])} entrees")
    for statut, compte in sorted(par_statut.items()):
        print(f"  {statut:<10} {compte}")
    # Un rapprochement par ressemblance est une DECISION de la machine : il se declare.
    for ligne in reformulees:
        print(f"  identite conservee — {ligne}")
    print(f"  -> {REGISTRE}")
