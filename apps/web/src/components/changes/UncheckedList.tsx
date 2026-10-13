import { Question } from "@phosphor-icons/react";
import type { RefObject } from "react";
import { type UncheckedThing, sentenceCase } from "@/lib/room-changes";
import { BoxPicture } from "./BoxPicture";

type CardProps = {
  base: string;
  thing: UncheckedThing;
  selected: boolean;
  onSelect: (id: string) => void;
  register: (node: HTMLButtonElement | null) => void;
};

function UncheckedCard({ base, thing, selected, onSelect, register }: CardProps) {
  const other = thing.video === "before" ? "after" : "before";
  const alt = thing.reason === "unsupported"
    ? `The ${thing.video} video's view of the ${thing.name}, whose box hangs with nothing under most of it`
    : `The ${thing.video} video's view of the ${thing.name}, which the ${other} video never looked at`;
  return (
    <li data-selected={selected}
      className="change-tone-unchecked relative grid grid-cols-[7rem_1fr] gap-3 rounded-xl bg-ink/[0.03] p-3 data-[selected=true]:bg-sheet data-[selected=true]:shadow-float data-[selected=true]:ring-2 data-[selected=true]:ring-[var(--change)]">
      <button ref={register} type="button" aria-pressed={selected} aria-label={`Show the ${thing.name} in the room`}
        onClick={() => onSelect(thing.id)}
        className="absolute inset-0 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent" />
      <BoxPicture picture={thing.picture ?? undefined} base={base} tone="unchecked" emptySpot={false}
        alt={alt} />
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

type ListProps = {
  base: string;
  things: UncheckedThing[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  cardRefs: RefObject<Map<string, HTMLButtonElement>>;
};

/** Things kept apart from the changes: seen by one video only, or hanging in the air. Each sentence says which. */
export function UncheckedList({ base, things, selectedId, onSelect, cardRefs }: ListProps) {
  if (things.length === 0) return null;
  return (
    <section aria-labelledby="unchecked" className="space-y-3 px-1">
      <h2 id="unchecked" className="font-display text-base font-semibold text-ink">Not counted as changes</h2>
      <ul className="space-y-2">
        {things.map((thing) => (
          <UncheckedCard key={thing.id} base={base} thing={thing} selected={thing.id === selectedId} onSelect={onSelect}
            register={(node) => {
              if (node) cardRefs.current.set(thing.id, node);
              else cardRefs.current.delete(thing.id);
            }} />
        ))}
      </ul>
    </section>
  );
}
