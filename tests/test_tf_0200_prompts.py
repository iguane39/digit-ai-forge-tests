"""TF-0200 — pan `prompts` : inventorier les prompts, les modèles et le corpus, gratuitement.

Verdict O2 de l'étude d'opportunité du 14/08/2026 : la v0 mesure ce qui se mesure SANS appeler
un modèle. Chaque test ci-dessous décrit un défaut que forge-tests ne voyait PAS avant ce pan —
un prompt qu'aucun cas n'exerce, un modèle désigné par un alias mouvant, un corpus déclaré et
introuvable — ou une garantie qui le rend jouable dans tout audit : il ne dépense rien.

TF-0201 (volet stabilité) est PRÉPARÉ ici, jamais exécuté : `mesure_d_instabilite` est testée
sur données figées, et l'audit ne l'invoque nulle part.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from forge_tests import flaky
from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, prompts

BANC_ROUGE = Path(__file__).resolve().parent.parent / "fixtures" / "banc-rouge"
BANC_VERT = Path(__file__).resolve().parent.parent / "fixtures" / "banc-vert"

EPINGLE = "claude-sonnet-4-5-20250929"
ALIAS = "claude-3-5-sonnet-latest"


def _ecrire(racine: Path, relatif: str, contenu: str) -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _projet(tmp_path: Path, modele: str = EPINGLE, cas: bool = True) -> Path:
    """Projet minimal : un prompt adressable, son modèle, et (au choix) son cas."""
    _ecrire(
        tmp_path,
        "prompts/assistant.prompt",
        f"modele: {modele}\n\nTu réponds à une question sur l'état d'une commande.\n",
    )
    if cas:
        _ecrire(
            tmp_path,
            "evals/assistant.eval.jsonl",
            '{"cas": "c1", "prompt": "prompts/assistant.prompt", "modele": "'
            + modele
            + '", "question": "q", "attendu": "a"}\n',
        )
    return tmp_path


# --- Inventaire des prompts -------------------------------------------------------------------
def test_un_fichier_prompt_est_inventorie(tmp_path: Path) -> None:
    _ecrire(tmp_path, "assistant.prompt", "Tu réponds brièvement.\n")
    assert [e.id for e in prompts.inventaire(tmp_path)] == ["prompt:assistant.prompt"]


def test_un_skill_est_un_prompt_adressable(tmp_path: Path) -> None:
    """Un `SKILL.md` EST un prompt : le taire laisserait hors inventaire tout l'outillage agent."""
    _ecrire(tmp_path, "skills/redaction/SKILL.md", "# Rédaction\n\nTu rédiges.\n")
    assert [e.id for e in prompts.inventaire(tmp_path)] == ["prompt:skills/redaction/SKILL.md"]


def test_un_document_du_dossier_prompts_est_inventorie(tmp_path: Path) -> None:
    _ecrire(tmp_path, "prompts/accueil.md", "# Accueil\n\nTu accueilles l'utilisateur.\n")
    assert [e.id for e in prompts.inventaire(tmp_path)] == ["prompt:prompts/accueil.md"]


def test_une_constante_de_prompt_systeme_est_reperee_par_ast(tmp_path: Path) -> None:
    """« Repérable sans deviner » : le NOM de la constante le dit, la valeur est un littéral."""
    _ecrire(
        tmp_path,
        "app/agent.py",
        'SYSTEM_PROMPT = "Tu es un assistant de suivi de commandes, factuel et bref."\n'
        'AUTRE_CONSTANTE = "valeur quelconque qui n\'est pas un prompt du tout, mais longue"\n',
    )
    assert [e.id for e in prompts.inventaire(tmp_path)] == ["prompt:app/agent.py:SYSTEM_PROMPT"]


def test_les_artefacts_et_dependances_ne_sont_pas_fouilles(tmp_path: Path) -> None:
    """Un prompt archivé dans `output\\` ou embarqué dans une dépendance n'est pas du produit."""
    _ecrire(tmp_path, "output/prompts/vieux.prompt", "Ancien prompt archivé.\n")
    _ecrire(tmp_path, "node_modules/paquet/prompts/tiers.prompt", "Prompt d'une dépendance.\n")
    _ecrire(tmp_path, "backend/.venv/lib/prompts/tiers.prompt", "Prompt d'une dépendance.\n")
    assert prompts.inventaire(tmp_path) == []


# --- Inventaire des modèles -------------------------------------------------------------------
def test_un_modele_nomme_dans_le_code_est_inventorie(tmp_path: Path) -> None:
    _ecrire(tmp_path, "app/client.py", f'MODELE = "{EPINGLE}"\n')
    assert [e.id for e in prompts.inventaire(tmp_path)] == [f"modele:{EPINGLE}"]


