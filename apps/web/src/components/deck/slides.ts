import type { ComponentType } from "react";
import type { ShotName } from "@/components/shop/shots";
import { BoomersSlide, PivotSlide } from "./slides/CustomerSlides";
import { LoopSlide } from "./slides/LoopSlide";
import { MissionSlide } from "./slides/MissionSlide";
import { PipelineSlide } from "./slides/PipelineSlide";
import { ModelSlide } from "./slides/ModelSlide";
import { PayoutsSlide } from "./slides/PayoutsSlide";
import { PlannerSlide } from "./slides/PlannerSlide";
import { RulebookSlide } from "./slides/RulebookSlide";
import { SaraSlide } from "./slides/SaraSlide";
import { StretchedSlide } from "./slides/StretchedSlide";
import { FindSlide, FixSlide, ScanSlide } from "./slides/StageSlides";
import { ClosingSlide, TitleSlide } from "./slides/TitleSlide";

export type SlideLayer = "behindStage" | "overStage";

export type SlideProps = { step: number; direction: 1 | -1; advance: () => void };

export type SlideDefinition = {
  id: string;
  shot: ShotName;
  layer: SlideLayer;
  steps?: number;
  Content: ComponentType<SlideProps>;
};

export const slides: SlideDefinition[] = [
  { id: "title", shot: "cloud", layer: "behindStage", Content: TitleSlide },
  { id: "sara", shot: "awayBeforeScan", layer: "overStage", steps: 4, Content: SaraSlide },
  { id: "payouts", shot: "awayBeforeScan", layer: "overStage", steps: 2, Content: PayoutsSlide },
  { id: "rulebook", shot: "awayBeforeScan", layer: "overStage", Content: RulebookSlide },
  { id: "stretched", shot: "awayBeforeScan", layer: "overStage", steps: 2, Content: StretchedSlide },
  { id: "mission", shot: "awayBeforeScan", layer: "overStage", Content: MissionSlide },
  { id: "scan", shot: "scan", layer: "overStage", Content: ScanSlide },
  { id: "pipeline", shot: "scan", layer: "overStage", Content: PipelineSlide },
  { id: "find", shot: "counter", layer: "overStage", Content: FindSlide },
  { id: "fix", shot: "counterFixed", layer: "overStage", Content: FixSlide },
  { id: "loop", shot: "awayAfterFix", layer: "overStage", steps: 3, Content: LoopSlide },
  { id: "pivot", shot: "awayAfterFix", layer: "overStage", Content: PivotSlide },
  { id: "boomers", shot: "awayAfterFix", layer: "overStage", steps: 3, Content: BoomersSlide },
  { id: "model", shot: "awayAfterFix", layer: "overStage", Content: ModelSlide },
  { id: "planner", shot: "awayAfterFix", layer: "overStage", steps: 2, Content: PlannerSlide },
  { id: "closing", shot: "cloud", layer: "overStage", Content: ClosingSlide },
];
