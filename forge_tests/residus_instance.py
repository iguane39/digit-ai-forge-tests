"""Résidus d'une campagne sur une instance hébergée — TF-2661.

**Le fait (Produit-82, lot 20261113h, RT-43).** La suite du produit, rejouée à chaque déploiement
sur la base réelle de la recette, créait des organisations et des identités sans les effacer :
315 organisations et 465 identités non marquées au 13/11/2026. Aucune règle ni contrôle ne
comparait l'état de l'instance avant et après une campagne : le résidu grossissait à chaque
déploiement, sans qu'aucun rapport le dise.

**La règle.** Une campagne qui touche une instance inscrit le décompte de ses objets métier AVANT
son premier pan et APRÈS son dernier, et un écart rend FAIL : ce que la campagne crée, elle le
retire. Le contrôle est celui de la forge ; le DÉCOMPTE est celui du produit, seul à savoir ce que
sont ses objets métier et comment les compter sans les confondre avec les données d'un
utilisateur. Il déclare donc une commande, `FORGE_TESTS_INSTANCE_DECOMPTE`, qui imprime un objet
JSON `{"organisations": 315, "identites": 465}` (des entiers positifs ou nuls, au moins un objet).
La commande est lancée sans interpréteur de commandes, depuis la racine du projet audité, en
lecture seule : la forge n'écrit rien chez l'audité (G-1) et ne déclare jamais « conforme » sur un
décompte qu'elle n'a pas obtenu.

**Quatre issues, toutes déclarées au rapport (`residus_instance.statut`)** :

  - `conforme` : deux décomptes lus, identiques — la campagne n'a rien laissé ;
  - `residus` : deux décomptes lus, au moins un objet dont le compte a changé — verdict FAIL, chaque
    objet nommé avec son compte avant, après et son écart (un objet qui a DISPARU est un écart
    comme un objet apparu : la campagne a touché à ce qu'elle n'avait pas créé) ;
  - `non_mesure` : un décompte manque ou est illisible (commande en échec, sortie non conforme), ou
    l'instance est hébergée et aucune commande n'est déclarée — le motif est publié, le verdict
    n'en est pas changé : un FAIL ne s'invente pas sur une mesure qu'on n'a pas, et un silence ne
    se lit pas « conforme » ;
  - `sans_objet` : aucune commande déclarée et aucune instance hébergée (URL de boucle locale ou
    aucune URL) : une instance locale se jette avec sa campagne.

Ce que la forge ne sait pas : si l'écart vient de la campagne ou d'un tiers qui écrivait sur la
même instance pendant ce temps. Le rapport le dit (`non_juge`) ; le produit qui partage son
instance de recette compte ce qu'il peut attribuer à la campagne.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from forge_tests.instance import _hote_port, _url_servie

CHAMP_DECOMPTE = "FORGE_TESTS_INSTANCE_DECOMPTE"

#: Délai d'un décompte. Une commande qui interroge une base hébergée tient en secondes ; passé ce
#: délai, la mesure est déclarée manquante, elle n'emporte pas l'audit.
DELAI_S = 120

#: Les hôtes d'une instance locale, jetée avec la campagne qui l'a montée.
_HOTES_LOCAUX = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

CONSIGNE = (
    f"déclarer `{CHAMP_DECOMPTE}` : une commande du PRODUIT qui imprime le décompte de ses objets "
    'métier en JSON, par exemple {"organisations": 315, "identites": 465} (entiers positifs ou '
    "nuls). La forge la joue avant le premier pan et après le dernier, et un écart rend FAIL"
)

#: Ce que le contrôle ne dit pas — publié au rapport quand il a mesuré.
LIMITES = (
    "residus_instance : l'écart est mesuré sur l'instance, pas attribué : un tiers qui écrit sur "
    "la même instance pendant la campagne s'y lirait aussi. Le décompte, lui, est celui que le "
    "produit déclare : un objet qu'il ne compte pas n'est pas contrôlé",
)


def hebergee(env: dict[str, str] | None = None) -> bool:
    """L'une des URL déclarées servies vise-t-elle un hôte autre que la boucle locale ?"""
    for entree in _url_servie(env):
        hote, _ = _hote_port(entree["url"])
        if hote and hote not in _HOTES_LOCAUX and not hote.endswith(".localhost"):
            return True
    return False


def _argv(commande: str) -> list[str]:
    """La commande déclarée, découpée sans interpréteur de commandes (aucune injection par `;`)."""
    morceaux = shlex.split(commande, posix=os.name != "nt")
    return [m[1:-1] if len(m) >= 2 and m[0] == m[-1] and m[0] in "\"'" else m for m in morceaux]


def lire_decompte(sortie: str) -> tuple[dict[str, int] | None, str | None]:
    """Le décompte que la commande a imprimé, ou le motif pour lequel il n'est pas exploitable."""
    try:
        brut = json.loads(sortie)
    except json.JSONDecodeError:
        return None, "la sortie n'est pas du JSON"
    if not isinstance(brut, dict) or not brut:
        return None, 'un objet JSON non vide est attendu, par exemple {"organisations": 315}'
    for objet, compte in brut.items():
        if isinstance(compte, bool) or not isinstance(compte, int) or compte < 0:
            return None, f"« {objet} » : un entier positif ou nul est attendu, reçu {compte!r}"
    return {str(objet): compte for objet, compte in brut.items()}, None


