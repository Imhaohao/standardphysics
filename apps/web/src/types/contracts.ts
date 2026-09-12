/**
 * Generated from packages/contracts by `npm run contracts`. Do not edit.
 * Change the Pydantic models instead, then regenerate.
 */

export interface StandardPhysicsContracts {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Annotation".
 */
export interface Annotation {
  kind: "dimension_line" | "region" | "path";
  label: string;
  point_inches: (number | null)[] | null;
  points: Vec3[];
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Vec3".
 */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "ApiError".
 */
export interface ApiError {
  error: string;
  need: string[] | null;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Artifact".
 */
export interface Artifact {
  bytes: number;
  id: string;
  kind: "room_usdz" | "room_json" | "room_metadata" | "walkthrough_mp4" | "frames" | "poses" | "coverage";
  sha256: string;
  stored_path: string | null;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Assessment".
 */
export interface Assessment {
  created_at: string;
  decision: Decision | null;
  findings: Finding[];
  graph_hash: string;
  graph_revision: number;
  id: string;
  pass_number: number;
  rulepack_version: string;
  scan_id: string;
  weave_run_url: string | null;
}
/**
 * TypeSafe's structured output, after validation.
 *
 * An action that fails validation authorizes nothing.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Decision".
 */
export interface Decision {
  action: "FIX" | "RESCAN_AREA" | "ASK_OWNER" | "ESCALATE" | "DONE";
  provider: string;
  question: string | null;
  rationale: string | null;
  target_finding_ids: string[];
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  check_id: string;
  citation: Citation;
  detail: string;
  fix: string | null;
  id: string;
  locus: Locus | null;
  measured_inches: number | null;
  outcome: "passes" | "problem" | "question";
  required_inches: number | null;
  title: string;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Citation".
 */
export interface Citation {
  authority: "ADA_2010" | "CBC" | "PAMC";
  edition: string;
  section: string;
  url: string | null;
}
/**
 * Where in the model this finding lives, and how to show it.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Locus".
 */
export interface Locus {
  annotation: Annotation;
  bbox_max: Vec3;
  bbox_min: Vec3;
  camera: CameraPose;
  node_ids: string[];
  point: Vec3;
  render_url: string | null;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "CameraPose".
 */
export interface CameraPose {
  fov_degrees: number;
  position: Vec3;
  target: Vec3;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Check".
 */
export interface Check {
  applies_to: string[];
  citation: Citation;
  id: string;
  threshold: number;
  tier: 1 | 2 | 3;
  title: string;
  unit: string;
  verified_by_human: boolean;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "ClearFloorResult".
 */
export interface ClearFloorResult {
  center: Vec3;
  fits: boolean;
  inches_deep: number;
  inches_wide: number;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "CreateScanRequest".
 */
export interface CreateScanRequest {
  device_model: string;
  duration_seconds: number;
  name: string;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "HeightResult".
 */
export interface HeightResult {
  inches: number;
  measured_at: Vec3;
  node_id: string;
}
/**
 * Row-major 4x4 transform.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Mat4".
 */
export interface Mat4 {
  /**
   * @minItems 16
   * @maxItems 16
   */
  m: [
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    number,
    ...number[]
  ];
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "NodeMove".
 */
export interface NodeMove {
  delta_rotation_z_degrees: number;
  delta_translation: Vec3;
  node_id: string;
}
/**
 * Movable nodes only. No resize, no fixture movement, no leaving the floor.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Proposal".
 */
export interface Proposal {
  base_graph_hash: string;
  id: string;
  inventory_after: {
    [k: string]: number;
  };
  inventory_before: {
    [k: string]: number;
  };
  moves: NodeMove[];
  rationale: string;
  targets: string[];
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "RulePack".
 */
export interface RulePack {
  checks: Check[];
  version: string;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Scan".
 */
export interface Scan {
  artifacts: Artifact[];
  content_hash: string | null;
  coverage: SurfaceCoverage[];
  created_at: string;
  device_model: string;
  duration_seconds: number;
  id: string;
  name: string;
  state: "uploading" | "measuring" | "checking" | "ready" | "failed";
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "SurfaceCoverage".
 */
export interface SurfaceCoverage {
  node_id: string;
  observed_fraction: number;
  viewpoint_count: number;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "ScanList".
 */
export interface ScanList {
  scans: Scan[];
}
/**
 * The routine we screen. Legs run between consecutive stops.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Scenario".
 */
export interface Scenario {
  name: string;
  /**
   * @minItems 2
   */
  stops: [Stop, Stop, ...Stop[]];
}
/**
 * A destination on a customer's route.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "Stop".
 */
export interface Stop {
  anchor_node_id: string | null;
  name: string;
  position: Vec3;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "SceneGraph".
 */
export interface SceneGraph {
  base_hash: string | null;
  nodes: SceneNode[];
  revision: number;
  scan_id: string;
}
/**
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "SceneNode".
 */
export interface SceneNode {
  dimensions: Vec3;
  id: string;
  kind: "wall" | "door" | "window" | "opening" | "floor" | "object";
  label: string;
  labeled_by: "roomplan" | "astra" | "owner";
  movable: boolean;
  parent_id: string | null;
  quality: "measured" | "needs_another_look" | "confirmed";
  raw_category: string;
  transform: Mat4;
}
/**
 * The bottleneck of a route leg, and where it is.
 *
 * This interface was referenced by `StandardPhysicsContracts`'s JSON-Schema
 * via the `definition` "WidthResult".
 */
export interface WidthResult {
  blocking_node_ids: string[];
  inches: number;
  needs_measurement: boolean;
  path: Vec3[];
  pinch_point: Vec3;
  reachable: boolean;
}
