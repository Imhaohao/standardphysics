import { forwardRef } from "react";
import { CHANGE_LABEL, type RoomChange, formatLength, formatTurn, sentenceCase } from "@/lib/room-changes";
import { BoxPicture } from "./BoxPicture";
import { ChangeTypeIcon } from "./ChangeTypeIcon";

function facts(change: RoomChange): [string, string][] {
  const rows: [string, string][] = [];
  if (change.type === "moved" && change.distance_m !== undefined) rows.push(["Moved", formatLength(change.distance_m)]);
  const turn = formatTurn(change.turn_deg);
  if (turn) rows.push(["Turned", turn]);
  rows.push(["Size", change.size_text.replace(/^about /, "")]);
  return rows;
}

/** One tick per frame of the other video; filled ticks saw empty space where the object is or was. */
function EvidenceMeter({ seen, of }: { seen: number; of: number }) {
  return (
    <div>
      <div className="flex gap-px" aria-hidden>
        {Array.from({ length: of }, (_, index) => (
          <span key={index} className={`h-2 flex-1 rounded-[1px] ${index < seen ? "bg-[var(--change)]" : "bg-ink/10"}`} />
        ))}
      </div>
      <p className="mt-1.5 text-sm text-ink-muted">
        <span className="measurement text-ink">{seen} of {of}</span> frames from the other video saw empty space here
      </p>
    </div>
  );
}

type ChangeCardProps = { change: RoomChange; base: string; selected: boolean; onSelect: (id: string) => void };

export const ChangeCard = forwardRef<HTMLButtonElement, ChangeCardProps>(function ChangeCard(
  { change, base, selected, onSelect },
  ref,
) {
  const { evidence } = change;
  return (
    <article
      data-selected={selected}
      className={`change-tone-${change.type} relative rounded-xl p-4 transition-[background-color,box-shadow] duration-150 hover:bg-ink/[0.03] data-[selected=true]:bg-sheet data-[selected=true]:shadow-float data-[selected=true]:ring-2 data-[selected=true]:ring-[var(--change)]`}
    >
      <h3 className="flex items-center gap-2">
        <span className="change-tone flex items-center gap-1 text-sm font-semibold">
          <ChangeTypeIcon type={change.type} size={16} />
          {CHANGE_LABEL[change.type]}
        </span>
        <button
          ref={ref}
          type="button"
          aria-pressed={selected}
          onClick={() => onSelect(change.id)}
          className="font-display text-lg font-semibold text-ink after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-accent"
        >
          {sentenceCase(change.name)}
          <span className="sr-only">, show it in the room</span>
        </button>
      </h3>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <BoxPicture picture={change.pictures.before} base={base} type={change.type} emptySpot={change.type === "added"}
          alt={`The before video at the spot where the ${change.name} ${change.type === "added" ? "later appeared" : "stood"}`} />
        <BoxPicture picture={change.pictures.after} base={base} type={change.type} emptySpot={change.type === "removed"}
          alt={`The after video at the spot where the ${change.name} ${change.type === "removed" ? "used to be" : "is now"}`} />
      </div>
      <p className="mt-3 text-base text-ink text-pretty">{change.sentence}</p>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {facts(change).map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="text-ink-muted">{key}</dt>
            <dd className="measurement text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3">
        <EvidenceMeter seen={evidence.seen_through_by} of={evidence.frames_in_other_video} />
      </div>
    </article>
  );
});
