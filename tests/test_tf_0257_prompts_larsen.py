"""TF-0257 — le pan `prompts` s auditait LUI-MEME, en Larsen, sans jamais converger.

Fait mesure (lot du 15/08/2026) : audit d un produit STRICTEMENT SANS LLM — aucun prompt,
aucun appel de modele, aucune dependance d IA. Le pan `prompts` a pourtant inventorie QUATRE
alias fantomes et exige CINQ contestations. Deux causes distinctes, empilees :

  1. l inventaire fouillait `forge\\`, le dossier de convention du PILOT depose dans le projet
     (ledger, contestations, artefacts d etape). L alias de l ORCHESTRATEUR, cite dans son
     propre ledger, etait compte comme un modele du PRODUIT ;
  2. le rapport d audit persiste — que `ETAPES-RUN` EXIGE, en
     `forge\\etapes\\tests\\rapport-forge-tests.json` — etait relu au run suivant. Or ce
     rapport contient les MESSAGES du pan, qui citent nommement `claude-opus-4-1-20250805` et
     `gemini-flash-latest` pour expliquer ce qu est un alias mouvant. Chaque run fabriquait
     donc la matiere que le suivant contestait : l audit ne convergeait JAMAIS.

Les deux etages sont testes SEPAREMENT, et chacun porte son temoin : ce qui est exclu doit
l etre pour la bonne raison, et ce qui ressemble a un artefact d auditeur sans en etre un doit
rester inventorie. Sans ce second sens, l exclusion serait un silence de plus.
"""

from __future__ import annotations

import json
from pathlib import Path

from forge_tests.adaptateurs import prompts
from forge_tests.livrables import nommage

# Ce que le ledger du pilot ecrit chez l audite : l alias de l ORCHESTRATEUR, pas du produit.
_LEDGER = json.dumps(
    {
        "evenement": "run_open",
        "modele": "claude-sonnet-4-5",
        "versions_forges": {"forge-tests": "13000f0"},
    },
    ensure_ascii=False,
)

# Le message que le pan lui-meme ecrit au rapport — c est LUI qui cite les deux alias.
_MESSAGE_DU_PAN = (
    "modèle « claude-sonnet-4-5 » désigné par un ALIAS mouvant, jamais par une version "
    "épinglée (forme `nom-AAAAMMJJ`) — un alias change le système sous test sans qu'aucun "
    "commit ne bouge : `claude-opus-4-1-20250805` a été retiré le 2026-08-05, et Google "
    "remappe ses alias `-latest` à dates fixes (`gemini-flash-latest` -> `gemini-3.5-flash` "
    "le 2026-05-19)"
)


def _rapport_forge_tests() -> dict:
    """Un rapport forge-tests reduit a sa SIGNATURE, portant les alias que le pan a ecrits."""
    return {
        "adaptateurs": [{"nom": "prompts-statique", "pan": "prompts", "verdict": "FAIL"}],
        "couverture_par_pan": {"prompts": {"inventorie": 4, "exerce": 0}},
        "pans_non_couverts": [],
        "findings": [{"id": "modele:claude-sonnet-4-5", "message": _MESSAGE_DU_PAN}],
        "non_juge": [_MESSAGE_DU_PAN],
        "verdict": "FAIL",
    }


def _produit_sans_llm(racine: Path) -> Path:
    """Un produit strictement sans LLM : du code, des gabarits Jinja, et rien d autre."""
    (racine / "app").mkdir(parents=True)
    (racine / "app" / "main.py").write_text(
        "def creer_app():\n    return object()\n", encoding="utf-8"
    )
    return racine


def _modeles(cible: Path) -> set[str]:
    return {e.id for e in prompts.inventaire(cible) if e.id.startswith("modele:")}


def _prompts(cible: Path) -> set[str]:
    return {e.id for e in prompts.inventaire(cible) if e.id.startswith("prompt:")}


class TestEtage1DossierForgeDuPilot:
    """`forge\\` est le dossier de l ORCHESTRATEUR — jamais la surface du produit."""

    def test_le_ledger_du_pilot_ne_fournit_aucun_modele_au_produit(self, tmp_path):
        cible = _produit_sans_llm(tmp_path)
        (cible / "forge").mkdir()
        (cible / "forge" / "ledger.jsonl").write_text(_LEDGER + "\n", encoding="utf-8")

        # ROUGE : `modele:claude-sonnet-4-5` etait inventorie — un modele du PILOT impute au
        # produit, puis conteste a la main run apres run.
        assert _modeles(cible) == set()

    def test_les_gabarits_du_pilot_ne_sont_pas_des_prompts_du_produit(self, tmp_path):
        cible = _produit_sans_llm(tmp_path)
        gabarits = cible / "forge" / "gabarits"
        gabarits.mkdir(parents=True)
        (gabarits / "AGENT-CAMPAGNE.md").write_text(
            "# Gabarit d agent de campagne\n\nTu ecris uniquement dans le depot cible.\n",
            encoding="utf-8",
        )

        # ROUGE : `prompt:forge/gabarits/AGENT-CAMPAGNE.md` — le dossier `gabarits` est une forme
        # adressable reconnue, et il appartenait ici au PILOT.
        assert _prompts(cible) == set()

    def test_un_produit_sans_llm_reste_sans_le_moindre_constat(self, tmp_path):
        cible = _produit_sans_llm(tmp_path)
        (cible / "forge" / "etapes" / "tests").mkdir(parents=True)
        (cible / "forge" / "ledger.jsonl").write_text(_LEDGER + "\n", encoding="utf-8")

        sortie = prompts.analyser(cible)

        # ROUGE : verdict FAIL et un finding `modele-non-epingle` par alias fantome — zero
        # contestation devrait etre necessaire sur un produit qui n a aucun LLM.
        assert sortie.verdict == "SKIP"
        assert sortie.findings == []

    def test_temoin_le_meme_fichier_hors_de_forge_reste_inventorie(self, tmp_path):
        """L exclusion porte sur le DOSSIER de convention, pas sur le contenu : un vrai fichier
        du produit qui nomme un modele doit toujours etre vu."""
        cible = _produit_sans_llm(tmp_path)
        (cible / "config.json").write_text(_LEDGER + "\n", encoding="utf-8")

        assert "modele:claude-sonnet-4-5" in _modeles(cible)


