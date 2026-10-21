import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { coverageCitation, coverageSummary, RULEPACK_COVERAGE, type CoverageEntry } from "./coverage";

function entry(overrides: Partial<CoverageEntry>): CoverageEntry {
  return { jurisdiction: "ADA2010", section: "404.2", title: "Doors", status: "covered", rule_ids: [], reason: "", ...overrides };
}

describe("rulepack coverage", () => {
  it("counts each status per jurisdiction and keeps every deferred section with its reason", () => {
    const summary = coverageSummary([
      entry({}),
      entry({ section: "201", status: "not_applicable_to_scope" }),
      entry({ section: "207", title: "Egress", status: "deferred", reason: "Needs egress analysis." }),
      entry({ jurisdiction: "CBC11B", section: "11B-404.2" }),
    ]);
    expect(summary.map(({ jurisdiction, covered, notApplicable }) => [jurisdiction, covered, notApplicable])).toEqual([
      ["ADA2010", 1, 1],
      ["CBC11B", 1, 0],
    ]);
    expect(summary[0]!.deferred).toEqual([{ citation: "§207", title: "Egress", reason: "Needs egress analysis." }]);
    expect(summary[0]!.name).toBe("2010 ADA Standards");
  });

  it("cites code sections with a section mark and regulations as written", () => {
    expect(coverageCitation({ jurisdiction: "CBC11B", section: "11B-202.5" })).toBe("§11B-202.5");
    expect(coverageCitation({ jurisdiction: "CBC11B", section: "1013.4" })).toBe("§1013.4");
    expect(coverageCitation({ jurisdiction: "ADA2010", section: "28 CFR 36.211" })).toBe("28 CFR 36.211");
  });

  it("matches rules/coverage.json as built into the site", () => {
    const raw = JSON.parse(readFileSync(new URL("../../../rules/coverage.json", import.meta.url), "utf8")) as { entries: CoverageEntry[] };
    const total = RULEPACK_COVERAGE.reduce((sum, entry) => sum + entry.covered + entry.notApplicable + entry.deferred.length, 0);
    expect(total).toBe(raw.entries.length);
    expect(RULEPACK_COVERAGE.map((entry) => entry.jurisdiction)).toEqual(["ADA2010", "CBC11B"]);
  });
});
