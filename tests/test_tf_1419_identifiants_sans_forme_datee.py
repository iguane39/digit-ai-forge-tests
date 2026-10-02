"""TF-1419 — `est_epingle()` prenait les identifiants Claude EN SERVICE pour des alias mouvants,
faute de connaître les noms de version publiés sans variante datée.

Mesuré le 24/09/2026 en exécutant `est_epingle()` (fichier au commit `60d470b` du 03/09) :
`claude-fable-5-1`, `claude-opus-5-5`, `claude-opus-5` et `claude-sonnet-5` rendaient `False` —
alias mouvant — alors que le tableau des modèles du skill `claude-api` (Claude Code 2.1.281,
`shared/models.md`) ne donne aucun identifiant daté pour les modèles sortis depuis Opus 4.6 :
l'identifiant publié EST la version, et le même skill interdit d'en fabriquer une variante
datée. Produit-61 a dû contester le constat le 05/09/2026 pour que son audit converge ;
confirmé TOUJOURS reproductible le 02/10/2026 en rejouant la fonction directement.

Correction : un référentiel daté et sourcé (`_IDENTIFIANTS_SANS_FORME_DATEE`, loi n° 4 du pilot)
des identifiants publiés sans variante datée, lu par `est_epingle()` avant de conclure à un
alias mouvant. Deux sens, dans les deux cas déjà couverts par `test_tf_0200_prompts.py` pour les
VRAIS alias (`-latest`, `gpt-4o`) — ce fichier n'y touche pas, et le prouve.
"""

from __future__ import annotations

from forge_tests.adaptateurs import prompts


def test_les_noms_de_version_en_service_sont_desormais_epingles() -> None:
    """Le défaut mesuré le 24/09 et confirmé le 02/10 : ces quatre noms rendaient False."""
    for nom in ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5"):
        assert prompts.est_epingle(nom), (
            f"« {nom} » devrait être lu comme épinglé via le référentiel "
            "_IDENTIFIANTS_SANS_FORME_DATEE — aucune variante datée n'est publiée pour ce nom"
        )


def test_le_verrou_ATTRAPE_le_defaut_du_24_09_sans_le_referentiel() -> None:
    """Second sens : sans le référentiel, la seule règle _EPINGLE (suffixe daté) rejette bien
    ces quatre noms — c'est exactement le faux signal mesuré, et ce test prouve qu'il existe
    toujours à ce niveau (la correction vit dans `est_epingle`, pas dans `_EPINGLE`)."""
    for nom in ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5"):
        assert not prompts._EPINGLE.search(nom), (
            f"« {nom} » porterait désormais un suffixe daté reconnu par _EPINGLE — si "
            "Anthropic en a publié un, retirer ce nom de _IDENTIFIANTS_SANS_FORME_DATEE "
            "plutôt que de laisser les deux mécanismes se chevaucher"
        )


def test_un_vrai_alias_qui_pointe_vers_une_forme_datee_reste_signale() -> None:
    """`claude-haiku-4-5` pointe vers `claude-haiku-4-5-20251001` : c'est un VRAI alias, il
    existe une forme à épingler à sa place, et il ne doit PAS entrer dans le référentiel."""
    assert "claude-haiku-4-5" not in prompts._SANS_FORME_DATEE
    assert not prompts.est_epingle("claude-haiku-4-5")


def test_un_suffixe_latest_reste_signale_meme_sur_une_famille_du_referentiel() -> None:
    """Fixture rouge de l'item : un `-latest` reste un alias mouvant, quelle que soit la
    famille — le référentiel ôte des faux positifs mesurés, il n'assouplit rien d'autre."""
    assert not prompts.est_epingle("claude-3-5-sonnet-latest")


def test_le_referentiel_est_date_et_source() -> None:
    """Loi n° 4 du pilot : une donnée volatile vit éditable, DATÉE et SOURCÉE — jamais une
    liste nue qu'aucun lecteur ne peut situer ni vérifier."""
    for entree in prompts._IDENTIFIANTS_SANS_FORME_DATEE:
        assert entree["nom"], "un référentiel sans nom ne référentie rien"
        assert entree["releve_le"], f"{entree['nom']} : aucune date de relevé"
        assert entree["source"], f"{entree['nom']} : aucune source"
