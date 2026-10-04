import { describe, expect, it } from "vitest";
import type { SceneGraph } from "@/types/contracts";
import { MAX_TRAVEL_METERS } from "@/types/geometry-rules";
import { centreOf, type Point, sizedFootprint, touching } from "./footprints";
import { type Arranging, nudge, pickUp, pull, turn } from "./held-piece";
import { breaches, doorKeepClear, layoutState, ruleBase } from "./layout-rules";
import { type PieceDescription, roomFrom } from "./layout-test-scene";
import { applyMoves, type MoveSet } from "./moves";
import { drawingFor, slide, slideSpace } from "./slide";

const FLOOR: PieceDescription = { id: "floor", kind: "floor", at: [0, 0, 0], size: [6, 4, 0.01] };

/** A 6 by 4 metre room whose walls' inner faces stand at x = ±2.95 and y = ±1.95. */
const WALLS: PieceDescription[] = [
  FLOOR,
  { id: "north", kind: "wall", label: "North wall", at: [0, 2, 1.25], size: [6.2, 0.1, 2.5] },
  { id: "south", kind: "wall", label: "South wall", at: [0, -2, 1.25], size: [6.2, 0.1, 2.5] },
  { id: "east", kind: "wall", label: "East wall", at: [3, 0, 1.25], size: [0.1, 4.2, 2.5] },
  { id: "west", kind: "wall", label: "West wall", at: [-3, 0, 1.25], size: [0.1, 4.2, 2.5] },
];

const chair = (at: number[], extra: Partial<PieceDescription> = {}): PieceDescription =>
  ({ id: "chair", kind: "object", label: "Chair", at: [at[0], at[1], 0.45], size: [0.5, 0.5, 0.9], movable: true, ...extra });

function arranging(pieces: PieceDescription[], moves: MoveSet = {}): Arranging {
  const base = roomFrom(pieces);
  return { rules: ruleBase(base), base, moves };
}

function slideOf(pieces: PieceDescription[], nodeId: string, target: Point, moves: MoveSet = {}) {
  const { rules, base } = arranging(pieces, moves);
  const space = slideSpace(drawingFor(rules, base, moves, nodeId));
  return { space, ...slide(space, space.start, target) };
}

function legalAfter(state: Arranging, moves: MoveSet, nodeId: string) {
  return breaches(layoutState(state.rules, state.base, moves), [nodeId]);
}

function nodeIn(scene: SceneGraph, id: string) {
  return scene.nodes.find((node) => node.id === id)!;
}

describe("sliding a piece along what it runs into", () => {
  it("stops flush against a wall and slides along it toward the pointer", () => {
    const { at, blockedBy } = slideOf([...WALLS, chair([0, 0])], "chair", { x: 1, y: 3 });
    expect(at.x).toBeCloseTo(1, 9);
    expect(at.y).toBeCloseTo(1.7, 8);
    expect(blockedBy.map((stop) => stop.nodeId)).toEqual(["north"]);
  });

  it("settles into a corner and stays there however hard it is pushed", () => {
    const { space, at, blockedBy } = slideOf([...WALLS, chair([0, 0])], "chair", { x: 5, y: 5 });
    expect([at.x, at.y].map((value) => +value.toFixed(6))).toEqual([2.7, 1.7]);
    expect(blockedBy.map((stop) => stop.nodeId).sort()).toEqual(["east", "north"]);
    expect(slide(space, at, { x: 9, y: 4 }).at).toEqual(at);
  });

  it("slides along another piece and turns toward the pointer again past its corner", () => {
    const table: PieceDescription = { id: "table", kind: "object", label: "Table", at: [0, 0, 0.375], size: [1, 1, 0.75], movable: true };
    const along = slideOf([...WALLS, table, chair([-1.5, 0])], "chair", { x: 1.5, y: 0.2 });
    expect([along.at.x, along.at.y].map((value) => +value.toFixed(6))).toEqual([-0.75, 0.2]);
    expect(along.blockedBy.map((stop) => stop.nodeId)).toEqual(["table"]);
    const around = slideOf([...WALLS, table, chair([-1.5, 0])], "chair", { x: 1.5, y: 1.2 });
    expect(around.at).toEqual({ x: 1.5, y: 1.2 });
    expect(around.blockedBy).toEqual([]);
  });

  it("lands in the same spot every time for the same pointer path, and a still pointer leaves it still", () => {
    const pieces = [...WALLS, chair([0, 0])];
    const path = [{ x: 1, y: 1 }, { x: 2.5, y: 3 }, { x: 4, y: 0.5 }, { x: 3.2, y: -3 }];
    const walk = () => {
      const { rules, base } = arranging(pieces);
      const space = slideSpace(drawingFor(rules, base, {}, "chair"));
      return path.reduce((at, target) => slide(space, at, target).at, space.start);
    };
    const first = walk();
    expect(walk()).toEqual(first);
    const { rules, base } = arranging(pieces);
    const space = slideSpace(drawingFor(rules, base, {}, "chair"));
    const settled = slide(space, first, path[path.length - 1]).at;
    expect(slide(space, settled, path[path.length - 1]).at).toEqual(settled);
  });
});

