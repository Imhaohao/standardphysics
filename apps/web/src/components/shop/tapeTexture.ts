import { CanvasTexture, ClampToEdgeWrapping, SRGBColorSpace } from "three";

export const TAPE_TEXTURE_INCHES = 48;
const PIXELS_PER_INCH = 128;
const TEXTURE_HEIGHT = 208;

const tickLengthByEighth: Record<number, number> = { 0: 70, 4: 50, 2: 36, 6: 36 };
const SHORT_TICK = 24;

function tickLength(eighth: number) {
  return tickLengthByEighth[eighth % 8] ?? SHORT_TICK;
}

function cssVariable(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function createTapeTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = TAPE_TEXTURE_INCHES * PIXELS_PER_INCH;
  canvas.height = TEXTURE_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D is unavailable");

  const ink = cssVariable("--color-ink");
  context.fillStyle = cssVariable("--color-tape");
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = ink;

  for (let eighth = 1; eighth < TAPE_TEXTURE_INCHES * 8; eighth += 1) {
    const x = (eighth / 8) * PIXELS_PER_INCH;
    const width = eighth % 8 === 0 ? 7 : 4;
    context.fillRect(x - width / 2, 0, width, tickLength(eighth));
  }

  context.font = `800 96px ${cssVariable("--font-display")}`;
  context.textAlign = "right";
  context.textBaseline = "alphabetic";
  for (let inch = 1; inch < TAPE_TEXTURE_INCHES; inch += 1) {
    context.fillText(String(inch), inch * PIXELS_PER_INCH - 12, TEXTURE_HEIGHT - 16);
  }

  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.wrapS = ClampToEdgeWrapping;
  texture.anisotropy = 8;
  return texture;
}
