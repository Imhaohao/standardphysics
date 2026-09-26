import type { ReactNode } from "react";
import { FloorPlan } from "@/components/FloorPlan";
import { OutcomeMatrix } from "@/components/workspace/OutcomeMatrix";
import { formatInches, groupFindings } from "@/lib/findings";
import { scopedSummary } from "@/lib/outcomes";
import type { Assessment, Finding, Report } from "@/types/contracts";
import { type Fact, FactList } from "./FactList";
import { splitQuestions } from "./reportCounts";
import { longDate } from "./reportDates";
import { WhatWeChecked } from "./WhatWeChecked";

function citation(finding: Finding) {
  const text = `${finding.citation.edition} ${finding.citation.section}`;
  return finding.citation.url ? <a href={finding.citation.url} className="underline decoration-rule underline-offset-2">{text}</a> : text;
}

function ProblemBlock({ finding }: { finding: Finding }) {
  const render = finding.locus?.render_url;
  return (
    <article className="grid gap-5 break-inside-avoid border-t border-rule py-8 sm:grid-cols-[minmax(0,15rem)_1fr]">
      {render ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={render} alt={`The spot where ${finding.title.toLowerCase()}`} className="aspect-[3/2] w-full rounded-lg bg-rule/40 object-cover" />
      ) : (
        <div className="hidden sm:block" />
      )}
      <div>
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="text-xl font-semibold leading-snug">{finding.title}</h3>
          {finding.measured_inches !== null && (
            <span className="measurement shrink-0 text-lg">{formatInches(finding.measured_inches)}</span>
          )}
        </div>
        <p className="mt-2 text-ink-muted">{finding.detail}</p>
        {finding.fix && <p className="mt-4 border-l-2 border-accent pl-3 font-medium">{finding.fix}</p>}
        <p className="mt-3 text-sm text-ink-faint">{citation(finding)}</p>
      </div>
    </article>
  );
}

function ProblemsSection({ problems }: { problems: Finding[] }) {
  if (problems.length === 0) return null;
  return (
    <section className="mt-12">
      <h2 className="heading-display text-2xl">What to fix</h2>
      <div className="mt-4">
        {problems.map((finding) => (
          <ProblemBlock key={finding.id} finding={finding} />
        ))}
      </div>
    </section>
  );
}

function NextStepsSection({ questions }: { questions: Finding[] }) {
  if (questions.length === 0) return null;
  return (
    <section className="mt-12 break-inside-avoid">
      <h2 className="heading-display text-2xl">Next steps</h2>
      <ol className="mt-4 flex list-decimal flex-col gap-4 pl-5">
        {questions.map((finding) => (
          <li key={finding.id}>
            <p className="font-semibold">{finding.title}</p>
            <p className="text-ink-muted">{finding.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function WhatThisIsNot() {
  return (
    <section className="mt-12 break-inside-avoid border-t border-rule pt-8">
      <h2 className="heading-display text-2xl">What this report is not</h2>
      <div className="mt-3 flex flex-col gap-3 text-ink-muted">
        <p>
          Standard Physics measures what the scan could see and compares it against the 2010 ADA
          Standards for Accessible Design.
        </p>
        <p>
          This is not an inspection and it is not legal advice. Only a Certified Access Specialist
          can inspect your shop in person, and only their report carries legal weight. Fixing what
          is listed here first makes that inspection shorter and cheaper.
        </p>
      </div>
    </section>
  );
}

function PreviewNotice({ preview }: { preview: boolean }) {
  if (!preview) return null;
  return (
    <p className="mb-8 rounded-lg bg-ink px-4 py-3 font-semibold text-paper">
      Preview report. The rules in it are waiting for a person to review them.
    </p>
  );
}

function ScopedSection({ assessment }: { assessment: Assessment | null }) {
  const scope = assessment?.scope ?? null;
  if (scope === null) return null;
  const summary = scopedSummary(scope);
  return (
    <section className="mt-12 break-inside-avoid" aria-label="Scoped check outcomes">
      <h2 className="heading-display text-2xl">Scoped check outcomes</h2>
      {summary && <p className="mt-2 text-ink-muted">{summary}</p>}
      <div className="mt-4 border-t border-rule">
        <OutcomeMatrix scope={scope} findings={assessment?.findings ?? []} />
      </div>
    </section>
  );
}

function reportFacts(checkedOn: Date, problems: number, toSend: number, beingChecked: number): Fact[] {
  const facts: Fact[] = [
    { label: "Checked", value: longDate.format(checkedOn) },
    { label: "To fix", value: problems },
    { label: "To send", value: toSend },
  ];
  return beingChecked > 0 ? [...facts, { label: "Photos being checked", value: beingChecked }] : facts;
}

interface ReportDocumentProps {
  report: Report;
  /** The scoped-check matrix answers questions only the team asks. */
  showScope: boolean;
  /** Controls above the report, left out when it is printed. */
  toolbar: ReactNode;
}

/** The report an owner reads, prints and shares, the same wherever it opens. */
export function ReportDocument({ report, showScope, toolbar }: ReportDocumentProps) {
  const { scan, scene, scenario, assessment, rules } = report;
  const groups = groupFindings(assessment?.findings ?? []);
  const { toSend, beingChecked } = splitQuestions(groups.questions);
  const checkedOn = new Date(assessment?.created_at ?? scan.created_at);

  return (
    <main className="mx-auto max-w-3xl px-5 py-10 print:max-w-none print:p-0">
      <div className="mb-10 flex flex-wrap items-center justify-between gap-x-2 gap-y-3 print:hidden">{toolbar}</div>

      <PreviewNotice preview={report.preview} />
      <header className="grid items-end gap-6 sm:grid-cols-[1fr_9rem]">
        <div>
          <h1 className="heading-display text-4xl">{scan.name}</h1>
          <FactList className="mt-4" facts={reportFacts(checkedOn, groups.problems.length, toSend.length, beingChecked.length)} />
        </div>
        {scene && <FloorPlan scene={scene} className="hidden aspect-square w-full sm:block" />}
      </header>

      <ProblemsSection problems={groups.problems} />
      {showScope && <ScopedSection assessment={assessment} />}
      <NextStepsSection questions={toSend} />
      <WhatWeChecked scenario={scenario} passes={groups.passes} rules={rules} />
      <WhatThisIsNot />
    </main>
  );
}
