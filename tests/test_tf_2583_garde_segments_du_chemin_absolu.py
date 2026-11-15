"""TF-2583 — un contrôle de la recette refuse `.parts` / `.parents` d'un chemin ABSOLU.

TF-2523 (14/11/2026) puis TF-2577 (15/11/2026) ont corrigé 4 puis 11 modules qui jugeaient les
segments du chemin absolu d'un fichier contre une liste de noms (`.claude`, `node_modules`, `input`,
`build`…) : un projet posé SOUS un de ces dossiers voyait son contenu écarté, la recette mesurait le
poste et non le dépôt. Aucune garde ne tenait la classe : le prochain `chemin.parts` écrit à la main
la rouvrait en silence.

Le contrôle lit le code de la forge (`forge_tests/`, `recette/`) par son arbre syntaxique et refuse
tout accès `.parts` ou `.parents` qui ne soit pas :
  - dans `forge_tests/exclusions.py`, la source unique de l'exclusion de périmètre ;
  - pris sur un chemin RELATIF : le résultat direct d'un `.relative_to(…)`, un nom affecté dans la
    même fonction par un `.relative_to(…)`, ou le repli sans racine du motif de TF-2577
    (`chemin.parts if racine is None else exclusions.parties_du_projet(chemin, racine)`) ;
  - ou sur la liste motivée `SITES_STRUCTURE_IMMEDIATE`, les sites qui lisent la structure
    immédiate d'un chemin (son nombre de segments, sa position depuis son propre fichier, son
    appartenance à un ancêtre) sans juger aucun NOM de dossier.

Une entrée de la liste qui ne correspond plus à aucun site est refusée elle aussi : une exemption
qui survit à son site couvrirait le prochain.

Portée : le code de la forge. `tests/` lit sa propre position
(`Path(__file__).resolve().parents[1]`) sur des dépôts qu'il fabrique ; il reste hors du contrôle,
comme `fixtures/` (données d'acceptation).

Deux sens, chacun avec sa fixture : ROUGE — l'ancien code de `noyau`, de `prompts` et de `chaine`
(avant TF-2577), et un `.parents` jugé par nom ; VERT — le correctif que le message propose
(`exclusions.parties_du_projet`), et le dépôt tel qu'il est.
"""

from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Le code de la forge : ce qui juge des chemins de projets audités.
PAQUETS_DU_CODE = ("forge_tests", "recette")

#: La source unique de l'exclusion de périmètre, seule à lire les segments d'un chemin comme tels.
FICHIER_EXEMPTE = "forge_tests/exclusions.py"

#: Les sites qui lisent la structure IMMÉDIATE d'un chemin, sans juger de nom de dossier.
#: Clé : (fichier relatif, expression de l'accès telle que `ast.unparse` la rend) ; valeur : motif.
SITES_STRUCTURE_IMMEDIATE: dict[tuple[str, str], str] = {
    ("forge_tests/__main__.py", "args.python.parts"): (
        "`len(…) == 1` : l'argument `--python` est-il un nom nu (cherché dans le PATH) ou un "
        "chemin ? Compte les segments, ne lit aucun nom de dossier."
    ),
    ("forge_tests/execution.py", "chemin.parts"): (
        "`len(…) == 1` sur la variable d'environnement de l'interpréteur : nom nu ou chemin, "
        "même geste que `--python`, aucun nom de dossier lu."
    ),
    ("forge_tests/adaptateurs/personas.py", "Path(relatif).parts"): (
        "`relatif` est reçu en texte, déjà calculé par `chemin.relative_to(cible).as_posix()` à "
        "l'unique appel (`_parcours_bruts`) : les segments sont ceux du projet."
    ),
    ("forge_tests/adaptateurs/reglages.py", "Path(__file__).resolve().parents"): (
        "`parents[2].parent` : la position du registre depuis le fichier du module lui-même, par "
        "son rang ; aucun nom n'est comparé."
    ),
    ("forge_tests/adaptateurs/securite.py", "application.parents"): (
        "`cible not in application.parents` : le dossier d'application est-il DANS le projet ? "
        "Compare deux chemins entiers entre eux, aucun nom de dossier."
    ),
    ("forge_tests/livrables/__init__.py", "depot.parents"): (
        "`racine in depot.parents` (G-1) : le dépôt des livrables est-il DANS le projet audité ? "
        "Compare deux chemins entiers entre eux, aucun nom de dossier."
    ),
}

