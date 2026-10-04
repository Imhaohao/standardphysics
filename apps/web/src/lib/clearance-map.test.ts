import { describe, expect, it } from "vitest";
import type { ClearanceMap, ClearancePinch } from "@/types/contracts";
import {
  type ClearanceField, contourAt, decodeClearance, type FillPalette, formatClearWidth, over, paintFills, paintScale,
  pinchesToMark, pinchWords, roomPointOf, sampleCode,
} from "./clearance-map";

const BANDS = { reduced_inches: 32, route_inches: 36, reduced_run_inches: 24, turning_inches: 60 };

/** The 12 by 10 cell room the server's `widths_png` wrote in grey-png.test.ts, with walls all round and a box inside. */
const SERVER_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAwAAAAKCAAAAAClR+AmAAAAOUlEQVR42m3MOQ7AMBQC0Wfy739iLykcWS5CNWIQXGmew6Ooj7tCG5Nk12sOhNwHhZYt9iw5pvvNC42dCRzkA/eYAAAAAElFTkSuQmCC";

function pinch(overrides: Partial<ClearancePinch>): ClearancePinch {
  return {
    finding_id: "f", point: { x: 0, y: 0, z: 0 }, inches: 31, meets_rule: false, origin: "Entrance", destination: "Counter",
    blocking_node_ids: [], ...overrides,
  };
}

function map(overrides: Partial<ClearanceMap> = {}): ClearanceMap {
  return {
    sequence: 1, graph_hash: "h", origin: { x: -1, y: 2, z: 0 }, cell_meters: 0.025, columns: 12, rows: 10,
    rotation_z_degrees: 0, widths_png: SERVER_PNG, width_step_inches: 0.5, bands: BANDS, pinches: [], ...overrides,
  };
}

function field(rows: number[][], overrides: Partial<ClearanceField> = {}): ClearanceField {
  return {
    columns: rows[0].length, rows: rows.length, cellMeters: 1, origin: { x: 0, y: 0 }, rotationDegrees: 0, stepInches: 0.5,
    codes: Uint8Array.from(rows.flat()), bands: BANDS, pinches: [], ...overrides,
  };
}

describe("formatClearWidth", () => {
  it("shows a width as the rest of the app does when that keeps it in its band", () => {
    expect([19.189, 30.999999999999996, 36, 36.04, 44.26].map((inches) => formatClearWidth(inches, BANDS))).toEqual(
      ["19.2 in", "31 in", "36 in", "36 in", "44.3 in"],
    );
  });

  it("keeps the digits that separate a width from a band edge it falls just short of", () => {
    expect([35.98, 35.95, 31.97, 59.99].map((inches) => formatClearWidth(inches, BANDS))).toEqual(
      ["35.98 in", "35.95 in", "31.97 in", "59.99 in"],
    );
  });

  it("counts a width within the checks' slack of an edge as meeting it", () => {
    expect(formatClearWidth(35.9999999999, BANDS)).toBe("36 in");
  });

  it("never shows a width that misses an edge at or past that edge", () => {
    for (let hundredths = 2900; hundredths < 6200; hundredths += 1) {
      const inches = hundredths / 100;
      const shown = Number.parseFloat(formatClearWidth(inches, BANDS));
      for (const edge of [32, 36, 60]) {
        if (inches < edge - 1e-6) expect(shown).toBeLessThan(edge);
      }
    }
  });
});

describe("decodeClearance", () => {
  it("reads the server's picture into one code a cell, top row first, with where the grid sits", async () => {
    const decoded = await decodeClearance(map({ pinches: [pinch({})] }));
    expect([decoded.columns, decoded.rows, decoded.stepInches, decoded.origin]).toEqual([12, 10, 0.5, { x: -1, y: 2 }]);
    expect(Array.from(decoded.codes.subarray(12 * 3, 12 * 4))).toEqual([0, 3, 7, 8, 5, 3, 3, 3, 5, 7, 3, 0]);
    expect(decoded.pinches).toHaveLength(1);
  });

  it("refuses a picture that is not the size of the grid it claims to describe", async () => {
    await expect(decodeClearance(map({ columns: 13 }))).rejects.toThrow("not the size of its grid");
  });
});

