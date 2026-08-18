"""PRÉSENT puis PLAUSIBLE — le second contrôle par champ, jumeau du premier (TF-0370).

Lot bourse-aux-vacants 20260818a, 18/08/2026.

**Le fait.** Le second étage de la recette avait établi l'écart « 5 annonces sans commune » en
testant `city-insee-code === null`. Or **11 annonces sur 1 249 portent latitude=0 ET
longitude=0** — le point (0,0), dans le golfe de Guinée, au large de l'Afrique. C'est l'anomalie
9873 du board, priorité 1, ouverte le 30/07 : « des annonces sont localisées dans la mer bordant
l'Afrique ». Les 11 lignes ont des adresses françaises réelles.

**Et elles passent les CINQ invariants du parc** : clé métier présente, unique, à la bonne
forme, code INSEE à cinq caractères, coordonnées PRÉSENTES. Le repli
`COALESCE(ads.latitude, ST_Y(cities.centroid))` ne joue pas non plus — **0 n'est pas NULL**.

La mesure avait donc trouvé le voisin immédiat — le champ VIDE — et manquait le champ FAUX, qui
est justement le cas rapporté par l'utilisateur. C'est le même patron que TF-0261 côté forge-seo
(« le crawler plafonné rend un chiffre plausible et faux »), et le voisin de TF-0344 piège 1
(« assertion d'absence sans preuve de présence ») un cran plus loin : là l'absence était mesurée
sur un écran, ici elle l'est sur une donnée.

**Le domaine n'est pas à deviner dans la plupart des cas** : il est déjà DÉCLARÉ dans le schéma
que la forge lit. `validate.Range(min=…, max=…)` et `validate.OneOf([…])` de marshmallow, les
`CHECK` du SQL, les `Enum`. Pour les grandeurs qui n'en portent aucun, un domaine déclaré par le
projet vaut mieux que rien — et « non déclarable » vaut mieux qu'un domaine inventé.

Trois issues, comme partout ailleurs : **conforme** · **hors domaine, AVEC LES LIGNES NOMMÉES**
· **domaine non déclarable, en le disant**.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CONFORME = "conforme"
HORS_DOMAINE = "hors_domaine"
NON_DECLARABLE = "non_declarable"

IGNORES = {"node_modules", ".venv", "__pycache__", ".git", ".oracles", ".pytest_cache",
           "dist", "build", "out", "tests", "test"}

#: `CHECK (col BETWEEN a AND b)` et `CHECK (col IN (…))` du SQL — l'autre endroit où un domaine
#: est déjà déclaré, et que personne ne lisait.
_CHECK_BETWEEN = re.compile(
    r"CHECK\s*\(\s*(?P<col>\w+)\s+BETWEEN\s+(?P<min>-?[\d.]+)\s+AND\s+(?P<max>-?[\d.]+)",
    re.I,
)
_CHECK_IN = re.compile(r"CHECK\s*\(\s*(?P<col>\w+)\s+IN\s*\((?P<valeurs>[^)]+)\)", re.I)


def _fichiers(cible: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not cible.is_dir():
        return []
    return [
        f for f in sorted(cible.rglob("*"))
        if f.is_file() and f.suffix.lower() in suffixes
        and not (IGNORES & {p.name for p in f.parents})
    ]


def _litteral(noeud: ast.AST):
    try:
        return ast.literal_eval(noeud)
    except (ValueError, SyntaxError):
        return None


def domaines_declares(cible: Path) -> dict[str, dict]:
    """Les domaines que le projet DÉCLARE DÉJÀ, lus là où il les écrit.

    Deux sources, parce que les projets en emploient deux : les validateurs de schéma
    (marshmallow `validate.Range` / `validate.OneOf`) et les `CHECK` du SQL. On ne lit que ce qui
    est écrit — un domaine déduit des valeurs observées serait une tautologie : il déclarerait
    conforme exactement ce qui est là, y compris les 11 points du golfe de Guinée.
    """
    domaines: dict[str, dict] = {}

    for fichier in _fichiers(cible, (".py",)):
        try:
            arbre = ast.parse(fichier.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for affectation in [n for n in ast.walk(arbre) if isinstance(n, ast.Assign)]:
            noms = [c.id for c in affectation.targets if isinstance(c, ast.Name)]
            if not noms or not isinstance(affectation.value, ast.Call):
                continue
            for appel in [n for n in ast.walk(affectation.value) if isinstance(n, ast.Call)]:
                quoi = appel.func.attr if isinstance(appel.func, ast.Attribute) else (
                    appel.func.id if isinstance(appel.func, ast.Name) else "")
                if quoi == "Range":
                    bornes = {k.arg: _litteral(k.value) for k in appel.keywords
                              if k.arg in ("min", "max")}
                    if bornes:
                        domaines[noms[0]] = {
                            "type": "intervalle", **bornes,
                            "source": f"{fichier.name} · validate.Range",
                        }
                elif quoi == "OneOf" and appel.args:
                    valeurs = _litteral(appel.args[0])
                    if valeurs:
                        domaines[noms[0]] = {
                            "type": "enumeration", "valeurs": list(valeurs),
                            "source": f"{fichier.name} · validate.OneOf",
                        }

    for fichier in _fichiers(cible, (".sql",)):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for m in _CHECK_BETWEEN.finditer(texte):
            domaines.setdefault(m.group("col"), {
                "type": "intervalle", "min": float(m.group("min")), "max": float(m.group("max")),
                "source": f"{fichier.name} · CHECK BETWEEN",
            })
        for m in _CHECK_IN.finditer(texte):
            valeurs = [v.strip().strip("'\"") for v in m.group("valeurs").split(",")]
            domaines.setdefault(m.group("col"), {
                "type": "enumeration", "valeurs": valeurs,
                "source": f"{fichier.name} · CHECK IN",
            })
    return domaines


def juger_champ(nom: str, valeurs: list, domaines: dict[str, dict], *, cle=None) -> dict:
    """Le second contrôle : la valeur est PRÉSENTE, mais est-elle PLAUSIBLE ?

    `cle` : fonction qui, pour un rang, rend son identifiant lisible. Sans elle, les lignes hors
    domaine sortent par leur position — utilisable, mais moins que par leur clé métier.

    Le premier contrôle (présence) n'est pas refait ici : `None` est écarté du jugement et
    COMPTÉ à part. Le confondre avec « hors domaine » ferait rendre deux fois le même constat, et
    surtout ferait croire que le contrôle de présence est redondant — il ne l'est pas, c'est son
    JUMEAU.
    """
    domaine = domaines.get(nom)
    presentes = [(rang, v) for rang, v in enumerate(valeurs) if v is not None]
    absentes = len(valeurs) - len(presentes)

    if not domaine:
        return {
            "champ": nom, "statut": NON_DECLARABLE, "absentes": absentes, "hors_domaine": [],
            "motif": (
                f"aucun domaine DÉCLARÉ pour « {nom} » — ni `validate.Range`/`OneOf` au schéma, "
                "ni `CHECK` au SQL. La plausibilité n est donc pas jugeable ici, et l inventer "
                "serait pire : le domaine se déclare (schéma ou projet), il ne se devine pas"
            ),
        }

    fautives = []
    for rang, valeur in presentes:
        if domaine["type"] == "intervalle":
            try:
                nombre = float(valeur)
            except (TypeError, ValueError):
                continue
            mini, maxi = domaine.get("min"), domaine.get("max")
            if (mini is not None and nombre < mini) or (maxi is not None and nombre > maxi):
                fautives.append((rang, valeur))
        elif domaine["type"] == "enumeration" and valeur not in domaine["valeurs"]:
            fautives.append((rang, valeur))

    if not fautives:
        return {
            "champ": nom, "statut": CONFORME, "absentes": absentes, "hors_domaine": [],
            "motif": (
                f"{len(presentes)} valeur(s) de « {nom} » dans le domaine déclaré "
                f"({domaine['source']})"
                + (f" ; {absentes} absente(s), jugée(s) par le contrôle de PRÉSENCE" if absentes
                   else "")
            ),
        }

    nommees = [
        f"{(cle(rang) if cle else f'rang {rang}')} = {valeur!r}" for rang, valeur in fautives[:20]
    ]
    reste = f" (+{len(fautives) - 20} autres)" if len(fautives) > 20 else ""
    return {
        "champ": nom, "statut": HORS_DOMAINE, "absentes": absentes,
        "hors_domaine": [rang for rang, _ in fautives],
        "motif": (
            f"{len(fautives)} valeur(s) de « {nom} » HORS du domaine déclaré "
            f"({domaine['source']}) — présentes, donc invisibles au contrôle de présence : "
            + " · ".join(nommees) + reste
        ),
    }


#: Le cas de (0,0) : deux champs chacun dans son domaine, dont la COMBINAISON est fausse. Un
#: contrôle par champ ne peut pas le voir — et le dire est plus utile que de faire semblant.
COUPLES_SUSPECTS = (
    ("latitude", "longitude", (0, 0),
     "le point (0,0) est dans le golfe de Guinée : chaque coordonnée est dans son domaine, "
     "c est leur COMBINAISON qui est fausse. 11 annonces sur 1 249 y étaient placées, avec des "
     "adresses françaises réelles (anomalie 9873, priorité 1)"),
)


def juger_couples(lignes: list[dict]) -> list[dict]:
    """Les combinaisons fausses dont chaque terme est valide. Nommément, jamais devinées.

    Un contrôle par champ ne peut PAS voir (0,0) : 0 est une latitude valide et 0 une longitude
    valide. C'est la limite du contrôle par champ, et la nommer est ce qui empêche de croire que
    « tous les champs conformes » veut dire « la donnée est bonne ».
    """
    constats = []
    for champ_a, champ_b, (val_a, val_b), motif in COUPLES_SUSPECTS:
        fautives = [
            i for i, ligne in enumerate(lignes)
            if champ_a in ligne and champ_b in ligne
            and _egal(ligne[champ_a], val_a) and _egal(ligne[champ_b], val_b)
        ]
        if fautives:
            constats.append({
                "couple": (champ_a, champ_b), "rangs": fautives,
                "motif": f"{len(fautives)} ligne(s) au couple ({champ_a}, {champ_b}) = "
                         f"({val_a}, {val_b}) — {motif}",
            })
    return constats


def _egal(valeur, attendu) -> bool:
    try:
        return valeur is not None and float(valeur) == float(attendu)
    except (TypeError, ValueError):
        return False


NON_JUGE = [
    "domaine : seuls les domaines DÉCLARÉS sont lus (`validate.Range`/`OneOf`, `CHECK` SQL). Un "
    "domaine déduit des valeurs observées serait une tautologie — il déclarerait conforme "
    "exactement ce qui est là, y compris les 11 points du golfe de Guinée",
    "domaine : un contrôle par CHAMP ne voit jamais une combinaison fausse dont chaque terme est "
    "valide. Les couples connus sont nommés (`COUPLES_SUSPECTS`) ; les autres échappent, et "
    "c est une limite, pas un oubli",
    "domaine : la PRÉSENCE n est pas rejugée ici — elle est comptée à part. Le contrôle de "
    "présence n est pas redondant, il est le JUMEAU de celui-ci",
]
