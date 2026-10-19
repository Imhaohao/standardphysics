/* Generated from core/schema/scene.schema.json by pnpm scene:types. Do not edit. */

export type ObservationSource = "measured" | "photo" | "owner";
/**
 * Value of an observation: a number (with `unit`), a yes/no answer, or text.
 */
export type ObservationValue = boolean | number | string;
export type OpeningKind = "door" | "window" | "opening";

export interface Scene {
  connections?: RoomConnection[];
  observations?: Observation[];
  rooms?: Room[];
  version: number;
}
export interface RoomConnection {
  from_room: string;
  /**
   * The door or opening shared by both rooms, when known.
   */
  opening_id?: string | null;
  to_room: string;
}
/**
 * A fact that cannot be derived from boxes: sign text, Braille present, door opening force reported
 * by the owner, a tape-measured height.
 */
export interface Observation {
  confidence?: number;
  id: string;
  metric: string;
  source: ObservationSource;
  subject_id: string;
  unit?: string | null;
  value: ObservationValue;
}
export interface Room {
  ceiling_height: number;
  floor: Polygon2;
  id: string;
  kind?: "shop" | "restaurant" | "restroom" | "office" | "corridor" | "kitchen" | "storage" | "other";
  name: string;
  objects?: Object[];
  openings?: Opening[];
  /**
   * Storey index; rooms sharing a storey share one floor plane and one occupancy grid.
   */
  storey?: number;
  walls?: Wall[];
}
/**
 * Floor outline in plan (x = world X, y = world Z).
 */
export interface Polygon2 {
  points: Vec2[];
}
export interface Vec2 {
  x: number;
  y: number;
}
export interface Object {
  attributes?: {
    [k: string]: string;
  };
  /**
   * Category from `rules/metrics.json` `object_categories`.
   */
  category: string;
  center: Vec3;
  confidence?: number;
  id: string;
  size: Vec31;
  source?: "roomplan" | "detector" | "mesh" | "owner";
  /**
   * Height of the top surface above the floor (usually `center.y + size.y / 2`).
   */
  top_height: number;
  yaw: number;
}
/**
 * Centre of the bounding box; `y` is height above the floor.
 */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}
/**
 * Box size (width along local X, height, depth along local Z).
 */
export interface Vec31 {
  x: number;
  y: number;
  z: number;
}
export interface Opening {
  center: Vec32;
  hardware?: string | null;
  height: number;
  id: string;
  kind: OpeningKind;
  swing?: DoorSwing | null;
  wall_id: string;
  width: number;
}
/**
 * Centre of the opening; `y` is the height of its middle above the floor.
 */
export interface Vec32 {
  x: number;
  y: number;
  z: number;
}
export interface DoorSwing {
  /**
   * Hinge side as seen from the side the door swings into.
   */
  hinge: "left" | "right";
  /**
   * Leaf count (1 or 2).
   */
  leaves?: number;
  /**
   * True when the door swings into this room.
   */
  swings_in: boolean;
}
export interface Wall {
  end: Vec2;
  height: number;
  id: string;
  start: Vec2;
  thickness?: number;
}
