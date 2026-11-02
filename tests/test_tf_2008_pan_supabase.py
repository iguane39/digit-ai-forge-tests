"""TF-2008 (part forge-tests) — le pan `supabase` : tables exposées, RLS et tests pgTAP sous rôle.

Avant ce pan, `supabase/migrations/` n était lu par aucun pan de forge-tests : une table publique
sans RLS, ou une migration qui réactive la RLS de `realtime.messages` et échoue en 42501,
passaient l audit sans un mot. Ce fichier prouve le pan dans les deux sens, sur des projets
synthétiques posés dans `tmp_path` :

  VERT  : chaque table exposée a sa RLS active et un test pgTAP qui la cite sous un rôle ;
  ROUGE : une table sans RLS sort `rls-absente`, une table jamais testée sous rôle sort non
          exercée, un test sans rôle n exerce rien, la réactivation de `realtime.messages` sort
          `realtime-rls-reactivee` ;
  NA    : sans migration Supabase, le pan est sans objet, PROUVÉ.

Formes SQL tirées des pages Supabase lues le 29/10/2026 : « Row Level Security », « Testing
Overview », « Advanced pgTAP Testing », « Realtime Authorization ».
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from forge_tests import classes  # noqa: E402
from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, supabase  # noqa: E402

_MIGRATION = """-- Tables de l'application : une exposée avec RLS, une exposée sans, une privée.
create table public.todos (
  id uuid primary key default gen_random_uuid(),
  task text not null,
  user_id uuid references auth.users not null
);
alter table public.todos enable row level security;
create policy "chacun ses taches" on todos for all to authenticated
  using ((select auth.uid()) = user_id);

create table if not exists "public"."journal" (id bigint primary key, ligne text);

