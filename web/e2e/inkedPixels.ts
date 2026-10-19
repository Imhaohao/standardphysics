import type { Locator } from "@playwright/test";

/** How many pixels of a section's ink canvases have been painted. */
export function inkedPixels(section: Locator) {
  return section.evaluate((root) =>
    [...root.querySelectorAll<HTMLCanvasElement>("canvas[data-ink-layer]")].reduce((total, canvas) => {
      const context = canvas.getContext("2d");
      if (!context || canvas.width === 0 || canvas.height === 0) return total;
      const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
      let painted = 0;
      for (let index = 3; index < data.length; index += 4) if (data[index]! > 0) painted += 1;
      return total + painted;
    }, 0),
  );
}

/** Waits until the ink stops changing, so a screenshot shows the finished drawing. */
export async function inkSettled(section: Locator, quietMs = 1500) {
  let previous = -1;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const current = await inkedPixels(section);
    if (current === previous) return current;
    previous = current;
    await section.page().waitForTimeout(quietMs);
  }
  return previous;
}
