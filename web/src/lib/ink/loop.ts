import type { Stamp } from "@/lib/brush/marks";

export interface InkSource {
  readonly busy: boolean;
  readonly nextStartAt: number;
  readonly activeStamps: readonly Stamp[];
  tick(): Stamp[];
  takeAll(): Stamp[];
}

export interface InkTarget {
  bake(stamps: readonly Stamp[]): void;
  drawLive(stamps: readonly Stamp[], now: number): void;
  clearLive(): void;
}

/** The browser hooks the loop needs, injectable so tests can drive frames by hand. */
export interface LoopHost {
  requestFrame(callback: () => void): number;
  cancelFrame(handle: number): void;
  setTimer(callback: () => void, delayMs: number): number;
  clearTimer(handle: number): void;
  now(): number;
  isHidden(): boolean;
}

export function browserLoopHost(): LoopHost {
  return {
    requestFrame: (callback) => requestAnimationFrame(callback),
    cancelFrame: (handle) => cancelAnimationFrame(handle),
    setTimer: (callback, delayMs) => window.setTimeout(callback, delayMs),
    clearTimer: (handle) => window.clearTimeout(handle),
    now: () => performance.now(),
    isHidden: () => document.visibilityState === "hidden",
  };
}

/**
 * Drives the pen only while there is ink to draw. When nothing is moving it schedules no frames at all,
 * sleeps on a timer until the next scheduled stamp, and stops entirely while the tab is hidden.
 */
export class InkLoop {
  private frameHandle: number | null = null;
  private timerHandle: number | null = null;
  private liveIsDirty = false;
  instant = false;

  constructor(
    private readonly source: InkSource,
    private readonly target: InkTarget,
    private readonly host: LoopHost,
  ) {}

  get running() {
    return this.frameHandle !== null || this.timerHandle !== null;
  }

  wake() {
    if (this.frameHandle !== null || this.host.isHidden()) return;
    this.cancelTimer();
    this.frameHandle = this.host.requestFrame(() => this.frame());
  }

  pause() {
    if (this.frameHandle !== null) this.host.cancelFrame(this.frameHandle);
    this.frameHandle = null;
    this.cancelTimer();
  }

  dispose() {
    this.pause();
  }

  /** Lays every pending stroke down finished, right now. */
  flush() {
    const finished = this.source.takeAll();
    if (finished.length > 0) this.target.bake(finished);
    if (this.liveIsDirty) this.target.clearLive();
    this.liveIsDirty = false;
  }

  private cancelTimer() {
    if (this.timerHandle !== null) this.host.clearTimer(this.timerHandle);
    this.timerHandle = null;
  }

  private frame() {
    this.frameHandle = null;
    const finished = this.instant ? this.source.takeAll() : this.source.tick();
    if (finished.length > 0) this.target.bake(finished);
    this.drawLive();
    this.scheduleNext();
  }

  private drawLive() {
    const now = this.host.now();
    const started = this.source.activeStamps.filter((stamp) => stamp.startsAt <= now);
    if (started.length === 0 && !this.liveIsDirty) return;
    this.target.clearLive();
    this.liveIsDirty = started.length > 0;
    if (this.liveIsDirty) this.target.drawLive(started, now);
  }

  private scheduleNext() {
    if (!this.source.busy) return;
    const wait = this.source.nextStartAt - this.host.now();
    if (this.liveIsDirty || wait <= 16 || !Number.isFinite(wait)) {
      this.wake();
      return;
    }
    this.timerHandle = this.host.setTimer(() => {
      this.timerHandle = null;
      this.wake();
    }, wait);
  }
}
