import type { Point } from "@/lib/brush/geometry";
import type { DraftRecorder } from "@/lib/brush/recorder";
import type { FindingStatus } from "@/lib/findings/types";
import type { InkSurface } from "@/lib/ink/surface";
import { fitProjection, planBounds, roomCentroid, squaredToSheet, type PlanBounds, type PlanRotation } from "@/lib/scene/plan";
import type { Room, Scene, Vec2 } from "@/lib/scene/types";
import { formatFeetAndInches } from "@/lib/scene/units";
import { draftObject, draftOpening, draftWall, type ToFrame } from "./draft";
import { draftPins, type PlanPin } from "./inkPlan";

const MARGIN_PX = 72;
const STROKE_GAP_MS = 220;
const ANGLE_TOLERANCE = 0.02;
const MIN_LABELLED_WALL_M = 1;

interface Layout {
  angle: number;
  bounds: PlanBounds;
  toFrame: ToFrame;
  rotate: PlanRotation;
}

export interface Draftable {
  id: string;
  draw: (d: DraftRecorder, toFrame: ToFrame) => void;
}

function wallLabel(d: DraftRecorder, from: Point, to: Point, inside: Point, text: string) {
  const [mx, my] = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2];
  const length = Math.hypot(to[0] - from[0], to[1] - from[1]) || 1;
  let [nx, ny] = [-(to[1] - from[1]) / length, (to[0] - from[0]) / length];
  if ((inside[0] - mx) * nx + (inside[1] - my) * ny > 0) [nx, ny] = [-nx, -ny];
  let rotation = Math.atan2(to[1] - from[1], to[0] - from[0]);
  if (rotation > Math.PI / 2 || rotation < -Math.PI / 2) rotation += Math.PI;
  d.textClear(text, mx + nx * d.unit * 1.4, my + ny * d.unit * 1.4, d.fontSize(0.66), { align: "center", baseline: "middle", rotation });
}

/** Everything in a room the pen can draw, in the order a person drafting it would: walls, then doors, then furniture. */
export function roomDraftables(room: Room): Draftable[] {
  const inside = roomCentroid(room);
  const wallsById = new Map(room.walls.map((wall) => [wall.id, wall]));
  const walls = room.walls.map((wall) => ({
    id: wall.id,
    draw: (d: DraftRecorder, toFrame: ToFrame) => {
      draftWall(d, wall, room.openings, toFrame);
      const length = Math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y);
      if (length >= MIN_LABELLED_WALL_M) wallLabel(d, toFrame(wall.start), toFrame(wall.end), toFrame(inside), formatFeetAndInches(length));
    },
  }));
  const openings = room.openings.map((opening) => ({
    id: opening.id,
    draw: (d: DraftRecorder, toFrame: ToFrame) => {
      const wall = wallsById.get(opening.wall_id);
      if (wall) draftOpening(d, opening, wall, inside, toFrame);
    },
  }));
  const objects = room.objects.map((object) => ({ id: object.id, draw: (d: DraftRecorder, toFrame: ToFrame) => draftObject(d, object, toFrame) }));
  return [...walls, ...openings, ...objects];
}

/** Whatever in the scene has not been drawn yet. */
export function pendingDraftables(scene: Scene, drawn: ReadonlySet<string>): Draftable[] {
  return scene.rooms.flatMap(roomDraftables).filter((item) => !drawn.has(item.id));
}

function needsRelayout(previous: Layout | null, angle: number, bounds: PlanBounds) {
  if (!previous) return true;
  if (Math.abs(previous.angle - angle) > ANGLE_TOLERANCE) return true;
  const grew = bounds.minX < previous.bounds.minX - 0.05 || bounds.minY < previous.bounds.minY - 0.05;
  return grew || bounds.maxX > previous.bounds.maxX + 0.05 || bounds.maxY > previous.bounds.maxY + 0.05;
}

/**
 * Inks a scan onto the sheet as it arrives. New walls, doors and furniture are drafted with the brush in order;
 * if the scan grows past the drawing's edge, everything drawn so far is laid down again at the new scale at once.
 */
export class LivePlanInk {
  private layout: Layout | null = null;
  private readonly drawn = new Set<string>();
  private readonly pinned = new Set<string>();
  private redraws = 0;

  constructor(
    private readonly surface: InkSurface,
    private readonly colors: Record<FindingStatus, string>,
  ) {}

  update(scene: Scene, pins: readonly PlanPin[]) {
    const view = squaredToSheet(scene);
    const bounds = planBounds(view.scene);
    if (!bounds) return;
    const angle = Math.atan2(view.rotate({ x: 1, y: 0 }).y, view.rotate({ x: 1, y: 0 }).x);
    const relaid = needsRelayout(this.layout, angle, bounds);
    if (relaid) this.relayout(angle, bounds, view.rotate);
    this.draftNew(view.scene);
    if (relaid && this.redraws > 1) this.surface.flush();
    this.pinNew(pins);
    this.surface.wake();
  }

  private relayout(angle: number, bounds: PlanBounds, rotate: PlanRotation) {
    const padded = { minX: bounds.minX - 0.6, minY: bounds.minY - 0.6, maxX: bounds.maxX + 0.6, maxY: bounds.maxY + 0.6 };
    const frame = { left: MARGIN_PX, top: MARGIN_PX, width: this.surface.width - MARGIN_PX * 2, height: this.surface.height - MARGIN_PX * 2 };
    const projection = fitProjection(padded, frame);
    this.redraws += 1;
    this.layout = { angle, bounds: padded, toFrame: projection.toFrame, rotate };
    this.surface.clear();
    this.surface.fit();
    this.drawn.clear();
    this.pinned.clear();
  }

  private draftNew(scene: Scene) {
    const layout = this.layout!;
    pendingDraftables(scene, this.drawn).forEach((item, index) => {
      this.drawn.add(item.id);
      this.surface.brush.stampWith((d) => item.draw(d, layout.toFrame), index * STROKE_GAP_MS);
    });
  }

  private pinNew(pins: readonly PlanPin[]) {
    const layout = this.layout!;
    const fresh = pins.filter((pin) => !this.pinned.has(pin.id)).map((pin) => ({ ...pin, at: layout.rotate(pin.at) as Vec2 }));
    fresh.forEach((pin) => this.pinned.add(pin.id));
    if (fresh.length > 0) draftPins(this.surface.brush, fresh, layout.toFrame, [this.surface.width, this.surface.height], this.colors, 600);
  }
}
