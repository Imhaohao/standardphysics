"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import type { AnswerInput, Report } from "@/lib/api/types";
import { scanChangesFrom } from "@/lib/scanNames";
import { ownerApi } from "@/lib/session";

export type SaveAnswersResult = { report: Report; error: null } | { report: null; error: string };

const ANSWER_VALUE_TYPES = new Set(["boolean", "number", "string"]);

function isAnswerInput(input: unknown): input is AnswerInput {
  const answer = input as Partial<AnswerInput> | null;
  if (typeof answer?.subject_id !== "string" || typeof answer.metric !== "string") return false;
  return answer.value === null || ANSWER_VALUE_TYPES.has(typeof answer.value);
}

const STATUS_ERRORS: Record<number, string> = {
  401: "Your session has ended. Sign in again, then try once more.",
  404: "We couldn't find this scan any more. It may have been deleted.",
  409: "This scan hasn't been checked yet, so there's nothing to answer. Try again once the report is ready.",
};

/** What to tell the owner when sp-server turns a request down. */
function explain(error: unknown) {
  const known = error instanceof ApiError ? STATUS_ERRORS[error.status] : undefined;
  return known ?? "We couldn't reach Standard Physics just now. Try again in a minute.";
}

/** Runs one owner request and turns a failure into words for the page. */
async function attempt(request: () => Promise<unknown>) {
  try {
    await request();
    return null;
  } catch (error) {
    return explain(error);
  }
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

/** Renames a scan and its shop. Resolves to an error to show, or null. */
export async function renameScan(scanId: string, name: string, siteName: string) {
  const { changes, error } = scanChangesFrom(name, siteName);
  if (!changes) return error;
  const { api } = await ownerApi();
  const failure = await attempt(() => api.updateScan(scanId, changes));
  if (!failure) revalidatePath("/", "layout");
  return failure;
}

/** Deletes a scan with its plan, report and files, then goes back to the list. */
export async function deleteScan(scanId: string) {
  const { api } = await ownerApi();
  const failure = await attempt(() => api.deleteScan(scanId));
  if (failure) return failure;
  revalidatePath("/", "layout");
  redirect("/shops");
}
