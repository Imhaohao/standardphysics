import type { SceneGraph, SceneNode } from "@/types/contracts";

/**
 * Rooms for the layout rule tests, written the way the shared fixture in
 * packages/fixtures writes them: a centre, a size and a turn instead of a
 * sixteen-number matrix. tests/test_layout_rule_cases.py builds the same rooms
 * from the same descriptions on the server's side.
 */

export type PieceDescription = {
  id: string;
  kind: string;
  label?: string;
  raw_category?: string;
  /** The centre, in room metres. */
  at: number[];
  /** Width, depth and height, in metres. */
  size: number[];
  /** Degrees about the vertical. */
  turn?: number;
  movable?: boolean;
  /** Where the scan found the piece, when a saved layout has moved it since. */
  measured?: number[];
};

export function pieceFrom(description: PieceDescription): SceneNode {
  const radians = ((description.turn ?? 0) * Math.PI) / 180;
  const [cos, sin] = [Math.cos(radians), Math.sin(radians)];
  const [x, y, z] = description.at;
  const node: SceneNode = {
    id: description.id,
    kind: description.kind,
    label: description.label ?? description.id,
    raw_category: description.raw_category ?? description.kind,
    quality: "measured",
    movable: description.movable ?? false,
    labeled_by: "roomplan",
    parent_id: null,
    dimensions: { x: description.size[0], y: description.size[1], z: description.size[2] },
    transform: { m: [cos, -sin, 0, x, sin, cos, 0, y, 0, 0, 1, z, 0, 0, 0, 1] },
  };
  return description.measured ? { ...node, measured_position: { x: description.measured[0], y: description.measured[1], z } } : node;
}

export function roomFrom(pieces: PieceDescription[]): SceneGraph {
  return { scan_id: "layout-rules", revision: 0, base_hash: null, nodes: pieces.map(pieceFrom) };
}
