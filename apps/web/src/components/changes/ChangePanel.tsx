import { type RefObject } from "react";
import { type ChangeScene, percent } from "@/lib/room-changes";
import { ChangeCard } from "./ChangeCard";
import { EvidenceDiagram } from "./EvidenceDiagram";

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

function CoverageBar({ label, share }: { label: string; share: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink-muted">{label}</span>
        <span className="measurement text-ink">{percent(share)}</span>
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
        <button type="button" aria-pressed={shown} onClick={onToggle}
          className="pressable rounded-lg px-3 py-2 text-sm font-medium text-ink-muted hover:bg-ink/5 hover:text-ink aria-pressed:bg-ink aria-pressed:text-paper">
          {shown ? "Hide them in the room" : "Show them in the room"}
        </button>
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
  base: string;
  scene: ChangeScene;
  selectedId: string | null;
  onSelect: (id: string) => void;
  cardRefs: RefObject<Map<string, HTMLButtonElement>>;
  blindSpots: boolean;
  onBlindSpots: () => void;
};

export function ChangePanel({ base, scene, selectedId, onSelect, cardRefs, blindSpots, onBlindSpots }: PanelProps) {
  return (
    <div className="space-y-6 px-4 pb-10 pt-6 sm:px-6">
      <header className="space-y-3 px-1">
        <h1 className="font-display text-2xl font-semibold text-ink text-balance">What changed in the room</h1>
        <p className="text-lg text-ink text-pretty">{scene.summary}</p>
      </header>
      <InputVideos base={base} scene={scene} />
      <ol className="space-y-2" aria-label="Changes">
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
      <BlindSpots scene={scene} shown={blindSpots} onToggle={onBlindSpots} />
    </div>
  );
}
