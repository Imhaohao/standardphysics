"use client";

import type { ReactNode } from "react";
import { facts } from "@/lib/facts";
import { FinePrint, MaskedLines } from "../primitives";
import { ScanWipe } from "../ScanWipe";

function StageCaption({ children, source }: { children: ReactNode; source?: string }) {
  return (
    <div className="deck-gutter flex h-full flex-col items-start justify-end whitespace-nowrap">
      <h2 className="font-display text-headline font-extrabold">{children}</h2>
      {source && (
        <div className="mt-deck-hairline">
          <FinePrint delay={1.6}>{source}</FinePrint>
        </div>
      )}
    </div>
  );
}

export function ScanSlide() {
  return (
    <StageCaption>
      <ScanWipe delay={0.2} duration={1.2}>Scan your</ScanWipe>
      <ScanWipe delay={0.4} duration={1.2}>shop with</ScanWipe>
      <ScanWipe delay={0.6} duration={1.2}>an iPhone.</ScanWipe>
    </StageCaption>
  );
}

export function FindSlide() {
  return (
    <StageCaption source={facts.counterHeightInLawsuit.source}>
      <MaskedLines lines={["The counter was", `about ${facts.counterHeightInLawsuit.value} inches.`]} delay={0.9} />
    </StageCaption>
  );
}

export function FixSlide() {
  return (
    <StageCaption source={`${facts.accessibleCounterMaxHeight.source} and Advisory 904.2`}>
      <MaskedLines lines={["Move the card", "reader to the", "low counter."]} delay={0.2} />
    </StageCaption>
  );
}

export function DemoSlide() {
  return (
    <StageCaption>
      <MaskedLines lines={["Let’s try it."]} delay={0.5} />
    </StageCaption>
  );
}
