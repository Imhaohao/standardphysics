import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import sampleScene from "@/fixtures/sample-scene.json";
import { indexSubjects } from "./describe";
import { objectBoxes, wallBoxes } from "./model";
import { dominantWallAngle, openingSpan, planBounds, squaredToSheet, wallSegments } from "./plan";
import { objectCategory, sceneFromCapturedRoom, snakeCase, yawOf, type CapturedRoom } from "./roomplan";
import type { Opening, Scene, Wall } from "./types";
import { formatFeetAndInches } from "./units";

const raw = JSON.parse(readFileSync(new URL("../../../fixtures/roomplan/apple_livingroom.room.json", import.meta.url), "utf8")) as CapturedRoom;

function rounded(value: unknown) {
  return JSON.parse(JSON.stringify(value, (_, v: unknown) => (typeof v === "number" ? Math.round(v * 1e4) / 1e4 : v))) as unknown;
}

const wall: Wall = { id: "w", start: { x: 0, y: 0 }, end: { x: 4, y: 0 }, height: 2.5, thickness: 0.1 };
const door: Opening = { id: "d", kind: "door", wall_id: "w", center: { x: 2, y: 1, z: 0 }, width: 1, height: 2, swing: null, hardware: null };

describe("RoomPlan converter", () => {
  const scene = sceneFromCapturedRoom(raw);
  const room = scene.rooms[0]!;

  it("matches the bundled fixture", () => {
    expect(rounded(scene)).toEqual(sampleScene);
  });

  it("keeps every surface and object", () => {
    expect(room.walls).toHaveLength(raw.walls!.length);
    expect(room.objects).toHaveLength(raw.objects!.length);
    expect(room.openings).toHaveLength((raw.doors?.length ?? 0) + (raw.windows?.length ?? 0) + (raw.openings?.length ?? 0));
  });

  it("puts the floor at zero and every opening on a wall", () => {
    for (const object of room.objects) expect(object.center.y - object.size.y / 2).toBeGreaterThan(-0.05);
    const wallIds = new Set(room.walls.map((w) => w.id));
    for (const opening of room.openings) expect(wallIds.has(opening.wall_id)).toBe(true);
  });

  it("names categories the way core does", () => {
    expect(snakeCase("diningRoom")).toBe("dining_room");
    expect(objectCategory("table", { TableType: "coffee" })).toBe("coffee_table");
    expect(objectCategory("stove", {})).toBe("range");
    expect(objectCategory("television", {})).toBe("television");
  });

  it("reads yaw from the local x axis", () => {
    const turn = Math.PI / 2;
    expect(yawOf([Math.cos(turn), 0, -Math.sin(turn), 0, 0, 1, 0, 0, Math.sin(turn), 0, Math.cos(turn)])).toBeCloseTo(turn);
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
    expect(new Set(names).size).toBe(names.length);
  });

  it("formats feet and inches", () => {
    expect(formatFeetAndInches(4.58)).toBe(`15'-0"`);
    expect(formatFeetAndInches(0.9144)).toBe(`3'-0"`);
  });
});
