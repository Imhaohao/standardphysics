import type { Scenario } from "@/types/contracts";

export type StopMarker = { key: string; label: string; stopIndexes: number[]; x: number; y: number };

const SAME_SPOT_METERS = 0.05;

/** One marker per spot, so an entrance that is also the exit is dragged as one. */
export function stopMarkers(scenario: Scenario): StopMarker[] {
  const markers: StopMarker[] = [];
  scenario.stops.forEach((stop, index) => {
    const { x, y } = stop.position;
    const shared = markers.find((marker) => Math.hypot(marker.x - x, marker.y - y) < SAME_SPOT_METERS);
    if (shared) {
      shared.stopIndexes.push(index);
      shared.label = `${shared.label} and ${stop.name.toLowerCase()}`;
      return;
    }
    markers.push({ key: `${index}`, label: stop.name, stopIndexes: [index], x, y });
  });
  return markers;
}

export function moveMarker(scenario: Scenario, marker: StopMarker, dx: number, dy: number): Scenario {
  const moving = new Set(marker.stopIndexes);
  return {
    ...scenario,
    stops: scenario.stops.map((stop, index) =>
      moving.has(index)
        ? { ...stop, position: { ...stop.position, x: stop.position.x + dx, y: stop.position.y + dy } }
        : stop,
    ) as Scenario["stops"],
  };
}
