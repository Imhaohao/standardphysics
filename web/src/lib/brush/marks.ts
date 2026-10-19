import { polylineLength, resample, TAU, type Point } from "./geometry";
import type { Random } from "./random";

export const PEN_SPEED_PX_PER_MS = 0.7;
export const TYPING_MS_PER_CHARACTER = 22;
export const LABEL_SCALE = 1.5;

export const LINE_WEIGHT = { heavy: 2.3, regular: 1.25, cable: 1, thin: 0.7 } as const;
export type LineWeight = keyof typeof LINE_WEIGHT;

/** How wet the ink is. Every number here was tuned by eye against the original p5 brush. */
export const INK = {
  resampleSpacing: 2.5,
  raggedness: 1.3,
  bleedReach: 3.8,
  bleedAlpha: 0.16,
  fiberChance: 0.22,
  grainChance: 0.45,
  bodyAlpha: 0.96,
  poolChance: 0.85,
  blobChance: 0.45,
  dripChance: 0.35,
  speckChance: 0.7,
} as const;

export type TextAlign = "left" | "center" | "right";
export type TextBaseline = "top" | "middle" | "bottom";

export interface InkBlob {
  index: number;
  size: number;
  drip: number;
}

export interface InkRun {
  points: Point[];
  length: number;
  seed: number;
  pooled: boolean;
  blobs: InkBlob[];
}

interface Scheduled {
  start: number;
  duration: number;
}

export interface InkMark extends Scheduled {
  kind: "ink";
  runs: InkRun[];
  weight: number;
  length: number;
  fillPolygon: Point[] | null;
  color?: string;
}

export interface TextMark extends Scheduled {
  kind: "text";
  text: string;
  x: number;
  y: number;
  size: number;
  align: TextAlign;
  baseline: TextBaseline;
  rotation: number;
  color?: string;
}

export interface Speck {
  x: number;
  y: number;
  radius: number;
  alpha: number;
}

export interface SpeckMark extends Scheduled {
  kind: "speck";
  specks: Speck[];
}

export interface BlotMark extends Scheduled {
  kind: "blot";
  points: Point[];
  cx: number;
  cy: number;
  color?: string;
}

/** Lifts ink back off the paper inside a polygon, for example to cut a doorway out of a wall already drawn. */
export interface EraseMark extends Scheduled {
  kind: "erase";
  points: Point[];
}

export type Mark = InkMark | TextMark | SpeckMark | BlotMark | EraseMark;

/** A group of marks drawn as one gesture, scheduled on the shared pen clock. */
export interface Stamp {
  marks: Mark[];
  startsAt: number;
  endsAt: number;
}

function createBlobs(rng: Random, pointCount: number, length: number, unit: number): InkBlob[] {
  if (length <= unit * 3 || !rng.chance(INK.blobChance)) return [];
  return Array.from({ length: rng.int(1, 3) }, () => ({
    index: rng.int(2, pointCount - 2),
    size: rng.float(2.2, 3.8),
    drip: rng.chance(INK.dripChance) ? rng.float(unit * 0.8, unit * 3) : 0,
  }));
}

export function createRun(rng: Random, rawPoints: readonly Point[], unit: number): InkRun {
  const points = resample(rawPoints, INK.resampleSpacing);
  const length = polylineLength(points);
  return {
    points,
    length,
    seed: rng.float(0, 1000),
    pooled: length > unit * 1.5 && rng.chance(INK.poolChance),
    blobs: createBlobs(rng, points.length, length, unit),
  };
}

export function specksAround(rng: Random, origin: Point, unit: number): SpeckMark {
  const specks = Array.from({ length: rng.int(6, 16) }, () => {
    const angle = rng.float(0, TAU);
    const reach = rng.float(unit * 0.4, unit * 3.5);
    return {
      x: origin[0] + Math.cos(angle) * reach,
      y: origin[1] + Math.sin(angle) * reach,
      radius: rng.float(0.4, 2),
      alpha: rng.float(0.47, 0.94),
    };
  });
  return { kind: "speck", specks, start: 0, duration: 0 };
}

const UNSCALED_DURATION: { [K in Mark["kind"]]: (mark: Extract<Mark, { kind: K }>) => number } = {
  ink: (mark) => Math.max(80, mark.length / PEN_SPEED_PX_PER_MS),
  text: (mark) => mark.text.length * TYPING_MS_PER_CHARACTER + 60,
  speck: () => 90,
  blot: () => 140,
  erase: () => 60,
};

export function markDuration(mark: Mark, speed = 1) {
  const duration = UNSCALED_DURATION[mark.kind] as (mark: Mark) => number;
  return duration(mark) / speed;
}
