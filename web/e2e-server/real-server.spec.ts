import { execFileSync, spawn } from "node:child_process";
import { expect, test, type Page } from "@playwright/test";
import { inkedPixels, inkSettled } from "../e2e/inkedPixels";

const API = process.env.SP_E2E_API ?? "http://localhost:8088";
const OWNER = { email: "owner@corner.shop", password: "corner-shop-sample" };
const SHOTS = "test-results/e2e-server";

/** Streams the bundled RoomPlan room into sp-server through scripts/capture-sample.ts. */
function captureArgs(extra: string[]) {
  return ["--experimental-strip-types", "--no-warnings", "scripts/capture-sample.ts", "--api", API, "--email", OWNER.email, "--password", OWNER.password, ...extra];
}

function captureFinishedScan(): string {
  const output = execFileSync("node", captureArgs([]), { encoding: "utf8" });
  return (JSON.parse(output.trim().split("\n").at(-1)!) as { scanId: string }).scanId;
}

async function createScan(token: string) {
  const response = await fetch(`${API}/v1/scans`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ name: "Back room" }) });
  return ((await response.json()) as { id: string }).id;
}

async function login() {
  const response = await fetch(`${API}/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(OWNER) });
  return ((await response.json()) as { token: string }).token;
}

async function signIn(page: Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/shops");
}

test("a finished scan from sp-server shows its model, report and replay", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const scanId = captureFinishedScan();
  await signIn(page);
  await expect(page.locator(`a[href="/shops/${scanId}"]`).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/shops.png`, fullPage: true });

  await page.goto(`/shops/${scanId}`);
  const drawing = page.getByRole("region", { name: "Shop drawing" });
  await expect(drawing.locator("canvas").first()).toBeVisible();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${SHOTS}/shop.png`, fullPage: true });

  await page.goto(`/shops/${scanId}/report`);
  await expect(page.getByRole("heading", { name: "What we measured" })).toBeVisible();
  const plan = page.getByRole("region", { name: "Floor plan with numbered findings" });
  await inkSettled(plan);
  expect(await inkedPixels(plan)).toBeGreaterThan(5_000);
  await page.screenshot({ path: `${SHOTS}/report.png`, fullPage: true });

  await page.goto(`/shops/${scanId}/live`);
  await expect(page.getByRole("heading", { level: 1, name: "Scan replay" })).toBeVisible();
  await page.waitForTimeout(8000);
  await page.screenshot({ path: `${SHOTS}/replay.png`, fullPage: true });
  expect(errors).toEqual([]);
});

test("a scan in progress inks itself as sp-server streams it", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const sockets: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  const scanId = await createScan(await login());
  await signIn(page);
  await page.goto(`/shops/${scanId}/live`);
  await expect(page.getByRole("heading", { level: 1, name: "Scanning now" })).toBeVisible();
  const sheet = page.getByRole("region", { name: "The scan, drawn as it is captured" });

  const capture = spawn("node", captureArgs(["--scan", scanId, "--pace", "700"]), { stdio: "inherit" });
  const finished = new Promise<number | null>((resolve) => capture.on("exit", resolve));

  await expect.poll(() => inkedPixels(sheet), { timeout: 30_000 }).toBeGreaterThan(1_000);
  await page.screenshot({ path: `${SHOTS}/live-walls.png`, fullPage: true });
  await page.waitForTimeout(6000);
  await page.screenshot({ path: `${SHOTS}/live-middle.png`, fullPage: true });
  expect(await finished).toBe(0);
  await expect(page.getByRole("link", { name: "Read the full report" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { level: 1, name: "Scan finished" })).toBeVisible();
  await inkSettled(sheet);
  await page.screenshot({ path: `${SHOTS}/live-finished.png`, fullPage: true });
  const live = sockets.filter((url) => url.includes("/live"));
  expect(live.length).toBeGreaterThan(0);
  for (const url of live) expect(url).toMatch(/[?&]ticket=[^&]+/);
  for (const url of live) expect(url).not.toMatch(/[?&]token=/);
  expect(errors).toEqual([]);
});