def test_une_mention_en_prose_n_est_pas_un_usage(tmp_path: Path) -> None:
    """Anti-faux-positif : un document qui PARLE d'un modèle ne le fait pas tourner."""
    _ecrire(
        tmp_path,
        "docs/note.md",
        "Nous avons comparé claude-3-5-sonnet-latest et gpt-4o avant de trancher.\n",
    )
    assert prompts.inventaire(tmp_path) == []


def test_un_modele_designe_par_un_alias_est_denonce(tmp_path: Path) -> None:
    """Le défaut le plus coûteux : le système sous test change sans qu'un commit ne bouge."""
    sortie = prompts.analyser(_projet(tmp_path, modele=ALIAS))
    alias = [f for f in sortie.findings if f.classe == "modele-non-epingle"]
    assert [f.id for f in alias] == [f"modele:{ALIAS}"]
    assert sortie.verdict == "FAIL"


def test_le_constat_d_alias_porte_son_motif(tmp_path: Path) -> None:
    """Un constat sans motif est une opinion : le message CITE les faits du 2026-08."""
    sortie = prompts.analyser(_projet(tmp_path, modele=ALIAS))
    message = next(f.message for f in sortie.findings if f.classe == "modele-non-epingle")
    assert "sans qu'aucun commit ne bouge" in message
    assert "claude-opus-4-1-20250805" in message and "2026-08-05" in message
    assert "latest" in message


def test_un_modele_epingle_ne_produit_aucun_constat(tmp_path: Path) -> None:
    """Sens vert : le contrôle DISCRIMINE, il ne dénonce pas tout nom de modèle."""
    sortie = prompts.analyser(_projet(tmp_path, modele=EPINGLE))
    assert [f for f in sortie.findings if f.classe == "modele-non-epingle"] == []
    assert sortie.verdict == "PASS"


def test_les_formes_d_epinglage_reconnues() -> None:
    assert prompts.est_epingle("claude-opus-4-1-20250805")
    assert prompts.est_epingle("gpt-5-2026-01-15")
    assert prompts.est_epingle("mistral-large-2411")
    assert not prompts.est_epingle("claude-3-5-sonnet-latest")
    assert not prompts.est_epingle("gpt-4o")
    assert not prompts.est_epingle("gemini-flash-latest")


# --- Corpus de questions / réponses attendues --------------------------------------------------
def test_un_prompt_sans_aucun_cas_est_nomme_non_exerce(tmp_path: Path) -> None:
    sortie = prompts.analyser(_projet(tmp_path, cas=False))
    assert "prompt:prompts/assistant.prompt" in sortie.surface["elements_non_exerces"]
    assert any(
        f.id == "prompt:prompts/assistant.prompt" and f.classe == "element-non-exerce"
        for f in sortie.findings
    )


def test_un_prompt_cite_par_un_cas_est_exerce(tmp_path: Path) -> None:
    sortie = prompts.analyser(_projet(tmp_path))
    assert sortie.surface["elements_non_exerces"] == []
    assert sortie.surface["ratio"] == 1.0


def test_un_cas_peut_designer_le_prompt_par_son_nom_de_fichier(tmp_path: Path) -> None:
    """Un corpus qui cite `assistant.prompt` désigne bien `prompts/assistant.prompt`."""
    racine = _projet(tmp_path, cas=False)
    _ecrire(
        racine,
        "evals/cas.json",
        '[{"cas": "c1", "prompt": "assistant.prompt", "modele": "' + EPINGLE + '"}]',
    )
    assert "prompt:prompts/assistant.prompt" in prompts.exerces(racine)


def test_un_corpus_declare_introuvable_est_non_testable(tmp_path: Path) -> None:
    """RT-6 : personne ne POUVAIT l'exercer ici — c'est un manque de configuration, pas un trou."""
    _ecrire(
        tmp_path,
        "prompts/resume.prompt",
        "corpus: evals/absent.eval.jsonl\n\nTu résumes en trois lignes.\n",
    )
    sortie = prompts.analyser(tmp_path)
    assert [n.element for n in sortie.non_testables] == ["prompt:prompts/resume.prompt"]
    assert sortie.non_testables[0].champs_requis == list(prompts.CHAMPS_REQUIS)
    assert "introuvable" in sortie.non_testables[0].motif


