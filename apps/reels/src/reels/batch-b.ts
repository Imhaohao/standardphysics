import { IMAGINE_HATING_DURATION, ImagineHating } from "./batch-b/ImagineHating";
import { ONLY_AI_DURATION, OnlyAiIWant } from "./batch-b/OnlyAiIWant";
import { TELL_ME_DURATION, TellMeSmallBusiness } from "./batch-b/TellMeSmallBusiness";
import type { ReelSpec } from "./registry";

export const batchB: ReelSpec[] = [
  { id: "OnlyAiIWant", component: OnlyAiIWant, durationInFrames: ONLY_AI_DURATION },
  { id: "ImagineHating", component: ImagineHating, durationInFrames: IMAGINE_HATING_DURATION },
  { id: "TellMeSmallBusiness", component: TellMeSmallBusiness, durationInFrames: TELL_ME_DURATION },
];
