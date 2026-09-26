import { formatInches } from "@/lib/findings";
import type { Finding, ReviewedRule, Scenario } from "@/types/contracts";
import { longDate } from "./reportDates";

function legs(scenario: Scenario | null): string[] {
  if (!scenario) return [];
  return scenario.stops.slice(1).map((stop, index) => `${scenario.stops[index].name} to ${stop.name}`);
}

function threshold(rule: ReviewedRule): string {
  const { threshold: value, unit } = rule.check;
  return unit === "in" ? formatInches(value) : `${value} ${unit}`;
}

function RulesTable({ rules }: { rules: ReviewedRule[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-ink-muted">
          <tr>
            <th className="py-2 pr-4 font-semibold">Section</th>
            <th className="py-2 pr-4 font-semibold">Check</th>
            <th className="py-2 pr-4 font-semibold">Standard</th>
            <th className="py-2 font-semibold">Reviewed by</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.check.id} className="border-t border-rule align-top">
              <td className="measurement whitespace-nowrap py-2 pr-4">{rule.check.citation.section}</td>
              <td className="py-2 pr-4">{rule.check.title}</td>
              <td className="measurement whitespace-nowrap py-2 pr-4">{threshold(rule)}</td>
              <td className="py-2">
                {rule.verified_by}, {longDate.format(new Date(rule.verified_at))}
                {rule.second_check_by && <span className="block text-ink-muted">Second check: {rule.second_check_by}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PathsMeasured({ scenario }: { scenario: Scenario | null }) {
  const measured = legs(scenario);
  if (measured.length === 0) return null;
  return (
    <>
      <h3 className="mt-6 font-semibold">Paths measured</h3>
      <ul className="mt-2 flex flex-wrap gap-2">
        {measured.map((leg) => (
          <li key={leg} className="rounded-md bg-rule/50 px-2.5 py-1 text-sm">{leg}</li>
        ))}
      </ul>
    </>
  );
}

function WhatPasses({ passes }: { passes: Finding[] }) {
  if (passes.length === 0) return null;
  return (
    <>
      <h3 className="mt-6 font-semibold">What passes</h3>
      <ul className="mt-2 flex flex-col gap-1">
        {passes.map((finding) => (
          <li key={finding.id}>{finding.title}</li>
        ))}
      </ul>
    </>
  );
}

function RulesReviewed({ rules }: { rules: ReviewedRule[] }) {
  if (rules.length === 0) return null;
  return (
    <>
      <h3 className="mt-6 font-semibold">Rules and who reviewed them</h3>
      <div className="mt-2">
        <RulesTable rules={rules} />
      </div>
    </>
  );
}

export function WhatWeChecked({ scenario, passes, rules }: { scenario: Scenario | null; passes: Finding[]; rules: ReviewedRule[] }) {
  return (
    <section className="mt-12 break-inside-avoid">
      <h2 className="heading-display text-2xl">What we checked</h2>
      <PathsMeasured scenario={scenario} />
      <WhatPasses passes={passes} />
      <RulesReviewed rules={rules} />
    </section>
  );
}
