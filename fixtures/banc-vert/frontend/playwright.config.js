import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  reporter: [["json", { outputFile: "resultat-playwright.json" }], ["line"]],
  use: { baseURL: "http://localhost:4173", trace: "off" },
  webServer: { command: "npm run preview", url: "http://localhost:4173", reuseExistingServer: true, timeout: 120000 },
});