def mesurer(
    cible: Path | str,
    env: dict[str, str] | None = None,
    executer=subprocess.run,
) -> dict:
    """Joue la commande de décompte déclarée. Rend `commande`, `decompte` (ou `None`) et `motif`."""
    e = os.environ if env is None else env
    commande = (e.get(CHAMP_DECOMPTE) or "").strip()
    if not commande:
        return {"commande": None, "decompte": None, "motif": None}
    try:
        resultat = executer(
            _argv(commande), capture_output=True, text=True, timeout=DELAI_S, check=False,
            cwd=str(cible), encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"commande": commande, "decompte": None,
                "motif": f"la commande n'a pas rendu sa mesure en {DELAI_S} s"}
    except (OSError, subprocess.SubprocessError, ValueError) as erreur:
        return {"commande": commande, "decompte": None,
                "motif": f"la commande n'a pas pu être lancée ({type(erreur).__name__} : {erreur})"}
    if resultat.returncode != 0:
        detail = " ".join(((resultat.stderr or resultat.stdout) or "").split())[:200]
        return {"commande": commande, "decompte": None,
                "motif": f"la commande a rendu le code {resultat.returncode} : {detail}"}
    decompte, motif = lire_decompte(resultat.stdout)
    return {"commande": commande, "decompte": decompte, "motif": motif}


def avant(cible: Path | str, env: dict[str, str] | None = None) -> dict:
    """Le décompte d'AVANT : à jouer avant le premier pan, une fois la configuration chargée."""
    return mesurer(cible, env)


def comparer(compte_avant: dict[str, int], compte_apres: dict[str, int]) -> list[dict]:
    """Chaque objet dont le compte a changé, par ordre alphabétique. Un objet absent compte 0."""
    ecarts = []
    for objet in sorted(set(compte_avant) | set(compte_apres)):
        a, b = compte_avant.get(objet, 0), compte_apres.get(objet, 0)
        if a != b:
            ecarts.append({"objet": objet, "avant": a, "apres": b, "ecart": b - a})
    return ecarts


def _section(statut: str, motif: str, **autres: object) -> dict:
    return {
        "statut": statut,
        "verdict": {"conforme": "PASS", "residus": "FAIL"}.get(statut),
        "commande": None,
        "avant": None,
        "apres": None,
        "ecarts": [],
        "motif": motif,
        "non_juge": [],
        **autres,
    }


def au_rapport(
    mesure_avant: dict, cible: Path | str, env: dict[str, str] | None = None
) -> dict:
    """La section `residus_instance` du rapport : le décompte d'après, la comparaison, le verdict.

    Toujours présente : une section qui disparaîtrait sans commande déclarée serait indiscernable
    d'une section qui a mesuré et n'a rien trouvé.
    """
    e = os.environ if env is None else env
    commande = mesure_avant.get("commande")
    if not commande:
        if hebergee(e):
            motif = (
                "instance hébergée déclarée, aucun décompte de ses objets métier : la campagne ne "
                f"dit pas ce qu'elle y laisse — {CONSIGNE}"
            )
            return _section("non_mesure", motif, non_juge=[f"residus_instance : {motif}"])
        return _section(
            "sans_objet",
            "aucune instance hébergée déclarée et aucune commande de décompte : une instance "
            "locale se jette avec sa campagne",
        )
    base = {"commande": commande, "avant": mesure_avant.get("decompte")}
    if mesure_avant.get("decompte") is None:
        motif = f"décompte « avant » inexploitable : {mesure_avant.get('motif')}"
        return _section("non_mesure", motif, **base, non_juge=[f"residus_instance : {motif}"])
    mesure_apres = mesurer(cible, e)
    base["apres"] = mesure_apres["decompte"]
    if mesure_apres["decompte"] is None:
        motif = f"décompte « après » inexploitable : {mesure_apres['motif']}"
        return _section("non_mesure", motif, **base, non_juge=[f"residus_instance : {motif}"])
    ecarts = comparer(mesure_avant["decompte"], mesure_apres["decompte"])
    if not ecarts:
        total = sum(mesure_apres["decompte"].values())
        return _section(
            "conforme",
            f"{len(mesure_apres['decompte'])} objet(s) métier, {total} au total, identiques avant "
            "et après la campagne",
            **base, non_juge=list(LIMITES),
        )
    detail = " ; ".join(
        f"{e_['objet']} {e_['ecart']:+d} ({e_['avant']} → {e_['apres']})" for e_ in ecarts
    )
    return _section(
        "residus",
        f"la campagne a changé l'état de l'instance : {detail}. Retirer ce que la campagne crée "
        "(nettoyage en fin de suite, ou données marquées et purgées), puis rejouer",
        **base, ecarts=ecarts, non_juge=list(LIMITES),
    )