CONSEIL = (
    "Un `.parts` ou `.parents` pris sur un chemin absolu juge aussi le dossier où le projet est "
    "posé (TF-2523, TF-2577). Écris `exclusions.parties_du_projet(chemin, racine)` ou "
    "`chemin.relative_to(racine).parts` ; si le site lit vraiment la structure immédiate du chemin "
    "(sans juger de nom), ajoute-le à SITES_STRUCTURE_IMMEDIATE avec son motif."
)


def _est_un_chemin_relatif(noeud: ast.AST) -> bool:
    """Le résultat d'un `.relative_to(…)`, éventuellement suivi d'appels (`.with_suffix(…)`)."""
    while isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute):
        if noeud.func.attr == "relative_to":
            return True
        noeud = noeud.func.value
    return False


def _noms_relatifs(portee: ast.AST) -> set[str]:
    """Les noms affectés, dans cette fonction (ou ce module), par un `.relative_to(…)`."""
    return {
        cible.id
        for affectation in ast.walk(portee)
        if isinstance(affectation, ast.Assign) and _est_un_chemin_relatif(affectation.value)
        for cible in affectation.targets
        if isinstance(cible, ast.Name)
    }


def _repli_sans_racine(acces: ast.Attribute, parents: dict[ast.AST, ast.AST]) -> bool:
    """`x.parts if racine is None else exclusions.parties_du_projet(x, racine)` (TF-2577)."""
    noeud: ast.AST = acces
    while noeud in parents:
        pere = parents[noeud]
        if isinstance(pere, ast.IfExp) and pere.body is noeud:
            autre = pere.orelse
            if isinstance(autre, ast.Call):
                fonction = autre.func
                nom = fonction.attr if isinstance(fonction, ast.Attribute) else (
                    fonction.id if isinstance(fonction, ast.Name) else ""
                )
                return nom == "parties_du_projet"
            return False
        noeud = pere
    return False


def sites_refuses(source: str, fichier: str) -> list[tuple[int, str]]:
    """Rend `(ligne, expression)` de chaque `.parts` / `.parents` que la règle refuse.

    `fichier` est le chemin relatif au dépôt, en `/` : il sert à `FICHIER_EXEMPTE` et à la liste.
    """
    if fichier == FICHIER_EXEMPTE:
        return []
    arbre = ast.parse(source, filename=fichier)
    parents = {fils: pere for pere in ast.walk(arbre) for fils in ast.iter_child_nodes(pere)}
    refuses: list[tuple[int, str]] = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Attribute) and noeud.attr in ("parts", "parents")):
            continue
        recepteur = noeud.value
        if _est_un_chemin_relatif(recepteur):
            continue
        portee: ast.AST = noeud
        while portee in parents and not isinstance(
            portee, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            portee = parents[portee]
        if isinstance(recepteur, ast.Name) and recepteur.id in _noms_relatifs(portee):
            continue
        if _repli_sans_racine(noeud, parents):
            continue
        expression = ast.unparse(noeud)
        if (fichier, expression) in SITES_STRUCTURE_IMMEDIATE:
            continue
        refuses.append((noeud.lineno, expression))
    return sorted(refuses)


def _sources_du_code() -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for paquet in PAQUETS_DU_CODE:
        for chemin in sorted((RACINE / paquet).rglob("*.py")):
            relatif = chemin.relative_to(RACINE)
            if "__pycache__" in relatif.parts:
                continue
            sources.append((relatif.as_posix(), chemin.read_text(encoding="utf-8")))
    return sources


# --- le dépôt tel qu'il est ----------------------------------------------------------------------
def test_le_code_de_la_forge_ne_juge_aucun_segment_du_chemin_absolu() -> None:
    """Le contrôle réel : aucun `.parts` / `.parents` hors règle dans le code de la forge."""
    fautifs = [
        f"{fichier}:{ligne} — `{expression}`"
        for fichier, source in _sources_du_code()
        for ligne, expression in sites_refuses(source, fichier)
    ]
    assert fautifs == [], CONSEIL + " Refusés : " + " ; ".join(fautifs)


def test_chaque_exemption_motivee_correspond_encore_a_un_site() -> None:
    """Une entrée qui ne couvre plus rien est refusée : elle couvrirait le prochain."""
    presents: set[tuple[str, str]] = set()
    for fichier, source in _sources_du_code():
        arbre = ast.parse(source, filename=fichier)
        presents |= {
            (fichier, ast.unparse(noeud))
            for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Attribute) and noeud.attr in ("parts", "parents")
        }
    perimees = sorted(set(SITES_STRUCTURE_IMMEDIATE) - presents)
    assert perimees == [], f"exemptions sans site : {perimees}"


