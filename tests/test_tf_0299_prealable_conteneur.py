"""TF-0299 — un préalable d ENVIRONNEMENT manquant se DÉCLARE, il ne ressemble pas à une régression.

Fait mesuré le 17/08/2026, en pleine campagne : Docker Desktop arrêté. La suite backend des bancs
se termine en code 1 sur `docker.errors.DockerException` — donc AVANT le premier test, la base du
banc étant montée par conteneur. Les pans `api`, `data`, `migrations`, `fichiers` et `back` perdent
leur couverture, et la recette affiche 10 défauts du corpus en `[MANQUE]` (12/22). Rien ne DIT que
le démon est absent : le lecteur doit le déduire. Cinq minutes de diagnostic, et sans agent
vigilant un « S-01 NON TENU » de plus — faux, puisque rien n avait régressé.

Deux idiomes déjà là, appliqués ici :

  - TF-0226, la section lint : un `ruff` introuvable est DÉCLARÉ comme tel, jamais confondu avec un
    dépôt propre ;
  - TF-0136, le port occupé : la cause qui empêche la suite de DÉMARRER est reconnue AVANT la
    branche « suite rouge », parce que les deux n appellent pas le même travail.

Et le tranchage du verdict, qui suit TF-0294 à la lettre : un verdict rendu sur une mesure
impossible n est pas un verdict. S-01 est donc SUSPENDU (code 3) quand tout le reste est vert, et
reste NON TENU quand une section est réellement rouge — sans quoi une mesure manquante absoudrait
un échec réel.

Double sens sur chaque règle : le témoin qui doit DÉCLARER, et celui qui ne doit PAS l être. Le
démon n est JAMAIS arrêté pour de vrai ici — les traces sont injectées, et `_run` est monkeypatché.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_tests import execution  # noqa: E402
from recette import verifier_corpus as vc  # noqa: E402

# La trace RÉELLE relevée sur ce poste le 17/08, Docker Desktop arrêté (Windows).
TRACE_DOCKER_ABSENT = (
    "ImportError while loading conftest 'C:\\banc\\backend\\conftest.py'.\n"
    "E   docker.errors.DockerException: Error while fetching server API version: "
    "(2, 'CreateFile', 'Le fichier specifie est introuvable.')\n"
)
# La forme Linux/CI du même fait — le démon n écoute pas sur sa socket.
TRACE_DOCKER_ABSENT_POSIX = (
    "E   docker.errors.DockerException: Error while fetching server API version: "
    "('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))\n"
)
# TÉMOIN : une suite VRAIMENT rouge, qui parle de docker sans que le démon soit en cause.
TRACE_SUITE_ROUGE = (
    "FAILED tests/test_deploiement.py::test_docker_compose_declare_la_base\n"
    "E   AssertionError: assert 'postgres' in services\n"
    "1 failed, 41 passed in 3.12s\n"
)


# --- Le lecteur de trace, dans les deux sens ----------------------------------------------------
@pytest.mark.parametrize("trace", [TRACE_DOCKER_ABSENT, TRACE_DOCKER_ABSENT_POSIX])
def test_le_demon_injoignable_est_reconnu_et_la_preuve_est_RENDUE(trace: str) -> None:
    """Rendre la LIGNE, pas un booléen : « le conteneur manque » sans sa trace serait un
    diagnostic à croire sur parole."""
    preuve = execution.prealable_conteneur(trace)

    assert preuve is not None
    assert "DockerException" in preuve


def test_une_suite_reellement_rouge_qui_parle_de_docker_n_est_PAS_reclassee() -> None:
    """Le sens qui absoudrait : reclasser une suite rouge en préalable manquant ferait passer un
    vrai défaut pour un poste mal équipé. Le mot « docker » ne suffit donc pas."""
    assert execution.prealable_conteneur(TRACE_SUITE_ROUGE) is None
    assert execution.prealable_conteneur("") is None


# --- Ce que l exécution DÉCLARE (le motif publié au rapport) ------------------------------------
def _mesurer_avec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trace: str) -> dict | None:
    """`mesurer` joué sur un projet factice dont la suite rend `trace` en code 1.

    Le démon n est pas touché : c est `_run` qui est remplacé — l arrêter pour de vrai casserait
    la recette de la campagne en cours et rendrait le test injouable en intégration.
    """
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")

    def _faux_run(commande, **_kwargs):
        if "import coverage" in commande:
            return subprocess.CompletedProcess(args=commande, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args=commande, returncode=1, stdout=trace, stderr=""
        )

    monkeypatch.setattr(execution, "_run", _faux_run)
    execution.mesurer.cache_clear()
    return execution.mesurer(str(tmp_path))


def test_le_motif_publie_NOMME_le_prealable_et_ecarte_la_suite_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AVANT le correctif, ce cas publiait « la suite backend s est terminée en échec » : un
    diagnostic faux — la suite n a jamais démarré — qui envoie chercher une régression."""
    assert _mesurer_avec(tmp_path, monkeypatch, TRACE_DOCKER_ABSENT) is None

    motif = execution.motif_indisponibilite(tmp_path, "backend", "")
    assert execution.PREALABLE_ABSENT in motif
    assert "conteneurs" in motif and "docker ps" in motif
    assert "s est terminée en échec" not in motif
    assert "DockerException" in motif  # la preuve voyage avec le motif


