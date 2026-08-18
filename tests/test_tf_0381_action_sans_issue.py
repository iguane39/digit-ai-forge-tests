"""TF-0381 — une action manuelle émise pour un pan que le rapport déclare à zéro élément.

Le fait, mesuré sur un audit réel (rapport du 18/08, projet d'ANALYSE qui ne sert aucune
application et n'écrit nulle part) : **dix actions `manuelle_utilisateur`**, une par pan, toutes
réclamant les six mêmes variables `DATABRICKS_*` — y compris pour `prompts` (0 prompt trouvé) et
`qualif`, qui attend une URL servie et pas un entrepôt.

Et le rapport se contredisait sur le même pan, deux champs d'écart :

  - motif du pan   : « api : 0 elements INVENTORIES (0 operations, 0 codes) »
  - action générée : « 1 élément(s) sont inventoriés mais aucune exécution ne pouvait… »

Les deux étaient exacts sur des objets différents — le second comptait le **marque-place**
`pan:api`, posé exprès pour qu'un pan sans surface ne soit pas tu. C'est le mot « inventoriés »
qui mentait, pas la mécanique.

Ce qui est corrigé tient en une distinction et une soustraction :

  1. un `NonTestable` dit désormais s'il nomme un élément **inventorié** ou un marque-place, et
     si sa configuration est **constatée** ou **présumée** ;
  2. la combinaison « aucun élément inventorié » + « configuration seulement présumée » ne
     produit plus d'action humaine. L'entrée **reste au rapport** avec son motif : ce qui
     disparaît est la demande adressée à quelqu'un, pas le constat. Nommer une limite n'est pas
     réclamer un geste.
"""

from __future__ import annotations

from forge_tests.actions import classifier


def _non_testable(pan: str, *, element: str, inventorie: bool, provenance: str) -> dict:
    return {
        "element": element,
        "champs_requis": ["DATABRICKS_HOST", "DATABRICKS_WAREHOUSE_ID"],
        "pan": pan,
        "motif": f"{pan} : non exercable sans configuration ({provenance})",
        "inventorie": inventorie,
        "provenance": provenance,
    }


def _configs(actions: list[dict]) -> list[dict]:
    return [a for a in actions if a["finding_ref"].startswith("non-testable:")]


# --- La soustraction : plus d'action là où elle ne mène nulle part -----------------------------
def test_marque_place_et_config_PRESUMEE_ne_produisent_plus_d_action() -> None:
    """Le cas réel, exactement : un pan sans surface, une configuration déduite d un
    `.env.example` que nul adaptateur ne revendique."""
    actions = classifier(
        [],
        non_testables=[_non_testable("api", element="pan:api", inventorie=False,
                                     provenance="presume")],
    )

    assert _configs(actions) == [], "une configuration reclamee pour un pan sans surface"


def test_le_pan_reste_NOMME_au_rapport_ce_qui_disparait_est_la_DEMANDE() -> None:
    """La moitié qui compte autant : `non_testables` est la liste du rapport, `classifier` ne la
    modifie pas. Supprimer le constat AVEC l action aurait remplacé un bruit par un silence."""
    entrees = [_non_testable("api", element="pan:api", inventorie=False, provenance="presume")]

    classifier([], non_testables=entrees)

    assert entrees[0]["motif"], "le constat survit a la suppression de l action"
    assert entrees[0]["pan"] == "api"


def test_les_DIX_pans_du_cas_reel_ne_produisent_plus_dix_demandes() -> None:
    """C'est l'ampleur qui faisait le mal : dix gestes identiques adressés à un humain, sur un
    projet d'analyse. Une action fausse coûte peu ; dix usent la crédibilité des vraies."""
    pans = ["api", "back", "batch", "data", "fichiers", "front", "migrations", "prompts",
            "qualif", "securite"]
    actions = classifier(
        [],
        non_testables=[_non_testable(p, element=f"pan:{p}", inventorie=False,
                                     provenance="presume") for p in pans],
    )

    assert _configs(actions) == []
    assert not [a for a in actions if a["categorie"] == "manuelle_utilisateur"]


