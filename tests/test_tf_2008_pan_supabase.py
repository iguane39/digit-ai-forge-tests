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
