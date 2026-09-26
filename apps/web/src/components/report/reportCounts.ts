import type { Finding, ReviewedRule } from "@/types/contracts";

/**
 * The title the server gives a photo question once the owner has sent the
 * photo and before a person on the team has checked it. The finding stays a
 * question, so this title is the only mark that nothing more is needed from
 * the owner (services/api/standardphysics_api/answered_findings.py).
 */
export const PHOTO_BEING_CHECKED_TITLE = "We have your photo";

export type OpenQuestions = { toSend: Finding[]; beingChecked: Finding[] };

export function isBeingChecked(finding: Finding): boolean {
  return finding.outcome === "question" && finding.title === PHOTO_BEING_CHECKED_TITLE;
}

/** Questions the owner still has to answer, apart from photos they already sent. */
export function splitQuestions(questions: Finding[]): OpenQuestions {
  return {
    toSend: questions.filter((finding) => !isBeingChecked(finding)),
    beingChecked: questions.filter(isBeingChecked),
  };
}

/** What each photo being checked shows, by the name its rule gives it ("The front door handle"). */
export function beingCheckedNames(beingChecked: Finding[], rules: ReviewedRule[]): string[] {
  const ruleNames = new Map(rules.map((rule) => [rule.check.id, rule.check.title]));
  return beingChecked.map((finding) => ruleNames.get(finding.check_id) ?? finding.citation.section);
}
