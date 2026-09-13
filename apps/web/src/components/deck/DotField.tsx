"use client";

import type { MotionValue } from "motion/react";
import { useEffect, useRef } from "react";

const DOT_GROWTH_WINDOW = 0.06;

type Dot = { x: number; y: number; threshold: number };
type FieldLayout = { dots: Dot[]; radius: number; highlighted: Dot | null };
export type FieldOrigin = { x: number; y: number };

function noiseAt(index: number) {
  const scatter = Math.sin(index * 12.9898) * 43758.5453;
  return scatter - Math.floor(scatter);
}

function layoutDots(count: number, width: number, height: number, origin: FieldOrigin): FieldLayout {
  const columns = Math.ceil(Math.sqrt((count * width) / height));
  const rows = Math.ceil(count / columns);
  const pitch = Math.min(width / columns, height / rows);
  const offset = { x: (width - columns * pitch) / 2, y: (height - rows * pitch) / 2 };
  const center = { x: origin.x * width, y: origin.y * height };
  const farthest = Math.hypot(Math.max(center.x, width - center.x), Math.max(center.y, height - center.y));

  let highlighted: Dot | null = null;
  let closest = Number.POSITIVE_INFINITY;
  const dots = Array.from({ length: count }, (_, index) => {
    const x = offset.x + ((index % columns) + 0.5) * pitch;
    const y = offset.y + (Math.floor(index / columns) + 0.5) * pitch;
    const distance = Math.hypot(x - center.x, y - center.y);
    const dot = { x, y, threshold: ((distance / farthest) * 0.85 + noiseAt(index) * 0.15) * (1 - DOT_GROWTH_WINDOW) };
    if (distance < closest) {
      closest = distance;
      highlighted = dot;
    }
    return dot;
  });
  return { dots, radius: pitch * 0.36, highlighted };
}

function grownRadius(dot: Dot, radius: number, progress: number) {
  const grown = Math.min(Math.max((progress - dot.threshold) / DOT_GROWTH_WINDOW, 0), 1);
  return radius * grown * (1 + Math.sin(grown * Math.PI) * 0.45);
}

function drawDots(context: CanvasRenderingContext2D, layout: FieldLayout, progress: number, colors: { ink: string; tape: string }, showHighlight: boolean) {
  context.fillStyle = colors.ink;
  context.beginPath();
  for (const dot of layout.dots) {
    if (dot === layout.highlighted) continue;
    const dotRadius = grownRadius(dot, layout.radius, progress);
    if (dotRadius <= 0) continue;
    context.moveTo(dot.x + dotRadius, dot.y);
    context.arc(dot.x, dot.y, dotRadius, 0, Math.PI * 2);
  }
  context.fill();
  if (!layout.highlighted || !showHighlight) return;
  context.fillStyle = colors.tape;
  context.beginPath();
  context.arc(layout.highlighted.x, layout.highlighted.y, Math.max(layout.radius * 1.6, 4), 0, Math.PI * 2);
  context.fill();
}

type DotFieldProps = {
  count: number;
  progress: MotionValue<number>;
  origin: FieldOrigin;
  showHighlight?: boolean;
  onHighlightPlaced?: (position: FieldOrigin) => void;
};

export function DotField({ count, progress, origin, showHighlight = true, onHighlightPlaced }: DotFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const styles = getComputedStyle(canvas);
    const colors = { ink: styles.color, tape: styles.getPropertyValue("--color-tape").trim() };
    let layout = layoutDots(count, 1, 1, origin);

    function render(value: number) {
      if (!canvas || !context) return;
      context.clearRect(0, 0, canvas.width, canvas.height);
      drawDots(context, layout, value, colors, showHighlight);
    }

    function resize() {
      if (!canvas || !context) return;
      const ratio = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      layout = layoutDots(count, width, height, origin);
      if (layout.highlighted) onHighlightPlaced?.({ x: layout.highlighted.x / width, y: layout.highlighted.y / height });
      render(progress.get());
    }

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    const unsubscribe = progress.on("change", render);
    return () => {
      observer.disconnect();
      unsubscribe();
    };
  }, [count, progress, origin, showHighlight, onHighlightPlaced]);

  return <canvas ref={canvasRef} aria-hidden className="size-full text-ink" />;
}
