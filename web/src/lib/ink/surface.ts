import { SchematicBrush } from "@/lib/brush/brush";
import type { Stamp } from "@/lib/brush/marks";
import { Random } from "@/lib/brush/random";
import { renderStamp, type InkPalette } from "@/lib/brush/render";
import { DRAFTING_UNIT_PX } from "@/lib/brush/sheet";
import { clearCanvas, context2d, createTextMeasurer, fitCanvases, readPalette } from "./canvas";
import { browserLoopHost, InkLoop, type InkTarget } from "./loop";

export interface InkSurfaceElements {
  /** The element the canvases cover; drawing coordinates are relative to its top-left corner. */
  surface: HTMLElement;
  paint: HTMLCanvasElement;
  live: HTMLCanvasElement;
}

export interface InkSurfaceOptions {
  speed?: number;
  paperToken?: string;
  specks?: boolean;
  random?: Random;
}

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

class CanvasTarget implements InkTarget {
  constructor(
    private readonly paint: HTMLCanvasElement,
    private readonly live: HTMLCanvasElement,
    private readonly palette: InkPalette,
  ) {}

  bake(stamps: readonly Stamp[]) {
    const context = context2d(this.paint);
    for (const stamp of stamps) renderStamp(context, stamp, Infinity, this.palette);
  }

  drawLive(stamps: readonly Stamp[], now: number) {
    const context = context2d(this.live);
    for (const stamp of stamps) renderStamp(context, stamp, now, this.palette);
  }

  clearLive() {
    clearCanvas(this.live);
  }
}

/**
 * A pair of canvases the brush draws on: `live` holds strokes still being drawn and is redrawn each frame,
 * `paint` holds finished ink and is only ever added to. The frame loop sleeps whenever the pen is idle or
 * the tab is hidden, and draws everything at once for people who prefer reduced motion.
 */
export class InkSurface {
  readonly brush: SchematicBrush;
  readonly palette: InkPalette;
  private readonly loop: InkLoop;
  private readonly motionQuery: MediaQueryList;
  private holdInstant = false;

  constructor(
    private readonly elements: InkSurfaceElements,
    options: InkSurfaceOptions = {},
  ) {
    this.palette = readPalette(elements.surface, options.paperToken);
    this.brush = new SchematicBrush({
      unit: DRAFTING_UNIT_PX,
      measureText: createTextMeasurer(this.palette.fontFamily),
      now: () => performance.now(),
      speed: options.speed,
      specks: options.specks,
      random: options.random,
    });
    this.loop = new InkLoop(this.brush, new CanvasTarget(elements.paint, elements.live, this.palette), browserLoopHost());
    this.motionQuery = window.matchMedia(REDUCED_MOTION);
    this.motionQuery.addEventListener("change", this.syncInstant);
    document.addEventListener("visibilitychange", this.onVisibilityChange);
    this.syncInstant();
  }

  get width() {
    return this.elements.surface.clientWidth;
  }

  get height() {
    return this.elements.surface.clientHeight;
  }

  /** Draw finished ink without animation, for example when replaying a drawing the visitor has already watched. */
  set instant(value: boolean) {
    this.holdInstant = value;
    this.syncInstant();
  }

  fit() {
    return fitCanvases(this.elements.surface, this.elements.paint, this.elements.live);
  }

  /** Call after giving the brush new work. */
  wake() {
    this.loop.wake();
  }

  /** Draws everything the brush has been given, finished and without animation. */
  flush() {
    this.loop.flush();
  }

  clear() {
    this.brush.clear();
    clearCanvas(this.elements.paint);
    clearCanvas(this.elements.live);
  }

  dispose() {
    this.loop.dispose();
    this.motionQuery.removeEventListener("change", this.syncInstant);
    document.removeEventListener("visibilitychange", this.onVisibilityChange);
    this.brush.clear();
  }

  private readonly syncInstant = () => {
    this.loop.instant = this.holdInstant || this.motionQuery.matches;
    this.wake();
  };

  private readonly onVisibilityChange = () => {
    if (document.visibilityState === "hidden") this.loop.pause();
    else this.loop.wake();
  };
}
