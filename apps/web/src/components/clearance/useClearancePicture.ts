"use client";

import { useEffect, useMemo, useState } from "react";
import { type ClearanceField, contourAt, type FillPalette, over, paintFills, paintScale, type Rgba, type Segment } from "@/lib/clearance-map";

/**
 * The map ready to draw: its pixels in the bands' colours, the same pixels on a canvas for the plan's image, and the
 * edge past which a route is too tight. The model takes the pixels themselves: a canvas keeps its colours multiplied
 * by their alpha, which loses what a clear pixel carries and darkens a band's edge once the model blends it.
 */
export type ClearancePicture = {
  field: ClearanceField;
  pixels: Uint8ClampedArray<ArrayBuffer>;
  width: number;
  height: number;
  canvas: HTMLCanvasElement;
  tightEdge: Segment[];
};

const FILL_TOKENS: Record<keyof FillPalette, string> = {
  turning: "--color-clearance-turning",
  route: "--color-clearance-route",
  reduced: "--color-clearance-reduced",
};

/** The tight edge's colour and the halo under it, read where a renderer needs a colour rather than a CSS variable. */
export const TIGHT_TOKEN = "--color-clearance-tight";
export const HALO_TOKEN = "--color-clearance-halo";

export function tokenValue(token: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
}

const GROUND_TOKEN = "--color-clearance-ground";

/**
 * Each band's colour as the stylesheet defines it, laid over the ground that knocks a photographed floor back. The
 * canvas parses the tokens' CSS, colour-mix and all, so the floor is painted in the colours the stylesheet names.
 */
function readFillPalette(): FillPalette {
  const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!probe) throw new Error("Canvas 2D is unavailable");
  const ground = rgbaOf(probe, tokenValue(GROUND_TOKEN));
  const entries = Object.entries(FILL_TOKENS).map(([band, token]) => [band, over(rgbaOf(probe, tokenValue(token)), ground)]);
  return Object.fromEntries(entries) as FillPalette;
}

function rgbaOf(probe: CanvasRenderingContext2D, colour: string): Rgba {
  probe.clearRect(0, 0, 1, 1);
  probe.fillStyle = "transparent";
  probe.fillStyle = colour;
  probe.fillRect(0, 0, 1, 1);
  const [red, green, blue, alpha] = probe.getImageData(0, 0, 1, 1).data;
  return [red, green, blue, alpha];
}

function paint(field: ClearanceField): ClearancePicture {
  const scale = paintScale(field);
  const [width, height] = [field.columns * scale, field.rows * scale];
  const pixels = paintFills(field, readFillPalette(), scale);
  const canvas = document.createElement("canvas");
  [canvas.width, canvas.height] = [width, height];
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D is unavailable");
  context.putImageData(new ImageData(pixels, width, height), 0, 0);
  return { field, pixels, width, height, canvas, tightEdge: contourAt(field, field.bands.reduced_inches) };
}

export function useClearancePicture(field: ClearanceField | null): ClearancePicture | null {
  return useMemo(() => (field ? paint(field) : null), [field]);
}

/** How long a replaced picture's address is kept, so the plan holds it until the next one has been drawn. */
const RELEASE_AFTER_MS = 2000;

/**
 * The picture as an image address for the plan. It is encoded off the main thread, and the plan keeps showing the
 * last one until the next is ready, so the map never blinks out while it catches up with a drag.
 */
export function usePictureUrl(picture: ClearancePicture | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!picture) return;
    let made: string | null = null;
    let current = true;
    picture.canvas.toBlob((blob) => {
      if (!blob || !current) return;
      made = URL.createObjectURL(blob);
      setUrl(made);
    });
    return () => {
      current = false;
      const replaced = made;
      if (replaced) setTimeout(() => URL.revokeObjectURL(replaced), RELEASE_AFTER_MS);
    };
  }, [picture]);
  return url;
}
