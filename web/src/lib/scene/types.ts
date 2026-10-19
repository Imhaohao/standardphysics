import type * as Generated from "./scene.gen";

/**
 * The v2 Scene as sp-server serializes it. `scene.gen.ts` is generated from core/schema/scene.schema.json, which
 * describes input and so marks defaulted fields optional; serde always writes them, so here every field is present.
 * Units are metres and radians, Y is up, and the floor of each storey is y = 0. Plan coordinates (Vec2) are world X and Z.
 */
type Filled<T> = { [K in keyof T]-?: Exclude<T[K], undefined> };

export type Vec2 = Generated.Vec2;
export type Vec3 = Generated.Vec3;
export type Polygon2 = Generated.Polygon2;
export type RoomKind = NonNullable<Generated.Room["kind"]>;
export type OpeningKind = Generated.OpeningKind;
export type ObjectSource = NonNullable<Generated.Object["source"]>;
export type ObservationSource = Generated.ObservationSource;
export type DoorSwing = Filled<Generated.DoorSwing>;
export type Wall = Filled<Generated.Wall>;
export type Opening = Filled<Omit<Generated.Opening, "swing">> & { swing: DoorSwing | null };
export type SceneObject = Filled<Generated.Object>;
export type RoomConnection = Filled<Generated.RoomConnection>;
export type Observation = Filled<Generated.Observation>;

export type Room = Filled<Omit<Generated.Room, "walls" | "openings" | "objects">> & {
  walls: Wall[];
  openings: Opening[];
  objects: SceneObject[];
};

export type Scene = Filled<Omit<Generated.Scene, "rooms" | "connections" | "observations">> & {
  rooms: Room[];
  connections: RoomConnection[];
  observations: Observation[];
};
