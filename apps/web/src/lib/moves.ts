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
