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

function pairKey(finding: Finding) {
  return sectionKey(finding.section) || finding.rule_id;
}

function pairFindings(findings: readonly Finding[]): FindingPair[] {
  const byKey = new Map<string, { ada: Finding | null; cbc: Finding | null }>();
  for (const finding of findings) {
    const key = pairKey(finding);
    const slot = byKey.get(key) ?? { ada: null, cbc: null };
    if (finding.jurisdiction === "CBC11B") slot.cbc = finding;
    else slot.ada = finding;
    byKey.set(key, slot);
  }
  return [...byKey.entries()]
    .map(([key, { ada, cbc }]) => ({ key, ada, cbc, governing: governingFinding(ada, cbc) }))
    .sort((a, b) => STATUS_RANK[a.governing.status] - STATUS_RANK[b.governing.status] || a.key.localeCompare(b.key, undefined, { numeric: true }));
}

function groupBySubject(findings: readonly Finding[]) {
  const bySubject = new Map<string, Finding[]>();
  for (const finding of findings) bySubject.set(finding.subject_id, [...(bySubject.get(finding.subject_id) ?? []), finding]);
  return bySubject;
}

/** Findings grouped by the element they are about, worst element first, each ADA/CBC pair side by side. */
export function groupByElement(findings: readonly Finding[], subjects: ReadonlyMap<string, Subject>): ElementGroup[] {
  const relevant = findings.filter((finding) => finding.status !== "not_applicable");
  return [...groupBySubject(relevant)]
    .map(([subjectId, subjectFindings]) => {
      const pairs = pairFindings(subjectFindings);
      const subject = subjects.get(subjectId) ?? null;
      return { subjectId, subject, name: subject?.name ?? "Whole shop", status: pairs[0]!.governing.status, pairs };
    })
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || a.name.localeCompare(b.name, undefined, { numeric: true }));
}

export function countStatuses(findings: readonly Finding[]): StatusCounts {
  const counts: StatusCounts = { pass: 0, fail: 0, needs_info: 0, not_applicable: 0 };
  for (const finding of findings) counts[finding.status] += 1;
  return counts;
}

/** Open questions for the owner, one per requirement, so a question asked under both codes is asked once. */
export function ownerQuestions(groups: readonly ElementGroup[]) {
  return groups.flatMap((group) =>
    group.pairs.filter((pair) => pair.governing.status === "needs_info").map((pair) => ({ group, pair, question: pair.governing.message })),
  );
}
