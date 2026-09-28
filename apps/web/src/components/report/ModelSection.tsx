"use client";

import { Cube, DownloadSimple } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { buttonClassName } from "@/components/ui/Button";
import { applyMoves } from "@/lib/moves";
import type { LayoutPlan, SceneGraph } from "@/types/contracts";

const RoomModel = dynamic(() => import("./RoomModel"), {
  ssr: false,
  loading: () => <div className="size-full animate-pulse bg-ink/[0.04]" />,
});

type Showing = "scanned" | "planned";

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(true);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

function modelHref(base: string, plan: LayoutPlan | null): string {
  return plan ? `${base}?plan=${encodeURIComponent(plan.id)}` : base;
}

function ShowingToggle({ plan, showing, onChange }: { plan: LayoutPlan; showing: Showing; onChange: (next: Showing) => void }) {
  const options: [Showing, string][] = [["scanned", "Show it as scanned"], ["planned", `Show ${plan.name}`]];
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(([value, label]) => (
        <button
          key={value}
          type="button"
          aria-pressed={showing === value}
          onClick={() => onChange(value)}
          className="pressable rounded-lg bg-ink/[0.07] px-3 py-1.5 text-sm font-medium hover:bg-ink/[0.12] aria-pressed:bg-ink aria-pressed:text-paper"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function useShownRoom(scene: SceneGraph, plan: LayoutPlan | null, showing: Showing) {
  const moved = useMemo(() => new Set(plan?.moves.map((move) => move.node_id) ?? []), [plan]);
  const planned = useMemo(
    () => (plan ? applyMoves(scene, Object.fromEntries(plan.moves.map((move) => [move.node_id, move]))) : null),
    [scene, plan],
  );
  const showPlan = planned !== null && showing === "planned";
  const ghosts = useMemo(() => (showPlan ? scene.nodes.filter((node) => moved.has(node.id)) : []), [showPlan, scene, moved]);
  return { shown: showPlan ? planned : scene, moved, ghosts, label: showPlan && plan ? `laid out as ${plan.name}` : "as scanned" };
}

function Downloads({ plan, modelBase, fileStem }: { plan: LayoutPlan | null; modelBase: string; fileStem: string }) {
  return (
    <div className="mt-4 flex flex-wrap gap-3">
      <a href={modelHref(modelBase, null)} download={`${fileStem}-as-scanned-mm.stl`} className={buttonClassName(plan ? "choice" : "primary")}>
        <DownloadSimple size={18} weight="bold" aria-hidden />
        Download as scanned (.stl)
      </a>
      {plan && (
        <a href={modelHref(modelBase, plan)} download className={buttonClassName("primary")}>
          <DownloadSimple size={18} weight="bold" aria-hidden />
          Download {plan.name} (.stl)
        </a>
      )}
    </div>
  );
}

interface ModelSectionProps {
  scene: SceneGraph;
  plan: LayoutPlan | null;
  /** Where the room downloads as STL, for this viewer: the owner's own address or a shared link's. */
  modelBase: string;
  fileStem: string;
}

/** The measured room rebuilt as boxes, the same geometry the STL carries, cut at 48 inches like a plan. */
export function ModelSection({ scene, plan, modelBase, fileStem }: ModelSectionProps) {
  const [showing, setShowing] = useState<Showing>("planned");
  const reducedMotion = useReducedMotion();
  const room = useShownRoom(scene, plan, showing);

  return (
    <section className="mt-16 print:hidden" aria-labelledby="room-model">
      <h2 id="room-model" className="heading-display text-3xl">3D model for your architect</h2>
      <div className="mt-6 border border-ink bg-sheet">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink px-4 py-2">
          {plan ? <ShowingToggle plan={plan} showing={showing} onChange={setShowing} /> : <span className="font-semibold">As scanned</span>}
          <span className="text-sm text-ink-muted">Cut at 48 in. Drag to turn it.</span>
        </div>
        <div className="aspect-[16/10] w-full" role="img" aria-label={`A 3D model of the room ${room.label}, with every measured piece drawn as a box.`}>
          <RoomModel scene={room.shown} moved={room.moved} ghosts={room.ghosts} turning={!reducedMotion} />
        </div>
      </div>
      <Downloads plan={plan} modelBase={modelBase} fileStem={fileStem} />
      <p className="mt-3 flex max-w-prose items-start gap-2 text-sm text-ink-muted">
        <Cube size={18} className="mt-0.5 shrink-0" aria-hidden />
        Millimetres with Z up. Every piece the scan measured is one box at its measured size, and a wall the scan saw
        as a sheet stays a sheet. Rhino and SketchUp open it as a mesh.
      </p>
    </section>
  );
}