describe("a door's keep-clear square", () => {
  const door: PieceDescription = { id: "door", kind: "door", label: "Side door", at: [0, 1, 1], size: [0.9, 0.05, 2], turn: 30 };
  const open: PieceDescription[] = [{ ...FLOOR, size: [8, 8, 0.01] }, door];

  it("is laid out in the door's own turned frame", () => {
    const zone = doorKeepClear(roomFrom([door]).nodes[0]);
    const corners = zone.map((corner) => [+corner.x.toFixed(4), +corner.y.toFixed(4)]);
    expect(corners).toEqual([[0.0603, -0.0044], [0.8397, 0.4456], [-0.0603, 2.0044], [-0.8397, 1.5544]]);
  });

  it("stops a piece at its turned edge rather than the square the world's axes would draw", () => {
    const { at, blockedBy } = slideOf([...open, chair([-2, 1])], "chair", { x: 0, y: 1.6 });
    const room = roomFrom([...open, chair([at.x, at.y])]);
    const placed = nodeIn(room, "chair");
    const zone = doorKeepClear(nodeIn(room, "door"));
    expect(touching(sizedFootprint(placed, 0.5 + 2e-6, 0.5 + 2e-6), zone)).toBe(true);
    expect(touching(sizedFootprint(placed, 0.5 - 2e-6, 0.5 - 2e-6), zone)).toBe(false);
    expect(blockedBy.map((stop) => stop.reason)).toEqual(["blocked_a_door"]);
    expect([at.x, at.y].map((value) => +value.toFixed(4))).toEqual([-0.9453, 1.0542]);
  });

  it("lets a piece slide around it, never standing in it on the way", () => {
    const state = arranging([...open, chair([-2, 1])]);
    let held = pickUp(state, "chair");
    let moves: MoveSet = {};
    for (let step = 0; step < 80; step++) {
      const pulled = pull({ ...state, moves }, held, 4 / 80, 0);
      ({ held, moves } = pulled);
      expect(legalAfter(state, moves, "chair")).toEqual([]);
    }
    expect(held.at.x).toBeCloseTo(2, 9);
    expect(held.at.y).toBeCloseTo(1, 9);
  });
});

describe("overlaps the server tolerates", () => {
  it("lets a piece pass through one the scan already had it overlapping", () => {
    const twice: PieceDescription[] = [
      ...WALLS,
      { id: "table", kind: "object", label: "Table", at: [0, 0, 0.375], size: [1, 1, 0.75], movable: true },
      { id: "copy", kind: "object", label: "Table seen twice", at: [0.3, 0, 0.375], size: [1, 1, 0.75] },
    ];
    expect(slideOf(twice, "table", { x: 1.4, y: 0 }).at).toEqual({ x: 1.4, y: 0 });
  });

  it("keeps a piece the scan left 3 mm into a wall sliding along it, never deeper", () => {
    const into = [...WALLS, chair([0, 1.703])];
    const along = slideOf(into, "chair", { x: 1, y: 1.703 });
    expect(along.at.x).toBeCloseTo(1, 9);
    expect(along.at.y).toBeCloseTo(1.703, 9);
    const deeper = slideOf(into, "chair", { x: 1, y: 2.5 });
    expect(deeper.at.y).toBeLessThanOrEqual(1.703 + 1e-9);
    expect(deeper.at.x).toBeCloseTo(1, 9);
  });

  it("puts a piece back on its scanned spot, where the server forgives an overlap the scan had there", () => {
    const moved: PieceDescription[] = [
      ...WALLS,
      { id: "table", kind: "object", label: "Table", at: [1.5, 0, 0.375], size: [1, 1, 0.75], movable: true, measured: [0, 0] },
      { id: "copy", kind: "object", label: "Table seen twice", at: [0.3, 0, 0.375], size: [1, 1, 0.75] },
    ];
    expect(slideOf(moved, "table", { x: 0.5, y: 0 }).at.x).toBeCloseTo(1.3, 8);
    expect(slideOf(moved, "table", { x: 0.004, y: -0.003 }).at).toEqual({ x: 0, y: 0 });
  });
});