def test_chaque_exemption_porte_son_motif() -> None:
    sans_motif = [cle for cle, motif in SITES_STRUCTURE_IMMEDIATE.items() if len(motif) < 40]
    assert sans_motif == [], f"exemption sans motif lisible : {sans_motif}"


# --- ROUGE : le défaut de la classe est refusé, pour la bonne raison -----------------------------
# Les trois extraits sont l'ancien code de TF-2577, tel qu'il était avant la correction.
def test_rouge_l_ancien_noyau_est_refuse() -> None:
    source = (
        "def provenance_de(source):\n"
        "    chemin = Path(str(source))\n"
        "    parties = {p.lower() for p in chemin.parts}\n"
        "    return parties\n"
    )
    assert sites_refuses(source, "forge_tests/noyau.py") == [(3, "chemin.parts")]


def test_rouge_l_ancien_prompts_est_refuse() -> None:
    source = (
        "def est_un_fichier_de_test(chemin):\n"
        "    return '__tests__' in chemin.parts\n"
    )
    assert sites_refuses(source, "forge_tests/adaptateurs/prompts.py") == [(2, "chemin.parts")]


def test_rouge_l_ancienne_chaine_est_refusee() -> None:
    source = (
        "def suites_du_depot(racine):\n"
        "    return [s for s in racine.rglob('test_*.py')\n"
        "            if not any(p in OUTILLAGE for p in s.parts)]\n"
    )
    assert sites_refuses(source, "forge_tests/chaine.py") == [(3, "s.parts")]


def test_rouge_un_parents_juge_par_nom_est_refuse() -> None:
    source = (
        "def sous_input(chemin):\n"
        "    return any(a.name == 'input' for a in chemin.parents)\n"
    )
    assert sites_refuses(source, "forge_tests/domaine.py") == [(2, "chemin.parents")]


def test_rouge_le_meme_acces_hors_de_la_liste_motivee_est_refuse() -> None:
    """Une exemption est liée à son fichier ET à son expression : ailleurs, le site est refusé."""
    source = "def nu(chemin):\n    return len(chemin.parts) == 1\n"
    assert sites_refuses(source, "forge_tests/execution.py") == []
    assert sites_refuses(source, "forge_tests/autre_module.py") == [(2, "chemin.parts")]


def test_rouge_un_nom_relatif_reaffecte_dans_une_autre_fonction_ne_couvre_pas() -> None:
    source = (
        "def a(fichier, racine):\n"
        "    relatif = fichier.relative_to(racine)\n"
        "    return relatif.parts\n"
        "\n"
        "def b(relatif):\n"
        "    return relatif.parts\n"
    )
    assert sites_refuses(source, "forge_tests/x.py") == [(6, "relatif.parts")]


