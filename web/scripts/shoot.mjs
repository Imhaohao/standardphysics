// Usage: node scripts/shoot.mjs <url> <outPrefix> <ms,ms,...> [width] [height]
import { chromium } from "@playwright/test";

const [url, prefix, times = "500,2000,6000", width = "1440", height = "900"] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: Number(width), height: Number(height) } });
const errors = [];
page.on("pageerror", (error) => errors.push(String(error)));
page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
const started = Date.now();
await page.goto(url, { waitUntil: "load" });
for (const ms of times.split(",").map(Number)) {
  const wait = ms - (Date.now() - started);
  if (wait > 0) await page.waitForTimeout(wait);
  await page.screenshot({ path: `${prefix}-${ms}.png`, fullPage: true });
}
console.log(JSON.stringify({ errors }, null, 1));
await browser.close();