def test_un_prompt_non_testable_n_est_pas_accuse_de_non_couverture(tmp_path: Path) -> None:
    """Confondre les deux, c'est reprocher au projet une carence de l'environnement d'audit."""
    racine = _projet(tmp_path)
    _ecrire(
        racine,
        "prompts/resume.prompt",
        "corpus: evals/absent.eval.jsonl\n\nTu résumes en trois lignes.\n",
    )
    sortie = prompts.analyser(racine)
    assert "prompt:prompts/resume.prompt" not in sortie.surface["elements_non_exerces"]
    assert [f for f in sortie.findings if "resume" in f.id] == []


# --- Contrat d'adaptateur et gratuité ----------------------------------------------------------
def test_le_pan_est_au_registre_avec_son_contrat() -> None:
    assert REGISTRE["prompts-statique"] is prompts
    assert prompts.PAN in PANS_ATTENDUS
    assert prompts.POUR_COUVRIR.strip() and prompts.NON_JUGE
    assert [c["code"] for c in prompts.CHAPITRES] == ["T8"]


def test_le_non_juge_declare_que_le_volet_execute_est_hors_v0() -> None:
    """La dépense est un mandat humain (règle 29) : le taire ferait croire à une mesure faite."""
    ensemble = " ".join(prompts.NON_JUGE)
    assert "regle 29" in ensemble
    assert "QUALITE d un prompt n est pas jugee" in ensemble


def test_un_projet_sans_prompt_ni_modele_sort_SKIP_nomme(tmp_path: Path) -> None:
    """Un inventaire vide ne prouve pas que tout va bien : il prouve qu'on n'a rien su énumérer."""
    sortie = prompts.analyser(tmp_path)
    assert sortie.verdict == "SKIP"
    assert any("non énumérable" in m for m in sortie.non_juge)


def test_un_alias_est_denonce_meme_sans_le_moindre_corpus(tmp_path: Path) -> None:
    """Le constat est STATIQUE : il tient là où AUCUN corpus n'existe, donc dans tout audit."""
    _ecrire(tmp_path, "app/client.py", f'MODELE = "{ALIAS}"\n')
    sortie = prompts.analyser(tmp_path)
    assert sortie.verdict == "FAIL"
    assert "modele-non-epingle" in {f.classe for f in sortie.findings}


def test_le_pan_n_ouvre_aucune_connexion(tmp_path: Path, monkeypatch) -> None:
    """La v0 tourne dans TOUT audit parce qu'elle ne dépense rien : zéro appel modèle, zéro réseau.

    Le sous-processus n'est PAS interdit ici : la cotation du risque, commune à tous les pans,
    interroge `git log` sur le fichier source. C'est la SORTIE RÉSEAU qui est la dépense.
    """

    def refuser(*_a: object, **_k: object) -> None:
        raise AssertionError("le pan prompts ne doit jamais sortir sur le réseau")

    monkeypatch.setattr(socket, "socket", refuser)
    monkeypatch.setattr(socket, "create_connection", refuser)
    sortie = prompts.analyser(_projet(tmp_path, modele=ALIAS))
    assert sortie.verdict == "FAIL"


def test_le_module_du_pan_n_importe_aucun_client_de_modele() -> None:
    """Une dépense ne s'introduit pas par accident : aucun client HTTP ni SDK n'est importable."""
    source = Path(prompts.__file__).read_text(encoding="utf-8")
    importe = {
        ligne.split()[1].split(".")[0]
        for ligne in source.splitlines()
        if ligne.startswith(("import ", "from "))
    }
    assert not importe & {
        "anthropic", "openai", "requests", "httpx", "urllib", "http", "socket", "aiohttp",
    }


# --- Les deux bancs ----------------------------------------------------------------------------
def test_le_banc_rouge_porte_les_deux_defauts_du_pan() -> None:
    sortie = prompts.analyser(BANC_ROUGE)
    classes = {f.classe for f in sortie.findings}
    assert "modele-non-epingle" in classes  # H-14
    assert any(
        f.classe == "element-non-exerce" and f.id.startswith("prompt:") for f in sortie.findings
    )  # H-15
    assert [n.element for n in sortie.non_testables] == ["prompt:prompts/resume.prompt"]


def test_le_banc_vert_ne_porte_aucun_finding() -> None:
    sortie = prompts.analyser(BANC_VERT)
    assert sortie.verdict == "PASS"
    assert sortie.findings == []


# --- TF-0201 — mesure de stabilité, PRÉPARÉE et non exécutée -----------------------------------
def _reponses(*valeurs: str, cas: str = "c1", champ: str = "verdict") -> list[dict]:
    return [{"cas": cas, "rejeu": rang, champ: valeur} for rang, valeur in enumerate(valeurs)]


