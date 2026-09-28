import { facts } from "@/lib/facts";
import type { ClauseRow, ScheduledMove } from "./redesign";
import { tally } from "./redesignCopy";

const dollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const wholeNumber = new Intl.NumberFormat("en-US");
const MINIMUM = facts.californiaMinimumDamages.value;

function exposure(failing: number): string {
  return failing > 0 ? dollars.format(MINIMUM) : dollars.format(0);
}

function Source({ fact, children }: { fact: { url: string }; children: string }) {
  return <a href={fact.url} className="underline decoration-rule underline-offset-2 hover:decoration-ink">{children}</a>;
}

interface Column {
  name: string;
  failing: number;
  construction: string;
}

function Figure({ column, emphasis }: { column: Column; emphasis: boolean }) {
  return (
    <div className={`px-5 py-5 ${emphasis ? "bg-ink text-paper" : "bg-sheet"}`}>
      <p className={`text-sm ${emphasis ? "text-paper/70" : "text-ink-muted"}`}>{column.name}</p>
      <p className="heading-display mt-2 text-5xl tabular-nums">{exposure(column.failing)}</p>
      <dl className={`mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm ${emphasis ? "text-paper/70" : "text-ink-muted"}`}>
        <dt>Failing spots</dt>
        <dd className={`tabular-nums ${emphasis ? "text-paper" : "text-ink"}`}>{column.failing}</dd>
        <dt>Construction</dt>
        <dd className={emphasis ? "text-paper" : "text-ink"}>{column.construction}</dd>
      </dl>
    </div>
  );
}

interface MoneyAtStakeProps {
  rows: ClauseRow[];
  schedule: ScheduledMove[];
  planName: string | null;
}

/**
 * The statutory minimum for one turned-away visit, as scanned and as planned.
 * California counts visits rather than barriers, so the figure is never a
 * barrier count times the minimum: it stays whole until the last spot clears.
 */
export function MoneyAtStake({ rows, schedule, planName }: MoneyAtStakeProps) {
  const count = tally(rows);
  const columns: Column[] = [{ name: "As scanned", failing: count.failing, construction: "None yet" }];
  if (planName) {
    const construction = schedule.some((move) => move.builtIn) ? "Needed for built-in pieces" : "None, furniture only";
    columns.push({ name: planName, failing: count.failing - count.cleared + count.broken, construction });
  }
  return (
    <section className="mt-16 break-inside-avoid" aria-labelledby="money-at-stake">
      <h2 id="money-at-stake" className="heading-display text-3xl">Money at stake per visit</h2>
      <div className={`mt-6 grid gap-px border border-ink bg-ink ${columns.length > 1 ? "sm:grid-cols-2" : ""}`}>
        {columns.map((column, index) => <Figure key={column.name} column={column} emphasis={index === columns.length - 1 && columns.length > 1} />)}
      </div>
      <div className="mt-4 max-w-prose text-ink-muted">
        <p>
          California awards at least {dollars.format(MINIMUM)} each time a customer is denied access, plus their legal
          fees (<Source fact={facts.californiaMinimumDamages}>Civil Code § 52(a)</Source>). It counts visits rather than
          barriers (<Source fact={facts.damagesCountedPerVisit}>§ 55.56(f)</Source>), so one failing spot carries the same
          exposure as five, and it ends only when the last one clears.
        </p>
        <p className="mt-3">
          Of the {wholeNumber.format(facts.casesWithMoneyPercent.caseReports)} California accessibility cases in the
          state&rsquo;s <Source fact={facts.casesWithMoneyPercent}>2025 annual report</Source>,{" "}
          {facts.casesWithMoneyPercent.value}% ended with money paid.
        </p>
      </div>
    </section>
  );
}
