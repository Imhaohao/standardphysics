import { SATISFYING_SCAN, SatisfyingScan } from "./batch-c/SatisfyingScan";
import { ONE_LINE_FAST, OneLineFast } from "./batch-c/oneline-fast/OneLineFast";
import type { ReelSpec } from "./registry";

export const batchC: ReelSpec[] = [
  { id: "SatisfyingScan", component: SatisfyingScan, durationInFrames: SATISFYING_SCAN.length },
  { id: "OneLineFast", component: OneLineFast, durationInFrames: ONE_LINE_FAST.length },
];