create table prive.secrets (id bigint primary key);
"""

_MIGRATION_JOURNAL_RLS = "alter table public.journal enable row level security;\n"

_TEST_SOUS_ROLE = """begin;
create extension if not exists pgtap with schema extensions;
select plan(1);
set local role authenticated;
set local request.jwt.claim.sub = '123e4567-e89b-12d3-a456-426614174000';
select results_eq('select count(*) from todos', ARRAY[0::bigint], 'aucune tache visible');
select * from finish();
rollback;
"""

_TEST_JOURNAL_HELPERS = """begin;
select plan(1);
select tests.authenticate_as('user1@test.com');
select is_empty('select * from public.journal', 'journal fermé à l utilisateur');
select * from finish();
rollback;
"""


def _projet(tmp_path: Path, fichiers: dict[str, str]) -> Path:
    racine = tmp_path / "projet"
    for relatif, contenu in fichiers.items():
        chemin = racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return racine


_M1 = "supabase/migrations/20261029000000_schema.sql"
_M2 = "supabase/migrations/20261029000100_journal_rls.sql"


def test_le_pan_est_au_registre_et_attendu() -> None:
    assert supabase.PAN in PANS_ATTENDUS
    assert REGISTRE["supabase-pgtap"] is supabase


def test_inventaire_des_tables_exposees_seulement(tmp_path: Path) -> None:
    ids = [e.id for e in supabase.inventaire(_projet(tmp_path, {_M1: _MIGRATION}))]
    # `prive.secrets` n est pas dans un schéma exposé : pas un élément du pan.
    assert ids == ["supabase:table:public.journal", "supabase:table:public.todos"]


def test_rouge_table_exposee_sans_rls(tmp_path: Path) -> None:
    racine = _projet(
        tmp_path, {_M1: _MIGRATION, "supabase/tests/database/todos.sql": _TEST_SOUS_ROLE}
    )
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "FAIL"
    rls = [f for f in sortie.findings if f.classe == classes.RLS_ABSENTE]
    assert [f.id for f in rls] == ["rls:public.journal"]
    assert sortie.surface is not None
    assert sortie.surface["elements_non_exerces"] == ["supabase:table:public.journal"]


def test_vert_rls_active_et_tests_sous_role(tmp_path: Path) -> None:
    racine = _projet(
        tmp_path,
        {
            _M1: _MIGRATION,
            _M2: _MIGRATION_JOURNAL_RLS,
            "supabase/tests/database/todos.sql": _TEST_SOUS_ROLE,
            "supabase/tests/database/journal.sql": _TEST_JOURNAL_HELPERS,
        },
    )
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]


def test_rouge_test_pgtap_sans_role_nexerce_rien(tmp_path: Path) -> None:
    """Un test qui interroge la table en `postgres` contourne la RLS : il ne la teste pas."""
    sans_role = "begin;\nselect plan(1);\nselect has_table('todos');\nselect * from finish();\n"
    racine = _projet(
        tmp_path, {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "supabase/tests/t.sql": sans_role}
    )
    assert supabase.exerces(racine) == set()


def test_rls_desactivee_par_une_migration_suivante(tmp_path: Path) -> None:
    desactive = "alter table public.todos disable row level security;\n"
    racine = _projet(tmp_path, {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS + desactive})
    rls = [f.id for f in supabase.analyser(racine).findings if f.classe == classes.RLS_ABSENTE]
    assert rls == ["rls:public.todos"]


def test_rouge_realtime_reactive_puis_remede(tmp_path: Path) -> None:
    realtime = (
        "alter table realtime.messages enable row level security;\n"
        'create policy "lecture" on realtime.messages for select to authenticated using (true);\n'
    )
    m3 = "supabase/migrations/20261029000200_realtime.sql"
    fichiers = {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, m3: realtime}
    racine = _projet(tmp_path, fichiers)
    constats = [
        f for f in supabase.analyser(racine).findings if f.classe == classes.REALTIME_RLS_REACTIVEE
    ]
    assert len(constats) == 1 and constats[0].localisation.endswith("_realtime.sql:1")
    # Remède proposé : retirer la ligne `alter table`, garder la politique.
    (racine / m3).write_text(realtime.split("\n", 1)[1], encoding="utf-8")
    constats = [
        f for f in supabase.analyser(racine).findings if f.classe == classes.REALTIME_RLS_REACTIVEE
    ]
    assert constats == []


def test_schemas_exposes_lus_dans_config_toml(tmp_path: Path) -> None:
    config = '[api]\nschemas = ["public", "graphql_public", "prive"]\n'
    racine = _projet(tmp_path, {_M1: _MIGRATION, "supabase/config.toml": config})
    ids = {e.id for e in supabase.inventaire(racine)}
    assert "supabase:table:prive.secrets" in ids


def test_table_supprimee_sort_de_linventaire(tmp_path: Path) -> None:
    racine = _projet(tmp_path, {_M1: _MIGRATION, _M2: "drop table if exists public.journal;\n"})
    assert [e.id for e in supabase.inventaire(racine)] == ["supabase:table:public.todos"]


def test_sans_migration_supabase_le_pan_est_sans_objet(tmp_path: Path) -> None:
    racine = _projet(tmp_path, {"migrations/001.sql": "create table t (id int);\n"})
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "NA"
    assert any("aucune migration Supabase" in n for n in sortie.non_juge)


# --- TF-2046 : une table appelée par l API depuis un fichier de `tests/` est exercée -----------
# Mesuré sur un banc RLS par l API (33 cas par rôle via `/rest/v1`) : 4 tables déclarées
# « inventoriée, jamais exercée », couverture 0 %, parce que seul un fichier pgTAP comptait.

_DECLARATION = "FORGE_TESTS_SUPABASE_TABLES_EXERCEES"
_ENV_PROJET = ".env.forge-tests"

_BANC_PY = '''"""Banc RLS par l API : chaque rôle appelle les tables par /rest/v1."""
import requests

BASE = "http://127.0.0.1:54321"


def test_todos_visibles_par_leur_proprietaire(jeton):
    r = requests.get(f"{BASE}/rest/v1/todos?select=*", headers={"Authorization": jeton})
    assert r.status_code == 200


def test_journal_via_le_client(client):
    assert client.from_("journal").select("*").execute().data == []
'''

_COMMENTAIRES_PY = '''"""Notes : voir /rest/v1/todos et client.from_("journal") plus bas."""
# GET /rest/v1/todos  -- a écrire
# client.from_("journal").select("*")


def test_rien_n_appelle_les_tables(client):
    assert client is not None
'''

_BANC_TS = '''// Banc e2e : https://exemple.test/rest/v1/journal n est qu un commentaire
/* const vieux = `${url}/rest/v1/todos`; */
const url = "http://127.0.0.1:54321";
test("todos", async () => {
  const r = await fetch(`${url}/rest/v1/todos?select=*`);
  expect(r.status).toBe(200);
});
'''


@pytest.fixture(autouse=True)
def _env_sans_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le champ du produit ne vient jamais de l environnement du poste qui joue la suite."""
    monkeypatch.delenv(_DECLARATION, raising=False)