# --- VERT : ce que la règle laisse passer, et le remède qu'elle recommande -----------------------
def test_vert_le_remede_du_message_passe() -> None:
    """Le correctif de TF-2577 pour `noyau` : le message le propose, il doit être accepté."""
    source = (
        "def provenance_de(source, racine=None):\n"
        "    chemin = Path(str(source))\n"
        "    parties = {p.lower() for p in exclusions.parties_du_projet(chemin, racine)}\n"
        "    return parties\n"
    )
    assert sites_refuses(source, "forge_tests/noyau.py") == []


def test_vert_un_relative_to_direct_passe() -> None:
    source = "def f(s, d):\n    return any(p in X for p in s.relative_to(d).parts[:-1])\n"
    assert sites_refuses(source, "forge_tests/x.py") == []


def test_vert_un_nom_affecte_par_relative_to_passe() -> None:
    source = (
        "def f(fichier, build):\n"
        "    relatif = fichier.relative_to(build).with_suffix('')\n"
        "    return list(relatif.parts)\n"
    )
    assert sites_refuses(source, "forge_tests/x.py") == []


def test_vert_le_repli_sans_racine_de_TF_2577_passe() -> None:
    source = (
        "def f(chemin, racine=None):\n"
        "    return chemin.parts if racine is None else (\n"
        "        exclusions.parties_du_projet(chemin, racine))\n"
    )
    assert sites_refuses(source, "forge_tests/x.py") == []


def test_vert_un_repli_vers_autre_chose_ne_passe_pas() -> None:
    """Le repli n'est reconnu que vers `parties_du_projet` : un autre `else` reste refusé."""
    source = "def f(chemin, racine=None):\n    return chemin.parts if racine is None else ()\n"
    assert sites_refuses(source, "forge_tests/x.py") == [(2, "chemin.parts")]


def test_vert_exclusions_py_est_la_source_unique() -> None:
    source = "def f(chemin):\n    return Path(chemin).parts\n"
    assert sites_refuses(source, "forge_tests/exclusions.py") == []
    assert sites_refuses(source, "forge_tests/noyau.py") == [(2, "Path(chemin).parts")]


# --- le seul site de la classe que le contrôle a trouvé : `gabarit_env.cles_connues` -------------
# `"__pycache__" in source.parts` jugeait aussi les dossiers PARENTS du paquet lu : posé sous un
# dossier `__pycache__`, il ne lisait plus aucun fichier, et le gabarit sortait sans une clé.
def test_gabarit_env_lit_un_paquet_pose_sous_un_dossier_pycache(tmp_path: Path) -> None:
    from forge_tests import gabarit_env

    base = tmp_path / "__pycache__" / "forge"
    base.mkdir(parents=True)
    (base / "module.py").write_text('CLE = "FORGE_TESTS_CLE_DE_TEST_2583"\n', encoding="utf-8")
    assert gabarit_env.cles_connues(base) == ["FORGE_TESTS_CLE_DE_TEST_2583"]


def test_gabarit_env_ecarte_toujours_le_pycache_du_paquet(tmp_path: Path) -> None:
    from forge_tests import gabarit_env

    base = tmp_path / "__pycache__" / "forge"
    (base / "__pycache__").mkdir(parents=True)
    (base / "module.py").write_text('CLE = "FORGE_TESTS_CLE_VUE_2583"\n', encoding="utf-8")
    (base / "__pycache__" / "copie.py").write_text(
        'CLE = "FORGE_TESTS_CLE_ECARTEE_2583"\n', encoding="utf-8"
    )
    assert gabarit_env.cles_connues(base) == ["FORGE_TESTS_CLE_VUE_2583"]
