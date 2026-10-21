import type { AnswerInput, AnswerValue } from "@/lib/api/types";
import { sentenceCase } from "@/lib/scene/describe";
import { ownerAsk } from "./format";
import type { ElementGroup, FindingPair } from "./group";
import type { Ask, AskValueType, Finding } from "./types";

/** One question the owner can answer here. ADA and California checks on the same subject and metric share it. */
export interface OwnerQuestion {
  key: string;
  subjectId: string;
  ask: Ask;
  checks: FindingPair[];
}

/** An open check with nothing to answer here yet, such as a slope the scan couldn't measure. */
export interface OpenCheck {
  ask: string;
  checks: FindingPair[];
}

export interface ElementQuestions {
  group: ElementGroup;
  questions: OwnerQuestion[];
  openChecks: OpenCheck[];
}

export const questionKey = (subjectId: string, metric: string) => JSON.stringify([subjectId, metric]);

function askingFinding(pair: FindingPair): (Finding & { ask: Ask }) | null {
  const finding = [pair.governing, pair.ada, pair.cbc].find((candidate) => candidate?.status === "needs_info" && candidate.ask);
  return (finding as (Finding & { ask: Ask }) | undefined) ?? null;
}

function addTo<T extends { checks: FindingPair[] }>(byKey: Map<string, T>, key: string, pair: FindingPair, create: () => T) {
  const entry = byKey.get(key) ?? create();
  entry.checks.push(pair);
  byKey.set(key, entry);
}

function questionsFor(group: ElementGroup): ElementQuestions {
  const questions = new Map<string, OwnerQuestion>();
  const openChecks = new Map<string, OpenCheck>();
  for (const pair of group.pairs.filter((candidate) => candidate.governing.status === "needs_info")) {
    const asking = askingFinding(pair);
    if (asking) {
      const subjectId = asking.ask.subject_id ?? asking.subject_id;
      const key = questionKey(subjectId, asking.ask.metric);
      addTo(questions, key, pair, () => ({ key, subjectId, ask: asking.ask, checks: [] }));
    } else {
      const ask = ownerAsk(pair.governing);
      addTo(openChecks, ask, pair, () => ({ ask, checks: [] }));
    }
  }
  return { group, questions: [...questions.values()], openChecks: [...openChecks.values()] };
}

/** Open questions for the owner, one entry per element so each plan pin number appears once. */
export function elementQuestions(groups: readonly ElementGroup[]): ElementQuestions[] {
  return groups.map(questionsFor).filter((entry) => entry.questions.length + entry.openChecks.length > 0);
}

export function questionCount(elements: readonly ElementQuestions[]) {
  return elements.reduce((sum, entry) => sum + entry.questions.length + entry.openChecks.length, 0);
}

export type ParsedAnswer = { kind: "blank" } | { kind: "value"; value: Exclude<AnswerValue, null> } | { kind: "invalid"; error: string };

const BLANK: ParsedAnswer = { kind: "blank" };
const BOOLEAN_WORDS: Record<string, boolean> = { yes: true, no: false };

function parseNumber(raw: string, whole: boolean): ParsedAnswer {
  const value = Number(raw.replace(/,/g, ""));
  if (!Number.isFinite(value)) return { kind: "invalid", error: "Enter a number, like 32 or 32.5." };
  if (whole && !Number.isInteger(value)) return { kind: "invalid", error: "Enter a whole number, like 2." };
  return { kind: "value", value };
}

const PARSERS: Record<AskValueType, (raw: string, ask: Pick<Ask, "options">) => ParsedAnswer> = {
  boolean: (raw) => (raw in BOOLEAN_WORDS ? { kind: "value", value: BOOLEAN_WORDS[raw]! } : { kind: "invalid", error: "Choose yes or no." }),
  number: (raw) => parseNumber(raw, false),
  integer: (raw) => parseNumber(raw, true),
  enum: (raw, ask) => (ask.options.includes(raw) ? { kind: "value", value: raw } : { kind: "invalid", error: "Choose one of the options." }),
};

/** Reads what the owner typed or picked. Choices arrive as "yes", "no" or the option itself. */
export function parseAnswer(ask: Pick<Ask, "value_type" | "options">, raw: string): ParsedAnswer {
  const trimmed = raw.trim();
  if (!trimmed) return BLANK;
  return PARSERS[ask.value_type](trimmed, ask);
}

/** The answers to send for the drafts the owner filled in, or the reasons some of them can't be sent. */
export function answersToSave(questions: readonly OwnerQuestion[], drafts: Readonly<Record<string, string>>) {
  const answers: AnswerInput[] = [];
  const errors: Record<string, string> = {};
  for (const question of questions) {
    const parsed = parseAnswer(question.ask, drafts[question.key] ?? "");
    if (parsed.kind === "invalid") errors[question.key] = parsed.error;
    if (parsed.kind === "value") answers.push({ subject_id: question.subjectId, metric: question.ask.metric, value: parsed.value });
  }
  return { answers, errors };
}

const UNIT_WORDS: Record<string, string> = { in: "inches", ft: "feet", lbf: "pounds of force", s: "seconds", deg: "degrees", "%": "percent" };

export function unitWord(unit: string) {
  return UNIT_WORDS[unit] ?? unit;
}

/** The choices an ask offers, as [value sent, words shown]. */
export function choicesFor(ask: Pick<Ask, "value_type" | "options">): [string, string][] {
  if (ask.value_type === "boolean") return [["yes", "Yes"], ["no", "No"]];
  return ask.options.map((option) => [option, sentenceCase(option)]);
}
