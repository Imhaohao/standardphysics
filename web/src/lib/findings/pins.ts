import type { PlanPin } from "@/lib/plan/inkPlan";
import type { ElementGroup } from "./group";

/** One numbered pin per element that needs fixing or needs an answer, numbered in report order. */
export function findingPins(groups: readonly ElementGroup[]): PlanPin[] {
  return groups
    .filter((group) => group.subject && (group.status === "fail" || group.status === "needs_info"))
    .map((group, index) => ({ id: group.subjectId, label: String(index + 1), at: group.subject!.anchor, status: group.status }));
}

export function pinLabels(pins: readonly PlanPin[]) {
  return new Map(pins.map((pin) => [pin.id, pin.label]));
}
