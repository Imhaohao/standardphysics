import { buildFreeSpace, planAmbientRoutes } from "@/lib/brush/ambient";
import { polylineLength, type Box } from "@/lib/brush/geometry";
import { collectKeepOuts, Debounced } from "./keepOuts";
import { InkSurface } from "./surface";

const PEN_SPEED_MULTIPLIER = 2.2;
const HAND_SPEED_PX_PER_MS = 0.8;
const ROUTE_OVERLAP = 0.6;
const CLEARANCE_PX = 20;
const RESCAN_DELAY_MS = 350;

export interface AmbientInkElements {
  page: HTMLElement;
  content: HTMLElement;
  paint: HTMLCanvasElement;
  live: HTMLCanvasElement;
}

/**
 * The ink that wanders across the empty paper behind every page. It drafts a few routes in the open space
 * below the content once per page, and only redrafts if the content later grows into its ink.
 */
export class AmbientInk {
  private readonly surface: InkSurface;
  private readonly rescan = new Debounced(() => this.rescanNow(), RESCAN_DELAY_MS);
  private readonly resizeObserver: ResizeObserver;
  private readonly mutationObserver: MutationObserver;
  private needsRedraft = true;
  private fontsReady = false;
  private disposed = false;

  constructor(private readonly elements: AmbientInkElements) {
    this.surface = new InkSurface({ surface: elements.page, paint: elements.paint, live: elements.live }, { speed: PEN_SPEED_MULTIPLIER, paperToken: "--color-paper" });
    this.resizeObserver = new ResizeObserver(() => this.rescan.schedule());
    this.resizeObserver.observe(elements.page);
    this.resizeObserver.observe(elements.content);
    this.mutationObserver = new MutationObserver(() => this.rescan.schedule());
    this.mutationObserver.observe(elements.content, { childList: true, subtree: true });
    document.addEventListener("visibilitychange", this.onVisibilityChange);
    void document.fonts.ready.then(() => {
      this.fontsReady = true;
      this.rescan.schedule();
    });
  }

  pageChanged() {
    this.needsRedraft = true;
    this.rescan.schedule();
  }

  dispose() {
    this.disposed = true;
    this.rescan.cancel();
    this.resizeObserver.disconnect();
    this.mutationObserver.disconnect();
    document.removeEventListener("visibilitychange", this.onVisibilityChange);
    this.surface.dispose();
  }

  private readonly onVisibilityChange = () => {
    if (document.visibilityState === "visible") this.rescan.schedule();
  };

  private rescanNow() {
    if (!this.fontsReady || this.disposed || document.visibilityState === "hidden") return;
    const { page, content } = this.elements;
    this.surface.fit();
    const keepOuts = collectKeepOuts(content, page, CLEARANCE_PX);
    const bounds: Box = [0, 0, page.clientWidth, page.clientHeight];
    if (this.needsRedraft || this.surface.brush.inkTouches(keepOuts)) {
      this.redraft(keepOuts, bounds);
      return;
    }
    this.surface.brush.setKeepOuts(keepOuts, bounds);
  }

  private redraft(keepOuts: Box[], bounds: Box) {
    this.needsRedraft = false;
    this.surface.clear();
    this.surface.brush.setKeepOuts(keepOuts, bounds);
    let startDelay = 0;
    for (const route of planAmbientRoutes(buildFreeSpace(bounds[2], bounds[3], keepOuts))) {
      const duration = polylineLength(route) / HAND_SPEED_PX_PER_MS;
      this.surface.brush.draftRoute(route, duration, startDelay);
      startDelay += duration * ROUTE_OVERLAP;
    }
    this.surface.wake();
  }
}