def test_vert_table_appelee_par_l_api_depuis_tests(tmp_path: Path) -> None:
    """Les deux formes de la demande : `/rest/v1/<table>` et `from_("<table>")`."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "tests/rls/test_banc.py": _BANC_PY},
    )
    assert supabase.exerces(racine) == {
        "supabase:table:public.journal",
        "supabase:table:public.todos",
    }
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]


def test_rouge_table_seulement_citee_en_commentaire_n_est_pas_exercee(tmp_path: Path) -> None:
    """Commentaire `#`, docstring, appel en toutes lettres dans un commentaire : rien ne compte."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "tests/test_notes.py": _COMMENTAIRES_PY},
    )
    assert supabase.exerces(racine) == set()
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert sortie.surface is not None
    assert sortie.surface["elements_non_exerces"] == [
        "supabase:table:public.journal",
        "supabase:table:public.todos",
    ]
    # Remède : remplacer les commentaires par de vrais appels fait passer les deux tables.
    (racine / "tests" / "test_notes.py").write_text(_BANC_PY, encoding="utf-8")
    assert supabase.analyser(racine).verdict == "PASS"


def test_rouge_commentaires_typescript_et_url_dans_une_chaine(tmp_path: Path) -> None:
    """`//` et `/* */` ne comptent pas ; le `//` d une URL dans une chaîne n ouvre rien."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "tests/e2e/rls.spec.ts": _BANC_TS},
    )
    assert supabase.exerces(racine) == {"supabase:table:public.todos"}


def test_rouge_appel_hors_de_tests_ne_compte_pas(tmp_path: Path) -> None:
    """Le code du produit qui appelle sa propre table n est pas un test."""
    racine = _projet(
        tmp_path, {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "src/client.py": _BANC_PY}
    )
    assert supabase.exerces(racine) == set()


def test_vert_table_declaree_par_le_produit(tmp_path: Path) -> None:
    """Le champ du produit désigne la table, nue (schéma `public`) ou qualifiée, ET son chemin de
    preuve (TF-2060, comme `declarations.py`) ; il le DIT."""
    racine = _projet(
        tmp_path,
        {
            _M1: _MIGRATION,
            _M2: _MIGRATION_JOURNAL_RLS,
            "tests/banc/rls.spec.ts": "// banc joué hors de ce pan\n",
            _ENV_PROJET: (
                f"{_DECLARATION}=todos=tests/banc/rls.spec.ts, "
                "public.journal=tests/banc/rls.spec.ts, prive.fantome=tests/banc/rls.spec.ts\n"
            ),
        },
    )
    assert supabase.exerces(racine) == {
        "supabase:table:public.journal",
        "supabase:table:public.todos",
    }
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "PASS"
    assert any(
        "sur déclaration du produit" in n and "public.todos (tests/banc/rls.spec.ts)" in n
        for n in sortie.non_juge
    )
    assert not any("REFUSÉE" in n for n in sortie.non_juge)


def test_rouge_declaration_sans_effet_sur_une_table_inconnue(tmp_path: Path) -> None:
    """Déclarer une table inexistante n en crée pas une : l inventaire vient des migrations."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, _ENV_PROJET: f"{_DECLARATION}=autre\n"},
    )
    assert supabase.exerces(racine) == set()
    assert supabase.analyser(racine).verdict == "FAIL"


# --- TF-2060 : supabase-js `.from("<table>")` et déclaration avec chemin de preuve --------------

_BANC_SUPABASE_JS = """import { createClient } from "@supabase/supabase-js";
const supabase = createClient(url, key);
test("todos par leur proprietaire", async () => {
  const { data } = await supabase
    .from("todos")
    .select("*");
  expect(data).toEqual([]);
});
test("journal via un schema", async () => {
  const r = await admin.schema("public")?.from('journal').select("*");
  expect(r.error).toBeNull();
});
"""

_FAUX_AMIS_JS = """test("aucun appel de table", () => {
  const a = Array.from("todos");
  const b = Buffer.from("journal");
  const c = Object.from("todos");
  const d = Uint8Array.from("journal");
  const e = Observable.from("todos");
  const f = Readable.from("journal");
  const g = Array.from("todos", (x) => x);
  const h = Array
    .from("journal");
  expect([a, b, c, d, e, f, g, h]).toBeDefined();
});
"""

_BANC_FROM_EN_COMMENTAIRE_JS = """// supabase.from("todos") a écrire
/* await supabase.from("journal").select("*") */
test("rien", () => { expect(1).toBe(1); });
"""


def test_vert_supabase_js_from_appelle_la_table(tmp_path: Path) -> None:
    """Chaîne sur plusieurs lignes, guillemets simples, `?.` et `.schema(…)` en amont."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "tests/e2e/rls.spec.ts": _BANC_SUPABASE_JS},
    )
    assert supabase.exerces(racine) == {
        "supabase:table:public.journal",
        "supabase:table:public.todos",
    }
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]


def test_rouge_faux_amis_de_from_n_exercent_aucune_table(tmp_path: Path) -> None:
    """`Array.from("todos")`, `Buffer.from("journal")` : même nom que la table, autre sens."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, "tests/unit/outils.test.ts": _FAUX_AMIS_JS},
    )
    assert supabase.exerces(racine) == set()
    assert supabase.analyser(racine).verdict == "FAIL"
    # Remède : le même fichier avec de vrais appels du client fait passer les deux tables.
    (racine / "tests" / "unit" / "outils.test.ts").write_text(
        _BANC_SUPABASE_JS, encoding="utf-8"
    )
    assert supabase.analyser(racine).verdict == "PASS"


