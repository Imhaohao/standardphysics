import { expect, test } from "@playwright/test";
import { inkedPixels, inkSettled } from "./inkedPixels";

test("the home sheet draws the sample shop in ink and offers sign-in", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Find what blocks customers in your shop" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Title block" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in to see your shops" })).toHaveAttribute("href", "/sign-in");

  const featured = page.getByRole("link", { name: /Open the sample shop/ });
  await expect(featured).toBeVisible();
  await expect.poll(() => inkedPixels(featured), { timeout: 20_000 }).toBeGreaterThan(5_000);

  await inkSettled(featured);
  const frame = page.locator("[data-sheet-frame]");
  await expect(frame).toHaveCount(1);
  await page.screenshot({ path: "test-results/e2e/home.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("the sign-in link leads to the sign-in form", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in to see your shops" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("every sheet links to the privacy policy", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("link", { name: "Privacy policy" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Privacy policy" })).toBeVisible();
  await expect(page.getByRole("link", { name: "tyadgirkar@gmail.com" }).first()).toHaveAttribute("href", "mailto:tyadgirkar@gmail.com");
});

test("a new owner creates an account from the sign-in form", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create an account" }).click();
  await expect(page.getByRole("heading", { name: "Create an account" })).toBeVisible();
  await page.getByLabel("Email").fill("new-owner@example.com");
  await page.getByLabel("Password").fill("a long password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/shops$/);
});
