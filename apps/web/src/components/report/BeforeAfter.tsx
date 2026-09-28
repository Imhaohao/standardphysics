import Link from "next/link";
import type { ReactNode } from "react";
import { applyMoves } from "@/lib/moves";
import type { LayoutPlan, SceneGraph } from "@/types/contracts";
import type { ClauseRow } from "./redesign";
import { PlanPanel, sharedFrame, type PlanMark } from "./PlanPanel";

function marksBefore(rows: ClauseRow[]): PlanMark[] {
  return rows.filter((row) => row.change !== "new_problem").map((row) => ({ row, state: "fails" }));
}

function marksAfter(rows: ClauseRow[]): PlanMark[] {
  return rows.map((row) => ({ row, state: row.change === "cleared" ? "cleared" : "fails" }));
}

function failingCount(marks: PlanMark[]): string {
  const failing = marks.filter((mark) => mark.state === "fails").length;
  return failing === 1 ? "1 spot fails" : `${failing} spots fail`;
}

function Sheet({ title, marks, children }: { title: string; marks: PlanMark[]; children: ReactNode }) {
  return (
    <figure className="break-inside-avoid border border-ink bg-sheet">
      <figcaption className="flex items-baseline justify-between gap-4 border-b border-ink px-4 py-2">
        <span className="font-semibold">{title}</span>
        <span className="text-sm text-ink-muted">{failingCount(marks)}</span>
      </figcaption>
      <div className="drafting-grid p-3">{children}</div>
    </figure>
  );
}

function LayoutPicker({ plans, shown, hrefFor }: { plans: LayoutPlan[]; shown: LayoutPlan; hrefFor: (planId: string) => string }) {
  if (plans.length < 2) return null;
  return (
    <nav aria-label="Layouts" className="mt-4 flex flex-wrap gap-2 print:hidden">
      {plans.map((plan) => (
        <Link
          key={plan.id}
          href={hrefFor(plan.id)}
          scroll={false}
          aria-current={plan.id === shown.id ? "true" : undefined}
          className="pressable rounded-lg bg-ink/[0.07] px-3 py-1.5 text-sm font-medium hover:bg-ink/[0.12] aria-[current]:bg-ink aria-[current]:text-paper"
        >
          Show {plan.name}
        </Link>
      ))}
    </nav>
  );
}

function Key() {
  return (
    <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-muted">
      <div className="flex items-center gap-2">
        <dt><svg viewBox="0 0 16 16" className="size-4" aria-hidden><circle cx="8" cy="8" r="7" className="fill-problem" /></svg></dt>
        <dd>Fails here</dd>
      </div>
      <div className="flex items-center gap-2">
        <dt><svg viewBox="0 0 16 16" className="size-4" aria-hidden><circle cx="8" cy="8" r="6.5" className="fill-sheet stroke-pass" strokeWidth="2" /></svg></dt>
        <dd>Cleared by the layout</dd>
      </div>
      <div className="flex items-center gap-2">
        <dt><svg viewBox="0 0 16 16" className="size-4" aria-hidden><rect x="1" y="4" width="14" height="8" className="fill-accent" /></svg></dt>
        <dd>Moved piece</dd>
      </div>
      <div className="flex items-center gap-2">
        <dt><svg viewBox="0 0 16 16" className="size-4" aria-hidden><rect x="1.5" y="4.5" width="13" height="7" className="fill-none stroke-accent" strokeDasharray="3 2" /></svg></dt>
        <dd>Where it stood</dd>
      </div>
    </dl>
  );
}

interface BeforeAfterProps {
  scene: SceneGraph;
  plans: LayoutPlan[];
  plan: LayoutPlan;
  rows: ClauseRow[];
  hrefFor: (planId: string) => string;
}

/** The room as scanned beside the room as the plan lays it out, at one scale so a move reads as a move. */
export function BeforeAfter({ scene, plans, plan, rows, hrefFor }: BeforeAfterProps) {
  const planned = applyMoves(scene, Object.fromEntries(plan.moves.map((move) => [move.node_id, move])));
  const frame = sharedFrame([scene, planned]);
  const moved = new Set(plan.moves.map((move) => move.node_id));
  const [before, after] = [marksBefore(rows), marksAfter(rows)];
  return (
    <section className="mt-16 break-inside-avoid print:mt-0 print:break-before-page" aria-labelledby="before-after">
      <h2 id="before-after" className="heading-display text-3xl">Before and after</h2>
      <LayoutPicker plans={plans} shown={plan} hrefFor={hrefFor} />
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Sheet title="As scanned" marks={before}>
          <PlanPanel scene={scene} frame={frame} marks={before} label={`The shop as scanned. ${failingCount(before)}.`} />
        </Sheet>
        <Sheet title={plan.name} marks={after}>
          <PlanPanel
            scene={planned} frame={frame} marks={after} label={`The shop laid out as ${plan.name}. ${failingCount(after)}.`}
            movedFrom={scene.nodes.filter((node) => moved.has(node.id))}
          />
        </Sheet>
      </div>
      <Key />
    </section>
  );
}
