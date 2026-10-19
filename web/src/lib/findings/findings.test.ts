import { describe, expect, it } from "vitest";
import { SAMPLE_FINDINGS, SAMPLE_SCENE } from "@/fixtures/sample";
import { indexSubjects } from "@/lib/scene/describe";
import { citation, formatMeasured, formatQuantity, formatRequirement } from "./format";
import { countStatuses, groupByElement, ownerQuestions, sectionKey } from "./group";
import { findingPins } from "./pins";
import type { Finding } from "./types";

function finding(overrides: Partial<Finding>): Finding {
  return { rule_id: "r", jurisdiction: "ADA2010", section: "404.2.3", subject_id: "door", status: "pass", measured: null, required: null, message: "", evidence: null, ...overrides };
}

describe("formatting", () => {
  it("formats quantities and requirements", () => {
    expect(formatQuantity(32, "in")).toBe('32"');
    expect(formatQuantity(29.44, "in")).toBe('29.4"');
    expect(formatQuantity(1 / 12, "ratio")).toBe("1:12");
    expect(formatMeasured({ value: 5, unit: "lbf" })).toBe("5 lbf");
    expect(formatRequirement({ op: ">=", value: 32, unit: "in" })).toBe('32" min');
    expect(formatRequirement({ op: "between", value: [15, 48], unit: "in" })).toBe('15" to 48"');
    expect(formatRequirement("Provide a level landing")).toBe("Provide a level landing");
    expect(formatRequirement({ any: true })).toBeNull();
  });

  it("cites each code its own way", () => {
    expect(citation({ jurisdiction: "ADA2010", section: "404.2.3" })).toBe("§404.2.3");
    expect(citation({ jurisdiction: "CBC11B", section: "11B-404.2.3" })).toBe("§11B-404.2.3");
    expect(citation({ jurisdiction: "CBC11B", section: "404.2.3" })).toBe("§11B-404.2.3");
    expect(sectionKey("§ 11B-404.2.3")).toBe("404.2.3");
  });
});

describe("grouping", () => {
  const findings = [
    finding({ jurisdiction: "ADA2010", status: "pass" }),
    finding({ jurisdiction: "CBC11B", section: "11B-404.2.3", status: "fail" }),
    finding({ section: "404.2.4", status: "needs_info", message: "Which way does the door swing?" }),
    finding({ jurisdiction: "CBC11B", section: "11B-404.2.4", status: "needs_info", message: "Which way does the door swing?" }),
    finding({ subject_id: "shelf", section: "902", status: "pass" }),
    finding({ subject_id: "shelf", section: "903", status: "not_applicable" }),
  ];
  const groups = groupByElement(findings, new Map());

  it("pairs ADA and CBC by section and lets the stricter one govern", () => {
    const door = groups[0]!;
    expect(door.subjectId).toBe("door");
    expect(door.status).toBe("fail");
    expect(door.pairs.map((pair) => pair.key)).toEqual(["404.2.3", "404.2.4"]);
    expect(door.pairs[0]!.ada?.status).toBe("pass");
    expect(door.pairs[0]!.governing.jurisdiction).toBe("CBC11B");
  });

  it("drops not-applicable findings and orders worst first", () => {
    expect(groups.map((group) => group.subjectId)).toEqual(["door", "shelf"]);
    expect(groups[1]!.pairs).toHaveLength(1);
  });

  it("asks each owner question once", () => {
    expect(ownerQuestions(groups).map((q) => q.question)).toEqual(["Which way does the door swing?"]);
    expect(countStatuses(findings)).toEqual({ pass: 2, fail: 1, needs_info: 2, not_applicable: 1 });
  });

  it("pins only elements that need something, numbered in report order", () => {
    const sampleGroups = groupByElement(SAMPLE_FINDINGS, indexSubjects(SAMPLE_SCENE));
    const pins = findingPins(sampleGroups);
    expect(pins.length).toBeGreaterThan(0);
    expect(pins.map((pin) => pin.label)).toEqual(pins.map((_, index) => String(index + 1)));
    expect(pins.every((pin) => pin.status === "fail" || pin.status === "needs_info")).toBe(true);
  });

  it("only cites subjects that exist in the sample scene", () => {
    const subjects = indexSubjects(SAMPLE_SCENE);
    for (const sample of SAMPLE_FINDINGS) expect(subjects.has(sample.subject_id)).toBe(true);
  });
});
