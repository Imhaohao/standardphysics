import type { InkPalette } from "@/lib/brush/render";

const MAX_CANVAS_PIXELS_TALL = 12000;
const MAX_PIXEL_RATIO = 2;

export function readPalette(element: HTMLElement, surfaceToken = "--color-sheet"): InkPalette {
  const styles = getComputedStyle(element);
  return {
    ink: styles.getPropertyValue("--color-ink").trim(),
    paper: styles.getPropertyValue(surfaceToken).trim(),
    fontFamily: styles.fontFamily,
  };
}

export function readColor(element: HTMLElement, token: string) {
  return getComputedStyle(element).getPropertyValue(token).trim();
}

export function createTextMeasurer(fontFamily: string) {
  const context = document.createElement("canvas").getContext("2d");
  return (text: string, size: number) => {
    if (!context) return text.length * size * 0.55;
    context.font = `500 ${size}px ${fontFamily}`;
    return context.measureText(text).width;
  };
}

export function context2d(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser can't draw on a canvas.");
  return context;
}

export function clearCanvas(canvas: HTMLCanvasElement) {
  const context = context2d(canvas);
  context.save();
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.restore();
}

function snapshotOf(canvas: HTMLCanvasElement) {
  if (canvas.width === 0 || canvas.height === 0) return null;
  const copy = document.createElement("canvas");
  copy.width = canvas.width;
  copy.height = canvas.height;
  context2d(copy).drawImage(canvas, 0, 0);
  return copy;
}

export function pixelRatioFor(height: number, devicePixelRatio: number) {
  return Math.min(devicePixelRatio || 1, MAX_PIXEL_RATIO, MAX_CANVAS_PIXELS_TALL / Math.max(1, height));
}

/** Sizes both canvases to the surface, keeping what is already painted. Returns false when nothing changed. */
export function fitCanvases(surface: HTMLElement, paint: HTMLCanvasElement, live: HTMLCanvasElement) {
  const pixelRatio = pixelRatioFor(surface.clientHeight, window.devicePixelRatio);
  const width = Math.round(surface.clientWidth * pixelRatio);
  const height = Math.round(surface.clientHeight * pixelRatio);
  if (paint.width === width && paint.height === height) return false;
  const snapshot = snapshotOf(paint);
  for (const canvas of [paint, live]) {
    canvas.width = width;
    canvas.height = height;
    context2d(canvas).setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }
  if (snapshot) context2d(paint).drawImage(snapshot, 0, 0, snapshot.width / pixelRatio, snapshot.height / pixelRatio);
  return true;
}
