import { describe, expect, it } from "vitest";
import { SAMPLE_REPORT, SAMPLE_SCENE } from "@/fixtures/sample";
import { sampleReportWithAnswers } from "@/fixtures/sampleAsks";
import { indexSubjects } from "@/lib/scene/describe";
import { groupByElement } from "./group";
import { answersToSave, choicesFor, elementQuestions, parseAnswer, questionCount, questionKey, type OwnerQuestion } from "./questions";
import type { Ask, Finding } from "./types";

const latch: Ask = { metric: "door.has_latch", prompt: "Does this door have a latch?", value_type: "boolean", unit: "", options: [], photo: true };

function finding(overrides: Partial<Finding>): Finding {
  return { rule_id: "r", jurisdiction: "ADA2010", section: "404.2.3", title: "", subject_id: "door", status: "needs_info", measured: null, required: "", message: "", evidence: "", severity: "violation", ...overrides };
}

function question(ask: Partial<Ask>): OwnerQuestion {
  return { key: "q", subjectId: "door", ask: { ...latch, ...ask }, checks: [] };
}

describe("owner questions", () => {
  const findings = [
    finding({ rule_id: "ADA-404.2.9", counterpart: "CBC-404.2.9", section: "404.2.9", ask: latch }),
    finding({ rule_id: "CBC-404.2.9", counterpart: "ADA-404.2.9", jurisdiction: "CBC11B", section: "11B-404.2.9", ask: latch }),
    finding({ rule_id: "ADA-404.2.8", section: "404.2.8", ask: latch }),
    finding({ rule_id: "ADA-302.1", section: "302.1", message: "Slope: needs more information (no scan mesh was captured)." }),
    finding({ rule_id: "ADA-404.2.3", status: "fail" }),
  ];
  const groups = groupByElement(findings, new Map());

  it("asks one question per subject and metric, covering every check it settles", () => {
    const [door] = elementQuestions(groups);
    expect(door!.questions).toHaveLength(1);
    expect(door!.questions[0]!.key).toBe(questionKey("door", "door.has_latch"));
    expect(door!.questions[0]!.checks.map((pair) => pair.key)).toEqual(["404.2.8", "ADA-404.2.9"]);
    expect(door!.openChecks).toHaveLength(1);
    expect(questionCount(elementQuestions(groups))).toBe(2);
  });

  it("finds asks in the sample shop once the fixture adds them", () => {
    const report = sampleReportWithAnswers(SAMPLE_REPORT, new Map());
    const elements = elementQuestions(groupByElement(report.findings, indexSubjects(SAMPLE_SCENE)));
    const asked = elements.flatMap((entry) => entry.questions);
    expect(asked.length).toBeGreaterThan(5);
    expect(new Set(asked.map((entry) => entry.key)).size).toBe(asked.length);
  });
});

describe("parsing answers", () => {
  it("reads yes and no, and ignores a blank", () => {
    expect(parseAnswer(latch, "yes")).toEqual({ kind: "value", value: true });
    expect(parseAnswer(latch, "no")).toEqual({ kind: "value", value: false });
    expect(parseAnswer(latch, "  ")).toEqual({ kind: "blank" });
    expect(parseAnswer(latch, "maybe").kind).toBe("invalid");
  });

  it("reads numbers, and insists on whole ones for integers", () => {
    const inches: Pick<Ask, "value_type" | "options"> = { value_type: "number", options: [] };
    expect(parseAnswer(inches, "32.5")).toEqual({ kind: "value", value: 32.5 });
    expect(parseAnswer(inches, "1,200")).toEqual({ kind: "value", value: 1200 });
    expect(parseAnswer(inches, "about 30").kind).toBe("invalid");
    expect(parseAnswer({ value_type: "integer", options: [] }, "2.5").kind).toBe("invalid");
    expect(parseAnswer({ value_type: "integer", options: [] }, "2")).toEqual({ kind: "value", value: 2 });
  });

  it("accepts only an enum's own options", () => {
    const facility: Pick<Ask, "value_type" | "options"> = { value_type: "enum", options: ["retail", "restaurant"] };
    expect(parseAnswer(facility, "retail")).toEqual({ kind: "value", value: "retail" });
    expect(parseAnswer(facility, "bank").kind).toBe("invalid");
    expect(choicesFor({ value_type: "enum", options: ["pre_1993"] })).toEqual([["pre_1993", "Pre 1993"]]);
    expect(choicesFor(latch)).toEqual([["yes", "Yes"], ["no", "No"]]);
  });

  it("sends only filled drafts and reports the ones it can't read", () => {
    const questions = [{ ...question({}), key: "a" }, { ...question({ metric: "door.projection_34_80", value_type: "number", unit: "in" }), key: "b" }, { ...question({}), key: "c" }];
    const { answers, errors } = answersToSave(questions, { a: "no", b: "four" });
    expect(answers).toEqual([{ subject_id: "door", metric: "door.has_latch", value: false }]);
    expect(Object.keys(errors)).toEqual(["b"]);
  });
});
