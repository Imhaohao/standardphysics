"use client";

import { ArrowClockwise, ArrowCounterClockwise, CheckCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { Arrangement } from "@/components/workspace/useArrangement";
import { ActionBar, StepHeading } from "./StepHeading";

/** Plan a layout: drag pieces on the model, see what's left to fix, and keep the plan without changing the scan. */
export function PlanPanel({ arrangement, before, onDone }: { arrangement: Arrangement; before: number; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  const left = arrangement.check ? arrangement.check.findings.filter((finding) => finding.outcome === "problem").length : before;
  const save = async () => setSaved(await arrangement.save());
  return (
    <div className="flex min-h-full flex-col gap-6">
      <StepHeading title="Plan a layout">Drag a piece of furniture on the model. We check the new layout each time you let go.</StepHeading>
      <PlanScore before={before} left={left} checking={arrangement.checking} moved={arrangement.hasMoves} />
      {arrangement.activeId && <TurnControls onTurn={(degrees) => arrangement.nudge(0, 0, degrees)} />}
      {arrangement.problem && <p role="alert" className="text-problem">{arrangement.problem}</p>}
      {saved && (
        <p role="status" className="flex items-center gap-2 font-medium text-pass">
          <CheckCircle size={20} weight="fill" aria-hidden />
          Saved. Move the real furniture, then walk the shop again to update your results.
        </p>
      )}
      <ActionBar>
        <Button variant="primary" className="justify-center" disabled={!arrangement.canSave} onClick={save}>
          {arrangement.saving ? "Saving" : "Save this plan"}
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <Button className="justify-center" disabled={!arrangement.hasMoves} onClick={arrangement.reset}>
            <ArrowCounterClockwise size={18} weight="bold" aria-hidden />
            Put it all back
          </Button>
          <Button className="justify-center" onClick={onDone}>Done</Button>
        </div>
      </ActionBar>
    </div>
  );
}

function PlanScore({ before, left, checking, moved }: { before: number; left: number; checking: boolean; moved: boolean }) {
  const better = moved && left < before;
  return (
    <p aria-live="polite" className={`flex items-baseline gap-3 rounded-2xl p-4 ${better ? "bg-pass/10" : "bg-sheet shadow-float"}`}>
      <span className={`text-4xl font-semibold tabular-nums ${better ? "text-pass" : ""}`}>{checking ? "…" : left}</span>
      <span className="text-lg">{checking ? "Checking the layout" : `${left === 1 ? "thing" : "things"} to fix with this layout`}</span>
    </p>
  );
}

const TURN_STEP_DEGREES = 15;

/** Turning a piece on a phone, where there's no keyboard: a step either way, checked like a drag. */
function TurnControls({ onTurn }: { onTurn: (degrees: number) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2" role="group" aria-label="Turn the piece you moved">
      <Button variant="choice" className="justify-center" onClick={() => onTurn(TURN_STEP_DEGREES)}>
        <ArrowCounterClockwise size={18} weight="bold" aria-hidden />
        Turn left
      </Button>
      <Button variant="choice" className="justify-center" onClick={() => onTurn(-TURN_STEP_DEGREES)}>
        <ArrowClockwise size={18} weight="bold" aria-hidden />
        Turn right
      </Button>
    </div>
  );
}
