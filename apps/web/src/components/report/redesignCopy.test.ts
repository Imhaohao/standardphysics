import { describe, expect, it } from "vitest";
import type { Finding, SceneNode } from "@/types/contracts";
import type { ClauseRow, ScheduledMove } from "./redesign";
import { constructionSentence, describeMove, measuredAgainst, remedy, verdict } from "./redesignCopy";

const citation = { authority: "ADA_2010", edition: "2010 ADA Standards", section: "403.5.1", url: null } as const;

function finding(outcome: Finding["outcome"], fix: string | null = null): Finding {
  return {
    id: "path", check_id: "route_clear_width", outcome, title: "The path to the counter is too narrow", detail: "",
    fix, asks: null, measured_inches: 31, required_inches: 36, citation, locus: null,
  };
}

const row = (number: number, change: ClauseRow["change"]): ClauseRow => ({
  number, change, before: change === "new_problem" ? finding("passes") : finding("problem", "Clear a 36 inch path."),
  after: change === "cleared" ? finding("passes") : finding("problem"),
});

function scheduled(label: string, inchesAcross: number, serves: ClauseRow[], builtIn = false): ScheduledMove {
  return { node: { id: label, label } as SceneNode, inchesAcross, inchesUp: 0, turnDegrees: 0, builtIn, serves };
}

describe("verdict", () => {
  it("says how many spots fail and how many the plan clears", () => {
    expect(verdict([row(1, "cleared"), row(2, "cleared")], "Layout 2")).toBe("Two spots fail the 2010 ADA Standards. Layout 2 clears both.");
    expect(verdict([row(1, "cleared"), row(2, "still_fails")], "Layout 1")).toBe("Two spots fail the 2010 ADA Standards. Layout 1 clears 1 of them.");
  });

  it("owns up to a spot the plan would break", () => {
    expect(verdict([row(1, "cleared"), row(2, "new_problem")], "Layout 3"))
      .toBe("One spot fails the 2010 ADA Standards. Layout 3 clears it, and one spot that passes today would fail.");
  });

  it("does not claim a plan fixed anything when nothing failed", () => {
    expect(verdict([], "Layout 1")).toBe("Nothing the scan measured fails, as scanned or in Layout 1.");
    expect(verdict([], null)).toBe("Nothing the scan measured fails the 2010 ADA Standards.");
  });
});

describe("move copy", () => {
  it("describes a move in the drawing's directions and skips a nudge", () => {
    expect(describeMove(scheduled("Display case", -3.94, []))).toBe("3.9 in left");
    expect(describeMove({ ...scheduled("Chair", 0.1, []), inchesUp: 24, turnDegrees: -90 })).toBe("24 in up, turned 90°");
  });

  it("names the pieces that clear a spot, and falls back to the rule's own fix", () => {
    const cleared = row(1, "cleared");
    const stuck = row(2, "still_fails");
    const schedule = [scheduled("Display case", 4, [cleared]), scheduled("Display case", -4, [cleared])];
    expect(remedy(cleared, schedule, "Layout 2")).toBe("Layout 2 moves the display case, which clears it.");
    expect(remedy(stuck, schedule, "Layout 2")).toBe("Clear a 36 inch path.");
  });

  it("calls for construction only when a built-in piece moves", () => {
    expect(constructionSentence([scheduled("Chair", 4, [])])).toBe("Every piece it moves stands free, so it needs no construction.");
    expect(constructionSentence([scheduled("Ordering counter", 4, [], true)])).toBe("It relocates the ordering counter, which is built in, so it needs construction.");
  });

  it("sets the measurement against the section's number", () => {
    expect(measuredAgainst(finding("problem"))).toBe("Measured 31 in where 403.5.1 sets 36 in.");
  });
});
