import type { Mat4, NodeMove, SceneGraph, SceneNode } from "@/types/contracts";

export type MoveSet = Record<string, NodeMove>;

/** Mirrors Lane C's move_node: turn about the node's own centre, then translate on the floor. */
export function moveNode(node: SceneNode, move: NodeMove): SceneNode {
  const m = node.transform.m;
  const angle = Math.atan2(m[4], m[0]) + (move.delta_rotation_z_degrees * Math.PI) / 180;
  const [cos, sin] = [Math.cos(angle), Math.sin(angle)];
  const x = m[3] + move.delta_translation.x;
  const y = m[7] + move.delta_translation.y;
  const z = m[11] + move.delta_translation.z;
  const transform = { m: [cos, -sin, 0, x, sin, cos, 0, y, 0, 0, 1, z, 0, 0, 0, 1] } as Mat4;
  return { ...node, transform };
}

export function applyMoves(scene: SceneGraph, moves: MoveSet): SceneGraph {
  if (Object.keys(moves).length === 0) return scene;
  return { ...scene, nodes: scene.nodes.map((node) => (moves[node.id] ? moveNode(node, moves[node.id]) : node)) };
}

function sameEnvelope(node: SceneNode, next: SceneNode | undefined): next is SceneNode {
  return !!next && next.kind === node.kind && next.movable === node.movable &&
    (["x", "y", "z"] as const).every((axis) => node.dimensions[axis] === next.dimensions[axis]);
}

function floorMove(node: SceneNode, next: SceneNode): NodeMove | null {
  if (!node.movable || node.kind !== "object") return null;
  const m = node.transform.m, n = next.transform.m;
  const angle = Math.atan2(n[4], n[0]) - Math.atan2(m[4], m[0]);
  const move: NodeMove = {
    node_id: node.id,
    delta_translation: { x: n[3] - m[3], y: n[7] - m[7], z: 0 },
    delta_rotation_z_degrees: Math.atan2(Math.sin(angle), Math.cos(angle)) * 180 / Math.PI,
  };
  return moveNode(node, move).transform.m.every((value, index) => Math.abs(value - n[index]) < 1e-6) ? move : null;
}

function sameRoom(base: SceneGraph, candidate: SceneGraph): boolean {
  return base.scan_id === candidate.scan_id && base.nodes.length === candidate.nodes.length;
}

/** Recover only floor moves from a screened candidate for the existing review/save flow. */
export function candidateMoves(base: SceneGraph, candidate: SceneGraph): NodeMove[] | null {
  if (!sameRoom(base, candidate)) return null;
  const proposed = new Map(candidate.nodes.map((node) => [node.id, node]));
  if (proposed.size !== base.nodes.length) return null;
  const moves: NodeMove[] = [];
  for (const node of base.nodes) {
    const next = proposed.get(node.id);
    if (!sameEnvelope(node, next)) return null;
    if (next.transform.m.some((value) => !Number.isFinite(value))) return null;
    if (node.transform.m.every((value, index) => Math.abs(value - next.transform.m[index]) < 1e-6)) continue;
    const move = floorMove(node, next);
    if (!move) return null;
    moves.push(move);
  }
  return moves;
}

export function withMove(moves: MoveSet, nodeId: string, dx: number, dy: number, degrees: number): MoveSet {
  const current = moves[nodeId] ?? { node_id: nodeId, delta_translation: { x: 0, y: 0, z: 0 }, delta_rotation_z_degrees: 0 };
  return {
    ...moves,
    [nodeId]: {
      node_id: nodeId,
      delta_translation: { x: current.delta_translation.x + dx, y: current.delta_translation.y + dy, z: 0 },
      delta_rotation_z_degrees: (current.delta_rotation_z_degrees + degrees) % 360,
    },
  };
}

export const METERS_PER_INCH = 0.0254;
