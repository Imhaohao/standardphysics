import { Matrix4, Vector3, type BufferGeometry } from "three";
import type { SceneNode } from "@/types/contracts";

export const MIN_DISPLAY_WALL_THICKNESS = 0.08;
const SINGULAR_SCALE = 0.000001;

/** Rendering keeps a visible wall shell without changing the measured graph. */
export function displayScale(node: SceneNode): [number, number, number] {
  const depth = node.kind === "wall" ? Math.max(node.dimensions.y, MIN_DISPLAY_WALL_THICKNESS) : node.dimensions.y;
  return [node.dimensions.x, node.dimensions.z, depth];
}

/** Cached GLBs made with a zero scale cannot be repaired by a transform alone. */
export function needsDisplayBoxFallback(node: SceneNode, geometry: BufferGeometry, matrix: Matrix4): boolean {
  if (node.kind !== "wall") return false;
  geometry.computeBoundingBox();
  const size = geometry.boundingBox?.getSize(new Vector3());
  if (!size || Math.min(size.x, size.y, size.z) <= SINGULAR_SCALE) return true;
  const elements = matrix.elements;
  const axisLengths = [
    Math.hypot(elements[0], elements[1], elements[2]),
    Math.hypot(elements[4], elements[5], elements[6]),
    Math.hypot(elements[8], elements[9], elements[10]),
  ];
  return Math.min(...axisLengths) <= SINGULAR_SCALE;
}
