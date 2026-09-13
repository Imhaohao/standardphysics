"use client";

import { motion, type MotionValue } from "motion/react";
import { useEffect, useRef } from "react";
import { facts } from "@/lib/facts";
import { CountFromProgress, FinePrint, MaskedLines, fadeReveal, useProgress } from "../primitives";

const lawsuitCount = facts.adaLawsuitsFiled2025.value;
const FILL_SECONDS = 2.8;
const FILL_DELAY = 0.35;
const DOT_GROWTH_WINDOW = 0.06;

type Dot = { x: number; y: number; threshold: number };

function layoutDots(width: number, height: number): { dots: Dot[]; radius: number } {
  const columns = Math.ceil(Math.sqrt((lawsuitCount * width) / height));
  const rows = Math.ceil(lawsuitCount / columns);
  const pitch = Math.min(width / columns, height / rows);
  const dots = Array.from({ length: lawsuitCount }, (_, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const diagonal = (column / columns) * 0.55 + (row / rows) * 0.45;
    const scatter = Math.sin(index * 12.9898) * 43758.5453;
    const noise = scatter - Math.floor(scatter);
    return {
      x: (column + 0.5) * pitch,
      y: (row + 0.5) * pitch,
      threshold: (diagonal * 0.82 + noise * 0.18) * (1 - DOT_GROWTH_WINDOW),
    };
  });
  return { dots, radius: pitch * 0.36 };
}

function drawDots(context: CanvasRenderingContext2D, dots: Dot[], radius: number, progress: number) {
  context.beginPath();
  for (const dot of dots) {
    const grown = Math.min(Math.max((progress - dot.threshold) / DOT_GROWTH_WINDOW, 0), 1);
    if (grown <= 0) continue;
    const overshoot = 1 + Math.sin(grown * Math.PI) * 0.45;
    const dotRadius = radius * grown * overshoot;
    context.moveTo(dot.x + dotRadius, dot.y);
    context.arc(dot.x, dot.y, dotRadius, 0, Math.PI * 2);
  }
  context.fill();
}

function DotField({ progress }: { progress: MotionValue<number> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const ink = getComputedStyle(canvas).color;
    let layout = layoutDots(1, 1);

    function resize() {
      if (!canvas || !context) return;
      const ratio = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      layout = layoutDots(width, height);
      render(progress.get());
    }

    function render(value: number) {
      if (!canvas || !context) return;
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = ink;
      drawDots(context, layout.dots, layout.radius, value);
    }

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    const unsubscribe = progress.on("change", render);
    return () => {
      observer.disconnect();
      unsubscribe();
    };
  }, [progress]);

  return <canvas ref={canvasRef} aria-hidden className="size-full text-ink" />;
}

export function LawsuitsSlide() {
  const progress = useProgress(FILL_SECONDS, FILL_DELAY, [0.33, 0, 0.2, 1]);

  return (
    <div className="deck-gutter relative grid h-full grid-cols-[1fr_1.15fr] grid-rows-[auto_1fr_auto] gap-x-deck-gap">
      <div className="col-start-1 row-start-1">
        <p className="font-display text-poster font-extrabold figures-tabular">
          <span className="line-mask">
            <motion.span className="block" variants={fadeReveal(0.1, 30)}>
              <CountFromProgress progress={progress} total={lawsuitCount} />
            </motion.span>
          </span>
        </p>
        <p className="mt-deck-rise font-display text-lede font-bold">
          <MaskedLines lines={["ADA lawsuits filed", "in federal court in 2025"]} delay={0.5} />
        </p>
      </div>
      <motion.div className="col-start-2 row-span-3 row-start-1 min-h-0" variants={fadeReveal(0)}>
        <DotField progress={progress} />
      </motion.div>
      <div className="col-start-1 row-start-3 self-end">
        <FinePrint delay={1.4}>{facts.adaLawsuitsFiled2025.source}</FinePrint>
      </div>
    </div>
  );
}
