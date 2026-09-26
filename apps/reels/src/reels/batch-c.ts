import { SATISFYING_SCAN, SatisfyingScan } from "./batch-c/SatisfyingScan";
import type { ReelSpec } from "./registry";

export const batchC: ReelSpec[] = [{ id: "SatisfyingScan", component: SatisfyingScan, durationInFrames: SATISFYING_SCAN.length }];
