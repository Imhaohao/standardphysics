"use client";

import { useEffect, useState } from "react";
import { type ChangeScene, type Cloud, parseCloud } from "@/lib/room-changes";

export type Loaded = { state: "loading" } | { state: "failed"; reason: string } | { state: "ready"; scene: ChangeScene; cloud: Cloud };

async function fetchScene(base: string, signal: AbortSignal): Promise<{ scene: ChangeScene; cloud: Cloud }> {
  const response = await fetch(`${base}/scene.json`, { signal });
  if (!response.ok) throw new Error(`${base}/scene.json answered ${response.status}`);
  const scene = (await response.json()) as ChangeScene;
  const points = await fetch(`${base}/${scene.cloud.file}`, { signal });
  if (!points.ok) throw new Error(`${base}/${scene.cloud.file} answered ${points.status}`);
  return { scene, cloud: parseCloud(await points.arrayBuffer(), scene.cloud.count) };
}

/** The detector's output for one room, read from the folder it was copied into under public/changes. */
export function useChangeScene(base: string): Loaded {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  useEffect(() => {
    const abort = new AbortController();
    fetchScene(base, abort.signal)
      .then(({ scene, cloud }) => setLoaded({ state: "ready", scene, cloud }))
      .catch((error: unknown) => {
        if (!abort.signal.aborted) setLoaded({ state: "failed", reason: String((error as Error).message ?? error) });
      });
    return () => abort.abort();
  }, [base]);
  return loaded;
}
