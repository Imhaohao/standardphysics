"use client";

import dynamic from "next/dynamic";
import type { ArrangeHandlers } from "@/components/workspace/ShopModel";
import type { RouteHandles } from "@/components/workspace/StopMarkers";
import type { ViewerPose } from "@/lib/camera";
import type { Focus } from "@/lib/findings";
import type { SceneGraph } from "@/types/contracts";

const Viewer = dynamic(() => import("@/components/workspace/Viewer"), {
  ssr: false,
  loading: () => <div className="size-full animate-pulse bg-rule/40 motion-reduce:animate-none" />,
});

const NO_NODES: string[] = [];
const NO_COVERAGE: [] = [];

/** What the model shows for the step on screen: where the camera sits, what's picked, and what can be dragged. */
export type ModelSetup = {
  shown: SceneGraph;
  pose: ViewerPose;
  selected: Focus | null;
  highlight: string[] | null;
  picking: boolean;
  route: RouteHandles | null;
  arrange: ArrangeHandlers | null;
  dragging: boolean;
  onSelectNode: (nodeId: string) => void;
  onClear: () => void;
};

/** What to do with the model right now, said on the model itself. */
export function ModelCaption({ children }: { children: string }) {
  return (
    <p className="pointer-events-none absolute inset-x-4 top-4 w-fit max-w-[calc(100%-2rem)] rounded-xl bg-sheet/95 px-3 py-2 text-sm font-medium shadow-float">
      {children}
    </p>
  );
}

export function OwnerModel({ scene, glbUrl, setup, lightweight }: { scene: SceneGraph; glbUrl: string | null; setup: ModelSetup; lightweight: boolean }) {
  return (
    <Viewer
      scene={setup.shown}
      exported={scene}
      highlightNodeIds={setup.highlight}
      picking={setup.picking}
      arrange={setup.arrange}
      route={setup.route}
      dragging={setup.dragging}
      cutWalls
      glbUrl={glbUrl}
      lidarUrl={null}
      pose={setup.pose}
      selected={setup.selected}
      onSelectNode={setup.onSelectNode}
      onClearSelection={setup.onClear}
      materialMode={glbUrl ? "reconstructed" : "plain"}
      scanGlbUrl={null}
      staleNodeIds={NO_NODES}
      coverage={NO_COVERAGE}
      lightweight={lightweight}
    />
  );
}
