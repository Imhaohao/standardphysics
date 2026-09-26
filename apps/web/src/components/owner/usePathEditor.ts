"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useRef, useState } from "react";
import { confirmRoute } from "@/lib/layout-client";
import { suggestPath } from "@/lib/owner-client";
import { moveMarker, type StopMarker, stopMarkers } from "@/lib/route";
import type { Destination } from "@/lib/owner-journey";
import type { Scenario } from "@/types/contracts";


/** The customer path while the owner shapes it: the places they picked, and stops they dragged. */
export function usePathEditor(scanId: string, starting: Scenario | null, picked: Destination[]) {
  const router = useRouter();
  const [scenario, setScenario] = useState<Scenario | null>(starting);
  const [destinations, setDestinations] = useState<Destination[]>(picked);
  const [touched, setTouched] = useState(false);
  const [pickedBefore, setPickedBefore] = useState(picked.join(","));
  // The page loads before the owner reaches this step, and the path and the
  // places it starts from arrive with a later refresh. Take them then, unless
  // the owner has already started shaping the path.
  if (!touched && picked.join(",") !== pickedBefore) {
    setPickedBefore(picked.join(","));
    setDestinations(picked);
  }
  if (scenario === null && starting !== null) setScenario(starting);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const latest = useRef(0);
  const markers = useMemo(() => (scenario ? stopMarkers(scenario) : []), [scenario]);

  const toggle = useCallback((place: Destination) => {
    const next = destinations.includes(place) ? destinations.filter((each) => each !== place) : [...destinations, place];
    setDestinations(next);
    setTouched(true);
    const asked = ++latest.current;
    suggestPath(scanId, next)
      .then((suggested) => { if (asked === latest.current) setScenario(suggested); })
      .catch(() => { if (asked === latest.current) setProblem("We couldn't draw that path. Try again."); });
  }, [destinations, scanId]);

  const drag = useCallback((marker: StopMarker, dx: number, dy: number) => {
    setTouched(true);
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
      setProblem("We couldn't save the path. Try again.");
      setSaving(false);
    }
  }, [scanId, scenario, router]);

  return { scenario, markers, destinations, saving, problem, toggle, drag, confirm };
}

export type PathEditor = ReturnType<typeof usePathEditor>;
