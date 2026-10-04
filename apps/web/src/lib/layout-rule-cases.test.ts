import { describe, expect, it } from "vitest";
import fixture from "@fixtures/layout_rule_cases.json";
import { centreOf } from "./footprints";
import { breaches, layoutState, movingWith, ruleBase } from "./layout-rules";
import { type PieceDescription, roomFrom } from "./layout-test-scene";
import type { MoveSet } from "./moves";
import { drawingFor, slide, slideSpace } from "./slide";

/**
 * The browser's port of the hard constraints against the verdicts in the
 * shared fixture, which tests/test_layout_rule_cases.py holds the server's drag
 * check to as well.
 */

type Verdict = { name: string; room: string; node: string; to: number[]; turn?: number; blocked: string[][] };
type SlideCase = { name: string; room: string; node: string; to: number[]; lands: number[]; past: number[]; refused: string };
type Fixture = { rooms: Record<string, PieceDescription[]>; verdicts: Verdict[]; slides: SlideCase[] };

const cases = fixture as unknown as Fixture;

function verdict(room: string, nodeId: string, to: number[], turn = 0): string[][] {
  const base = roomFrom(cases.rooms[room]);
  const at = centreOf(base.nodes.find((node) => node.id === nodeId)!);
  const moves: MoveSet = {
    [nodeId]: { node_id: nodeId, delta_translation: { x: to[0] - at.x, y: to[1] - at.y, z: 0 }, delta_rotation_z_degrees: turn },
  };
  const found = breaches(layoutState(ruleBase(base), base, moves), movingWith(base, moves, nodeId));
  const pairs = new Set(found.map((blocked) => `${blocked.node_id}|${blocked.reason}`));
  return [...pairs].sort().map((pair) => pair.split("|"));
}

describe("the shared layout verdicts", () => {
  it.each(cases.verdicts.map((found) => [found.name, found] as const))("%s", (_, found) => {
    expect(verdict(found.room, found.node, found.to, found.turn)).toEqual([...found.blocked].sort());
  });
});

describe("the shared slides", () => {
  it.each(cases.slides.map((found) => [found.name, found] as const))("%s", (_, found) => {
    const base = roomFrom(cases.rooms[found.room]);
    const space = slideSpace(drawingFor(ruleBase(base), base, {}, found.node));
    const { at } = slide(space, space.start, { x: found.to[0], y: found.to[1] });
    expect(at.x).toBeCloseTo(found.lands[0], 6);
    expect(at.y).toBeCloseTo(found.lands[1], 6);
    expect(verdict(found.room, found.node, [at.x, at.y])).toEqual([]);
    expect(verdict(found.room, found.node, found.past)).toEqual([[found.node, found.refused]]);
  });
});
