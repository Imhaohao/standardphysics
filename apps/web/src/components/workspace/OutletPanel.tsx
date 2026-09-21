"use client";

import {
  CheckCircle,
  Lightning,
  MapPin,
  NavigationArrow,
  Question,
  ThumbsDown,
  ThumbsUp,
  WarningCircle,
} from "@phosphor-icons/react";
import { useMemo } from "react";
import { Button } from "@/components/ui/Button";
import {
  assessOutletAccessibility,
  wheelchairMotionGeometry,
  type MotionPoint,
  type OutletAccessibilityAssessment,
  type WheelchairProfile,
} from "@/lib/wheelchair-motion";
import type { SceneGraph, SceneNode } from "@/types/contracts";

const INCHES_PER_METER = 39.3701;

const REACH_DEFAULTS = { minReachHeight: 0.38, maxReachHeight: 1.22, maxReachDistance: 0.6 };

type OutletPanelProps = {
  scene: SceneGraph;
  selectedId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  wheelchairPos: MotionPoint | null;
  wheelchairProfile: WheelchairProfile;
  onProfileChange?: (profile: WheelchairProfile) => void;
  onPreviewApproach?: (point: MotionPoint) => void;
  onUpdateReviewStatus?: (nodeId: string, status: "confirmed_by_user" | "rejected_by_user") => void;
};

const NAMED_FITTINGS = new Set(["outlet", "candidate_outlet"]);

/** Kinds that carry an attachment for some reason other than being a fitting on a surface. */
const NOT_A_FITTING = new Set(["wall", "floor", "opening", "door", "window", "object"]);

export function isOutletNode(node: SceneNode): boolean {
  if (node.kind === "whiteboard" || node.raw_category === "whiteboard") return false;
  if (NAMED_FITTINGS.has(node.kind)) return true;
  if (!node.attachment) return false;
  const reviewed = node.raw_category === "outlet" || node.attachment.review_status !== undefined;
  return reviewed && !NOT_A_FITTING.has(node.kind);
}

/**
 * How every state in this panel looks, written once.
 *
 * Each carries an icon as well as a colour, so the state survives being read by
 * someone who cannot tell the colours apart.
 */
const APPROACH_LOOK = {
  clear: { Icon: CheckCircle, tint: "text-emerald-700 dark:text-emerald-400", label: "Clear" },
  blocked: { Icon: WarningCircle, tint: "text-rose-700 dark:text-rose-400", label: "Blocked" },
  needs_verification: { Icon: Question, tint: "text-amber-700 dark:text-amber-400", label: "Needs a look" },
} as const;

const REACH_LOOK = {
  within_reach: { Icon: CheckCircle, tint: "text-emerald-700 dark:text-emerald-400", label: "Within reach" },
  outside_reach: { Icon: WarningCircle, tint: "text-rose-700 dark:text-rose-400", label: "Out of reach" },
  needs_verification: { Icon: Question, tint: "text-amber-700 dark:text-amber-400", label: "Needs a look" },
} as const;

