import { Question } from "@phosphor-icons/react/dist/ssr";
import { citation } from "@/lib/findings/format";
import type { ownerQuestions } from "@/lib/findings/group";

type Questions = ReturnType<typeof ownerQuestions>;

/** What we couldn't measure from the scan, asked plainly so the owner can answer from memory or a quick look. */
export function OwnerQuestions({ questions, labels }: { questions: Questions; labels: Map<string, string> }) {
  if (questions.length === 0) return null;
  return (
    <section aria-labelledby="questions-heading" data-ink-avoid className="border border-ink bg-paper break-inside-avoid">
      <h2 id="questions-heading" className="heading-display flex items-center gap-2 border-b border-ink px-4 py-3 text-2xl">
        <Question size={24} weight="fill" aria-hidden className="text-attention" />
        Questions for you
      </h2>
      <ol className="divide-y divide-ink/20">
        {questions.map(({ group, pair, question }) => (
          <li key={`${group.subjectId}-${pair.key}`} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 px-4 py-3">
            <span className="font-semibold tabular-nums text-ink-muted">{labels.get(group.subjectId) ?? ""}</span>
            <span>
              <span className="block text-lg text-pretty">{question}</span>
              <span className="block text-sm text-ink-muted">
                {group.name}, {[pair.ada, pair.cbc].filter((finding) => finding !== null).map((finding) => citation(finding!)).join(" and ")}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
