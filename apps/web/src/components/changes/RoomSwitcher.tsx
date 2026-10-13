import Link from "next/link";
import { buttonClassName } from "@/components/ui/Button";
import { EXAMPLE_ROOMS } from "@/lib/room-changes";

/** The checked-in example rooms; a room of your own opens with ?room= in the address. */
export function RoomSwitcher({ current }: { current: string }) {
  return (
    <nav aria-label="Example rooms" className="grid grid-cols-3 gap-1 rounded-xl bg-ink/[0.04] p-1">
      {EXAMPLE_ROOMS.map(({ room, label }) => (
        <Link key={room} href={`/changes?room=${room}`} aria-current={room === current ? "page" : undefined}
          className={`${buttonClassName("toggle")} justify-center aria-[current=page]:bg-ink aria-[current=page]:text-paper`}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
