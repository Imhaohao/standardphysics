import { drawnNodes, FloorPlan, footprint, paddedFrame, planBounds, toDrawing, type PlanBounds } from "@/components/FloorPlan";
import { formatFeetAndInches } from "@/lib/units";
import type { SceneGraph, SceneNode } from "@/types/contracts";
import type { ClauseRow } from "./redesign";

export type MarkState = "fails" | "cleared";

export interface PlanMark {
  row: ClauseRow;
  state: MarkState;
}

/** One window onto both layouts, with room left for the overall dimensions. */
export function sharedFrame(scenes: SceneGraph[]): PlanBounds {
  const box = planBounds(scenes.flatMap(drawnNodes));
  const framed = paddedFrame(box, 0.05);
  const dimensionRoom = Math.max(box.width, box.height) * 0.1;
  return { ...framed, minX: framed.minX - dimensionRoom, width: framed.width + dimensionRoom, height: framed.height + dimensionRoom };
}

function markPoint(row: ClauseRow): [number, number] | null {
  const point = (row.before ?? row.after)?.locus?.point;
  return point ? toDrawing(point.x, point.y) : null;
}

const MARK_CLASS: Record<MarkState, { shape: string; label: string }> = {
  fails: { shape: "fill-problem stroke-problem", label: "fill-sheet" },
  cleared: { shape: "fill-sheet stroke-pass", label: "fill-pass" },
};

function Mark({ mark, radius }: { mark: PlanMark; radius: number }) {
  const at = markPoint(mark.row);
  if (!at) return null;
  const classes = MARK_CLASS[mark.state];
  return (
    <g transform={`translate(${at[0]} ${at[1]})`}>
      <circle r={radius} className={classes.shape} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <text className={`${classes.label} font-semibold`} fontSize={radius * 1.15} textAnchor="middle" dominantBaseline="central">
        {mark.row.number}
      </text>
    </g>
  );
}

/** Where a moved piece stood before, drawn as the dashed outline an architect uses for "existing, to be moved". */
function Ghost({ node }: { node: SceneNode }) {
  const { x, y, width, depth, degrees } = footprint(node);
  const [dx, dy] = toDrawing(x, y);
  return (
    <rect
      x={-width / 2} y={-depth / 2} width={width} height={depth}
      className="fill-none stroke-accent" strokeWidth={1.5} strokeDasharray="4 3" vectorEffect="non-scaling-stroke"
      transform={`translate(${dx} ${dy}) rotate(${-degrees})`}
    />
  );
}

function MoveArrow({ from, to, headSize }: { from: SceneNode; to: SceneNode; headSize: number }) {
  const [x1, y1] = toDrawing(from.transform.m[3], from.transform.m[7]);
  const [x2, y2] = toDrawing(to.transform.m[3], to.transform.m[7]);
  const length = Math.hypot(x2 - x1, y2 - y1);
  if (length < headSize) return null;
  const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
  return (
    <g className="stroke-accent" strokeWidth={1.5}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} vectorEffect="non-scaling-stroke" />
      <path
        d={`M 0 0 L ${-headSize} ${-headSize / 2} L ${-headSize} ${headSize / 2} Z`}
        className="fill-accent" vectorEffect="non-scaling-stroke"
        transform={`translate(${x2} ${y2}) rotate(${angle})`}
      />
    </g>
  );
}

function OverallDimensions({ scene, unit }: { scene: SceneGraph; unit: number }) {
  const box = planBounds(drawnNodes(scene));
  const [left, top] = toDrawing(box.minX, box.minY + box.height);
  const [right, bottom] = toDrawing(box.minX + box.width, box.minY);
  const [above, beside] = [top - unit * 2.2, left - unit * 2.2];
  const tick = unit * 0.5;
  return (
    <g className="fill-ink-muted stroke-ink-muted" strokeWidth={1}>
      <line x1={left} y1={above} x2={right} y2={above} vectorEffect="non-scaling-stroke" />
      <line x1={left} y1={above - tick} x2={left} y2={above + tick} vectorEffect="non-scaling-stroke" />
      <line x1={right} y1={above - tick} x2={right} y2={above + tick} vectorEffect="non-scaling-stroke" />
      <text x={(left + right) / 2} y={above - unit * 0.7} fontSize={unit * 1.2} textAnchor="middle" stroke="none">
        {formatFeetAndInches(box.width)}
      </text>
      <line x1={beside} y1={top} x2={beside} y2={bottom} vectorEffect="non-scaling-stroke" />
      <line x1={beside - tick} y1={top} x2={beside + tick} y2={top} vectorEffect="non-scaling-stroke" />
      <line x1={beside - tick} y1={bottom} x2={beside + tick} y2={bottom} vectorEffect="non-scaling-stroke" />
      <text
        x={beside - unit * 0.7} y={(top + bottom) / 2} fontSize={unit * 1.2} textAnchor="middle" stroke="none"
        transform={`rotate(-90 ${beside - unit * 0.7} ${(top + bottom) / 2})`}
      >
        {formatFeetAndInches(box.height)}
      </text>
    </g>
  );
}

interface PlanPanelProps {
  scene: SceneGraph;
  frame: PlanBounds;
  marks: PlanMark[];
  label: string;
  /** The pieces a plan moves, as they stood before it moved them. */
  movedFrom?: SceneNode[];
}

/** A plan of one layout, with numbered marks where a check fails or was cleared. */
export function PlanPanel({ scene, frame, marks, label, movedFrom = [] }: PlanPanelProps) {
  const unit = Math.max(frame.width, frame.height) / 60;
  const shown = new Map(scene.nodes.map((node) => [node.id, node]));
  return (
    <FloorPlan scene={scene} frame={frame} label={label} emphasized={new Set(movedFrom.map((node) => node.id))} className="block w-full">
      <OverallDimensions scene={scene} unit={unit} />
      {movedFrom.map((node) => (
        <g key={node.id}>
          <Ghost node={node} />
          {shown.get(node.id) && <MoveArrow from={node} to={shown.get(node.id)!} headSize={unit * 0.9} />}
        </g>
      ))}
      {marks.map((mark) => (
        <Mark key={mark.row.number} mark={mark} radius={unit * 1.3} />
      ))}
    </FloorPlan>
  );
}
