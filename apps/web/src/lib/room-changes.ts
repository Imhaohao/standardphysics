/** The change detector's scene.json and cloud.bin, read for the /changes viewer. */

export type ChangeType = "moved" | "added" | "removed";
export type Video = "before" | "after";
export type Vec3 = [number, number, number];

export type ChangeBox = { center: Vec3; size: Vec3; yaw_deg: number; corners: Vec3[] };
export type ChangePlace = { box: ChangeBox; where: string };
/** How many frames of the other video looked at a spot and saw mostly empty space there. */
export type SpotEvidence = { empty_in: number; of: number; video: Video };
export type ChangePicture = { file: string; video: Video; time_s: number; aspect: number; box: [number, number][] };

export type RoomChange = {
  id: string;
  type: ChangeType;
  name: string;
  detail: string;
  sentence: string;
  size: Vec3;
  size_text: string;
  confidence: number;
  evidence: { points: number; old_spot: SpotEvidence | null; new_spot: SpotEvidence | null };
  before: ChangePlace | null;
  after: ChangePlace | null;
  pictures: Partial<Record<Video, ChangePicture>>;
  distance_m?: number;
  turn_deg?: number | null;
};

export type UncheckedThing = {
  id: string;
  video: Video;
  /** "one video": the other video never looked there; "unsupported": it hangs in the air. */
  reason?: "one video" | "unsupported";
  name: string;
  detail: string;
  sentence: string;
  box: ChangeBox;
  size_text: string;
  picture: ChangePicture | null;
};

export type ChangeCamera = {
  video: Video;
  frame: number;
  time_s: number;
  position: Vec3;
  rotation: number[];
  fov_y_deg: number;
  aspect: number;
};

export type ChangeScene = {
  format: number;
  inputs: Record<Video, string>;
  /** Small H.264 copies beside scene.json, or null where the detector had no ffmpeg to make one. */
  videos: Record<Video, string | null>;
  summary: string;
  changes: RoomChange[];
  coverage: { before_checked_by_other: number; after_checked_by_other: number };
  /** Things only one video saw, in places the other never looked: listed, never counted as changes. */
  unchecked?: UncheckedThing[];
  /** Furniture that stayed put, which the sentences describe changes against. */
  furniture: { name: string; box: ChangeBox }[];
  room: { low: Vec3; high: Vec3 };
  cloud: { file: string; count: number };
  cameras: ChangeCamera[];
};

export type Cloud = {
  count: number;
  positions: Float32Array;
  colors: Uint8Array;
  video: Uint8Array;
  seen: Uint8Array;
  change: Uint8Array;
};

/** Never seen by the other video, so nothing there could be checked. */
export const UNSEEN = 2;

/** cloud.bin is five arrays end to end: positions, colours, then one byte each for video, seen and change. */
export function parseCloud(buffer: ArrayBuffer, count: number): Cloud {
  const expected = count * (12 + 3 + 3);
  if (buffer.byteLength !== expected) {
    throw new Error(`cloud.bin holds ${buffer.byteLength} bytes; ${count} points need ${expected}`);
  }
  const positions = new Float32Array(buffer, 0, count * 3);
  let offset = count * 12;
  const take = (length: number) => {
    const part = new Uint8Array(buffer, offset, length);
    offset += length;
    return part;
  };
  return { count, positions, colors: take(count * 3), video: take(count), seen: take(count), change: take(count) };
}

/** The twelve edges of a box whose corners are numbered x + 2y + 4z, as the detector writes them. */
export const BOX_EDGES: [number, number][] = [
  [0, 1], [2, 3], [4, 5], [6, 7],
  [0, 2], [1, 3], [4, 6], [5, 7],
  [0, 4], [1, 5], [2, 6], [3, 7],
];

export function edgePositions(corners: Vec3[]): Float32Array {
  return new Float32Array(BOX_EDGES.flatMap(([a, b]) => [...corners[a], ...corners[b]]));
}

/** Where a change sits now, or where it was if it is gone. */
export function placeOf(change: RoomChange): ChangePlace {
  const place = change.after ?? change.before;
  if (!place) throw new Error(`change ${change.id} has no place`);
  return place;
}

