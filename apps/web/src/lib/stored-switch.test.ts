import { afterEach, describe, expect, it, vi } from "vitest";
import { readSwitch, writeSwitch } from "./stored-switch";

function storage(items: Record<string, string> = {}) {
  return { getItem: (key: string) => items[key] ?? null, setItem: (key: string, value: string) => { items[key] = value; }, items };
}

function refusing() {
  const refuse = () => { throw new DOMException("The operation is insecure.", "SecurityError"); };
  return { getItem: refuse, setItem: refuse };
}

afterEach(() => vi.unstubAllGlobals());

describe("a switch this browser remembers", () => {
  it("reads back what was chosen, and the default until something was", () => {
    const local = storage();
    vi.stubGlobal("window", { localStorage: local });
    expect(readSwitch("sp_clearance_map", false)).toBe(false);
    writeSwitch("sp_clearance_map", true);
    expect(local.items.sp_clearance_map).toBe("on");
    expect(readSwitch("sp_clearance_map", false)).toBe(true);
    writeSwitch("sp_clearance_map", false);
    expect(readSwitch("sp_clearance_map", true)).toBe(false);
  });

  it("falls back to the default, and forgets quietly, where the browser refuses storage", () => {
    vi.stubGlobal("window", { localStorage: refusing() });
    expect(readSwitch("sp_clearance_map", false)).toBe(false);
    expect(() => writeSwitch("sp_clearance_map", true)).not.toThrow();
  });
});
