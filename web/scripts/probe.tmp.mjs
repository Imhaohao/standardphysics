import { chromium } from "@playwright/test";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => console.log("console:", m.type(), m.text()));
page.on("pageerror", (e) => console.log("pageerror:", e));
await page.goto(process.argv[2]);
await page.waitForTimeout(4000);
console.log(await page.evaluate(() => [document.visibilityState, getComputedStyle(document.body).getPropertyValue("--color-ink"), matchMedia("(prefers-reduced-motion: reduce)").matches]));
const info = await page.evaluate(() => Array.from(document.querySelectorAll("canvas")).map((c) => {
  const ctx = c.getContext("2d"); const d = c.width && c.height ? ctx.getImageData(0, 0, c.width, c.height).data : [];
  let inked = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) inked++;
  return { w: c.width, h: c.height, cw: c.clientWidth, ch: c.clientHeight, inked };
}));
console.log(JSON.stringify(info));
await browser.close();