describe("stacked pieces", () => {
  it("carries what rides on a table, and stops when the rider overhanging its edge reaches a wall", () => {
    const pieces: PieceDescription[] = [
      ...WALLS,
      { id: "table", kind: "object", label: "Table", at: [1.5, 0, 0.375], size: [1, 1, 0.75], movable: true },
      { id: "laptop", kind: "object", label: "Laptop", at: [1.9, 0, 0.77], size: [0.3, 0.2, 0.04], movable: true },
    ];
    const state = arranging(pieces);
    const { at, blockedBy } = slideOf(pieces, "table", { x: 4, y: 0 });
    expect(at.x).toBeCloseTo(2.95 - 0.55, 8);
    expect(blockedBy.map((stop) => stop.nodeId)).toEqual(["east"]);
    const carried = applyMoves(state.base, pull(state, pickUp(state, "table"), 4, 0).moves);
    expect(centreOf(nodeIn(carried, "laptop")).x).toBeCloseTo(2.8, 8);
  });

  it("lets a low stool pass under a shelf that a table runs into", () => {
    const shelf: PieceDescription = { id: "shelf", kind: "object", label: "Shelf", at: [0, 0, 0.8], size: [0.8, 0.4, 0.4] };
    const stool: PieceDescription = { id: "stool", kind: "object", label: "Stool", at: [-1.5, 0, 0.225], size: [0.4, 0.4, 0.45], movable: true };
    const table: PieceDescription = { id: "table", kind: "object", label: "Table", at: [-1.5, 0, 0.375], size: [0.6, 0.6, 0.75], movable: true };
    expect(slideOf([...WALLS, shelf, stool], "stool", { x: 1.5, y: 0 }).at).toEqual({ x: 1.5, y: 0 });
    expect(slideOf([...WALLS, shelf, table], "table", { x: 1.5, y: 0 }).at.x).toBeCloseTo(-0.7, 8);
  });

  it("holds two things standing on surfaces apart wherever their footprints meet, whatever their heights", () => {
    const pieces: PieceDescription[] = [
      ...WALLS,
      { id: "counter", kind: "object", label: "Counter", at: [1.5, 0, 0.5], size: [1, 1.2, 1] },
      { id: "register", kind: "object", label: "Register", at: [1.05, 0, 1.1], size: [0.4, 0.4, 0.2] },
      { id: "cart", kind: "object", label: "Cart", at: [-1, 0, 0.4], size: [0.6, 0.6, 0.8], movable: true },
      { id: "tray", kind: "object", label: "Tray", at: [-0.75, 0, 0.825], size: [0.5, 0.5, 0.05], movable: true },
    ];
    const { at, blockedBy } = slideOf(pieces, "cart", { x: 1, y: 0 });
    expect(at.x).toBeCloseTo(0.35, 8);
    expect(blockedBy.map((stop) => stop.nodeId)).toEqual(["register"]);
  });

  it("lifts a piece resting on another rather than sliding it, for the server to judge where it lands", () => {
    const pieces: PieceDescription[] = [
      ...WALLS,
      { id: "table", kind: "object", label: "Table", at: [0, 0, 0.375], size: [1, 1, 0.75], movable: true },
      { id: "laptop", kind: "object", label: "Laptop", at: [0, 0, 0.77], size: [0.3, 0.2, 0.04], movable: true },
    ];
    expect(slideOf(pieces, "laptop", { x: 5, y: 0 }).at).toEqual({ x: 5, y: 0 });
  });
});

