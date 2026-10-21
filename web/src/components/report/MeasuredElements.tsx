import { FindingPairTable } from "@/components/report/FindingPairTable";
import { StatusMark } from "@/components/ui/StatusMark";
import type { ElementGroup } from "@/lib/findings/group";

const measuredPairs = (group: ElementGroup) => group.pairs.filter((pair) => pair.governing.status !== "needs_info");

function ElementSection({ group, label }: { group: ElementGroup; label: string | undefined }) {
  const pairs = measuredPairs(group);
  const questions = group.pairs.length - pairs.length;
  return (
    <section aria-labelledby={`element-${group.subjectId}`} data-ink-avoid className="border border-ink bg-paper break-inside-avoid-page">
      <h3 id={`element-${group.subjectId}`} className="flex flex-wrap items-center justify-between gap-3 border-b border-ink px-4 py-3">
        <span className="heading-display text-xl">{label ? `${label}. ${group.name}` : group.name}</span>
        <StatusMark status={group.status} />
      </h3>
      <FindingPairTable pairs={pairs} />
      {questions > 0 && (
        <p className="px-4 py-3 text-sm text-ink-muted">
          {questions === 1 ? "One more check on this needs" : `${questions} more checks on this need`} an answer from you, listed under Questions for you.
        </p>
      )}
    </section>
  );
}

/** Every element with at least one measured result, each requirement under both codes. */
export function MeasuredElements({ groups, labels }: { groups: ElementGroup[]; labels: Map<string, string> }) {
  return (
    <section aria-labelledby="elements-heading" className="flex flex-col gap-6">
      <h2 id="elements-heading" className="heading-display text-3xl">
        What we measured
      </h2>
      {groups
        .filter((group) => measuredPairs(group).length > 0)
        .map((group) => (
          <ElementSection key={group.subjectId} group={group} label={labels.get(group.subjectId)} />
        ))}
    </section>
  );
}
