import type { Opening, Room, Scene, SceneObject, Vec2, Wall } from "./types";

const CATEGORY_NAMES: Record<string, string> = {
  shelving: "Shelving",
  storage: "Storage unit",
  coffee_table: "Coffee table",
  dining_table: "Dining table",
  sofa: "Sofa",
  cabinet: "Cabinet",
  television: "Television",
  oven: "Oven",
  fireplace: "Fireplace",
};

const OPENING_NAMES: Record<Opening["kind"], string> = { door: "Door", opening: "Doorway", window: "Window" };

export function sentenceCase(snake: string) {
  const words = snake.trim().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function categoryName(category: string) {
  return CATEGORY_NAMES[category] ?? sentenceCase(category);
}

export type SubjectKind = "object" | "opening" | "wall" | "room";

export interface Subject {
  id: string;
  kind: SubjectKind;
  name: string;
  room: Room;
  /** Where to pin the subject on the plan, in plan metres (world x, world z), and how high it sits. */
  anchor: Vec2;
  height: number;
  /** The element this subject's findings are listed under: itself, or for a route or floor check, its element or room. */
  groupId: string;
}

function numbered<T>(items: T[], name: (item: T) => string): Map<T, string> {
  const totals = new Map<string, number>();
  for (const item of items) totals.set(name(item), (totals.get(name(item)) ?? 0) + 1);
  const seen = new Map<string, number>();
  return new Map(
    items.map((item) => {
      const base = name(item);
      const index = (seen.get(base) ?? 0) + 1;
      seen.set(base, index);
      return [item, (totals.get(base) ?? 0) > 1 ? `${base} ${index}` : base];
    }),
  );
}

function objectSubject(room: Room, object: SceneObject, name: string): Subject {
  return { id: object.id, kind: "object", name, room, anchor: { x: object.center.x, y: object.center.z }, height: object.top_height, groupId: object.id };
}

function openingSubject(room: Room, opening: Opening, name: string): Subject {
  return { id: opening.id, kind: "opening", name, room, anchor: { x: opening.center.x, y: opening.center.z }, height: opening.height, groupId: opening.id };
}

function wallSubject(room: Room, wall: Wall, name: string): Subject {
  const anchor = { x: (wall.start.x + wall.end.x) / 2, y: (wall.start.y + wall.end.y) / 2 };
  return { id: wall.id, kind: "wall", name, room, anchor, height: wall.height, groupId: wall.id };
}

function roomSubject(room: Room): Subject {
  const points = room.floor.points;
  const anchor = { x: points.reduce((s, p) => s + p.x, 0) / (points.length || 1), y: points.reduce((s, p) => s + p.y, 0) / (points.length || 1) };
  return { id: room.id, kind: "room", name: room.name, room, anchor, height: 0, groupId: room.id };
}

/** sp-core also checks things that are not elements: the floor surface, and the route to an element or through a room. */
function derivedSubjects(room: Subject, elements: Subject[]): Subject[] {
  const lowerFirst = (name: string) => name.charAt(0).toLowerCase() + name.slice(1);
  return [
    { ...room, id: `floor:${room.id}`, name: "Floor" },
    { ...room, id: `route:${room.id}`, name: "Route through the room" },
    ...elements.map((element) => ({ ...element, id: `route:${element.id}`, name: `Route to the ${lowerFirst(element.name)}` })),
  ];
}

function roomSubjects(room: Room): Subject[] {
  const objectNames = numbered(room.objects, (object) => categoryName(object.category));
  const openingNames = numbered(room.openings, (opening) => OPENING_NAMES[opening.kind]);
  const wallNames = numbered(room.walls, () => "Wall");
  const whole = roomSubject(room);
  const elements = [
    ...room.objects.map((object) => objectSubject(room, object, objectNames.get(object)!)),
    ...room.openings.map((opening) => openingSubject(room, opening, openingNames.get(opening)!)),
  ];
  return [whole, ...elements, ...room.walls.map((wall) => wallSubject(room, wall, wallNames.get(wall)!)), ...derivedSubjects(whole, elements)];
}

/** Every element a finding can be about, by id, with a name a shop owner would recognise. */
export function indexSubjects(scene: Scene): Map<string, Subject> {
  return new Map(scene.rooms.flatMap(roomSubjects).map((subject) => [subject.id, subject]));
}
