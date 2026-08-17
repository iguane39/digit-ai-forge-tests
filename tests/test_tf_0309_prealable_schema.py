"""TF-0309 — le rejeu des migrations sur base neuve DÉCLARE pourquoi il n a rien mesuré.

Reste déclaré de TF-0299 : `execution.schema_obtenu` rendait None sans motif. Les deux pans qui
le consultent (`data`, `migrations`) publiaient alors « schema reel non introspectable » — un
constat vrai qui ne dit RIEN de la cause. Or cette sonde monte sa base par conteneur
(`testcontainers`) : sur un projet dont la suite backend n en utilise pas (SQLite en test), le
démon absent frappe ICI et nulle part ailleurs. C était le dernier chemin conteneur encore
capable de se taire — celui que le motif du domaine `backend` ne couvrait pas.

Même contrat que TF-0299, donc même double sens sur chaque règle :

  - le démon injoignable porte le marqueur `PREALABLE_ABSENT` et la PREUVE lue dans la trace ;
  - un rejeu qui échoue pour SA propre raison (migration invalide) garde un motif qui l accuse,
    lui — le préalable ne devient pas l explication de tout.

Le démon n est JAMAIS arrêté pour de vrai : `_run` est monkeypatché, comme dans TF-0299.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_tests import execution  # noqa: E402

# La trace RÉELLE que la sonde laisse quand `PostgresContainer(...)` ne trouve pas le démon :
# l exception remonte non attrapée, donc en stderr, et aucun fichier de schéma n est écrit.
TRACE_DEMON_ABSENT = (
    'Traceback (most recent call last):\n'
    '  File "verifier_schema.py", line 62, in main\n'
    '    with PostgresContainer("postgres:16-alpine", driver="psycopg") as conteneur:\n'
    "docker.errors.DockerException: Error while fetching server API version: "
    "(2, 'CreateFile', 'Le fichier specifie est introuvable.')\n"
)
# TÉMOIN : le rejeu ATTEINT sa base et c est une migration qui casse. Rien à absoudre ici.
TRACE_MIGRATION_INVALIDE = (
    'Traceback (most recent call last):\n'
    '  File "verifier_schema.py", line 68, in main\n'
    "sqlalchemy.exc.ProgrammingError: (psycopg.errors.UndefinedTable) "
    'relation "utilisateur" does not exist\n'
)


def _rejeu_avec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trace: str, *, code: int = 1
) -> dict | None:
    """`schema_obtenu` joué sur un projet factice dont la sonde rend `trace` en `code`."""
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_bytes(b"")

    def _faux_run(commande, **_kwargs):
        return subprocess.CompletedProcess(
            args=commande, returncode=code, stdout="", stderr=trace
        )

    monkeypatch.setattr(execution, "_run", _faux_run)
    execution.schema_obtenu.cache_clear()
    return execution.schema_obtenu(str(tmp_path))


def test_le_demon_absent_sur_CE_chemin_porte_le_marqueur_et_sa_preuve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cœur de l item : AVANT, ce cas rendait None en silence — deux pans perdaient leur
    contrôle d effet réel sans que rien ne dise que le poste n était pas équipé."""
    assert _rejeu_avec(tmp_path, monkeypatch, TRACE_DEMON_ABSENT) is None

    motif = execution.motif_indisponibilite(tmp_path, "schema", "")
    assert execution.PREALABLE_ABSENT in motif
    assert "conteneurs" in motif and "docker ps" in motif
    assert "DockerException" in motif  # la preuve voyage avec le motif


