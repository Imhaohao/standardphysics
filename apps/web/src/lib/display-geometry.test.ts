import { BoxGeometry, Matrix4 } from "three";
import { describe, expect, it } from "vitest";
import { displayScale, MIN_DISPLAY_WALL_THICKNESS, needsDisplayBoxFallback } from "./display-geometry";
import type { SceneNode } from "@/types/contracts";

const wall: SceneNode = {
  id: "wall", kind: "wall", label: "Wall", raw_category: "wall",
  dimensions: { x: 4, y: 0, z: 2.4 },
  transform: { m: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1.2, 0, 0, 0, 1] },
  quality: "measured", movable: false, labeled_by: "roomplan", parent_id: null,
};

describe("display-only wall geometry", () => {
  it("gives a zero-thickness measured wall a visible shell without rewriting its dimensions", () => {
    expect(displayScale(wall)).toEqual([4, 2.4, MIN_DISPLAY_WALL_THICKNESS]);
    expect(wall.dimensions.y).toBe(0);
  });

  it("replaces cached GLB wall geometry with a singular mesh or transform", () => {
    const box = new BoxGeometry(1, 1, 1);
    expect(needsDisplayBoxFallback(wall, box, new Matrix4().makeScale(1, 1, 0))).toBe(true);
    expect(needsDisplayBoxFallback(wall, box, new Matrix4())).toBe(false);
    box.dispose();
  });
});
