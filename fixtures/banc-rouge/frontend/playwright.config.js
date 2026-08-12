import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  reporter: [["json", { outputFile: "resultat-playwright.json" }], ["line"]],
  use: { baseURL: "http://localhost:41733", trace: "off" },
  // TF-0136 : `reuseExistingServer: true` faisait passer pour « notre serveur » n importe quel
  // processus deja present sur ce port — sur un poste ou un AUTRE projet occupe 4173, la suite
  // s executait en silence contre cette autre application (aucun data-testid en commun),
  // confondant un banc de corpus avec une instance etrangere. `false` force Playwright a
  // demarrer SON PROPRE serveur ; s il trouve le port deja pris, il echoue fort et nommement
  // (« ... is already used ... ») au lieu de tester la mauvaise page sans le dire.
  webServer: { command: "npm run preview", url: "http://localhost:41733", reuseExistingServer: false, timeout: 120000 },
});
