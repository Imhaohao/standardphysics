"use client";

import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeScene, Cloud } from "@/lib/room-changes";
import { ChangePanel } from "./ChangePanel";
import { ChangeStage, type Focus, type Orbit } from "./ChangeStage";
import { type Showing, StageToolbar } from "./StageToolbar";
import { useChangeScene } from "./useChangeScene";

const STEP = Math.PI / 12;
const KEY_ORBITS: Record<string, [number, number, number]> = {
  ArrowLeft: [-STEP, 0, 1], ArrowRight: [STEP, 0, 1], ArrowUp: [0, STEP / 2, 1], ArrowDown: [0, -STEP / 2, 1],
  "+": [0, 0, 0.85], "=": [0, 0, 0.85], "-": [0, 0, 1.18],
};

function useSelection(scene: ChangeScene) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus>({ kind: "overview", nonce: 0 });
  const cardRefs = useRef(new Map<string, HTMLButtonElement>());

  const select = useCallback((id: string) => {
    const known = [...scene.changes, ...(scene.unchecked ?? [])].some((item) => item.id === id);
    if (!known) return;
    setSelectedId(id);
    setFocus((current) => ({ kind: "item", id, nonce: current.nonce + 1 }));
    cardRefs.current.get(id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [scene]);

  const reset = useCallback(() => {
    setSelectedId(null);
    setFocus((current) => ({ kind: "overview", nonce: current.nonce + 1 }));
  }, []);

  return { selectedId, setSelectedId, focus, select, reset, cardRefs };
}

function useEscapeToClear(clear: () => void) {
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") clear();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clear]);
}

/** On a phone the 3D view stays pinned over the top 52% of the screen, so cards under it are not being read. */
const STAGE_COVERS = "-52% 0px 0px 0px";

/** The change whose card is most in view, so a phone's 3D view can name the one being read. */
function useReading(cardRefs: { current: Map<string, HTMLButtonElement> }, scene: ChangeScene) {
  const [readingId, setReadingId] = useState<string | null>(null);
  useEffect(() => {
    const shares = new Map<string, number>();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => shares.set((entry.target as HTMLElement).dataset.changeId ?? "", entry.intersectionRatio));
      const [best] = [...shares.entries()].filter(([, share]) => share > 0.4).sort((a, b) => b[1] - a[1]);
      setReadingId(best ? best[0] : null);
    }, { threshold: [0, 0.25, 0.5, 0.75, 1], rootMargin: STAGE_COVERS });
    cardRefs.current.forEach((card, id) => {
      card.dataset.changeId = id;
      observer.observe(card);
    });
    return () => observer.disconnect();
  }, [cardRefs, scene]);
  return readingId;
}

function useKeyboardOrbit() {
  const orbit = useRef<Orbit | null>(null);
  const onOrbit = useCallback((next: Orbit) => {
    orbit.current = next;
  }, []);
  const onKeyDown = useCallback((event: KeyboardEvent<HTMLElement>) => {
    const step = KEY_ORBITS[event.key];
    if (!step || event.target !== event.currentTarget || !orbit.current) return;
    event.preventDefault();
    orbit.current(...step);
  }, []);
  return { onOrbit, onKeyDown };
}

function ReadyViewer({ room, base, scene, cloud }: { room: string; base: string; scene: ChangeScene; cloud: Cloud }) {
  const { selectedId, setSelectedId, focus, select, reset, cardRefs } = useSelection(scene);
  const { onOrbit, onKeyDown } = useKeyboardOrbit();
  const readingId = useReading(cardRefs, scene);
  const [showing, setShowing] = useState<Showing>("both");
  const [paths, setPaths] = useState(false);
  const [blindSpots, setBlindSpots] = useState(false);
  const toggleBlindSpots = useCallback(() => setBlindSpots((on) => !on), []);
  const clear = useCallback(() => setSelectedId(null), [setSelectedId]);
  useEscapeToClear(clear);
  const view = useMemo(() => ({
    before: showing !== "after", after: showing !== "before", blindSpots, paths,
  }), [showing, blindSpots, paths]);

  return (
    <main className="flex min-h-dvh flex-col lg:h-dvh lg:flex-row">
      <section aria-labelledby="stage-help" tabIndex={0} onKeyDown={onKeyDown}
        className="sticky top-0 z-10 h-[52dvh] shrink-0 bg-paper outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent lg:relative lg:h-auto lg:flex-1">
        <p id="stage-help" className="sr-only">
          The room in 3D, built from both videos. Drag or use the arrow keys to turn it, scroll or press plus and minus to zoom.
        </p>
        <div className="pointer-events-none absolute inset-x-0 top-0 z-20 p-3 sm:p-4">
          <div className="pointer-events-auto w-fit">
            <StageToolbar showing={showing} onShowing={setShowing} paths={paths} onPaths={() => setPaths((on) => !on)}
              blindSpots={blindSpots} onBlindSpots={toggleBlindSpots} onReset={reset} />
          </div>
        </div>
        <ChangeStage scene={scene} cloud={cloud} view={view} selectedId={selectedId} readingId={readingId} focus={focus}
          onSelect={select} onClear={clear} onOrbit={onOrbit} />
      </section>
      <aside className="bg-paper lg:w-[440px] lg:shrink-0 lg:overflow-y-auto lg:shadow-[-1px_0_0_var(--color-rule)]">
        <ChangePanel room={room} base={base} scene={scene} selectedId={selectedId} onSelect={select} cardRefs={cardRefs}
          blindSpots={blindSpots} onBlindSpots={toggleBlindSpots} />
      </aside>
    </main>
  );
}

/** The /changes page: the shared 3D room on one side, what changed and how we know on the other. */
export function ChangeViewer({ room, base }: { room: string; base: string }) {
  const loaded = useChangeScene(base);
  if (loaded.state === "loading") {
    return <p className="grid min-h-dvh place-items-center text-base text-ink-muted">Loading the room…</p>;
  }
  if (loaded.state === "failed") {
    return (
      <div className="mx-auto grid min-h-dvh max-w-prose content-center gap-2 px-6">
        <h1 className="font-display text-xl font-semibold text-ink">This room didn&apos;t load</h1>
        <p className="text-base text-ink-muted">
          {loaded.reason}. Run the detector with its output folder under apps/web/public/changes, then open
          this page with that folder&apos;s name in the address, like /changes?room=my-room.
        </p>
      </div>
    );
  }
  return <ReadyViewer room={room} base={base} scene={loaded.scene} cloud={loaded.cloud} />;
}
