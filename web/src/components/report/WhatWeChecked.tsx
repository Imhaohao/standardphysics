import { CaretDown } from "@phosphor-icons/react/dist/ssr";
import type { JurisdictionCoverage } from "@/lib/coverage";

function CountsTable({ coverage }: { coverage: JurisdictionCoverage[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[36rem] border-collapse text-left">
        <thead>
          <tr className="border-b border-ink text-sm text-ink-muted">
            <th scope="col" className="px-4 py-2 font-medium">Code</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Tested by our rules</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Doesn&rsquo;t apply to a shop&rsquo;s customer areas</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Not checked yet</th>
          </tr>
        </thead>
        <tbody>
          {coverage.map((entry) => (
            <tr key={entry.jurisdiction} className="border-b border-ink/20 last:border-b-0">
              <th scope="row" className="px-4 py-3 font-semibold">{entry.name}</th>
              <td className="measurement px-4 py-3 text-right text-lg">{entry.covered}</td>
              <td className="measurement px-4 py-3 text-right text-lg">{entry.notApplicable}</td>
              <td className="measurement px-4 py-3 text-right text-lg text-attention">{entry.deferred.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeferredList({ coverage }: { coverage: JurisdictionCoverage[] }) {
  const total = coverage.reduce((sum, entry) => sum + entry.deferred.length, 0);
  return (
    <details className="group border-t border-ink">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 font-medium hover:bg-ink/5 [&::-webkit-details-marker]:hidden">
        See the {total} sections we don&rsquo;t check yet, and why
        <CaretDown size={18} weight="bold" aria-hidden className="shrink-0 transition-transform duration-150 group-open:rotate-180" />
      </summary>
      {coverage.map((entry) => (
        <section key={entry.jurisdiction} aria-label={`${entry.name} sections not checked yet`} className="border-t border-ink/20">
          <h3 className="px-4 pt-3 font-semibold">{entry.name}</h3>
          <ul className="divide-y divide-ink/10">
            {entry.deferred.map((section) => (
              <li key={`${section.citation} ${section.title}`} className="grid gap-x-4 gap-y-0.5 px-4 py-2.5 sm:grid-cols-[8rem_minmax(0,1fr)]">
                <span className="font-semibold tabular-nums">{section.citation}</span>
                <span className="flex min-w-0 flex-col">
                  <span>{section.title}</span>
                  <span className="text-sm text-ink-muted text-pretty">{section.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </details>
  );
}

/**
 * How much of each code the rulepack covers, so a clean report isn't read as a clean bill of health. Sections that
 * aren't checked yet sit behind a disclosure with the rulepack's reason for each.
 */
export function WhatWeChecked({ coverage }: { coverage: JurisdictionCoverage[] }) {
  return (
    <section aria-labelledby="coverage-heading" className="flex flex-col gap-4 break-inside-avoid-page">
      <h2 id="coverage-heading" className="heading-display text-3xl">
        What we checked
      </h2>
      <p className="max-w-3xl text-pretty text-ink-muted">
        Each code is split into numbered sections. This counts how many of them our rules test, how many don&rsquo;t apply to the customer areas
        of a small business, and how many we can&rsquo;t check from a scan yet. A section we don&rsquo;t check yet can still apply to your shop.
      </p>
      <div data-ink-avoid className="border border-ink bg-paper">
        <CountsTable coverage={coverage} />
        <DeferredList coverage={coverage} />
      </div>
    </section>
  );
}
