"use client";

import { Canvas } from "@react-three/fiber";
import { Component, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { clipPlanes, zoomRange, type ViewerPose } from "@/lib/camera";
import type { Focus } from "@/lib/findings";
import type { NodeTextureCoverage, SceneGraph, SceneNode } from "@/types/contracts";
import { FindingAnnotation } from "./Annotation";
import { type FoundHandles, FoundOutlines } from "./FoundOutlines";
import { CameraRig } from "./CameraRig";
import { MODEL, outcomeColor, SCAN_CUT_HEIGHT } from "./palette";
import { type ArrangeHandlers, BoxShopModel, GlbShopModel } from "./ShopModel";
import { LidarShopModel } from "./LidarShopModel";
import { CombinedRooms } from "./CombinedRooms";
import { PaintedScan, type ScanPieces } from "./PaintedScan";
import { GaussianSplatScan } from "./GaussianSplatScan";
import { ShopLights } from "./ShopLights";
import type { CapturedSplatAsset } from "@/lib/captured-splats";
import type { RoomGroup, RoomPlacement } from "@/lib/room-groups";
import { lightCasts } from "@/lib/scan-shadows";
import { shownSurface, type ShownSurface } from "@/lib/viewer-source";
import type { MotionPoint } from "@/lib/motion-vector";
import type { WheelchairProfile } from "@/lib/wheelchair-profile";
import { StaffAreas, type StaffHandles } from "./StaffAreas";
import { type RouteHandles, StopMarkers } from "./StopMarkers";
import { WheelchairController, type WheelchairState } from "./WheelchairController";

type ViewerProps = {
  scene: SceneGraph;
  highlightNodeIds?: string[] | null;
  /** Every piece stays visible and tappable while one is outlined, for choosing a piece. */
  picking?: boolean;
  /** The walks of a combined scan and where they have been dragged, drawn as captured surface. */
  combinedRooms?: { rooms: RoomGroup[]; placements: Record<string, RoomPlacement> } | null;
  exported: SceneGraph;
  arrange: ArrangeHandlers | null;
  dragAllNodes?: boolean;
  lightweight?: boolean;
  route: RouteHandles | null;
  /** Floor only staff use, hatched, and draggable while the owner shapes the path. */
  staff?: StaffHandles | null;
  /** The pieces the scan found, outlined and linked to the owner's list of them. */
  found?: FoundHandles | null;
  /** Pixels to slide the picture right, clear of a panel laid over the canvas's left edge. */
  frameShift?: number;
  dragging: boolean;
  cutWalls: boolean;
  glbUrl: string | null;
  lidarUrl: string | null;
  pose: ViewerPose;
  selected: Focus | null;
  onSelectNode: (nodeId: string) => void;
  onClearSelection: () => void;
  materialMode: "reconstructed" | "captured" | "plain" | "coverage" | "scan" | "splat";
  scanGlbUrl: string | null;
  splatAssets?: CapturedSplatAsset[];
  onSplatError?: (message: string | null) => void;
  staleNodeIds: string[];
  coverage: NodeTextureCoverage[];
  wheelchairMode?: boolean;
  wheelchairProfile?: WheelchairProfile;
  onWheelchairStateChange?: (state: WheelchairState) => void;
  wheelchairDockTarget?: SceneNode | null;
  wheelchairDockDestination?: MotionPoint | null;
  onClearWheelchairDock?: () => void;
  onWheelchairSelectNode?: (node: SceneNode) => void;
  onWheelchairExit?: () => void;
  /** Where the walk-through starts and which way it faces. Left out, it starts in a corner facing -z. */
  wheelchairStart?: WheelchairStart | null;
};

export type WheelchairStart = { position: [number, number, number]; yaw: number };


class GlbFallback extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

const GROUND_PLANE_ARGS: [number, number] = [160, 160];
const BG_COLOR_ARGS: [string] = ["#f6f5f1"];
const DPR_DEFAULT: [number, number] = [1, 2];
const DPR_LIGHTWEIGHT: [number, number] = [1, 1];
const DPR_SPLATS: [number, number] = [1, 1.5];
const EMPTY_STALE_SET = new Set<string>();
const NOTHING_TO_DO = () => {};

type ShopSurfacesProps = Pick<ViewerProps, "scene" | "exported" | "arrange" | "dragAllNodes" | "lightweight" | "glbUrl" | "scanGlbUrl" | "splatAssets" | "onSplatError" | "lidarUrl" | "selected" | "onSelectNode" | "cutWalls" | "materialMode" | "staleNodeIds" | "coverage" | "highlightNodeIds" | "combinedRooms" | "picking"> & { surface: ShownSurface };

/** The boxes have no captured surface to show, so the captured modes fall back to plain material on them. */
function boxMaterialMode(mode: ViewerProps["materialMode"]) {
  return mode === "scan" || mode === "splat" ? ("plain" as const) : mode;
}

/** The captured room for the surfaces that show one, or null for the boxes. */
function capturedRoom(props: ShopSurfacesProps, boxes: ReactNode, picking: ReactNode, pieces: ScanPieces | null): ReactNode | null {
  const { surface, scanGlbUrl, splatAssets } = props;
  if (surface === "splats" && splatAssets) {
    return <SplatRoom key={JSON.stringify(splatAssets)} assets={splatAssets} fallback={boxes} picking={picking} onError={props.onSplatError} />;
  }
  if (surface === "scan" && scanGlbUrl) {
    return <ScannedRoom url={scanGlbUrl} whileLoading={boxes} picking={picking} cutAbove={props.cutWalls ? SCAN_CUT_HEIGHT : null} pieces={pieces} shadows={!props.lightweight} />;
  }
  return null;
}

/**
 * While furniture can be dragged, the movable pieces as they were scanned, to
 * cut out of the scan, and the layout they now stand in. The cut list only
 * changes with the scan, so dragging moves pieces without cutting again.
 */
function useScanPieces(exported: SceneGraph, placed: SceneGraph, arranging: boolean): ScanPieces | null {
  const carve = useMemo(() => (arranging ? exported.nodes.filter((node) => node.kind === "object") : null), [exported, arranging]);
  return useMemo(() => (carve ? { carve, placed } : null), [carve, placed]);
}

function ShopSurfaces(props: ShopSurfacesProps) {
  const { exported, glbUrl, lidarUrl, materialMode, selected, staleNodeIds, coverage, scene, arrange, dragAllNodes, lightweight, onSelectNode, cutWalls, highlightNodeIds, picking: choosing } = props;

  /* Picking a walk in the Combine panel has to show which one it is, or four
     grey floor plans look alike and the one being dragged is anybody's guess.
     The highlight outranks a selected finding because while rooms are being
     placed, that is what the owner is working on. */
  const focus = useMemo(() => {
    if (highlightNodeIds) return new Set<string>(highlightNodeIds);
    return selected?.locus ? new Set<string>(selected.locus.node_ids) : null;
  }, [highlightNodeIds, selected]);
  const staleSet = useMemo(() => (staleNodeIds ? new Set(staleNodeIds) : EMPTY_STALE_SET), [staleNodeIds]);
  const coverageMap = useMemo(() => new Map(coverage.map((entry) => [entry.node_id, entry.textured_fraction])), [coverage]);

  const modelProps = useMemo(() => ({
    shown: scene,
    focus,
    focusColor: highlightNodeIds || !selected ? MODEL.accent : outcomeColor(selected.outcome),
    onSelectNode,
    arrange,
    dragAllNodes,
    lightweight,
    cutWalls,
    materialMode: boxMaterialMode(materialMode),
    staleNodeIds: staleSet,
    coverage: coverageMap,
    picking: choosing,
  }), [scene, focus, selected, highlightNodeIds, onSelectNode, arrange, dragAllNodes, lightweight, cutWalls, materialMode, staleSet, coverageMap, choosing]);

  const pieces = useScanPieces(exported, scene, arrange !== null);
  const boxes = <BoxShopModel {...modelProps} />;
  const picking = <BoxShopModel {...modelProps} pickOnly />;
  if (props.surface === "combined" && props.combinedRooms) {
    return (
      <>
        {boxes}
        <CombinedRooms rooms={props.combinedRooms.rooms} placements={props.combinedRooms.placements} />
      </>
    );
  }
  const captured = capturedRoom(props, boxes, picking, pieces);
  if (captured) return captured;
  const reconstructed = !glbUrl ? boxes : (
    <GlbFallback key={glbUrl} fallback={boxes}>
      <Suspense fallback={boxes}>
        <GlbShopModel url={glbUrl} exported={exported} {...modelProps} />
      </Suspense>
    </GlbFallback>
  );
  return <group>{lidarUrl && <LidarShopModel key={lidarUrl} url={lidarUrl} />}{reconstructed}</group>;
}

function SplatRoom({ assets, fallback, picking, onError }: { assets: CapturedSplatAsset[]; fallback: ReactNode; picking: ReactNode; onError?: (message: string | null) => void }) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => { onError?.(null); }, [onError]);
  return <group>
    {(!ready || failed) && fallback}
    {ready && !failed && picking}
    {!failed && <GaussianSplatScan assets={assets} onReady={() => { setReady(true); onError?.(null); }} onError={() => {
      setFailed(true);
      onError?.("Photographic reconstruction couldn’t load on this device.");
    }} />}
  </group>;
}

