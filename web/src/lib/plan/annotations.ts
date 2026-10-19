import { categoryName } from "@/lib/scene/describe";
import { planBounds, type PlanBounds } from "@/lib/scene/plan";
import type { Scene, Vec2 } from "@/lib/scene/types";
import { formatFeetAndInches } from "@/lib/scene/units";

export interface PlanNote {
  at: Vec2;
  text: string;
}

export interface PlanAnnotations {
  bounds: PlanBounds;
  widthLabel: string;
  depthLabel: string;
  notes: PlanNote[];
}

/** The overall dimensions of the plan and a size note for its largest pieces of furniture. */
export function planAnnotations(scene: Scene, noteCount = 3): PlanAnnotations | null {
  const bounds = planBounds(scene);
  if (!bounds) return null;
  const notes = scene.rooms
    .flatMap((room) => room.objects)
    .sort((a, b) => b.size.x * b.size.z - a.size.x * a.size.z)
    .slice(0, noteCount)
    .map((object) => ({
      at: { x: object.center.x, y: object.center.z },
      text: `${categoryName(object.category)} ${formatFeetAndInches(object.size.x)} × ${formatFeetAndInches(object.size.z)}`,
    }));
  return {
    bounds,
    widthLabel: formatFeetAndInches(bounds.maxX - bounds.minX),
    depthLabel: formatFeetAndInches(bounds.maxY - bounds.minY),
    notes,
  };
}

/** Stacks note shelves top to bottom beside the plan, each as close to its target's height as the one above allows. */
export function shelfRows(targetYs: readonly number[], top: number, bottom: number, spacing: number) {
  const order = targetYs.map((y, index) => ({ y, index })).sort((a, b) => a.y - b.y);
  const rows = new Array<number>(targetYs.length).fill(top);
  let next = top;
  for (const { y, index } of order) {
    rows[index] = Math.min(bottom, Math.max(next, y));
    next = rows[index]! + spacing;
  }
  return rows;
}