def test_une_suite_rouge_garde_son_motif_de_suite_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second sens, au niveau du motif : le préalable ne doit pas devenir l explication de tout."""
    assert _mesurer_avec(tmp_path, monkeypatch, TRACE_SUITE_ROUGE) is None

    motif = execution.motif_indisponibilite(tmp_path, "backend", "")
    assert execution.PREALABLE_ABSENT not in motif
    assert "échec" in motif


# --- Le pan `back` : il accusait la suite d un projet sain --------------------------------------
def _pan_back_sur_suite_non_verte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trace: str
) -> str:
    """Le motif publié par le pan `back` quand la suite ne part pas verte, la cause étant `trace`.

    `_suite_verte_ou_injouable` est remplacé plutôt que joué : l interpréteur du projet factice
    est un fichier vide, et ce qu on mesure ici est le MOTIF, pas la mécanique de mutation.
    """
    from forge_tests.adaptateurs import mutation

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "calcul.py").write_text(
        "def total(a, b):\n    if a > 0:\n        return a + b\n    return b\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calcul.py").write_text(
        "from app.calcul import total\n\n\ndef test_total():\n    assert total(1, 2) == 3\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")

    _mesurer_avec(tmp_path, monkeypatch, trace)  # c est elle qui DÉCLARE le motif
    # D-34 (01/09/2026) — la campagne de mutation est A LA DEMANDE depuis la décision humaine du
    # jour. Ce test porte sur ce que le pan dit QUAND IL SE JOUE : sans cette demande explicite,
    # il rendrait le SKIP de la porte et ce banc mesurerait la porte au lieu du motif. La
    # précondition est donc DÉCLARÉE ici plutôt que le test affaibli.
    monkeypatch.setenv("FORGE_TESTS_MUTATION", "1")
    monkeypatch.setattr(mutation, "_suite_verte_ou_injouable", lambda *_a: False)
    sortie = mutation.analyser(tmp_path)

    assert sortie.verdict == "SKIP", sortie.verdict
    return sortie.non_juge[-1]


def test_le_pan_back_reprend_le_prealable_au_lieu_d_accuser_la_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mutation` déclarait « suite rouge avant mutation » : la suite n était pas rouge, elle
    n avait pas pu démarrer. Sans cela, les trois défauts `back` du corpus (H-08, A-2, A-3)
    sortaient en [MANQUE] sans que rien ne dise pourquoi."""
    motif = _pan_back_sur_suite_non_verte(tmp_path, monkeypatch, TRACE_DOCKER_ABSENT)

    assert execution.PREALABLE_ABSENT in motif
    assert "suite rouge avant mutation" not in motif


