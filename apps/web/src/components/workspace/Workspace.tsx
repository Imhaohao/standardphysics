"use client";

import { ArrowLeft, ArrowsOutCardinal, HandGrabbing, ListChecks, SquareHalfBottom } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { overviewPose, poseFromLocus, topDownPose, type ViewerPose } from "@/lib/camera";
import { findingForNode, groupFindings } from "@/lib/findings";
import { METERS_PER_INCH } from "@/lib/moves";
import type { Assessment, Finding, Scan, SceneGraph } from "@/types/contracts";
import { ArrangePanel } from "./ArrangePanel";
import { FindingsList } from "./FindingsList";
import type { ArrangeHandlers } from "./ShopModel";
import { type Arrangement, useArrangement } from "./useArrangement";

const Viewer = dynamic(() => import("./Viewer"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-rule/30" />,
});

type WorkspaceProps = {
  scan: Scan;
  scene: SceneGraph;
  exported: SceneGraph;
  assessment: Assessment | null;
  glbUrl: string | null;
};

type ViewMode = "overview" | "top";
type Task = "findings" | "arrange";

function poseFor(scene: SceneGraph, selected: Finding | null, mode: ViewMode): ViewerPose {
  if (selected?.locus) return poseFromLocus(selected.locus.camera);
  return mode === "top" ? topDownPose(scene) : overviewPose(scene);
}

const NUDGES: Record<string, [number, number]> = {
  ArrowUp: [0, 1],
  ArrowDown: [0, -1],
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
};

function arrangeKey(event: KeyboardEvent, arrangement: Arrangement) {
  const inches = (event.shiftKey ? 6 : 1) * METERS_PER_INCH;
  const nudge = NUDGES[event.key];
  if (nudge) {
    event.preventDefault();
    arrangement.nudge(nudge[0] * inches, nudge[1] * inches, 0);
  } else if (event.key === "r" || event.key === "R") {
    arrangement.nudge(0, 0, event.shiftKey ? -15 : 15);
  }
}

function useKeyboard(task: Task, arrangement: Arrangement, clear: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        clear();
        arrangement.setActiveId(null);
        return;
      }
      const typing = (event.target as HTMLElement).closest("input, textarea, nav");
      if (task === "arrange" && arrangement.activeId && !typing) arrangeKey(event, arrangement);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [task, arrangement, clear]);
}

export function Workspace({ scan, scene, exported, assessment, glbUrl }: WorkspaceProps) {
  const findings = useMemo(() => assessment?.findings ?? [], [assessment]);
  const groups = useMemo(() => groupFindings(findings), [findings]);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [mode, setMode] = useState<ViewMode>("overview");
  const [task, setTask] = useState<Task>("findings");
  const [dragging, setDragging] = useState(false);
  const arrangement = useArrangement(scan.id, scene);
  const pose = useMemo(() => poseFor(scene, selected, mode), [scene, selected, mode]);

  const clear = useCallback(() => setSelected(null), []);
  const selectNode = useCallback((nodeId: string) => setSelected(findingForNode(findings, nodeId) ?? null), [findings]);
  const toggle = (finding: Finding) => setSelected((current) => (current?.id === finding.id ? null : finding));
  const showView = (next: ViewMode) => {
    setSelected(null);
    setMode(next);
  };
  const switchTask = (next: Task) => {
    setSelected(null);
    if (next === "findings") arrangement.reset();
    setTask(next);
  };

  useKeyboard(task, arrangement, clear);

  const { setActiveId, drag, drop, activeId, blockedIds } = arrangement;
  const handlers: ArrangeHandlers | null = useMemo(
    () =>
      task !== "arrange"
        ? null
        : {
            activeId,
            blockedIds,
            onGrab: (nodeId) => {
              setActiveId(nodeId);
              setDragging(true);
            },
            onDrag: drag,
            onDrop: () => {
              setDragging(false);
              drop();
            },
          },
    [task, activeId, blockedIds, setActiveId, drag, drop],
  );

  return (
    <div className="grid h-dvh grid-rows-[auto_minmax(18rem,55dvh)_1fr] lg:grid-cols-[1fr_24rem] lg:grid-rows-[auto_1fr]">
      <header className="flex items-center gap-3 px-3 py-3 lg:col-span-2">
        <Link href="/" className="rounded-lg p-2 text-ink-muted hover:bg-ink/5 hover:text-ink" aria-label="Your shops">
          <ArrowLeft size={20} weight="bold" />
        </Link>
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold">{scan.name}</h1>
        <div className="flex gap-1 rounded-xl bg-rule/50 p-1" role="group" aria-label="What to do">
          <Button variant="chip" aria-pressed={task === "findings"} onClick={() => switchTask("findings")}>
            <ListChecks size={16} weight="bold" aria-hidden />
            Findings
          </Button>
          <Button variant="chip" aria-pressed={task === "arrange"} onClick={() => switchTask("arrange")}>
            <HandGrabbing size={16} weight="bold" aria-hidden />
            Move furniture
          </Button>
        </div>
      </header>
      <section className="relative min-h-0 touch-none overflow-hidden lg:rounded-tr-2xl" aria-label="Shop model">
        <Viewer
          scene={arrangement.shown}
          exported={exported}
          arrange={handlers}
          dragging={dragging}
          glbUrl={glbUrl}
          pose={pose}
          selected={task === "findings" ? selected : null}
          onSelectNode={selectNode}
          onClearSelection={clear}
        />
        <div className="absolute bottom-4 left-4 flex gap-2">
          <Button variant="chip" aria-pressed={mode === "overview" && !selected} onClick={() => showView("overview")}>
            <ArrowsOutCardinal size={16} weight="bold" aria-hidden />
            Whole shop
          </Button>
          <Button variant="chip" aria-pressed={mode === "top" && !selected} onClick={() => showView("top")}>
            <SquareHalfBottom size={16} weight="bold" aria-hidden />
            From above
          </Button>
        </div>
      </section>
      <aside className="min-h-0 overflow-y-auto px-3 pb-10 pt-4 lg:pt-0">
        {task === "arrange" ? (
          <ArrangePanel arrangement={arrangement} fallbackFindings={findings} />
        ) : findings.length > 0 ? (
          <FindingsList groups={groups} selectedId={selected?.id ?? null} onSelect={toggle} />
        ) : (
          <p className="px-3 text-ink-muted">
            {scan.state === "ready" ? "Findings show up here once the shop is checked." : "Checking your shop"}
          </p>
        )}
      </aside>
    </div>
  );
}
