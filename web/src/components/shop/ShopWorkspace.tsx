"use client";

import { Cube, MapTrifold } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { InkedPlan, STATUS_TOKENS } from "@/components/plan/InkedPlan";
import { StatusMark } from "@/components/ui/StatusMark";
import type { ElementGroup } from "@/lib/findings/group";
import { findingPins } from "@/lib/findings/pins";
import { readColor } from "@/lib/ink/canvas";
import type { Scene } from "@/lib/scene/types";
import type { ModelPalette } from "./ModelViewer";

const ModelViewer = dynamic(() => import("./ModelViewer"), {
  ssr: false,
  loading: () => <div className="flex size-full items-center justify-center text-ink-muted">Building the model</div>,
});

type View = "model" | "plan";

const VIEWS: { id: View; label: string; icon: typeof Cube }[] = [
  { id: "model", label: "3D model", icon: Cube },
  { id: "plan", label: "Floor plan", icon: MapTrifold },
];

function readModelPalette(element: HTMLElement): ModelPalette {
  return {
    paper: readColor(element, "--color-paper"),
    sheet: readColor(element, "--color-sheet"),
    ink: readColor(element, "--color-ink"),
    faint: readColor(element, "--color-ink-faint"),
    accent: readColor(element, "--color-accent"),
    status: Object.fromEntries(Object.entries(STATUS_TOKENS).map(([status, token]) => [status, readColor(element, token)])) as ModelPalette["status"],
  };
}

function ViewSwitch({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <div className="flex border-b border-ink">
      {VIEWS.map(({ id, label, icon: ViewIcon }) => (
        <button
          key={id}
          type="button"
          aria-pressed={view === id}
          onClick={() => onChange(id)}
          className="pressable flex items-center gap-2 border-r border-ink px-4 py-2 text-sm font-medium text-ink-muted hover:text-ink aria-pressed:bg-ink aria-pressed:text-paper"
        >
          <ViewIcon size={18} aria-hidden />
          {label}
        </button>
      ))}
    </div>
  );
}

function FindingList({ groups, labels, selectedId, onSelect }: { groups: ElementGroup[]; labels: Map<string, string>; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <ol className="divide-y divide-ink/20">
      {groups.map((group) => {
        const label = labels.get(group.subjectId);
        const selected = selectedId === group.subjectId;
        return (
          <li key={group.subjectId}>
            <button
              type="button"
              onClick={() => onSelect(group.subjectId)}
              aria-pressed={selected}
              className="grid w-full grid-cols-[2rem_minmax(0,1fr)] gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-sheet aria-pressed:bg-sheet aria-pressed:shadow-[inset_3px_0_0_var(--color-accent)]"
            >
              <span className="font-semibold tabular-nums text-ink-muted">{label ?? ""}</span>
              <span className="flex min-w-0 flex-col gap-1">
                <span className="flex flex-wrap items-center justify-between gap-x-3">
                  <span className="font-semibold">{group.name}</span>
                  <StatusMark status={group.status} />
                </span>
                <span className="text-sm text-ink-muted text-pretty">{group.pairs[0]!.governing.message}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** The shop's model or plan beside its findings. Picking a finding in either place highlights it in both. */
export function ShopWorkspace({ scene, groups }: { scene: Scene; groups: ElementGroup[] }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>("model");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [palette, setPalette] = useState<ModelPalette | null>(null);
  const pins = useMemo(() => findingPins(groups), [groups]);
  const labels = useMemo(() => new Map(pins.map((pin) => [pin.id, pin.label])), [pins]);
  const pinHeights = useMemo(() => new Map(groups.map((group) => [group.subjectId, group.subject?.height ?? 1])), [groups]);

  useEffect(() => {
    if (rootRef.current) setPalette(readModelPalette(rootRef.current));
  }, []);

  return (
    <div ref={rootRef} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <section aria-label="Shop drawing" data-ink-avoid className="flex flex-col border border-ink bg-paper">
        <ViewSwitch view={view} onChange={setView} />
        <div className="drafting-grid relative h-[28rem] sm:h-[34rem]">
          {view === "model" && palette && (
            <ModelViewer scene={scene} palette={palette} pins={pins} pinHeights={pinHeights} selectedPinId={selectedId} onSelectPin={setSelectedId} />
          )}
          {view === "plan" && <InkedPlan scene={scene} name="shop" pins={pins} showNotes={false} selectedPinId={selectedId} onSelectPin={setSelectedId} className="size-full" />}
        </div>
      </section>
      <section aria-labelledby="findings-heading" data-ink-avoid className="border border-ink bg-paper">
        <h2 id="findings-heading" className="heading-display border-b border-ink px-4 py-3 text-xl">
          What we found
        </h2>
        <FindingList groups={groups} labels={labels} selectedId={selectedId} onSelect={setSelectedId} />
      </section>
    </div>
  );
}
