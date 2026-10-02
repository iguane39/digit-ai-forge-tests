"""TF-1229 (volet a de TF-0964) — aucun oracle statique ne signalait un fournisseur de jetons
construit SANS identifiant alors qu'une identité ASSIGNÉE est posée par l'environnement.

Constat du 14/09/2026, confirmé le 02/10/2026 : `DefaultAzureCredential()` construit sans
`client_id` ni `managed_identity_client_id` résout l'identité SYSTÈME de l'hôte (ou échoue) là
où l'infrastructure assigne une identité PRÉCISE par `AZURE_CLIENT_ID` (volet b, commit
`1d856701`, déjà corrigé côté produit). Le volet statique — voir ce défaut dans le CODE, avant
la mise en production — ne relevait d'aucune des deux forges candidates : ni
`forge_tests/adaptateurs/securite.py` (trois oracles délégués : sast, secrets, sca, aucun des
trois ne parle d'identité de client), ni `digit-ai-forge-websec/oracles` (oracle-dast,
oracle-exposition, oracle-sca).

Correction : `_findings_identite_assignee`, contrôle STATIQUE et PUR PYTHON (aucun outil tiers
à invoquer, donc indépendant du registre `FORGE_TESTS_ORACLES`), câblé dans le pan `securite`.
Jeu d'essai à double sens : un fichier qui construit le fournisseur SANS identifiant alors qu'il
référence `AZURE_CLIENT_ID` est rouge ; un fichier qui le construit AVEC l'identifiant, ou qui
n'assigne aucune identité, reste vert.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import securite


def _registre(racine: Path) -> Path:
    """Un registre d'oracles externes VIDE — aucun script sast/secrets/sca. Le contrôle de cet
    item doit juger MÊME dans cet état : il ne délègue à aucun outil tiers."""
    racine.mkdir(parents=True, exist_ok=True)
    return racine


def _produit(racine: Path, contenu: str) -> Path:
    (racine / "backend" / "app").mkdir(parents=True)
    (racine / "backend" / "app" / "identite.py").write_text(contenu, encoding="utf-8")
    return racine


_SANS_IDENTIFIANT = (
    "import os\n"
    "from azure.identity import DefaultAzureCredential\n\n"
    "IDENTITE = os.environ['AZURE_CLIENT_ID']\n\n"
    "def fournisseur_de_jetons():\n"
    "    return DefaultAzureCredential()\n"
)

_AVEC_IDENTIFIANT = (
    "import os\n"
    "from azure.identity import DefaultAzureCredential\n\n"
    "IDENTITE = os.environ['AZURE_CLIENT_ID']\n\n"
    "def fournisseur_de_jetons():\n"
    "    return DefaultAzureCredential(managed_identity_client_id=IDENTITE)\n"
)

_SANS_IDENTITE_ASSIGNEE = (
    "from azure.identity import DefaultAzureCredential\n\n"
    "def fournisseur_de_jetons():\n"
    "    return DefaultAzureCredential()\n"
)


def test_rouge_fournisseur_sans_identifiant_alors_qu_une_identite_est_assignee(
    tmp_path: Path,
) -> None:
    """Le défaut mesuré en production (volet b) : rien ne le voyait dans le code."""
    application = tmp_path / "produit" / "backend"
    _produit(tmp_path / "produit", _SANS_IDENTIFIANT)

    findings = securite._findings_identite_assignee(application)

    assert len(findings) == 1
    assert findings[0].classe == "fournisseur-jetons-sans-identifiant"
    assert findings[0].severite == "bloquant"
    assert "identite.py" in findings[0].localisation
    assert "AZURE_CLIENT_ID" in findings[0].message


def test_vert_fournisseur_construit_avec_l_identifiant(tmp_path: Path) -> None:
    """Contre-épreuve : le même contexte, mais l'identifiant EST transmis — plus rien à dire."""
    application = tmp_path / "produit" / "backend"
    _produit(tmp_path / "produit", _AVEC_IDENTIFIANT)

    assert securite._findings_identite_assignee(application) == []


def test_vert_sans_identite_assignee_le_controle_se_tait(tmp_path: Path) -> None:
    """Deuxième contre-épreuve : aucune AZURE_CLIENT_ID dans ce projet — rien à reprocher, le
    pan aveugle qui se tait est utile, pas un pan aveugle qui accuse."""
    application = tmp_path / "produit" / "backend"
    _produit(tmp_path / "produit", _SANS_IDENTITE_ASSIGNEE)

    assert securite._findings_identite_assignee(application) == []


def test_le_controle_juge_meme_sans_registre_d_oracles_externes(
    tmp_path: Path, monkeypatch
) -> None:
    """Indépendant du registre : aucun oracle-{sast,secrets,sca}.mjs n'existe, le pan reste
    FAIL et publie le finding plutôt que de se taire derrière un SKIP de registre."""
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    cible = tmp_path / "produit"
    _produit(cible, _SANS_IDENTIFIANT)
    monkeypatch.setattr(securite, "_racine_oracles", lambda: _registre(tmp_path / "oracles"))

    sortie = securite.analyser(cible)

    assert sortie.verdict == "FAIL"
    assert any(f.classe == "fournisseur-jetons-sans-identifiant" for f in sortie.findings)


def test_le_controle_ne_force_pas_un_FAIL_quand_il_n_a_rien_trouve_et_que_tout_est_absent(
    tmp_path: Path, monkeypatch
) -> None:
    """Non-régression TF-0219 : sans registre ET sans défaut d'identité, le motif de SKIP reste
    celui des oracles externes (registre introuvable) — ce contrôle ne force pas un verdict
    quand il n'a rien à dire."""
    monkeypatch.delenv("FORGE_TESTS_SOURCES", raising=False)
    cible = tmp_path / "produit"
    _produit(cible, _SANS_IDENTITE_ASSIGNEE)
    monkeypatch.setattr(securite, "_racine_oracles", lambda: None)

    sortie = securite.analyser(cible)

    assert sortie.verdict == "SKIP"
    assert "FORGE_TESTS_ORACLES" in sortie.non_juge[-1]
