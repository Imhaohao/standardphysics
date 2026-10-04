import { Box3, OrthographicCamera, Sphere, Vector3 } from "three";
import type { SceneGraph, SceneNode } from "@/types/contracts";
import { toViewerMatrix } from "./scene-matrix";
import type { ShownSurface } from "./viewer-source";

/** A transform entry may drift this far, a tenth of a millimetre or as little turn, before a piece counts as moved. */
const MOVE_TOLERANCE = 1e-4;

/** Whether a piece stands anywhere other than where it was scanned: slid, turned, or set down on something else. */
export function movedFromScan(scanned: SceneNode, placed: SceneNode): boolean {
  return scanned.transform.m.some((value, index) => Math.abs(value - placed.transform.m[index]) > MOVE_TOLERANCE);
}

/**
 * Whether a piece throws a shadow onto the photographed room.
 *
 * The photographs already hold the shadow every piece threw where it was
 * scanned, so a piece left in place throws nothing more: a second shadow would
 * darken that floor twice. A piece that moved or turned throws one from where it
 * stands now, and a piece the scan never saw has no shadow in the photographs
 * at all.
 */
export function castsShadow(scanned: SceneNode | undefined, placed: SceneNode): boolean {
  return scanned === undefined || movedFromScan(scanned, placed);
}

/** The ids of the furniture in `placed` that throws a shadow, judged against the pieces as they were scanned. */
export function shadowCasters(scanned: SceneNode[], placed: SceneGraph): Set<string> {
  const before = new Map(scanned.map((node) => [node.id, node]));
  const casting = placed.nodes.filter((node) => node.kind === "object" && castsShadow(before.get(node.id), node));
  return new Set(casting.map((node) => node.id));
}

/**
 * Whether the light casts at all for the surface on screen.
 *
 * The boxes are a model lit like one, so every box throws a shadow. A
 * photographed room already holds its own shadows, so on the painted scan the
 * light casts only while furniture can be moved across it. The splats and the
 * combined rooms have nothing cut out of them that could move.
 */
export function lightCasts(surface: ShownSurface, arranging: boolean): boolean {
  return surface === "boxes" || (surface === "scan" && arranging);
}

/** Degrees the light leans away from straight overhead. Ceiling lights put a shop's shadows almost under what throws them. */
const LIGHT_TILT_DEGREES = 15;
const LIGHT_TILT = (LIGHT_TILT_DEGREES * Math.PI) / 180;

/**
 * The direction toward the light, in viewer space.
 *
 * It stands high and leans toward the room's west, so a piece's shadow lands
 * about a quarter of the piece's height to its east. From the overview's
 * south-east corner that is below and to the right of the piece, on the side
 * the camera sees, where a shadow falling away from the camera would hide
 * behind the piece that throws it.
 */
export const TOWARD_LIGHT = new Vector3(-Math.sin(LIGHT_TILT), Math.cos(LIGHT_TILT), 0);

/** Metres kept around the room's measured edge, so a piece set against a wall still shades the floor past it. */
const ROOM_MARGIN = 0.5;
/** How far beyond the room's reach the light stands, so no surface is ever behind it. */
const STAND_OFF = 1;
/** The longest side of the shadow map, in texels. */
const MAX_MAP_TEXELS = 2048;
/** Texels per metre at most, about 4 mm each, which is already finer than a thinned scan's triangles. */
const MAX_TEXELS_PER_METRE = 256;
/** How far behind a caster's surface, in metres, a receiver must sit before it counts as shaded, so a lit face never shades itself. */
const BIAS_METRES = 0.004;

/** What a room with nothing measured in it is taken to be: a ten-metre square to stand a light over. */
const EMPTY_ROOM = new Box3(new Vector3(-5, 0, -5), new Vector3(5, 3, 5));

const UNIT_CORNERS = [-0.5, 0.5].flatMap((x) => [-0.5, 0.5].flatMap((y) => [-0.5, 0.5].map((z) => new Vector3(x, y, z))));

function boxCorners(box: Box3): Vector3[] {
  const size = box.getSize(new Vector3());
  const centre = box.getCenter(new Vector3());
  return UNIT_CORNERS.map((corner) => corner.clone().multiply(size).add(centre));
}

/** Every measured box of the scene, walls and furniture alike, in viewer space. */
export function roomBounds(scene: SceneGraph): Box3 {
  const bounds = new Box3();
  for (const node of scene.nodes) {
    if (!node.transform.m.every(Number.isFinite)) continue;
    const toWorld = toViewerMatrix(node.transform);
    const size = new Vector3(node.dimensions.x, node.dimensions.z, node.dimensions.y);
    for (const corner of UNIT_CORNERS) bounds.expandByPoint(corner.clone().multiply(size).applyMatrix4(toWorld));
  }
  return bounds.isEmpty() ? EMPTY_ROOM.clone() : bounds;
}

/** Where the light stands and how its shadow camera is framed, in the units a DirectionalLight takes. */
export type ShadowRig = {
  position: Vector3;
  target: Vector3;
  left: number;
  right: number;
  top: number;
  bottom: number;
  near: number;
  far: number;
  /** Texels wide and high, in the room's proportions, so every texel covers the same square of floor. */
  mapSize: [number, number];
  /** The filter radius in texels that gives the soft edge its width. */
  radius: number;
  /** BIAS_METRES in the shadow camera's depth, which runs from 0 at `near` to 1 at `far`. */
  bias: number;
};

/** The room's box seen from the light: x and y across the shadow map, z along the light (negative, ahead of it). */
function fromTheLight(box: Box3, position: Vector3, target: Vector3): Box3 {
  const eye = new OrthographicCamera();
  eye.position.copy(position);
  eye.lookAt(target);
  eye.updateMatrixWorld();
  return new Box3().setFromPoints(boxCorners(box).map((corner) => corner.applyMatrix4(eye.matrixWorldInverse)));
}

/**
 * The light stood over the room and its shadow camera framed tight around it.
 *
 * A shadow map stretched over a fixed seventy-metre square spent most of its
 * texels on empty air, so a chair's legs came out as smudges. Framing only the
 * room, seen along the light, puts every texel on the floor. `penumbra` is the
 * width in metres of a shadow's soft edge; the filter radius is worked out from
 * it, so a small room and a large one get the same softness in metres.
 */
export function shadowRig(room: Box3, penumbra: number): ShadowRig {
  const box = room.clone().expandByScalar(ROOM_MARGIN);
  const target = box.getCenter(new Vector3());
  const position = target.clone().addScaledVector(TOWARD_LIGHT, box.getBoundingSphere(new Sphere()).radius + STAND_OFF);
  const seen = fromTheLight(box, position, target);
  const [width, height, depth] = [seen.max.x - seen.min.x, seen.max.y - seen.min.y, seen.max.z - seen.min.z];
  const texelsPerMetre = Math.min(MAX_MAP_TEXELS / Math.max(width, height), MAX_TEXELS_PER_METRE);
  return {
    position,
    target,
    left: seen.min.x,
    right: seen.max.x,
    top: seen.max.y,
    bottom: seen.min.y,
    near: -seen.max.z,
    far: -seen.min.z,
    mapSize: [Math.ceil(width * texelsPerMetre), Math.ceil(height * texelsPerMetre)],
    radius: (penumbra / 2) * texelsPerMetre,
    bias: -BIAS_METRES / depth,
  };
}
