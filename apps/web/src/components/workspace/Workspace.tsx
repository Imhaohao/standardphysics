"use client";

import { ArrowLeft, ArrowsOutCardinal, SquareHalfBottom } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { overviewPose, poseFromLocus, topDownPose, type ViewerPose } from "@/lib/camera";
import { findingForNode, groupFindings } from "@/lib/findings";
import type { Assessment, Finding, Scan, SceneGraph } from "@/types/contracts";
import { FindingsList } from "./FindingsList";

const Viewer = dynamic(() => import("./Viewer"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-rule/30" />,
});

type WorkspaceProps = { scan: Scan; scene: SceneGraph; assessment: Assessment | null; glbUrl: string | null };

type ViewMode = "overview" | "top";

function poseFor(scene: SceneGraph, selected: Finding | null, mode: ViewMode): ViewerPose {
  if (selected?.locus) return poseFromLocus(selected.locus.camera);
  return mode === "top" ? topDownPose(scene) : overviewPose(scene);
}

export function Workspace({ scan, scene, assessment, glbUrl }: WorkspaceProps) {
  const findings = useMemo(() => assessment?.findings ?? [], [assessment]);
  const groups = useMemo(() => groupFindings(findings), [findings]);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [mode, setMode] = useState<ViewMode>("overview");
  const pose = useMemo(() => poseFor(scene, selected, mode), [scene, selected, mode]);

  const clear = useCallback(() => setSelected(null), []);
  const selectNode = useCallback((nodeId: string) => setSelected(findingForNode(findings, nodeId) ?? null), [findings]);
  const toggle = (finding: Finding) => setSelected((current) => (current?.id === finding.id ? null : finding));
  const showView = (next: ViewMode) => {
    setSelected(null);
    setMode(next);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && clear();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clear]);

  return (
    <div className="grid h-dvh grid-rows-[auto_minmax(18rem,55dvh)_1fr] lg:grid-cols-[1fr_24rem] lg:grid-rows-[auto_1fr]">
      <header className="flex items-center gap-3 px-3 py-3 lg:col-span-2">
        <Link href="/" className="rounded-lg p-2 text-ink-muted hover:bg-ink/5 hover:text-ink" aria-label="Your shops">
          <ArrowLeft size={20} weight="bold" />
        </Link>
        <h1 className="truncate text-lg font-semibold">{scan.name}</h1>
      </header>
      <section className="relative min-h-0 overflow-hidden lg:rounded-tr-2xl" aria-label="Shop model">
        <Viewer scene={scene} glbUrl={glbUrl} pose={pose} selected={selected} onSelectNode={selectNode} onClearSelection={clear} />
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
        {findings.length > 0 ? (
          <FindingsList groups={groups} selectedId={selected?.id ?? null} onSelect={toggle} />
        ) : (
          <p className="px-3 text-ink-muted">{scan.state === "ready" ? "Findings show up here once the shop is checked." : "Checking your shop"}</p>
        )}
      </aside>
    </div>
  );
}
