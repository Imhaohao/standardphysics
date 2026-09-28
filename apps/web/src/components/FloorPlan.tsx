import type { ReactNode } from "react";
import type { SceneGraph, SceneNode } from "@/types/contracts";

type DrawnKind = "floor" | "wall" | "object";

const DRAWN_KINDS: readonly DrawnKind[] = ["floor", "object", "wall"];

const STYLE: Record<DrawnKind, { fill: string; stroke: string; strokeWidth: number }> = {
  floor: { fill: "none", stroke: "var(--color-ink-faint)", strokeWidth: 0.75 },
  object: { fill: "hatch", stroke: "var(--color-ink)", strokeWidth: 1.25 },
  wall: { fill: "var(--color-ink)", stroke: "var(--color-ink)", strokeWidth: 1 },
};

export interface PlanBounds {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

export function footprint(node: SceneNode) {
  const [m0, , , x, m4, , , y] = node.transform.m;
  const degrees = (Math.atan2(m4, m0) * 180) / Math.PI;
  return { x, y, width: node.dimensions.x, depth: node.dimensions.y, degrees };
}

function isDrawn(node: SceneNode): node is SceneNode & { kind: DrawnKind } {
  return (DRAWN_KINDS as readonly string[]).includes(node.kind);
}

export function drawnNodes(scene: SceneGraph) {
  return scene.nodes.filter(isDrawn);
}

export function planBounds(nodes: SceneNode[]): PlanBounds {
  const reach = nodes.map((node) => {
    const { x, y, width, depth, degrees } = footprint(node);
    const [cos, sin] = [Math.abs(Math.cos((degrees * Math.PI) / 180)), Math.abs(Math.sin((degrees * Math.PI) / 180))];
    const [halfX, halfY] = [(cos * width + sin * depth) / 2, (sin * width + cos * depth) / 2];
    return [x - halfX, y - halfY, x + halfX, y + halfY];
  });
  const [minX, minY] = [Math.min(...reach.map((b) => b[0])), Math.min(...reach.map((b) => b[1]))];
  const [maxX, maxY] = [Math.max(...reach.map((b) => b[2])), Math.max(...reach.map((b) => b[3]))];
  return { minX, minY, width: maxX - minX, height: maxY - minY };
}

/** The drawing's own extent padded on every side, for a plan drawn alone. */
export function paddedFrame(box: PlanBounds, share = 0.04): PlanBounds {
  const pad = Math.max(box.width, box.height) * share;
  return { minX: box.minX - pad, minY: box.minY - pad, width: box.width + 2 * pad, height: box.height + 2 * pad };
}

/** A scene point in the drawing's coordinates, where y grows downward. */
export function toDrawing(x: number, y: number): [number, number] {
  return [x, -y];
}

interface FloorPlanProps {
  scene: SceneGraph;
  className?: string;
  /** The window onto the plan, so two layouts of one room line up at one scale. */
  frame?: PlanBounds;
  /** Pieces drawn in the accent, such as the ones a plan moves. */
  emphasized?: ReadonlySet<string>;
  /** What the drawing shows, for a reader who cannot see it. Left unset, the drawing is decoration. */
  label?: string;
  /** Marks drawn over the plan, in drawing coordinates from `toDrawing`. */
  children?: ReactNode;
}

function nodeFill(node: SceneNode & { kind: DrawnKind }, emphasized: boolean, hatchId: string): string {
  if (emphasized) return "var(--color-accent)";
  const fill = STYLE[node.kind].fill;
  return fill === "hatch" ? `url(#${hatchId})` : fill;
}

/** The shop from above, drawn from measured footprints, with the scan's own axes. */
export function FloorPlan({ scene, className = "", frame, emphasized, label, children }: FloorPlanProps) {
  const drawn = drawnNodes(scene);
  if (drawn.length === 0) return null;
  const box = planBounds(drawn);
  const view = frame ?? paddedFrame(box);
  const layered = [...drawn].sort((a, b) => DRAWN_KINDS.indexOf(a.kind) - DRAWN_KINDS.indexOf(b.kind));
  const hatchSpacing = Math.max(box.width, box.height) / 90;
  const hatchId = `floor-plan-hatch-${scene.scan_id}-${scene.revision}`;

  return (
    <svg
      viewBox={`${view.minX} ${-(view.minY + view.height)} ${view.width} ${view.height}`}
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-floor-plan
    >
      <defs>
        <pattern id={hatchId} width={hatchSpacing} height={hatchSpacing} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width={hatchSpacing} height={hatchSpacing} fill="var(--color-paper)" />
          <line x1="0" y1="0" x2="0" y2={hatchSpacing} stroke="var(--color-ink)" strokeWidth={hatchSpacing * 0.18} />
        </pattern>
      </defs>
      {layered.map((node) => {
        const { x, y, width, depth, degrees } = footprint(node);
        const isEmphasized = emphasized?.has(node.id) ?? false;
        return (
          <rect
            key={node.id}
            x={-width / 2}
            y={-depth / 2}
            width={width}
            height={depth}
            fill={nodeFill(node, isEmphasized, hatchId)}
            stroke={isEmphasized ? "var(--color-accent)" : STYLE[node.kind].stroke}
            strokeWidth={STYLE[node.kind].strokeWidth}
            vectorEffect="non-scaling-stroke"
            transform={`translate(${x.toFixed(4)} ${(-y).toFixed(4)}) rotate(${(-degrees).toFixed(3)})`}
          />
        );
      })}
      {children}
    </svg>
  );
}
