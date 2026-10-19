/**
 * The v2 Scene contract, mirrored by hand from core/sp-core/src/scene.rs (JSON Schema in
 * core/schema/scene.schema.json). Units are metres and radians, Y is up, and the floor of each storey is y = 0.
 * Plan coordinates (Vec2) are world X and world Z.
 */
export interface Vec2 {
  x: number;
  y: number;
}

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Polygon2 {
  points: Vec2[];
}

export type RoomKind = "shop" | "restaurant" | "restroom" | "office" | "corridor" | "kitchen" | "storage" | "other";
export type OpeningKind = "door" | "window" | "opening";
export type ObjectSource = "roomplan" | "detector" | "mesh" | "owner";
export type ObservationSource = "measured" | "photo" | "owner";

export interface Wall {
  id: string;
  start: Vec2;
  end: Vec2;
  height: number;
  thickness: number;
}

export interface DoorSwing {
  hinge: "left" | "right";
  swings_in: boolean;
  leaves: number;
}

export interface Opening {
  id: string;
  kind: OpeningKind;
  wall_id: string;
  center: Vec3;
  width: number;
  height: number;
  swing?: DoorSwing | null;
  hardware?: string | null;
}

export interface SceneObject {
  id: string;
  category: string;
  center: Vec3;
  /** Width, height, depth. */
  size: Vec3;
  yaw: number;
  top_height: number;
  confidence: number;
  source: ObjectSource;
  attributes: Record<string, string>;
}

export interface Room {
  id: string;
  name: string;
  kind: RoomKind;
  storey: number;
  floor: Polygon2;
  ceiling_height: number;
  walls: Wall[];
  openings: Opening[];
  objects: SceneObject[];
}

export interface RoomConnection {
  from_room: string;
  to_room: string;
  opening_id?: string | null;
}

export interface Observation {
  id: string;
  subject_id: string;
  metric: string;
  value: boolean | number | string;
  unit?: string | null;
  source: ObservationSource;
  confidence: number;
}

export interface Scene {
  version: number;
  rooms: Room[];
  connections: RoomConnection[];
  observations: Observation[];
}