def test_un_rejeu_qui_echoue_pour_SA_raison_n_est_PAS_reclasse_en_prealable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le sens qui absoudrait : une migration invalide déguisée en poste mal équipé ferait passer
    un vrai défaut pour un préalable manquant, et la recette SUSPENDRAIT son verdict à tort."""
    assert _rejeu_avec(tmp_path, monkeypatch, TRACE_MIGRATION_INVALIDE) is None

    motif = execution.motif_indisponibilite(tmp_path, "schema", "")
    assert execution.PREALABLE_ABSENT not in motif
    assert "echoue" in motif and "UndefinedTable" in motif


def test_le_motif_du_rejeu_ne_se_publie_PAS_sous_le_domaine_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le domaine est PROPRE à ce chemin : écraser le motif de la suite backend reclasserait une
    suite vraiment rouge en poste mal équipé (défaut symétrique de TF-0299), et un délai dépassé
    sur le rejeu se publiait sous le motif que lisent `api` et `batch`."""
    _rejeu_avec(tmp_path, monkeypatch, TRACE_DEMON_ABSENT)

    assert execution.motif_indisponibilite(tmp_path, "backend", "intact") == "intact"


def _non_juge_des_deux_pans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trace: str
) -> dict[str, str]:
    """Le `non_juge` que `data` et `migrations` publient quand le rejeu n a rien rendu.

    Les inventaires et la couverture sont injectés : ce qu on mesure ici est la REPRISE du motif,
    pas la mécanique de chaque pan (elle a ses propres tests).
    """
    from forge_tests.adaptateurs import data, migrations
    from forge_tests.noyau import Element

    _rejeu_avec(tmp_path, monkeypatch, trace)  # c est le rejeu qui DÉCLARE
    publies: dict[str, str] = {}
    for module in (data, migrations):
        monkeypatch.setattr(module, "schema_obtenu", lambda _c: None)
        monkeypatch.setattr(module, "exerces", lambda _c: set())
        monkeypatch.setattr(
            module,
            "inventaire",
            lambda _c, pan=module.PAN: [
                Element(id="table:client", pan=pan, libelle="table client", source="x.sql")
            ],
        )
        monkeypatch.setattr(module, "_fichiers_modeles", lambda _c: [], raising=False)
        monkeypatch.setattr(module, "_sql", lambda _c: [], raising=False)
        monkeypatch.setattr(module, "_fichiers", lambda _c: [], raising=False)
        monkeypatch.setattr(module, "_downgrades_vides", lambda _c: [], raising=False)
        publies[module.PAN] = " | ".join(module.analyser(tmp_path).non_juge)
    return publies


def test_les_deux_pans_consommateurs_REPRENNENT_la_cause_declaree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un motif déclaré que personne ne lit est une affordance non câblée (loi 1) : `data` et
    `migrations` le publient à leur `non_juge`, faute de quoi le rapport reste muet."""
    publies = _non_juge_des_deux_pans(tmp_path, monkeypatch, TRACE_DEMON_ABSENT)

    for pan, texte in publies.items():
        assert "schema reel non introspectable" in texte, pan  # le constat historique demeure
        assert execution.PREALABLE_ABSENT in texte, pan
        assert "docker ps" in texte, pan


def test_la_cause_publiee_ne_FUIT_pas_d_un_banc_a_l_autre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Constaté en écrivant le test précédent : `data` passait sa constante `NON_JUGE` à
    `evaluer_surface`, qui garde la liste REÇUE — l `append` mutait donc le module, et la cause
    du premier banc réapparaissait sur le second. Plus le motif est précis, plus la fuite ment."""
    from forge_tests.adaptateurs import data, migrations

    avant = {module.NOM: list(module.NON_JUGE) for module in (data, migrations)}
    _non_juge_des_deux_pans(tmp_path, monkeypatch, TRACE_DEMON_ABSENT)

    for module in (data, migrations):
        assert list(module.NON_JUGE) == avant[module.NOM], module.NOM


def test_la_cause_reprise_reste_celle_du_rejeu_quand_ce_n_est_PAS_un_prealable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second sens de la reprise : les pans ne doivent pas annoncer un poste mal équipé quand
    c est la migration qui est invalide."""
    publies = _non_juge_des_deux_pans(tmp_path, monkeypatch, TRACE_MIGRATION_INVALIDE)

    for pan, texte in publies.items():
        assert execution.PREALABLE_ABSENT not in texte, pan
        assert "UndefinedTable" in texte, pan