def test_instabilite_des_verdicts_identiques_est_nulle() -> None:
    mesure = prompts.mesure_d_instabilite(_reponses("passant", "passant", "passant"))
    assert mesure["cas_instables"] == {}
    assert mesure["stabilite"] == 1.0
    assert mesure["repetitions"] == 3


def test_un_verdict_qui_varie_a_entree_identique_est_une_instabilite() -> None:
    mesure = prompts.mesure_d_instabilite(_reponses("passant", "non_passant", "passant"))
    assert mesure["cas_instables"] == {"c1": ["passant", "non_passant", "passant"]}
    assert mesure["stabilite"] == 0.0


def test_une_reponse_qui_varie_sans_verdict_est_une_instabilite() -> None:
    """Sans jugement fourni, la RÉPONSE elle-même est la valeur observée."""
    mesure = prompts.mesure_d_instabilite(
        _reponses("la commande C-1 est livrée", "aucune idée", champ="reponse")
    )
    assert list(mesure["cas_instables"]) == ["c1"]


def test_deux_reponses_identiques_au_blanc_pres_sont_la_meme_reponse() -> None:
    """Crier à l'instabilité sur du formatage rendrait la mesure inutilisable."""
    mesure = prompts.mesure_d_instabilite(
        _reponses("commande  C-1\n livrée", "commande C-1 livrée", champ="reponse")
    )
    assert mesure["cas_instables"] == {}


def test_un_cas_absent_d_un_rejeu_compte_comme_une_variation() -> None:
    """Une réponse manquante EST une variation : la taire serait un vert offert."""
    reponses = [
        {"cas": "c1", "rejeu": 0, "verdict": "passant"},
        {"cas": "c2", "rejeu": 0, "verdict": "passant"},
        {"cas": "c1", "rejeu": 1, "verdict": "passant"},
    ]
    mesure = prompts.mesure_d_instabilite(reponses)
    assert mesure["cas_instables"] == {"c2": ["passant", "absent"]}
    assert mesure["tous_ids"] == ["c1", "c2"]


def test_un_seul_rejeu_ne_prouve_rien_et_se_refuse() -> None:
    with pytest.raises(ValueError):
        prompts.mesure_d_instabilite(_reponses("passant"))


def test_la_mesure_reutilise_la_logique_de_flaky() -> None:
    """Une copie de la règle dériverait : c'est `flaky.variations` qui tranche, ici comme là-bas."""
    releves = [{"c1": "PASSED", "c2": "PASSED"}, {"c1": "FAILED", "c2": "PASSED"}]
    assert flaky.variations(releves) == {"c1": ["PASSED", "FAILED"]}
    mesure = prompts.mesure_d_instabilite(
        [
            {"cas": "c1", "rejeu": 0, "verdict": "PASSED"},
            {"cas": "c2", "rejeu": 0, "verdict": "PASSED"},
            {"cas": "c1", "rejeu": 1, "verdict": "FAILED"},
            {"cas": "c2", "rejeu": 1, "verdict": "PASSED"},
        ]
    )
    assert mesure["cas_instables"] == flaky.variations(releves)


# --- Branchement aux livrables et aux actions --------------------------------------------------
def test_le_chapitre_T8_est_derive_du_registre() -> None:
    from forge_tests.livrables import surface

    codes = {c["code"]: c for c in surface.chapitres(REGISTRE)}
    assert "T8" in codes and codes["T8"]["pans"] == ["prompts"]
    assert codes["T8"]["axe_connu"] is True


def test_les_elements_du_pan_sont_rattaches_a_un_sous_chapitre() -> None:
    """Un élément rangé nulle part est un élément qu'on cesse de lire."""
    from forge_tests.livrables import surface

    for identifiant in ("prompt:prompts/assistant.prompt", f"modele:{EPINGLE}"):
        _libelle, derive = surface.sous_chapitre("prompt", identifiant)
        assert derive, identifiant


def test_un_modele_non_epingle_recoit_une_suite_classee() -> None:
    """Sans règle, le constat sortirait en « défaut d'auditeur » : mesuré, mais sans destinataire."""
    from forge_tests.actions import classifier

    action = classifier(
        [{"id": f"modele:{ALIAS}", "classe": "modele-non-epingle", "pan": "prompts",
          "message": "alias mouvant"}]
    )[0]
    assert action["etape_cible"] == "development"
    assert action["categorie"] == "manuelle_dev"
    assert "épingler" in action["attendu"]
