import { SATISFYING_SCAN, SatisfyingScan } from "./batch-c/SatisfyingScan";
import { ONE_LINE_FAST, OneLineFast } from "./batch-c/oneline-fast/OneLineFast";
import { DOORKNOB_FACTS_DURATION, DoorknobFacts } from "./batch-c/doorknob/DoorknobFacts";
import type { ReelSpec } from "./registry";

export const batchC: ReelSpec[] = [
  { id: "SatisfyingScan", component: SatisfyingScan, durationInFrames: SATISFYING_SCAN.length },
  { id: "OneLineFast", component: OneLineFast, durationInFrames: ONE_LINE_FAST.length },
  { id: "DoorknobFacts", component: DoorknobFacts, durationInFrames: DOORKNOB_FACTS_DURATION },
];
