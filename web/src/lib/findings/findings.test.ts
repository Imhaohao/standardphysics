import { describe, expect, it } from "vitest";
import { SAMPLE_FINDINGS, SAMPLE_SCENE } from "@/fixtures/sample";
import { indexSubjects } from "@/lib/scene/describe";
import { citation, formatMeasured, formatQuantity, formatRequirement, missingReason, ownerAsk } from "./format";
import { countStatuses, groupByElement, sectionKey } from "./group";
import { elementQuestions } from "./questions";
import { findingPins } from "./pins";
import type { Finding } from "./types";

function finding(overrides: Partial<Finding>): Finding {
  return { rule_id: "r", jurisdiction: "ADA2010", section: "404.2.3", title: "", subject_id: "door", status: "pass", measured: null, required: "", message: "", evidence: "", severity: "violation", ...overrides };
}

describe("formatting", () => {
  it("formats quantities and measurements", () => {
    expect(formatQuantity(32, "in")).toBe('32"');
    expect(formatQuantity(29.44, "in")).toBe('29.4"');
    expect(formatQuantity(1 / 12, "ratio")).toBe("1:12");
    expect(formatMeasured({ text: "5", value: 5, unit: "lbf" })).toBe("5 lbf");
    expect(formatMeasured({ text: "33.5-34.5", value: 34.5, lo: 33.5, hi: 34.5, unit: "in" })).toBe('33.5" to 34.5"');
    expect(formatMeasured({ text: "yes", value: null, unit: "" })).toBe("yes");
    expect(formatMeasured(null)).toBeNull();
  });

  it("reads sp-core requirement strings", () => {
    expect(formatRequirement(">= 36 in")).toBe('36" min');
    expect(formatRequirement("<= 48 in")).toBe('48" max');
    expect(formatRequirement("between 28 and 34 in")).toBe('28" to 34"');
    expect(formatRequirement(">= 36 in and <= 48 in")).toBe('36" min and 48" max');
    expect(formatRequirement(">= 1")).toBe("1 min");
    expect(formatRequirement("true")).toBe("true");
    expect(formatRequirement("")).toBeNull();
  });

  it("turns what the engine is missing into a plain ask", () => {
    const needs = (reason: string) => ({ message: `Thing: needs more information (${reason}).` });
    expect(ownerAsk(needs("needs a photo of the element (door.has_latch)"))).toBe("Send us a photo of it.");
    expect(ownerAsk(needs("scope unknown: needs a photo or tape measurement; the scan box does not resolve this detail"))).toBe("Measure it, or send us a photo.");
    expect(ownerAsk(needs("something new"))).toBe("Something new");
    expect(missingReason({ message: "Thing: measured 3 in, required >= 4 in." })).toBeNull();
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
    finding({ jurisdiction: "ADA2010", rule_id: "ada.door.width", counterpart: "cbc.door.width", status: "pass" }),
    finding({ jurisdiction: "CBC11B", rule_id: "cbc.door.width", counterpart: "ada.door.width", section: "11B-404.2.3", status: "fail" }),
    finding({ section: "404.2.4", status: "needs_info", title: "Door swing", message: "Door swing: needs more information (overlaps a fixture's clear floor if the door swings in; swing not captured)." }),
    finding({ jurisdiction: "CBC11B", section: "11B-404.2.4", status: "needs_info", title: "Door swing", message: "Door swing: needs more information (overlaps a fixture's clear floor if the door swings in; swing not captured)." }),
    finding({ subject_id: "shelf", section: "902", status: "pass" }),
    finding({ subject_id: "shelf", section: "903", status: "not_applicable" }),
  ];
  const groups = groupByElement(findings, new Map());

  it("pairs ADA and CBC by section and lets the stricter one govern", () => {
    const door = groups[0]!;
    expect(door.subjectId).toBe("door");
    expect(door.status).toBe("fail");
    expect(door.pairs.map((pair) => pair.key)).toEqual(["ada.door.width", "404.2.4"]);
    expect(door.pairs[0]!.ada?.status).toBe("pass");
    expect(door.pairs[0]!.governing.jurisdiction).toBe("CBC11B");
  });

  it("never lets a second finding for the same requirement overwrite the first", () => {
    const shared = [
      finding({ subject_id: "floor:room", rule_id: "ADA-303.2", counterpart: "CBC-303.2", status: "fail" }),
      finding({ subject_id: "route:room", rule_id: "ADA-303.2", counterpart: "CBC-303.2", status: "pass" }),
      finding({ subject_id: "room", jurisdiction: "CBC11B", rule_id: "CBC-403.5.1-a", section: "11B-403.5.1", status: "fail" }),
      finding({ subject_id: "room", jurisdiction: "CBC11B", rule_id: "CBC-403.5.1-b", section: "11B-403.5.1", status: "pass" }),
    ];
    const subjects = new Map([
      ["floor:room", { groupId: "room" }],
      ["route:room", { groupId: "room" }],
      ["room", { groupId: "room" }],
    ]) as unknown as Parameters<typeof groupByElement>[1];
    const [group] = groupByElement(shared, subjects);
    expect(group!.status).toBe("fail");
    expect(group!.pairs).toHaveLength(4);
    expect(group!.pairs.filter((pair) => pair.governing.status === "fail")).toHaveLength(2);
    expect(new Set(group!.pairs.map((pair) => pair.key)).size).toBe(4);
  });

  it("drops not-applicable findings and orders worst first", () => {
    expect(groups.map((group) => group.subjectId)).toEqual(["door", "shelf"]);
    expect(groups[1]!.pairs).toHaveLength(1);
  });

  it("asks each owner question once", () => {
    const questions = elementQuestions(groups);
    expect(questions.map((entry) => entry.group.subjectId)).toEqual(["door"]);
    expect(questions[0]!.openChecks.map((check) => [check.checks.map((pair) => pair.governing.title), check.ask])).toEqual([[["Door swing"], "Tell us which way the door swings."]]);
    expect(countStatuses(findings)).toEqual({ pass: 2, fail: 1, needs_info: 2, not_applicable: 1 });
  });

  it("pins only elements that need something, numbered in report order", () => {
    const sampleGroups = groupByElement(SAMPLE_FINDINGS, indexSubjects(SAMPLE_SCENE));
    const pins = findingPins(sampleGroups);
    expect(pins.length).toBeGreaterThan(0);
    expect(pins.map((pin) => pin.label)).toEqual(pins.map((_, index) => String(index + 1)));
    expect(pins.every((pin) => pin.status === "fail" || pin.status === "needs_info")).toBe(true);
  });

  it("names every subject the engine reports on except the site as a whole", () => {
    const subjects = indexSubjects(SAMPLE_SCENE);
    const unnamed = new Set(SAMPLE_FINDINGS.map((finding) => finding.subject_id).filter((id) => !subjects.has(id)));
    expect([...unnamed]).toEqual(["site"]);
  });
});
