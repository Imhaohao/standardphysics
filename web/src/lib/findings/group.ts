import type { Subject } from "@/lib/scene/describe";
import type { Finding, FindingStatus, StatusCounts } from "./types";

/** Worse first: a failure outranks an open question, which outranks a pass. */
export const STATUS_RANK: Record<FindingStatus, number> = { fail: 0, needs_info: 1, pass: 2, not_applicable: 3 };

/** One requirement checked under both codes: the ADA finding and the California finding for the same section. */
export interface FindingPair {
  key: string;
  ada: Finding | null;
  cbc: Finding | null;
  /** The finding whose result decides what the owner has to do: the stricter outcome of the two. */
  governing: Finding;
}

export interface ElementGroup {
  subjectId: string;
  name: string;
  subject: Subject | null;
  status: FindingStatus;
  pairs: FindingPair[];
}

export function sectionKey(section: string) {
  return section.replace(/^§\s*/, "").replace(/^11B-/i, "").trim();
}

function worse(a: Finding, b: Finding) {
  return STATUS_RANK[b.status] < STATUS_RANK[a.status] ? b : a;
}

export function governingFinding(ada: Finding | null, cbc: Finding | null): Finding {
  if (ada && cbc) return worse(cbc, ada);
  const either = ada ?? cbc;
  if (!either) throw new Error("A finding pair needs at least one finding.");
  return either;
}

/** sp-core links an ADA rule and its California twin through `counterpart`; both share the smaller of the two ids. */
function pairKey(finding: Finding) {
  const { rule_id: ruleId, counterpart } = finding;
  if (counterpart) return counterpart < ruleId ? counterpart : ruleId;
  return sectionKey(finding.section) || ruleId;
}

/**
 * A group can hold several findings with the same pair key (a floor and the route through the same room, or
 * several California rules under one section with no ADA twin). Each finding gets its own slot so none is
 * overwritten: a later pass must never hide an earlier failure.
 */
function pairFindings(findings: readonly Finding[]): FindingPair[] {
  const byKey = new Map<string, { ada: Finding | null; cbc: Finding | null }[]>();
  for (const finding of findings) {
    const key = pairKey(finding);
    const side = finding.jurisdiction === "CBC11B" ? "cbc" : "ada";
    const slots = byKey.get(key) ?? [];
    const slot = slots.find((candidate) => candidate[side] === null) ?? { ada: null, cbc: null };
    if (!slots.includes(slot)) slots.push(slot);
    slot[side] = finding;
    byKey.set(key, slots);
  }
  return [...byKey.entries()]
    .flatMap(([key, slots]) => slots.map((slot, index) => ({ key: index === 0 ? key : `${key}#${index + 1}`, ...slot })))
    .map(({ key, ada, cbc }) => ({ key, ada, cbc, governing: governingFinding(ada, cbc) }))
    .sort((a, b) => STATUS_RANK[a.governing.status] - STATUS_RANK[b.governing.status] || a.key.localeCompare(b.key, undefined, { numeric: true }));
}

function groupBySubject(findings: readonly Finding[], subjects: ReadonlyMap<string, Subject>) {
  const bySubject = new Map<string, Finding[]>();
  for (const finding of findings) {
    const key = subjects.get(finding.subject_id)?.groupId ?? finding.subject_id;
    bySubject.set(key, [...(bySubject.get(key) ?? []), finding]);
  }
  return bySubject;
}

/** Findings grouped by the element they are about, worst element first, each ADA/CBC pair side by side. */
export function groupByElement(findings: readonly Finding[], subjects: ReadonlyMap<string, Subject>): ElementGroup[] {
  const relevant = findings.filter((finding) => finding.status !== "not_applicable");
  return [...groupBySubject(relevant, subjects)]
    .map(([subjectId, subjectFindings]) => {
      const pairs = pairFindings(subjectFindings);
      const subject = subjects.get(subjectId) ?? null;
      return { subjectId, subject, name: subject?.name ?? "Whole shop", status: pairs[0]!.governing.status, pairs };
    })
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || a.name.localeCompare(b.name, undefined, { numeric: true }));
}

/** One line for a list: the worst requirement's title, and how many more share its status. */
export function groupHeadline(group: ElementGroup) {
  const [first, ...rest] = group.pairs;
  const more = rest.filter((pair) => pair.governing.status === first!.governing.status).length;
  return more > 0 ? `${first!.governing.title} and ${more} more` : first!.governing.title;
}

export function countStatuses(findings: readonly Finding[]): StatusCounts {
  const counts: StatusCounts = { pass: 0, fail: 0, needs_info: 0, not_applicable: 0 };
  for (const finding of findings) counts[finding.status] += 1;
  return counts;
}
