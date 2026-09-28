import { Hammer } from "@phosphor-icons/react/dist/ssr";
import type { ScheduledMove } from "./redesign";
import { describeMove } from "./redesignCopy";

function Serves({ move }: { move: ScheduledMove }) {
  if (move.serves.length === 0) return <span className="text-ink-muted">Not tied to a failing spot</span>;
  return (
    <span className="flex flex-wrap gap-x-4 gap-y-1.5">
      {move.serves.map((row) => (
        <span key={row.number} className="flex items-center gap-2 text-sm">
          <span className="flex size-6 items-center justify-center rounded-full bg-ink font-semibold text-paper tabular-nums">{row.number}</span>
          <span className="measurement">{(row.before ?? row.after)?.citation.section}</span>
        </span>
      ))}
    </span>
  );
}

/** What the plan moves, how far on the drawing, and which marks each move answers. */
export function MoveSchedule({ schedule, planName }: { schedule: ScheduledMove[]; planName: string }) {
  if (schedule.length === 0) return null;
  return (
    <section className="mt-16 break-inside-avoid" aria-labelledby="move-schedule">
      <h2 id="move-schedule" className="heading-display text-3xl">What {planName} moves</h2>
      <div className="relative mt-6 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left">
          <thead className="text-sm text-ink-muted">
            <tr>
              <th scope="col" className="py-2 pr-4 font-semibold">Piece</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Move on the plan</th>
              <th scope="col" className="py-2 font-semibold">Answers</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((move, index) => (
              <tr key={`${move.node.id}-${index}`} className="break-inside-avoid border-t border-rule align-top">
                <td className="py-3 pr-4">
                  <span className="font-semibold">{move.node.label}</span>
                  {move.builtIn && (
                    <span className="mt-1 flex items-center gap-1 text-sm text-attention">
                      <Hammer size={16} weight="bold" aria-hidden />
                      Built in, so moving it is construction
                    </span>
                  )}
                </td>
                <td className="measurement whitespace-nowrap py-3 pr-4">{describeMove(move)}</td>
                <td className="py-3"><Serves move={move} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
