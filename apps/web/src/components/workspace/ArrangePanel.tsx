"use client";

import { ArrowCounterClockwise, CircleNotch } from "@phosphor-icons/react";
import { blockedSentence } from "@/lib/blocked-copy";
import { groupFindings } from "@/lib/findings";
import type { Finding } from "@/types/contracts";
import { Button } from "@/components/ui/Button";
import type { Arrangement } from "./useArrangement";
import { FindingsList } from "./FindingsList";

function Status({ arrangement, problems }: { arrangement: Arrangement; problems: number }) {
  if (arrangement.checking) {
    return (
      <p className="flex items-center gap-2 font-medium" role="status">
        <CircleNotch size={18} className="animate-spin text-ink-muted" aria-hidden />
        Checking the new layout
      </p>
    );
  }
  if (!arrangement.check) {
    return <p className="text-ink-muted">Drag a table or case to move it. Press R to turn the one you picked.</p>;
  }
  if (problems === 0 && arrangement.check.blocked.length === 0) {
    return <p className="font-semibold text-pass" role="status">This layout passes every check</p>;
  }
  return (
    <p className="font-semibold" role="status">
      {problems === 1 ? "1 thing still to fix" : `${problems} things still to fix`}
    </p>
  );
}

export function ArrangePanel({ arrangement, fallbackFindings }: { arrangement: Arrangement; fallbackFindings: Finding[] }) {
  const findings = arrangement.check?.findings ?? fallbackFindings;
  const groups = groupFindings(findings);

  return (
    <div className="flex flex-col gap-5">
      <div className="px-3">
        <Status arrangement={arrangement} problems={groups.problems.length} />
        {arrangement.check?.blocked.map((blocked) => (
          <p key={`${blocked.node_id}-${blocked.reason}`} className="mt-2 flex gap-2 text-problem">
            <span className="mt-2 size-2 shrink-0 rounded-full bg-problem" aria-hidden />
            {blockedSentence(blocked)}
          </p>
        ))}
        {arrangement.problem && <p className="mt-2 text-problem">{arrangement.problem}</p>}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" onClick={arrangement.save} disabled={!arrangement.canSave} className="disabled:opacity-40">
            {arrangement.saving ? "Saving" : "Save this layout"}
          </Button>
          {arrangement.hasMoves && (
            <Button onClick={arrangement.reset}>
              <ArrowCounterClockwise size={16} weight="bold" aria-hidden />
              Put everything back
            </Button>
          )}
        </div>
      </div>
      <FindingsList groups={groups} selectedId={null} onSelect={() => undefined} />
    </div>
  );
}
