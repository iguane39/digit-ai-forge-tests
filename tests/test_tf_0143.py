"""TF-0143 — le générateur de cas API produit des cas EXÉCUTABLES, pas seulement plausibles.

`forge_tests.generateur` synthétisait déjà des cas nominal (2xx) + limite (404, ressource
inexistante) + rejet (401, 422) depuis le schéma OpenAPI, en refusant explicitement ce qu il ne
sait pas dériver honnêtement (400/403/409/415/429/500 → `non-generables.json`, jamais un cas
inventé). Ce qui manquait : la PREUVE que le fichier assemblé COMPILE — la moitié de l oracle
« collectable » qui ne dépend d aucun environnement de projet cible (l autre moitié, la collecte
RÉELLE sous pytest avec les dépendances de l application, exige les bancs et vit dans
`recette/precision_generateur.py`, seul endroit du dépôt qui dispose de leurs `.venv`).

Sans ce garde, un défaut du générateur (gabarit mal formé, valeur mal échappée) se serait déposé
en PROPOSITION invalide — un fichier qu on ne peut même pas ouvrir avec pytest — sans qu aucun
signal ne le distingue d une proposition saine. La loi du générateur (« il ne produit que ce
qu il sait construire honnêtement ») s applique donc aussi à la forme du fichier, pas seulement
au choix des cas.
"""

from __future__ import annotations

from forge_tests.generateur import CasNonCollectable, construire, verifier_syntaxe

# Schéma OpenAPI minimal : une collection créable (POST, corps requis) et sa ressource
# paramétrée (GET), exactement la forme que `construire` sait dériver honnêtement.
_SCHEMA = {
    "paths": {
        "/api/comptes": {
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["nom"],
                                "properties": {"nom": {"type": "string"}},
                            }
                        }
                    }
                },
                "responses": {"201": {}, "422": {}},
            }
        },
        "/api/comptes/{id}": {
            "get": {"responses": {"200": {}, "404": {}}},
        },
    },
    "components": {"schemas": {}},
}


def _finding(identifiant: str, risque: int = 10) -> dict:
    return {
        "id": identifiant,
        "classe": "element-non-exerce",
        "localisation": "openapi",
        "message": "inventorie, jamais exerce",
        "risque": risque,
    }


# --- VERT : un cas dérivable produit un fichier qui COMPILE --------------------------------
def test_cas_derivable_compile_et_contient_un_test() -> None:
    rapport = {
        "findings": [
            _finding("code:POST /api/comptes=201"),
            _finding("code:GET /api/comptes/{}=404"),
        ]
    }
    contenu, refuses = construire(rapport, _SCHEMA)
    assert contenu, "un cas derivable doit produire du contenu"
    assert "def test_genere_" in contenu
    # Ne lève rien : `construire` a déjà appliqué `verifier_syntaxe` en interne — cet appel
    # direct est ce que l'oracle « compile » prouve ici, pas une simple confiance amont.
    verifier_syntaxe(contenu)


# --- ROUGE (refus motivé, jamais un faux cas) : code non dérivable exclu, pas inventé -------
def test_code_non_derivable_est_refuse_jamais_emis_comme_cas_casse() -> None:
    rapport = {
        "findings": [
            _finding("code:POST /api/comptes=201"),
            _finding("code:POST /api/comptes=409"),  # conflit métier : non dérivable du schéma
        ]
    }
    contenu, refuses = construire(rapport, _SCHEMA)
    assert "409" not in contenu
    motifs = {r["id"]: r["motif"] for r in refuses}
    assert "code:POST /api/comptes=409" in motifs
    assert motifs["code:POST /api/comptes=409"]  # motif non vide


# --- Oracle « compile », isolé : preuve directe, indépendante de `construire` ---------------
def test_verifier_syntaxe_ne_leve_rien_sur_du_python_valide() -> None:
    verifier_syntaxe("def test_genere_x(client) -> None:\n    assert client is not None\n")


def test_verifier_syntaxe_leve_sur_du_python_invalide() -> None:
    """RED : un fichier syntaxiquement cassé est un défaut du générateur — jamais silencieux."""
    casse = "def test_genere_x(client) -> None:\n    assert (\n"  # parenthèse jamais refermée
    try:
        verifier_syntaxe(casse)
    except CasNonCollectable as erreur:
        assert "compile" in str(erreur)
    else:
        raise AssertionError("un fichier non-compilable doit lever CasNonCollectable")


def test_verifier_syntaxe_ignore_un_contenu_vide() -> None:
    """Un rapport sans cas dérivable produit un contenu vide — ce n'est pas une erreur."""
    verifier_syntaxe("")


# --- Cas limite qui a réellement failli casser la génération : chemin non-ASCII -------------
def test_chemin_non_ascii_reste_collectable_apres_normalisation_du_nom() -> None:
    """Un identifiant d'élément dérivé d'un chemin accentué doit rester un nom de fonction
    Python valide : `_nom` normalise déjà, ce test prouve que le fichier ENTIER compile encore
    une fois ce cas mêlé à un cas standard — pas seulement le nom de la fonction en isolation.
    """
    schema = {
        "paths": {
            "/api/résumé": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["titre"],
                                    "properties": {"titre": {"type": "string"}},
                                }
                            }
                        }
                    },
                    "responses": {"201": {}},
                }
            }
        },
        "components": {"schemas": {}},
    }
    rapport = {"findings": [_finding("code:POST /api/résumé=201")]}
    contenu, _ = construire(rapport, schema)
    assert contenu  # ne lève pas : la construction inclut déjà verifier_syntaxe
    assert "def test_genere_" in contenu
