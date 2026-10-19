import { boxInside, type Box } from "@/lib/brush/geometry";

/**
 * What the ambient pen must stay away from. Text blocks and controls are found by tag, and anything that
 * paints a surface opts in with `data-ink-avoid`. Reading only these elements' rects, with no computed
 * styles and no text-node walk, keeps a rescan to a handful of layout reads.
 */
export const KEEP_OUT_SELECTOR = [
  "h1", "h2", "h3", "h4", "p", "li", "dt", "dd", "label", "a", "button", "input", "select", "textarea",
  "img", "svg", "canvas:not([data-ink-layer])", "video", "table", "figure", "[data-ink-avoid]",
].join(",");

export interface RectLike {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

export function toKeepOut(rect: RectLike, origin: { left: number; top: number }, clearancePx: number): Box {
  return [rect.left - origin.left - clearancePx, rect.top - origin.top - clearancePx, rect.right - origin.left + clearancePx, rect.bottom - origin.top + clearancePx];
}

/** Drops boxes that sit wholly inside another, so the pen checks each surface once instead of every line in it. */
export function withoutContained(boxes: readonly Box[]): Box[] {
  const bySize = [...boxes].sort((a, b) => (b[2] - b[0]) * (b[3] - b[1]) - (a[2] - a[0]) * (a[3] - a[1]));
  const kept: Box[] = [];
  for (const box of bySize) {
    if (!kept.some((outer) => boxInside(box, outer))) kept.push(box);
  }
  return kept;
}

export function keepOutBoxes(rects: readonly RectLike[], origin: { left: number; top: number }, clearancePx: number): Box[] {
  const visible = rects.filter((rect) => rect.width > 0 && rect.height > 0);
  return withoutContained(visible.map((rect) => toKeepOut(rect, origin, clearancePx)));
}

export function collectKeepOuts(content: HTMLElement, page: HTMLElement, clearancePx: number): Box[] {
  const rects = Array.from(content.querySelectorAll(KEEP_OUT_SELECTOR), (element) => element.getBoundingClientRect());
  return keepOutBoxes(rects, page.getBoundingClientRect(), clearancePx);
}

/** Runs `task` once after calls stop arriving for `delayMs`. */
export class Debounced {
  private handle: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly task: () => void,
    private readonly delayMs: number,
  ) {}

  schedule() {
    clearTimeout(this.handle);
    this.handle = setTimeout(() => {
      this.handle = undefined;
      this.task();
    }, this.delayMs);
  }

  cancel() {
    clearTimeout(this.handle);
    this.handle = undefined;
  }
}
