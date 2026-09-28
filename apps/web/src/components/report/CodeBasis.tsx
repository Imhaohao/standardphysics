import { CheckCircle, XCircle } from "@phosphor-icons/react/dist/ssr";
import { formatInches } from "@/lib/findings";
import type { Finding } from "@/types/contracts";
import type { ClauseRow } from "./redesign";

function Section({ finding }: { finding: Finding }) {
  const { section, url } = finding.citation;
  if (!url) return <span className="measurement font-semibold">{section}</span>;
  return <a href={url} className="measurement font-semibold underline decoration-rule underline-offset-2 hover:decoration-ink">{section}</a>;
}

function Outcome({ finding }: { finding: Finding | null }) {
  if (!finding) return <span className="text-ink-muted">Not measured</span>;
  const fails = finding.outcome === "problem";
  const Icon = fails ? XCircle : CheckCircle;
  return (
    <span className={`flex items-center gap-1.5 ${fails ? "text-problem" : "text-pass"}`}>
      <Icon size={18} weight="fill" aria-hidden className="shrink-0" />
      <span className="measurement text-ink">{finding.measured_inches === null ? "" : formatInches(finding.measured_inches)}</span>
      <span className="sr-only">{fails ? "fails" : "passes"}</span>
    </span>
  );
}

function Row({ row, planned }: { row: ClauseRow; planned: boolean }) {
  const finding = (row.before ?? row.after)!;
  return (
    <tr className="break-inside-avoid border-t border-rule align-top">
      <td className="py-3 pr-3 font-semibold tabular-nums">{row.number}</td>
      <td className="py-3 pr-4"><Section finding={finding} /></td>
      <td className="py-3 pr-4">{finding.title}</td>
      <td className="measurement whitespace-nowrap py-3 pr-4">{finding.required_inches === null ? "" : formatInches(finding.required_inches)}</td>
      <td className="whitespace-nowrap py-3 pr-4"><Outcome finding={row.before} /></td>
      {planned && <td className="whitespace-nowrap py-3"><Outcome finding={row.after} /></td>}
    </tr>
  );
}

interface CodeBasisProps {
  rows: ClauseRow[];
  planName: string | null;
}

/** Each failing spot against the section that sets its number, as scanned and as planned. */
export function CodeBasis({ rows, planName }: CodeBasisProps) {
  if (rows.length === 0) return null;
  return (
    <section className="mt-16 break-inside-avoid" aria-labelledby="code-basis">
      <h2 id="code-basis" className="heading-display text-3xl">Code basis</h2>
      <div className="relative mt-6 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left">
          <thead className="text-sm text-ink-muted">
            <tr>
              <th scope="col" className="py-2 pr-3 font-semibold"><span className="sr-only">Mark</span></th>
              <th scope="col" className="py-2 pr-4 font-semibold">Section</th>
              <th scope="col" className="py-2 pr-4 font-semibold">What the scan found</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Sets</th>
              <th scope="col" className="py-2 pr-4 font-semibold">As scanned</th>
              {planName && <th scope="col" className="py-2 font-semibold">{planName}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => <Row key={row.number} row={row} planned={planName !== null} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}