/**
 * The room as it was scanned, shown instead of the boxes rather than with them.
 *
 * Two surfaces a few centimetres apart fight over every pixel, and the boxes
 * miss the real surfaces by inches, so drawing both at once gives a room that
 * flickers. The boxes stand in only while the scan is on its way. Once it is
 * there they stay as invisible targets, so tapping the scanned counter still
 * picks the counter, and a picked piece is outlined over the scan.
 */
function ScannedRoom({ url, whileLoading, picking, cutAbove, pieces, shadows }: { url: string; whileLoading: ReactNode; picking: ReactNode; cutAbove: number | null; pieces: ScanPieces | null; shadows: boolean }) {
  return (
    <group>
      <GlbFallback key={url} fallback={whileLoading}>
        <Suspense fallback={whileLoading}><PaintedScan url={url} cutAbove={cutAbove} pieces={pieces} shadows={shadows} />{picking}</Suspense>
      </GlbFallback>
    </group>
  );
}

/**
 * Splats are expensive enough to pay for with resolution and antialiasing; the boxes are not.
 * A lightweight device draws no shadows at all; elsewhere they are filtered, so their edges are soft.
 */
function canvasTuning(lightweight: boolean | undefined, splatAssets: CapturedSplatAsset[] | undefined) {
  const splatting = Boolean(splatAssets?.length);
  return {
    dpr: lightweight ? DPR_LIGHTWEIGHT : splatting ? DPR_SPLATS : DPR_DEFAULT,
    antialias: !splatting,
    shadows: lightweight ? false : ("percentage" as const),
  };
}

