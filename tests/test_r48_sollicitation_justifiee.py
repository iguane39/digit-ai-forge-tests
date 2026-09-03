"""R-48 — UNE SOLLICITATION HUMAINE DIT POURQUOI ELLE N'EST PAS DEDUCTIBLE (24/08/2026).

LE FAIT, ET C'EST UN RETOUR HUMAIN EN SEANCE (23/08) : « demande a la Factory de retravailler les
elements qu'elle peut traiter toute seule sans que j'aie de decisions a prendre a ce niveau-la —
l'exemple de l'input est particulierement parlant, forcement que les inputs ne pouvaient pas entrer
dans le perimetre d'audit, c'est juste logique ». Les quatre constats du lot de ce jour-la n'etaient
pas quatre defauts : c'etait quatre fois le meme reflexe. L'outil preferait DEGRADER son verdict et
rendre la main plutot que trancher.

Le cout est double, et le second est le pire : le temps humain, et le SIGNAL NOYE. Un rapport qui
demande quatre arbitrages inutiles apprend a son lecteur a survoler la liste — donc a manquer le
cinquieme, celui qui comptait.

CE QUE CE TEST VERROUILLE : les deux familles d'action qui reclament une INFORMATION ou un
ARBITRAGE portent leur `non_deductible`. Sans ce test, le champ pourrait disparaitre a la premiere
reecriture du module sans qu'aucun rouge ne le dise — et le pilot ne s'en apercevrait qu'au prochain
lot, chez un client.

CE QU'IL NE VERROUILLE PAS, et c'est deliberé : les actions qui demandent de CORRIGER un defaut
trouve. Demander un travail n'est pas demander une decision, et la raison pour laquelle la forge ne
le fait pas elle-meme est permanente — elle audite, elle ne modifie pas le produit. Exiger une
justification sous chacune produirait du remplissage : quatorze suites etaient concernees.
"""
import re

from forge_tests import actions

# Les tournures qui disent une NON-DEDUCTIBILITE, et non ce qu'il faut faire.
RAISON = re.compile(
    r"(arbitr|aucun agent|personne d autre|ne se deduit|ne se déduit|deux "
    r"(personnes|developpeurs|développeurs) competent|deux (personnes|developpeurs|développeurs) "
    r"compétent|acces|accès|jeton|hote|hôte|secret|identifiant|qui tient l environnement|intention "
    r"du projet)",
    re.I,
)


def test_configuration_reclamee_dit_pourquoi_elle_nest_pas_deductible():
    """Une configuration d'audit absente est le SEUL manque que l'outil ne peut pas combler."""
    action = actions._action_configuration(
        "non-testable:api:DATABRICKS_HOST", "du pan « api »", {"requete"}, ["DATABRICKS_HOST"]
    )
    assert action["categorie"] == "manuelle_utilisateur"
    assert action.get("non_deductible"), (
        "R-48 : la sollicitation ne dit pas pourquoi elle est necessaire")
    assert RAISON.search(action["non_deductible"]), (
        "R-48 : la justification parle de ce qu'il FAUT faire et non de ce que l'outil ne pouvait "
        f"pas decider — « {action['non_deductible'][:90]} »"
    )


def test_pan_non_couvert_justifie_selon_son_destinataire():
    """La non-deductibilite depend du DESTINATAIRE : un acces manquant n'est pas un arbitrage."""
    dev = actions.classifier(
        [], non_testables=[],
        pans_non_couverts=[
            {"pan": "front", "motif": "0 element", "chemin": "ecrire un test"}],
    )
    assert len(dev) == 1
    assert dev[0]["categorie"] == "manuelle_dev"
    assert "ARBITRAGE" in dev[0]["non_deductible"], (
        "ecrire la couverture d'un pan est un choix de conception : le dire est ce qui distingue "
        "cette demande d'un defaut d'automatisation"
    )


def test_corriger_un_defaut_trouve_nexige_aucune_justification():
    """BORNE assumee : demander un TRAVAIL n'est pas demander une DECISION.

    Sans cette borne, R-48 exigerait une phrase de non-deductibilite sous « corrigez ce lien
    casse » — quatorze suites concernees, et autant de remplissage qui userait la credibilite de
    la regle. Le test existe pour que la borne ne se perde pas dans une relecture zelee.
    """
    action = actions._action({"classe": "lien-casse", "id": "/a", "message": "404"}, set())
    assert action["categorie"] in actions.CATEGORIES
    assert "non_deductible" not in action, (
        "une action de CORRECTION n'a pas a se justifier : la raison est permanente et vaut pour "
        "toutes — la forge audite, elle ne modifie pas le produit"
    )
