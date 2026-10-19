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
