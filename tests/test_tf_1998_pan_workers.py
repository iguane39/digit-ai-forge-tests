"""TF-1998 (part forge-tests) — le pan `workers` : un Worker Cloudflare a une surface testable.

Avant ce pan, un Worker audité sortait des 17 pans sans qu aucun ne le nomme : pas de FastAPI,
pas de React, pas de migrations SQL. Le cron d un Worker pouvait ne jamais être testé sans que
l audit le dise. Ce fichier prouve le pan dans les deux sens, sur des projets synthétiques posés
dans `tmp_path` :

  VERT  : chaque gestionnaire que la configuration Wrangler déclare est dispatché par un test qui
          tourne dans le runtime Workers (intégration Vitest ou harnais `createTestHarness`) ;
  ROUGE : un cron, une classe Durable Object, un Workflow jamais dispatchés sortent NOMMÉS non
          exercés ; des tests Vitest hors du runtime Workers n exercent rien ;
  NA    : sans configuration Wrangler, le pan est sans objet, PROUVÉ.

Motifs de dispatch tirés des pages Cloudflare lues le 29/10/2026 : « Test APIs » (10/10/2026),
« Interact with Workers » et « Get started » du harnais (27/07/2026).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from forge_tests.adaptateurs import PANS_ATTENDUS, REGISTRE, workers  # noqa: E402
from forge_tests.adaptateurs.workers import _jsonc_vers_json  # noqa: E402

_WRANGLER = """{
  // Worker de démonstration : un cron, une file, une classe Durable Object, un Workflow.
  "name": "worker-demo",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-29",
  "triggers": { "crons": ["0 3 * * *"] },
  "durable_objects": { "bindings": [
    { "name": "COMPTEUR", "class_name": "Compteur" },
    { "name": "EXTERNE", "class_name": "Externe", "script_name": "autre-worker" },
  ] },
  "workflows": [ { "name": "rapport", "binding": "RAPPORT", "class_name": "Rapport" } ],
}
"""

_MODULE = """import { DurableObject, WorkflowEntrypoint } from "cloudflare:workers";