def test_le_pan_back_accuse_toujours_une_suite_VRAIMENT_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second sens : une suite rouge avant mutation reste un score non calculable, dit comme tel."""
    motif = _pan_back_sur_suite_non_verte(tmp_path, monkeypatch, TRACE_SUITE_ROUGE)

    assert "suite rouge avant mutation" in motif
    assert execution.PREALABLE_ABSENT not in motif


# --- La section `corpus` de la recette : DÉCLARER au lieu de ressembler à une régression --------
def _rapport(motifs: dict[str, str], findings: list[dict] | None = None) -> dict:
    """Rapport minimal tel que la section `corpus` le lit."""
    return {
        "findings": findings or [],
        "motifs_non_couverture": motifs,
        "non_testables": [],
        "modules": [{"module": "app/x.py", "exerce": True}],
        "seuils": {"couverture_surface_api": {"valeur": 1.0}},
        "pans_non_couverts": [],
        "verdict": "PARTIEL",
    }


_MOTIF_CONTENEUR = (
    f"api : 12 elements INVENTORIES mais couverture non mesurable — {execution.PREALABLE_ABSENT} "
    "— demon de conteneurs INJOIGNABLE : la suite backend du projet monte sa base par conteneur"
)


def test_la_section_corpus_DECLARE_les_defauts_non_mesurables_et_ne_les_compte_pas_en_echec(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le cœur de l item : les défauts des pans sans mesure sortent NON MESURABLES, NOMMÉS un par
    un, et ne comptent pas comme échecs — un `[MANQUE]` serait une régression annoncée à tort."""
    prealables = {"rouge": {"api": _MOTIF_CONTENEUR}}
    attendus = [code for code, pan, *_reste in vc.CORPUS if pan == "api"]
    assert attendus, "le corpus doit porter au moins un défaut du pan api"

    echecs = vc.verifier_corpus_des_bancs(
        _rapport({"api": _MOTIF_CONTENEUR}), _rapport({"api": _MOTIF_CONTENEUR}), [], {},
        prealables,
    )
    sortie = capsys.readouterr().out

    assert "PRÉALABLE D ENVIRONNEMENT ABSENT" in sortie
    assert "NON MESURABLE" in sortie
    for code in attendus:
        assert f"[NON MESURABLE] {code}" in sortie, sortie
    assert "demon de conteneurs INJOIGNABLE" in sortie
    # Les défauts des AUTRES pans restent des manques : le préalable n absout que ce qu il touche.
    assert "[MANQUE ] H-10" in sortie
    # Le banc vert dont des pans n ont pas été mesurés voit son « 0 bloquant » déclaré PARTIEL.
    assert "PARTIEL" in sortie
    # Les non mesurables ne sont pas des échecs, les autres manques oui.
    assert echecs == len(vc.CORPUS) - len(attendus)


