import type { LayoutPlan } from "@/types/contracts";
import type { ClauseRow, ScheduledMove } from "./redesign";
import { constructionSentence, measuredAgainst, remedy, tally, verdict } from "./redesignCopy";

interface Stat {
  label: string;
  value: number;
}

function stats(rows: ClauseRow[], plan: LayoutPlan | null, openQuestions: number): Stat[] {
  const count = tally(rows);
  const scanned = { label: "Failing as scanned", value: count.failing };
  const questions = { label: "Still to answer", value: openQuestions };
  if (!plan) return [scanned, questions];
  return [
    scanned,
    { label: `Failing in ${plan.name}`, value: count.failing - count.cleared + count.broken },
    { label: "Pieces moved", value: plan.moves.length },
    questions,
  ];
}

const STAT_COLUMNS: Record<number, string> = { 2: "grid-cols-2", 4: "grid-cols-2 sm:grid-cols-4" };

function Stats({ items }: { items: Stat[] }) {
  return (
    <dl className={`mt-8 grid gap-px border border-ink bg-ink ${STAT_COLUMNS[items.length]}`}>
      {items.map((stat) => (
        <div key={stat.label} className="bg-sheet px-4 py-3">
          <dt className="text-sm text-ink-muted">{stat.label}</dt>
          <dd className="heading-display mt-1 text-4xl tabular-nums">{stat.value}</dd>
        </div>
      ))}
    </dl>
  );
}

const BADGE: Record<ClauseRow["change"], string> = {
  cleared: "bg-sheet text-pass ring-2 ring-pass ring-inset",
  still_fails: "bg-problem text-sheet",
  new_problem: "bg-problem text-sheet",
};

function Reason({ row, schedule, planName }: { row: ClauseRow; schedule: ScheduledMove[]; planName: string | null }) {
  const finding = (row.before ?? row.after)!;
  const answer = remedy(row, schedule, planName);
  return (
    <li className="grid break-inside-avoid grid-cols-[2rem_1fr] gap-x-3">
      <span className={`flex size-8 items-center justify-center rounded-full font-semibold tabular-nums ${BADGE[row.change]}`}>{row.number}</span>
      <div>
        <p className="font-semibold">{finding.title}</p>
        <p className="text-ink-muted">{measuredAgainst(finding)}</p>
        {answer && <p className="mt-1">{answer}</p>}
      </div>
    </li>
  );
}

interface ExecutiveSummaryProps {
  rows: ClauseRow[];
  plan: LayoutPlan | null;
  schedule: ScheduledMove[];
  openQuestions: number;
}

/** The answer first: what fails, what the layout does about it, and why each change is there. */
export function ExecutiveSummary({ rows, plan, schedule, openQuestions }: ExecutiveSummaryProps) {
  const planName = plan?.name ?? null;
  return (
    <section className="mt-12" aria-labelledby="summary">
      <h2 id="summary" className="sr-only">Summary</h2>
      <p className="heading-display max-w-4xl text-3xl text-balance sm:text-4xl">{verdict(rows, planName)}</p>
      {plan && rows.length > 0 && <p className="mt-3 max-w-prose text-lg">{constructionSentence(schedule)}</p>}
      <Stats items={stats(rows, plan, openQuestions)} />
      {rows.length > 0 && (
        <ol className="mt-8 grid gap-6 md:grid-cols-2">
          {rows.map((row) => <Reason key={row.number} row={row} schedule={schedule} planName={planName} />)}
        </ol>
      )}
    </section>
  );
}
