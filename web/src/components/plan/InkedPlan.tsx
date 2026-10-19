"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Point } from "@/lib/brush/geometry";
import { STATUS_LABEL } from "@/lib/findings/format";
import type { FindingStatus } from "@/lib/findings/types";
import { readColor } from "@/lib/ink/canvas";
import { InkSurface } from "@/lib/ink/surface";
import { planAnnotations } from "@/lib/plan/annotations";
import type { ToFrame } from "@/lib/plan/draft";
import { draftPins, draftPlanAnnotations, type PlanPin } from "@/lib/plan/inkPlan";
import { squaredToSheet } from "@/lib/scene/plan";
import type { Scene } from "@/lib/scene/types";
import { PlanSvg } from "./PlanSvg";

const PEN_SPEED_MULTIPLIER = 1.4;
const REDRAW_DELAY_MS = 200;
const NO_PINS: readonly PlanPin[] = [];

export const STATUS_TOKENS: Record<FindingStatus, string> = {
  fail: "--color-problem",
  needs_info: "--color-attention",
  pass: "--color-pass",
  not_applicable: "--color-ink-faint",
};

function planToFrame(svg: SVGSVGElement, frame: HTMLElement): ToFrame | null {
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  const origin = frame.getBoundingClientRect();
  return ({ x, y }) => {
    const point = new DOMPoint(x, y).matrixTransform(matrix);
    return [point.x - origin.left, point.y - origin.top];
  };
}

function statusColors(frame: HTMLElement) {
  return Object.fromEntries(Object.entries(STATUS_TOKENS).map(([status, token]) => [status, readColor(frame, token)])) as Record<FindingStatus, string>;
}

interface InkedPlanProps {
  scene: Scene;
  name: string;
  className?: string;
  pins?: readonly PlanPin[];
  showNotes?: boolean;
  selectedPinId?: string | null;
  onSelectPin?: (pinId: string) => void;
}

/**
 * The measured plan as a crisp drawing, with the drafting around it inked in by the brush: overall dimensions,
 * size notes and finding callouts. The pen draws once; later redraws at a new size lay the ink down instantly.
 */
export function InkedPlan({ scene, name, className = "", pins = NO_PINS, showNotes = true, selectedPinId = null, onSelectPin }: InkedPlanProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const paintRef = useRef<HTMLCanvasElement>(null);
  const liveRef = useRef<HTMLCanvasElement>(null);
  const view = useMemo(() => squaredToSheet(scene), [scene]);
  const annotations = useMemo(() => planAnnotations(view.scene), [view]);
  const placedPins = useMemo(() => pins.map((pin) => ({ ...pin, at: view.rotate(pin.at) })), [pins, view]);
  const [pinSpots, setPinSpots] = useState<ReadonlyMap<string, Point>>(new Map());

  useEffect(() => {
    const [frame, paint, live] = [frameRef.current, paintRef.current, liveRef.current];
    const svg = frame?.querySelector<SVGSVGElement>("svg[data-floor-plan]");
    if (!frame || !paint || !live || !svg || !annotations) return;
    const surface = new InkSurface({ surface: frame, paint, live }, { speed: PEN_SPEED_MULTIPLIER, paperToken: "--color-paper" });
    let drawnAt = "";
    let redrawTimer: number | undefined;
    let disposed = false;

    const redraw = () => {
      const toFrame = planToFrame(svg, frame);
      if (disposed || !toFrame) return;
      surface.instant = drawnAt !== "";
      drawnAt = `${frame.clientWidth}x${frame.clientHeight}`;
      surface.clear();
      surface.fit();
      draftPlanAnnotations(surface.brush, annotations, toFrame, frame.clientWidth, showNotes);
      setPinSpots(draftPins(surface.brush, placedPins, toFrame, [frame.clientWidth, frame.clientHeight], statusColors(frame)));
      surface.wake();
    };

    const observer = new ResizeObserver(() => {
      if (`${frame.clientWidth}x${frame.clientHeight}` === drawnAt) return;
      window.clearTimeout(redrawTimer);
      redrawTimer = window.setTimeout(redraw, REDRAW_DELAY_MS);
    });
    void document.fonts.ready.then(() => {
      if (disposed) return;
      redraw();
      observer.observe(frame);
    });

    return () => {
      disposed = true;
      window.clearTimeout(redrawTimer);
      observer.disconnect();
      surface.dispose();
    };
  }, [annotations, placedPins, showNotes]);

  return (
    <div ref={frameRef} className={`relative ${className}`}>
      <div className={`absolute top-14 bottom-6 left-14 sm:left-20 ${showNotes ? "right-6 sm:right-64" : "right-6 sm:right-10"}`}>
        <PlanSvg scene={view.scene} name={name} className="size-full" />
      </div>
      <canvas ref={paintRef} data-ink-layer aria-hidden className="pointer-events-none absolute inset-0 size-full" />
      <canvas ref={liveRef} data-ink-layer aria-hidden className="pointer-events-none absolute inset-0 size-full" />
      {onSelectPin &&
        pins.map((pin) => {
          const spot = pinSpots.get(pin.id);
          if (!spot) return null;
          const selected = pin.id === selectedPinId;
          return (
            <button
              key={pin.id}
              type="button"
              onClick={() => onSelectPin(pin.id)}
              aria-pressed={selected}
              aria-label={`Finding ${pin.label}: ${STATUS_LABEL[pin.status]}`}
              className={`absolute size-9 -translate-x-1/2 -translate-y-1/2 rounded-full transition-shadow duration-150 hover:ring-2 hover:ring-ink/30 ${selected ? "ring-2 ring-accent ring-offset-2 ring-offset-paper" : ""}`}
              style={{ left: spot[0], top: spot[1] }}
            />
          );
        })}
      {annotations && (
        <p className="sr-only">
          The plan measures {annotations.widthLabel} wide by {annotations.depthLabel} deep.
          {annotations.notes.map((note) => ` ${note.text}.`).join("")}
        </p>
      )}
    </div>
  );
}
