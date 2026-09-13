import { describe, expect, it } from "vitest";
import type { Assessment, Scan } from "@/types/contracts";
import { scanStatus } from "./scan-status";

const scan = { state: "ready" } as Scan;
const assessment = (rulesChecked: number | null): Assessment => ({ findings: [], rules_checked: rulesChecked }) as unknown as Assessment;

describe("scanStatus", () => {
  it("never calls an unchecked shop a pass", () => {
    expect(scanStatus(scan, assessment(0))).toBe("Checks start once a person reviews the rules");
  });

  it("calls a checked shop with no findings a pass", () => {
    expect(scanStatus(scan, assessment(13))).toBe("Everything we checked passes");
  });

  it("shows the processing state until there is an assessment", () => {
    expect(scanStatus({ state: "failed" } as Scan, null)).toBe("This scan didn't go through. Scan the shop again.");
    expect(scanStatus(scan, null)).toBe("Ready");
  });
});
