import type { Metadata } from "next";
import { FindingPairTable } from "@/components/report/FindingPairTable";
import { OwnerQuestions } from "@/components/report/OwnerQuestions";
import { PrintButton } from "@/components/report/PrintButton";
import { InkedPlan } from "@/components/plan/InkedPlan";
import { SHEET_GRID_CLASS, SheetField } from "@/components/sheet/SheetField";
import { SheetPage } from "@/components/sheet/SheetPage";
import { ShopHeader } from "@/components/shop/ShopHeader";
import { StatusMark } from "@/components/ui/StatusMark";
import { ownerQuestions, type ElementGroup } from "@/lib/findings/group";
import { findingPins, pinLabels } from "@/lib/findings/pins";
import { loadOwnedShop } from "@/lib/loadShop";
import { shopName } from "@/lib/shopSheet";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: PageProps<"/shops/[scanId]/report">): Promise<Metadata> {
  const { sheet } = await loadOwnedShop((await params).scanId);
  return { title: `Accessibility report for ${shopName(sheet.scan)}` };
}

const dateFormat = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

function countWhere(groups: ElementGroup[], status: ElementGroup["status"]) {
  return groups.filter((group) => group.status === status).length;
}

function ElementSection({ group, label }: { group: ElementGroup; label: string | undefined }) {
  return (
    <section aria-labelledby={`element-${group.subjectId}`} data-ink-avoid className="border border-ink bg-paper break-inside-avoid-page">
      <h3 id={`element-${group.subjectId}`} className="flex flex-wrap items-center justify-between gap-3 border-b border-ink px-4 py-3">
        <span className="heading-display text-xl">{label ? `${label}. ${group.name}` : group.name}</span>
        <StatusMark status={group.status} />
      </h3>
      <FindingPairTable pairs={group.pairs} />
    </section>
  );
}

export default async function ReportPage({ params }: PageProps<"/shops/[scanId]/report">) {
  const { sheet } = await loadOwnedShop((await params).scanId);
  const { scan, scene, report, groups } = sheet;
  const pins = findingPins(groups);
  const labels = pinLabels(pins);
  return (
    <SheetPage className="flex flex-col gap-8">
      <ShopHeader backHref={sheet.href} backLabel={`Back to ${shopName(scan)}`} title={`Accessibility report for ${shopName(scan)}`}>
        <PrintButton />
      </ShopHeader>
      {!report ? (
        <p data-ink-avoid className="text-lg text-ink-muted">This shop hasn&rsquo;t been checked yet. The report appears here within a minute of the scan finishing.</p>
      ) : (
        <>
          <dl data-ink-avoid className={`${SHEET_GRID_CLASS} border border-ink *:bg-paper sm:grid-cols-4`}>
            <SheetField label="Checked">{dateFormat.format(new Date(report.created_at))}</SheetField>
            <SheetField label="Needs fixing">{countWhere(groups, "fail")}</SheetField>
            <SheetField label="Questions for you">{countWhere(groups, "needs_info")}</SheetField>
            <SheetField label="Meets every rule">{countWhere(groups, "pass")}</SheetField>
          </dl>
          <p className="max-w-3xl text-pretty text-ink-muted">
            We checked each element against the 2010 ADA Standards and California&rsquo;s Building Code, Chapter 11B. Where the two
            disagree, the stricter rule is the one your shop has to meet, and California&rsquo;s Unruh Act lets customers enforce it.
          </p>
          {scene && (
            <section aria-label="Floor plan with numbered findings" data-ink-avoid className="border border-ink bg-paper break-inside-avoid">
              <InkedPlan scene={scene} name="report" pins={pins} showNotes={false} className="drafting-grid h-[26rem] print:h-[22rem]" />
            </section>
          )}
          <OwnerQuestions questions={ownerQuestions(groups)} labels={labels} />
          <section aria-labelledby="elements-heading" className="flex flex-col gap-6">
            <h2 id="elements-heading" className="heading-display text-3xl">
              Every element we checked
            </h2>
            {groups.map((group) => (
              <ElementSection key={group.subjectId} group={group} label={labels.get(group.subjectId)} />
            ))}
          </section>
        </>
      )}
    </SheetPage>
  );
}
