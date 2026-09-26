"use client";

import { Check, Hourglass } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { type ChecklistStatus, thingsToFix } from "@/lib/owner-journey";
import { useSeenOnce } from "@/lib/seen-once";
import type { Finding } from "@/types/contracts";
import { type CardActions, FindingCard } from "./FindingCard";
import { ActionBar } from "./StepHeading";

export type Row = { finding: Finding; status: ChecklistStatus };

/**
 * The results and the checklist are one list. Before the owner starts fixing,
 * it counts what to fix; after, each card carries its status and the header
 * counts what's done.
 */
export function ResultsPanel({ rows, selectedId, fixing, saving, actions, onStartFixing, readOnly, footer, stillToCheck, pending, children }: {
  rows: Row[];
  selectedId: string | null;
  fixing: boolean;
  saving: boolean;
  actions: CardActions;
  onStartFixing: () => void;
  readOnly: boolean;
  footer?: ReactNode;
  /** The questions the checks couldn't settle yet, shown after the list. */
  stillToCheck?: ReactNode;
  /** How many of those there are, so a shop with none to fix isn't called clear while some wait. */
  pending: number;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-full flex-col gap-6">
      {fixing ? <Progress rows={rows} /> : <Count count={rows.length} pending={pending} />}
      {rows.length > 0 && <FirstResultsTip />}
      <ul className="flex flex-col gap-4">
        {rows.map(({ finding, status }) => (
          <li key={finding.id}>
            <FindingCard finding={finding} selected={finding.id === selectedId} status={status} fixing={fixing && !readOnly} saving={saving} actions={actions} />
          </li>
        ))}
      </ul>
      {stillToCheck}
      {footer}
      {children}
      {!fixing && !readOnly && rows.length > 0 && (
        <ActionBar>
          <Button variant="primary" className="justify-center" onClick={onStartFixing}>Start fixing</Button>
        </ActionBar>
      )}
    </div>
  );
}

/** The count sits in the mark, so the words beside it don't repeat the number. */
function Count({ count, pending }: { count: number; pending: number }) {
  if (count === 0) {
    const clear = pending === 0;
    return (
      <header className="flex items-center gap-4">
        <span className={`grid size-14 shrink-0 place-items-center rounded-full ${clear ? "bg-pass/15 text-pass" : "bg-ink/[0.06] text-ink-muted"}`} aria-hidden>
          {clear ? <Check size={28} weight="bold" /> : <Hourglass size={26} weight="bold" />}
        </span>
        <h1 className="heading-display text-3xl">{clear ? thingsToFix(0) : "Nothing to fix so far"}</h1>
      </header>
    );
  }
  return (
    <header className="flex items-center gap-4">
      <span className="grid size-14 shrink-0 place-items-center rounded-full bg-problem/10 text-2xl font-semibold tabular-nums text-problem" aria-hidden>{count}</span>
      <h1 className="heading-display text-3xl"><span className="sr-only">{count} </span>{count === 1 ? "thing to fix" : "things to fix"}</h1>
    </header>
  );
}

/** How far through the list the owner is: one segment per item, filled once it has a status. */
function Progress({ rows }: { rows: Row[] }) {
  const done = rows.filter((row) => row.status !== "to_do").length;
  return (
    <header className="flex flex-col gap-3">
      <h1 className="heading-display text-3xl">{done} of {rows.length} done</h1>
      <div className="flex gap-1" aria-hidden>
        {rows.map(({ finding, status }) => (
          <span key={finding.id} className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${status === "to_do" ? "bg-ink/10" : "bg-pass"}`} />
        ))}
      </div>
    </header>
  );
}

function FirstResultsTip() {
  const [seen, markSeen] = useSeenOnce("sp_results_tip");
  if (seen) return null;
  return (
    <aside className="flex items-start gap-3 rounded-2xl bg-ink p-4 text-paper">
      <p className="flex-1 text-pretty">Red means it misses the ADA number. Tap one to see where it is.</p>
      <Button variant="inverse" className="shrink-0" onClick={markSeen}>Got it</Button>
    </aside>
  );
}
