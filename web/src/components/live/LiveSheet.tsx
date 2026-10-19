"use client";

import { ArrowCounterClockwise, CheckCircle, FileText } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { STATUS_TOKENS } from "@/components/plan/InkedPlan";
import { Button, buttonClassName } from "@/components/ui/Button";
import { ShopHeader } from "@/components/shop/ShopHeader";
import { StatusMark } from "@/components/ui/StatusMark";
import { liveFindings, liveTitle, type LiveState } from "@/lib/api/live";
import { groupByElement, groupHeadline, type ElementGroup } from "@/lib/findings/group";
import { findingPins } from "@/lib/findings/pins";
import type { FindingStatus } from "@/lib/findings/types";
import { readColor } from "@/lib/ink/canvas";
import { InkSurface } from "@/lib/ink/surface";
import type { PlanPin } from "@/lib/plan/inkPlan";
import { LivePlanInk } from "@/lib/plan/livePlan";
import { indexSubjects } from "@/lib/scene/describe";
import { useLiveScan, type LiveSource } from "./useLiveScan";

const PHASE_COPY: Record<LiveState["phase"], string> = {
  connecting: "Connecting to the scan",
  live: "Scanning now",
  finished: "Scan finished and checked",
  error: "The connection dropped",
};

/** Numbers findings in the order they first turn up, so a pin keeps its number while the scan goes on. */
function useArrivalLabels(groups: ElementGroup[]) {
  const [labels] = useState(() => new Map<string, string>());
  return useMemo(() => {
    for (const pin of findingPins(groups)) if (!labels.has(pin.id)) labels.set(pin.id, String(labels.size + 1));
    const pins = findingPins(groups).map((pin) => ({ ...pin, label: labels.get(pin.id)! }));
    return { pins, labels: new Map(labels) };
  }, [groups, labels]);
}

function useLivePlanInk(state: LiveState, pins: readonly PlanPin[]) {
  const frameRef = useRef<HTMLDivElement>(null);
  const paintRef = useRef<HTMLCanvasElement>(null);
  const liveRef = useRef<HTMLCanvasElement>(null);
  const inkRef = useRef<LivePlanInk | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const [frame, paint, live] = [frameRef.current, paintRef.current, liveRef.current];
    if (!frame || !paint || !live) return;
    const surface = new InkSurface({ surface: frame, paint, live }, { speed: 1.2, paperToken: "--color-paper" });
    const colors = Object.fromEntries(Object.entries(STATUS_TOKENS).map(([status, token]) => [status, readColor(frame, token)])) as Record<FindingStatus, string>;
    let disposed = false;
    void document.fonts.ready.then(() => {
      if (disposed) return;
      surface.fit();
      inkRef.current = new LivePlanInk(surface, colors);
      setReady(true);
    });
    return () => {
      disposed = true;
      inkRef.current = null;
      surface.dispose();
    };
  }, []);

  useEffect(() => {
    if (ready) inkRef.current?.update(state.scene, pins);
  }, [ready, state.scene, pins]);

  return { frameRef, paintRef, liveRef };
}

function PhaseLine({ phase, error }: { phase: LiveState["phase"]; error: string | null }) {
  const finished = phase === "finished";
  return (
    <p role="status" className="flex items-center gap-2 font-semibold">
      {finished ? (
        <CheckCircle size={20} weight="fill" aria-hidden className="text-pass" />
      ) : (
        <span aria-hidden className={`size-2.5 rounded-full ${phase === "error" ? "bg-problem" : "bg-accent motion-safe:animate-pulse"}`} />
      )}
      {error ?? PHASE_COPY[phase]}
    </p>
  );
}

function FindingFeed({ groups, labels }: { groups: ElementGroup[]; labels: ReadonlyMap<string, string> }) {
  if (groups.length === 0) return <p className="px-4 py-3 text-ink-muted">Findings show up here as each wall, door and piece of furniture is measured.</p>;
  return (
    <ol aria-live="polite" className="divide-y divide-ink/20">
      {groups.map((group) => (
        <li key={group.subjectId} className="flex flex-col gap-1 px-4 py-3">
          <span className="flex flex-wrap items-center justify-between gap-x-3">
            <span className="font-semibold">
              {labels.has(group.subjectId) ? `${labels.get(group.subjectId)}. ` : ""}
              {group.name}
            </span>
            <StatusMark status={group.status} />
          </span>
          <span className="text-sm text-ink-muted text-pretty">{groupHeadline(group)}</span>
        </li>
      ))}
    </ol>
  );
}

/** A scan drawing itself: walls, doors and furniture are inked onto the sheet the moment they are captured. */
interface LiveSheetProps {
  source: LiveSource;
  reportHref: string;
  backHref: string;
  backLabel: string;
}

export function LiveSheet(props: LiveSheetProps) {
  const [run, setRun] = useState(0);
  return <LiveRun key={run} {...props} onReplay={() => setRun((count) => count + 1)} />;
}

function LiveRun({ source, reportHref, backHref, backLabel, onReplay }: LiveSheetProps & { onReplay: () => void }) {
  const state = useLiveScan(source);
  const groups = useMemo(() => groupByElement(liveFindings(state), indexSubjects(state.scene)), [state]);
  return (
    <>
      <ShopHeader backHref={backHref} backLabel={backLabel} title={liveTitle(source.kind, state.phase)} />
      <LiveLayout state={state} groups={groups} reportHref={reportHref} canReplay={source.kind === "replay"} onReplay={onReplay} />
    </>
  );
}

function LiveLayout({ state, groups, reportHref, canReplay, onReplay }: { state: LiveState; groups: ElementGroup[]; reportHref: string; canReplay: boolean; onReplay: () => void }) {
  const { pins, labels } = useArrivalLabels(groups);
  const { frameRef, paintRef, liveRef } = useLivePlanInk(state, pins);
  const finished = state.phase === "finished";
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-start">
      <section aria-label="The scan, drawn as it is captured" data-ink-avoid className="border border-ink bg-paper">
        <div ref={frameRef} className="drafting-grid relative h-[30rem] sm:h-[38rem]">
          <canvas ref={paintRef} data-ink-layer aria-hidden className="pointer-events-none absolute inset-0 size-full" />
          <canvas ref={liveRef} data-ink-layer aria-hidden className="pointer-events-none absolute inset-0 size-full" />
        </div>
      </section>
      <section aria-labelledby="live-heading" data-ink-avoid className="flex flex-col border border-ink bg-paper">
        <div className="flex flex-col gap-3 border-b border-ink px-4 py-3">
          <h2 id="live-heading" className="heading-display text-xl">
            {finished ? "What we found" : <>What we&rsquo;ve found so far</>}
          </h2>
          <PhaseLine phase={state.phase} error={state.error} />
        </div>
        <FindingFeed groups={groups} labels={labels} />
        {finished && (
          <div className="mt-auto flex flex-wrap gap-3 border-t border-ink p-4">
            <Link href={reportHref} className={buttonClassName("primary")}>
              <FileText size={18} aria-hidden />
              Read the full report
            </Link>
            {canReplay && (
              <Button variant="quiet" onClick={onReplay}>
                <ArrowCounterClockwise size={18} aria-hidden />
                Replay
              </Button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
