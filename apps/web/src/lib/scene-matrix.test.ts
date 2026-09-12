import { Matrix4, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import type { Mat4 } from "@/types/contracts";
import { displayMatrix, toViewerMatrix } from "./scene-matrix";

const translation = (x: number, y: number, z: number): Mat4 => ({ m: [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1] });

function rotationZ(degrees: number, x = 0, y = 0): Mat4 {
  const r = (degrees * Math.PI) / 180;
  const [c, s] = [Math.cos(r), Math.sin(r)];
  return { m: [c, -s, 0, x, s, c, 0, y, 0, 0, 1, 0, 0, 0, 0, 1] };
}

const position = (matrix: Matrix4) => new Vector3().setFromMatrixPosition(matrix).toArray().map((v) => +v.toFixed(6) + 0);

describe("toViewerMatrix", () => {
  it("places a scene position the way Blender's glTF export does", () => {
    expect(position(toViewerMatrix(translation(2, 2.4, 0.375)))).toEqual([2, 0.375, -2.4]);
  });

  it("turns a rotation about scene Z into a rotation about three.js Y", () => {
    const east = new Vector3(1, 0, 0).applyMatrix4(toViewerMatrix(rotationZ(90)));
    expect(east.toArray().map((v) => +v.toFixed(6) + 0)).toEqual([0, 0, -1]);
  });
});

describe("displayMatrix", () => {
  it("leaves a mesh where the GLB put it when nothing moved", () => {
    const glbWorld = new Matrix4().makeTranslation(1, 2, 3);
    const shown = displayMatrix(glbWorld, translation(1, -3, 2), translation(1, -3, 2));
    expect(position(shown)).toEqual([1, 2, 3]);
  });

  it("carries a moved node's mesh by the same move", () => {
    const glbWorld = toViewerMatrix(translation(2, 0, 0.45));
    const shown = displayMatrix(glbWorld, translation(2, 0, 0.45), translation(2.127, 0, 0.45));
    expect(position(shown)).toEqual([2.127, 0.45, 0]);
  });

  it("turns a mesh about its node's centre, not the world origin", () => {
    const glbWorld = toViewerMatrix(translation(3, 1, 0));
    const shown = displayMatrix(glbWorld, translation(3, 1, 0), rotationZ(90, 3, 1));
    expect(position(shown)).toEqual([3, 0, -1]);
  });
});