describe("paintFills", () => {
  const palette: FillPalette = { reduced: [200, 120, 0, 140], route: [40, 120, 80, 60], turning: [30, 110, 70, 120] };
  const clear = [40, 120, 80, 0];
  const pixelsOf = (pixels: Uint8ClampedArray) => Array.from({ length: pixels.length / 4 }, (_, at) => Array.from(pixels.subarray(at * 4, at * 4 + 4)));

  it("paints each cell its band's colour at the rule pack's widths, and leaves blocked and too-tight cells clear", () => {
    const halfInches = [[0, 63, 64, 71], [72, 119, 120, 255]];
    const pixels = pixelsOf(paintFills(field(halfInches), palette));
    expect(pixels).toEqual([clear, clear, palette.reduced, palette.reduced, palette.route, palette.route, palette.turning, palette.turning]);
  });

  it("keeps the route band's colour in clear pixels, so blending one into a band never darkens its edge", () => {
    expect(pixelsOf(paintFills(field([[0]]), palette))[0].slice(0, 3)).toEqual(palette.route.slice(0, 3));
  });

  it("places band edges between cell centres when painting two pixels a cell", () => {
    const pixels = pixelsOf(paintFills(field([[60, 80]]), palette, 2));
    expect(pixels.slice(0, 4)).toEqual([clear, palette.reduced, palette.route, palette.route]);
  });
});

describe("over", () => {
  it("lays a band's tint over the ground the way a browser composites them", () => {
    expect(over([46, 125, 79, 51], [252, 251, 248, 189])).toEqual([200, 219, 205, 202]);
    expect(over([46, 125, 79, 255], [252, 251, 248, 189])).toEqual([46, 125, 79, 255]);
    expect(over([46, 125, 79, 0], [252, 251, 248, 0])).toEqual([46, 125, 79, 0]);
  });
});

describe("sampleCode", () => {
  it("blends the four cell centres around a point and holds the edge cells' value past the edge", () => {
    const grid = field([[0, 100], [50, 150]]);
    expect(sampleCode(grid, 0.5, 0.5)).toBe(75);
    expect(sampleCode(grid, -0.25, 0)).toBe(0);
    expect(sampleCode(grid, 1.25, 1.25)).toBe(150);
  });
});

describe("paintScale", () => {
  it("paints two pixels a cell for a shop-sized grid and one for a grid too big to paint that finely", () => {
    expect(paintScale(field([[0]], { columns: 360, rows: 440 }))).toBe(2);
    expect(paintScale(field([[0]], { columns: 1200, rows: 900 }))).toBe(1);
  });
});

describe("roomPointOf", () => {
  it("puts the picture's top-left corner at the grid's highest y, since the picture reads as a plan", () => {
    const grid = field([[0, 0, 0], [0, 0, 0]], { origin: { x: 1, y: 2 } });
    expect(roomPointOf(grid, 0, 0)).toEqual({ x: 1, y: 4 });
    expect(roomPointOf(grid, 3, 2)).toEqual({ x: 4, y: 2 });
  });

  it("turns the grid about its origin when the server says it is turned", () => {
    const turned = roomPointOf(field([[0, 0, 0]], { rotationDegrees: 90 }), 3, 1);
    expect(turned.x).toBeCloseTo(0);
    expect(turned.y).toBeCloseTo(3);
  });
});

describe("contourAt", () => {
  it("traces the edge of the floor a 32 inch route fits, between the last cell too tight and the first wide enough", () => {
    const step = [0, 0, 80, 80];
    const segments = contourAt(field([step, step, step, step]), 32);
    const xs = segments.flatMap(([a, b]) => [a.x, b.x]);
    const crossing = 1.5 + (32 / 0.5 - 0.5) / 80;
    expect(xs.every((x) => Math.abs(x - crossing) < 1e-9)).toBe(true);
    const length = segments.reduce((sum, [a, b]) => sum + Math.hypot(b.x - a.x, b.y - a.y), 0);
    expect(length).toBeCloseTo(3);
  });

  it("draws nothing across a floor that is all one side of the line", () => {
    expect(contourAt(field([[90, 90], [90, 90]]), 32)).toEqual([]);
    expect(contourAt(field([[10, 10], [10, 10]]), 32)).toEqual([]);
  });

  it("closes a loop round a pillar standing in open floor", () => {
    const rows = Array.from({ length: 7 }, (_, row) => Array.from({ length: 7 }, (_, column) => (row === 3 && column === 3 ? 0 : 100)));
    const segments = contourAt(field(rows), 32);
    const ends = segments.flatMap(([a, b]) => [a, b]).map(({ x, y }) => `${x.toFixed(6)},${y.toFixed(6)}`);
    const counts = new Map<string, number>();
    ends.forEach((end) => counts.set(end, (counts.get(end) ?? 0) + 1));
    expect(segments.length).toBeGreaterThanOrEqual(4);
    expect([...counts.values()].every((count) => count === 2)).toBe(true);
  });
});

describe("the pinches the map marks", () => {
  it("are the gaps the route fails, with their width, or the stop nothing reaches", () => {
    const failing = pinch({ inches: 35.98 });
    const sealed = pinch({ finding_id: "sealed", inches: null });
    const fine = pinch({ finding_id: "fine", inches: 75, meets_rule: true });
    const marked = pinchesToMark(field([[0]], { pinches: [failing, sealed, fine] }));
    expect(marked.map((each) => pinchWords(each, BANDS))).toEqual(["35.98 in", "No way through"]);
  });
});
