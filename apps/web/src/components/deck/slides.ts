import type { ComponentType } from "react";
import type { ShotName } from "@/components/shop/shots";
import { LawsuitsSlide } from "./slides/LawsuitsSlide";
import { MissionSlide } from "./slides/MissionSlide";
import { PayoutsSlide } from "./slides/PayoutsSlide";
import { ReceiptSlide } from "./slides/ReceiptSlide";
import { RulebookSlide } from "./slides/RulebookSlide";
import { DemoSlide, FindSlide, FixSlide, ScanSlide } from "./slides/StageSlides";
import { SuedSlide } from "./slides/SuedSlide";
import { TitleSlide } from "./slides/TitleSlide";

export type SlideLayer = "behindStage" | "overStage";

export type SlideDefinition = {
  id: string;
  shot: ShotName;
  layer: SlideLayer;
  Content: ComponentType;
};

export const slides: SlideDefinition[] = [
  { id: "title", shot: "cloud", layer: "behindStage", Content: TitleSlide },
  { id: "sued", shot: "awayBeforeScan", layer: "overStage", Content: SuedSlide },
  { id: "receipt", shot: "awayBeforeScan", layer: "overStage", Content: ReceiptSlide },
  { id: "lawsuits", shot: "awayBeforeScan", layer: "overStage", Content: LawsuitsSlide },
  { id: "rulebook", shot: "awayBeforeScan", layer: "overStage", Content: RulebookSlide },
  { id: "mission", shot: "awayBeforeScan", layer: "overStage", Content: MissionSlide },
  { id: "scan", shot: "scan", layer: "overStage", Content: ScanSlide },
  { id: "find", shot: "counter", layer: "overStage", Content: FindSlide },
  { id: "fix", shot: "counterFixed", layer: "overStage", Content: FixSlide },
  { id: "payouts", shot: "awayAfterFix", layer: "overStage", Content: PayoutsSlide },
  { id: "demo", shot: "route", layer: "overStage", Content: DemoSlide },
];
