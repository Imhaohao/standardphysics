import { describe, expect, it } from "vitest";
import type { Assessment, Finding, Scan } from "@/types/contracts";
import { formatMinutes, inspectionBusinessDays, measurementsTaken, minutesToResults } from "./turnaround";

const scan = { created_at: "2026-09-28T05:26:30Z" } as Scan;

function assessment(createdAt: string, measured: (number | null)[] = []): Assessment {
  const findings = measured.map((measured_inches) => ({ measured_inches }) as Finding);
  return { created_at: createdAt, findings } as Assessment;
}

describe("time saved", () => {
  it("measures the minutes from upload to the first results, whenever the checks last ran", () => {
    const ready = { ...scan, results_ready_at: "2026-09-28T05:29:42Z" };
    expect(minutesToResults(ready)).toBeCloseTo(3.2);
  });

  it("has no time to report before results, or when the stamps run backwards", () => {
    expect(minutesToResults({ ...scan, results_ready_at: null })).toBeNull();
    expect(minutesToResults({ ...scan, results_ready_at: "2026-09-28T05:00:00Z" })).toBeNull();
  });

  it("writes the wait the way a person says it", () => {
    expect([0.4, 13.5, 60, 95].map(formatMinutes)).toEqual(["Under a minute", "14 minutes", "1 hour", "1 hour 35 min"]);
  });

  it("counts only the checks that came back with a number", () => {
    expect(measurementsTaken(assessment("2026-09-28T05:40:00Z", [31, null, 47]))).toBe(2);
  });

  it("adds the day on site to the published report turnaround", () => {
    expect(inspectionBusinessDays()).toEqual({ fewest: 4, most: 6 });
  });
});
