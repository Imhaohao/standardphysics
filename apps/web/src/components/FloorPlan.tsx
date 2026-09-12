import type { SceneGraph, SceneNode } from "@/types/contracts";

const FILL: Record<SceneNode["kind"], string | null> = {
  floor: "var(--color-sheet)",
  wall: "var(--color-ink)",
  object: "var(--color-ink-faint)",
  door: null,
  window: null,
  opening: null,
};

function footprint(node: SceneNode) {
  const [m0, , , x, m4, , , y] = node.transform.m;
  const degrees = (Math.atan2(m4, m0) * 180) / Math.PI;
  return { x, y, width: node.dimensions.x, depth: node.dimensions.y, degrees };
}

function bounds(nodes: SceneNode[]) {
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

/** The shop from above, drawn from measured footprints. North is up. */
export function FloorPlan({ scene, className = "" }: { scene: SceneGraph; className?: string }) {
  const drawn = scene.nodes.filter((node) => FILL[node.kind] !== null);
  if (drawn.length === 0) return null;
  const box = bounds(drawn);
  const pad = Math.max(box.width, box.height) * 0.04;
  const order = ["floor", "object", "wall"];
  const layered = [...drawn].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));

  return (
    <svg
      viewBox={`${box.minX - pad} ${-(box.minY + box.height) - pad} ${box.width + 2 * pad} ${box.height + 2 * pad}`}
      className={className}
      aria-hidden
    >
      {layered.map((node) => {
        const { x, y, width, depth, degrees } = footprint(node);
        return (
          <rect
            key={node.id}
            x={-width / 2}
            y={-depth / 2}
            width={width}
            height={depth}
            fill={FILL[node.kind] ?? undefined}
            transform={`translate(${x} ${-y}) rotate(${-degrees})`}
          />
        );
      })}
    </svg>
  );
}
