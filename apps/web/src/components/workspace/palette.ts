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

/**
 * Where the scanned surface is cut in the overview, in metres.
 *
 * Higher than the boxes' cut, because the scan is worth looking at for the
 * shelving and signage the photos show, and lower than a ceiling, so the lid
 * closing the ceiling's holes never roofs over the room seen from above.
 */
export const SCAN_CUT_HEIGHT = 2.2;

/**
 * How a moved piece's shadow lies on the photographed room.
 *
 * `darkening` is the share of its brightness a floor loses where a piece shades
 * it. Swept over a photographed concrete floor, 0.45 read as a hole cut into the
 * photograph and 0.25 blended into the floor's own blotches; a third reads as
 * shade. A surface turned away from the light loses less (see shadowCatcher.ts).
 *
 * `penumbra` is the width of a shadow's soft edge in metres. Shop light comes
 * from wide ceiling fittings, so a crisp sunlit edge looked pasted on; ten
 * centimetres keeps a table's outline and loses the hard line.
 */
export const SHADOW = { color: "#000000", darkening: 0.35, penumbra: 0.1 } as const;

const NODE_COLORS: Record<string, string> = {
  outlet: MODEL.outlet,
  candidate_outlet: MODEL.candidate_outlet,
  wall: MODEL.wall,
  floor: MODEL.floor,
};

export function nodeColor(node: SceneNode): string {
  if (node.appearance?.base_color) return node.appearance.base_color;
  if (node.kind === "object") return node.movable ? MODEL.movable : MODEL.fixture;
  return NODE_COLORS[node.kind] ?? MODEL.opening;
}

export function outcomeColor(outcome: Finding["outcome"]): string {
  if (outcome === "problem") return MODEL.problem;
  if (outcome === "passes") return MODEL.pass;
  return MODEL.ink;
}