export class Compteur extends DurableObject {}
export class Rapport extends WorkflowEntrypoint {}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const amont = await fetch("https://exemple.invalid/");
    return new Response("ok");
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(Promise.resolve());
  },
};
"""

_VITEST_WORKERS = """import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";
export default defineConfig({
  plugins: [cloudflareTest({ wrangler: { configPath: "./wrangler.jsonc" } })],
});
"""

_TEST_FETCH = """import { exports } from "cloudflare:workers";
import { it, expect } from "vitest";
it("répond", async () => {
  const reponse = await exports.default.fetch("https://exemple.invalid/");
  expect(await reponse.text()).toBe("ok");
});
"""

_TEST_COMPLET = """import { env, exports } from "cloudflare:workers";
import {
  createScheduledController, createExecutionContext, runInDurableObject, introspectWorkflow,
} from "cloudflare:test";
it("cron", async () => {
  const ctrl = createScheduledController({ cron: "0 3 * * *" });
  await exports.default.scheduled(ctrl, env, createExecutionContext());
});
it("compteur", async () => {
  const stub = env.COMPTEUR.get(env.COMPTEUR.idFromName("a"));
  await runInDurableObject(stub, async (instance) => instance);
});
it("rapport", async () => {
  await using introspecteur = await introspectWorkflow(env.RAPPORT);
});
"""


def _worker(tmp_path: Path, fichiers: dict[str, str]) -> Path:
    racine = tmp_path / "worker"
    for relatif, contenu in fichiers.items():
        chemin = racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return racine


def _base(**ajouts: str) -> dict[str, str]:
    return {"wrangler.jsonc": _WRANGLER, "src/index.ts": _MODULE, **ajouts}


def test_le_pan_est_au_registre_et_attendu() -> None:
    assert workers.PAN in PANS_ATTENDUS
    assert REGISTRE["workers-wrangler"] is workers


def test_jsonc_virgule_puis_commentaire_puis_accolade() -> None:
    texte = '{ "a": "https://x.invalid//y", "b": [1, 2, /* fin */ ], // c\n }'
    assert json.loads(_jsonc_vers_json(texte)) == {"a": "https://x.invalid//y", "b": [1, 2]}
    assert json.loads(_jsonc_vers_json('{"c": "x\\\\", "d": 1,}')) == {"c": "x\\", "d": 1}


def test_inventaire_tire_de_la_configuration_et_du_module(tmp_path: Path) -> None:
    ids = sorted(e.id for e in workers.inventaire(_worker(tmp_path, _base())))
    # La classe `Externe` vit dans un autre Worker (script_name) : elle n est pas d ici.
    assert ids == [
        "workers:durable-object:Compteur",
        "workers:fetch:src/index.ts",
        "workers:scheduled:src/index.ts",
        "workers:workflow:Rapport",
    ]


def test_rouge_seule_la_route_http_est_testee(tmp_path: Path) -> None:
    racine = _worker(
        tmp_path, _base(**{"vitest.config.ts": _VITEST_WORKERS, "test/index.spec.ts": _TEST_FETCH})
    )
    sortie = workers.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert sortie.surface is not None
    assert sortie.surface["elements_exerces"] == ["workers:fetch:src/index.ts"]
    assert sorted(sortie.surface["elements_non_exerces"]) == [
        "workers:durable-object:Compteur",
        "workers:scheduled:src/index.ts",
        "workers:workflow:Rapport",
    ]


def test_vert_chaque_gestionnaire_dispatche(tmp_path: Path) -> None:
    racine = _worker(
        tmp_path,
        _base(
            **{
                "vitest.config.ts": _VITEST_WORKERS,
                "test/index.spec.ts": _TEST_FETCH,
                "test/evenements.spec.ts": _TEST_COMPLET,
            }
        ),
    )
    sortie = workers.analyser(racine)
    assert sortie.verdict == "PASS", [f.message for f in sortie.findings]
    assert sortie.surface is not None and sortie.surface["ratio"] == 1.0


def test_rouge_tests_hors_du_runtime_workers(tmp_path: Path) -> None:
    """Les mêmes tests sous un Vitest sans intégration Workers ne tournent pas dans workerd."""
    vitest_node = (
        'import { defineConfig } from "vitest/config";\nexport default defineConfig({});\n'
    )
    racine = _worker(
        tmp_path,
        _base(
            **{
                "vitest.config.ts": vitest_node,
                "test/index.spec.ts": _TEST_FETCH,
                "test/evenements.spec.ts": _TEST_COMPLET,
            }
        ),
    )
    sortie = workers.analyser(racine)
    assert sortie.verdict == "FAIL"
    assert sortie.surface is not None and sortie.surface["exerce"] == 0
    assert any("aucun fichier de test ne tourne dans le runtime" in n for n in sortie.non_juge)


def test_harnais_dintegration_compte_sans_configuration_vitest(tmp_path: Path) -> None:
    """`createTestHarness` exécute le Worker dans workerd : ses dispatchs comptent."""
    harnais = (
        'import { createTestHarness } from "wrangler";\n'
        'const server = createTestHarness({ workers: [{ configPath: "./wrangler.jsonc" }] });\n'
        'test("route", async () => { await server.fetch("/"); });\n'
        'test("cron", async () => {\n'
        '  const apiWorker = server.getWorker("worker-demo");\n'
        '  await apiWorker.scheduled({ cron: "0 3 * * *", scheduledTime: new Date() });\n'
        "});\n"
    )
    racine = _worker(tmp_path, _base(**{"test/integration.test.ts": harnais}))
    exerces = workers.exerces(racine)
    assert exerces == {"workers:fetch:src/index.ts", "workers:scheduled:src/index.ts"}


def test_cron_declare_sans_methode_reste_un_element(tmp_path: Path) -> None:
    """Un cron déclaré par la configuration est un gestionnaire attendu, même si le module ne
    le définit pas au motif lu : la configuration fait foi."""
    module = "export default { async fetch(request) { return new Response(''); } };\n"
    racine = _worker(tmp_path, _base(**{"src/index.ts": module}))
    ids = {e.id for e in workers.inventaire(racine)}
    assert "workers:scheduled:src/index.ts" in ids


def test_sans_configuration_wrangler_le_pan_est_sans_objet(tmp_path: Path) -> None:
    racine = _worker(tmp_path, {"src/index.ts": _MODULE})
    sortie = workers.analyser(racine)
    assert sortie.verdict == "NA"
    assert any("aucune configuration Wrangler" in n for n in sortie.non_juge)


def test_appel_fetch_sortant_nest_pas_un_gestionnaire(tmp_path: Path) -> None:
    """`await fetch(url)` dans le module n invente pas de gestionnaire supplémentaire."""
    module = "export async function aide() {\n  const r = await fetch('https://x.invalid');\n}\n"
    wrangler = '{ "name": "w", "main": "src/index.ts", "compatibility_date": "2026-10-29" }'
    racine = _worker(tmp_path, {"wrangler.jsonc": wrangler, "src/index.ts": module})
    assert workers.inventaire(racine) == []
    assert workers.analyser(racine).verdict == "SKIP"
