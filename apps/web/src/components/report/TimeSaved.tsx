import { facts } from "@/lib/facts";
import type { Assessment, Scan } from "@/types/contracts";
import { formatMinutes, inspectionBusinessDays, measurementsTaken, minutesToResults } from "./turnaround";

interface Panel {
  name: string;
  figure: string;
  rows: [string, string][];
}

function Figure({ panel, emphasis }: { panel: Panel; emphasis: boolean }) {
  const muted = emphasis ? "text-paper/70" : "text-ink-muted";
  return (
    <div className={`px-5 py-5 ${emphasis ? "bg-ink text-paper" : "bg-sheet"}`}>
      <p className={`text-sm ${muted}`}>{panel.name}</p>
      <p className="heading-display mt-2 text-5xl tabular-nums">{panel.figure}</p>
      <dl className={`mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm ${muted}`}>
        {panel.rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt>{label}</dt>
            <dd className={`tabular-nums ${emphasis ? "text-paper" : "text-ink"}`}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** How long this report took against a published inspection turnaround, both from recorded sources. */
export function TimeSaved({ scan, assessment }: { scan: Scan; assessment: Assessment | null }) {
  const minutes = minutesToResults(scan);
  if (minutes === null) return null;
  const days = inspectionBusinessDays();
  const { onSiteDays, reportBusinessDays } = facts.inspectionTurnaround;
  const panels: Panel[] = [
    {
      name: "An in-person inspection",
      figure: `${days.fewest}–${days.most} business days`,
      rows: [
        ["On site", onSiteDays === 1 ? "1 day" : `${onSiteDays} days`],
        ["Report", `${reportBusinessDays.fewest} to ${reportBusinessDays.most} business days later`],
      ],
    },
    {
      name: "This report",
      figure: formatMinutes(minutes),
      rows: [
        ["Rules checked", String(assessment?.rules_checked ?? 0)],
        ["Measurements taken", String(measurementsTaken(assessment))],
      ],
    },
  ];
  return (
    <section className="mt-16 break-inside-avoid" aria-labelledby="time-saved">
      <h2 id="time-saved" className="heading-display text-3xl">Time saved</h2>
      <p className="mt-3 max-w-prose text-lg">
        This report was ready {formatMinutes(minutes).toLowerCase()} after the scan arrived, {days.fewest} to {days.most}{" "}
        business days sooner than an in-person inspection report.
      </p>
      <div className="mt-6 grid gap-px border border-ink bg-ink sm:grid-cols-2">
        {panels.map((panel, index) => <Figure key={panel.name} panel={panel} emphasis={index === 1} />)}
      </div>
      <p className="mt-4 max-w-prose text-sm text-ink-muted">
        The inspection turnaround is the one{" "}
        <a href={facts.inspectionTurnaround.url} className="underline decoration-rule underline-offset-2 hover:decoration-ink">
          Proactive Access
        </a>
        , a California Certified Access Specialist firm, publishes. The time here runs from the scan&rsquo;s upload to
        its first checked results.
      </p>
    </section>
  );
}
