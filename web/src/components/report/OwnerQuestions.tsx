import { Question } from "@phosphor-icons/react/dist/ssr";
import { citation } from "@/lib/findings/format";
import type { FindingPair, ownerQuestions } from "@/lib/findings/group";

type Questions = ReturnType<typeof ownerQuestions>;
type Asked = Questions[number]["questions"];

/** The same ask often settles several checks on one element, so each ask is listed once with the checks it covers. */
function byAsk(asked: Asked) {
  const groups = new Map<string, Asked>();
  for (const entry of asked) groups.set(entry.ask, [...(groups.get(entry.ask) ?? []), entry]);
  return [...groups];
}

function citations(pair: FindingPair) {
  return [pair.ada, pair.cbc].flatMap((finding) => (finding ? [citation(finding)] : [])).filter(Boolean).join(" and ");
}

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
        {questions.map(({ group, questions: asked }) => (
          <li key={group.subjectId} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 px-4 py-3">
            <span className="font-semibold tabular-nums text-ink-muted">{labels.get(group.subjectId) ?? ""}</span>
            <div className="flex flex-col gap-2">
              <span className="font-semibold">{group.name}</span>
              <ul className="flex flex-col gap-3">
                {byAsk(asked).map(([ask, checks]) => (
                  <li key={ask}>
                    <span className="block text-pretty">{ask}</span>
                    <ul className="text-sm text-ink-muted">
                      {checks.map(({ pair, question }) => (
                        <li key={pair.key}>
                          {question}, {citations(pair)}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
