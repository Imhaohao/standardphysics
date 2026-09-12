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
} as const;

export const WALL_CUT_HEIGHT = 1.2;

export function nodeColor(node: SceneNode): string {
  if (node.kind === "wall") return MODEL.wall;
  if (node.kind === "floor") return MODEL.floor;
  if (node.kind !== "object") return MODEL.opening;
  return node.movable ? MODEL.movable : MODEL.fixture;
}

export function outcomeColor(outcome: Finding["outcome"]): string {
  if (outcome === "problem") return MODEL.problem;
  if (outcome === "passes") return MODEL.pass;
  return MODEL.ink;
}
