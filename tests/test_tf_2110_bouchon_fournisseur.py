"""TF-2110 — le pan prompts exige un bouchon pour tout appel de fournisseur LLM dans un test.

Fait (étude du 03/11/2026, ligne C3) : le pan connaissait les clients `openai`, `google-genai` et
`@google/genai` (`_CLIENTS_DE_MODELE`) mais ne jugeait pas qu un TEST appelle le fournisseur réel.
Un test d un produit OpenAI ou Gemini dépense alors à chaque exécution de recette, sans qu aucun
commit ne le dise. Produit-12 porte le bon modèle : un double HTTP par `monkeypatch` qui vérifie
l ADRESSE appelée sans rien dépenser.

Trois sens, chacun avec sa fixture :
  - ROUGE  — un appel réel dans un fichier de test, aucun double : constat, fichier et ligne ;
  - VERT   — le même appel sous double (dans le fichier, ou dans une configuration voisine) ;
  - Produit-12 — l adresse CITÉE comme valeur attendue, à côté d un double : aucun constat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests import actions
from forge_tests.adaptateurs import prompts

CLASSE = "appel-fournisseur-llm-reel-dans-un-test"


def _projet(racine: Path, fichiers: dict[str, str]) -> Path:
    """Un produit qui déclare un client de modèle (donc ni NA ni sans objet) et ses fichiers."""
    projet = racine / "produit"
    projet.mkdir()
    (projet / "pyproject.toml").write_text(
        '[project]\nname = "p"\ndependencies = ["openai>=1.0", "httpx"]\n', encoding="utf-8"
    )
    for relatif, texte in fichiers.items():
        chemin = projet / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")
    return projet


def _constats(projet: Path) -> list:
    return [f for f in prompts.analyser(projet).findings if f.classe == CLASSE]


# --- ROUGE : l appel réel, sans double ------------------------------------------------------------
APPEL_REEL_PY = (
    "from openai import OpenAI\n"
    "\n"
    "\n"
    "def test_resume_un_texte():\n"
    "    client = OpenAI(api_key='cle-de-test')\n"
    "    reponse = client.chat.completions.create(model='m', messages=[])\n"
    "    assert reponse.choices\n"
)


def test_rouge_un_appel_reel_dans_un_test_python_est_denonce_avec_fichier_et_ligne(
    tmp_path: Path,
) -> None:
    projet = _projet(tmp_path, {"backend/tests/test_resume.py": APPEL_REEL_PY})
    constats = _constats(projet)
    assert len(constats) == 1
    constat = constats[0]
    assert constat.localisation.endswith("backend/tests/test_resume.py:5"), constat.localisation
    assert constat.severite == "bloquant"
    assert prompts.analyser(projet).verdict == "FAIL"


def test_rouge_le_constat_porte_son_motif(tmp_path: Path) -> None:
    """Un constat sans motif est une opinion : il dit ce que coûte l appel réel."""
    constat = _constats(_projet(tmp_path, {"tests/test_a.py": APPEL_REEL_PY}))[0]
    assert "dépense" in constat.message.lower()
    assert "double" in constat.message and "monkeypatch" in constat.message


@pytest.mark.parametrize(
    "appel",
    [
        "requests.post('https://api.openai.com/v1/chat/completions', json={})",
        "requests.post('https://monressource.openai.azure.com/openai/deployments/d', json={})",
        "requests.post('https://generativelanguage.googleapis.com/v1beta/models/m:generate')",
        "client = OpenAI(api_key='x')",
        "client = AzureOpenAI(api_key='x', azure_endpoint='y')",
        "client = genai.Client(api_key='x')",
    ],
)
def test_rouge_chacune_des_formes_d_appel_declenche_le_constat(tmp_path: Path, appel: str) -> None:
    source = f"def test_appel():\n    {appel}\n"
    assert len(_constats(_projet(tmp_path, {"tests/test_forme.py": source}))) == 1, appel


@pytest.mark.parametrize(
    "appel",
    [
        "const client = new OpenAI({ apiKey: 'x' });",
        "const client = new GoogleGenAI({ apiKey: 'x' });",
        "await fetch('https://api.openai.com/v1/responses', { method: 'POST' });",
    ],
)
@pytest.mark.parametrize(
    "nom", ["src/resume.test.ts", "src/resume.spec.js", "src/__tests__/resume.tsx"]
)
def test_rouge_un_test_javascript_ou_typescript_est_juge_comme_un_test_python(
    tmp_path: Path, appel: str, nom: str
) -> None:
    source = f"test('appel', async () => {{\n  {appel}\n}});\n"
    constats = _constats(_projet(tmp_path, {nom: source}))
    assert len(constats) == 1, (nom, appel)
    assert constats[0].localisation.endswith(f"{nom}:2")


def test_rouge_un_produit_dont_le_seul_defaut_est_l_appel_reel_n_est_ni_skip_ni_na(
    tmp_path: Path,
) -> None:
    """Aucun prompt, aucun modèle nommé : l inventaire est vide, le constat ne doit pas l être."""
    sortie = prompts.analyser(_projet(tmp_path, {"tests/test_a.py": APPEL_REEL_PY}))
    assert sortie.verdict == "FAIL", sortie.non_juge
    assert [f.classe for f in sortie.findings] == [CLASSE]


def test_rouge_l_appel_reel_est_vu_meme_sans_client_declare_au_manifeste(tmp_path: Path) -> None:
    """Un appel HTTP direct à l adresse du fournisseur n a besoin d aucune dépendance."""
    projet = tmp_path / "produit"
    (projet / "tests").mkdir(parents=True)
    (projet / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    (projet / "tests" / "test_brut.py").write_text(
        "def test_brut():\n    httpx.post('https://api.openai.com/v1/embeddings')\n",
        encoding="utf-8",
    )
    sortie = prompts.analyser(projet)
    assert sortie.verdict == "FAIL"
    assert [f.classe for f in sortie.findings] == [CLASSE]


# --- VERT : le même appel, sous double ------------------------------------------------------------
APPEL_SOUS_DOUBLE_PY = (
    "from openai import OpenAI\n"
    "\n"
    "\n"
    "def test_resume_un_texte(monkeypatch):\n"
    "    monkeypatch.setattr(OpenAI, 'chat', FauxChat())\n"
    "    client = OpenAI(api_key='cle-de-test')\n"
    "    reponse = client.chat.completions.create(model='m', messages=[])\n"
    "    assert reponse.choices\n"
)


def test_vert_le_meme_appel_sous_monkeypatch_ne_produit_aucun_constat(tmp_path: Path) -> None:
    projet = _projet(tmp_path, {"backend/tests/test_resume.py": APPEL_SOUS_DOUBLE_PY})
    assert _constats(projet) == []
    assert prompts.analyser(projet).verdict != "FAIL"


@pytest.mark.parametrize(
    "double",
    [
        "from unittest import mock",
        "from unittest.mock import patch",
        "@patch('app.client.OpenAI')",
        "import respx",
        "transport = httpx.MockTransport(lambda r: None)",
        "import responses",
        "@pytest.mark.vcr",
        "cassette = 'cassettes/resume.yaml'",
        "import nock from 'nock';",
        "import { setupServer } from 'msw/node';",
        "vi.mock('openai');",
        "jest.mock('openai');",
    ],
)
def test_vert_chacun_des_doubles_listes_leve_le_constat(tmp_path: Path, double: str) -> None:
    source = f"{double}\n\n{APPEL_REEL_PY}"
    javascript = any(mot in double for mot in ("nock", "msw", "vi.mock", "jest.mock"))
    nom = "tests/a.test.ts" if javascript else "tests/test_double.py"
    assert _constats(_projet(tmp_path, {nom: source})) == [], double


def test_vert_un_double_dans_la_configuration_de_test_voisine_suffit(tmp_path: Path) -> None:
    """`conftest.py` du dossier de tests, ou d un dossier parent, bouche pour tous les fichiers."""
    projet = _projet(
        tmp_path,
        {
            "backend/tests/conftest.py": (
                "import pytest\n\n@pytest.fixture(autouse=True)\n"
                "def _bouchon(monkeypatch):\n    monkeypatch.setattr('openai.OpenAI', Faux)\n"
            ),
            "backend/tests/unitaires/test_resume.py": APPEL_REEL_PY,
        },
    )
    assert _constats(projet) == []


def test_vert_une_configuration_javascript_voisine_suffit(tmp_path: Path) -> None:
    projet = _projet(
        tmp_path,
        {
            "web/vitest.setup.ts": "import { vi } from 'vitest';\nvi.mock('openai');\n",
            "web/src/resume.test.ts": "test('a', () => { new OpenAI({ apiKey: 'x' }); });\n",
        },
    )
    assert _constats(projet) == []


def test_rouge_un_double_dans_un_dossier_etranger_ne_bouche_pas(tmp_path: Path) -> None:
    """Le double d un AUTRE sous-projet n est pas voisin : le constat reste."""
    projet = _projet(
        tmp_path,
        {
            "autre/tests/conftest.py": "def f(monkeypatch):\n    monkeypatch.setattr(a, b, c)\n",
            "backend/tests/test_resume.py": APPEL_REEL_PY,
        },
    )
    assert len(_constats(projet)) == 1


# --- Produit-12 : l adresse CITÉE par l assertion, à côté d un double ---------------------------
ADRESSE_ATTENDUE_PY = (
    "import httpx\n"
    "\n"
    "\n"
    "def test_le_client_appelle_la_bonne_adresse(monkeypatch):\n"
    "    appelees = []\n"
    "\n"
    "    def faux_post(url, **_):\n"
    "        appelees.append(url)\n"
    "        return httpx.Response(200, json={})\n"
    "\n"
    "    monkeypatch.setattr(httpx, 'post', faux_post)\n"
    "    appeler_le_fournisseur()\n"
    "    assert appelees == ['https://api.openai.com/v1/chat/completions']\n"
)


def test_produit_12_l_adresse_attendue_par_une_assertion_sous_double_ne_declenche_pas(
    tmp_path: Path,
) -> None:
    projet = _projet(tmp_path, {"backend/tests/test_mutants_fournisseurs.py": ADRESSE_ATTENDUE_PY})
    assert _constats(projet) == []
    assert prompts.analyser(projet).verdict != "FAIL"


def test_produit_12_le_meme_fichier_sans_son_double_redevient_rouge(tmp_path: Path) -> None:
    """Le contrôle DISCRIMINE : c est le double qui lève le constat, pas la forme de l assertion."""
    double = "monkeypatch.setattr(httpx, 'post', faux_post)"
    sans_double = ADRESSE_ATTENDUE_PY.replace(double, "pass")
    sans_double = sans_double.replace("(monkeypatch)", "()")
    assert "monkeypatch" not in sans_double
    assert len(_constats(_projet(tmp_path, {"tests/test_adresse.py": sans_double}))) == 1


# --- Ce qui n est PAS un appel de test ------------------------------------------------------------
def test_vert_le_code_du_produit_appelle_le_fournisseur_sans_constat(tmp_path: Path) -> None:
    """Le client de production DOIT appeler le fournisseur : le constat ne vise que les tests."""
    projet = _projet(
        tmp_path,
        {"backend/app/llm.py": "from openai import OpenAI\n\nclient = OpenAI(api_key='x')\n"},
    )
    assert _constats(projet) == []


def test_vert_une_ligne_de_commentaire_n_est_pas_un_appel(tmp_path: Path) -> None:
    source = "# attention : ne jamais appeler api.openai.com ici\ndef test_a():\n    assert True\n"
    assert _constats(_projet(tmp_path, {"tests/test_a.py": source})) == []


def test_vert_un_double_ne_se_confond_pas_avec_un_mot_courant(tmp_path: Path) -> None:
    """`responses` est un mot ordinaire : seul le paquet `responses` bouche (écart déclaré)."""
    source = "def test_a():\n    responses = []\n    OpenAI(api_key='x')\n"
    assert len(_constats(_projet(tmp_path, {"tests/test_a.py": source}))) == 1


def test_le_constat_a_une_suite_classee_et_n_est_pas_un_defaut_d_auditeur() -> None:
    finding = {"id": "appel-fournisseur:tests/test_a.py", "classe": CLASSE, "pan": "prompts",
               "message": "m"}
    action = actions.classifier([finding])[0]
    assert "DÉFAUT D'AUDITEUR" not in action["attendu"]
    assert action["categorie"] == "manuelle_dev"
