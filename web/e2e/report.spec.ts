import { expect, test } from "@playwright/test";
import { inkedPixels, inkSettled } from "./inkedPixels";

test("the findings report groups the sample shop by element with both codes side by side", async ({ page }) => {
  await page.goto("/shops/sample-living-room/report");

  await expect(page.getByRole("heading", { name: "Every element we checked" })).toBeVisible();
  const questions = page.getByRole("region", { name: "Questions for you" });
  await expect(questions.getByRole("listitem").first()).toContainText(/§\d[\d.]* and §11B-\d/);

  const elements = page.getByRole("region", { name: "Every element we checked" });
  await expect(elements.getByText(/^§11B-\d/).first()).toBeVisible();
  await expect(elements.getByText(/^§\d/).first()).toBeVisible();
  await expect(elements.getByText(/min$/).first()).toBeVisible();

  const plan = page.getByRole("region", { name: "Floor plan with numbered findings" });
  await expect(plan.getByText(/The plan measures \d+'-\d+" wide/)).toBeAttached();
  await expect.poll(() => inkedPixels(plan), { timeout: 20_000 }).toBeGreaterThan(5_000);

  await inkSettled(plan);
  await page.emulateMedia({ media: "print" });
  await page.screenshot({ path: "test-results/e2e/report-print.png", fullPage: true });
});