describe("the floor's edge and the travel limit", () => {
  const openFloor = [FLOOR];

  it("stops a piece with its corners a centimetre past the floor's edge", () => {
    const { at, blockedBy } = slideOf([...openFloor, chair([0, 0])], "chair", { x: 10, y: 0 });
    expect(at.x).toBeCloseTo(3 + 0.01 - 0.25, 5);
    expect(at.x).toBeLessThan(3 + 0.01 - 0.25);
    expect(blockedBy.map((stop) => stop.reason)).toEqual(["left_the_floor"]);
  });

  it("lets a piece the scan left past the edge move along it, no further out", () => {
    const out = [...openFloor, chair([2.78, 0])];
    const { at } = slideOf(out, "chair", { x: 2.9, y: 1 });
    expect(at.y).toBeCloseTo(1, 9);
    expect(at.x).toBeCloseTo(2.79, 5);
    const state = arranging(out);
    const cornered = pull(state, pickUp(state, "chair"), 1, 3);
    expect(legalAfter(state, cornered.moves, "chair")).toEqual([]);
  });

  it("stops furniture 60 inches from where the scan found it and slides round that circle", () => {
    const shelf: PieceDescription = { id: "case", kind: "object", label: "Display case", at: [0, 0, 0.45], size: [2.4, 0.6, 0.9], movable: true };
    const pieces = [{ ...FLOOR, size: [10, 10, 0.01] }, shelf];
    const straight = slideOf(pieces, "case", { x: 3, y: 0 });
    expect(straight.at.x).toBeCloseTo(MAX_TRAVEL_METERS, 5);
    expect(straight.at.x).toBeLessThan(MAX_TRAVEL_METERS);
    expect(straight.blockedBy.map((stop) => stop.reason)).toEqual(["moved_too_far"]);
    const state = arranging(pieces);
    const round = pull(state, { ...pickUp(state, "case"), at: straight.at, wanted: straight.at }, 0, 1);
    expect(Math.hypot(round.held.at.x, round.held.at.y)).toBeCloseTo(MAX_TRAVEL_METERS, 5);
    expect(round.held.at.y).toBeGreaterThan(0.4);
  });

  it("slides along a wall toward a pointer beyond the travel limit, as far as the nearest legal spot", () => {
    const shelf: PieceDescription = { id: "case", kind: "object", label: "Display case", at: [1.6, 0, 0.45], size: [2.4, 0.6, 0.9], movable: true };
    const along = slideOf([...WALLS, shelf], "case", { x: 3.4, y: 0.9 });
    expect(along.at.x).toBeCloseTo(1.75, 8);
    expect(along.at.y).toBeCloseTo(0.9, 8);
    const capped = slideOf([...WALLS, shelf], "case", { x: 3.4, y: 3 });
    expect(capped.at.x).toBeCloseTo(1.75, 8);
    expect(Math.hypot(capped.at.x - 1.6, capped.at.y)).toBeCloseTo(MAX_TRAVEL_METERS, 5);
    expect(capped.blockedBy.map((stop) => stop.reason).sort()).toEqual(["collided", "moved_too_far"]);
  });
});

describe("keyboard nudges and turns", () => {
  const caseNearWall: PieceDescription = { id: "case", kind: "object", label: "Display case", at: [0, 1.4, 0.45], size: [2.4, 0.6, 0.9], movable: true };

  it("refuses a turn that would swing a piece into a wall, saying what it would hit", () => {
    const state = arranging([...WALLS, caseNearWall]);
    expect(turn(state, "case", 15)).toEqual({ moves: {}, refused: [{ node_id: "case", reason: "collided", detail: "Display case into North wall" }] });
  });

  it("turns a piece with room to turn", () => {
    const state = arranging([...WALLS, { ...caseNearWall, at: [0, 0, 0.45] }]);
    const { moves, refused } = turn(state, "case", 15);
    expect(refused).toEqual([]);
    expect(moves.case.delta_rotation_z_degrees).toBe(15);
  });

  it("slides a nudge as far as it goes, and explains one that cannot move at all", () => {
    const near = arranging([...WALLS, chair([0, 1.69])]);
    const partway = nudge(near, "chair", 0, 0.1524);
    expect(partway.refused).toEqual([]);
    expect(centreOf(nodeIn(applyMoves(near.base, partway.moves), "chair")).y).toBeCloseTo(1.7, 8);
    const flush = arranging([...WALLS, chair([0, 1.7])]);
    expect(nudge(flush, "chair", 0, 0.0254)).toEqual({ moves: {}, refused: [{ node_id: "chair", reason: "collided", detail: "Chair into North wall" }] });
  });
});