function hasCombinedMeshes(combinedRooms: ViewerProps["combinedRooms"]): boolean {
  return Boolean(combinedRooms?.rooms.some((room) => room.scan_glb_url));
}

/** Which surface the room is drawn as, and whether the light casts onto it. */
function lighting({ materialMode, splatAssets, scanGlbUrl, combinedRooms, arrange, lightweight }: ViewerProps) {
  const surface = shownSurface({ materialMode, hasSplats: Boolean(splatAssets?.length), hasScanGlb: scanGlbUrl !== null, combined: hasCombinedMeshes(combinedRooms) });
  return { surface, castShadow: !lightweight && lightCasts(surface, arrange !== null) };
}

type WheelchairProps = Pick<ViewerProps, "scene" | "wheelchairMode" | "wheelchairProfile" | "onWheelchairStateChange" | "wheelchairDockTarget" | "wheelchairDockDestination" | "onClearWheelchairDock" | "onWheelchairSelectNode" | "onWheelchairExit" | "wheelchairStart">;

function startProps(start: WheelchairStart | null | undefined) {
  return start ? { initialPosition: start.position, initialYaw: start.yaw } : {};
}

function Wheelchair({ scene, wheelchairMode, wheelchairProfile, onWheelchairStateChange, wheelchairDockTarget, wheelchairDockDestination, onClearWheelchairDock, onWheelchairSelectNode, onWheelchairExit, wheelchairStart }: WheelchairProps) {
  if (!wheelchairMode || !wheelchairProfile || !onWheelchairStateChange) return null;
  return (
    <WheelchairController
      active={wheelchairMode}
      scene={scene}
      profile={wheelchairProfile}
      onStateChange={onWheelchairStateChange}
      dockTarget={wheelchairDockTarget ?? null}
      dockDestination={wheelchairDockDestination ?? null}
      onClearDock={onClearWheelchairDock ?? NOTHING_TO_DO}
      onSelectNode={onWheelchairSelectNode ?? NOTHING_TO_DO}
      onExit={onWheelchairExit}
      {...startProps(wheelchairStart)}
    />
  );
}

