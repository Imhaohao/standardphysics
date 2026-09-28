import { HourglassMedium } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import type { ReactNode } from "react";
import { OutcomeMatrix } from "@/components/workspace/OutcomeMatrix";
import { formatInches, groupFindings } from "@/lib/findings";
import { applyMoves } from "@/lib/moves";
import { scopedSummary } from "@/lib/outcomes";
import type { Assessment, Finding, LayoutPlan, Report, SceneGraph } from "@/types/contracts";
import { BeforeAfter } from "./BeforeAfter";
import { CodeBasis } from "./CodeBasis";
import { ExecutiveSummary } from "./ExecutiveSummary";
import { ModelSection } from "./ModelSection";
import { MoneyAtStake } from "./MoneyAtStake";
import { MoveSchedule } from "./MoveSchedule";
import { choosePlan, compareClauses, moveSchedule, type ClauseRow } from "./redesign";
import { beingCheckedNames, splitQuestions } from "./reportCounts";
import { ReportCover } from "./ReportCover";
import { TimeSaved } from "./TimeSaved";
import { WhatWeChecked } from "./WhatWeChecked";
import { Wordmark } from "./Wordmark";

function citation(finding: Finding) {
  const text = `${finding.citation.edition} ${finding.citation.section}`;
  return finding.citation.url ? <a href={finding.citation.url} className="underline decoration-rule underline-offset-2">{text}</a> : text;
}

function ProblemBlock({ finding, number }: { finding: Finding; number: number }) {
  const render = finding.locus?.render_url;
  return (
    <article className={`grid gap-5 break-inside-avoid border-t border-rule py-8 ${render ? "sm:grid-cols-[minmax(0,18rem)_1fr]" : ""}`}>
      {render && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={render} alt={`The spot where ${finding.title.toLowerCase()}`} className="aspect-[3/2] w-full bg-rule/40 object-cover" />
      )}
      <div>
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="text-xl font-semibold leading-snug">
            <span className="me-2 tabular-nums text-problem">{number}</span>
            {finding.title}
          </h3>
          {finding.measured_inches !== null && (
            <span className="measurement shrink-0 text-lg">{formatInches(finding.measured_inches)}</span>
          )}
        </div>
        <p className="mt-2 text-ink-muted">{finding.detail}</p>
        {finding.fix && <p className="mt-4 border-l-2 border-accent pl-3 font-medium">{finding.fix}</p>}
        <p className="mt-3 text-sm text-ink-muted">{citation(finding)}</p>
      </div>
    </article>
  );
}

function ProblemsSection({ rows }: { rows: ClauseRow[] }) {
  const failing = rows.filter((row) => row.change !== "new_problem" && row.before);
  if (failing.length === 0) return null;
  return (
    <section className="mt-16 print:mt-0 print:break-before-page">
      <h2 className="heading-display text-3xl">What to fix</h2>
      <div className="mt-4">
        {failing.map((row) => (
          <ProblemBlock key={row.number} finding={row.before!} number={row.number} />
        ))}
      </div>
    </section>
  );
}

function StepsToSend({ toSend }: { toSend: Finding[] }) {
  if (toSend.length === 0) return null;
  return (
    <ol className="mt-4 flex list-decimal flex-col gap-4 pl-5">
      {toSend.map((finding) => (
        <li key={finding.id} className="break-inside-avoid">
          <p className="font-semibold">{finding.title}</p>
          <p className="text-ink-muted">{finding.detail}</p>
        </li>
      ))}
    </ol>
  );
}

function PhotosBeingChecked({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div className="mt-8 break-inside-avoid">
      <h3 className="font-semibold">Photos being checked</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {names.map((name, index) => (
          <li key={`${index}-${name}`} className="flex items-start gap-2">
            <HourglassMedium size={20} className="mt-0.5 shrink-0 text-attention" aria-hidden />
            {name}
          </li>
        ))}
      </ul>
    </div>
  );
}

function NextStepsSection({ toSend, beingChecked }: { toSend: Finding[]; beingChecked: string[] }) {
  if (toSend.length + beingChecked.length === 0) return null;
  return (
    <section className="mt-16">
      <h2 className="heading-display break-after-avoid text-3xl">Next steps</h2>
      <StepsToSend toSend={toSend} />
      <PhotosBeingChecked names={beingChecked} />
    </section>
  );
}

function Disclaimer() {
  return (
    <footer className="mt-16 break-inside-avoid border-t border-rule pt-6 text-sm text-ink-muted">
      <p className="max-w-prose">
        Standard Physics measures what the scan could see and compares it against the 2010 ADA Standards. This report
        is not an inspection and not legal advice. Only a Certified Access Specialist can inspect the shop in person,
        and only their report carries legal weight.
      </p>
      <nav aria-label="Terms and privacy" className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
        <Link href="/terms" className="underline decoration-rule underline-offset-2 hover:text-ink">Terms of use</Link>
        <Link href="/privacy" className="underline decoration-rule underline-offset-2 hover:text-ink">Privacy policy</Link>
      </nav>
      <p className="mt-2 hidden print:block">standardphysics.app/terms and standardphysics.app/privacy</p>
    </footer>
  );
}

