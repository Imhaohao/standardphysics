import type { SceneNode } from "@/types/contracts";
import {
  BLOCKING_HEIGHT, CANE_DETECTABLE, PASSABLE_KINDS, SHEET_AREA, SHEET_REACH, SHEET_THICKNESS, UNCLAIMED_SURFACE,
} from "@/types/geometry-rules";

/**
 * What a node is to the room, read the way the server reads it: a sheet that
 * makes the room (a wall, the floor, a door), or a solid standing in it, and
 * whether that solid takes up floor somebody has to get around.
 */

/** Whether the region encloses the space rather than standing in it: thin one way, broad the other two. */
export function boundsTheRoom(node: SceneNode): boolean {
  const [thinnest, middle, longest] = [node.dimensions.x, node.dimensions.y, node.dimensions.z].sort((a, b) => a - b);
  if (thinnest > SHEET_THICKNESS || middle <= SHEET_THICKNESS) return false;
  return middle * longest >= SHEET_AREA || longest >= SHEET_REACH;
}

/** How far the region reaches up and down in the room, whichever way its own frame is turned. */
function uprightExtent(node: SceneNode): number {
  const m = node.transform.m;
  const { x, y, z } = node.dimensions;
  return Math.abs(m[8]) * x + Math.abs(m[9]) * y + Math.abs(m[10]) * z;
}

/** A sheet lying down: a floor, or a ceiling over one. */
export function liesFlat(node: SceneNode): boolean {
  return boundsTheRoom(node) && uprightExtent(node) <= SHEET_THICKNESS;
}

/** A sheet standing up: a wall, or something set into one. */
export function standsUpright(node: SceneNode): boolean {
  return boundsTheRoom(node) && uprightExtent(node) > SHEET_THICKNESS;
}

/** A wall as the scan knows it: an upright sheet, or anything labelled a wall. */
export function readsAsWall(node: SceneNode): boolean {
  return standsUpright(node) || node.kind === "wall";
}

function measuredNothing(node: SceneNode): boolean {
  return Math.max(node.dimensions.x, node.dimensions.y, node.dimensions.z) <= 0;
}

/**
 * Whether the node takes up floor a customer has to get around: its top rises
 * past a quarter inch and its underside comes below 27 inches. A wall cabinet a
 * metre up and a floor mat both leave the floor free.
 */
export function blocksFloor(node: SceneNode): boolean {
  if (PASSABLE_KINDS.has(node.kind) || measuredNothing(node) || node.raw_category === UNCLAIMED_SURFACE) return false;
  const centre = node.transform.m[11];
  return centre + node.dimensions.z / 2 > BLOCKING_HEIGHT && centre - node.dimensions.z / 2 < CANE_DETECTABLE;
}
