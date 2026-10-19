import { afterEach, describe, expect, it, vi } from "vitest";
import type { Stamp } from "@/lib/brush/marks";
import { Debounced, keepOutBoxes, withoutContained } from "./keepOuts";
import { InkLoop, type InkSource, type LoopHost } from "./loop";
import { pixelRatioFor } from "./canvas";

function stamp(startsAt: number, endsAt: number): Stamp {
  return { marks: [], startsAt, endsAt };
}

class FakeSource implements InkSource {
  stamps: Stamp[] = [];
  constructor(private readonly clock: { now: number }) {}
  get busy() {
    return this.stamps.length > 0;
  }
  get nextStartAt() {
    return Math.min(Infinity, ...this.stamps.map((s) => s.startsAt));
  }
  get activeStamps() {
    return this.stamps;
  }
  tick() {
    const done = this.stamps.filter((s) => this.clock.now >= s.endsAt);
    this.stamps = this.stamps.filter((s) => this.clock.now < s.endsAt);
    return done;
  }
  takeAll() {
    const all = this.stamps;
    this.stamps = [];
    return all;
  }
}

function fakeHost(clock: { now: number }) {
  const frames: (() => void)[] = [];
  const timers: { at: number; run: () => void }[] = [];
  let hidden = false;
  const host: LoopHost = {
    requestFrame: (callback) => frames.push(callback),
    cancelFrame: () => frames.splice(0),
    setTimer: (callback, delay) => timers.push({ at: clock.now + delay, run: callback }),
    clearTimer: () => timers.splice(0),
    now: () => clock.now,
    isHidden: () => hidden,
  };
  return {
    host,
    frames,
    timers,
    hide: (value: boolean) => (hidden = value),
    runFrame: () => frames.shift()?.(),
  };
}

function setup() {
  const clock = { now: 0 };
  const source = new FakeSource(clock);
  const target = { bake: vi.fn(), drawLive: vi.fn(), clearLive: vi.fn() };
  const fake = fakeHost(clock);
  return { clock, source, target, fake, loop: new InkLoop(source, target, fake.host) };
}

describe("InkLoop", () => {
  it("schedules no frames while the pen is idle", () => {
    const { loop, fake } = setup();
    loop.wake();
    fake.runFrame();
    expect(fake.frames).toHaveLength(0);
    expect(fake.timers).toHaveLength(0);
    expect(loop.running).toBe(false);
  });

  it("animates while ink is drawing and stops once it is baked", () => {
    const { loop, fake, source, clock, target } = setup();
    source.stamps.push(stamp(0, 100));
    loop.wake();
    fake.runFrame();
    expect(target.drawLive).toHaveBeenCalled();
    expect(fake.frames).toHaveLength(1);
    clock.now = 150;
    fake.runFrame();
    expect(target.bake).toHaveBeenCalledTimes(1);
    fake.runFrame();
    expect(loop.running).toBe(false);
  });

  it("sleeps on a timer until a stamp scheduled for later", () => {
    const { loop, fake, source } = setup();
    source.stamps.push(stamp(5000, 6000));
    loop.wake();
    fake.runFrame();
    expect(fake.frames).toHaveLength(0);
    expect(fake.timers[0]?.at).toBe(5000);
  });

  it("does nothing while the tab is hidden", () => {
    const { loop, fake, source } = setup();
    source.stamps.push(stamp(0, 100));
    fake.hide(true);
    loop.wake();
    expect(fake.frames).toHaveLength(0);
    fake.hide(false);
    loop.wake();
    expect(fake.frames).toHaveLength(1);
  });

  it("bakes everything at once when instant", () => {
    const { loop, fake, source, target } = setup();
    source.stamps.push(stamp(0, 100), stamp(2000, 3000));
    loop.instant = true;
    loop.wake();
    fake.runFrame();
    expect(target.bake).toHaveBeenCalledWith(expect.arrayContaining([expect.any(Object), expect.any(Object)]));
    expect(loop.running).toBe(false);
  });
});

describe("keep-outs", () => {
  const rect = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom, width: right - left, height: bottom - top });

  it("offsets rects to the page and pads them", () => {
    expect(keepOutBoxes([rect(110, 220, 210, 260)], { left: 10, top: 20 }, 5)).toEqual([[95, 195, 205, 245]]);
  });

  it("drops empty rects and anything inside a bigger surface", () => {
    const boxes = keepOutBoxes([rect(0, 0, 400, 300), rect(20, 20, 100, 40), rect(50, 50, 50, 80), rect(500, 0, 600, 50)], { left: 0, top: 0 }, 0);
    expect(boxes).toEqual([[0, 0, 400, 300], [500, 0, 600, 50]]);
    expect(withoutContained([])).toEqual([]);
  });

  afterEach(() => vi.useRealTimers());

  it("debounces rescans to one after a burst of changes", () => {
    vi.useFakeTimers();
    const task = vi.fn();
    const debounced = new Debounced(task, 350);
    for (let i = 0; i < 20; i++) debounced.schedule();
    vi.advanceTimersByTime(349);
    expect(task).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(task).toHaveBeenCalledTimes(1);
  });

  it("caps the canvas pixel ratio", () => {
    expect(pixelRatioFor(800, 3)).toBe(2);
    expect(pixelRatioFor(20000, 2)).toBeCloseTo(0.6);
  });
});