def test_sans_prealable_declare_les_memes_defauts_restent_des_MANQUES(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Second sens, et c est le garde-fou essentiel : sans préalable déclaré, un défaut non détecté
    reste un MANQUE. Sinon la nouveauté deviendrait une amnistie générale."""
    attendus = [code for code, pan, *_reste in vc.CORPUS if pan == "api"]

    echecs = vc.verifier_corpus_des_bancs(_rapport({}), _rapport({}), [], {}, {})
    sortie = capsys.readouterr().out

    assert "NON MESURABLE" not in sortie
    for code in attendus:
        assert f"[MANQUE ] {code}" in sortie
    assert echecs == len(vc.CORPUS)


# --- Le relevé des préalables, dérivé du rapport et non écrit en dur ---------------------------
def test_les_pans_sans_mesure_sont_DERIVES_du_rapport() -> None:
    """Une liste de pans « dépendants du conteneur » écrite en dur mentirait au premier pan
    ajouté : elle est donc lue dans les motifs que les pans ont publiés."""
    releve = vc.prealables_absents(
        {
            "rouge": _rapport({"api": _MOTIF_CONTENEUR, "visuel": "navigateur absent du poste"}),
            "vert": _rapport({"api": _MOTIF_CONTENEUR}),
            "absent": None,
        }
    )

    assert releve == {"rouge": {"api": _MOTIF_CONTENEUR}, "vert": {"api": _MOTIF_CONTENEUR}}


def test_un_rapport_sans_prealable_ne_declare_RIEN() -> None:
    """Le témoin du relevé : un motif de non-couverture ordinaire n est pas un préalable absent."""
    assert vc.prealables_absents({"rouge": _rapport({"visuel": "aucun golden de reference"})}) == {}


# --- Le verdict S-01, quatre états et l ordre entre eux ----------------------------------------
def test_un_prealable_absent_SUSPEND_S01_et_sort_3() -> None:
    """Le faux verdict que l item dénonce : « S-01 NON TENU » sur dix défauts NON MESURÉS. Ni TENU
    ni NON TENU, comme l arbre instable de TF-0294 — et un code de sortie qui se distingue."""
    lignes, code = verdict = vc.verdict_s01(
        True, False, {"rouge": {"api": _MOTIF_CONTENEUR}}
    )

    assert code == 3, verdict
    texte = "\n".join(lignes)
    assert "S-01 NON PRONONCÉ" in texte
    assert "S-01 TENU" not in texte and "S-01 NON TENU" not in texte
    assert "api" in texte  # les pans sans mesure sont NOMMÉS


def test_sans_prealable_le_verdict_est_PRONONCE_comme_avant() -> None:
    """Second sens : le garde-fou ne doit rien suspendre quand la mesure a eu lieu."""
    lignes, code = vc.verdict_s01(True, False, {})

    assert code == 0
    assert "  S-01 TENU" in lignes


def test_une_section_reellement_rouge_garde_son_NON_TENU_malgre_le_prealable() -> None:
    """L autre sens du tranchage : quelque chose EST rouge indépendamment du conteneur. Suspendre
    ici absoudrait un échec réel — le préalable est dit, le verdict est rendu."""
    lignes, code = vc.verdict_s01(False, False, {"rouge": {"api": _MOTIF_CONTENEUR}})

    texte = "\n".join(lignes)
    assert code == 1
    assert "S-01 NON TENU" in texte
    assert "PRÉALABLE D ENVIRONNEMENT ABSENT" in texte


def test_une_recette_PARTIELLE_reste_non_prononcee_sans_devenir_un_refus() -> None:
    """La priorité entre les états : le sélecteur ne prononce déjà pas S-01, et son code de sortie
    (0/1) ne doit pas devenir 3 — l appelant distinguerait un refus là où il n y a qu une
    sélection."""
    assert vc.verdict_s01(True, True, {"rouge": {"api": _MOTIF_CONTENEUR}})[1] == 0
    assert vc.verdict_s01(False, True, {"rouge": {"api": _MOTIF_CONTENEUR}})[1] == 1


def test_la_recette_ENTIERE_sort_3_quand_le_prealable_manque(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le bout en bout, joué sur la section la moins coûteuse (`sql`, sur pièces) érigée en
    recette ENTIÈRE — seule une recette entière peut prononcer, donc seule elle peut refuser."""
    monkeypatch.setattr(vc, "SECTIONS", {"sql": vc.SECTIONS["sql"]})
    monkeypatch.setattr(vc, "verifier_lecture_sql", lambda: 0)
    monkeypatch.setattr(vc, "empreinte_arbre", lambda *_a, **_k: {"module.py": "identique"})
    monkeypatch.setattr(
        vc, "prealables_absents", lambda _rapports: {"rouge": {"api": _MOTIF_CONTENEUR}}
    )
    # `prealables_absents` n est consulté que si des bancs sont audités : la section `sql` n en
    # audite aucun, on lui en déclare un le temps du test.
    monkeypatch.setitem(vc.SECTIONS["sql"], "bancs", ("rouge",))
    monkeypatch.setattr(vc, "_empreintes", lambda _banc: {})
    monkeypatch.setattr(vc, "analyser_servi", lambda _banc: _rapport({"api": _MOTIF_CONTENEUR}))
    monkeypatch.setattr(vc, "alterations", lambda _avant: [])

    code = vc.main([])
    sortie = capsys.readouterr().out

    assert code == 3, sortie
    assert "S-01 NON PRONONCÉ" in sortie
    assert "S-01 TENU" not in sortie and "S-01 NON TENU" not in sortie
    assert "RECETTE PARTIELLE" not in sortie
