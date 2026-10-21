import { expect, test } from "@playwright/test";
import { inkedPixels, inkSettled } from "./inkedPixels";

test("the findings report groups the sample shop by element with both codes side by side", async ({ page }) => {
  await page.goto("/shops/sample-living-room/report");

  await expect(page.getByRole("heading", { name: "What we measured" })).toBeVisible();
  const questions = page.getByRole("region", { name: "Questions for you" });
  await expect(questions.getByRole("listitem").first()).toContainText(/§\d[\d.]* and §11B-\d/);

  const elements = page.getByRole("region", { name: "What we measured" });
  await expect(elements.getByText(/^§11B-\d/).first()).toBeVisible();
  await expect(elements.getByText(/^§\d/).first()).toBeVisible();
  await expect(elements.getByText(/min$/).first()).toBeVisible();

  const checked = page.getByRole("region", { name: "What we checked" });
  await expect(checked.getByRole("row", { name: /^2010 ADA Standards \d+ \d+ \d+$/ })).toBeVisible();
  await checked.getByText(/^See the \d+ sections we don’t check yet/).click();
  await expect(checked.getByText("§11B-202.5")).toBeVisible();

  const plan = page.getByRole("region", { name: "Floor plan with numbered findings" });
  await expect(plan.getByText(/The plan measures \d+'-\d+" wide/)).toBeAttached();
  await expect.poll(() => inkedPixels(plan), { timeout: 20_000 }).toBeGreaterThan(5_000);

  await inkSettled(plan);
  await page.emulateMedia({ media: "print" });
  await page.screenshot({ path: "test-results/e2e/report-print.png", fullPage: true });
});

test("an owner answers a question and the report counts it", async ({ page }) => {
  await page.goto("/shops/sample-living-room/report");
  const questions = page.getByRole("region", { name: "Questions for you" });
  const fireDoors = questions.getByRole("group", { name: "Is this a rated fire door?" });
  const asked = await fireDoors.count();
  expect(asked).toBeGreaterThan(0);
  await fireDoors.first().getByText("No", { exact: true }).click();
  await questions.getByRole("button", { name: "Save answers" }).click();
  await expect(questions.getByRole("status")).toHaveText("Saved your answer, and the report now counts it.");
  await expect(fireDoors).toHaveCount(asked - 1);

  const given = page.getByRole("region", { name: "Your answers" });
  await given.getByText("Your answers").click();
  await expect(given.getByText("Is fire door").first()).toBeVisible();
  await page.screenshot({ path: "test-results/e2e/report-answered.png", fullPage: true });
  await given.getByRole("button", { name: /^Clear your answer about is fire door/ }).first().click();
  await expect(fireDoors).toHaveCount(asked);
});
