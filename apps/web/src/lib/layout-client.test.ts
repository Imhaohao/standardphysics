import { afterEach, describe, expect, it, vi } from "vitest";
import { checkLayout, LAYOUT_CHECK_DEADLINE_MS } from "./layout-client";

/** A server that never answers, but gives up the way a real fetch does when its signal aborts. */
function stalledServer() {
  return vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
  }));
}

/** AbortSignal.timeout runs on the runtime's own clock, so it is rebuilt on the faked setTimeout. */
function timeoutOnFakeClock() {
  vi.spyOn(AbortSignal, "timeout").mockImplementation((milliseconds) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(new DOMException("timed out", "TimeoutError")), milliseconds);
    return controller.signal;
  });
}

describe("checkLayout", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("gives up on a check the server never answers", async () => {
    vi.useFakeTimers();
    timeoutOnFakeClock();
    vi.stubGlobal("fetch", stalledServer());
    const checking = checkLayout("scan", 0, 1, []);
    const outcome = expect(checking).rejects.toMatchObject({ name: "TimeoutError" });
    await vi.advanceTimersByTimeAsync(LAYOUT_CHECK_DEADLINE_MS - 1);
    expect(AbortSignal.timeout).toHaveBeenCalledWith(LAYOUT_CHECK_DEADLINE_MS);
    await vi.advanceTimersByTimeAsync(1);
    await outcome;
  });

  it("waits two minutes before giving up", () => {
    expect(LAYOUT_CHECK_DEADLINE_MS).toBe(120_000);
  });
});
