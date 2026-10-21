import { expect, test } from "@playwright/test";

test("an owner shares a read-only link, and stopping it closes the link", async ({ page, browser, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/shops/sample-living-room/report");
  const links = page.getByRole("region", { name: "Read-only links" });
  await links.getByRole("button", { name: "Share a read-only link" }).click();
  await expect(links.getByRole("status")).toContainText("Link copied");

  const path = await links.getByRole("link").first().textContent();
  expect(path).toMatch(/^\/r\/[A-Za-z0-9_-]{43}$/);
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(new RegExp(`${path}$`));

  const visitor = await browser.newPage();
  await visitor.goto(path!);
  await expect(visitor.getByRole("heading", { level: 1, name: "Accessibility report for Corner shop" })).toBeVisible();
  await expect(visitor.getByRole("button", { name: "Save answers" })).toHaveCount(0);
  await expect(visitor.getByRole("region", { name: "Questions for the owner" })).toBeVisible();
  await visitor.screenshot({ path: "test-results/e2e/shared-report.png" });

  await links.getByRole("button", { name: "Stop sharing" }).first().click();
  await expect(links.getByRole("status")).toHaveText("That link no longer opens the report.");
  const gone = await visitor.goto(path!);
  expect(gone?.status()).toBe(404);
});
