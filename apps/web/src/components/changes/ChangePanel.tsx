import { type RefObject } from "react";
import { Button } from "@/components/ui/Button";
import { type ChangeScene, formatLength, percent, phoneHeight } from "@/lib/room-changes";
import { ChangeCard } from "./ChangeCard";
import { EvidenceDiagram } from "./EvidenceDiagram";
import { Figure } from "./Figure";
import { RoomSwitcher } from "./RoomSwitcher";
import { UncheckedList } from "./UncheckedList";

function InputVideos({ base, scene }: { base: string; scene: ChangeScene }) {
  const { before, after } = scene.videos ?? { before: null, after: null };
  if (!before || !after) return null;
  return (
    <details className="group rounded-xl bg-ink/[0.04] px-4 py-3">
      <summary className="cursor-pointer text-sm font-medium text-ink">Watch the two input videos</summary>
      <div className="mt-3 grid grid-cols-2 gap-3">
        {([["Before", before], ["After", after]] as const).map(([label, file]) => (
          <figure key={label}>
            <video src={`${base}/${file}`} controls muted playsInline preload="metadata"
              className="aspect-[4/3] w-full rounded-md bg-ink/10 object-cover" />
            <figcaption className="mt-1 text-sm text-ink-muted">{label}</figcaption>
          </figure>
        ))}
      </div>
    </details>
  );
}

/** What the distances rest on: the phone height the room was scaled to, and how many frames were compared. */
function MeasuredWith({ scene }: { scene: ChangeScene }) {
  const frames = (video: "before" | "after") => scene.cameras.filter((camera) => camera.video === video).length;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-ink-muted">Phone height</dt>
      <dd className="text-ink"><Figure>{formatLength(phoneHeight(scene.cameras))}</Figure> above the floor</dd>
      <dt className="text-ink-muted">Frames compared</dt>
      <dd className="text-ink"><Figure>{String(frames("before"))}</Figure> before and <Figure>{String(frames("after"))}</Figure> after</dd>
    </dl>
  );
}

function CoverageBar({ label, share }: { label: string; share: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink-muted">{label}</span>
        <Figure>{percent(share)}</Figure>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[repeating-linear-gradient(135deg,var(--color-unseen)_0_2px,transparent_2px_6px)]"
        role="presentation">
        <div className="h-full rounded-full bg-ink" style={{ width: percent(share) }} />
      </div>
    </div>
  );
}

function BlindSpots({ scene, shown, onToggle }: { scene: ChangeScene; shown: boolean; onToggle: () => void }) {
  const { before_checked_by_other: before, after_checked_by_other: after } = scene.coverage;
  return (
    <section aria-labelledby="blind-spots" className="space-y-4 px-1">
      <div className="flex items-center justify-between gap-3">
        <h2 id="blind-spots" className="font-display text-base font-semibold text-ink">Blind spots</h2>
        <Button variant="toggle" aria-pressed={shown} onClick={onToggle}>
          {shown ? "Hide them in the room" : "Show them in the room"}
        </Button>
      </div>
      <div className="space-y-3">
        <CoverageBar label="Before video's surfaces the after video saw again" share={before} />
        <CoverageBar label="After video's surfaces the before video had seen" share={after} />
      </div>
      <p className="text-sm text-ink-muted text-pretty">
        The hatched part of each bar was only filmed once, so it can&apos;t be checked and is never reported as a change.
      </p>
      <details className="rounded-xl bg-ink/[0.04] px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium text-ink">How a change is told apart from a blind spot</summary>
        <div className="mt-3 space-y-3">
          <EvidenceDiagram />
          <p className="text-sm text-ink-muted text-pretty">
            Every surface from one video is checked against each frame of the other. A frame that sees past the spot
            where a surface was counts as evidence that it is gone. A frame that is blocked, or never pointed there,
            counts for nothing, so moving the camera or hiding a corner behind the sofa never reads as a change.
          </p>
        </div>
      </details>
    </section>
  );
}

type PanelProps = {
  room: string;
  base: string;
  scene: ChangeScene;
  selectedId: string | null;
  onSelect: (id: string) => void;
  cardRefs: RefObject<Map<string, HTMLButtonElement>>;
  blindSpots: boolean;
  onBlindSpots: () => void;
};

export function ChangePanel({ room, base, scene, selectedId, onSelect, cardRefs, blindSpots, onBlindSpots }: PanelProps) {
  return (
    <div className="space-y-6 px-4 pb-10 pt-6 sm:px-6">
      <RoomSwitcher current={room} />
      <header className="space-y-3 px-1">
        <h1 className="font-display text-2xl font-semibold text-ink text-balance">What changed in the room</h1>
        <p className="text-lg text-ink text-pretty">{scene.summary}</p>
        <MeasuredWith scene={scene} />
      </header>
      <InputVideos base={base} scene={scene} />
      <h2 id="changes-list" className="sr-only">Changes</h2>
      <ol className="space-y-2" aria-labelledby="changes-list">
        {scene.changes.map((change) => (
          <li key={change.id}>
            <ChangeCard
              ref={(node) => {
                if (node) cardRefs.current.set(change.id, node);
                else cardRefs.current.delete(change.id);
              }}
              change={change} base={base} selected={change.id === selectedId} onSelect={onSelect} />
          </li>
        ))}
      </ol>
      <UncheckedList base={base} things={scene.unchecked ?? []} selectedId={selectedId} onSelect={onSelect}
        cardRefs={cardRefs} />
      <BlindSpots scene={scene} shown={blindSpots} onToggle={onBlindSpots} />
    </div>
  );
}
