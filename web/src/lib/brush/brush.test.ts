import { describe, expect, it } from "vitest";
import { buildFreeSpace, clearanceAt, planAmbientRoutes, AMBIENT_CELL_PX } from "./ambient";
import { SchematicBrush } from "./brush";
import { boxesOverlap, cutPolyline, polylineLength, resample, splitDashes, type Box, type Point } from "./geometry";
import { markDuration } from "./marks";
import { Random, seededSource, smoothNoise } from "./random";
import { zoneAt } from "./sheet";
import { inchesForLength } from "./vocabulary";

const UNIT = 12;
const measure = (text: string, size: number) => text.length * size * 0.55;

function brushAt(clock: { now: number }, seed = 1) {
  return new SchematicBrush({ unit: UNIT, measureText: measure, now: () => clock.now, random: new Random(seededSource(seed)) });
}

function sweep(width: number, height: number, count = 600): Point[] {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / (count - 1)) * Math.PI * 2.6;
    return [width * 0.45 + Math.cos(angle) * width * 0.3, height * 0.45 + Math.sin(angle) * height * 0.3] as const;
  });
}

describe("geometry", () => {
  it("cuts a polyline at a pen-travel budget", () => {
    const route: Point[] = [[0, 0], [10, 0], [10, 10]];
    expect(cutPolyline(route, 15)).toEqual([[0, 0], [10, 0], [10, 5]]);
    expect(cutPolyline(route, 0)).toEqual([]);
  });

  it("splits a line into dashes that add up to the drawn share", () => {
    const dashes = splitDashes([[0, 0], [100, 0]], 6, 4);
    expect(dashes).toHaveLength(10);
    expect(dashes.reduce((sum, dash) => sum + polylineLength(dash), 0)).toBeCloseTo(60);
  });

  it("resamples without changing the length", () => {
    const route: Point[] = [[0, 0], [30, 40]];
    const dense = resample(route, 2.5);
    expect(dense.length).toBe(21);
    expect(polylineLength(dense)).toBeCloseTo(50);
  });
});

describe("random", () => {
  it("repeats the same drawing for the same seed", () => {
    const [a, b] = [new Random(seededSource(9)), new Random(seededSource(9))];
    expect(Array.from({ length: 5 }, () => a.next())).toEqual(Array.from({ length: 5 }, () => b.next()));
  });

  it("keeps smooth noise in [0, 1] and continuous", () => {
    for (let x = 0; x < 20; x += 0.37) {
      expect(smoothNoise(x)).toBeGreaterThanOrEqual(0);
      expect(smoothNoise(x)).toBeLessThanOrEqual(1);
      expect(Math.abs(smoothNoise(x + 0.001) - smoothNoise(x))).toBeLessThan(0.01);
    }
  });
});

describe("sheet scale", () => {
  it("reads dimensions in inches at six inches per grid unit", () => {
    expect(inchesForLength(UNIT * 6, UNIT)).toBe('36"');
  });

  it("names the drafting zone under the pen", () => {
    expect(zoneAt(10, 10, 800, 600)).toBe("A1");
    expect(zoneAt(799, 599, 800, 600)).toBe("F8");
  });

  it("times ink by length and text by characters", () => {
    expect(markDuration({ kind: "text", text: "abcd", x: 0, y: 0, size: 10, align: "left", baseline: "top", rotation: 0, start: 0, duration: 0 })).toBe(4 * 22 + 60);
    expect(markDuration({ kind: "speck", specks: [], start: 0, duration: 0 }, 2)).toBe(45);
  });
});

describe("SchematicBrush", () => {
  it("schedules nodes along a route to draw in one after another", () => {
    const clock = { now: 1000 };
    const brush = brushAt(clock);
    brush.draftRoute(sweep(1200, 800), 9000);
    expect(brush.activeStamps.length).toBeGreaterThan(10);
    const starts = brush.activeStamps.map((stamp) => stamp.startsAt);
    expect(starts).toEqual([...starts].sort((a, b) => a - b));
    expect(starts.at(-1)).toBeGreaterThan(clock.now + 8000);
    expect(brush.nextStartAt).toBe(starts[0]);
  });

  it("follows the pointer with a lag and bakes stamps once their pen finishes", () => {
    const clock = { now: 0 };
    const brush = brushAt(clock);
    brush.pointerDown(0, 0);
    brush.pointerMove(600, 0);
    for (let frame = 0; frame < 120; frame++) brush.tick();
    brush.pointerUp();
    expect(brush.activeStamps.length).toBeGreaterThan(3);
    clock.now = 60_000;
    expect(brush.tick().length).toBeGreaterThan(3);
    expect(brush.busy).toBe(false);
  });

  it("takes everything at once for reduced motion", () => {
    const brush = brushAt({ now: 0 });
    brush.draftRoute(sweep(900, 600), 5000);
    const count = brush.activeStamps.length;
    expect(brush.takeAll()).toHaveLength(count);
    expect(brush.busy).toBe(false);
  });
});

describe("ambient ink", () => {
  const [width, height] = [1440, 900];
  const content: Box[] = [[380, 60, 760, 140], [380, 150, 760, 620]];

  it("measures clearance as zero inside content and growing away from it", () => {
    const space = buildFreeSpace(width, height, content);
    expect(clearanceAt(space, 500, 300)).toBe(0);
    expect(clearanceAt(space, 1100, 780)).toBeGreaterThan(clearanceAt(space, 790, 300));
  });

  it("keeps routes low on the page and clear of content", () => {
    const space = buildFreeSpace(width, height, content);
    for (let seed = 1; seed < 6; seed++) {
      for (const [x, y] of planAmbientRoutes(space, { random: seededSource(seed) }).flat()) {
        expect(y).toBeGreaterThan(height * 0.5);
        const near: Box = [x - AMBIENT_CELL_PX * 2, y - AMBIENT_CELL_PX * 2, x + AMBIENT_CELL_PX * 2, y + AMBIENT_CELL_PX * 2];
        expect(content.some((box) => boxesOverlap(box, near))).toBe(false);
      }
    }
  });

  it("never records a mark that touches a keep-out", () => {
    const brush = new SchematicBrush({ unit: UNIT, measureText: measure, now: () => 0, speed: 2, random: new Random(seededSource(3)) });
    brush.setKeepOuts(content, [0, 0, width, height]);
    const space = buildFreeSpace(width, height, content);
    const routes = planAmbientRoutes(space, { random: seededSource(3) });
    expect(routes.length).toBeGreaterThan(0);
    for (const route of routes) brush.draftRoute(route, 4000);
    expect(brush.activeStamps.length).toBeGreaterThan(0);
    expect(brush.inkTouches(content)).toBe(false);
  });
});
