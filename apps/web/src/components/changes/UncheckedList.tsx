import { Question } from "@phosphor-icons/react";
import { type UncheckedThing, sentenceCase } from "@/lib/room-changes";
import { BoxPicture } from "./BoxPicture";

function UncheckedCard({ base, thing }: { base: string; thing: UncheckedThing }) {
  const other = thing.video === "before" ? "after" : "before";
  return (
    <li className="change-tone-unchecked grid grid-cols-[7rem_1fr] gap-3 rounded-xl bg-ink/[0.03] p-3">
      <BoxPicture picture={thing.picture ?? undefined} base={base} tone="unchecked" emptySpot={false}
        alt={`The ${thing.video} video's view of the ${thing.name}, which the ${other} video never looked at`} />
      <div className="min-w-0 space-y-1">
        <h3 className="flex items-center gap-1.5 font-display text-base font-semibold text-ink">
          <Question size={16} weight="bold" aria-hidden className="text-[var(--color-unseen)]" />
          {sentenceCase(thing.name)}
        </h3>
        <p className="text-sm text-ink-muted text-pretty">{thing.sentence}</p>
      </div>
    </li>
  );
}

/** Things only one video saw, kept apart from the changes because one look can't say whether they are new. */
export function UncheckedList({ base, things }: { base: string; things: UncheckedThing[] }) {
  if (things.length === 0) return null;
  return (
    <section aria-labelledby="unchecked" className="space-y-3 px-1">
      <h2 id="unchecked" className="font-display text-base font-semibold text-ink">Seen by one video only</h2>
      <ul className="space-y-2">
        {things.map((thing) => <UncheckedCard key={thing.id} base={base} thing={thing} />)}
      </ul>
    </section>
  );
}