# --- Et ce qui doit SURVIVRE : les deux moitiés sans lesquelles on aurait tout éteint ----------
def test_un_element_INVENTORIE_produit_toujours_son_action() -> None:
    """Le sens sans lequel la correction serait une régression : quand il y a bien quelque chose
    à mesurer, le manque de configuration reste un geste d exploitant. C'est RT-6."""
    actions = classifier(
        [],
        non_testables=[_non_testable("api", element="endpoint:GET /commandes", inventorie=True,
                                     provenance="constate")],
    )

    config = _configs(actions)
    assert len(config) == 1
    assert config[0]["categorie"] == "manuelle_utilisateur"
    assert "1 élément(s) sont inventoriés" in config[0]["attendu"]


def test_une_config_CONSTATEE_survit_meme_sans_element_inventorie() -> None:
    """L'autre moitié, et elle est plus fine : « constaté » veut dire qu une TRACE D EXÉCUTION a
    nommé la variable. Le pan n a rien inventorié parce qu il n a pas pu tourner — renseigner la
    configuration est alors exactement ce qui permettra de savoir s il y a quelque chose."""
    actions = classifier(
        [],
        non_testables=[_non_testable("data", element="pan:data", inventorie=False,
                                     provenance="constate")],
    )

    config = _configs(actions)
    assert len(config) == 1
    assert "aucun élément n est inventorié" in config[0]["attendu"]
    assert "TRACE D EXÉCUTION" in config[0]["attendu"], "le motif dit POURQUOI il est légitime"


# --- La contradiction du rapport, refermée ----------------------------------------------------
def test_un_marque_place_n_est_JAMAIS_compte_comme_element_inventorie() -> None:
    """Le mot qui mentait. Le marque-place est exclu du compte, quelle que soit la provenance —
    sinon le rapport annonce « 1 élément inventorié » deux champs après « 0 elements
    INVENTORIES »."""
    actions = classifier(
        [],
        non_testables=[
            _non_testable("data", element="pan:data", inventorie=False, provenance="constate"),
            _non_testable("data", element="table:bronze.ventes", inventorie=True,
                          provenance="constate"),
        ],
    )

    for a in _configs(actions):
        assert "1 élément(s) sont inventoriés" not in a["attendu"] or "pan:" not in str(a)
    comptes = [a["attendu"] for a in _configs(actions)
               if "élément(s) sont inventoriés" in a["attendu"]]
    assert all("2 élément(s)" not in c for c in comptes), "le marque-place gonflait le compte"


def test_un_pan_NON_COUVERT_sans_action_de_config_n_est_plus_adresse_a_l_exploitant() -> None:
    """Conséquence en cascade, et elle est voulue : la catégorie d une action « pan non couvert »
    se choisit selon qu une configuration l aurait débloqué. Sans demande de configuration
    exploitable, le pan n est plus adressé à l exploitant — le reproche exact de l item."""
    actions = classifier(
        [],
        non_testables=[_non_testable("prompts", element="pan:prompts", inventorie=False,
                                     provenance="presume")],
        pans_non_couverts=[{"pan": "prompts", "motif": "aucun prompt adressable",
                            "pour_couvrir": "rendre les prompts adressables"}],
    )

    pan = [a for a in actions if a["finding_ref"] == "pan-non-couvert:prompts"]
    assert len(pan) == 1
    assert pan[0]["categorie"] != "manuelle_utilisateur"
    assert pan[0]["etape_cible"] != "mep-config"


def test_la_limite_est_declaree() -> None:
    """Loi 3. Une action qui disparaît sans que la règle soit écrite est une mesure qu on croira
    perdue au premier audit qui l attendra."""
    from forge_tests.actions import NON_JUGE

    declare = " ".join(NON_JUGE)
    assert "PRESUMEE" in declare
    assert "ce qui disparait est la demande, pas le constat" in declare
