"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Vector3 } from "three";
import type { ChangeScene } from "@/lib/room-changes";
import { ChangePanel } from "./ChangePanel";
import { ChangeStage, type Shot, changeShot, overviewShot } from "./ChangeStage";
import { type Showing, StageToolbar } from "./StageToolbar";
import { useChangeScene } from "./useChangeScene";

type CameraReader = () => [Vector3, Vector3];

function useSelection(scene: ChangeScene) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [shot, setShot] = useState<Shot>(() => overviewShot(scene));
  const readCamera = useRef<CameraReader | null>(null);
  const cardRefs = useRef(new Map<string, HTMLButtonElement>());

  const select = useCallback((id: string) => {
    const change = scene.changes.find((item) => item.id === id);
    const read = readCamera.current;
    if (!change || !read) return;
    const [position, target] = read();
    setSelectedId(id);
    setShot(changeShot(change, position, target));
    cardRefs.current.get(id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [scene]);

  const reset = useCallback(() => {
    setSelectedId(null);
    setShot({ ...overviewShot(scene), key: `overview-${Date.now()}` });
  }, [scene]);

  const onCamera = useCallback((read: CameraReader) => {
    readCamera.current = read;
  }, []);

  return { selectedId, setSelectedId, shot, select, reset, onCamera, cardRefs };
}

function useEscapeToClear(clear: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") clear();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clear]);
}

function ReadyViewer({ base, scene, cloud }: { base: string; scene: ChangeScene; cloud: Parameters<typeof ChangeStage>[0]["cloud"] }) {
  const { selectedId, setSelectedId, shot, select, reset, onCamera, cardRefs } = useSelection(scene);
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
      <section aria-label="Room in 3D" className="relative h-[62dvh] shrink-0 lg:h-auto lg:flex-1">
        <ChangeStage scene={scene} cloud={cloud} view={view} selectedId={selectedId} shot={shot}
          onSelect={select} onClear={clear} onCamera={onCamera} />
        <div className="pointer-events-none absolute inset-x-0 top-0 p-3 sm:p-4">
          <div className="pointer-events-auto w-fit">
            <StageToolbar showing={showing} onShowing={setShowing} paths={paths} onPaths={() => setPaths((on) => !on)}
              blindSpots={blindSpots} onBlindSpots={toggleBlindSpots} onReset={reset} />
          </div>
        </div>
      </section>
      <aside className="bg-paper lg:w-[440px] lg:shrink-0 lg:overflow-y-auto lg:shadow-[-1px_0_0_var(--color-rule)]">
        <ChangePanel base={base} scene={scene} selectedId={selectedId} onSelect={select} cardRefs={cardRefs}
          blindSpots={blindSpots} onBlindSpots={toggleBlindSpots} />
      </aside>
    </main>
  );
}

/** The /changes page: the shared 3D room on one side, what changed and how we know on the other. */
export function ChangeViewer({ base }: { base: string }) {
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
  return <ReadyViewer base={base} scene={loaded.scene} cloud={loaded.cloud} />;
}
