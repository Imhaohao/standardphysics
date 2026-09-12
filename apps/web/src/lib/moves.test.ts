import { describe, expect, it } from "vitest";
import type { SceneNode } from "@/types/contracts";
import { applyMoves, moveNode, withMove } from "./moves";

const table: SceneNode = {
  id: "t", kind: "object", label: "Table", raw_category: "table", quality: "measured", movable: true,
  labeled_by: "roomplan", parent_id: null, dimensions: { x: 0.6, y: 0.6, z: 0.75 },
  transform: { m: [1, 0, 0, 2, 0, 1, 0, 2.2, 0, 0, 1, 0.375, 0, 0, 0, 1] },
};

const rounded = (values: number[]) => values.map((v) => +v.toFixed(6) + 0);

describe("moveNode", () => {
  it("translates on the floor and keeps height", () => {
    const moved = moveNode(table, { node_id: "t", delta_translation: { x: 0.127, y: -0.5, z: 0 }, delta_rotation_z_degrees: 0 });
    expect(rounded([moved.transform.m[3], moved.transform.m[7], moved.transform.m[11]])).toEqual([2.127, 1.7, 0.375]);
  });

  it("turns about the node's own centre, matching Lane C's move_node", () => {
    const moved = moveNode(table, { node_id: "t", delta_translation: { x: 0, y: 0, z: 0 }, delta_rotation_z_degrees: 90 });
    expect(rounded(moved.transform.m)).toEqual([0, -1, 0, 2, 1, 0, 0, 2.2, 0, 0, 1, 0.375, 0, 0, 0, 1]);
  });
});

describe("withMove", () => {
  it("adds a drag on top of the moves so far", () => {
    const once = withMove({}, "t", 0.1, 0, 15);
    const twice = withMove(once, "t", 0.05, 0.2, 15);
    expect(twice.t.delta_translation).toEqual({ x: 0.15000000000000002, y: 0.2, z: 0 });
    expect(twice.t.delta_rotation_z_degrees).toBe(30);
  });

  it("leaves a scene with no moves untouched", () => {
    const scene = { scan_id: "s", revision: 0, base_hash: null, nodes: [table] };
    expect(applyMoves(scene, {})).toBe(scene);
  });
});
