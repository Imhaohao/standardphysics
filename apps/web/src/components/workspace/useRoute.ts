"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { confirmRoute } from "@/lib/layout-client";
import { moveMarker, type StopMarker, stopMarkers } from "@/lib/route";
import type { Scenario } from "@/types/contracts";

export type RouteState = ReturnType<typeof useRoute>;

export function useRoute(scanId: string, saved: Scenario | null, suggested: Scenario | null) {
  const router = useRouter();
  const starting = saved ?? suggested;
  const [scenario, setScenario] = useState<Scenario | null>(starting);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const markers = useMemo(() => (scenario ? stopMarkers(scenario) : []), [scenario]);

  const drag = useCallback((marker: StopMarker, dx: number, dy: number) => {
    setScenario((current) => (current ? moveMarker(current, marker, dx, dy) : current));
  }, []);

  const confirm = useCallback(async () => {
    if (!scenario) return;
    setSaving(true);
    setProblem(null);
    try {
      await confirmRoute(scanId, scenario);
      router.refresh();
    } catch {
      setProblem("We couldn't save the route. Try again.");
    } finally {
      setSaving(false);
    }
  }, [scanId, scenario, router]);

  return {
    scenario, markers, saving, problem, confirmed: saved !== null, changed: scenario !== starting,
    drag, confirm, reset: () => setScenario(starting),
  };
}
