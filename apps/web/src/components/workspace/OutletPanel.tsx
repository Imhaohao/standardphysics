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

type OutletPanelProps = {
  scene: SceneGraph;
  selectedId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  wheelchairPos: MotionPoint | null;
  wheelchairProfile: WheelchairProfile;
  onPreviewApproach?: (point: MotionPoint) => void;
  onUpdateReviewStatus?: (nodeId: string, status: "confirmed_by_user" | "rejected_by_user") => void;
};

export function isOutletNode(node: SceneNode): boolean {
  if (node.kind === "whiteboard" || node.raw_category === "whiteboard") return false;
  if (node.kind === "outlet" || node.kind === "candidate_outlet") return true;
  if (node.attachment && (node.raw_category === "outlet" || node.attachment.review_status !== undefined)) {
    return node.kind !== "wall" && node.kind !== "floor" && node.kind !== "opening" && node.kind !== "door" && node.kind !== "window" && node.kind !== "object";
  }
  return false;
}

export function OutletPanel({
  scene,
  selectedId,
  onSelectNode,
  wheelchairPos,
  wheelchairProfile,
  onPreviewApproach,
  onUpdateReviewStatus,
}: OutletPanelProps) {
  const geometry = useMemo(() => wheelchairMotionGeometry(scene.nodes), [scene.nodes]);

  const outletNodes = useMemo(() => {
    return scene.nodes.filter(isOutletNode);
  }, [scene.nodes]);

  const selectedNode = useMemo(() => {
    return outletNodes.find((n) => n.id === selectedId) ?? null;
  }, [outletNodes, selectedId]);

  const assessment: OutletAccessibilityAssessment | null = useMemo(() => {
    if (!selectedNode) return null;
    return assessOutletAccessibility(
      wheelchairPos ?? { x: 0, z: 0 },
      selectedNode,
      geometry,
      wheelchairProfile
    );
  }, [selectedNode, wheelchairPos, geometry, wheelchairProfile]);

  return (
    <div className="flex flex-col gap-4 p-4 text-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Lightning className="h-5 w-5 text-amber-500" weight="fill" />
          <h2 className="text-base font-semibold text-ink">Photographed Outlets</h2>
        </div>
        <span className="rounded-full bg-rule/50 px-2 py-0.5 text-xs font-medium text-ink-muted">
          {outletNodes.length} found
        </span>
      </div>

      <p className="text-xs text-ink-muted">
        Identified from camera evidence and projected to support surfaces. Approach and reach are evaluated using your current wheelchair position and profile.
      </p>

      {outletNodes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-rule p-6 text-center text-ink-muted">
          <Question className="mx-auto mb-2 h-8 w-8 text-ink-muted/60" />
          <p className="font-medium">No outlets identified in this scan yet</p>
          <p className="mt-1 text-xs">
            Outlets require photographed evidence on surveyed walls. If an outlet was missed, try taking additional overlapping captures of the lower wall.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Select an outlet to inspect
          </label>
          <div className="flex flex-col gap-1.5">
            {outletNodes.map((node) => {
              const isSelected = node.id === selectedId;
              const isCandidate = node.kind === "candidate_outlet" || node.attachment?.review_status === "candidate";
              const isConfirmed = node.attachment?.review_status === "confirmed_by_user";
              const isRejected = node.attachment?.review_status === "rejected_by_user";

              return (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => onSelectNode(isSelected ? null : node.id)}
                  className={`flex items-center justify-between rounded-lg border p-2.5 text-left transition-colors ${
                    isSelected
                      ? "border-sky-500 bg-sky-50/50 shadow-sm dark:bg-sky-950/20"
                      : "border-rule/60 bg-sheet/80 hover:bg-sheet"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <MapPin className={`h-4 w-4 ${isSelected ? "text-sky-600" : "text-ink-muted"}`} />
                    <div>
                      <p className="font-medium text-ink">{node.label}</p>
                      <p className="text-[11px] text-ink-muted">
                        Height: {(node.transform.m[11] * INCHES_PER_METER).toFixed(0)}″ •{" "}
                        {node.attachment?.support_type === "lidar_surface" ? "LiDAR support" : "Inferred plane"}
                      </p>
                    </div>
                  </div>
                  <div>
                    {isRejected ? (
                      <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800">
                        Flagged wrong
                      </span>
                    ) : isConfirmed ? (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">
                        Confirmed
                      </span>
                    ) : isCandidate ? (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                        Candidate
                      </span>
                    ) : (
                      <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-800">
                        Observed
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {selectedNode && assessment && (
        <div className="mt-2 flex flex-col gap-3 rounded-xl border border-rule bg-sheet p-3.5 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-semibold text-ink">{selectedNode.label}</h3>
              <p className="text-xs text-ink-muted">
                Observed height above local floor: {assessment.targetHeightAboveFloor.toFixed(2)} m ({(assessment.targetHeightAboveFloor * INCHES_PER_METER).toFixed(0)}″)
              </p>
            </div>
          </div>

          {/* Observations / Evidence */}
          {selectedNode.attachment?.observations && selectedNode.attachment.observations.length > 0 && (
            <div className="rounded-lg bg-rule/30 p-2 text-xs">
              <p className="font-semibold text-ink">Photographic Evidence</p>
              <p className="text-[11px] text-ink-muted">
                Frame {selectedNode.attachment.observations[0].frame_id} • Confidence{" "}
                {(selectedNode.attachment.observations[0].confidence * 100).toFixed(0)}%
              </p>
            </div>
          )}

          {/* Approach & Reach Breakdown */}
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-rule/60 p-2">
              <p className="text-[10px] font-semibold uppercase text-ink-muted">Approach Route</p>
              <div className="mt-1 flex items-center gap-1.5">
                {assessment.approachStatus === "clear" ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-emerald-600" weight="fill" />
                    <span className="text-xs font-semibold text-emerald-700">Clear</span>
                  </>
                ) : assessment.approachStatus === "blocked" ? (
                  <>
                    <WarningCircle className="h-4 w-4 text-rose-600" weight="fill" />
                    <span className="text-xs font-semibold text-rose-700">Blocked</span>
                  </>
                ) : (
                  <>
                    <Question className="h-4 w-4 text-amber-600" weight="fill" />
                    <span className="text-xs font-semibold text-amber-700">Needs check</span>
                  </>
                )}
              </div>
              {assessment.approachDistance !== null && (
                <p className="mt-0.5 text-[11px] text-ink-muted">
                  Route: {assessment.approachDistance.toFixed(1)} m
                </p>
              )}
            </div>

            <div className="rounded-lg border border-rule/60 p-2">
              <p className="text-[10px] font-semibold uppercase text-ink-muted">Modeled Reach</p>
              <div className="mt-1 flex items-center gap-1.5">
                {assessment.reachStatus === "within_reach" ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-emerald-600" weight="fill" />
                    <span className="text-xs font-semibold text-emerald-700">Within reach</span>
                  </>
                ) : assessment.reachStatus === "outside_reach" ? (
                  <>
                    <WarningCircle className="h-4 w-4 text-rose-600" weight="fill" />
                    <span className="text-xs font-semibold text-rose-700">Outside reach</span>
                  </>
                ) : (
                  <>
                    <Question className="h-4 w-4 text-amber-600" weight="fill" />
                    <span className="text-xs font-semibold text-amber-700">Unknown profile</span>
                  </>
                )}
              </div>
              {assessment.reachDistance !== null && (
                <p className="mt-0.5 text-[11px] text-ink-muted">
                  Reach: {assessment.reachDistance.toFixed(2)} m
                </p>
              )}
            </div>
          </div>

          {/* Action: Preview Approach */}
          {assessment.approachCandidate && assessment.approachStatus === "clear" && onPreviewApproach && (
            <Button
              variant="primary"
              className="w-full text-xs"
              onClick={() => onPreviewApproach(assessment.approachCandidate!)}
            >
              <NavigationArrow className="mr-1.5 h-3.5 w-3.5" weight="bold" />
              Preview approach from chair position
            </Button>
          )}

          {/* Unresolved reasons */}
          {assessment.unresolvedReasons.length > 0 && (
            <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
              <p className="font-semibold">Unresolved conditions:</p>
              <ul className="mt-1 list-disc pl-4 text-[11px] space-y-0.5">
                {assessment.unresolvedReasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Disclaimers */}
          <div className="rounded-lg bg-rule/20 p-2 text-[10px] text-ink-muted">
            <p className="font-semibold text-ink">What this scan cannot establish:</p>
            <ul className="mt-1 list-disc pl-3.5 space-y-0.5">
              {assessment.disclaimers.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          </div>

          {/* User Review / Correction Flow */}
          {onUpdateReviewStatus && (
            <div className="mt-1 flex items-center gap-2 border-t border-rule/60 pt-2 text-xs">
              <span className="text-[11px] text-ink-muted">Your review:</span>
              <Button
                variant="quiet"
                className="h-7 px-2 text-xs text-emerald-700"
                onClick={() => onUpdateReviewStatus(selectedNode.id, "confirmed_by_user")}
              >
                <ThumbsUp className="mr-1 h-3 w-3" />
                Confirm
              </Button>
              <Button
                variant="quiet"
                className="h-7 px-2 text-xs text-rose-700"
                onClick={() => onUpdateReviewStatus(selectedNode.id, "rejected_by_user")}
              >
                <ThumbsDown className="mr-1 h-3 w-3" />
                Flag wrong
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