/** What is drawn on the floor: staff-only areas under the customer path and its stops. */
function FloorPlanMarks({ route, staff }: { route: RouteHandles | null; staff: StaffHandles | null }) {
  return (
    <>
      {staff && <StaffAreas handles={staff} />}
      {route && <StopMarkers route={route} />}
    </>
  );
}

export default function Viewer(viewerProps: ViewerProps) {
  const {
    scene,
    lightweight,
    route,
    dragging,
    splatAssets,
    pose,
    selected,
    onClearSelection,
    wheelchairMode = false,
    wheelchairProfile,
    onWheelchairStateChange,
    wheelchairDockTarget = null,
    wheelchairDockDestination = null,
    onClearWheelchairDock,
    onWheelchairSelectNode,
    onWheelchairExit,
  } = viewerProps;
  const tuning = canvasTuning(lightweight, splatAssets);
  const { surface, castShadow } = lighting(viewerProps);
  return (
    <Canvas
      frameloop={wheelchairMode ? "always" : "demand"}
      dpr={tuning.dpr}
      shadows={tuning.shadows}
      camera={{ position: pose.position, fov: pose.fov, ...clipPlanes(scene) }}
      flat
      gl={{ antialias: tuning.antialias, localClippingEnabled: true }}
      onCreated={(state) => {
        if (process.env.NODE_ENV === "development") Object.assign(window, { __viewer: state });
        state.camera.lookAt(pose.target[0], pose.target[1], pose.target[2]);
      }}
      onPointerMissed={onClearSelection}
      aria-label="3D model of the shop"
    >
      <color attach="background" args={BG_COLOR_ARGS} />
      <ShopLights room={viewerProps.exported} castShadow={castShadow} />
      {!wheelchairMode && <CameraRig pose={pose} locked={dragging} bounds={null} zoom={zoomRange(scene)} frameShift={viewerProps.frameShift} />}
      <Wheelchair
        scene={scene}
        wheelchairMode={wheelchairMode}
        wheelchairProfile={wheelchairProfile}
        onWheelchairStateChange={onWheelchairStateChange}
        wheelchairDockTarget={wheelchairDockTarget}
        wheelchairDockDestination={wheelchairDockDestination}
        onClearWheelchairDock={onClearWheelchairDock}
        onWheelchairSelectNode={onWheelchairSelectNode}
        onWheelchairExit={onWheelchairExit}
        wheelchairStart={viewerProps.wheelchairStart}
      />
      <mesh rotation-x={-Math.PI / 2} position-y={-0.002} receiveShadow>
        <planeGeometry args={GROUND_PLANE_ARGS} />
        <meshStandardMaterial color={MODEL.ground} roughness={1} />
      </mesh>
      <ShopSurfaces {...viewerProps} surface={surface} />
      {selected && <FindingAnnotation finding={selected} />}
      <FloorPlanMarks route={route} staff={viewerProps.staff ?? null} />
      <FoundOutlines scene={scene} handles={viewerProps.found} />
    </Canvas>
  );
}
