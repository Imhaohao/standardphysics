import { describe, expect, it } from "vitest";
import sampleScene from "@/fixtures/sample-scene.json";
import { indexSubjects } from "./describe";
import { objectBoxes, wallBoxes } from "./model";
import { dominantWallAngle, openingSpan, planBounds, squaredToSheet, wallSegments } from "./plan";
import type { Opening, Scene, Wall } from "./types";
import { formatFeetAndInches } from "./units";

const wall: Wall = { id: "w", start: { x: 0, y: 0 }, end: { x: 4, y: 0 }, height: 2.5, thickness: 0.1 };
const door: Opening = { id: "d", kind: "door", wall_id: "w", center: { x: 2, y: 1, z: 0 }, width: 1, height: 2, swing: null, hardware: null };

describe("sample scene", () => {
  const room = (sampleScene as unknown as Scene).rooms[0]!;

  it("is sp-core's conversion with every field written out", () => {
    expect(room.walls.length).toBeGreaterThan(0);
    for (const wall of room.walls) expect(wall.thickness).toBeGreaterThan(0);
    const wallIds = new Set(room.walls.map((wall) => wall.id));
    for (const opening of room.openings) expect(wallIds.has(opening.wall_id)).toBe(true);
    for (const object of room.objects) expect(object.center.y - object.size.y / 2).toBeGreaterThan(-0.05);
  });
});

describe("plan geometry", () => {
  it("cuts a door gap out of its wall", () => {
    expect(openingSpan(door, wall)).toEqual([1.5, 2.5]);
    const pieces = wallSegments(wall, [door]);
    expect(pieces.map(([a, b]) => [a.x, b.x])).toEqual([[0, 1.5], [2.5, 4]]);
  });

  it("finds bounds and squares the sample to the sheet", () => {
    const scene = sampleScene as unknown as Scene;
    expect(planBounds(scene)).not.toBeNull();
    const squared = squaredToSheet(scene).scene;
    const angle = Math.abs(dominantWallAngle(squared)) % (Math.PI / 2);
    expect(Math.min(angle, Math.PI / 2 - angle)).toBeLessThan(0.01);
  });

  it("builds wall pieces with a lintel over the door", () => {
    const scene: Scene = { version: 2, rooms: [{ id: "r", name: "Shop", kind: "shop", storey: 0, floor: { points: [] }, ceiling_height: 2.5, walls: [wall], openings: [door], objects: [] }], connections: [], observations: [] };
    const boxes = wallBoxes(scene);
    expect(boxes).toHaveLength(3);
    expect(boxes.find((box) => box.id === "d:lintel")?.size[1]).toBeCloseTo(0.5);
    expect(objectBoxes(scene)).toEqual([]);
  });

  it("names subjects so owners recognise them", () => {
    const subjects = [...indexSubjects(sampleScene as unknown as Scene).values()];
    const names = subjects.map((subject) => subject.name);
    expect(names).toContain("Wall 1");
    expect(names).toContain("Floor");
    expect(names).toContain("Route to the table 1");
    expect(new Set(names).size).toBe(names.length);
  });

  it("formats feet and inches", () => {
    expect(formatFeetAndInches(4.58)).toBe(`15'-0"`);
    expect(formatFeetAndInches(0.9144)).toBe(`3'-0"`);
  });
});
