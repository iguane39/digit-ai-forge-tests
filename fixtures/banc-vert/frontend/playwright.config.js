import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  reporter: [["json", { outputFile: "resultat-playwright.json" }], ["line"]],
  use: { baseURL: "http://localhost:41743", trace: "off" },
  // TF-0136 : voir le meme commentaire dans fixtures/banc-rouge/frontend/playwright.config.js —
  // `false` empeche ce banc de se faire passer, en silence, pour un processus tiers deja assis
  // sur le port 4173.
  webServer: { command: "npm run preview", url: "http://localhost:41743", reuseExistingServer: false, timeout: 120000 },
});
