import type { Mat4, SceneGraph, SceneNode } from "@/types/contracts";
import { formatInches } from "./findings";
import { METERS_PER_INCH } from "./moves";

function angleOf(transform: Mat4): number {
  return Math.atan2(transform.m[4], transform.m[0]);
}

function shortestTurn(from: number, to: number): number {
  return Math.atan2(Math.sin(to - from), Math.cos(to - from));
}

function between(a: SceneNode, b: SceneNode, t: number): SceneNode {
  const [ma, mb] = [a.transform.m, b.transform.m];
  const angle = angleOf(a.transform) + shortestTurn(angleOf(a.transform), angleOf(b.transform)) * t;
  const [cos, sin] = [Math.cos(angle), Math.sin(angle)];
  const at = (index: number) => ma[index] + (mb[index] - ma[index]) * t;
  return { ...b, transform: { m: [cos, -sin, 0, at(3), sin, cos, 0, at(7), 0, 0, 1, at(11), 0, 0, 0, 1] } as Mat4 };
}

/** The shop partway from one layout to another. t = 0 is before, 1 is after. */
export function interpolateLayout(before: SceneGraph, after: SceneGraph, t: number): SceneGraph {
  const earlier = new Map(before.nodes.map((node) => [node.id, node]));
  return {
    ...after,
    nodes: after.nodes.map((node) => {
      const start = earlier.get(node.id);
      return start ? between(start, node, t) : node;
    }),
  };
}

export type Movement = { nodeId: string; label: string; inches: number; degrees: number };

export function movements(before: SceneGraph, after: SceneGraph): Movement[] {
  const earlier = new Map(before.nodes.map((node) => [node.id, node]));
  return after.nodes.flatMap((node) => {
    const start = earlier.get(node.id);
    if (!start) return [];
    const meters = Math.hypot(node.transform.m[3] - start.transform.m[3], node.transform.m[7] - start.transform.m[7]);
    const degrees = (shortestTurn(angleOf(start.transform), angleOf(node.transform)) * 180) / Math.PI;
    const inches = meters / METERS_PER_INCH;
    if (inches < 0.25 && Math.abs(degrees) < 0.5) return [];
    return [{ nodeId: node.id, label: node.label, inches, degrees }];
  });
}

export function describeMovement(movement: Movement): string {
  const parts: string[] = [];
  if (movement.inches >= 0.25) parts.push(`moved ${formatInches(movement.inches)}`);
  if (Math.abs(movement.degrees) >= 0.5) parts.push(`turned ${Math.round(Math.abs(movement.degrees))}°`);
  return `${movement.label} ${parts.join(" and ")}`;
}
