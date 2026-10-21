import { describe, expect, it } from "vitest";
import type { Answer } from "@/lib/api/types";
import type { Subject } from "@/lib/scene/describe";
import { formatAnswerValue, givenAnswers, metricLabel } from "./answers";

function answer(overrides: Partial<Answer>): Answer {
  return { subject_id: "door-1", metric: "door.has_latch", value: true, answered_at: "2026-10-20T10:00:00Z", source: "owner", confidence: 1, photo_artifact_id: null, ...overrides };
}

describe("given answers", () => {
  it("reads metric ids and values in plain words", () => {
    expect(metricLabel("door.is_fire_door")).toBe("Is fire door");
    expect(formatAnswerValue(false)).toBe("No");
    expect(formatAnswerValue(32.5)).toBe("32.5");
    expect(formatAnswerValue("pre_1993")).toBe("Pre 1993");
  });

  it("names each element, marks photo answers and orders by element", () => {
    const subjects = new Map([["door-1", { name: "Door" } as Subject]]);
    const rows = givenAnswers(
      [answer({ subject_id: "site", metric: "site.has_customer_parking", value: false }), answer({ source: "photo", confidence: 0.9, photo_artifact_id: "a1" }), answer({ metric: "door.gone", value: null })],
      subjects,
    );
    expect(rows.map((row) => [row.element, row.topic, row.value, row.fromPhoto])).toEqual([
      ["Door", "Has latch", "Yes", true],
      ["Whole shop", "Has customer parking", "No", false],
    ]);
  });
});
