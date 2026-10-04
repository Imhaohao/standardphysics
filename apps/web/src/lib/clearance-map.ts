import type { ClearanceBands, ClearanceMap, ClearancePinch } from "@/types/contracts";
import { shownFigure } from "./findings";
import { base64Bytes, readGreyPng } from "./grey-png";

/**
 * The clearance map decoded: one stored width code per cell, top row first, and where those cells sit in the room.
 * A code of 0 is a cell nobody can stand on; any other is the clear width in steps of `stepInches`, rounded down.
 */
export type ClearanceField = {
  columns: number;
  rows: number;
  cellMeters: number;
  origin: { x: number; y: number };
  rotationDegrees: number;
  stepInches: number;
  codes: Uint8Array;
  bands: ClearanceBands;
  pinches: ClearancePinch[];
};

export type RoomPoint = { x: number; y: number };

/** The colours the floor is painted in, as straight RGBA bytes, one for each band a route fits in. */
export type FillPalette = Record<"turning" | "route" | "reduced", Rgba>;
export type Rgba = [number, number, number, number];

/**
 * The slack the rule pack allows a comparison, in inches (packages/agents rules/pack.py): a measurement within a
 * millionth of an inch of a threshold meets it. Kept here so a width the checks pass is never shown a tenth short.
 */
const COMPARISON_EPSILON = 1e-6;

export async function decodeClearance(map: ClearanceMap): Promise<ClearanceField> {
  const image = await readGreyPng(base64Bytes(map.widths_png));
  if (image.width !== map.columns || image.height !== map.rows) throw new Error("The clearance picture is not the size of its grid.");
  return {
    columns: map.columns, rows: map.rows, cellMeters: map.cell_meters, origin: { x: map.origin.x, y: map.origin.y },
    rotationDegrees: map.rotation_z_degrees, stepInches: map.width_step_inches, codes: image.pixels,
    bands: map.bands, pinches: map.pinches,
  };
}

/**
 * A width as the map labels it: the figure the rest of the app shows, unless that figure would reach a band edge the
 * width falls short of, and then rounded down to a tenth instead. 19.19 in is "19.2 in" here as everywhere, but
 * 35.98 in is "35.9 in", never "36 in", and 31.97 in is "31.9 in". A width the checks count as 36 is "36 in".
 */
export function formatClearWidth(inches: number, bands: ClearanceBands): string {
  const figure = shownFigure(inches);
  const edges = [bands.reduced_inches, bands.route_inches, bands.turning_inches];
  const roundedOnto = edges.some((edge) => inches + COMPARISON_EPSILON < edge && Number.parseFloat(figure) >= edge);
  return roundedOnto ? `${Math.floor((inches + COMPARISON_EPSILON) * 10) / 10} in` : `${figure} in`;
}

/** The most pixels the painted map runs to on its longer side, which keeps a big room's picture light to paint. */
const MOST_PICTURE_PIXELS = 2048;
const MOST_PIXELS_PER_CELL = 2;

/** One straight-alpha colour laid over another, as a browser composites them. */
export function over(top: Rgba, bottom: Rgba): Rgba {
  const [topAlpha, bottomAlpha] = [top[3] / 255, bottom[3] / 255];
  const alpha = topAlpha + bottomAlpha * (1 - topAlpha);
  if (alpha === 0) return [top[0], top[1], top[2], 0];
  const channel = (index: number) => Math.round((top[index] * topAlpha + bottom[index] * bottomAlpha * (1 - topAlpha)) / alpha);
  return [channel(0), channel(1), channel(2), Math.round(alpha * 255)];
}

/** Pixels per cell to paint at: two where the room is small enough, so band edges run smooth, otherwise one. */
export function paintScale(field: ClearanceField): number {
  const fits = Math.floor(MOST_PICTURE_PIXELS / Math.max(field.columns, field.rows));
  return Math.max(1, Math.min(MOST_PIXELS_PER_CELL, fits));
}

/**
 * The map's colours, top row first, four bytes a pixel and `scale` pixels to a cell. Each pixel takes the band of
 * the width found between the cell centres around it, so a band's edge follows the field instead of the cells'
 * stair-steps. Blocked and too-tight floor stays clear; its colour channels carry the route band's, so a renderer
 * that blends neighbouring pixels never darkens the edge of a band toward black.
 */
export function paintFills(field: ClearanceField, palette: FillPalette, scale = 1): Uint8ClampedArray<ArrayBuffer> {
  const [width, height] = [field.columns * scale, field.rows * scale];
  const pixels = new Uint8ClampedArray(new ArrayBuffer(width * height * 4));
  const steps = bandSteps(field, palette);
  for (let row = 0; row < height; row += 1) {
    const down = (row + 0.5) / scale - 0.5;
    for (let column = 0; column < width; column += 1) {
      const colour = colourOf(sampleCode(field, (column + 0.5) / scale - 0.5, down), steps);
      const at = (row * width + column) * 4;
      [pixels[at], pixels[at + 1], pixels[at + 2], pixels[at + 3]] = colour;
    }
  }
  return pixels;
}

type BandStep = { above: number; colour: Rgba };