def test_rouge_from_en_commentaire_ou_hors_de_tests_ne_compte_pas(tmp_path: Path) -> None:
    racine = _projet(
        tmp_path,
        {
            _M1: _MIGRATION,
            _M2: _MIGRATION_JOURNAL_RLS,
            "tests/e2e/notes.spec.ts": _BANC_FROM_EN_COMMENTAIRE_JS,
            "src/data.ts": _BANC_SUPABASE_JS,
        },
    )
    assert supabase.exerces(racine) == set()


def test_rouge_from_js_dans_un_fichier_python_ou_une_chaine_non_js(tmp_path: Path) -> None:
    """`.from("<table>")` est du JS : un `.sh` qui le cite n appelle rien."""
    racine = _projet(
        tmp_path,
        {
            _M1: _MIGRATION,
            _M2: _MIGRATION_JOURNAL_RLS,
            "tests/run.sh": 'echo \'x.from("todos")\'\n',
        },
    )
    assert supabase.exerces(racine) == set()


def test_rouge_declaration_sans_chemin_de_preuve_ne_compte_pas(tmp_path: Path) -> None:
    """Forme d avant TF-2060 : une table nue. Refusée, DITE au rapport, table non exercée."""
    racine = _projet(
        tmp_path,
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, _ENV_PROJET: f"{_DECLARATION}=todos\n"},
    )
    assert supabase.exerces(racine) == set()
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "FAIL"
    refus = [n for n in sortie.non_juge if "REFUSÉE" in n]
    assert len(refus) == 1 and "todos" in refus[0] and "aucun chemin de preuve" in refus[0]
    assert "PAS comme exercée" in refus[0]


def test_rouge_declaration_a_preuve_introuvable_ou_hors_du_projet(tmp_path: Path) -> None:
    (tmp_path / "ailleurs.txt").write_text("hors du projet\n", encoding="utf-8")
    racine = _projet(
        tmp_path,
        {
            _M1: _MIGRATION,
            _M2: _MIGRATION_JOURNAL_RLS,
            _ENV_PROJET: f"{_DECLARATION}=todos=tests/absent.spec.ts, journal=../ailleurs.txt\n",
        },
    )
    assert supabase.exerces(racine) == set()
    refus = " ".join(n for n in supabase.analyser(racine).non_juge if "REFUSÉE" in n)
    assert "introuvable ou illisible (tests/absent.spec.ts)" in refus
    assert "hors du projet (../ailleurs.txt)" in refus


def test_les_mentions_d_un_projet_ne_fuient_pas_vers_le_suivant(tmp_path: Path) -> None:
    """Le non-jugé du module n est pas une pile : deux analyses de suite, chacune sa mention."""
    avec = _projet(
        tmp_path / "a",
        {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS, _ENV_PROJET: f"{_DECLARATION}=todos\n"},
    )
    sans = _projet(tmp_path / "b", {_M1: _MIGRATION, _M2: _MIGRATION_JOURNAL_RLS})
    avant = list(supabase.NON_JUGE)
    assert any("REFUSÉE" in n for n in supabase.analyser(avec).non_juge)
    assert not any("REFUSÉE" in n for n in supabase.analyser(sans).non_juge)
    assert avant == supabase.NON_JUGE


def test_vert_declaration_avec_preuve_lisible_et_sa_reparation(tmp_path: Path) -> None:
    """Remède proposé par le message (`table=chemin/du/test`) : il doit PASSER."""
    racine = _projet(
        tmp_path,
        {
            _M1: _MIGRATION,
            _M2: _MIGRATION_JOURNAL_RLS,
            "tests/banc.spec.ts": "// preuve\n",
            _ENV_PROJET: f"{_DECLARATION}=todos, journal=tests/banc.spec.ts\n",
        },
    )
    assert supabase.exerces(racine) == {"supabase:table:public.journal"}
    (racine / _ENV_PROJET).write_text(
        f"{_DECLARATION}=todos=tests/banc.spec.ts, journal=tests/banc.spec.ts\n", encoding="utf-8"
    )
    sortie = supabase.analyser(racine)
    assert sortie.verdict == "PASS"
    assert not any("REFUSÉE" in n for n in sortie.non_juge)
