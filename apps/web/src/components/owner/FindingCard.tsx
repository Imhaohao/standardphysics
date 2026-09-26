"use client";

import { ArrowsOutCardinal } from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import { formatInches } from "@/lib/findings";
import { type ChecklistStatus, comparisonBars } from "@/lib/owner-journey";
import type { Finding } from "@/types/contracts";
import { StatusControl } from "./StatusControl";

const MOVABLE = new Set(["route_clear_width", "passing_space", "turning_space", "turn_clear_width", "exit_path", "service_counter_approach", "door_maneuvering_clearance"]);

export type CardActions = {
  onShow: (finding: Finding) => void;
  onStatus: (finding: Finding, status: ChecklistStatus) => void;
  onPlan: (finding: Finding) => void;
};

/**
 * One thing to fix. The picture shows the spot, the two bars show how far off
 * it is, and the line under them says what to do. Once the owner starts fixing,
 * the card also carries its status.
 */
export function FindingCard({ finding, selected, status, fixing, saving, actions }: {
  finding: Finding;
  selected: boolean;
  status: ChecklistStatus;
  fixing: boolean;
  saving: boolean;
  actions: CardActions;
}) {
  return (
    <article className={`flex flex-col gap-4 rounded-2xl bg-sheet p-4 shadow-float transition-shadow duration-150 ${selected ? "ring-2 ring-accent" : ""} ${status !== "to_do" ? "opacity-75" : ""}`}>
      <button type="button" onClick={() => actions.onShow(finding)} aria-pressed={selected} className="flex flex-col gap-3 text-left">
        <Picture finding={finding} />
        <h2 className="text-lg font-semibold leading-snug text-pretty">{finding.title}</h2>
      </button>
      <Comparison finding={finding} />
      {finding.fix && <p className="border-l-2 border-accent pl-3 font-medium text-pretty">{finding.fix}</p>}
      {MOVABLE.has(finding.check_id) && (
        <Button className="self-start" onClick={() => actions.onPlan(finding)}>
          <ArrowsOutCardinal size={18} weight="bold" aria-hidden />
          See a layout that fixes this
        </Button>
      )}
      {fixing && <StatusControl name={`status-${finding.id}`} status={status} disabled={saving} onChange={(next) => actions.onStatus(finding, next)} />}
    </article>
  );
}

function Picture({ finding }: { finding: Finding }) {
  const render = finding.locus?.render_url;
  if (!render) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={render} alt="" className="aspect-video w-full rounded-xl bg-rule/40 object-cover outline outline-1 -outline-offset-1 outline-black/10" />
  );
}

/** The measurement and the number the standard needs, as two bars on one scale. */
function Comparison({ finding }: { finding: Finding }) {
  const { measured_inches: measured, required_inches: required } = finding;
  if (measured === null || required === null) return null;
  const bars = comparisonBars(measured, required);
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2">
      <dt className="sr-only">Your shop</dt>
      <dd className="h-3 bg-problem" style={{ width: `${bars.measured * 100}%` }} aria-hidden />
      <dd className="measurement text-lg font-semibold text-problem">{formatInches(measured)}</dd>
      <dt className="sr-only">What&rsquo;s needed</dt>
      <dd className="h-3 border-2 border-dashed border-ink/50" style={{ width: `${bars.required * 100}%` }} aria-hidden />
      <dd className="measurement text-ink-muted">{formatInches(required)} needed</dd>
    </dl>
  );
}
