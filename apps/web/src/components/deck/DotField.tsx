"use client";

import type { MotionValue } from "motion/react";
import { useEffect, useRef } from "react";

const DOT_GROWTH_WINDOW = 0.06;

type Dot = { x: number; y: number; threshold: number; unpaid: boolean };
type FieldLayout = { dots: Dot[]; radius: number; highlighted: Dot | null };
export type FieldOrigin = { x: number; y: number };

function noiseAt(index: number) {
  const scatter = Math.sin(index * 12.9898) * 43758.5453;
  return scatter - Math.floor(scatter);
}

function scrambledShare(index: number) {
  let value = Math.imul(index ^ 0x9e3779b9, 0x85ebca6b);
  value = Math.imul(value ^ (value >>> 13), 0xc2b2ae35);
  value ^= value >>> 16;
  return (value >>> 0) / 4294967296;
}

function layoutDots(count: number, width: number, height: number, origin: FieldOrigin, unpaidShare: number): FieldLayout {
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
    const dot = { x, y, threshold: ((distance / farthest) * 0.85 + noiseAt(index) * 0.15) * (1 - DOT_GROWTH_WINDOW), unpaid: scrambledShare(index) < unpaidShare };
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

type FieldColors = { ink: string; tape: string; unpaid: string };

function addDot(context: CanvasRenderingContext2D, dot: Dot, radius: number) {
  context.moveTo(dot.x + radius, dot.y);
  context.arc(dot.x, dot.y, radius, 0, Math.PI * 2);
}

class FieldPainter {
  private readonly settled: HTMLCanvasElement;
  private readonly settledContext: CanvasRenderingContext2D;
  private order: Dot[] = [];
  private unpaid: Dot[] = [];
  private settledCount = 0;
  private layout: FieldLayout = { dots: [], radius: 0, highlighted: null };

  constructor(private readonly colors: FieldColors) {
    this.settled = document.createElement("canvas");
    this.settledContext = this.settled.getContext("2d") as CanvasRenderingContext2D;
  }

  reset(layout: FieldLayout, pixelWidth: number, pixelHeight: number, ratio: number) {
    this.layout = layout;
    this.order = layout.dots.filter((dot) => dot !== layout.highlighted).sort((left, right) => left.threshold - right.threshold);
    this.unpaid = this.order.filter((dot) => dot.unpaid);
    this.settled.width = pixelWidth;
    this.settled.height = pixelHeight;
    this.settledContext.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.settledContext.fillStyle = this.colors.ink;
    this.settledCount = 0;
  }

  private settleUpTo(progress: number) {
    const context = this.settledContext;
    context.beginPath();
    while (this.settledCount < this.order.length && progress >= this.order[this.settledCount].threshold + DOT_GROWTH_WINDOW) {
      addDot(context, this.order[this.settledCount], this.layout.radius);
      this.settledCount += 1;
    }
    context.fill();
  }

  private unsettleIfRewound(progress: number) {
    if (this.settledCount === 0) return;
    const last = this.order[this.settledCount - 1];
    if (progress >= last.threshold + DOT_GROWTH_WINDOW) return;
    this.settledContext.save();
    this.settledContext.setTransform(1, 0, 0, 1, 0, 0);
    this.settledContext.clearRect(0, 0, this.settled.width, this.settled.height);
    this.settledContext.restore();
    this.settledCount = 0;
  }

  paint(context: CanvasRenderingContext2D, progress: number, showHighlight: boolean, unpaidFade: number) {
    this.unsettleIfRewound(progress);
    this.settleUpTo(progress);
    context.save();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, context.canvas.width, context.canvas.height);
    context.drawImage(this.settled, 0, 0);
    context.restore();

    context.fillStyle = this.colors.ink;
    context.beginPath();
    for (let index = this.settledCount; index < this.order.length; index += 1) {
      const dot = this.order[index];
      if (dot.threshold >= progress) break;
      addDot(context, dot, grownRadius(dot, this.layout.radius, progress));
    }
    context.fill();
    this.paintUnpaid(context, unpaidFade);
    this.paintHighlight(context, showHighlight);
  }

  private paintUnpaid(context: CanvasRenderingContext2D, fade: number) {
    if (fade <= 0 || this.unpaid.length === 0) return;
    context.save();
    context.globalAlpha = Math.min(fade, 1);
    context.fillStyle = this.colors.unpaid;
    context.beginPath();
    for (const dot of this.unpaid) addDot(context, dot, this.layout.radius + 0.6);
    context.fill();
    context.restore();
  }

  private paintHighlight(context: CanvasRenderingContext2D, showHighlight: boolean) {
    const highlighted = this.layout.highlighted;
    if (!highlighted || !showHighlight) return;
    context.fillStyle = this.colors.tape;
    context.beginPath();
    context.arc(highlighted.x, highlighted.y, Math.max(this.layout.radius * 1.6, 4), 0, Math.PI * 2);
    context.fill();
  }
}

type DotFieldProps = {
  count: number;
  progress: MotionValue<number>;
  origin: FieldOrigin;
  showHighlight?: boolean;
  onHighlightPlaced?: (position: FieldOrigin) => void;
  unpaidShare?: number;
  unpaidFade?: MotionValue<number>;
};

export function DotField({ count, progress, origin, showHighlight = true, onHighlightPlaced, unpaidShare = 0, unpaidFade }: DotFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const showHighlightRef = useRef(showHighlight);
  const repaintRef = useRef<() => void>(() => {});

  useEffect(() => {
    showHighlightRef.current = showHighlight;
    repaintRef.current();
  }, [showHighlight]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const styles = getComputedStyle(canvas);
    const painter = new FieldPainter({ ink: styles.color, tape: styles.getPropertyValue("--color-tape").trim(), unpaid: styles.getPropertyValue("--color-rule").trim() });

    function render(value: number) {
      painter.paint(context as CanvasRenderingContext2D, value, showHighlightRef.current, unpaidFade?.get() ?? 0);
    }

    function resize() {
      if (!canvas || !context) return;
      const ratio = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const layout = layoutDots(count, width, height, origin, unpaidShare);
      painter.reset(layout, canvas.width, canvas.height, ratio);
      if (layout.highlighted) onHighlightPlaced?.({ x: layout.highlighted.x / width, y: layout.highlighted.y / height });
      render(progress.get());
    }

    repaintRef.current = () => render(progress.get());
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    const unsubscribe = progress.on("change", render);
    const unsubscribeFade = unpaidFade?.on("change", () => render(progress.get()));
    return () => {
      observer.disconnect();
      unsubscribe();
      unsubscribeFade?.();
    };
  }, [count, progress, origin, onHighlightPlaced, unpaidShare, unpaidFade]);

  return <canvas ref={canvasRef} aria-hidden className="size-full text-ink" />;
}
