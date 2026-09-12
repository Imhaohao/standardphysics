import { describe, expect, it } from "vitest";
import { toViewer } from "./coordinates";

describe("toViewer", () => {
  it("puts the scene's up axis on three.js's up axis", () => {
    expect(toViewer({ x: 0, y: 0, z: 2 })).toEqual([0, 2, -0]);
  });

  it("keeps east as +x", () => {
    expect(toViewer({ x: 3, y: 0, z: 0 })).toEqual([3, 0, -0]);
  });

  it("sends the scene's north (+y) to three.js's -z, matching Blender's glTF export", () => {
    expect(toViewer({ x: 0, y: 4, z: 0 })).toEqual([0, 0, -4]);
  });
});
