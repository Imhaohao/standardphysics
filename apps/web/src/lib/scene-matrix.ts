import { Matrix4 } from "three";
import type { Mat4 } from "@/types/contracts";

/** Z-up scene coordinates to three.js Y-up: (x, y, z) becomes (x, z, -y). */
const ZUP_TO_YUP = new Matrix4().set(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1);
const YUP_TO_ZUP = ZUP_TO_YUP.clone().invert();

export function toViewerMatrix(transform: Mat4): Matrix4 {
  const rowMajor = new Matrix4().set(...(transform.m as Parameters<Matrix4["set"]>));
  return ZUP_TO_YUP.clone().multiply(rowMajor).multiply(YUP_TO_ZUP);
}

/**
 * Where a GLB mesh belongs when the shown layout differs from the one the GLB
 * was exported from. The rigid move between the two scene transforms is
 * applied to the mesh's own world matrix, so scanned meshes and boxes both
 * follow furniture that moved, whatever their local origin.
 */
export function displayMatrix(glbWorld: Matrix4, exported: Mat4, shown: Mat4): Matrix4 {
  const move = toViewerMatrix(shown).multiply(toViewerMatrix(exported).invert());
  return move.multiply(glbWorld);
}
