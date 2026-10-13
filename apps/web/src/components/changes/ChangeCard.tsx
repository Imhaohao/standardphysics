import { forwardRef } from "react";
import { CHANGE_LABEL, type RoomChange, type SpotEvidence, formatLength, sentenceCase } from "@/lib/room-changes";
import { BoxPicture } from "./BoxPicture";
import { ChangeTypeIcon } from "./ChangeTypeIcon";
import { Figure } from "./Figure";


/** Footprint and height as two plain numbers; the sentence already carries distance and turn. */
function SizeFacts({ size }: { size: RoomChange["size"] }) {
  const [a, b, height] = size;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-ink-muted">Footprint</dt>
      <dd><Figure>{formatLength(Math.max(a, b))}</Figure> by <Figure>{formatLength(Math.min(a, b))}</Figure></dd>
      <dt className="text-ink-muted">Height</dt>
      <dd><Figure>{formatLength(height)}</Figure></dd>
    </dl>
  );
}

const SPOT_WORDS = { old: "where it was", new: "where it is now" } as const;

/** One tick per frame of the other video; a filled tick saw mostly empty space at the spot. */
function EvidenceMeter({ spot, which }: { spot: SpotEvidence; which: keyof typeof SPOT_WORDS }) {
  return (
    <div>
      <div className="flex gap-px" aria-hidden>
        {Array.from({ length: spot.of }, (_, index) => (
          <span key={index} className={`h-2 flex-1 rounded-[1px] ${index < spot.empty_in ? "bg-[var(--change)]" : "bg-ink/10"}`} />
        ))}
      </div>
      <p className="mt-1.5 text-sm text-ink-muted tabular-nums">
        <span className="font-medium text-ink">{spot.empty_in} of {spot.of}</span> {spot.video} frames saw empty space {SPOT_WORDS[which]}
      </p>
    </div>
  );
}

function Evidence({ change }: { change: RoomChange }) {
  const { old_spot: oldSpot, new_spot: newSpot } = change.evidence;
  return (
    <div className="space-y-3">
      {oldSpot && <EvidenceMeter spot={oldSpot} which="old" />}
      {newSpot && <EvidenceMeter spot={newSpot} which="new" />}
    </div>
  );
}

type ChangeCardProps = { change: RoomChange; base: string; selected: boolean; onSelect: (id: string) => void };

export const ChangeCard = forwardRef<HTMLButtonElement, ChangeCardProps>(function ChangeCard(
  { change, base, selected, onSelect },
  ref,
) {
  return (
    <article
      data-selected={selected}
      className={`change-tone-${change.type} relative rounded-xl p-4 transition-[background-color,box-shadow] duration-150 hover:bg-ink/[0.03] data-[selected=true]:bg-sheet data-[selected=true]:shadow-float data-[selected=true]:ring-2 data-[selected=true]:ring-[var(--change)]`}
    >
      <button
        ref={ref}
        type="button"
        aria-pressed={selected}
        aria-label={`Show the ${change.name} in the room`}
        onClick={() => onSelect(change.id)}
        className="absolute inset-0 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      />
      <h3 className="flex items-center gap-2">
        <span className="change-tone flex items-center gap-1 text-sm font-semibold">
          <ChangeTypeIcon type={change.type} size={16} />
          {CHANGE_LABEL[change.type]}
        </span>
        <span className="font-display text-lg font-semibold text-ink">{sentenceCase(change.name)}</span>
      </h3>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <BoxPicture picture={change.pictures.before} base={base} tone={change.type} emptySpot={change.type === "added"}
          alt={`The before video at the spot where the ${change.name} ${change.type === "added" ? "later appeared" : "stood"}`} />
        <BoxPicture picture={change.pictures.after} base={base} tone={change.type} emptySpot={change.type === "removed"}
          alt={`The after video at the spot where the ${change.name} ${change.type === "removed" ? "used to be" : "is now"}`} />
      </div>
      <p className="mt-3 text-base text-ink text-pretty">{change.sentence}</p>
      <div className="mt-3 space-y-3">
        <SizeFacts size={change.size} />
        <Evidence change={change} />
      </div>
    </article>
  );
});
