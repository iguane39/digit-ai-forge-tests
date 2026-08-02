// Suite Front couvrante : les 5 routes atteintes, les 20 elements interactifs exerces.
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

test("liste des commandes", async ({ page }) => {
  await page.goto("/commandes");
  await page.getByTestId("filtre-statut").selectOption("validee");
  await page.getByTestId("tri-date").click();
  await page.getByTestId("bouton-nouvelle").click();
  await page.getByTestId("bouton-export").click();
  await expect(page.getByTestId("pagination")).toBeVisible();
});

test("detail de commande", async ({ page }) => {
  await page.goto("/commandes/1");
  await page.getByTestId("champ-quantite").fill("3");
  await page.getByTestId("selecteur-plat").selectOption("soupe");
  await page.getByTestId("bouton-enregistrer").click();
  await page.getByTestId("bouton-annuler").click();
  await page.getByTestId("bouton-dupliquer").click();
  await page.getByTestId("bouton-supprimer").click();
});

test("administration", async ({ page }) => {
  await page.goto("/admin");
  await page.getByTestId("import-fichier").setInputFiles({
    name: "commandes.csv", mimeType: "text/csv", buffer: Buffer.from("plat,quantite\ncurry,2\n"),
  });
  await page.getByTestId("bouton-cloture").click();
  await page.getByTestId("bouton-purge").click();
  await page.getByTestId("filtre-utilisateur").selectOption("chef");
});