const REVIEW_LOOK = {
  rejected_by_user: { fill: "bg-rose-100 text-rose-900 dark:bg-rose-950/50 dark:text-rose-200", label: "Flagged wrong" },
  confirmed_by_user: { fill: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-200", label: "Confirmed" },
  candidate: { fill: "bg-amber-100 text-amber-900 dark:bg-amber-950/50 dark:text-amber-200", label: "Candidate" },
  detected: { fill: "bg-sky-100 text-sky-900 dark:bg-sky-950/50 dark:text-sky-200", label: "Observed" },
} as const;

type ReviewState = keyof typeof REVIEW_LOOK;

function reviewState(node: SceneNode): ReviewState {
  const said = node.attachment?.review_status;
  if (said === "rejected_by_user" || said === "confirmed_by_user") return said;
  if (said === "candidate" || node.kind === "candidate_outlet") return "candidate";
  return "detected";
}

function ReviewBadge({ node }: { node: SceneNode }) {
  const look = REVIEW_LOOK[reviewState(node)];
  return <span className={`shrink-0 px-2 py-0.5 text-xs font-medium ${look.fill}`}>{look.label}</span>;
}

/** A measurement beside what it measures, so neither has to be read as a sentence. */
function Measure({ name, value }: { name: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-ink-muted">{name}</span>
      <span className="font-mono text-xs tabular-nums text-ink">{value}</span>
    </div>
  );
}

function heightLabel(assessment: OutletAccessibilityAssessment | undefined): string {
  const height = assessment?.targetHeightAboveFloor;
  if (height === null || height === undefined) return "not measured";
  return `${(height * INCHES_PER_METER).toFixed(0)}″`;
}

function routeLabel(assessment: OutletAccessibilityAssessment | undefined): string {
  const distance = assessment?.approachDistance;
  if (distance === null || distance === undefined) return "no route";
  return `${distance.toFixed(1)} m`;
}

function OutletRow({
  node,
  assessment,
  selected,
  onSelect,
}: {
  node: SceneNode;
  assessment: OutletAccessibilityAssessment | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  const reach = REACH_LOOK[assessment?.reachStatus ?? "needs_verification"];
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex w-full flex-col gap-2 rounded-lg p-3 text-left transition-colors ${
        selected ? "bg-sheet ring-2 ring-sky-500" : "bg-sheet/70 ring-1 ring-rule/60 hover:bg-sheet"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          <MapPin size={16} className={selected ? "text-sky-600" : "text-ink-muted"} aria-hidden />
          <span className="truncate text-sm font-medium text-ink">{node.label}</span>
        </span>
        <ReviewBadge node={node} />
      </div>
      <Measure name="Height above floor" value={heightLabel(assessment)} />
      <Measure name="Route from chair" value={routeLabel(assessment)} />
      <span className={`flex items-center gap-1.5 text-xs font-medium ${reach.tint}`}>
        <reach.Icon size={14} weight="fill" aria-hidden />
        {reach.label}
      </span>
    </button>
  );
}

type ReachKey = "minReachHeight" | "maxReachHeight" | "maxReachDistance";

/** One reach limit the owner sets for themselves. */
function ReachSlider({
  name,
  field,
  min,
  max,
  profile,
  onProfileChange,
}: {
  name: string;
  field: ReachKey;
  min: number;
  max: number;
  profile: WheelchairProfile;
  onProfileChange: (profile: WheelchairProfile) => void;
}) {
  const value = profile.reach?.[field] ?? REACH_DEFAULTS[field];
  return (
    <label className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
      <span className="text-xs text-ink-muted">{name}</span>
      <span className="font-mono text-xs tabular-nums text-ink">{value.toFixed(2)} m</span>
      <input
        className="col-span-2 w-full accent-sky-600"
        type="range"
        min={min}
        max={max}
        step={0.01}
        value={value}
        onChange={(event) =>
          onProfileChange({
            ...profile,
            reach: { ...REACH_DEFAULTS, ...profile.reach, [field]: Number(event.target.value) },
          })
        }
      />
    </label>
  );
}

function ReachSettings({
  profile,
  onProfileChange,
}: {
  profile: WheelchairProfile;
  onProfileChange: (profile: WheelchairProfile) => void;
}) {
  return (
    <details className="rounded-lg bg-sheet/95 px-3 py-2 shadow-sm ring-1 ring-rule/60">
      <summary className="cursor-pointer text-sm font-medium text-ink">Your reach</summary>
      <div className="mt-3 grid gap-3">
        <ReachSlider name="Lowest you can reach" field="minReachHeight" min={0.1} max={0.8} profile={profile} onProfileChange={onProfileChange} />
        <ReachSlider name="Highest you can reach" field="maxReachHeight" min={0.8} max={1.8} profile={profile} onProfileChange={onProfileChange} />
        <ReachSlider name="How far you can reach" field="maxReachDistance" min={0.2} max={1.2} profile={profile} onProfileChange={onProfileChange} />
      </div>
    </details>
  );
}

function StatusCell({
  heading,
  look,
  measure,
}: {
  heading: string;
  look: { Icon: typeof CheckCircle; tint: string; label: string };
  measure: string | null;
}) {
  return (
    <div className="rounded-lg bg-rule/20 p-2.5">
      <p className="text-xs text-ink-muted">{heading}</p>
      <p className={`mt-1 flex items-center gap-1.5 text-sm font-medium ${look.tint}`}>
        <look.Icon size={16} weight="fill" aria-hidden />
        {look.label}
      </p>
      {measure ? <p className="mt-1 font-mono text-xs tabular-nums text-ink-muted">{measure}</p> : null}
    </div>
  );
}

function EvidenceNote({ node }: { node: SceneNode }) {
  const observed = node.attachment?.observations?.[0];
  if (!observed) return null;
  return (
    <div className="rounded-lg bg-rule/20 p-2.5">
      <p className="text-sm font-medium text-ink">Photographed in frame {observed.frame_id}</p>
      <p className="mt-0.5 text-xs text-ink-muted">
        The detector was {(observed.confidence * 100).toFixed(0)}% sure of what it saw.
      </p>
    </div>
  );
}

function ReviewButtons({
  nodeId,
  onUpdateReviewStatus,
}: {
  nodeId: string;
  onUpdateReviewStatus: (nodeId: string, status: "confirmed_by_user" | "rejected_by_user") => void;
}) {
  return (
    <div className="flex items-center gap-2 border-t border-rule/60 pt-3">
      <Button variant="quiet" className="text-emerald-700 dark:text-emerald-400" onClick={() => onUpdateReviewStatus(nodeId, "confirmed_by_user")}>
        <ThumbsUp size={16} aria-hidden />
        That is an outlet
      </Button>
      <Button variant="quiet" className="text-rose-700 dark:text-rose-400" onClick={() => onUpdateReviewStatus(nodeId, "rejected_by_user")}>
        <ThumbsDown size={16} aria-hidden />
        That is not
      </Button>
    </div>
  );
}

function UnsettledList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <div className="rounded-lg bg-amber-50 p-2.5 dark:bg-amber-950/30">
      <p className="text-sm font-medium text-amber-900 dark:text-amber-200">What the scan could not settle</p>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-amber-900 dark:text-amber-300">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function heightSentence(height: number | null): string {
  if (height === null) return "no floor modelled here";
  return `${height.toFixed(2)} m (${(height * INCHES_PER_METER).toFixed(0)}″)`;
}

function OutletDetail({
  node,
  assessment,
  onPreviewApproach,
  onUpdateReviewStatus,
}: {
  node: SceneNode;
  assessment: OutletAccessibilityAssessment;
  onPreviewApproach?: (point: MotionPoint) => void;
  onUpdateReviewStatus?: (nodeId: string, status: "confirmed_by_user" | "rejected_by_user") => void;
}) {
  const { approachCandidate, approachStatus, approachDistance, reachDistance } = assessment;
  const canDrive = approachCandidate && approachStatus === "clear" && onPreviewApproach;
  return (
    <div className="flex flex-col gap-3 rounded-xl bg-sheet p-4 shadow-sm ring-1 ring-rule">
      <h3 className="text-sm font-semibold text-ink">{node.label}</h3>
      <Measure name="Height above the floor beneath it" value={heightSentence(assessment.targetHeightAboveFloor)} />

      <EvidenceNote node={node} />

      <div className="grid grid-cols-2 gap-2">
        <StatusCell
          heading="Getting there"
          look={APPROACH_LOOK[approachStatus]}
          measure={approachDistance === null ? null : `${approachDistance.toFixed(1)} m of travel`}
        />
        <StatusCell
          heading="Reaching it"
          look={REACH_LOOK[assessment.reachStatus]}
          measure={reachDistance === null ? null : `${reachDistance.toFixed(2)} m away`}
        />
      </div>

      {canDrive ? (
        <Button variant="primary" className="w-full" onClick={() => onPreviewApproach(approachCandidate)}>
          <NavigationArrow size={16} weight="bold" aria-hidden />
          Drive the chair to this outlet
        </Button>
      ) : null}

      <UnsettledList reasons={assessment.unresolvedReasons} />

      <div className="rounded-lg bg-rule/20 p-2.5">
        <p className="text-sm font-medium text-ink">What no scan can tell you</p>
        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-ink-muted">
          {assessment.disclaimers.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      {onUpdateReviewStatus ? <ReviewButtons nodeId={node.id} onUpdateReviewStatus={onUpdateReviewStatus} /> : null}
    </div>
  );
}

function NothingFound() {
  return (
    <div className="rounded-xl border border-dashed border-rule p-6 text-center">
      <Question size={32} className="mx-auto mb-2 text-ink-muted/60" aria-hidden />
      <p className="text-sm font-medium text-ink">No outlet was photographed in this scan</p>
      <p className="mt-1 text-xs text-ink-muted">
        An outlet has to be seen head-on to be placed. Walking the lower walls again, slowly, is what usually finds them.
      </p>
    </div>
  );
}

export function OutletPanel({
  scene,
  selectedId,
  onSelectNode,
  wheelchairPos,
  wheelchairProfile,
  onProfileChange,
  onPreviewApproach,
  onUpdateReviewStatus,
}: OutletPanelProps) {
  const geometry = useMemo(() => wheelchairMotionGeometry(scene.nodes), [scene.nodes]);
  const outletNodes = useMemo(() => scene.nodes.filter(isOutletNode), [scene.nodes]);

  const assessments = useMemo(() => {
    const found = new Map<string, OutletAccessibilityAssessment>();
    for (const node of outletNodes) {
      found.set(node.id, assessOutletAccessibility(wheelchairPos, node, geometry, wheelchairProfile));
    }
    return found;
  }, [outletNodes, wheelchairPos, geometry, wheelchairProfile]);

  const selectedNode = outletNodes.find((node) => node.id === selectedId) ?? null;
  const assessment = selectedNode ? assessments.get(selectedNode.id) ?? null : null;

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
          <Lightning size={20} className="text-amber-500" weight="fill" aria-hidden />
          Outlets
        </h2>
        <span className="rounded-full bg-rule/50 px-2 py-0.5 text-xs font-medium text-ink-muted">
          {outletNodes.length} photographed
        </span>
      </div>

      <p className="text-xs text-ink-muted">
        Each of these was seen in a photograph and placed on the surface it is fixed to. Getting there and
        reaching it are worked out from where the chair is now and the reach you set below.
      </p>

      {outletNodes.length === 0 ? (
        <NothingFound />
      ) : (
        <div className="flex flex-col gap-2">
          {outletNodes.map((node) => (
            <OutletRow
              key={node.id}
              node={node}
              assessment={assessments.get(node.id)}
              selected={node.id === selectedId}
              onSelect={() => onSelectNode(node.id === selectedId ? null : node.id)}
            />
          ))}
        </div>
      )}

      {onProfileChange ? <ReachSettings profile={wheelchairProfile} onProfileChange={onProfileChange} /> : null}

      {selectedNode && assessment ? (
        <OutletDetail
          node={selectedNode}
          assessment={assessment}
          onPreviewApproach={onPreviewApproach}
          onUpdateReviewStatus={onUpdateReviewStatus}
        />
      ) : null}
    </div>
  );
}
