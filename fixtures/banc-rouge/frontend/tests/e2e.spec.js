// Suite Front.
import { test, expect } from "@playwright/test";

test("accueil", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("lien-connexion")).toBeVisible();
  await expect(page.getByTestId("lien-commandes")).toBeVisible();
});

test("login", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("champ-email").fill("chef@exemple.fr");
  await page.getByTestId("champ-mot-de-passe").fill("secret");
  await page.getByTestId("bouton-valider").click();
});
