import { describe, expect, it } from "vitest";
import type { Assessment, Scan } from "@/types/contracts";
import { allClearSentence, scanStatus } from "./scan-status";

const scan = { state: "ready" } as Scan;
const assessment = (rulesChecked: number | null): Assessment => ({ findings: [], rules_checked: rulesChecked }) as unknown as Assessment;

describe("scanStatus", () => {
  it("never calls an unchecked shop a pass", () => {
    expect(scanStatus(scan, assessment(0), true)).toBe("Checks start once a person reviews the rules");
    expect(scanStatus(scan, assessment(0), false)).toBe("Checks start once a person reviews the rules");
  });

  it("calls a checked shop with no findings a pass", () => {
    expect(scanStatus(scan, assessment(13), true)).toBe("Everything we checked passes");
  });

  it("asks for the route before calling a shop without one a pass", () => {
    expect(scanStatus(scan, assessment(8), false)).toBe(
      "Everything we checked passes so far. Mark the customer route to check the paths too.",
    );
  });

  it("shows the processing state until there is an assessment", () => {
    expect(scanStatus({ state: "failed" } as Scan, null, false)).toBe("This scan didn't go through. Scan the shop again.");
    expect(scanStatus(scan, null, false)).toBe("Ready");
  });
});

describe("allClearSentence", () => {
  it("keeps a layout's pass inside what ran", () => {
    const passes = "This layout passes everything we checked";
    expect(allClearSentence({ rulesChecked: 13, routeConfirmed: true }, passes)).toBe(passes);
    expect(allClearSentence({ rulesChecked: null, routeConfirmed: false }, passes)).toBe(`${passes} so far. Mark the customer route to check the paths too.`);
    expect(allClearSentence({ rulesChecked: 0, routeConfirmed: true }, passes)).toBe("Checks start once a person reviews the rules");
  });
});