function PreviewNotice({ preview }: { preview: boolean }) {
  if (!preview) return null;
  return (
    <p className="mb-6 flex items-start gap-3 border-l-4 border-attention bg-attention/10 px-4 py-3">
      <HourglassMedium size={20} className="mt-0.5 shrink-0 text-attention" aria-hidden />
      This is a preview report. The rules in it are waiting for a person to review them.
    </p>
  );
}

function ScopedSection({ assessment }: { assessment: Assessment | null }) {
  const scope = assessment?.scope ?? null;
  if (scope === null) return null;
  const summary = scopedSummary(scope);
  return (
    <section className="mt-16 break-inside-avoid" aria-label="Scoped check outcomes">
      <h2 className="heading-display text-3xl">Scoped check outcomes</h2>
      {summary && <p className="mt-2 text-ink-muted">{summary}</p>}
      <div className="mt-4 border-t border-rule">
        <OutcomeMatrix scope={scope} findings={assessment?.findings ?? []} />
      </div>
    </section>
  );
}

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "shop";
}

interface ReportDocumentProps {
  report: Report;
  /** The scoped-check matrix answers questions only the team asks. */
  showScope: boolean;
  /** Controls above the report, left out when it is printed. */
  toolbar: ReactNode;
  /** The layout the reader picked; without one, the layout that clears the most is shown. */
  planId?: string;
  /** This page's own address, which the layout picker adds `?plan=` to. */
  pagePath: string;
  /** Where this reader downloads the room as STL. */
  modelBase: string;
}

function planned(scene: SceneGraph, plan: LayoutPlan | null): SceneGraph {
  return plan ? applyMoves(scene, Object.fromEntries(plan.moves.map((move) => [move.node_id, move]))) : scene;
}

function redesignOf(report: Report, planId: string | undefined) {
  const scene = report.scene;
  const plan = scene ? choosePlan(report.plans, planId) : null;
  const rows = compareClauses(report.assessment?.findings ?? [], plan?.findings ?? null);
  if (!scene || !plan) return { plan: null, planName: null, rows, schedule: [], shown: scene };
  return { plan, planName: plan.name, rows, schedule: moveSchedule(scene, plan, rows), shown: planned(scene, plan) };
}

function Drawings({ report, redesign, hrefFor, modelBase }: {
  report: Report;
  redesign: ReturnType<typeof redesignOf>;
  hrefFor: (planId: string) => string;
  modelBase: string;
}) {
  const { scene, scan } = report;
  if (!scene) return null;
  const { plan, rows } = redesign;
  return (
    <>
      {plan && <BeforeAfter scene={scene} plans={report.plans} plan={plan} rows={rows} hrefFor={hrefFor} />}
      <CodeBasis rows={rows} planName={redesign.planName} />
      {plan && <MoveSchedule schedule={redesign.schedule} planName={plan.name} />}
      <MoneyAtStake rows={rows} schedule={redesign.schedule} planName={redesign.planName} />
      <TimeSaved scan={scan} assessment={report.assessment} />
      <ModelSection scene={scene} plan={plan} modelBase={modelBase} fileStem={slug(scan.name)} />
    </>
  );
}

/** The report an owner reads, prints and hands to an architect, the same wherever it opens. */
export function ReportDocument({ report, showScope, toolbar, planId, pagePath, modelBase }: ReportDocumentProps) {
  const { scan, scene, scenario, assessment, rules } = report;
  const groups = groupFindings(assessment?.findings ?? []);
  const { toSend, beingChecked } = splitQuestions(groups.questions);
  const redesign = redesignOf(report, planId);
  const hrefFor = (id: string) => `${pagePath}?plan=${encodeURIComponent(id)}`;

  return (
    <main className="mx-auto max-w-6xl px-5 py-10 print:max-w-none print:p-0">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-x-2 gap-y-3 print:hidden">{toolbar}</div>
      <Wordmark className="mb-6 hidden print:block" />

      <PreviewNotice preview={report.preview} />
      <ReportCover scan={scan} scene={scene} shown={redesign.shown} plan={redesign.plan} assessment={assessment} />
      <ExecutiveSummary rows={redesign.rows} plan={redesign.plan} schedule={redesign.schedule} openQuestions={groups.questions.length} />
      <Drawings report={report} redesign={redesign} hrefFor={hrefFor} modelBase={modelBase} />
      <ProblemsSection rows={redesign.rows} />
      {showScope && <ScopedSection assessment={assessment} />}
      <NextStepsSection toSend={toSend} beingChecked={beingCheckedNames(beingChecked, rules)} />
      <WhatWeChecked scenario={scenario} passes={groups.passes} rules={rules} preview={report.preview} />
      <Disclaimer />
    </main>
  );
}
