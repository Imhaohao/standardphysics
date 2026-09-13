"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import type { ReactNode } from "react";
import { ShopStage } from "@/components/shop/ShopStage";
import { slides, type SlideLayer } from "./slides";
import { useDeckNavigation } from "./useDeckNavigation";
import { useFullscreenShortcut, useIdleCursor } from "./usePresenterChrome";

const layerClassName: Record<SlideLayer, string> = {
  behindStage: "z-0",
  overStage: "z-20",
};

function SlideFrame({ layer, label, children }: { layer: SlideLayer; label: string; children: ReactNode }) {
  return (
    <motion.section
      aria-label={label}
      className={`absolute inset-0 ${layerClassName[layer]}`}
      initial="enter"
      animate="present"
      exit="exit"
    >
      {children}
    </motion.section>
  );
}

export function Deck() {
  const { index, handlePointerDown, handlePointerUp, handleContextMenu } = useDeckNavigation(slides.length);
  const cursorIsIdle = useIdleCursor();
  useFullscreenShortcut();

  const slide = slides[index];

  return (
    <MotionConfig reducedMotion="user">
      <main
        className={`fixed inset-0 overflow-hidden bg-paper text-ink select-none ${cursorIsIdle ? "cursor-none" : "cursor-default"}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onContextMenu={handleContextMenu}
      >
        <ShopStage shot={slide.shot} />
        <AnimatePresence>
          <SlideFrame key={slide.id} layer={slide.layer} label={`Slide ${index + 1} of ${slides.length}`}>
            <slide.Content />
          </SlideFrame>
        </AnimatePresence>
        <div aria-hidden className="paper-grain pointer-events-none absolute inset-0 z-30" />
      </main>
    </MotionConfig>
  );
}
