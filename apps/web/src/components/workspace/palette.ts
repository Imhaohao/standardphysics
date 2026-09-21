import type { Finding, SceneNode } from "@/types/contracts";

export const MODEL = {
  ground: "#efece5",
  floor: "#f4f2ec",
  wall: "#8e897f",
  fixture: "#e2ded5",
  movable: "#fbfaf7",
  opening: "#dbe4ef",
  ink: "#1b1c1e",
  problem: "#c8372d",
  pass: "#2e7d4f",
  accent: "#2f5e9e",
  outlet: "#e69f00",
  candidate_outlet: "#d55e00",
} as const;

export const WALL_CUT_HEIGHT = 1.2;

const KIND_COLORS: Record<string, string> = {
  outlet: MODEL.outlet,
  candidate_outlet: MODEL.candidate_outlet,
  wall: MODEL.wall,
  floor: MODEL.floor,
};

export function nodeColor(node: SceneNode): string {
  if (node.appearance?.base_color) return node.appearance.base_color;
  const byKind = KIND_COLORS[node.kind];
  if (byKind) return byKind;
  if (node.kind !== "object") return MODEL.opening;
  return node.movable ? MODEL.movable : MODEL.fixture;
}

export function outcomeColor(outcome: Finding["outcome"]): string {
  if (outcome === "problem") return MODEL.problem;
  if (outcome === "passes") return MODEL.pass;
  return MODEL.ink;
}
