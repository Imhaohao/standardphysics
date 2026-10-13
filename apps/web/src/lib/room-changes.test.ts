import { describe, expect, it } from "vitest";
import {
  BOX_EDGES, type RoomChange, type Vec3, cameraPath, changeCentre, changeReach, citedFurniture, edgePositions, formatLength,
  formatTurn, moveArc, parseCloud, percent, phoneHeight, placeOf, sentenceCase,
} from "./room-changes";

function cube(center: Vec3, half = 0.5) {
  const corners: Vec3[] = [];
  for (const z of [-1, 1]) for (const y of [-1, 1]) for (const x of [-1, 1]) {
    corners.push([center[0] + x * half, center[1] + y * half, center[2] + z * half]);
  }
  return { center, size: [2 * half, 2 * half, 2 * half] as Vec3, yaw_deg: 0, corners };
}

function change(overrides: Partial<RoomChange>): RoomChange {
  return {
    id: "c1", type: "moved", name: "armchair", detail: "white armchair", sentence: "", size: [1, 1, 1],
    size_text: "about 1.0 m by 1.0 m and 1.0 m tall", confidence: 1,
    evidence: { points: 10, old_spot: { empty_in: 20, of: 32, video: "after" }, new_spot: null },
    before: { box: cube([0, 0, 0.5]), where: "" }, after: { box: cube([3, 0, 0.5]), where: "" }, pictures: {},
    ...overrides,
  };
}

describe("parseCloud", () => {
  it("reads the five arrays end to end", () => {
    const count = 2;
    const buffer = new ArrayBuffer(count * 18);
    new Float32Array(buffer, 0, 6).set([1, 2, 3, 4, 5, 6]);
    new Uint8Array(buffer, 24).set([10, 20, 30, 40, 50, 60, 0, 1, 0, 2, 3, 0]);
    const cloud = parseCloud(buffer, count);
    expect(Array.from(cloud.positions)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(Array.from(cloud.colors)).toEqual([10, 20, 30, 40, 50, 60]);
    expect(Array.from(cloud.video)).toEqual([0, 1]);
    expect(Array.from(cloud.seen)).toEqual([0, 2]);
    expect(Array.from(cloud.change)).toEqual([3, 0]);
  });

  it("refuses a file of the wrong size", () => {
    expect(() => parseCloud(new ArrayBuffer(10), 2)).toThrow(/need 36/);
  });
});

describe("boxes", () => {
  it("joins the eight corners into twelve edges of one unit each", () => {
    const flat = edgePositions(cube([0, 0, 0]).corners);
    expect(flat).toHaveLength(BOX_EDGES.length * 6);
    for (let i = 0; i < flat.length; i += 6) {
      const length = Math.hypot(flat[i + 3] - flat[i], flat[i + 4] - flat[i + 1], flat[i + 5] - flat[i + 2]);
      expect(length).toBeCloseTo(1);
    }
  });

  it("frames a move from its midpoint and reaches both boxes", () => {
    const moved = change({});
    expect(changeCentre(moved)).toEqual([1.5, 0, 0.5]);
    expect(changeReach(moved)).toBeCloseTo(Math.hypot(2, 0.5, 0.5));
    expect(placeOf(moved).box.center).toEqual([3, 0, 0.5]);
    expect(placeOf(change({ after: null })).box.center).toEqual([0, 0, 0.5]);
    expect(() => placeOf(change({ before: null, after: null }))).toThrow();
  });
});

describe("words and numbers", () => {
  it("rounds lengths the way the sentences do", () => {
    expect(formatLength(0.43)).toBe("45 cm");
    expect(formatLength(0.99)).toBe("1.0 m");
    expect(formatLength(3.04)).toBe("3.0 m");
  });

  it("names the direction of a turn and skips small or unknown ones", () => {
    expect(formatTurn(-152)).toBe("150° clockwise, seen from above");
    expect(formatTurn(95)).toBe("90° counterclockwise, seen from above");
    expect(formatTurn(10)).toBeNull();
    expect(formatTurn(null)).toBeNull();
    expect(sentenceCase("bamboo basket")).toBe("Bamboo basket");
    expect(percent(0.966)).toBe("97%");
  });
});

describe("paths", () => {
  it("orders each video's cameras by time", () => {
    const camera = (video: "before" | "after", time_s: number, x: number) => ({
      video, frame: 0, time_s, position: [x, 0, 1.5] as Vec3, rotation: [1, 0, 0, 0, 1, 0, 0, 0, 1], fov_y_deg: 50, aspect: 1.3,
    });
    const cameras = [camera("before", 2, 2), camera("after", 0, 9), camera("before", 1, 1)];
    expect(cameraPath(cameras, "before").map((p) => p[0])).toEqual([1, 2]);
    expect(phoneHeight(cameras)).toBe(1.5);
    expect(phoneHeight([])).toBe(0);
  });

  it("arcs above both ends of a move and lands on them", () => {
    const arc = moveArc([0, 0, 1], [2, 0, 1]);
    expect(arc[0]).toEqual([0, 0, 1]);
    expect(arc[arc.length - 1]).toEqual([2, 0, 1]);
    expect(Math.max(...arc.map((p) => p[2]))).toBeGreaterThan(1.2);
  });
});

describe("citedFurniture", () => {
  it("labels only furniture a sentence places a change against", () => {
    const box = { center: [0, 0, 0], size: [1, 1, 1], yaw_deg: 0, corners: [] };
    const scene = {
      changes: [{ sentence: "A basket appeared on the coffee table." }],
      furniture: [{ name: "coffee table", box }, { name: "white plastic chair", box }],
    } as unknown as Parameters<typeof citedFurniture>[0];
    expect(citedFurniture(scene).map((piece) => piece.name)).toEqual(["coffee table"]);
  });
});
