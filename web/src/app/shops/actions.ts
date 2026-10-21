"use server";

import { ApiError } from "@/lib/api/client";
import type { AnswerInput, Report } from "@/lib/api/types";
import { ownerApi } from "@/lib/session";

export type SaveAnswersResult = { report: Report; error: null } | { report: null; error: string };

const ANSWER_VALUE_TYPES = new Set(["boolean", "number", "string"]);

function isAnswerInput(input: unknown): input is AnswerInput {
  const answer = input as Partial<AnswerInput> | null;
  if (typeof answer?.subject_id !== "string" || typeof answer.metric !== "string") return false;
  return answer.value === null || ANSWER_VALUE_TYPES.has(typeof answer.value);
}

const STATUS_ERRORS: Record<number, string> = {
  404: "We couldn't find this scan any more. It may have been deleted.",
  409: "This scan hasn't been checked yet, so there's nothing to answer. Try again once the report is ready.",
};

/** What to tell the owner when sp-server turns a request down. */
function explain(error: unknown) {
  if (error instanceof ApiError && error.unauthorized) return "Your session has ended. Sign in again to save your answers.";
  if (error instanceof ApiError && STATUS_ERRORS[error.status]) return STATUS_ERRORS[error.status]!;
  return "We couldn't reach Standard Physics just now. Try again in a minute.";
}

/** Stores the owner's answers and hands back the report re-evaluated with them. */
export async function saveAnswers(scanId: string, answers: unknown[]): Promise<SaveAnswersResult> {
  if (!answers.every(isAnswerInput)) return { report: null, error: "Some of those answers didn't come through. Reload the page and try again." };
  const { api } = await ownerApi();
  try {
    return { report: await api.saveAnswers(scanId, answers), error: null };
  } catch (error) {
    return { report: null, error: explain(error) };
  }
}
