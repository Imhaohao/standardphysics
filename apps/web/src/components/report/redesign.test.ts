import { describe, expect, it } from "vitest";
import type { Finding, LayoutPlan, Mat4, SceneGraph, SceneNode } from "@/types/contracts";
import { choosePlan, compareClauses, moveSchedule, needsConstruction } from "./redesign";

const citation = { authority: "ADA_2010", edition: "2010 ADA Standards", section: "403.5.1", url: null } as const;

function finding(id: string, outcome: Finding["outcome"], nodeIds: string[] = [], point = { x: 0, y: 0, z: 0 }): Finding {
  const locus = {
    annotation: { kind: "none" }, bbox_min: point, bbox_max: point, point, node_ids: nodeIds, render_url: null,
    camera: { position: point, target: point, fov_degrees: 50 },
  } as unknown as Finding["locus"];
  return {
    id, check_id: "route_clear_width", outcome, title: id, detail: "", fix: null, asks: null,
    measured_inches: 31, required_inches: 36, citation, locus,
  };
}

function plan(id: string, createdAt: string, findings: Finding[], moves: LayoutPlan["moves"] = []): LayoutPlan {
  return { id, scan_id: "s", base_revision: 0, name: id, created_at: createdAt, findings, moves };
}

function node(id: string, x: number, y: number, movable = true): SceneNode {
  const transform = { m: [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, 0.45, 0, 0, 0, 1] } as Mat4;
  return {
    id, kind: "object", label: id, labeled_by: "test", movable, parent_id: null, quality: "measured",
    raw_category: id, dimensions: { x: 1, y: 0.5, z: 0.9 }, transform,
  };
}

const move = (nodeId: string, dx: number) => ({ node_id: nodeId, delta_translation: { x: dx, y: 0, z: 0 }, delta_rotation_z_degrees: 0 });

describe("choosePlan", () => {
  const worse = plan("worse", "2026-09-28T01:00:00Z", [finding("a", "problem")]);
  const clearsOld = plan("clears-old", "2026-09-28T02:00:00Z", [finding("a", "passes")]);
  const clearsNew = plan("clears-new", "2026-09-28T03:00:00Z", [finding("a", "passes")]);

  it("shows the plan leaving the fewest problems, the newest of a tie", () => {
    expect(choosePlan([worse, clearsOld, clearsNew], undefined)?.id).toBe("clears-new");
  });

  it("shows the plan the reader picked even when another clears more", () => {
    expect(choosePlan([worse, clearsNew], "worse")?.id).toBe("worse");
  });

  it("has nothing to show without plans", () => {
    expect(choosePlan([], "anything")).toBeNull();
  });
});

describe("compareClauses", () => {
  it("marks each spot that failed as cleared or still failing, and adds spots the plan breaks", () => {
    const before = [finding("path", "problem"), finding("turn", "problem"), finding("aisle", "passes")];
    const after = [finding("path", "passes"), finding("turn", "problem"), finding("aisle", "problem")];

    const rows = compareClauses(before, after);

    expect(rows.map((row) => [row.number, row.before?.id ?? row.after?.id, row.change])).toEqual([
      [1, "path", "cleared"],
      [2, "turn", "still_fails"],
      [3, "aisle", "new_problem"],
    ]);
  });

  it("lists the scan's problems on their own when there is no plan", () => {
    const rows = compareClauses([finding("path", "problem"), finding("aisle", "passes")], null);
    expect(rows).toEqual([expect.objectContaining({ number: 1, after: null, change: "still_fails" })]);
  });
});

describe("moveSchedule", () => {
  it("ties a move to the spot whose check measured that piece", () => {
    const scene: SceneGraph = { scan_id: "s", revision: 0, base_hash: null, nodes: [node("case", 3, 3), node("stool", 9, 9)] };
    const rows = compareClauses([finding("path", "problem", ["case"])], [finding("path", "passes", ["case"])]);
    const layout = plan("p", "2026-09-28T01:00:00Z", [], [move("case", 0.1016), move("stool", 1)]);

    const schedule = moveSchedule(scene, layout, rows);

    expect(schedule.map((entry) => [entry.node.id, Math.round(entry.inchesAcross), entry.serves.map((row) => row.number)]))
      .toEqual([["case", 4, [1]], ["stool", 39, []]]);
  });

  it("ties a move to a spot when the piece stood inside the clearance the rule asks for", () => {
    const inside = node("chair", 0.6, 0);
    const scene: SceneGraph = { scan_id: "s", revision: 0, base_hash: null, nodes: [inside] };
    const rows = compareClauses([finding("turn", "problem")], [finding("turn", "passes")]);

    const schedule = moveSchedule(scene, plan("p", "t", [], [move("chair", 1)]), rows);

    expect(schedule[0].serves.map((row) => row.number)).toEqual([1]);
  });

  it("calls a plan construction only when it moves something built in", () => {
    const scene: SceneGraph = { scan_id: "s", revision: 0, base_hash: null, nodes: [node("case", 0, 0), node("counter", 2, 2, false)] };
    const furnitureOnly = moveSchedule(scene, plan("p", "t", [], [move("case", 0.1)]), []);
    const withCounter = moveSchedule(scene, plan("p", "t", [], [move("case", 0.1), move("counter", 0.5)]), []);
    expect([needsConstruction(furnitureOnly), needsConstruction(withCounter)]).toEqual([false, true]);
  });
});