/** Each filled band from the widest down, with the stored code a width has to pass to be in it. */
function bandSteps(field: ClearanceField, palette: FillPalette): BandStep[] {
  const above = (inches: number) => inches / field.stepInches - 0.5;
  return [
    { above: above(field.bands.turning_inches), colour: palette.turning },
    { above: above(field.bands.route_inches), colour: palette.route },
    { above: above(field.bands.reduced_inches), colour: palette.reduced },
    { above: -Infinity, colour: [palette.route[0], palette.route[1], palette.route[2], 0] },
  ];
}

function colourOf(code: number, steps: BandStep[]): Rgba {
  for (const step of steps) {
    if (code > step.above) return step.colour;
  }
  return steps[steps.length - 1].colour;
}

/** The stored code at a point between cell centres, blended from the four around it. */
export function sampleCode({ codes, columns, rows }: ClearanceField, column: number, row: number): number {
  const [left, top] = [clamp(Math.floor(column), columns - 1), clamp(Math.floor(row), rows - 1)];
  const [right, bottom] = [clamp(left + 1, columns - 1), clamp(top + 1, rows - 1)];
  const [across, down] = [clamp(column - left, 1), clamp(row - top, 1)];
  const upper = codes[top * columns + left] * (1 - across) + codes[top * columns + right] * across;
  const lower = codes[bottom * columns + left] * (1 - across) + codes[bottom * columns + right] * across;
  return upper * (1 - down) + lower * down;
}

function clamp(value: number, most: number): number {
  return Math.min(Math.max(value, 0), most);
}

/** Where a point of the picture, in cells from its top-left corner, lies in the room. */
export function roomPointOf(field: ClearanceField, column: number, row: number): RoomPoint {
  const along = { x: column * field.cellMeters, y: (field.rows - row) * field.cellMeters };
  const turn = (field.rotationDegrees * Math.PI) / 180;
  const [cos, sin] = [Math.cos(turn), Math.sin(turn)];
  return { x: field.origin.x + cos * along.x - sin * along.y, y: field.origin.y + sin * along.x + cos * along.y };
}

export type Segment = [RoomPoint, RoomPoint];

/**
 * The edge of the floor at least `inches` wide, as line segments in the room: marching squares over the cell
 * centres, with each crossing placed where the stored widths either side of it say the threshold falls.
 */
export function contourAt(field: ClearanceField, inches: number): Segment[] {
  const level = inches / field.stepInches - 0.5;
  const segments: Segment[] = [];
  for (let row = 0; row + 1 < field.rows; row += 1) {
    for (let column = 0; column + 1 < field.columns; column += 1) {
      const pattern = patternAt(field, row, column, level);
      if (pattern !== 0 && pattern !== ALL_ABOVE) segments.push(...squareSegments(field, row, column, level, pattern));
    }
  }
  return segments;
}

/** Corners of one square of cell centres, clockwise from top-left, and the four edges between them. */
const CORNERS: [number, number][] = [[0, 0], [0, 1], [1, 1], [1, 0]];
const EDGES: [number, number][] = [[0, 1], [1, 2], [3, 2], [0, 3]];
const ALL_ABOVE = 15;

/** Which edges the line crosses for each pattern of corners above the level, bit 8 being the top-left corner. */
const CROSSINGS: [number, number][][] = [
  [], [[3, 2]], [[2, 1]], [[3, 1]], [[0, 1]], [[3, 0], [2, 1]], [[0, 2]], [[3, 0]],
  [[3, 0]], [[0, 2]], [[3, 2], [0, 1]], [[0, 1]], [[3, 1]], [[2, 1]], [[3, 2]], [],
];

function patternAt({ codes, columns }: ClearanceField, row: number, column: number, level: number): number {
  const at = row * columns + column;
  const above = (index: number, bit: number) => (codes[index] > level ? bit : 0);
  return above(at, 8) | above(at + 1, 4) | above(at + columns + 1, 2) | above(at + columns, 1);
}

function squareSegments(field: ClearanceField, row: number, column: number, level: number, pattern: number): Segment[] {
  const values = CORNERS.map(([down, across]) => field.codes[(row + down) * field.columns + column + across]);
  return CROSSINGS[pattern].map(([from, to]) => [crossing(field, row, column, values, level, from), crossing(field, row, column, values, level, to)]);
}

function crossing(field: ClearanceField, row: number, column: number, values: number[], level: number, edge: number): RoomPoint {
  const [a, b] = EDGES[edge];
  const share = (level - values[a]) / (values[b] - values[a]);
  const [downA, acrossA] = CORNERS[a];
  const [downB, acrossB] = CORNERS[b];
  const centre = (down: number, across: number) => ({ down: row + down + 0.5, across: column + across + 0.5 });
  const [start, end] = [centre(downA, acrossA), centre(downB, acrossB)];
  return roomPointOf(field, start.across + share * (end.across - start.across), start.down + share * (end.down - start.down));
}

/** The pinches worth a mark: gaps the route cannot get through at its required width, or cannot get through at all. */
export function pinchesToMark(field: ClearanceField): ClearancePinch[] {
  return field.pinches.filter((pinch) => !pinch.meets_rule);
}

/** What a pinch's mark says: its measured width, or that nothing gets through. */
export function pinchWords(pinch: ClearancePinch, bands: ClearanceBands): string {
  return pinch.inches === null ? "No way through" : formatClearWidth(pinch.inches, bands);
}