class TestEtage2ArtefactsDeLAuditeur:
    """Le rapport que la forge a ecrit hier n est pas la surface du produit d aujourd hui."""

    def test_un_rapport_persiste_ne_fournit_aucun_modele(self, tmp_path):
        """Place HORS de `forge\\` : l etage 2 doit tenir SEUL, sans l etage 1."""
        cible = _produit_sans_llm(tmp_path)
        (cible / "rapport-forge-tests.json").write_text(
            json.dumps(_rapport_forge_tests(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ROUGE : trois alias inventories d un coup — `claude-sonnet-4-5`,
        # `claude-opus-4-1-20250805` et `gemini-flash-latest` — tous ecrits par le pan LUI-MEME
        # au run precedent.
        assert _modeles(cible) == set()

    def test_l_audit_converge_d_un_run_a_l_autre(self, tmp_path):
        """La propriete qui manquait : rejouer l audit sur son propre rapport ne cree rien."""
        cible = _produit_sans_llm(tmp_path)
        premier = prompts.analyser(cible)
        (cible / "rapport-forge-tests.json").write_text(
            json.dumps(_rapport_forge_tests(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        second = prompts.analyser(cible)

        assert (second.verdict, second.findings) == (premier.verdict, premier.findings)

    def test_un_livrable_scelle_par_la_forge_est_ecarte(self, tmp_path):
        """Cahier de tests recopie dans le projet : scelle, donc reconnaissable comme derive."""
        cible = _produit_sans_llm(tmp_path)
        dossier = cible / "prompts"
        dossier.mkdir()
        corps = f"# Cahier de tests techniques\n\n{_MESSAGE_DU_PAN}\n"
        (dossier / "cahier.md").write_text(
            nommage.sceller({"rapport_nom": "rapport-forge-tests.json"}, corps),
            encoding="utf-8",
        )

        assert _prompts(cible) == set()
        assert _modeles(cible) == set()

    def test_temoin_le_meme_cahier_non_scelle_reste_inventorie(self, tmp_path):
        """C est le SCEAU qui ecarte, pas le nom ni le dossier : sans lui, le document est du
        produit et doit compter."""
        cible = _produit_sans_llm(tmp_path)
        dossier = cible / "prompts"
        dossier.mkdir()
        (dossier / "cahier.md").write_text(
            f"# Cahier de tests techniques\n\n{_MESSAGE_DU_PAN}\n", encoding="utf-8"
        )

        assert "prompt:prompts/cahier.md" in _prompts(cible)

    def test_temoin_un_json_du_produit_qui_ressemble_reste_inventorie(self, tmp_path):
        """Un JSON qui porte une partie seulement de la signature n est PAS un rapport : la
        reconnaissance est exacte, elle n ecarte pas au flair."""
        cible = _produit_sans_llm(tmp_path)
        charge = _rapport_forge_tests()
        del charge["adaptateurs"]  # il ne reste plus la signature d un rapport forge-tests
        (cible / "config-modeles.json").write_text(
            json.dumps(charge, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Les trois alias que le pan cite dans son propre message reviennent : c est bien le
        # Larsen, et il ne se declenche QUE sur la signature complete.
        assert "modele:gemini-flash-latest" in _modeles(cible)

    def test_la_signature_ne_depend_pas_du_nom_du_fichier(self, tmp_path):
        """Un rapport renomme reste un rapport — l exclusion lit le CONTENU, pas la convention."""
        cible = _produit_sans_llm(tmp_path)
        (cible / "audit-du-15-aout.json").write_text(
            json.dumps(_rapport_forge_tests(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        assert _modeles(cible) == set()


class TestCoherenceDuMarqueurDeSceau:
    """Le littéral recopié dans `prompts.py` doit suivre `nommage.DEBUT_SCEAU`."""

    def test_le_marqueur_recopie_est_celui_du_scelleur(self):
        # Un import direct serait circulaire (`livrables/__init__` importe le REGISTRE des
        # adaptateurs) : la copie est assumee, sa derive est ici RENDUE IMPOSSIBLE.
        assert prompts._DEBUT_SCEAU == nommage.DEBUT_SCEAU

    def test_un_document_reellement_scelle_est_reconnu(self):
        assert prompts.est_un_artefact_d_auditeur(nommage.sceller({"x": "1"}, "corps\n"))

    def test_un_document_ordinaire_ne_l_est_pas(self):
        assert not prompts.est_un_artefact_d_auditeur("# Un document du produit\n")
