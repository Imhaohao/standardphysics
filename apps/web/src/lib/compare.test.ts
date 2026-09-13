import { describe, expect, it } from "vitest";
import type { SceneGraph, SceneNode } from "@/types/contracts";
import { describeMovement, interpolateLayout, movements } from "./compare";
import { moveNode } from "./moves";

const caseEast: SceneNode = {
  id: "case", kind: "object", label: "Display case", raw_category: "storage", quality: "measured", movable: true,
  labeled_by: "roomplan", parent_id: null, dimensions: { x: 2, y: 0.6, z: 0.9 },
  transform: { m: [1, 0, 0, 1.6, 0, 1, 0, 0, 0, 0, 1, 0.45, 0, 0, 0, 1] },
};
const counter: SceneNode = { ...caseEast, id: "counter", label: "Ordering counter", movable: false };
const before: SceneGraph = { scan_id: "s", revision: 0, base_hash: null, nodes: [caseEast, counter] };
const after: SceneGraph = {
  ...before,
  revision: 1,
  nodes: [moveNode(caseEast, { node_id: "case", delta_translation: { x: 0.127, y: 0, z: 0 }, delta_rotation_z_degrees: 90 }), counter],
};

describe("interpolateLayout", () => {
  it("is the before layout at 0 and the after layout at 1", () => {
    expect(interpolateLayout(before, after, 0).nodes[0].transform.m[3]).toBeCloseTo(1.6);
    expect(interpolateLayout(before, after, 1).nodes[0].transform.m[3]).toBeCloseTo(1.727);
  });

  it("is halfway along and halfway turned at 0.5", () => {
    const m = interpolateLayout(before, after, 0.5).nodes[0].transform.m;
    expect(m[3]).toBeCloseTo(1.6635);
    expect((Math.atan2(m[4], m[0]) * 180) / Math.PI).toBeCloseTo(45);
  });
});

describe("movements", () => {
  it("lists only what moved, in inches and degrees", () => {
    const found = movements(before, after);
    expect(found).toHaveLength(1);
    expect(describeMovement(found[0])).toBe("Display case moved 5 in and turned 90°");
  });
});