export function changeCentre(change: RoomChange): Vec3 {
  const places = [change.before, change.after].filter((place): place is ChangePlace => place !== null);
  const sum = places.reduce<Vec3>((total, place) => [
    total[0] + place.box.center[0], total[1] + place.box.center[1], total[2] + place.box.center[2],
  ], [0, 0, 0]);
  return [sum[0] / places.length, sum[1] / places.length, sum[2] / places.length];
}

/** Radius of a sphere holding every box of the change, for framing the camera on it. */
export function changeReach(change: RoomChange): number {
  const centre = changeCentre(change);
  const corners = [change.before, change.after].flatMap((place) => place?.box.corners ?? []);
  return Math.max(0.4, ...corners.map((corner) => Math.hypot(...corner.map((v, i) => v - centre[i]))));
}

/** The detector's own rounding (language.length), so a number reads the same in the sentence and the panel. */
export function formatLength(metres: number): string {
  const centimetres = Math.floor((metres * 100) / 5 + 0.5) * 5;
  if (centimetres < 100) return `${centimetres} cm`;
  return `${(Math.floor(metres * 10 + 0.5) / 10).toFixed(1)} m`;
}

/** The rendered rooms checked in under public/changes, each testing something different. */
export const EXAMPLE_ROOMS = [
  { room: "living-room", label: "Living room" },
  { room: "studio", label: "Studio" },
  { room: "office", label: "Office" },
  { room: "bedroom", label: "Bedroom" },
  { room: "kitchen", label: "Kitchen" },
  { room: "workshop", label: "Workshop" },
  { room: "lounge", label: "Lounge" },
  { room: "study", label: "Study" },
  { room: "living-room-same", label: "No changes" },
  { room: "living-room-blind-spot", label: "Blind spot" },
] as const;

/** The furniture some sentence places a change against; the rest stays unlabelled so a misread piece can't mislead. */
export function citedFurniture(scene: Pick<ChangeScene, "changes" | "furniture">): NonNullable<ChangeScene["furniture"]> {
  const sentences = scene.changes.map((change) => change.sentence);
  return (scene.furniture ?? []).filter((piece) => sentences.some((sentence) => sentence.includes(`the ${piece.name}`)));
}

/** Positive yaw turns counterclockwise when the room is seen from above. */
export function formatTurn(degrees: number | null | undefined): string | null {
  if (degrees === null || degrees === undefined || Math.abs(degrees) < 20) return null;
  const side = degrees > 0 ? "counterclockwise" : "clockwise";
  return `${Math.round(Math.abs(degrees) / 15) * 15}° ${side}, seen from above`;
}

export function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

export const CHANGE_LABEL: Record<ChangeType, string> = {
  moved: "Moved",
  added: "New",
  removed: "Gone",
};

/** The CSS token each change type is drawn in; the stylesheet owns the colours themselves. */
export const CHANGE_TOKEN: Record<ChangeType, string> = {
  moved: "--color-moved",
  added: "--color-added",
  removed: "--color-removed",
};

/** How high the phone was held, as the room is measured: the median camera height above the floor. */
export function phoneHeight(cameras: ChangeCamera[]): number {
  const heights = cameras.map((camera) => camera.position[2]).sort((a, b) => a - b);
  if (heights.length === 0) return 0;
  const middle = Math.floor(heights.length / 2);
  return heights.length % 2 ? heights[middle] : (heights[middle - 1] + heights[middle]) / 2;
}

/** A camera path through one video's frames, in the order they were filmed. */
export function cameraPath(cameras: ChangeCamera[], video: Video): Vec3[] {
  return cameras.filter((camera) => camera.video === video).sort((a, b) => a.time_s - b.time_s)
    .map((camera) => camera.position);
}

/** A raised arc from where a moved object was to where it is, for the arrow drawn between them. */
export function moveArc(from: Vec3, to: Vec3, steps = 32): Vec3[] {
  const span = Math.hypot(to[0] - from[0], to[1] - from[1]);
  const lift = Math.min(0.6, 0.25 * span) + Math.max(from[2], to[2]);
  return Array.from({ length: steps + 1 }, (_, index) => {
    const t = index / steps;
    const height = (1 - t) * (1 - t) * from[2] + 2 * (1 - t) * t * lift + t * t * to[2];
    return [from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t, height] as Vec3;
  });
}
