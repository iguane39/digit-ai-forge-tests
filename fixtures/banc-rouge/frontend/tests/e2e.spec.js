// Suite Front.
import { test } from "@playwright/test";

test("accueil", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("lien-connexion").click();
  await page.getByTestId("lien-commandes").click();
});

test("login", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("champ-email").fill("chef@exemple.fr");
  await page.getByTestId("champ-mot-de-passe").fill("secret");
  await page.getByTestId("bouton-valider").click();
});
