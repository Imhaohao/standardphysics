import { ONLY_AI_DURATION, OnlyAiIWant } from "./batch-b/OnlyAiIWant";
import type { ReelSpec } from "./registry";

export const batchB: ReelSpec[] = [{ id: "OnlyAiIWant", component: OnlyAiIWant, durationInFrames: ONLY_AI_DURATION }];
