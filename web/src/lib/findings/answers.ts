import type { Answer, AnswerValue } from "@/lib/api/types";
import { sentenceCase, type Subject } from "@/lib/scene/describe";

/** An answer already given, ready to list: which element, what it was about and what was said. */
export interface GivenAnswer {
  key: string;
  answer: Answer;
  element: string;
  topic: string;
  value: string;
  fromPhoto: boolean;
}

/** "door.has_latch" reads as "Has latch". Answers carry only the metric id, not the question that was asked. */
export function metricLabel(metric: string) {
  return sentenceCase(metric.slice(metric.indexOf(".") + 1));
}

const VALUE_WORDS: Record<string, (value: AnswerValue) => string> = {
  boolean: (value) => (value ? "Yes" : "No"),
  number: (value) => String(value),
  string: (value) => sentenceCase(String(value)),
};

export function formatAnswerValue(value: AnswerValue) {
  if (value === null) return "";
  return VALUE_WORDS[typeof value]?.(value) ?? String(value);
}

/** The owner's answers, grouped by element in name order, newest first within an element. */
export function givenAnswers(answers: readonly Answer[], subjects: ReadonlyMap<string, Subject>): GivenAnswer[] {
  return answers
    .filter((answer) => answer.value !== null)
    .map((answer) => ({
      key: JSON.stringify([answer.subject_id, answer.metric]),
      answer,
      element: subjects.get(answer.subject_id)?.name ?? "Whole shop",
      topic: metricLabel(answer.metric),
      value: formatAnswerValue(answer.value),
      fromPhoto: answer.source === "photo",
    }))
    .sort((a, b) => a.element.localeCompare(b.element, undefined, { numeric: true }) || b.answer.answered_at.localeCompare(a.answer.answered_at));
}
