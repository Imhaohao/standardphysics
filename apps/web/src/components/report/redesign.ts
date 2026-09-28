import { METERS_PER_INCH } from "@/lib/moves";
import type { Finding, LayoutPlan, NodeMove, SceneGraph, SceneNode, Vec3 } from "@/types/contracts";

export type ClauseChange = "cleared" | "still_fails" | "new_problem";

/** One measured spot that fails before the plan, after it, or both. */
export interface ClauseRow {
  number: number;
  before: Finding | null;
  after: Finding | null;
  change: ClauseChange;
}

/** One piece the plan moves, and the rows it makes room for. */
export interface ScheduledMove {
  node: SceneNode;
  inchesAcross: number;
  inchesUp: number;
  turnDegrees: number;
  builtIn: boolean;
  serves: ClauseRow[];
}

const isProblem = (finding: Finding | null | undefined) => finding?.outcome === "problem";

function problemCount(plan: LayoutPlan): number {
  return plan.findings.filter(isProblem).length;
}

/** The plan to show: the one asked for, or else the one leaving the fewest problems, newest first on a tie. */
export function choosePlan(plans: LayoutPlan[], requestedId: string | undefined): LayoutPlan | null {
  const requested = plans.find((plan) => plan.id === requestedId);
  if (requested) return requested;
  const newestFirst = [...plans].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return newestFirst.reduce<LayoutPlan | null>((best, plan) => (!best || problemCount(plan) < problemCount(best) ? plan : best), null);
}

function changeOf(before: Finding | null, after: Finding | null, planned: boolean): ClauseChange {
  if (!isProblem(before)) return "new_problem";
  return !planned || isProblem(after) ? "still_fails" : "cleared";
}

/**
 * Every spot that fails on either side, matched by finding id, which stays the
 * same for the same check at the same place when only furniture moves.
 * Without a plan, the scan's own problems are listed on their own.
 */
export function compareClauses(before: Finding[], after: Finding[] | null): ClauseRow[] {
  const afterById = new Map((after ?? []).map((finding) => [finding.id, finding]));
  const beforeById = new Map(before.map((finding) => [finding.id, finding]));
  const failedBefore = before.filter(isProblem);
  const failedOnlyAfter = (after ?? []).filter((finding) => isProblem(finding) && !isProblem(beforeById.get(finding.id)));
  const rows = [...failedBefore, ...failedOnlyAfter].map((finding) => {
    const beforeFinding = beforeById.get(finding.id) ?? null;
    const afterFinding = after ? (afterById.get(finding.id) ?? null) : null;
    return { before: beforeFinding, after: afterFinding, change: changeOf(beforeFinding, afterFinding, after !== null) };
  });
  return rows.map((row, index) => ({ ...row, number: index + 1 }));
}

function distanceToFootprint(point: Vec3, node: SceneNode): number {
  const m = node.transform.m;
  const [dx, dy] = [point.x - m[3], point.y - m[7]];
  const localX = Math.abs(dx * m[0] + dy * m[4]) - node.dimensions.x / 2;
  const localY = Math.abs(-dx * m[4] + dy * m[0]) - node.dimensions.y / 2;
  return Math.hypot(Math.max(localX, 0), Math.max(localY, 0));
}

/**
 * A move serves a failing spot when the piece is one the check measured, or
 * when it stood inside the clearance the rule asks for around that spot.
 */
function serves(node: SceneNode, row: ClauseRow): boolean {
  const finding = row.before ?? row.after;
  const locus = finding?.locus;
  if (!finding || !locus) return false;
  if (locus.node_ids.includes(node.id)) return true;
  const reach = ((finding.required_inches ?? 0) * METERS_PER_INCH) / 2;
  return distanceToFootprint(locus.point, node) <= reach;
}

function scheduled(node: SceneNode, move: NodeMove, rows: ClauseRow[]): ScheduledMove {
  return {
    node,
    inchesAcross: move.delta_translation.x / METERS_PER_INCH,
    inchesUp: move.delta_translation.y / METERS_PER_INCH,
    turnDegrees: move.delta_rotation_z_degrees,
    builtIn: !node.movable,
    serves: rows.filter((row) => serves(node, row)),
  };
}

/** What the plan moves, in the order it was planned, each tied to the rows it makes room for. */
export function moveSchedule(scene: SceneGraph, plan: LayoutPlan, rows: ClauseRow[]): ScheduledMove[] {
  const nodes = new Map(scene.nodes.map((node) => [node.id, node]));
  return plan.moves.flatMap((move) => {
    const node = nodes.get(move.node_id);
    return node ? [scheduled(node, move, rows)] : [];
  });
}

export function needsConstruction(schedule: ScheduledMove[]): boolean {
  return schedule.some((move) => move.builtIn);
}
